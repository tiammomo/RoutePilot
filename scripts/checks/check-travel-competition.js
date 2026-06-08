const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

const report = {
  route_generation: [],
  constraint: [],
  personalization: [],
  replan: [],
  data_grounding: [],
  performance: [],
};

async function request(path, options = {}) {
  const started = Date.now();
  const response = await fetch(`${baseUrl}${path}`, options);
  const elapsedMs = Date.now() - started;
  const text = await response.text();
  if (!response.ok) throw new Error(`${path} failed: ${response.status} ${text}`);
  return { elapsedMs, json: text ? JSON.parse(text) : null };
}

async function get(path) {
  return request(path);
}

async function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function record(category, label, pass, detail = '') {
  report[category].push({ label, pass: Boolean(pass), detail: String(detail || '') });
}

function proposalOf(result) {
  return result.planning_response?.proposals?.[0] || result.proposals?.[0] || null;
}

function planningOf(result) {
  return result.planning_response || result;
}

function stopsOf(result) {
  const proposal = proposalOf(result);
  return proposal?.pois || proposal?.stops || [];
}

function namesOf(result) {
  return proposalOf(result)?.ordered_poi_names || stopsOf(result).map((stop) => stop.name);
}

function requestSnapshotOf(result) {
  return result.planning_response?.request_snapshot || result.request_snapshot || {};
}

function hasFoodStop(result) {
  return stopsOf(result).some((stop) => stop.poi_type === 'food' || stop.meal_slot === 'lunch');
}

function riskVisible(proposal, keyword) {
  const risks = proposal?.risks || [];
  if (keyword === 'budget' && proposal?.budget_summary?.within_budget === false) return true;
  if (keyword === 'duration' && proposal?.duration_summary?.within_duration === false) return true;
  if (!risks.length) return false;
  const text = risks.map(String).join(' ');
  if (keyword === 'budget') return /budget|预算|棰勭畻/.test(text);
  if (keyword === 'duration') return /duration|时长|時間|璺嚎|椂闀/.test(text);
  return true;
}

function routeOverlapRatio(leftNames, rightNames) {
  const left = new Set(leftNames);
  const right = new Set(rightNames);
  const overlap = [...left].filter((name) => right.has(name)).length;
  return overlap / Math.max(1, Math.min(left.size, right.size));
}

