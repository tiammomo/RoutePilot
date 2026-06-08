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

function firstProposal(result) {
  return result.planning_response?.proposals?.[0] || result.proposals?.[0];
}

function names(result) {
  return firstProposal(result)?.ordered_poi_names || [];
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function main() {
  const seed = await post('/api/v1/travel/parse-and-plan', {
    goal: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
  });
  const before = names(seed);
  assert(before.length >= 3, `seed should have at least 3 POIs: ${before.join(' -> ')}`);

  const result = await post('/api/v1/travel/replan', {
    previous_request: seed.planning_response.request_snapshot,
    selected_proposal: seed.planning_response.proposals[0],
    adjustment_text: '把第二个点换成更少走路的室内点，其他地方不变',
  });
  const after = names(result);
  assert(after.length >= 3, `replan should have at least 3 POIs: ${after.join(' -> ')}`);
  assert(after[1] !== before[1], `second POI should change, still got ${after[1]}`);
  assert(!after.includes(before[1]), `replaced POI leaked back into route: ${before[1]}`);
  assert(after[0] === before[0], `first POI should stay unchanged: ${before[0]} -> ${after[0]}`);
  assert(after[2] === before[2], `third POI should stay unchanged: ${before[2]} -> ${after[2]}`);
  assert(!/Temple|剧场|酒店|市民文化中心/.test(after[1]), `replacement should be a visitor-friendly indoor culture POI: ${after[1]}`);
  assert(/博物馆|美术馆|艺术中心|展览馆/.test(after[1]), `replacement should prefer museum/gallery/art center: ${after[1]}`);

  console.log('[travel-targeted-replan] passed');
  console.log(`before: ${before.join(' -> ')}`);
  console.log(`after: ${after.join(' -> ')}`);
}

main().catch((error) => {
  console.error('[travel-targeted-replan] failed:', error);
  process.exit(1);
});
