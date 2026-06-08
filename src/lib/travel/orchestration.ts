import {
  getTravelCandidateBuckets,
  getTravelEvidence,
  parseAndPlanTravel,
  parseGoalToTravelRequest,
  replanTravelRoute,
  type TravelCandidateBuckets,
  type TravelPlanningRequest,
} from '@/lib/travel/planner';

export type TravelAgentKey =
  | 'intent_agent'
  | 'clarification_agent'
  | 'wiki_retrieval_agent'
  | 'database_recall_agent'
  | 'poi_retrieval_agent'
  | 'ugc_evidence_agent'
  | 'minimax_route_draft_agent'
  | 'route_draft_validator_agent'
  | 'route_composition_agent'
  | 'constraint_judge_agent'
  | 'minimax_rerank_agent';

export type TravelPatchActionType =
  | 'add_stop'
  | 'replace_stop'
  | 'remove_stop'
  | 'tighten_budget'
  | 'shorten_duration'
  | 'reorder_stop'
  | 'meal_refine';

export type TravelPreserveScope =
  | 'all'
  | 'all_except_target'
  | 'meals_only'
  | 'culture_only'
  | 'first_stop_only';

export interface TravelRoutePatch {
  action_type: TravelPatchActionType;
  target_stop_index: number | null;
  target_poi_id: string | null;
  preserve_scope: TravelPreserveScope;
  new_constraints: Partial<TravelPlanningRequest>;
  clarification_needed: boolean;
}

export interface TravelPlanningIntent {
  operation: 'new_plan' | 'replan';
  parsed_request: TravelPlanningRequest;
  patch: TravelRoutePatch | null;
  confidence: number;
  reasons: string[];
}

export interface TravelClarificationDecision {
  required: boolean;
  reason: string | null;
  message: string | null;
}

export interface TravelEvidenceSummary {
  poi_id: string;
  poi_name: string;
  evidence_summary: string[];
  claims: Array<Record<string, any>>;
}

export interface TravelCandidateSet {
  resolved_area: string;
  cultureCandidates: Array<Record<string, any>>;
  mealCandidates: Array<Record<string, any>>;
  snackCandidates: Array<Record<string, any>>;
  indoorCandidates: Array<Record<string, any>>;
}

export interface TravelAgentTraceEntry {
  agent_key: TravelAgentKey;
  status: 'completed' | 'clarification_required';
  started_at: string;
  completed_at: string;
  elapsed_ms: number;
  summary: string;
  input_summary: Record<string, any>;
  output_summary: Record<string, any>;
  payload_preview: Record<string, any>;
}

export interface TravelPlanningSessionState {
  raw_user_input: string;
  conversation_context: {
    operation: 'new_plan' | 'replan';
    request_id: string;
    previous_request_snapshot: Partial<TravelPlanningRequest> | null;
    previous_route_names: string[];
  };
  intent: TravelPlanningIntent | null;
  clarification: TravelClarificationDecision | null;
  candidate_sets: TravelCandidateSet | null;
  evidence_map: Record<string, TravelEvidenceSummary>;
  route_skeleton_before: {
    ordered_poi_ids: string[];
    ordered_poi_names: string[];
  } | null;
  route_patch_request: TravelRoutePatch | null;
  draft_proposals: Array<Record<string, any>>;
  judged_proposals: Array<Record<string, any>>;
  final_selected_proposals: Array<Record<string, any>>;
  agent_trace: TravelAgentTraceEntry[];
}

export interface TravelOrchestrationResult {
  status: 'travel_plan_completed' | 'travel_replan_completed' | 'travel_clarification_required';
  parsed_request?: Record<string, any>;
  parser_confidence?: number;
  parser_notes?: string[];
  parser_correction_hints?: string[];
  planning_response?: Record<string, any>;
  clarification?: TravelClarificationDecision;
  clarificationPayload?: TravelClarificationDecision;
  agentTrace: TravelAgentTraceEntry[];
  sessionState: TravelPlanningSessionState;
  sessionStateSummary: Record<string, any>;
}

function nowIso() {
  return new Date().toISOString();
}

