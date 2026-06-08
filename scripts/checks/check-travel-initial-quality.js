const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3001';

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

function planning(result) {
  return result.planning_response || result;
}

function proposal(result) {
  return planning(result).proposals?.[0] || null;
}

function stops(result) {
  return proposal(result)?.pois || [];
}

function names(result) {
  return proposal(result)?.ordered_poi_names || [];
}

function snapshot(result) {
  return planning(result).request_snapshot || {};
}

function foodStops(result) {
  return stops(result).filter((stop) => stop.poi_type === 'food' || stop.meal_slot === 'lunch');
}

function cultureStops(result) {
  return stops(result).filter((stop) => stop.poi_type !== 'food');
}

function hasRisk(result, pattern) {
  return (proposal(result)?.risks || []).some((risk) => pattern.test(String(risk)));
}

function assertTimeline(label, result) {
  for (const stop of stops(result)) {
    assert(/^\d{2}:\d{2}$/.test(String(stop.arrival_time || '')), `${label}: missing arrival_time for ${stop.name}`);
    assert(/^\d{2}:\d{2}$/.test(String(stop.departure_time || '')), `${label}: missing departure_time for ${stop.name}`);
  }
}

function overlapRatio(left, right) {
  const a = new Set(left);
  const b = new Set(right);
  return [...a].filter((name) => b.has(name)).length / Math.max(1, Math.min(a.size, b.size));
}

async function plan(label, goal) {
  const result = await post('/api/v1/travel/parse-and-plan', { goal });
  assert(proposal(result), `${label}: missing proposal`);
  assert(stops(result).length >= 3, `${label}: should include at least 3 stops`);
  assertTimeline(label, result);
  return result;
}

async function main() {
  const qianmen = await plan('qianmen mixed', '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路');
  const qianmenSnapshot = snapshot(qianmen);
  const qianmenFood = foodStops(qianmen);
  assert(qianmenSnapshot.route_mode === 'mixed', `qianmen: route_mode should be mixed, got ${qianmenSnapshot.route_mode}`);
  assert(qianmenFood.length >= 1, `qianmen: should include food: ${names(qianmen).join(' -> ')}`);
  assert(cultureStops(qianmen).length >= 2, `qianmen: should include at least 2 culture stops: ${names(qianmen).join(' -> ')}`);
  assert(!qianmenFood.every((stop) => stop.meal_type === 'coffee' || stop.is_coffee_stop), `qianmen: lunch should not be coffee-only: ${JSON.stringify(qianmenFood)}`);
  assert(proposal(qianmen).total_budget_estimate <= 200 || hasRisk(qianmen, /budget|预算/i), 'qianmen: budget should pass or expose risk');
  assert(qianmenSnapshot.preference_signals?.quality_food === true, 'qianmen: quality_food signal should be true');
  assert(qianmenSnapshot.preference_signals?.avoid_queue === true, 'qianmen: avoid_queue signal should be true');

  const gugong = await plan('gugong culture', '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭');
  assert(snapshot(gugong).route_mode === 'culture', `gugong: route_mode should be culture, got ${snapshot(gugong).route_mode}`);
  assert(foodStops(gugong).length === 0, `gugong: should not include food: ${names(gugong).join(' -> ')}`);
  assert(cultureStops(gugong).length >= 3, 'gugong: should include at least 3 culture stops');

  const senior = await plan('senior mixed', '带老人去北海附近玩4小时，少走路，别太累，中午安排吃饭');
  const seniorSnapshot = snapshot(senior);
  assert(seniorSnapshot.persona_id === 'senior_relaxed', `senior: expected senior_relaxed, got ${seniorSnapshot.persona_id}`);
  assert(seniorSnapshot.walk_preference === 'low', `senior: walk_preference should be low, got ${seniorSnapshot.walk_preference}`);
  assert(foodStops(senior).length >= 1, `senior: should include food: ${names(senior).join(' -> ')}`);
  assert(cultureStops(senior).every((stop) => Number(stop.stay_minutes || 0) <= 120), 'senior: culture stops should be reasonably short');

  const kids = await plan('kids mixed', '带小孩去北京玩4小时，亲子友好，中午吃饭');
  const kidsSnapshot = snapshot(kids);
  assert(kidsSnapshot.persona_id === 'family_kids', `kids: expected family_kids, got ${kidsSnapshot.persona_id}`);
  assert(foodStops(kids).length >= 1, `kids: should include food: ${names(kids).join(' -> ')}`);
  assert(stops(kids).some((stop) => /亲子|儿童|孩子|博物馆|科技|自然|低压力|family|children|museum/i.test(`${stop.name} ${(stop.planning_tags || []).join(' ')} ${(stop.evidence_tags || []).join(' ')}`)), `kids: should include family-friendly/culture POI: ${names(kids).join(' -> ')}`);

  const couple = await plan('couple mixed', '情侣在故宫附近玩4小时，想浪漫一点，中午吃饭');
  const coupleSnapshot = snapshot(couple);
  assert(coupleSnapshot.persona_id === 'couple_romantic', `couple: expected couple_romantic, got ${coupleSnapshot.persona_id}`);
  assert(foodStops(couple).length >= 1, `couple: should include food: ${names(couple).join(' -> ')}`);
  assert(overlapRatio(names(couple), names(senior)) < 1, `couple/senior routes should differ: ${names(couple).join(' -> ')}`);
  assert(overlapRatio(names(couple), names(kids)) < 1, `couple/kids routes should differ: ${names(couple).join(' -> ')}`);

  console.log('[travel-initial-quality] passed');
  for (const [label, result] of [['qianmen', qianmen], ['gugong', gugong], ['senior', senior], ['kids', kids], ['couple', couple]]) {
    console.log(`${label}: ${names(result).join(' -> ')}`);
  }
}

main().catch((error) => {
  console.error('[travel-initial-quality] failed:', error);
  process.exit(1);
});
