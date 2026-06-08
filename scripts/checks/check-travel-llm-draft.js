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
  const body = {
    goal: '带老人去北海，别太累，玩3小时，中午吃饭，不想排队。',
  };
  const result = await post('/api/v1/travel/parse-and-plan', body);
  const planning = result?.planning_response || result || {};
  const draft = planning.route_draft;
  const validation = planning.validator_result;
  const metrics = planning.generation_metrics || {};
  const proposals = Array.isArray(planning.proposals) ? planning.proposals : [];
  const primary = proposals[0] || {};
  const primaryIds = Array.isArray(primary.ordered_poi_ids) ? primary.ordered_poi_ids : [];

  assert(draft && typeof draft === 'object', 'route_draft should exist');
  assert(['minimax', 'rule_fallback'].includes(String(draft.draft_source)), `unexpected draft source: ${draft.draft_source}`);
  assert(Array.isArray(draft.ordered_poi_ids) && draft.ordered_poi_ids.length >= 3, 'draft should include ordered POI ids');
  assert(validation && typeof validation === 'object', 'validator_result should exist');
  assert(['valid', 'repaired', 'rejected'].includes(String(validation.status)), `unexpected validator status: ${validation.status}`);
  assert(validation.status !== 'rejected' || Array.isArray(validation.rejection_reasons), 'rejected draft should expose reasons');
  assert(metrics.route_draft_used === true, 'metrics.route_draft_used should be true');
  assert(['minimax', 'rule_fallback'].includes(String(metrics.draft_source)), 'metrics should expose draft source');
  assert(Array.isArray(planning.repair_actions), 'planning should expose repair_actions array');
  if (validation.status !== 'rejected') {
    assert(primaryIds.length >= 3, 'primary proposal should contain ordered POI ids');
    assert(validation.valid_ordered_poi_ids.every((id) => primaryIds.includes(id)), 'validated draft POIs should be included in primary route');
  }

  const mockIds = draft.ordered_poi_ids.slice(0, 3);
  const mockResult = await post('/api/v1/travel/parse-and-plan', {
    ...body,
    debug_route_draft_mock: JSON.stringify({
      selected_poi_ids: mockIds,
      ordered_poi_ids: mockIds,
      meal_stop_id: null,
      estimated_fit: 0.91,
      preference_reasoning: 'Mocked MiniMax RouteDraft selected valid backend candidates for validation.',
      known_risks: [],
      used_wiki_citation_ids: [],
    }),
  });
  const mockPlanning = mockResult?.planning_response || mockResult || {};
  const mockDraft = mockPlanning.route_draft;
  const mockValidation = mockPlanning.validator_result;
  assert(mockDraft?.draft_source === 'minimax', 'mocked MiniMax RouteDraft should be adopted as minimax draft');
  assert(mockDraft?.llm_used === true, 'mocked MiniMax RouteDraft should mark llm_used=true');
  assert(['valid', 'repaired'].includes(String(mockValidation?.status)), `mocked RouteDraft should pass or repair, got ${mockValidation?.status}`);

  console.log('[travel-llm-draft] passed');
  console.log(JSON.stringify({
    draft_source: draft.draft_source,
    draft_llm_used: draft.llm_used,
    draft_llm_attempted: draft.llm_attempted,
    draft_fallback_reason: draft.fallback_reason,
    validator_status: validation.status,
    repair_actions: validation.repair_actions,
    ordered_poi_ids: draft.ordered_poi_ids,
    mocked_draft_source: mockDraft.draft_source,
    mocked_validator_status: mockValidation.status,
  }, null, 2));
}

main().catch((error) => {
  console.error('[travel-llm-draft] failed:', error);
  process.exit(1);
});