function summarizeStops(proposal: Record<string, any> | null | undefined): string[] {
  return Array.isArray(proposal?.ordered_poi_names) ? proposal.ordered_poi_names.map(String) : [];
}

function normalizeTravelInstruction(value: string): string {
  return value.trim().replace(/^[/\\]+\s*/, '').trim();
}

function getMealStopsFromProposal(proposal: Record<string, any> | null): string[] {
  const pois = Array.isArray(proposal?.pois) ? proposal.pois : [];
  return pois
    .filter((poi: Record<string, any>) => {
      const poiType = String(poi.poi_type || '').toLowerCase();
      const mealType = String(poi.meal_type || '').toLowerCase();
      return poi.meal_slot === 'lunch' || poiType === 'food' || ['meal', 'snack', 'coffee', 'dessert', 'hotel_dining'].includes(mealType);
    })
    .map((poi: Record<string, any>) => String(poi.name || '').trim())
    .filter(Boolean);
}

function needsMealClarification(text: string, proposal: Record<string, any> | null) {
  const normalized = normalizeTravelInstruction(text);
  const asksToAdd = /(再加|添加|增加|加一个|顺路)/.test(normalized);
  const asksMeal = /(午餐|午饭|中午|吃饭|餐饮|餐厅|饭店|小吃|正餐|美食)/.test(normalized);
  const explicitlyReplaces = /(替换|换掉|换一个|换成|改成|去掉|删除|不去|别去|不要去)/.test(normalized);
  const explicitlySecondMeal = /(下午茶|甜品|茶饮|奶茶|咖啡|加餐|晚餐|夜宵)/.test(normalized);
  const mealStops = getMealStopsFromProposal(proposal);
  if (asksToAdd && asksMeal && !explicitlyReplaces && !explicitlySecondMeal && mealStops.length > 0) {
    return {
      required: true,
      reason: 'ambiguous_meal_addition_existing_meal',
      message: [
        '意图澄清 Agent：我识别到你想“再加一个午餐/吃饭地点”，但当前路线里已经有餐饮安排。',
        '',
        `当前餐饮点：${mealStops.join('、')}`,
        '为了避免机械追加第二个午餐、导致路线超时或不符合逻辑，请直接补一句你的选择：',
        '- 替换当前午餐，换成更适合午餐的地方',
        '- 保留当前午餐，再加一个预算50以内的小吃/下午茶',
        '- 保留当前路线，只把午餐时间或预算重新优化',
      ].join('\n'),
    };
  }
  const asksRemove = /(不去|别去|不要去|去掉|排除|避开|取消|删除)/.test(normalized);
  const names = summarizeStops(proposal);
  const genericPlaceOnly = /(不去|别去|不要去|去掉|删除)\s*(这个地方|那个地方|这里|那里|这个点|那个点|这个景点|那个景点|这个地方吧|那个地方吧)/.test(normalized);
  if (asksRemove && (genericPlaceOnly || !/(不去.{2,}|删除.{2,}|去掉.{2,})/.test(normalized))) {
    return {
      required: true,
      reason: 'missing_excluded_place',
      message: [
        '意图澄清 Agent：我识别到你想删除或避开某个地点，但还缺少具体地点名称。',
        '',
        names.length ? `当前路线包含：${names.join('、')}` : '当前还没有可参考的路线地点。',
        '',
        '请直接补一句，例如：',
        '- 不去瑞幸咖啡，换一个更适合午餐的地方',
        '- 去掉第二个点，换成更少走路的室内点',
      ].join('\n'),
    };
  }
  return { required: false, reason: null, message: null };
}

function summarizeSkeleton(existingItinerary: Record<string, any> | null) {
  const proposal = Array.isArray(existingItinerary?.planning_response?.proposals)
    ? existingItinerary?.planning_response?.proposals?.[0]
    : null;
  return proposal
    ? {
        ordered_poi_ids: Array.isArray(proposal.ordered_poi_ids) ? proposal.ordered_poi_ids.map(String) : [],
        ordered_poi_names: summarizeStops(proposal),
      }
    : null;
}