function validateRouteShape(label, result, options = {}) {
  const planning = planningOf(result);
  const proposal = proposalOf(result);
  const stops = stopsOf(result);
  record('route_generation', `${label}: has planning response`, Boolean(planning), JSON.stringify(Object.keys(result || {})));
  record('route_generation', `${label}: returns multiple proposals`, (planning.proposals || []).length >= 3, `count=${(planning.proposals || []).length}`);
  record('route_generation', `${label}: first proposal has >=3 POIs`, stops.length >= 3, `count=${stops.length}`);
  record('route_generation', `${label}: ordered ids align with stops`, (proposal?.ordered_poi_ids || []).length === stops.length, `ids=${(proposal?.ordered_poi_ids || []).length}, stops=${stops.length}`);
  record('route_generation', `${label}: route has timeline`, stops.every((stop) => /^\d{2}:\d{2}$/.test(String(stop.arrival_time || '')) && /^\d{2}:\d{2}$/.test(String(stop.departure_time || ''))), namesOf(result).join(' -> '));
  record('route_generation', `${label}: route has stay durations`, stops.every((stop) => Number(stop.stay_minutes || 0) > 0), namesOf(result).join(' -> '));
  record('route_generation', `${label}: route has transfer details`, stops.every((stop, index) => index === 0 || (Number.isFinite(Number(stop.transfer_from_previous_minutes)) && Number.isFinite(Number(stop.transfer_from_previous_meters)) && ['commute_edge', 'coordinate_estimate'].includes(String(stop.transfer_source)))), namesOf(result).join(' -> '));
  record('route_generation', `${label}: has quality summary`, Boolean(proposal?.quality_summary), JSON.stringify(proposal?.quality_summary || {}));
  record('route_generation', `${label}: quality marks executable route`, proposal?.quality_summary?.executable_route === true, JSON.stringify(proposal?.quality_summary || {}));
  record('route_generation', `${label}: competition readiness >=0.75`, Number(proposal?.quality_summary?.competition_readiness_score || 0) >= 0.75, JSON.stringify(proposal?.quality_summary || {}));
  record('route_generation', `${label}: llm rerank payload visible`, Boolean(planning.llm_rerank), JSON.stringify(planning.llm_rerank || {}));
  record('route_generation', `${label}: natural language explanation visible`, String(planning.natural_language_explanation || '').length > 0, String(planning.natural_language_explanation || ''));
  record('route_generation', `${label}: final selected proposal visible`, Boolean(planning.final_selected_proposal_id), String(planning.final_selected_proposal_id || ''));
  record('data_grounding', `${label}: transfer source summary visible`, Boolean(proposal?.transfer_source_summary || proposal?.quality_summary?.commute), JSON.stringify(proposal?.transfer_source_summary || proposal?.quality_summary?.commute || {}));
  record('data_grounding', `${label}: database recall metric visible`, typeof planning.generation_metrics?.database_recall_used === 'boolean', JSON.stringify(planning.generation_metrics || {}));
  record('data_grounding', `${label}: llm rerank metric visible`, typeof planning.generation_metrics?.llm_rerank_used === 'boolean', JSON.stringify(planning.generation_metrics || {}));

  if (options.food === true) record('constraint', `${label}: includes requested meal stop`, hasFoodStop(result), namesOf(result).join(' -> '));
  if (options.food === false) record('constraint', `${label}: excludes meal stop`, !hasFoodStop(result), namesOf(result).join(' -> '));

  if (Number.isFinite(options.maxBudget)) {
    const totalBudget = Number(proposal?.total_budget_estimate || 0);
    record('constraint', `${label}: budget satisfied or risk-visible`, totalBudget <= options.maxBudget || riskVisible(proposal, 'budget'), `budget=${totalBudget}, max=${options.maxBudget}`);
  }
  if (Number.isFinite(options.maxDuration)) {
    const totalDuration = Number(proposal?.total_route_duration_min || 0);
    record('constraint', `${label}: duration satisfied or risk-visible`, totalDuration <= options.maxDuration || riskVisible(proposal, 'duration'), `duration=${totalDuration}, max=${options.maxDuration}`);
  }

  if (options.lowWalk) {
    const highWalkStops = stops.filter((stop) => {
      const signals = stop.evidence_summary?.signals || {};
      return stop.walk_intensity === 'high' || signals.walk_intensity === 'high' || /walk:high/.test(JSON.stringify(stop.evidence_summary || {}));
    });
    record('constraint', `${label}: low-walk route avoids obvious high-walk evidence`, highWalkStops.length === 0, highWalkStops.map((stop) => stop.name).join(' -> '));
  }

  record('data_grounding', `${label}: every stop has recommendation reason`, stops.every((stop) => String(stop.recommendation_reason || '').length > 0), namesOf(result).join(' -> '));
  record('data_grounding', `${label}: every stop has evidence summary`, stops.every((stop) => Boolean(stop.evidence_summary)), namesOf(result).join(' -> '));
  const evidencedStops = stops.filter((stop) => {
    const evidence = stop.evidence_summary || {};
    return Number(evidence.evidence_review_count || 0) > 0
      || (Array.isArray(evidence.top_evidence) && evidence.top_evidence.length > 0)
      || Boolean(evidence.signals && Object.keys(evidence.signals).length > 0);
  });
  record('data_grounding', `${label}: at least 2 POIs grounded by UGC/features`, evidencedStops.length >= 2, `grounded=${evidencedStops.length}`);
  record('data_grounding', `${label}: quality summary evidence coverage >=0.5`, Number(proposal?.quality_summary?.data_grounding?.evidence_coverage_rate || 0) >= 0.5, JSON.stringify(proposal?.quality_summary?.data_grounding || {}));

  const metrics = planning.generation_metrics || {};
  record('performance', `${label}: within 10s metric`, metrics.within_10s === true, JSON.stringify(metrics));
}

