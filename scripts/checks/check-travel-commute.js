const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:33003';

async function get(path) {
  const response = await fetch(`${baseUrl}${path}`);
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

async function post(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function flattenProposalStops(result) {
  return (result.planning_response?.proposals || result.proposals || [])
    .flatMap((proposal) => proposal.pois || []);
}

async function main() {
  const health = await get('/api/v1/travel/health');
  assert(health.commute?.loaded === true, `commute edge index should load: ${JSON.stringify(health.commute)}`);
  assert(Number(health.commute?.edge_count || 0) > 0, 'commute edge index should contain rows');
  assert(health.cache?.commute_edge_index_ready === true, 'health cache should report commute edge index ready');

  const result = await post('/api/v1/travel/parse-and-plan', {
    goal: '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
  });
  const metrics = result.planning_response?.generation_metrics;
  assert(metrics?.commute_edges_loaded === true, `planner should load commute edges: ${JSON.stringify(metrics)}`);
  assert(metrics?.within_10s === true, `planner should remain within 10s: ${JSON.stringify(metrics)}`);

  const deterministic = await post('/api/v1/travel/plan', {
    route_mode: 'culture',
    area: '故宫',
    max_total_pois: 3,
    must_include_poi_ids: ['amap_B0H65CPLW1', 'amap_B000A9LF82'],
    route_order_poi_ids: ['amap_B0H65CPLW1', 'amap_B000A9LF82'],
  });
  const deterministicMetrics = deterministic.generation_metrics;
  assert(Number(deterministicMetrics?.commute_edges_used || 0) > 0, `planner should use at least one commute edge: ${JSON.stringify(deterministicMetrics)}`);
  assert(Number(deterministicMetrics?.commute_edge_hit_rate || 0) > 0, `planner should report commute hit rate: ${JSON.stringify(deterministicMetrics)}`);

  const stops = flattenProposalStops(deterministic);
  assert(stops.some((stop) => stop.transfer_source === 'commute_edge'), 'at least one stop should use commute_edge transfer source');
  assert(stops.every((stop) => stop.transfer_source !== 'commute_edge' || Number(stop.transfer_duration_s || 0) > 0), 'commute transfers should have positive duration seconds');

  console.log(`[travel-commute] loaded ${health.commute.edge_count} commute edges`);
  console.log(`[travel-commute] deterministic route used ${deterministicMetrics.commute_edges_used} commute edges, hit rate ${deterministicMetrics.commute_edge_hit_rate}`);
  console.log('[travel-commute] passed');
}

main().catch((error) => {
  console.error('[travel-commute] failed:', error);
  process.exit(1);
});