function createEmptyState(params: {
  rawUserInput: string;
  requestId: string;
  operation: 'new_plan' | 'replan';
  previousRequestSnapshot: Partial<TravelPlanningRequest> | null;
  previousRouteNames: string[];
}): TravelPlanningSessionState {
  return {
    raw_user_input: params.rawUserInput,
    conversation_context: {
      operation: params.operation,
      request_id: params.requestId,
      previous_request_snapshot: params.previousRequestSnapshot,
      previous_route_names: params.previousRouteNames,
    },
    intent: null,
    clarification: null,
    candidate_sets: null,
    evidence_map: {},
    route_skeleton_before: params.previousRouteNames.length
      ? {
          ordered_poi_ids: [],
          ordered_poi_names: params.previousRouteNames,
        }
      : null,
    route_patch_request: null,
    draft_proposals: [],
    judged_proposals: [],
    final_selected_proposals: [],
    agent_trace: [],
  };
}

function inferPatch(params: {
  text: string;
  existingItinerary: Record<string, any> | null;
  parsedRequest: TravelPlanningRequest;
  operation: 'new_plan' | 'replan';
}): TravelRoutePatch | null {
  if (params.operation === 'new_plan') return null;
  const text = params.text;
  const previousProposal = Array.isArray(params.existingItinerary?.planning_response?.proposals)
    ? params.existingItinerary?.planning_response?.proposals?.[0]
    : null;
  const previousIds = Array.isArray(previousProposal?.ordered_poi_ids) ? previousProposal.ordered_poi_ids.map(String) : [];
  const previousNames = summarizeStops(previousProposal);
  const targetIndexMatch = text.match(/第\s*([一二三四五六七八九123456789])\s*个点/);
  const targetIndex = targetIndexMatch
    ? Math.max(0, '一二三四五六七八九'.includes(targetIndexMatch[1]) ? '一二三四五六七八九'.indexOf(targetIndexMatch[1]) : Number(targetIndexMatch[1]) - 1)
    : null;
  const targetPoiId = targetIndex !== null ? previousIds[targetIndex] || null : null;
  const targetName = targetIndex !== null ? previousNames[targetIndex] || null : null;

  const patch: TravelRoutePatch = {
    action_type: /不去|去掉|删除|排除|避开/.test(text)
      ? 'remove_stop'
      : /替换|换成|换一个|改成/.test(text)
        ? (/午餐|吃饭|餐饮|小吃|下午茶|咖啡/.test(text) ? 'meal_refine' : 'replace_stop')
        : /预算降到|预算控制|预算压到/.test(text)
          ? 'tighten_budget'
          : /缩短|控制在.*小时|4小时以内|少走路/.test(text) && /重新规划|调整|优化/.test(text)
            ? 'shorten_duration'
            : /加一个|再加|添加|增加|顺路/.test(text)
              ? 'add_stop'
              : 'reorder_stop',
    target_stop_index: targetIndex,
    target_poi_id: targetPoiId,
    preserve_scope: /保留第一个点/.test(text)
      ? 'first_stop_only'
      : /保留当前午餐|午餐不变|保留餐饮/.test(text)
        ? 'meals_only'
        : /文化不变|景点不变/.test(text)
          ? 'culture_only'
          : /其他地方不变|原来的点都保留|保留原路线/.test(text)
            ? (targetPoiId ? 'all_except_target' : 'all')
            : 'all',
    new_constraints: {
      max_budget: params.parsedRequest.max_budget,
      max_duration_min: params.parsedRequest.max_duration_min,
      walk_preference: params.parsedRequest.walk_preference,
    },
    clarification_needed: false,
  };

  if (patch.action_type === 'remove_stop' && !targetPoiId && !targetName && !/不去.{2,}/.test(text)) {
    patch.clarification_needed = true;
  }
  return patch;
}

function buildSessionSummary(state: TravelPlanningSessionState) {
  return {
    operation: state.conversation_context.operation,
    area: state.intent?.parsed_request.area || state.candidate_sets?.resolved_area || null,
    patch_action: state.route_patch_request?.action_type || null,
    clarification_required: Boolean(state.clarification?.required),
    candidate_counts: state.candidate_sets
      ? {
          culture: state.candidate_sets.cultureCandidates.length,
          meal: state.candidate_sets.mealCandidates.length,
          snack: state.candidate_sets.snackCandidates.length,
          indoor: state.candidate_sets.indoorCandidates.length,
        }
      : null,
    final_proposal_count: state.final_selected_proposals.length,
  };
}

