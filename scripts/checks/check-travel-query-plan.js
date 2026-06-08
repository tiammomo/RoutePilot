const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function post(path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${text}`);
  }
  return text ? JSON.parse(text) : null;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function templates(payload) {
  return (payload.query_plan?.steps || []).map((step) => step.template);
}

async function assertCommonDictionary() {
  const text = '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队';
  const first = await post('/api/v1/travel/query-plan', { raw_text: text });
  assert(first.intent?.parser === 'dictionary', `expected dictionary parser, got ${first.intent?.parser}`);
  assert(first.intent?.llm_used === false, 'common request should not use MiniMax');
  assert(first.intent?.area === '前门', `area ${first.intent?.area}`);
  assert(first.intent?.duration_minutes === 240, `duration ${first.intent?.duration_minutes}`);
  assert(first.intent?.budget_cny === 200, `budget ${first.intent?.budget_cny}`);
  assert(first.generation_metrics?.within_10s === true, 'common request should be within 10s');
  for (const template of ['candidate_culture_pois', 'candidate_food_pois', 'low_queue_pois']) {
    assert(templates(first).includes(template), `missing template ${template}`);
    const result = first.results.find((entry) => entry.template === template);
    assert(result && Array.isArray(result.rows), `${template} should return rows`);
  }

  const second = await post('/api/v1/travel/query-plan', { raw_text: text });
  assert(second.intent?.parser === 'cache', `expected intent cache parser, got ${second.intent?.parser}`);
  assert(second.generation_metrics?.intent_cache_hit === true, 'second request should hit intent cache');
  assert(second.generation_metrics?.query_cache_hit === true, 'second request should hit query cache');
  console.log('[travel-query-plan] dictionary/cache path passed');
}

async function assertMoreDictionaryCases() {
  const senior = await post('/api/v1/travel/query-plan', { raw_text: '带老人去北海玩4小时，别太累，中午吃饭' });
  assert(senior.intent?.parser === 'dictionary', `senior parser ${senior.intent?.parser}`);
  assert(senior.intent?.persona === 'senior', `senior persona ${senior.intent?.persona}`);
  assert(senior.intent?.walk_preference === 'low', `senior walk ${senior.intent?.walk_preference}`);

  const replan = await post('/api/v1/travel/query-plan', { raw_text: '故宫附近玩4小时，把第二个点换成室内点，其他地方不变' });
  assert(replan.intent?.replan_action === 'replace_stop', `replan action ${replan.intent?.replan_action}`);
  assert(replan.intent?.indoor_preferred === true, 'replan should prefer indoor');
  assert(templates(replan).includes('indoor_pois'), 'replan should include indoor query');
  console.log('[travel-query-plan] extra dictionary cases passed');
}

async function assertMiniMaxFallbackShape() {
  const fallback = await post('/api/v1/travel/query-plan', { raw_text: '想轻松逛逛，别太商业，顺便吃点东西' });
  assert(fallback.intent?.missing_fields?.includes('area'), 'fallback/clarification should mark missing area');
  assert(fallback.intent?.missing_fields?.includes('duration_minutes'), 'fallback/clarification should mark missing duration');
  assert(fallback.results.length === 0, 'missing fields should skip SQL queries');
  assert(fallback.clarification?.required === true, 'missing fields should require clarification');
  console.log(`[travel-query-plan] fallback parser=${fallback.intent?.parser}`);
}

async function main() {
  await assertCommonDictionary();
  await assertMoreDictionaryCases();
  await assertMiniMaxFallbackShape();
  console.log('[travel-query-plan] passed');
}

main().catch((error) => {
  console.error('[travel-query-plan] failed:', error);
  process.exit(1);
});
