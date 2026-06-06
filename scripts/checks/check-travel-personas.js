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

function firstProposal(result) {
  return result.planning_response?.proposals?.[0] || result.proposals?.[0];
}

function requestSnapshot(result) {
  return result.planning_response?.request_snapshot || result.request_snapshot;
}

function stopNames(result) {
  return firstProposal(result)?.ordered_poi_names || [];
}

function stops(result) {
  const proposal = firstProposal(result);
  return proposal?.stops || proposal?.pois || [];
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function overlapRatio(a, b) {
  const left = new Set(a);
  const right = new Set(b);
  const overlap = [...left].filter((name) => right.has(name)).length;
  return overlap / Math.max(1, Math.min(left.size, right.size));
}

async function runCase(label, goal, expectedPersona) {
  const result = await post('/api/v1/travel/parse-and-plan', { goal });
  const snapshot = requestSnapshot(result);
  const proposal = firstProposal(result);
  const routeStops = stops(result);
  const foodCount = routeStops.filter((stop) => stop.poi_type === 'food').length;
  const cultureCount = routeStops.filter((stop) => stop.poi_type !== 'food').length;
  assert(snapshot?.persona_id === expectedPersona, `${label}: expected persona ${expectedPersona}, got ${snapshot?.persona_id}`);
  assert(routeStops.length >= 3, `${label}: expected at least 3 stops`);
  assert(foodCount >= 1, `${label}: expected a food stop`);
  assert(cultureCount >= 2, `${label}: expected at least 2 culture stops`);
  return result;
}

async function main() {
  const cases = {
    couple: await runCase(
      'couple',
      '情侣去王府井附近玩4小时，中午吃饭，想浪漫一点，预算300以内，少排队',
      'couple_romantic',
    ),
    senior: await runCase(
      'senior',
      '带老人去王府井附近玩4小时，中午吃饭，少走路，别太累，预算300以内',
      'senior_relaxed',
    ),
    kids: await runCase(
      'kids',
      '带小孩去王府井附近玩4小时，中午吃饭，亲子友好，别太累，预算300以内',
      'family_kids',
    ),
  };

  const coupleNames = stopNames(cases.couple);
  const seniorNames = stopNames(cases.senior);
  const kidsNames = stopNames(cases.kids);
  assert(overlapRatio(coupleNames, seniorNames) < 1, `couple/senior routes are identical: ${coupleNames.join(' -> ')}`);
  assert(overlapRatio(coupleNames, kidsNames) < 1, `couple/kids routes are identical: ${coupleNames.join(' -> ')}`);

  const seniorStops = stops(cases.senior);
  const kidsStops = stops(cases.kids);
  assert(seniorStops.every((stop) => stop.stay_minutes <= 65 || stop.poi_type === 'food'), 'senior route should keep culture stops short');
  assert(kidsStops.some((stop) => /儿童|亲子|妇女儿童|剧院|博物馆/.test(stop.name)), `kids route lacks family-friendly POI: ${kidsNames.join(' -> ')}`);

  console.log('[travel-personas] passed');
  console.log(`couple: ${coupleNames.join(' -> ')}`);
  console.log(`senior: ${seniorNames.join(' -> ')}`);
  console.log(`kids: ${kidsNames.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-personas] failed:', error);
  process.exit(1);
});