async function runCoreRouteCases() {
  const cases = [
    {
      label: 'qianmen_meal_budget_queue',
      goal: '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。',
      options: { food: true, maxBudget: 200, maxDuration: 240, lowWalk: true },
    },
    {
      label: 'gugong_culture_no_meal',
      goal: '故宫附近文化路线，不吃饭，预算100以内，少走路。',
      options: { food: false, maxBudget: 100, lowWalk: true },
    },
    {
      label: 'senior_beihai_relaxed',
      goal: '带老人去北海，别太累，中午吃饭。',
      options: { food: true, lowWalk: true },
    },
    {
      label: 'couple_wangfujing_romantic',
      goal: '情侣在王府井晚上玩3小时，吃饭，想浪漫一点，不想排队。',
      options: { food: true, maxDuration: 180 },
    },
    {
      label: 'family_indoor_half_day',
      goal: '亲子半日游，室内优先，中午吃饭，预算300以内。',
      options: { food: true, maxBudget: 300, maxDuration: 240, lowWalk: true },
    },
  ];

  const results = {};
  for (const item of cases) {
    const { json } = await post('/api/v1/travel/parse-and-plan', { goal: item.goal });
    validateRouteShape(item.label, json, item.options);
    results[item.label] = json;
    console.log(`[competition:${item.label}] ${namesOf(json).join(' -> ')}`);
  }
  return results;
}

async function runPersonalizationCases() {
  const cases = [
    ['couple', '情侣在王府井附近玩4小时，中午吃饭，想浪漫一点，预算300以内，少排队', 'couple_romantic'],
    ['senior', '带老人去王府井附近玩4小时，中午吃饭，少走路，别太累，预算300以内', 'senior_relaxed'],
    ['family', '带小孩去王府井附近玩4小时，中午吃饭，亲子友好，别太累，预算300以内', 'family_kids'],
  ];
  const routes = {};
  for (const [label, goal, expectedPersona] of cases) {
    const { json } = await post('/api/v1/travel/parse-and-plan', { goal });
    const snapshot = requestSnapshotOf(json);
    routes[label] = namesOf(json);
    record('personalization', `${label}: persona parsed`, snapshot.persona_id === expectedPersona, `got=${snapshot.persona_id}`);
    validateRouteShape(`persona_${label}`, json, { food: true, maxBudget: 300, maxDuration: 240, lowWalk: label !== 'couple' });
  }
  record('personalization', 'couple and senior routes differ', routeOverlapRatio(routes.couple, routes.senior) < 1, `${routes.couple.join(' -> ')} / ${routes.senior.join(' -> ')}`);
  record('personalization', 'couple and family routes differ', routeOverlapRatio(routes.couple, routes.family) < 1, `${routes.couple.join(' -> ')} / ${routes.family.join(' -> ')}`);
}

async function runReplanCases(seedResults) {
  const gugongSeed = seedResults.gugong_culture_no_meal;
  const qianmenSeed = seedResults.qianmen_meal_budget_queue;
  const gugongBefore = namesOf(gugongSeed);
  const qianmenBefore = namesOf(qianmenSeed);

  const targeted = await post('/api/v1/travel/replan', {
    previous_request: gugongSeed.planning_response.request_snapshot,
    selected_proposal: gugongSeed.planning_response.proposals[0],
    adjustment_text: '把第二个点换成室内点，其他地方不变。',
  });
  const targetedNames = namesOf(targeted.json);
  record('replan', 'replace second stop keeps first', targetedNames[0] === gugongBefore[0], `${gugongBefore.join(' -> ')} => ${targetedNames.join(' -> ')}`);
  record('replan', 'replace second stop changes second', targetedNames[1] !== gugongBefore[1], `${gugongBefore.join(' -> ')} => ${targetedNames.join(' -> ')}`);
  record('replan', 'replace second stop keeps third', targetedNames[2] === gugongBefore[2], `${gugongBefore.join(' -> ')} => ${targetedNames.join(' -> ')}`);

  const addedLunch = await post('/api/v1/travel/replan', {
    previous_request: gugongSeed.planning_response.request_snapshot,
    selected_proposal: gugongSeed.planning_response.proposals[0],
    adjustment_text: '再加一个顺路的午餐地点，原来的点都保留。',
  });
  const addedLunchNames = namesOf(addedLunch.json);
  record('replan', 'add lunch increases route length', addedLunchNames.length === gugongBefore.length + 1, `${gugongBefore.join(' -> ')} => ${addedLunchNames.join(' -> ')}`);
  record('replan', 'add lunch preserves original POIs', gugongBefore.every((name) => addedLunchNames.includes(name)), `${gugongBefore.join(' -> ')} => ${addedLunchNames.join(' -> ')}`);
  record('replan', 'add lunch includes food stop', hasFoodStop(addedLunch.json), addedLunchNames.join(' -> '));

  const budgetReplan = await post('/api/v1/travel/replan', {
    previous_request: qianmenSeed.planning_response.request_snapshot,
    selected_proposal: qianmenSeed.planning_response.proposals[0],
    adjustment_text: '预算降到100，保留第一个点，重新规划。',
  });
  const budgetNames = namesOf(budgetReplan.json);
  const budgetProposal = proposalOf(budgetReplan.json);
  record('replan', 'budget replan preserves first stop', budgetNames[0] === qianmenBefore[0], `${qianmenBefore.join(' -> ')} => ${budgetNames.join(' -> ')}`);
  record('replan', 'budget replan satisfies or exposes budget risk', Number(budgetProposal?.total_budget_estimate || 0) <= 100 || riskVisible(budgetProposal, 'budget'), `budget=${budgetProposal?.total_budget_estimate}`);
}