function markTrace(
  state: TravelPlanningSessionState,
  entry: Omit<TravelAgentTraceEntry, 'started_at' | 'completed_at' | 'elapsed_ms'> & { elapsed_ms: number },
) {
  const completedAt = nowIso();
  state.agent_trace.push({
    ...entry,
    started_at: completedAt,
    completed_at: completedAt,
    elapsed_ms: entry.elapsed_ms,
  });
}

function compactPoi(item: Record<string, any>) {
  return {
    poi_id: item.poi_id,
    name: item.name,
    area: item.area || item.district || null,
    poi_type: item.poi_type || null,
    meal_type: item.meal_type || null,
    avg_cost: item.avg_cost ?? null,
    rating: item.rating ?? null,
  };
}

async function buildEvidenceMap(candidateSets: TravelCandidateSet) {
  const picked = [
    ...candidateSets.cultureCandidates,
    ...candidateSets.mealCandidates,
    ...candidateSets.snackCandidates,
    ...candidateSets.indoorCandidates,
  ]
    .slice(0, 20)
    .filter((item, index, array) => array.findIndex((other) => other.poi_id === item.poi_id) === index);
  const entries = await Promise.all(
    picked.map(async (poi) => {
      const evidence = await getTravelEvidence(String(poi.poi_id));
      return [
        String(poi.poi_id),
        {
          poi_id: String(poi.poi_id),
          poi_name: String(poi.name || ''),
          evidence_summary: Array.isArray(evidence?.evidence_summary) ? evidence.evidence_summary : evidence?.evidence_summary ? [String(evidence.evidence_summary)] : [],
          claims: Array.isArray(evidence?.claims) ? evidence.claims.slice(0, 4) : [],
        } satisfies TravelEvidenceSummary,
      ] as const;
    }),
  );
  return Object.fromEntries(entries);
}

function judgeProposals(proposals: Array<Record<string, any>>, request: TravelPlanningRequest) {
  return proposals.map((proposal, index) => {
    const risks = Array.isArray(proposal.risks) ? proposal.risks : [];
    const budgetPass = request.max_budget == null || Number(proposal.total_budget_estimate || 0) <= Number(request.max_budget);
    const durationPass = request.max_duration_min == null || Number(proposal.total_route_duration_min || 0) <= Number(request.max_duration_min);
    const foodCount = Array.isArray(proposal.pois) ? proposal.pois.filter((poi: Record<string, any>) => poi.poi_type === 'food').length : 0;
    const cultureCount = Array.isArray(proposal.pois) ? proposal.pois.filter((poi: Record<string, any>) => poi.poi_type !== 'food').length : 0;
    const coveragePass = request.route_mode === 'mixed' ? foodCount >= 1 && cultureCount >= 2 : cultureCount >= 3;
    return {
      ...proposal,
      constraint_judgement: {
        selected_by_agent: index === 0 ? 'constraint_judge_agent' : 'route_composition_agent',
        passes: budgetPass && durationPass && coveragePass,
        budget_pass: budgetPass,
        duration_pass: durationPass,
        coverage_pass: coveragePass,
        reasons: [
          budgetPass ? '预算满足约束。' : '预算超出约束。',
          durationPass ? '总时长满足约束。' : '总时长超出约束。',
          coveragePass ? 'POI 覆盖满足约束。' : 'POI 覆盖不足。',
        ],
        risk_count: risks.length,
      },
      selected_by_agent: index === 0 ? 'constraint_judge_agent' : 'route_composition_agent',
      selection_reasons: Array.isArray(proposal.pois)
        ? proposal.pois.map((poi: Record<string, any>) => ({
            poi_id: poi.poi_id,
            name: poi.name,
            selected_by_agent: poi.poi_type === 'food' ? 'route_composition_agent' : 'poi_retrieval_agent',
            reason: poi.recommendation_reason || 'Matched local POI, evidence, and route constraints.',
          }))
        : [],
    };
  });
}

