const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function post(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  const projectId = `project-agent-orchestration-${Date.now()}`;
  await post('/api/projects', {
    project_id: projectId,
    name: 'agent-orchestration-check',
    initialPrompt: '',
  });

  const result = await post(`/api/chat/${projectId}/act`, {
    instruction: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
    displayInstruction: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
    travelCapabilityId: 'mixed_food_route',
  });

  const trace = Array.isArray(result.agentTrace) ? result.agentTrace : [];
  const keys = trace.map((entry) => entry.agent_key);
  const expected = [
    'intent_agent',
    'clarification_agent',
    'poi_retrieval_agent',
    'ugc_evidence_agent',
    'route_composition_agent',
    'constraint_judge_agent',
  ];

  assert(result.status === 'travel_plan_completed', `unexpected status: ${result.status}`);
  assert(trace.length >= expected.length, `expected at least ${expected.length} trace entries, got ${trace.length}`);
  for (const key of expected) assert(keys.includes(key), `missing trace entry for ${key}`);
  assert(result.sessionStateSummary?.candidate_counts?.culture >= 1, 'candidate summary missing culture count');
  assert(Array.isArray(result.travelItinerary?.agent_trace), 'travelItinerary should include agent_trace');
  assert(result.travelItinerary?.planning_response?.proposals?.[0]?.constraint_judgement, 'primary proposal should include constraint_judgement');

  console.log('[travel-agent-orchestration] passed');
  console.log(`trace: ${keys.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-agent-orchestration] failed:', error);
  process.exit(1);
});
