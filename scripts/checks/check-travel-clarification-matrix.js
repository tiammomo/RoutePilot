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

async function createProject(name) {
  const projectId = `project-${name}-${Date.now()}`;
  await post('/api/projects', { project_id: projectId, name, initialPrompt: '' });
  return projectId;
}

async function main() {
  const mealProject = await createProject('clarify-meal');
  await post(`/api/chat/${mealProject}/act`, {
    instruction: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
    displayInstruction: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
    travelCapabilityId: 'mixed_food_route',
  });
  const ambiguousMeal = await post(`/api/chat/${mealProject}/act`, {
    instruction: '再加一个顺路的午餐地点，原来的点都保留',
    displayInstruction: '再加一个顺路的午餐地点，原来的点都保留',
    travelCapabilityId: 'mixed_food_route',
  });
  assert(ambiguousMeal.status === 'travel_clarification_required', `meal clarification should trigger, got ${ambiguousMeal.status}`);
  assert(String(ambiguousMeal.message || '').includes('当前路线里已经有餐饮安排'), 'meal clarification message should mention existing meal');

  const removeProject = await createProject('clarify-remove');
  await post(`/api/chat/${removeProject}/act`, {
    instruction: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
    displayInstruction: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
    travelCapabilityId: 'culture_route',
  });
  const ambiguousRemove = await post(`/api/chat/${removeProject}/act`, {
    instruction: '不去这个地方，其他地方不变',
    displayInstruction: '不去这个地方，其他地方不变',
    travelCapabilityId: 'culture_route',
  });
  assert(ambiguousRemove.status === 'travel_clarification_required', `remove clarification should trigger, got ${ambiguousRemove.status}`);
  assert(String(ambiguousRemove.message || '').includes('当前路线包含'), 'remove clarification should list current route');

  console.log('[travel-clarification-matrix] passed');
}

main().catch((error) => {
  console.error('[travel-clarification-matrix] failed:', error);
  process.exit(1);
});