function buildRouteDiff(beforeNames: string[], afterProposal: Record<string, any> | null) {
  const afterNames = summarizeStops(afterProposal);
  return {
    kept: beforeNames.filter((name) => afterNames.includes(name)),
    removed: beforeNames.filter((name) => !afterNames.includes(name)),
    added: afterNames.filter((name) => !beforeNames.includes(name)),
    reordered: beforeNames.length === afterNames.length && beforeNames.some((name, index) => afterNames[index] !== name),
  };
}

export async function executeTravelPlanningSession(params: {
  text: string;
  requestId: string;
  existingItinerary: Record<string, any> | null;
}): Promise<TravelOrchestrationResult> {
  const previousRequestSnapshot = (params.existingItinerary?.planning_response?.request_snapshot || params.existingItinerary?.parsed_request || null) as Partial<TravelPlanningRequest> | null;
  const previousRouteNames = summarizeSkeleton(params.existingItinerary)?.ordered_poi_names || [];
  const operation = params.existingItinerary ? 'replan' : 'new_plan';
  const state = createEmptyState({
    rawUserInput: params.text,
    requestId: params.requestId,
    operation,
    previousRequestSnapshot,
    previousRouteNames,
  });
  state.route_skeleton_before = summarizeSkeleton(params.existingItinerary);

  const intentStarted = performance.now();
  const parsed = await parseGoalToTravelRequest(params.text, previousRequestSnapshot || undefined);
  const patch = inferPatch({
    text: params.text,
    existingItinerary: params.existingItinerary,
    parsedRequest: parsed.parsed_request,
    operation,
  });
  state.intent = {
    operation,
    parsed_request: parsed.parsed_request,
    patch,
    confidence: parsed.parser_confidence,
    reasons: parsed.parser_notes,
  };
  state.route_patch_request = patch;
  markTrace(state, {
    agent_key: 'intent_agent',
    status: 'completed',
    elapsed_ms: Number((performance.now() - intentStarted).toFixed(2)),
    summary: operation === 'replan' ? '识别为动态重规划请求。' : '识别为首次路线规划请求。',
    input_summary: { raw_user_input: params.text, previous_route_names: previousRouteNames },
    output_summary: {
      operation,
      area: parsed.parsed_request.area || null,
      budget: parsed.parsed_request.max_budget ?? null,
      duration: parsed.parsed_request.max_duration_min ?? null,
      patch_action: patch?.action_type || null,
    },
    payload_preview: {
      parsed_request: parsed.parsed_request,
      patch,
    },
  });

  const clarificationStarted = performance.now();
  const primaryProposal = Array.isArray(params.existingItinerary?.planning_response?.proposals)
    ? params.existingItinerary?.planning_response?.proposals?.[0]
    : null;
  const clarification = operation === 'replan' ? needsMealClarification(params.text, primaryProposal) : { required: false, reason: null, message: null };
  state.clarification = {
    required: Boolean(clarification.required),
    reason: clarification.reason ?? null,
    message: clarification.message ?? null,
  };
  markTrace(state, {
    agent_key: 'clarification_agent',
    status: clarification.required ? 'clarification_required' : 'completed',
    elapsed_ms: Number((performance.now() - clarificationStarted).toFixed(2)),
    summary: clarification ? '命中澄清规则，等待用户补充。' : '当前请求无需额外澄清。',
    input_summary: {
      operation,
      patch_action: patch?.action_type || null,
      previous_route_names: previousRouteNames,
    },
    output_summary: {
      required: Boolean(clarification.required),
      reason: clarification.reason ?? null,
    },
    payload_preview: state.clarification,
  });

  if (clarification.required) {
    return {
      status: 'travel_clarification_required',
      clarification: state.clarification,
      clarificationPayload: state.clarification,
      agentTrace: state.agent_trace,
      sessionState: state,
      sessionStateSummary: buildSessionSummary(state),
    };
  }

  const retrievalStarted = performance.now();
  const buckets: TravelCandidateBuckets = await getTravelCandidateBuckets(parsed.parsed_request);
  state.candidate_sets = {
    resolved_area: buckets.resolved_area,
    cultureCandidates: buckets.cultureCandidates.map(compactPoi),
    mealCandidates: buckets.mealCandidates.map(compactPoi),
    snackCandidates: buckets.snackCandidates.map(compactPoi),
    indoorCandidates: buckets.indoorCandidates.map(compactPoi),
  };
  markTrace(state, {
    agent_key: 'poi_retrieval_agent',
    status: 'completed',
    elapsed_ms: Number((performance.now() - retrievalStarted).toFixed(2)),
    summary: '已按区域和类型分桶筛选候选 POI。',
    input_summary: {
      area: parsed.parsed_request.area || buckets.resolved_area,
      route_mode: parsed.parsed_request.route_mode,
      walk_preference: parsed.parsed_request.walk_preference,
    },
    output_summary: {
      resolved_area: buckets.resolved_area,
      culture_count: state.candidate_sets.cultureCandidates.length,
      meal_count: state.candidate_sets.mealCandidates.length,
      snack_count: state.candidate_sets.snackCandidates.length,
      indoor_count: state.candidate_sets.indoorCandidates.length,
    },
    payload_preview: state.candidate_sets,
  });

  const evidenceStarted = performance.now();
  state.evidence_map = await buildEvidenceMap(state.candidate_sets);
  markTrace(state, {
    agent_key: 'ugc_evidence_agent',
    status: 'completed',
    elapsed_ms: Number((performance.now() - evidenceStarted).toFixed(2)),
    summary: '已整理候选点的 UGC 证据和风险信号。',
    input_summary: { candidate_count: Object.keys(state.evidence_map).length },
    output_summary: {
      evidence_pois: Object.keys(state.evidence_map).length,
    },
    payload_preview: {
      evidence_map: Object.fromEntries(Object.entries(state.evidence_map).slice(0, 6)),
    },
  });

  const routeStarted = performance.now();
  const planningResponse = (operation === 'replan'
    ? await replanTravelRoute({
        previous_request: previousRequestSnapshot || undefined,
        selected_proposal: Array.isArray(params.existingItinerary?.planning_response?.proposals)
          ? params.existingItinerary?.planning_response?.proposals?.[0]
          : undefined,
        adjustment_text: params.text,
      })
    : (await parseAndPlanTravel({ goal: params.text, defaults: previousRequestSnapshot || undefined })).planning_response) as Record<string, any>;
  const wikiRetrieval = planningResponse.wiki_retrieval || null;
  markTrace(state, {
    agent_key: 'wiki_retrieval_agent',
    status: 'completed',
    elapsed_ms: Number(wikiRetrieval?.elapsed_ms || planningResponse.generation_metrics?.wiki_retrieval_elapsed_ms || 0),
    summary: Array.isArray(wikiRetrieval?.hits) && wikiRetrieval.hits.length > 0
      ? '已从 Obsidian LLM-Wiki 检索路线知识证据。'
      : 'Obsidian LLM-Wiki 未命中可用证据。',
    input_summary: {
      vault_path: wikiRetrieval?.vault_path || 'travel-data/wiki',
      query: params.text,
    },
    output_summary: {
      hit_count: Array.isArray(wikiRetrieval?.hits) ? wikiRetrieval.hits.length : 0,
      citation_count: Array.isArray(wikiRetrieval?.citations) ? wikiRetrieval.citations.length : 0,
      wiki_retrieval_used: Boolean(planningResponse.generation_metrics?.wiki_retrieval_used),
    },
    payload_preview: {
      hits: Array.isArray(wikiRetrieval?.hits) ? wikiRetrieval.hits.slice(0, 5) : [],
      citations: Array.isArray(wikiRetrieval?.citations) ? wikiRetrieval.citations.slice(0, 5) : [],
    },
  });
  const databaseRecallResults = Array.isArray(planningResponse.query_results) ? planningResponse.query_results : [];
  markTrace(state, {
    agent_key: 'database_recall_agent',
    status: 'completed',
    elapsed_ms: Number(planningResponse.generation_metrics?.sql_elapsed_ms || 0),
    summary: databaseRecallResults.length > 0 ? '已通过白名单 SQL 召回 POI / UGC / 区域画像候选。' : '当前请求缺少关键字段或未执行数据库召回。',
    input_summary: {
      query_plan_steps: Array.isArray(planningResponse.query_plan?.steps) ? planningResponse.query_plan.steps.length : 0,
    },
    output_summary: {
      template_count: databaseRecallResults.length,
      database_recall_used: Boolean(planningResponse.generation_metrics?.database_recall_used),
    },
    payload_preview: {
      query_plan: planningResponse.query_plan || null,
      results: databaseRecallResults.slice(0, 4),
    },
  });
  const routeDraft = planningResponse.route_draft || null;
  markTrace(state, {
    agent_key: 'minimax_route_draft_agent',
    status: 'completed',
    elapsed_ms: Number(routeDraft?.elapsed_ms || planningResponse.generation_metrics?.draft_elapsed_ms || 0),
    summary: routeDraft?.draft_source === 'minimax'
      ? 'MiniMax selected and ordered POIs from the backend candidate pool.'
      : 'MiniMax RouteDraft was unavailable; the system used a safe rule fallback draft.',
    input_summary: {
      candidate_pool_locked: true,
      model: routeDraft?.model || null,
      llm_attempted: Boolean(routeDraft?.llm_attempted || routeDraft?.llm_used),
    },
    output_summary: {
      draft_source: routeDraft?.draft_source || null,
      llm_used: Boolean(routeDraft?.llm_used),
      ordered_poi_count: Array.isArray(routeDraft?.ordered_poi_ids) ? routeDraft.ordered_poi_ids.length : 0,
      fallback_reason: routeDraft?.fallback_reason || planningResponse.generation_metrics?.draft_fallback_reason || null,
    },
    payload_preview: {
      ordered_poi_ids: Array.isArray(routeDraft?.ordered_poi_ids) ? routeDraft.ordered_poi_ids : [],
      meal_stop_id: routeDraft?.meal_stop_id || null,
      preference_reasoning: routeDraft?.preference_reasoning || null,
      known_risks: Array.isArray(routeDraft?.known_risks) ? routeDraft.known_risks.slice(0, 4) : [],
    },
  });
  const validatorResult = planningResponse.validator_result || null;
  const repairActions = Array.isArray(planningResponse.repair_actions) ? planningResponse.repair_actions : [];
  markTrace(state, {
    agent_key: 'route_draft_validator_agent',
    status: 'completed',
    elapsed_ms: 0,
    summary: validatorResult?.status === 'valid'
      ? 'RouteDraft passed backend safety validation.'
      : validatorResult?.status === 'repaired'
        ? 'RouteDraft was repaired before executable timeline generation.'
        : 'RouteDraft validation required fallback or rejection handling.',
    input_summary: {
      route_draft_present: Boolean(routeDraft),
      requested_meal: Boolean(
        parsed.parsed_request.preference_signals?.lunch ||
          parsed.parsed_request.preference_signals?.formal_meal ||
          parsed.parsed_request.preference_signals?.snack,
      ),
      max_budget: parsed.parsed_request.max_budget ?? null,
      max_duration_min: parsed.parsed_request.max_duration_min ?? null,
    },
    output_summary: {
      validator_status: validatorResult?.status || null,
      valid_poi_count: Array.isArray(validatorResult?.validated_poi_ids) ? validatorResult.validated_poi_ids.length : 0,
      repair_action_count: repairActions.length,
    },
    payload_preview: {
      validator_result: validatorResult,
      repair_actions: repairActions.slice(0, 6),
    },
  });
  state.draft_proposals = Array.isArray(planningResponse.proposals) ? planningResponse.proposals : [];
  const routePatchSummary = buildRouteDiff(previousRouteNames, state.draft_proposals[0] || null);
  const primaryTransferSummary = state.draft_proposals[0]?.transfer_source_summary || state.draft_proposals[0]?.quality_summary?.commute || {};
  const commuteEdgesUsed = Number(primaryTransferSummary.commute_edges_used || 0);
  const coordinateEstimatesUsed = Number(primaryTransferSummary.coordinate_estimates_used || 0);
  markTrace(state, {
    agent_key: 'route_composition_agent',
    status: 'completed',
    elapsed_ms: Number((performance.now() - routeStarted).toFixed(2)),
    summary: operation === 'replan' ? '已基于旧骨架生成局部重规划方案。' : '已生成多套候选路线方案。',
    input_summary: {
      operation,
      previous_route_names: previousRouteNames,
      patch_action: patch?.action_type || null,
    },
    output_summary: {
      proposal_count: state.draft_proposals.length,
      route_patch_summary: routePatchSummary,
      commute_edges_used: commuteEdgesUsed,
      coordinate_estimates_used: coordinateEstimatesUsed,
    },
    payload_preview: {
      top_proposal: state.draft_proposals[0]
        ? {
            title: state.draft_proposals[0].display_title || state.draft_proposals[0].title || state.draft_proposals[0].strategy,
            ordered_poi_names: state.draft_proposals[0].ordered_poi_names,
          }
        : null,
      route_patch_summary: routePatchSummary,
      transfer_source_summary: primaryTransferSummary,
    },
  });

  const judgeStarted = performance.now();
  state.judged_proposals = judgeProposals(state.draft_proposals, parsed.parsed_request);
  state.final_selected_proposals = state.judged_proposals;
  markTrace(state, {
    agent_key: 'constraint_judge_agent',
    status: 'completed',
    elapsed_ms: Number((performance.now() - judgeStarted).toFixed(2)),
    summary: '已完成预算、时长、覆盖率和风险校验。',
    input_summary: {
      proposal_count: state.draft_proposals.length,
      budget_limit: parsed.parsed_request.max_budget ?? null,
      duration_limit: parsed.parsed_request.max_duration_min ?? null,
    },
    output_summary: {
      passed_count: state.judged_proposals.filter((proposal) => proposal.constraint_judgement?.passes).length,
      primary_passes: Boolean(state.judged_proposals[0]?.constraint_judgement?.passes),
    },
    payload_preview: {
      primary_constraint_judgement: state.judged_proposals[0]?.constraint_judgement || null,
    },
  });

  const llmRerank = planningResponse.llm_rerank || null;
  markTrace(state, {
    agent_key: 'minimax_rerank_agent',
    status: 'completed',
    elapsed_ms: Number(llmRerank?.elapsed_ms || 0),
    summary: llmRerank?.llm_used
      ? 'MiniMax 已对 3 个候选方案做偏好重排，并生成自然语言解释。'
      : llmRerank?.rerank_source === 'wiki_local'
        ? 'MiniMax 未返回合规结果，已由 Obsidian Wiki 证据接管本地重排。'
        : 'MiniMax 偏好重排未生效，保留规则 planner 原始排序。',
    input_summary: {
      proposal_count: state.judged_proposals.length,
      model: llmRerank?.model || null,
    },
    output_summary: {
      llm_rerank_used: Boolean(llmRerank?.llm_used),
      rerank_source: llmRerank?.rerank_source || null,
      primary_proposal_id: llmRerank?.primary_proposal_id || planningResponse.final_selected_proposal_id || null,
      fallback_reason: llmRerank?.fallback_reason || null,
    },
    payload_preview: {
      llm_rerank: llmRerank,
      natural_language_explanation: planningResponse.natural_language_explanation || null,
    },
  });

  const finalPlanning = {
    ...planningResponse,
    proposals: state.judged_proposals,
    route_patch_summary: routePatchSummary,
  } as Record<string, any>;

  return {
    status: operation === 'replan' ? 'travel_replan_completed' : 'travel_plan_completed',
    parsed_request: operation === 'replan' ? finalPlanning.request_snapshot : parsed.parsed_request,
    parser_confidence: parsed.parser_confidence,
    parser_notes: parsed.parser_notes,
    parser_correction_hints: parsed.parser_correction_hints,
    planning_response: finalPlanning,
    agentTrace: state.agent_trace,
    sessionState: state,
    sessionStateSummary: buildSessionSummary(state),
  };
}
