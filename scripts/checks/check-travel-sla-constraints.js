const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function request(path, options = {}) {
  const started = Date.now();
  const response = await fetch(`${baseUrl}${path}`, options);
  const elapsedMs = Date.now() - started;
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${text}`);
  return { elapsedMs, json: text ? JSON.parse(text) : null };
}

async function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function planningOf(result) {
  return result.planning_response || result;
}

function proposalOf(result) {
  const planning = planningOf(result);
  return planning.proposals?.[0] || null;
}

function assertSla(planning, label, elapsedMs) {
  const metrics = planning.generation_metrics || {};
  assert(metrics.within_10s === true, `${label}: generation_metrics.within_10s should be true`);
  assert(metrics.sla?.target_ms === 10000, `${label}: sla.target_ms should be 10000`);
  assert(metrics.sla?.within_10s === true, `${label}: sla.within_10s should be true`);
  assert(String(metrics.sla?.fast_path || '').length > 0, `${label}: sla.fast_path should be visible`);
  assert(elapsedMs < 10000, `${label}: API response should be under 10s, got ${elapsedMs}ms`);
}

function assertConstraintPayload(proposal, label) {
  assert(proposal, `${label}: first proposal should exist`);
  assert(proposal.constraint_report?.checks?.poi_count?.actual >= 3, `${label}: should include >=3 POIs`);
  assert(proposal.constraint_report?.checks?.poi_count?.satisfied === true, `${label}: poi_count constraint should pass`);
  assert(typeof proposal.constraint_report?.checks?.category_coverage?.food_count === 'number', `${label}: food coverage should be reported`);
  assert(typeof proposal.constraint_report?.checks?.category_coverage?.culture_or_entertainment_count === 'number', `${label}: culture coverage should be reported`);
  assert(typeof proposal.constraint_report?.checks?.budget?.satisfied === 'boolean', `${label}: budget constraint should be explicit`);
  assert(typeof proposal.constraint_report?.checks?.duration?.satisfied === 'boolean', `${label}: duration constraint should be explicit`);
  assert(typeof proposal.constraint_report?.checks?.queue?.satisfied === 'boolean', `${label}: queue constraint should be explicit`);
  assert(Array.isArray(proposal.constraint_resolution?.priority_order), `${label}: constraint priority should be visible`);
  assert(String(proposal.constraint_resolution?.user_visible_summary || '').length > 0, `${label}: conflict summary should be visible`);
  assert(proposal.quality_summary?.validations?.poi_count_valid === true, `${label}: quality validations should include poi_count_valid`);
  assert(typeof proposal.quality_summary?.validations?.timeline_valid === 'boolean', `${label}: quality validations should include timeline_valid`);
}

async function main() {
  await post('/api/v1/travel/warmup', {});

  const cases = [
    ['mixed_route', '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。'],
    ['conflict_route', '王府井附近玩3小时，中午吃好点，预算80以内，不想排队，还要安排4个点。'],
  ];

  let seed = null;
  for (const [label, goal] of cases) {
    const result = await post('/api/v1/travel/parse-and-plan', { goal });
    const planning = planningOf(result.json);
    const proposal = proposalOf(result.json);
    assertSla(planning, label, result.elapsedMs);
    assertConstraintPayload(proposal, label);
    seed = seed || result.json;
    console.log(`[travel-sla-constraints:${label}] ${result.elapsedMs}ms, ${proposal.ordered_poi_names.join(' -> ')}`);
  }

  const replan = await post('/api/v1/travel/replan', {
    previous_request: seed.planning_response.request_snapshot,
    selected_proposal: seed.planning_response.proposals[0],
    adjustment_text: '把第二个点换成室内点，其他地方不变。',
  });
  const patch = replan.json.route_patch_summary || replan.json.replan_metadata?.route_patch_summary;
  assertSla(planningOf(replan.json), 'replan', replan.elapsedMs);
  assertConstraintPayload(proposalOf(replan.json), 'replan');
  assert(patch && typeof patch.changed === 'boolean', 'replan: route_patch_summary should be visible');
  assert(Array.isArray(patch.before_route_names) && Array.isArray(patch.after_route_names), 'replan: patch should include before/after names');
  console.log(`[travel-sla-constraints:replan] ${replan.elapsedMs}ms, changed=${patch.changed}`);

  console.log('[travel-sla-constraints] passed');
}

main().catch((error) => {
  console.error('[travel-sla-constraints] failed:', error);
  process.exit(1);
});
