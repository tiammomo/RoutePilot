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

function proposal(result) {
  return result.travelItinerary?.planning_response?.proposals?.[0] || result.planning_response?.proposals?.[0] || null;
}

function names(result) {
  return proposal(result)?.ordered_poi_names || [];
}

function pois(result) {
  return proposal(result)?.pois || [];
}

function foodPois(result) {
  return pois(result).filter((poi) => poi.poi_type === 'food');
}

function routeDiff(result) {
  return result.travelItinerary?.planning_response?.route_patch_summary || result.planning_response?.route_patch_summary || {};
}

function hasAgent(result, agentKey) {
  return Array.isArray(result.agentTrace) && result.agentTrace.some((entry) => entry.agent_key === agentKey);
}

async function createProject(projectId, capabilityId = 'culture_route') {
  await post('/api/projects', {
    project_id: projectId,
    name: projectId,
    initialPrompt: '',
    travelCapabilityId: capabilityId,
  });
}

async function act(projectId, instruction, capabilityId = 'culture_route', suffix = Date.now().toString(36)) {
  return post(`/api/chat/${projectId}/act`, {
    instruction,
    displayInstruction: instruction,
    travelCapabilityId: capabilityId,
    requestId: `${projectId}-${suffix}`,
  });
}

async function assertArbitraryRouteAddition({
  label,
  seedGoal,
  adjustment,
  expectedPattern,
  capabilityId = 'culture_route',
}) {
  const projectId = `project-generic-additions-${label}-${Date.now().toString(36)}`;
  await createProject(projectId, capabilityId);
  const seed = await act(projectId, seedGoal, capabilityId, 'seed');
  const before = names(seed);
  assert(seed.status === 'travel_plan_completed', `${label}: seed should plan, got ${seed.status}`);
  assert(before.length >= 3, `${label}: seed should have at least 3 stops: ${before.join(' -> ')}`);

  const added = await act(projectId, adjustment, capabilityId, 'add');
  const after = names(added);
  assert(added.status === 'travel_replan_completed', `${label}: add should replan, got ${added.status}`);
  assert(after.some((name) => expectedPattern.test(name)), `${label}: add should include requested place: ${after.join(' -> ')}`);
  for (const original of before) assert(after.includes(original), `${label}: add should preserve original route stop: ${original}; before=${before.join(' -> ')} after=${after.join(' -> ')}`);
  assert(after.length >= before.length + 1, `${label}: route should grow after addition: ${before.join(' -> ')} => ${after.join(' -> ')}`);
  return { before, after };
}

