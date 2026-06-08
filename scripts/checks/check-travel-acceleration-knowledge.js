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

function planningOf(result) {
  return result?.planning_response || result || {};
}

async function main() {
  await post('/api/v1/travel/warmup', {});

  const commonText = '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。';
  const firstQuery = await post('/api/v1/travel/query-plan', { raw_text: commonText });
  assert(['dictionary', 'cache'].includes(String(firstQuery.intent?.parser)), `common semantic path should use dictionary/cache, got ${firstQuery.intent?.parser}`);
  assert(firstQuery.intent?.llm_used === false, 'common semantic path should skip blocking LLM');

  const secondQuery = await post('/api/v1/travel/query-plan', { raw_text: commonText });
  assert(['cache', 'dictionary'].includes(String(secondQuery.intent?.parser)), `repeat query should stay on local semantic/cache path, got ${secondQuery.intent?.parser}`);
  assert(secondQuery.intent?.llm_used === false, 'repeat query should not use blocking LLM');

  const planned = await post('/api/v1/travel/parse-and-plan', { goal: commonText });
  const planning = planningOf(planned);
  assert(['dictionary', 'cache'].includes(String(planned.intent?.parser || planning.intent?.parser)), 'parse-and-plan should use common semantic fast path or its intent cache');
  assert(planning.acceleration?.enabled === true, 'planning should expose acceleration summary');
  assert(planning.acceleration?.layers?.common_semantic_fast_path === true, 'planning acceleration should mark semantic fast path');
  assert(planning.acceleration?.layers?.route_corpus === true || planning.generation_metrics?.route_corpus_used === true, 'planning should use route corpus or expose route corpus metric');
  assert(Array.isArray(planning.acceleration?.cache_layers_hit), 'planning should expose cache layer list');
  assert(planning.knowledge_guidance && typeof planning.knowledge_guidance === 'object', 'planning should expose knowledge guidance summary');
  assert(typeof planning.generation_metrics?.knowledge_guidance_used === 'boolean', 'metrics should expose knowledge guidance flag');
  assert(planning.generation_metrics?.acceleration_layers && typeof planning.generation_metrics.acceleration_layers === 'object', 'metrics should expose acceleration layers');

  const knowledgeCase = await post('/api/v1/travel/parse-and-plan', {
    goal: '想轻松逛逛，别太商业，顺便吃点东西。',
  });
  const knowledgePlanning = planningOf(knowledgeCase);
  assert(knowledgePlanning.knowledge_guidance && typeof knowledgePlanning.knowledge_guidance === 'object', 'ambiguous route should expose knowledge guidance');
  assert(typeof knowledgePlanning.knowledge_guidance.knowledge_base?.hit_count === 'number', 'knowledge guidance should expose hit count');

  console.log('[travel-acceleration-knowledge] passed');
  console.log(JSON.stringify({
    common_parser: planned.intent?.parser || planning.intent?.parser,
    fast_path: planning.generation_metrics?.sla?.fast_path,
    cache_layers_hit: planning.acceleration?.cache_layers_hit,
    knowledge_guidance_used: planning.generation_metrics?.knowledge_guidance_used,
    knowledge_hit_count: planning.generation_metrics?.knowledge_hit_count,
  }, null, 2));
}

main().catch((error) => {
  console.error('[travel-acceleration-knowledge] failed:', error);
  process.exit(1);
});
