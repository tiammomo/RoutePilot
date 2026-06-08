const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function post(pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${pathname} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function dailyRoutes(result) {
  const planning = result.travelItinerary?.planning_response || result.planning_response || result || {};
  return Array.isArray(planning.daily_itinerary) ? planning.daily_itinerary : [];
}

function assertRouteContains(days, pattern, message) {
  const names = days.flatMap((day) => day.proposal?.ordered_poi_names || []);
  assert(names.some((name) => pattern.test(String(name))), `${message}: ${names.join(' -> ')}`);
}

function assertNoImplausibleNamedTransfer(days, fromPattern, toPattern, maxMeters, message) {
  for (const day of days) {
    const stops = day.proposal?.pois || [];
    for (let index = 1; index < stops.length; index += 1) {
      const previous = stops[index - 1];
      const current = stops[index];
      const namesMatch =
        (fromPattern.test(String(previous.name)) && toPattern.test(String(current.name)))
        || (toPattern.test(String(previous.name)) && fromPattern.test(String(current.name)));
      if (!namesMatch) continue;
      const meters = Number(current.transfer_from_previous_meters || 0);
      assert(meters >= maxMeters, `${message}: got ${meters}m between ${previous.name} and ${current.name}`);
    }
  }
}

function assertNoLowValueStops(days, label) {
  const names = days.flatMap((day) => day.proposal?.ordered_poi_names || []);
  assert(
    !names.some((name) => /周边补充|周边休息|需确认|石碑|观景平台|管理处|服务处|科普小屋|文化活动室|售票|入口|出口|卫生间|停车场/.test(String(name))),
    `${label}: includes low-value or placeholder stop: ${names.join(' -> ')}`,
  );
}

async function runPlannerGenericDayCase(label, goal, expectedDays) {
  const result = await post('/api/v1/travel/plan', { goal });
  const days = dailyRoutes(result);
  const planning = result.planning_response || result || {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals : [];
  assert(Number(planning.day_count) === expectedDays, `${label}: expected day_count ${expectedDays}, got ${planning.day_count}`);
  assert(days.length === expectedDays, `${label}: expected ${expectedDays} daily routes, got ${days.length}`);
  assert(proposals.length >= 3, `${label}: expected at least 3 trip proposals, got ${proposals.length}`);
  const signatures = proposals.map((proposal) => (proposal.ordered_poi_names || []).join(' -> '));
  assert(new Set(signatures).size > 1, `${label}: trip proposals should not all be identical: ${signatures.join(' || ')}`);
  for (const [index, day] of days.entries()) {
    const stops = day.proposal?.pois || [];
    assert(stops.length >= 3, `${label}: day ${index + 1} should have >=3 stops`);
    assert(stops.slice(1).every((stop) => stop.transfer_mode), `${label}: day ${index + 1} should include transfer modes`);
  }
  assertNoLowValueStops(days, label);
  return {
    label,
    day_count: planning.day_count,
    routes: days.map((day) => (day.proposal?.ordered_poi_names || []).join(' -> ')),
    proposal_routes: signatures,
  };
}

async function runPlannerAccommodationAnchorCase() {
  const result = await post('/api/v1/travel/plan', {
    goal: '住在故宫附近，三天去颐和园、天坛、长城，想吃好吃的',
  });
  const planning = result.planning_response || result || {};
  const days = dailyRoutes(result);
  const primary = Array.isArray(planning.proposals) ? planning.proposals[0] : null;
  assert(Number(planning.day_count) === 3, `accommodation anchor: expected 3 days, got ${planning.day_count}`);
  assert(primary?.accommodation, 'accommodation anchor: primary proposal should expose accommodation');
  assert(/故宫/.test(String(primary.accommodation.name)), `accommodation anchor: should preserve requested hotel area, got ${primary.accommodation.name}`);
  assertRouteContains(days, /颐和园/, 'accommodation anchor: should keep requested Summer Palace');
  assertRouteContains(days, /天坛/, 'accommodation anchor: should keep requested Temple of Heaven');
  assertRouteContains(days, /长城|八达岭/, 'accommodation anchor: should keep requested Great Wall');
  assert(days.every((day) => day.accommodation || day.proposal?.accommodation), 'accommodation anchor: each day should expose accommodation');
  assert(days.every((day) => {
    const first = day.proposal?.pois?.[0];
    return first && first.transfer_from_label && Number(first.transfer_from_previous_minutes || 0) > 0;
  }), 'accommodation anchor: each first stop should include hotel outbound transfer');
  assert(days.every((day) => Number((day.accommodation || day.proposal?.accommodation)?.return_transfer_minutes || 0) > 0), 'accommodation anchor: each day should estimate return transfer');
  assertNoLowValueStops(days, 'accommodation anchor');
  return {
    label: 'planner-accommodation-anchor',
    accommodation: primary.accommodation,
    routes: days.map((day) => (day.proposal?.ordered_poi_names || []).join(' -> ')),
  };
}

async function runPlannerHotelRecommendationsCase() {
  const result = await post('/api/v1/travel/parse-and-plan', {
    goal: '住在798附近酒店，安排一天轻松一点的北京路线，想吃点靠谱的午饭',
  });
  const planning = result.planning_response || {};
  const primary = Array.isArray(planning.proposals) ? planning.proposals[0] : null;
  const recommendations = Array.isArray(planning.hotel_recommendations) ? planning.hotel_recommendations : [];
  const proposalRecommendations = Array.isArray(primary?.hotel_recommendations) ? primary.hotel_recommendations : [];
  const stops = Array.isArray(primary?.pois) ? primary.pois : [];
  assert(primary?.accommodation, 'hotel recommendations: primary proposal should expose accommodation');
  assert(
    ['matched_hotel', 'matched_area_hotel'].includes(String(primary.accommodation.location_confidence || '')),
    `hotel recommendations: expected real hotel match, got ${primary.accommodation.location_confidence}`,
  );
  assert(recommendations.length > 0, 'hotel recommendations: planning_response should expose hotel_recommendations');
  assert(proposalRecommendations.length > 0, 'hotel recommendations: proposal should expose hotel_recommendations');
  assert(
    stops.every((stop) => String(stop.poi_type || '').toLowerCase() !== 'accommodation' && String(stop.poi_kind || '').toLowerCase() !== 'hotel'),
    `hotel recommendations: hotels should not be timeline stops: ${stops.map((stop) => `${stop.name}/${stop.poi_type}`).join(' -> ')}`,
  );
  return {
    label: 'planner-hotel-recommendations',
    accommodation: primary.accommodation,
    hotel_recommendations: recommendations.slice(0, 3).map((hotel) => hotel.name),
  };
}

async function runPlannerQualityCase() {
  const result = await post('/api/v1/travel/plan', {
    goal: '三天玩北京，想去颐和园，吃好吃的，逛故宫，预算3000',
    route_mode: 'mixed',
    area: '故宫',
    max_budget: 3000,
    max_duration_min: 1440,
    day_count: 3,
    max_total_pois: 4,
    must_include_names: ['颐和园', '故宫'],
    preference_signals: {
      lunch: true,
      formal_meal: true,
      quality_food: true,
    },
  });
  const days = dailyRoutes(result);
  assert(Number(result.day_count) === 3, `planner quality: expected 3 days, got ${result.day_count}`);
  assert(days.length === 3, `planner quality: expected 3 daily routes, got ${days.length}`);
  assertRouteContains(days, /颐和园/, 'planner quality: should include Summer Palace');
  assertRouteContains(days, /故宫博物院/, 'planner quality: should resolve 故宫 to 故宫博物院');
  assertNoImplausibleNamedTransfer(days, /颐和园/, /故宫|TRB|景山|北海/, 8000, 'planner quality: should not place Summer Palace next to Forbidden City area');
  for (const [index, day] of days.entries()) {
    const stops = day.proposal?.pois || [];
    assert(stops.length >= 3, `planner quality: day ${index + 1} should have >=3 stops`);
    assert(stops.some((stop) => stop.poi_type === 'food'), `planner quality: day ${index + 1} should include food for mixed route`);
    assert(!stops.some((stop) => /停车场|出入口|体育中心|足球场|服务中心/.test(String(stop.name))), `planner quality: day ${index + 1} includes facility-like stop`);
    assert(Number(day.proposal?.total_route_duration_min || 0) <= 600, `planner quality: day ${index + 1} duration is too long`);
  }
  assertNoLowValueStops(days, 'planner quality');
  return {
    label: 'planner-quality-generic-three-day',
    routes: days.map((day) => (day.proposal?.ordered_poi_names || []).join(' -> ')),
  };
}

async function runCase(label, instruction, expectedDays) {
  const projectId = `project-multiday-${label}-${Date.now().toString(36)}`;
  await post('/api/projects', {
    project_id: projectId,
    name: projectId,
    initialPrompt: '',
    travelCapabilityId: 'mixed_food_route',
  });
  const result = await post(`/api/chat/${projectId}/act`, {
    instruction,
    displayInstruction: instruction,
    travelCapabilityId: 'mixed_food_route',
    requestId: `${projectId}-seed`,
  });
  const planning = result.travelItinerary?.planning_response || result.planning_response || {};
  const days = dailyRoutes(result);
  assert(result.status === 'travel_plan_completed', `${label}: should complete planning, got ${result.status}`);
  assert(Number(planning.day_count) === expectedDays, `${label}: expected day_count ${expectedDays}, got ${planning.day_count}`);
  assert(days.length === expectedDays, `${label}: expected ${expectedDays} daily_itinerary items, got ${days.length}`);
  const routeSignatures = days.map((day) => (day.proposal?.ordered_poi_names || []).join(' -> '));
  for (const [index, signature] of routeSignatures.entries()) {
    assert(signature.split(' -> ').filter(Boolean).length >= 3, `${label}: day ${index + 1} should have >=3 POIs: ${signature}`);
  }
  assertNoLowValueStops(days, label);
  assert(new Set(routeSignatures).size > 1, `${label}: multi-day routes should not all be identical: ${routeSignatures.join(' || ')}`);
  return {
    label,
    day_count: planning.day_count,
    resolved_area: planning.resolved_area,
    routes: routeSignatures,
    elapsed_ms: planning.generation_metrics?.sla?.elapsed_ms ?? planning.generation_metrics?.elapsed_ms,
  };
}

async function runPlannerFoodKeywordCase() {
  const result = await post('/api/v1/travel/plan', {
    goal: '北京两天一晚，第一次来，别太累，想吃烤鸭',
  });
  const days = dailyRoutes(result);
  assertRouteContains(days, /烤鸭|四季民福|全聚德|便宜坊|大董|利群/, 'food keyword: should honor roast duck preference');
  assertNoLowValueStops(days, 'food keyword');
  return {
    label: 'planner-food-keyword-roast-duck',
    routes: days.map((day) => (day.proposal?.ordered_poi_names || []).join(' -> ')),
  };
}

async function main() {
  const rows = [];
  rows.push(await runPlannerQualityCase());
  rows.push(await runPlannerGenericDayCase('planner-two-day-unknown-budget', '两天玩北京，想吃点好吃的，不知道去哪', 2));
  rows.push(await runPlannerGenericDayCase('planner-four-day-must-includes', '四天想去长城、故宫、天坛，吃饭预算还没定', 4));
  rows.push(await runPlannerAccommodationAnchorCase());
  rows.push(await runPlannerHotelRecommendationsCase());
  rows.push(await runPlannerFoodKeywordCase());
  rows.push(await runCase('five-day-summer-palace', '五天玩颐和园，想吃好吃的。', 5));
  rows.push(await runCase('four-day-beihai-hotel', '4天在北海附近慢慢玩，住酒店，想吃点靠谱的，不要太累。', 4));
  console.log('[travel-multiday-itinerary] passed');
  for (const row of rows) {
    console.log(JSON.stringify(row, null, 2));
  }
}

main().catch((error) => {
  console.error('[travel-multiday-itinerary] failed:', error);
  process.exit(1);
});
