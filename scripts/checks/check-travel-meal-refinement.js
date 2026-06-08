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

function stops(result) {
  return proposal(result)?.pois || [];
}

function mealStops(result) {
  return stops(result).filter((stop) => stop.poi_type === 'food' || stop.meal_slot === 'lunch');
}

function snackStops(result) {
  return stops(result).filter((stop) => {
    const mealType = String(stop.meal_type || '').toLowerCase();
    return stop.meal_slot === 'snack' || ['snack', 'coffee', 'dessert'].includes(mealType) || stop.is_coffee_stop;
  });
}

function routeDiff(result) {
  return result.travelItinerary?.planning_response?.route_patch_summary || result.planning_response?.route_patch_summary || {};
}

function hasJudge(result) {
  const primary = proposal(result);
  return Boolean(primary?.constraint_judgement);
}

async function createProject(projectId) {
  await post('/api/projects', {
    project_id: projectId,
    name: projectId,
    initialPrompt: '',
    travelCapabilityId: 'mixed_food_route',
  });
}

async function act(projectId, instruction, suffix) {
  return post(`/api/chat/${projectId}/act`, {
    instruction,
    displayInstruction: instruction,
    travelCapabilityId: 'mixed_food_route',
    requestId: `${projectId}-${suffix}`,
  });
}

async function main() {
  const projectId = `project-meal-refinement-${Date.now().toString(36)}`;
  await createProject(projectId);

  const seed = await act(projectId, '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路', 'seed');
  assert(seed.status === 'travel_plan_completed', `seed should plan, got ${seed.status}`);
  const beforeNames = names(seed);
  const seedMeal = mealStops(seed)[0];
  assert(seedMeal, `seed should include lunch: ${beforeNames.join(' -> ')}`);
  assert(hasJudge(seed), 'seed should include constraint judgement');

  const snack = await act(projectId, '保留当前午餐，再加一个预算50以内的小吃/下午茶', 'snack');
  const snackNames = names(snack);
  const snackFood = mealStops(snack).find((stop) => stop.name === seedMeal.name);
  const addedSnack = snackStops(snack).find((stop) => !beforeNames.includes(stop.name));
  assert(snack.status === 'travel_replan_completed', `snack refinement should replan, got ${snack.status}`);
  assert(snackFood, `snack refinement should preserve original lunch: ${seedMeal.name} => ${snackNames.join(' -> ')}`);
  assert(addedSnack, `snack refinement should add snack/coffee/dessert: ${snackNames.join(' -> ')}`);
  assert(addedSnack.meal_slot === 'snack', `added afternoon tea should be meal_slot=snack: ${JSON.stringify(addedSnack)}`);
  assert(!['meal', 'hotel_dining'].includes(String(addedSnack.meal_type || '').toLowerCase()), `added afternoon tea should not be formal meal: ${JSON.stringify(addedSnack)}`);
  assert(routeDiff(snack).added?.includes(addedSnack.name), 'snack refinement should write added snack to route_patch_summary');
  assert(hasJudge(snack), 'snack refinement should include constraint judgement');

  const replaceMeal = await act(projectId, '替换当前午餐，换成更适合午餐的地方', 'replace-meal');
  const replacementMeal = mealStops(replaceMeal)[0];
  const replaceNames = names(replaceMeal);
  assert(replaceMeal.status === 'travel_replan_completed', `meal replacement should replan, got ${replaceMeal.status}`);
  assert(replacementMeal, `meal replacement should keep a lunch stop: ${replaceNames.join(' -> ')}`);
  assert(replacementMeal.meal_slot === 'lunch' || replacementMeal.poi_type === 'food', `replacement should be food/lunch: ${JSON.stringify(replacementMeal)}`);
  assert(replacementMeal.name !== seedMeal.name, `meal replacement should replace original lunch: ${seedMeal.name}`);
  assert(routeDiff(replaceMeal).removed?.includes(seedMeal.name), 'meal replacement should write removed lunch to route_patch_summary');
  assert(routeDiff(replaceMeal).added?.includes(replacementMeal.name), 'meal replacement should write added lunch to route_patch_summary');
  assert(hasJudge(replaceMeal), 'meal replacement should include constraint judgement');

  console.log('[travel-meal-refinement] passed');
  console.log(`seed: ${beforeNames.join(' -> ')}`);
  console.log(`snack: ${snackNames.join(' -> ')}`);
  console.log(`replace meal: ${replaceNames.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-meal-refinement] failed:', error);
  process.exit(1);
});