async function runCommuteCase() {
  const health = await get('/api/v1/travel/health');
  record('data_grounding', 'commute edge index loaded', health.json?.commute?.loaded === true, JSON.stringify(health.json?.commute || {}));
  record('data_grounding', 'commute edge index has rows', Number(health.json?.commute?.edge_count || 0) > 0, `count=${health.json?.commute?.edge_count}`);

  const deterministic = await post('/api/v1/travel/plan', {
    route_mode: 'culture',
    area: '故宫',
    max_total_pois: 3,
    must_include_poi_ids: ['amap_B0H65CPLW1', 'amap_B000A9LF82'],
    route_order_poi_ids: ['amap_B0H65CPLW1', 'amap_B000A9LF82'],
  });
  const stops = stopsOf(deterministic.json);
  const metrics = deterministic.json.generation_metrics || {};
  record('data_grounding', 'deterministic route uses commute edge', stops.some((stop) => stop.transfer_source === 'commute_edge'), namesOf(deterministic.json).join(' -> '));
  record('data_grounding', 'commute metrics report hit rate', Number(metrics.commute_edge_hit_rate || 0) > 0, JSON.stringify(metrics));
}

async function runPerformanceWarmPath() {
  await post('/api/v1/travel/warmup', {});
  const times = [];
  const internalTimes = [];
  for (let index = 0; index < 5; index += 1) {
    const { elapsedMs, json } = await post('/api/v1/travel/parse-and-plan', {
      goal: '故宫附近玩4小时，想看文化景点，少走路，不吃饭，预算100以内',
    });
    times.push(elapsedMs);
    internalTimes.push(Number(json.planning_response?.generation_metrics?.elapsed_ms || Infinity));
  }
  const hotInternal = internalTimes.slice(1);
  record('performance', 'hot planner internal <500ms', hotInternal.every((time) => time < 500), `internal=${internalTimes.join(', ')}`);
  record('performance', 'hot API responses within 10s', times.slice(1).every((time) => time < 10000), `api=${times.join(', ')}`);
}

function summarize() {
  const scores = {};
  let allPassed = true;
  for (const [category, checks] of Object.entries(report)) {
    const passed = checks.filter((check) => check.pass).length;
    const total = checks.length;
    const score = total ? Number((passed / total).toFixed(3)) : 0;
    const pass = score >= 0.8 && total > 0;
    scores[`${category}_score`] = score;
    scores[`${category}_pass`] = pass;
    if (!pass) allPassed = false;
  }
  return { ...scores, overall_pass: allPassed };
}

function printReport(summary) {
  console.log('\n[travel-competition] score report');
  for (const [category, checks] of Object.entries(report)) {
    const failed = checks.filter((check) => !check.pass);
    const passed = checks.length - failed.length;
    console.log(`- ${category}: ${passed}/${checks.length}`);
    for (const check of failed) {
      console.log(`  FAIL ${check.label}: ${check.detail}`);
    }
  }
  console.log(JSON.stringify(summary, null, 2));
}

async function main() {
  const seedResults = await runCoreRouteCases();
  await runPersonalizationCases();
  await runReplanCases(seedResults);
  await runCommuteCase();
  await runPerformanceWarmPath();

  const summary = summarize();
  printReport(summary);
  if (!summary.overall_pass) throw new Error('competition acceptance score below threshold');
  console.log('[travel-competition] passed');
}

main().catch((error) => {
  const summary = summarize();
  printReport(summary);
  console.error('[travel-competition] failed:', error);
  process.exit(1);
});