async function main() {
  const cultureProjectId = `project-generic-additions-culture-${Date.now().toString(36)}`;
  await createProject(cultureProjectId, 'culture_route');
  const seed = await act(cultureProjectId, '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭', 'culture_route', 'seed');
  assert(seed.status === 'travel_plan_completed', `seed should plan, got ${seed.status}`);
  const before = names(seed);
  assert(before.length >= 3, `seed should have at least 3 stops: ${before.join(' -> ')}`);

  const genericAdd = await act(cultureProjectId, '再加一个顺路的景点，原来的点都保留', 'culture_route', 'generic-add');
  const genericAfter = names(genericAdd);
  const genericAdded = genericAfter.filter((name) => !before.includes(name));
  assert(genericAdd.status === 'travel_replan_completed', `generic add should replan, got ${genericAdd.status}`);
  assert(genericAfter.length === before.length + 1, `generic add should add exactly one stop: ${before.join(' -> ')} => ${genericAfter.join(' -> ')}`);
  for (const original of before) assert(genericAfter.includes(original), `generic add should preserve original stop: ${original}`);
  assert(genericAdded.length === 1, `generic add should expose exactly one added name: ${genericAdded.join(', ')}`);
  assert(!foodPois(genericAdd).some((poi) => genericAdded.includes(poi.name)), `generic scenic add should not add food: ${genericAdded[0]}`);
  assert(routeDiff(genericAdd).added?.includes(genericAdded[0]), 'generic add should write added stop to route_patch_summary');
  assert(hasAgent(genericAdd, 'route_composition_agent'), 'generic add should include route composition agent trace');

  const slashProjectId = `project-generic-additions-slash-${Date.now().toString(36)}`;
  await createProject(slashProjectId, 'culture_route');
  const slashSeed = await act(slashProjectId, '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭', 'culture_route', 'seed');
  const slashBefore = names(slashSeed);
  assert(slashSeed.status === 'travel_plan_completed', `slash seed should plan, got ${slashSeed.status}`);
  assert(slashBefore.length >= 3, `slash seed should have at least 3 stops: ${slashBefore.join(' -> ')}`);

  const slashAdd = await act(slashProjectId, '/再加一个顺路的景点，原来的点都保留', 'culture_route', 'slash-add');
  const slashAfter = names(slashAdd);
  assert(slashAdd.status === 'travel_replan_completed', `slash add should replan, got ${slashAdd.status}`);
  assert(slashAfter.length === slashBefore.length + 1, `slash add should add exactly one stop: ${slashBefore.join(' -> ')} => ${slashAfter.join(' -> ')}`);
  for (const original of slashBefore) assert(slashAfter.includes(original), `slash add should preserve original stop: ${original}`);

  const naturalProjectId = `project-generic-additions-natural-${Date.now().toString(36)}`;
  await createProject(naturalProjectId, 'culture_route');
  const naturalSeed = await act(naturalProjectId, '故宫附近文化路线，少走路，不吃饭', 'culture_route', 'seed');
  const naturalBefore = names(naturalSeed);
  assert(naturalSeed.status === 'travel_plan_completed', `natural seed should plan, got ${naturalSeed.status}`);
  assert(naturalBefore.length >= 3, `natural seed should have at least 3 stops: ${naturalBefore.join(' -> ')}`);

  const naturalAdd = await act(naturalProjectId, '我有点想去长城', 'culture_route', 'natural-add-great-wall');
  const naturalAfter = names(naturalAdd);
  assert(naturalAdd.status === 'travel_replan_completed', `natural named add should replan, got ${naturalAdd.status}`);
  assert(naturalAfter.some((name) => /长城|八达岭/.test(name)), `natural named add should include Great Wall: ${naturalAfter.join(' -> ')}`);
  for (const original of naturalBefore) assert(naturalAfter.includes(original), `natural named add should preserve original stop: ${original}`);
  assert(!naturalAfter[0]?.includes('什刹海'), `natural named add should not fall back to Shichahai route: ${naturalAfter.join(' -> ')}`);

  const implicitProjectId = `project-generic-additions-implicit-${Date.now().toString(36)}`;
  await createProject(implicitProjectId, 'culture_route');
  const implicitSeed = await act(implicitProjectId, '故宫附近文化路线，少走路，不吃饭', 'culture_route', 'seed');
  const implicitBefore = names(implicitSeed);
  const implicitAdd = await act(implicitProjectId, '长城也不错？', 'culture_route', 'implicit-add-great-wall');
  const implicitAfter = names(implicitAdd);
  assert(implicitAdd.status === 'travel_replan_completed', `implicit named add should replan, got ${implicitAdd.status}`);
  assert(implicitAfter.some((name) => /长城|八达岭/.test(name)), `implicit named add should include Great Wall: ${implicitAfter.join(' -> ')}`);
  for (const original of implicitBefore) assert(implicitAfter.includes(original), `implicit named add should preserve original stop: ${original}`);

  const tiantanProjectId = `project-generic-additions-tiantan-${Date.now().toString(36)}`;
  await createProject(tiantanProjectId, 'culture_route');
  const tiantanSeed = await act(tiantanProjectId, '故宫附近文化路线，少走路，不吃饭', 'culture_route', 'seed');
  const tiantanBefore = names(tiantanSeed);
  const tiantanAdd = await act(tiantanProjectId, '还想去天坛公园', 'culture_route', 'natural-add-tiantan');
  const tiantanAfter = names(tiantanAdd);
  assert(tiantanAdd.status === 'travel_replan_completed', `tiantan add should replan, got ${tiantanAdd.status}`);
  assert(tiantanAfter.some((name) => /天坛公园/.test(name)), `tiantan add should include requested POI: ${tiantanAfter.join(' -> ')}`);
  for (const original of tiantanBefore) assert(tiantanAfter.includes(original), `tiantan add should preserve original stop: ${original}`);

  const universalProjectId = `project-generic-additions-universal-${Date.now().toString(36)}`;
  await createProject(universalProjectId, 'culture_route');
  const universalSeed = await act(universalProjectId, '故宫附近文化路线，少走路，不吃饭', 'culture_route', 'seed');
  const universalBefore = names(universalSeed);
  const universalAdd = await act(universalProjectId, '能不能把环球影城也放进去', 'culture_route', 'natural-add-universal');
  const universalAfter = names(universalAdd);
  assert(universalAdd.status === 'travel_replan_completed', `universal add should replan, got ${universalAdd.status}`);
  assert(universalAfter.some((name) => /环球影城/.test(name)), `universal add should include requested arbitrary place: ${universalAfter.join(' -> ')}`);
  for (const original of universalBefore) assert(universalAfter.includes(original), `universal add should preserve original stop: ${original}`);

  const unknownProjectId = `project-generic-additions-unknown-${Date.now().toString(36)}`;
  await createProject(unknownProjectId, 'culture_route');
  const unknownSeed = await act(unknownProjectId, '故宫附近文化路线，少走路，不吃饭', 'culture_route', 'seed');
  const unknownBefore = names(unknownSeed);
  const unknownAdd = await act(unknownProjectId, '顺便去某某小众展馆', 'culture_route', 'natural-add-unknown');
  const unknownAfter = names(unknownAdd);
  const unknownPois = pois(unknownAdd);
  assert(unknownAdd.status === 'travel_replan_completed', `unknown add should replan, got ${unknownAdd.status}`);
  assert(unknownAfter.some((name) => /某某小众展馆/.test(name)), `unknown add should include fallback requested place: ${unknownAfter.join(' -> ')}`);
  assert(unknownPois.some((poi) => /某某小众展馆/.test(poi.name) && Array.isArray(poi.planning_tags) && poi.planning_tags.includes('needs_address_confirmation')), 'unknown add should mark fallback POI as needing address confirmation');
  for (const original of unknownBefore) assert(unknownAfter.includes(original), `unknown add should preserve original stop: ${original}`);

  const arbitraryRouteCases = [
    {
      label: 'qianmen-mixed-add-tiantan',
      capabilityId: 'mixed_food_route',
      seedGoal: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
      adjustment: '还想去天坛公园',
      expectedPattern: /天坛公园/,
    },
    {
      label: 'shichahai-culture-add-summer-palace',
      capabilityId: 'culture_route',
      seedGoal: '什刹海附近安排4小时文化路线，少走路，不吃饭',
      adjustment: '也想去颐和园',
      expectedPattern: /颐和园/,
    },
    {
      label: 'wangfujing-budget-add-unknown',
      capabilityId: 'budget_route',
      seedGoal: '王府井附近玩3小时，预算80以内，少走路，不吃饭',
      adjustment: '顺便去临时朋友推荐的小展馆',
      expectedPattern: /临时朋友推荐的小展馆/,
    },
  ];
  const arbitraryResults = [];
  for (const item of arbitraryRouteCases) {
    arbitraryResults.push({
      label: item.label,
      ...(await assertArbitraryRouteAddition(item)),
    });
  }

  const addLunchToCulture = await act(cultureProjectId, '再加一个顺路的午餐地点，原来的点都保留', 'culture_route', 'add-lunch');
  const lunchNames = names(addLunchToCulture);
  const lunchStops = foodPois(addLunchToCulture);
  assert(addLunchToCulture.status === 'travel_replan_completed', `add lunch to no-food route should replan, got ${addLunchToCulture.status}`);
  assert(lunchStops.length === 1, `add lunch should insert exactly one food stop: ${lunchNames.join(' -> ')}`);
  assert(lunchStops[0]?.meal_slot === 'lunch', `added food should be lunch: ${JSON.stringify(lunchStops[0])}`);
  for (const original of before) assert(lunchNames.includes(original), `add lunch should preserve original stop: ${original}`);

  const mealProjectId = `project-generic-additions-meal-${Date.now().toString(36)}`;
  await createProject(mealProjectId, 'mixed_food_route');
  const mealSeed = await act(mealProjectId, '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路', 'mixed_food_route', 'seed');
  assert(mealSeed.status === 'travel_plan_completed', `meal seed should plan, got ${mealSeed.status}`);
  assert(foodPois(mealSeed).length >= 1, 'meal seed should include a food stop');

  const ambiguousLunch = await act(mealProjectId, '再加一个顺路的午餐地点，原来的点都保留', 'mixed_food_route', 'ambiguous-lunch');
  assert(ambiguousLunch.status === 'travel_clarification_required', `existing lunch add should clarify, got ${ambiguousLunch.status}`);
  assert(ambiguousLunch.needsClarification === true, 'existing lunch add should mark needsClarification');
  assert(hasAgent(ambiguousLunch, 'clarification_agent'), 'existing lunch add should include clarification agent trace');

  console.log('[travel-generic-additions] passed');
  console.log(`generic add: ${before.join(' -> ')} => ${genericAfter.join(' -> ')}`);
  console.log(`natural named add: ${naturalBefore.join(' -> ')} => ${naturalAfter.join(' -> ')}`);
  console.log(`implicit named add: ${implicitBefore.join(' -> ')} => ${implicitAfter.join(' -> ')}`);
  console.log(`tiantan add: ${tiantanBefore.join(' -> ')} => ${tiantanAfter.join(' -> ')}`);
  console.log(`universal add: ${universalBefore.join(' -> ')} => ${universalAfter.join(' -> ')}`);
  console.log(`unknown add: ${unknownBefore.join(' -> ')} => ${unknownAfter.join(' -> ')}`);
  for (const item of arbitraryResults) {
    console.log(`${item.label}: ${item.before.join(' -> ')} => ${item.after.join(' -> ')}`);
  }
  console.log(`add lunch: ${lunchNames.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-generic-additions] failed:', error);
  process.exit(1);
});
