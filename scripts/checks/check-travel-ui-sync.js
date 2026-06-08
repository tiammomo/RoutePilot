const fs = require('fs/promises');
const path = require('path');

const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';
const projectsDir = path.resolve(process.env.PROJECTS_DIR || './data/projects');

async function post(pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${pathname} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

async function getJson(pathname) {
  const response = await fetch(`${baseUrl}${pathname}`);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${pathname} failed: ${response.status} ${text}`);
  }
  return JSON.parse(text);
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function firstProposal(itinerary) {
  return itinerary?.planning_response?.proposals?.[0] || null;
}

function names(itinerary) {
  return firstProposal(itinerary)?.ordered_poi_names || [];
}

async function act(projectId, instruction, suffix) {
  return post(`/api/chat/${projectId}/act`, {
    instruction,
    displayInstruction: instruction,
    travelCapabilityId: 'culture_route',
    requestId: `${projectId}-${suffix}`,
  });
}

async function main() {
  const projectId = `project-ui-sync-${Date.now().toString(36)}`;
  const projectPath = path.join(projectsDir, projectId);
  await post('/api/projects', {
    project_id: projectId,
    name: projectId,
    initialPrompt: '',
    travelCapabilityId: 'culture_route',
  });

  const seed = await act(projectId, '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭', 'seed');
  assert(seed.status === 'travel_plan_completed', `seed should plan, got ${seed.status}`);
  const before = names(seed.travelItinerary);

  const changed = await act(projectId, '把第二个点换成更少走路的室内点，其他地方不变', 'replace-second');
  assert(changed.status === 'travel_replan_completed', `replace should replan, got ${changed.status}`);
  const responseItinerary = changed.travelItinerary;
  const responseProposal = firstProposal(responseItinerary);
  const responseDiff = responseItinerary?.planning_response?.route_patch_summary;
  assert(responseProposal?.constraint_judgement, 'chat response should include constraint_judgement');
  assert(Array.isArray(responseProposal?.selection_reasons) && responseProposal.selection_reasons.length > 0, 'chat response should include selection_reasons');
  assert(responseItinerary?.planning_response?.llm_rerank, 'chat response should include llm_rerank');
  assert(typeof responseItinerary?.planning_response?.natural_language_explanation === 'string', 'chat response should include natural language explanation');
  assert(typeof responseItinerary?.planning_response?.generation_metrics?.database_recall_used === 'boolean', 'chat response should include database recall metric');
  assert(responseDiff?.removed?.includes(before[1]), 'chat response should include removed stop in route diff');
  assert(Array.isArray(changed.agentTrace) && changed.agentTrace.some((entry) => entry.agent_key === 'route_composition_agent'), 'chat response should include route_composition_agent trace');
  assert(Array.isArray(changed.agentTrace) && changed.agentTrace.some((entry) => entry.agent_key === 'database_recall_agent'), 'chat response should include database_recall_agent trace');
  assert(Array.isArray(changed.agentTrace) && changed.agentTrace.some((entry) => entry.agent_key === 'minimax_rerank_agent'), 'chat response should include minimax_rerank_agent trace');

  const artifactItinerary = await getJson(`/api/projects/${projectId}/artifact?path=${encodeURIComponent('data_file/final/itinerary-data.json')}`);
  const artifactTrace = await getJson(`/api/projects/${projectId}/artifact?path=${encodeURIComponent('.travelpilot/agent-trace.json')}`);
  const artifactState = await getJson(`/api/projects/${projectId}/artifact?path=${encodeURIComponent('.travelpilot/session-state.json')}`);
  const diskItinerary = await readJson(path.join(projectPath, 'data_file', 'final', 'itinerary-data.json'));
  const diskTrace = await readJson(path.join(projectPath, '.travelpilot', 'agent-trace.json'));

  assert(JSON.stringify(names(artifactItinerary)) === JSON.stringify(names(responseItinerary)), 'artifact API itinerary should match chat response route');
  assert(JSON.stringify(names(diskItinerary)) === JSON.stringify(names(responseItinerary)), 'disk itinerary should match chat response route');
  assert(JSON.stringify(artifactItinerary.planning_response.route_patch_summary) === JSON.stringify(responseDiff), 'artifact route diff should match chat response');
  assert(artifactItinerary.planning_response.proposals[0].constraint_judgement, 'artifact itinerary should include constraint_judgement');
  assert(Array.isArray(artifactItinerary.planning_response.proposals[0].selection_reasons), 'artifact itinerary should include selection_reasons');
  assert(artifactItinerary.planning_response.llm_rerank, 'artifact itinerary should include llm_rerank');
  assert(typeof artifactItinerary.planning_response.natural_language_explanation === 'string', 'artifact itinerary should include natural language explanation');
  assert(typeof artifactItinerary.planning_response.generation_metrics?.database_recall_used === 'boolean', 'artifact itinerary should include database recall metric');
  assert(Array.isArray(artifactTrace) && artifactTrace.length >= 6, 'artifact agent trace should include agent entries');
  assert(Array.isArray(artifactTrace) && artifactTrace.some((entry) => entry.agent_key === 'database_recall_agent'), 'artifact trace should include database recall agent');
  assert(Array.isArray(artifactTrace) && artifactTrace.some((entry) => entry.agent_key === 'minimax_rerank_agent'), 'artifact trace should include minimax rerank agent');
  assert(Array.isArray(diskTrace) && diskTrace.length === artifactTrace.length, 'disk agent trace should match artifact API trace length');
  assert(artifactState?.final_selected_proposals?.[0]?.constraint_judgement, 'session state should include judged proposal');

  console.log('[travel-ui-sync] passed');
  console.log(`before: ${before.join(' -> ')}`);
  console.log(`after: ${names(responseItinerary).join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-ui-sync] failed:', error);
  process.exit(1);
});
