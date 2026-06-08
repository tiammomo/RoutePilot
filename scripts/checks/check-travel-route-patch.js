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
  const projectId = `project-route-patch-${Date.now()}`;
  await post('/api/projects', { project_id: projectId, name: 'route-patch-check', initialPrompt: '' });

  const seed = await post(`/api/chat/${projectId}/act`, {
    instruction: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
    displayInstruction: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
    travelCapabilityId: 'culture_route',
  });
  const before = seed.travelItinerary.planning_response.proposals[0].ordered_poi_names;

  const changed = await post(`/api/chat/${projectId}/act`, {
    instruction: '把第二个点换成更少走路的室内点，其他地方不变',
    displayInstruction: '把第二个点换成更少走路的室内点，其他地方不变',
    travelCapabilityId: 'culture_route',
  });

  const after = changed.travelItinerary.planning_response.proposals[0].ordered_poi_names;
  const diff = changed.travelItinerary.planning_response.route_patch_summary;
  const patch = changed.agentTrace.find((entry) => entry.agent_key === 'route_composition_agent')?.payload_preview?.route_patch_summary;

  assert(changed.status === 'travel_replan_completed', `unexpected status: ${changed.status}`);
  assert(after[0] === before[0], 'first stop should stay');
  assert(after[1] !== before[1], 'second stop should change');
  assert(after[2] === before[2], 'third stop should stay');
  assert(Array.isArray(diff?.removed) && diff.removed.includes(before[1]), 'route_patch_summary should include removed stop');
  assert(Array.isArray(diff?.added) && diff.added.some((name) => !before.includes(name)), 'route_patch_summary should include added replacement');
  assert(patch, 'route composition agent payload should include route patch summary');

  console.log('[travel-route-patch] passed');
  console.log(`before: ${before.join(' -> ')}`);
  console.log(`after: ${after.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-route-patch] failed:', error);
  process.exit(1);
});
