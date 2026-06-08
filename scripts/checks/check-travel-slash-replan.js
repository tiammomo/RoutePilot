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

async function main() {
  const projectId = `project-slash-replan-${Date.now().toString(36)}`;
  await post('/api/projects', {
    project_id: projectId,
    name: 'slash replan regression',
    initialPrompt: '前门附近玩4小时，中午吃饭，预算200以内，少走路',
    travelCapabilityId: 'mixed_food_route',
  });

  const seed = await post(`/api/chat/${projectId}/act`, {
    instruction: '前门附近玩4小时，中午吃饭，预算200以内，少走路',
    displayInstruction: '前门附近玩4小时，中午吃饭，预算200以内，少走路',
    isInitialPrompt: true,
    travelCapabilityId: 'mixed_food_route',
    requestId: `${projectId}-seed`,
  });
  if (seed.status !== 'travel_plan_completed') {
    throw new Error(`seed should create a travel plan, got ${seed.status}`);
  }

  const result = await post(`/api/chat/${projectId}/act`, {
    instruction: '/不去正阳门箭楼，换一个附近文化点',
    displayInstruction: '/不去正阳门箭楼，换一个附近文化点',
    isInitialPrompt: false,
    travelCapabilityId: 'mixed_food_route',
    requestId: `${projectId}-slash-replan`,
  });

  if (result.status !== 'travel_replan_completed') {
    throw new Error(`slash exclusion should replan the existing itinerary, got ${result.status}`);
  }

  console.log('[travel-slash-replan] passed');
}

main().catch((error) => {
  console.error('[travel-slash-replan] failed:', error);
  process.exit(1);
});
