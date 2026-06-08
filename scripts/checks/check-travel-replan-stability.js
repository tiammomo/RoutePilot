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

function planningOf(result) {
  return result.planning_response || result;
}

function proposalOf(result) {
  return planningOf(result).proposals?.[0] || null;
}

function namesOf(result) {
  return proposalOf(result)?.ordered_poi_names || [];
}

function idsOf(result) {
  return proposalOf(result)?.ordered_poi_ids || [];
}

function stopsOf(result) {
  return proposalOf(result)?.pois || [];
}

function patchOf(result) {
  return planningOf(result).route_patch_summary || planningOf(result).replan_metadata?.route_patch_summary || {};
}

function hasRisk(result, pattern) {
  return (proposalOf(result)?.risks || []).some((risk) => pattern.test(String(risk)));
}

function hasFood(result) {
  return stopsOf(result).some((stop) => stop.poi_type === 'food' || stop.meal_slot === 'lunch');
}

function isIndoorCultureName(name) {
  return /博物馆|美术馆|艺术中心|展览馆|展览|文化馆|科技馆/.test(String(name));
}

function assertTimeline(label, result) {
  const stops = stopsOf(result);
  assert(stops.length >= 3, `${label}: should include at least 3 POIs`);
  for (const stop of stops) {
    assert(/^\d{2}:\d{2}$/.test(String(stop.arrival_time || '')), `${label}: missing arrival_time for ${stop.name}`);
    assert(/^\d{2}:\d{2}$/.test(String(stop.departure_time || '')), `${label}: missing departure_time for ${stop.name}`);
  }
}

function assertPatchVisible(label, result) {
  const patch = patchOf(result);
  assert(Array.isArray(patch.kept), `${label}: route_patch_summary.kept should be visible`);
  assert(Array.isArray(patch.removed), `${label}: route_patch_summary.removed should be visible`);
  assert(Array.isArray(patch.added), `${label}: route_patch_summary.added should be visible`);
  assert(typeof patch.changed === 'boolean', `${label}: route_patch_summary.changed should be visible`);
}

function assertPreserved(label, before, after, ignored = new Set()) {
  for (const name of before) {
    if (ignored.has(name)) continue;
    assert(after.includes(name), `${label}: original POI should stay: ${name}; before=${before.join(' -> ')} after=${after.join(' -> ')}`);
  }
}

async function replan(seed, adjustmentText) {
  return post('/api/v1/travel/replan', {
    previous_request: planningOf(seed).request_snapshot,
    selected_proposal: proposalOf(seed),
    adjustment_text: adjustmentText,
  });
}

