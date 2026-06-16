const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:33003';

async function post(pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${pathname} failed: ${response.status} ${text}`);
  }
  return text ? JSON.parse(text) : null;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function getPlanning(result) {
  return result?.planning_response || result || {};
}

function getProposals(result) {
  return Array.isArray(getPlanning(result).proposals) ? getPlanning(result).proposals : [];
}

function getIds(result) {
  return getProposals(result).map((proposal) => String(proposal.proposal_id));
}

function stableSignature(proposal) {
  return JSON.stringify({
    proposal_id: proposal?.proposal_id || null,
    ordered_poi_ids: Array.isArray(proposal?.ordered_poi_ids) ? proposal.ordered_poi_ids : [],
    ordered_poi_names: Array.isArray(proposal?.ordered_poi_names) ? proposal.ordered_poi_names : [],
    total_budget_estimate: proposal?.total_budget_estimate ?? null,
    total_route_duration_min: proposal?.total_route_duration_min ?? null,
    total_transfer_minutes: proposal?.total_transfer_minutes ?? null,
  });
}

async function main() {
  const json = await post('/api/v1/travel/parse-and-plan', {
    goal: '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。',
  });

  const planning = getPlanning(json);
  const proposals = getProposals(json);
  const ids = getIds(json);
  const rerank = planning.llm_rerank;

  assert(proposals.length >= 3, `expected >=3 proposals, got ${proposals.length}`);
  assert(rerank && typeof rerank === 'object', 'planning_response.llm_rerank should exist');
  assert(Array.isArray(rerank.ranked_proposal_ids), 'rerank.ranked_proposal_ids should be an array');
  assert(rerank.ranked_proposal_ids.length === ids.length, 'rerank should return all proposal ids');
  assert(new Set(rerank.ranked_proposal_ids).size === ids.length, 'rerank ids should be unique');
  assert(rerank.ranked_proposal_ids.every((id) => ids.includes(String(id))), 'rerank ids must belong to planner proposals');
  assert(ids[0] === String(planning.final_selected_proposal_id), 'final_selected_proposal_id should match reordered first proposal');
  assert(ids.includes(String(rerank.primary_proposal_id)), 'primary proposal must belong to planner proposals');
  assert(typeof planning.natural_language_explanation === 'string' && planning.natural_language_explanation.trim().length > 0, 'natural language explanation should exist');
  assert(typeof planning.generation_metrics?.database_recall_used === 'boolean', 'database_recall_used metric should exist');
  assert(typeof planning.generation_metrics?.llm_rerank_used === 'boolean', 'llm_rerank_used metric should exist');

  const byId = new Map(proposals.map((proposal) => [String(proposal.proposal_id), stableSignature(proposal)]));
  for (const proposalId of rerank.ranked_proposal_ids) {
    assert(byId.has(String(proposalId)), `missing signature for proposal ${proposalId}`);
  }

  const mockConfigured = Boolean(process.env.TRAVELPILOT_RERANK_MOCK_RESPONSE);
  if (mockConfigured && rerank.llm_used) {
    assert(ids[0] === String(rerank.primary_proposal_id), 'when rerank is active, first proposal should match rerank primary id');
  } else {
    assert(['string', 'object'].includes(typeof rerank.fallback_reason) || rerank.fallback_reason === null, 'fallback reason should be string or null');
  }

  console.log('[travel-llm-rerank] passed');
  console.log(`proposal order: ${ids.join(' -> ')}`);
  console.log(`primary: ${planning.final_selected_proposal_id}`);
  console.log(`llm_used: ${rerank.llm_used}, fallback_reason: ${rerank.fallback_reason ?? 'none'}`);
}

main().catch((error) => {
  console.error('[travel-llm-rerank] failed:', error);
  process.exit(1);
});
