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

async function main() {
  const result = await post('/api/v1/travel/parse-and-plan', {
    goal: '带老人去北海，别太累，玩3小时，中午吃饭，不想排队。',
  });
  const planning = result?.planning_response || result || {};
  const advice = planning.planning_advice;
  const metrics = planning.generation_metrics || {};
  const firstProposal = Array.isArray(planning.proposals) ? planning.proposals[0] : null;
  const stops = Array.isArray(firstProposal?.pois) ? firstProposal.pois : [];

  assert(advice && typeof advice === 'object', 'planning_advice should exist');
  assert(['minimax', 'wiki_local'].includes(String(advice.source)), `unexpected advice source: ${advice.source}`);
  assert(metrics.planning_advice_used === true, 'generation_metrics.planning_advice_used should be true');
  assert(['minimax', 'wiki_local'].includes(String(metrics.planning_advice_source)), 'metrics should expose planning advice source');
  assert(Number(stops.length) <= 3, `short senior route should be capped to 3 POIs, got ${stops.length}`);
  assert(firstProposal?.request_constraints?.walk_preference === 'low' || planning.request_snapshot?.walk_preference === 'low', 'planner should receive low walking preference');
  assert(planning.request_snapshot?.max_total_pois === 3, `planner request should be adjusted to 3 POIs, got ${planning.request_snapshot?.max_total_pois}`);

  console.log('[travel-planning-advice] passed');
  console.log(`source=${advice.source}, llm_used=${advice.llm_used}, max_total_pois=${advice.max_total_pois}, pace=${advice.pace}`);
}

main().catch((error) => {
  console.error('[travel-planning-advice] failed:', error);
  process.exit(1);
});
