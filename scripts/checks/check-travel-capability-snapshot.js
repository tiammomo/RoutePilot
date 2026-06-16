const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:33003';

async function get(pathname) {
  const response = await fetch(`${baseUrl}${pathname}`);
  const text = await response.text();
  if (!response.ok) throw new Error(`${pathname} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

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

function proposalsOf(planning) {
  return Array.isArray(planning.proposals) ? planning.proposals : [];
}

function stopsOf(proposal) {
  return Array.isArray(proposal?.pois) ? proposal.pois : [];
}

function hasTransferDetails(proposal) {
  return stopsOf(proposal).every((stop, index) => (
    index === 0
      || (
        Number.isFinite(Number(stop.transfer_from_previous_minutes))
        && Number.isFinite(Number(stop.transfer_from_previous_meters))
        && ['commute_edge', 'coordinate_estimate'].includes(String(stop.transfer_source))
      )
  ));
}

function assertCoreRoute(planning) {
  const proposals = proposalsOf(planning);
  assert(proposals.length >= 3, `expected at least 3 proposals, got ${proposals.length}`);
  for (const proposal of proposals.slice(0, 3)) {
    const stops = stopsOf(proposal);
    assert(stops.length >= 3, `proposal ${proposal.proposal_id} should have at least 3 stops`);
    assert(Array.isArray(proposal.ordered_poi_names) && proposal.ordered_poi_names.length === stops.length, `proposal ${proposal.proposal_id} should expose ordered POI names`);
    assert(Number.isFinite(Number(proposal.total_route_duration_min)), `proposal ${proposal.proposal_id} should expose total duration`);
    assert(Number.isFinite(Number(proposal.total_budget_estimate)), `proposal ${proposal.proposal_id} should expose budget estimate`);
    assert(hasTransferDetails(proposal), `proposal ${proposal.proposal_id} should expose per-leg transfer details`);
    assert(stops.some((stop) => String(stop.evidence_summary || '').length > 0 || stop.evidence_summary), `proposal ${proposal.proposal_id} should include evidence summaries`);
  }
}

function assertWiki(planning) {
  assert(planning.wiki_retrieval && typeof planning.wiki_retrieval === 'object', 'wiki_retrieval should exist');
  assert(planning.generation_metrics?.wiki_retrieval_used === true, 'wiki retrieval metric should be true');
  assert(Array.isArray(planning.wiki_retrieval.hits), 'wiki_retrieval.hits should be an array');
  assert(planning.wiki_retrieval.hits.length > 0, 'wiki retrieval should return hits');
  const hit = planning.wiki_retrieval.hits[0];
  assert(hit.title && hit.path && hit.type, 'wiki hit should include title/path/type');
}

function assertPlanningAdvice(planning) {
  const advice = planning.planning_advice;
  assert(advice && typeof advice === 'object', 'planning_advice should exist');
  assert(['minimax', 'wiki_local'].includes(String(advice.source)), `unexpected planning advice source: ${advice.source}`);
  assert(planning.generation_metrics?.planning_advice_used === true, 'planning advice metric should be true');
  assert(['minimax', 'wiki_local'].includes(String(planning.generation_metrics?.planning_advice_source)), 'planning advice source metric should exist');
}

function assertRouteDraft(planning) {
  const draft = planning.route_draft;
  const validation = planning.validator_result;
  assert(draft && typeof draft === 'object', 'route_draft should exist');
  assert(['minimax', 'rule_fallback'].includes(String(draft.draft_source)), `unexpected draft source: ${draft.draft_source}`);
  assert(Array.isArray(draft.ordered_poi_ids) && draft.ordered_poi_ids.length >= 3, 'route_draft should expose ordered POI ids');
  assert(validation && typeof validation === 'object', 'validator_result should exist');
  assert(['valid', 'repaired', 'rejected'].includes(String(validation.status)), `unexpected validator status: ${validation.status}`);
  assert(Array.isArray(planning.repair_actions), 'repair_actions should be an array');
  assert(planning.generation_metrics?.route_draft_used === true, 'route draft metric should be true');
  assert(['minimax', 'rule_fallback'].includes(String(planning.generation_metrics?.draft_source)), 'draft source metric should exist');
}

function assertRerank(planning) {
  const rerank = planning.llm_rerank;
  const proposalIds = proposalsOf(planning).map((proposal) => String(proposal.proposal_id));
  assert(rerank && typeof rerank === 'object', 'llm_rerank should exist');
  assert(['minimax', 'wiki_local', 'planner_fallback'].includes(String(rerank.rerank_source)), `unexpected rerank source: ${rerank.rerank_source}`);
  assert(Array.isArray(rerank.ranked_proposal_ids), 'rerank should include ranked proposal ids');
  assert(rerank.ranked_proposal_ids.every((id) => proposalIds.includes(String(id))), 'rerank ids must belong to planner proposals');
  assert(proposalIds.includes(String(planning.final_selected_proposal_id)), 'final selected proposal should belong to planner proposals');
  assert(typeof planning.natural_language_explanation === 'string' && planning.natural_language_explanation.trim().length > 0, 'natural language explanation should exist');
}

function assertCommute(planning) {
  const primary = proposalsOf(planning)[0];
  const summary = primary?.transfer_source_summary || primary?.quality_summary?.commute || {};
  assert(summary && typeof summary === 'object', 'transfer source summary should exist');
  assert(Number.isFinite(Number(summary.commute_edges_used || 0)), 'commute edge count should be numeric');
  assert(Number.isFinite(Number(summary.coordinate_estimates_used || 0)), 'coordinate estimate count should be numeric');
  const transferModes = stopsOf(primary).slice(1).map((stop) => stop.transfer_mode).filter(Boolean);
  assert(
    stopsOf(primary).some((stop, index) => index > 0 && stop.transfer_source === 'commute_edge')
      || transferModes.some((mode) => ['walking_estimate', 'bike_estimate', 'driving_estimate'].includes(String(mode))),
    'route should use commute edges or typed coordinate fallback modes',
  );
}

async function main() {
  const health = await get('/api/v1/travel/health');
  assert(health.status === 'ok', 'travel health should be ok');
  assert(health.commute?.loaded === true, 'commute edge index should load');
  assert(Number(health.commute?.edge_count || 0) > 0, 'commute edge index should contain rows');

  const queryPlan = await post('/api/v1/travel/query-plan', {
    raw_text: '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。',
  });
  assert(queryPlan.intent && typeof queryPlan.intent === 'object', 'query-plan should return intent');
  assert(Array.isArray(queryPlan.query_plan?.steps) && queryPlan.query_plan.steps.length > 0, 'query-plan should return whitelist SQL steps');
  assert(Array.isArray(queryPlan.results), 'query-plan should return SQL template results');

  const result = await post('/api/v1/travel/parse-and-plan', {
    goal: '带老人去北海，别太累，玩3小时，中午吃饭，不想排队。',
  });
  const planning = planningOf(result);
  assertCoreRoute(planning);
  assertWiki(planning);
  assertPlanningAdvice(planning);
  assertRouteDraft(planning);
  assertRerank(planning);
  assertCommute(planning);

  const summary = {
    parser: result.intent?.parser || planning.intent?.parser || null,
    planning_advice_source: planning.planning_advice?.source || null,
    draft_source: planning.route_draft?.draft_source || null,
    validator_status: planning.validator_result?.status || null,
    rerank_source: planning.llm_rerank?.rerank_source || null,
    rerank_llm_used: Boolean(planning.llm_rerank?.llm_used),
    wiki_hits: planning.wiki_retrieval?.hits?.length || 0,
    proposals: proposalsOf(planning).length,
    primary_transfer_summary: proposalsOf(planning)[0]?.transfer_source_summary || null,
  };
  console.log('[travel-capability-snapshot] passed');
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  console.error('[travel-capability-snapshot] failed:', error);
  process.exit(1);
});