async function main() {
  const gugong = await post('/api/v1/travel/parse-and-plan', {
    goal: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
  });
  assertTimeline('gugong seed', gugong);
  assert(!hasFood(gugong), `gugong seed: should not include food: ${namesOf(gugong).join(' -> ')}`);
  assert(proposalOf(gugong).total_budget_estimate <= 100 || hasRisk(gugong, /budget|预算/i), 'gugong seed: budget should pass or expose risk');

  const qianmen = await post('/api/v1/travel/parse-and-plan', {
    goal: '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
  });
  assertTimeline('qianmen seed', qianmen);
  assert(hasFood(qianmen), `qianmen seed: should include lunch/food: ${namesOf(qianmen).join(' -> ')}`);
  assert(stopsOf(qianmen).filter((stop) => stop.poi_type !== 'food').length >= 2, 'qianmen seed: should include at least two culture/entertainment stops');
  assert(proposalOf(qianmen).total_budget_estimate <= 200 || hasRisk(qianmen, /budget|预算/i), 'qianmen seed: budget should pass or expose risk');

  const senior = await post('/api/v1/travel/parse-and-plan', {
    goal: '带老人去北海附近玩4小时，少走路，别太累，中午安排吃饭',
  });
  assertTimeline('senior seed', senior);
  const seniorRequest = planningOf(senior).request_snapshot || {};
  assert(seniorRequest.persona_id === 'senior_relaxed' || seniorRequest.walk_preference === 'low' || seniorRequest.preference_signals?.senior === true, 'senior seed: should apply senior or low-walk preference');
  assert(stopsOf(senior).every((stop) => stop.poi_type === 'food' || Number(stop.stay_minutes || 0) <= 120), 'senior seed: culture stops should stay reasonably short');

  const gugongBefore = namesOf(gugong);
  const targeted = await replan(gugong, '把第二个点换成更少走路的室内景点，其他地方不变');
  const targetedAfter = namesOf(targeted);
  assertPatchVisible('targeted replace', targeted);
  assert(targetedAfter[0] === gugongBefore[0], `targeted replace: first POI should stay: ${gugongBefore.join(' -> ')} => ${targetedAfter.join(' -> ')}`);
  assert(targetedAfter[1] !== gugongBefore[1], `targeted replace: second POI should change: ${targetedAfter.join(' -> ')}`);
  assert(targetedAfter[2] === gugongBefore[2], `targeted replace: third POI should stay: ${gugongBefore.join(' -> ')} => ${targetedAfter.join(' -> ')}`);
  assert(!targetedAfter.includes(gugongBefore[1]), `targeted replace: old second POI leaked back: ${gugongBefore[1]}`);
  assert(isIndoorCultureName(targetedAfter[1]), `targeted replace: replacement should be indoor culture: ${targetedAfter[1]}`);
  assert(patchOf(targeted).removed.includes(gugongBefore[1]), 'targeted replace: patch should expose removed stop');
  assert(patchOf(targeted).added.some((name) => !gugongBefore.includes(name)), 'targeted replace: patch should expose added replacement');

  const lastReplace = await replan(gugong, '把最后一个点换成室内景点，其他地方不变');
  const lastAfter = namesOf(lastReplace);
  assertPatchVisible('last replace', lastReplace);
  assert(lastAfter[lastAfter.length - 1] !== gugongBefore[gugongBefore.length - 1], `last replace: last stop should change: ${gugongBefore.join(' -> ')} => ${lastAfter.join(' -> ')}`);
  assertPreserved('last replace', gugongBefore.slice(0, -1), lastAfter);

  const genericAdd = await replan(gugong, '再加一个顺路的景点，原来的点都保留');
  const genericAfter = namesOf(genericAdd);
  const genericAdded = genericAfter.filter((name) => !gugongBefore.includes(name));
  assertPatchVisible('generic add', genericAdd);
  assert(genericAfter.length === gugongBefore.length + 1, `generic add: should add exactly one stop: ${gugongBefore.join(' -> ')} => ${genericAfter.join(' -> ')}`);
  assertPreserved('generic add', gugongBefore, genericAfter);
  assert(genericAdded.length === 1, `generic add: should expose exactly one added name: ${genericAdded.join(', ')}`);
  assert(!stopsOf(genericAdd).some((stop) => genericAdded.includes(stop.name) && stop.poi_type === 'food'), `generic add: scenic addition should not be food: ${genericAdded[0]}`);
  assert(patchOf(genericAdd).added.includes(genericAdded[0]), 'generic add: patch should expose added stop');

  for (const [label, text, pattern] of [
    ['tiantan', '还想去天坛公园', /天坛公园/],
    ['great-wall', '长城也不错？', /长城|八达岭/],
    ['universal', '能不能把环球影城也放进去', /环球影城/],
  ]) {
    const named = await replan(gugong, text);
    const namedAfter = namesOf(named);
    assertPatchVisible(`named add ${label}`, named);
    assert(namedAfter.some((name) => pattern.test(name)), `named add ${label}: requested POI should appear: ${namedAfter.join(' -> ')}`);
    assertPreserved(`named add ${label}`, gugongBefore, namedAfter);
  }

  const unknown = await replan(gugong, '顺便去某某小众展馆');
  const unknownAfter = namesOf(unknown);
  assertPatchVisible('unknown add', unknown);
  assert(unknownAfter.some((name) => /某某小众展馆/.test(name)), `unknown add: fallback place should appear: ${unknownAfter.join(' -> ')}`);
  assert(stopsOf(unknown).some((stop) => /某某小众展馆/.test(stop.name) && Array.isArray(stop.planning_tags) && stop.planning_tags.includes('needs_address_confirmation')), 'unknown add: fallback should need address confirmation');
  assertPreserved('unknown add', gugongBefore, unknownAfter);

  const conflict = await replan(gugong, '不要第二个点了，换成室内点，其他不变');
  const conflictAfter = namesOf(conflict);
  const conflictIds = new Set(idsOf(conflict));
  const requestSnapshot = planningOf(conflict).request_snapshot || {};
  const mustIds = new Set(requestSnapshot.must_include_poi_ids || []);
  const excludedIds = new Set(requestSnapshot.exclude_poi_ids || []);
  assertPatchVisible('exclude replace conflict', conflict);
  assert(!conflictAfter.includes(gugongBefore[1]), `exclude replace conflict: removed second POI leaked back: ${conflictAfter.join(' -> ')}`);
  assert(patchOf(conflict).removed.includes(gugongBefore[1]), 'exclude replace conflict: patch should expose removed stop');
  for (const id of excludedIds) {
    assert(!mustIds.has(id), `exclude replace conflict: excluded POI id still present in must_include_poi_ids: ${id}`);
    assert(!conflictIds.has(id), `exclude replace conflict: excluded POI id leaked into route: ${id}`);
  }

  console.log('[travel-replan-stability] passed');
  console.log(`targeted: ${gugongBefore.join(' -> ')} => ${targetedAfter.join(' -> ')}`);
  console.log(`generic add: ${gugongBefore.join(' -> ')} => ${genericAfter.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-replan-stability] failed:', error);
  process.exit(1);
});
