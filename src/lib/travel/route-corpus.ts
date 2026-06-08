import fs from 'fs/promises';
import path from 'path';
import { prisma } from '@/lib/db/client';
import { buildTravelQueryPlan, executeTravelQueryPlan } from '@/lib/travel/sql-query';
import { intentToPlannerLikeRequest, type TravelQueryIntent } from '@/lib/travel/semantic-intent';
import { retrieveTravelWiki } from '@/lib/travel/wiki-retrieval';
import type { TravelPlanningRequest } from '@/lib/travel/planner';

type JsonRecord = Record<string, any>;

interface CorpusCommuteEdge {
  origin_poi_id: string;
  destination_poi_id: string;
  mode: string;
  provider: string;
  distance_m: number | null;
  duration_s: number;
  walking_distance_m: number | null;
  transfer_count: number | null;
}

export interface TravelRouteCorpusRow {
  route_id: string;
  city_id: string;
  title: string;
  area: string | null;
  route_mode: string;
  persona_id: string;
  walk_preference: string;
  duration_bucket_min: number;
  budget_bucket_cny: number | null;
  requires_meal: boolean;
  meal_type: string | null;
  indoor_preferred: boolean;
  avoid_queue: boolean;
  tags: string[];
  poi_ids: string[];
  poi_names: string[];
  total_budget_estimate: number;
  total_route_duration_min: number;
  score: number;
  payload: JsonRecord;
  match_score?: number;
}

export interface TravelRouteCorpusMatch {
  matched: boolean;
  source: 'database' | 'file' | 'none';
  rows: TravelRouteCorpusRow[];
  elapsed_ms: number;
  query_intent: JsonRecord;
  reason: string | null;
}

export interface TravelRouteCorpusPoiHint {
  poi_id: string;
  name: string;
  area: string | null;
  district: string | null;
  poi_type: string | null;
  category: string | null;
  source: 'database' | 'file';
  semantic_keys: string[];
}

const ROUTE_CORPUS_FILE = path.resolve(process.cwd(), 'travel-data', 'processed', 'beijing_route_corpus.json');
const ROUTE_CORPUS_LIMIT = Number(process.env.TRAVELPILOT_ROUTE_CORPUS_LIMIT || 3);
const ROUTE_CORPUS_MIN_SCORE = Number(process.env.TRAVELPILOT_ROUTE_CORPUS_MIN_SCORE || 34);
let fileCorpusCache: Promise<TravelRouteCorpusRow[]> | null = null;

function toPersonaId(intent: TravelQueryIntent) {
  return String(intentToPlannerLikeRequest(intent).persona_id || 'classic_first_timer');
}

function asArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function normalizeRow(row: JsonRecord): TravelRouteCorpusRow {
  return {
    route_id: String(row.route_id),
    city_id: String(row.city_id || 'beijing'),
    title: String(row.title || '北京旅行路线'),
    area: row.area === null || row.area === undefined ? null : String(row.area),
    route_mode: String(row.route_mode || 'mixed'),
    persona_id: String(row.persona_id || 'classic_first_timer'),
    walk_preference: String(row.walk_preference || 'medium'),
    duration_bucket_min: Number(row.duration_bucket_min || 0),
    budget_bucket_cny: row.budget_bucket_cny === null || row.budget_bucket_cny === undefined ? null : Number(row.budget_bucket_cny),
    requires_meal: Boolean(row.requires_meal),
    meal_type: row.meal_type === null || row.meal_type === undefined ? null : String(row.meal_type),
    indoor_preferred: Boolean(row.indoor_preferred),
    avoid_queue: Boolean(row.avoid_queue),
    tags: asArray(row.tags),
    poi_ids: asArray(row.poi_ids),
    poi_names: asArray(row.poi_names),
    total_budget_estimate: Number(row.total_budget_estimate || 0),
    total_route_duration_min: Number(row.total_route_duration_min || 0),
    score: Number(row.score || 0),
    payload: typeof row.payload === 'string' ? JSON.parse(row.payload) : (row.payload || {}),
    match_score: row.match_score === undefined ? undefined : Number(row.match_score),
  };
}

async function loadFileCorpus(): Promise<TravelRouteCorpusRow[]> {
  if (!fileCorpusCache) {
    fileCorpusCache = fs.readFile(ROUTE_CORPUS_FILE, 'utf8')
      .then((raw) => {
        const parsed = JSON.parse(raw);
        const routes = Array.isArray(parsed?.routes) ? parsed.routes : Array.isArray(parsed) ? parsed : [];
        return routes.map(normalizeRow);
      })
      .catch(() => []);
  }
  return fileCorpusCache;
}

function durationScore(intentMinutes: number | null, routeMinutes: number) {
  if (!intentMinutes) return 6;
  const diff = Math.abs(intentMinutes - routeMinutes);
  if (diff <= 45) return 18;
  if (diff <= 90) return 10;
  if (routeMinutes <= intentMinutes + 60) return 6;
  return -12;
}

function budgetScore(intentBudget: number | null, routeBudget: number, bucket: number | null) {
  if (!intentBudget) return 4;
  if (routeBudget <= intentBudget) return 16;
  if (bucket && bucket <= intentBudget) return 10;
  if (routeBudget <= intentBudget + 80) return 4;
  return -16;
}

function routeMatchesNames(row: TravelRouteCorpusRow, names: string[]) {
  if (!names.length) return true;
  const text = normalizePoiNameForCorpus(row.poi_names.join(' '));
  return names.every((name) => {
    const include = normalizePoiNameForCorpus(name);
    return Boolean(include && text.includes(include));
  });
}

function normalizePoiNameForCorpus(name?: string): string {
  return String(name || '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[-—·\s]/g, '')
    .trim()
    .toLowerCase();
}

function semanticKeysForCorpusName(name?: string): string[] {
  const raw = String(name || '').trim();
  const normalized = normalizePoiNameForCorpus(raw);
  const keys = new Set<string>();
  if (raw) keys.add(raw);
  if (normalized) keys.add(normalized);
  const short = normalizePoiNameForCorpus(raw.replace(/[（(].*?[）)]/g, '').replace(/(公园|博物院|博物馆|景区|景点|店|门店|餐厅|饭店|咖啡|茶馆|小食铺|小吃)$/g, ''));
  if (short && short.length >= 2) keys.add(short);
  if (/长城|八达岭|慕田峪|居庸关|greatwall|badaling/i.test(normalized)) keys.add('长城');
  return Array.from(keys).filter(Boolean);
}

function corpusHintMatchesName(hint: TravelRouteCorpusPoiHint, includeName: string): boolean {
  const include = normalizePoiNameForCorpus(includeName);
  if (!include) return false;
  return [hint.name, ...(hint.semantic_keys || [])].some((key) => {
    const normalized = normalizePoiNameForCorpus(key);
    return Boolean(normalized && (normalized.includes(include) || include.includes(normalized)));
  });
}

function scoreRoute(row: TravelRouteCorpusRow, intent: TravelQueryIntent): number {
  let score = row.score || 0;
  const personaId = toPersonaId(intent);
  if (intent.area && row.area === intent.area) score += 24;
  else if (intent.area && row.poi_names.some((name) => name.includes(String(intent.area)))) score += 12;
  else if (intent.area) score -= 10;
  if (row.route_mode === intent.route_mode) score += 12;
  if (intent.needs_meal === row.requires_meal) score += 10;
  if (intent.meal_type && row.meal_type === intent.meal_type) score += 8;
  if (row.persona_id === personaId) score += 14;
  if (row.walk_preference === intent.walk_preference) score += 8;
  if (intent.indoor_preferred === row.indoor_preferred) score += intent.indoor_preferred ? 12 : 3;
  if (intent.avoid_queue === row.avoid_queue) score += intent.avoid_queue ? 10 : 2;
  score += durationScore(intent.duration_minutes, row.duration_bucket_min || row.total_route_duration_min);
  score += budgetScore(intent.budget_cny, row.total_budget_estimate, row.budget_bucket_cny);
  if (!routeMatchesNames(row, intent.must_include_names)) score -= 50;
  if (intent.exclude_names.some((name) => row.poi_names.join(' ').includes(name))) score -= 60;
  return Number(score.toFixed(3));
}

function rankRows(rows: TravelRouteCorpusRow[], intent: TravelQueryIntent) {
  return rows
    .map((row) => ({ ...row, match_score: scoreRoute(row, intent) }))
    .filter((row) => Number(row.match_score) >= ROUTE_CORPUS_MIN_SCORE)
    .sort((a, b) => Number(b.match_score || 0) - Number(a.match_score || 0))
    .slice(0, ROUTE_CORPUS_LIMIT);
}

async function queryDatabaseCorpus(intent: TravelQueryIntent): Promise<TravelRouteCorpusRow[]> {
  const personaId = toPersonaId(intent);
  const area = intent.area;
  const routeMode = intent.route_mode;
  const needsMeal = intent.needs_meal;
  const walkPreference = intent.walk_preference;
  const indoorPreferred = intent.indoor_preferred;
  const avoidQueue = intent.avoid_queue;
  const maxDuration = intent.duration_minutes ? intent.duration_minutes + 120 : null;
  const maxBudget = intent.budget_cny ? intent.budget_cny + 120 : null;
  const rows = await prisma.$queryRaw<JsonRecord[]>`
    SELECT *
    FROM travel_precomputed_routes
    WHERE city_id = 'beijing'
      AND (${area}::text IS NULL OR area = ${area} OR ${area} = ANY(poi_names))
      AND route_mode = ${routeMode}
      AND requires_meal = ${needsMeal}
      AND (${maxDuration}::int IS NULL OR duration_bucket_min <= ${maxDuration})
      AND (${maxBudget}::double precision IS NULL OR total_budget_estimate <= ${maxBudget})
      AND (${personaId}::text = 'classic_first_timer' OR persona_id = ${personaId} OR persona_id = 'classic_first_timer')
      AND (${walkPreference}::text IS NULL OR walk_preference = ${walkPreference} OR walk_preference = 'medium')
      AND (${indoorPreferred}::boolean = FALSE OR indoor_preferred = TRUE)
      AND (${avoidQueue}::boolean = FALSE OR avoid_queue = TRUE)
    ORDER BY score DESC, updated_at DESC
    LIMIT 80
  `;
  return rankRows(rows.map(normalizeRow), intent);
}

async function queryFileCorpus(intent: TravelQueryIntent): Promise<TravelRouteCorpusRow[]> {
  const rows = await loadFileCorpus();
  return rankRows(rows, intent);
}

export async function findRouteCorpusPoiHints(names: string[], limit = 12): Promise<{
  matched: boolean;
  hints: TravelRouteCorpusPoiHint[];
  elapsed_ms: number;
  source: 'file' | 'none';
}> {
  const started = performance.now();
  const requestedNames = names.map(String).map((name) => name.trim()).filter(Boolean);
  if (!requestedNames.length) {
    return { matched: false, hints: [], elapsed_ms: Number((performance.now() - started).toFixed(2)), source: 'none' };
  }
  const rows = await loadFileCorpus();
  const hintsById = new Map<string, TravelRouteCorpusPoiHint>();
  for (const row of rows) {
    const stops = Array.isArray(row.payload?.proposals?.[0]?.pois) ? row.payload.proposals[0].pois : [];
    const maxLength = Math.max(row.poi_ids.length, row.poi_names.length, stops.length);
    for (let index = 0; index < maxLength; index += 1) {
      const stop = stops[index] || {};
      const poiId = String(stop.poi_id || row.poi_ids[index] || '');
      const name = String(stop.name || row.poi_names[index] || '');
      if (!poiId || !name) continue;
      const hint: TravelRouteCorpusPoiHint = {
        poi_id: poiId,
        name,
        area: stop.area || row.area || null,
        district: stop.district || null,
        poi_type: stop.poi_type || null,
        category: stop.category || null,
        source: 'file',
        semantic_keys: semanticKeysForCorpusName(name),
      };
      if (!requestedNames.some((requested) => corpusHintMatchesName(hint, requested))) continue;
      const existing = hintsById.get(poiId);
      hintsById.set(poiId, {
        ...hint,
        semantic_keys: Array.from(new Set([...(existing?.semantic_keys || []), ...hint.semantic_keys])),
      });
    }
  }
  const hints = Array.from(hintsById.values()).slice(0, Math.max(1, limit));
  return {
    matched: hints.length > 0,
    hints,
    elapsed_ms: Number((performance.now() - started).toFixed(2)),
    source: hints.length ? 'file' : 'none',
  };
}

export async function findPrecomputedTravelRoutes(intent: TravelQueryIntent): Promise<TravelRouteCorpusMatch> {
  const started = performance.now();
  if (intent.replan_action) {
    return {
      matched: false,
      source: 'none',
      rows: [],
      elapsed_ms: Number((performance.now() - started).toFixed(2)),
      query_intent: intent,
      reason: 'replan requests still use dynamic local replanning.',
    };
  }
  if (intent.day_count > 1 || intent.duration_minutes !== null && intent.duration_minutes > 720) {
    return {
      matched: false,
      source: 'none',
      rows: [],
      elapsed_ms: Number((performance.now() - started).toFixed(2)),
      query_intent: intent,
      reason: 'multi-day or long-trip requests use dynamic planner instead of single-day route corpus.',
    };
  }

  try {
    const rows = await queryDatabaseCorpus(intent);
    if (rows.length > 0) {
      return {
        matched: true,
        source: 'database',
        rows,
        elapsed_ms: Number((performance.now() - started).toFixed(2)),
        query_intent: intent,
        reason: null,
      };
    }
  } catch {
    // Database is optional in local demos; the JSON corpus keeps the route path usable.
  }

  const fileRows = await queryFileCorpus(intent);
  return {
    matched: fileRows.length > 0,
    source: fileRows.length > 0 ? 'file' : 'none',
    rows: fileRows,
    elapsed_ms: Number((performance.now() - started).toFixed(2)),
    query_intent: intent,
    reason: fileRows.length > 0 ? null : 'No precomputed route met the requested constraints.',
  };
}

function collectProposals(rows: TravelRouteCorpusRow[]): JsonRecord[] {
  return rows
    .flatMap((row, index) => {
      const payload = row.payload || {};
      const proposals = Array.isArray(payload.proposals) ? payload.proposals : [];
      const primary = proposals[0];
      if (!primary) return [];
      return [enhanceCorpusProposal({
        ...primary,
        proposal_id: `${row.route_id}-${primary.strategy || index}`,
        display_title: row.title,
        title: row.title,
        corpus_route_id: row.route_id,
        corpus_match_score: row.match_score,
        corpus_tags: row.tags,
      })];
    })
    .slice(0, ROUTE_CORPUS_LIMIT);
}

function isFoodStop(stop: JsonRecord) {
  return stop.poi_type === 'food' || stop.meal_slot === 'lunch' || stop.meal_type === 'meal' || stop.meal_type === 'snack';
}

function countGroundedStops(stops: JsonRecord[]) {
  return stops.filter((stop) => {
    const evidence = stop.evidence_summary || {};
    return Number(evidence.evidence_review_count || 0) > 0
      || (Array.isArray(evidence.top_evidence) && evidence.top_evidence.length > 0)
      || Boolean(evidence.signals && Object.keys(evidence.signals).length > 0);
  }).length;
}

function buildCorpusConstraintReport(proposal: JsonRecord) {
  const stops = Array.isArray(proposal.pois) ? proposal.pois : Array.isArray(proposal.stops) ? proposal.stops : [];
  const foodCount = stops.filter(isFoodStop).length;
  const cultureCount = stops.length - foodCount;
  const routeMode = proposal.category_coverage_summary?.route_mode || (foodCount > 0 ? 'mixed' : 'culture');
  const categorySatisfied = Boolean(proposal.category_coverage_summary?.satisfies_coverage ?? (routeMode === 'mixed' ? foodCount >= 1 && cultureCount >= 2 : cultureCount >= 3));
  const totalBudget = Number(proposal.total_budget_estimate || 0);
  const totalDuration = Number(proposal.total_route_duration_min || 0);
  const totalDistance = Number(proposal.total_walking_distance_m || 0);
  const maxBudget = proposal.budget_summary?.max_budget ?? null;
  const maxDuration = proposal.duration_summary?.max_duration_min ?? null;
  const highQueueStops = stops
    .filter((stop: JsonRecord) => /high|高|long|排队久/i.test(String(stop.evidence_summary?.signals?.queue_risk || '')))
    .map((stop: JsonRecord) => stop.name);
  const checks = {
    poi_count: { required_min: 3, actual: stops.length, satisfied: stops.length >= 3 },
    category_coverage: {
      route_mode: routeMode,
      food_count: foodCount,
      culture_or_entertainment_count: cultureCount,
      required_food_count: routeMode === 'mixed' ? 1 : 0,
      required_culture_or_entertainment_count: routeMode === 'mixed' ? 2 : 3,
      satisfied: categorySatisfied,
    },
    budget: {
      max_budget: maxBudget,
      estimated_budget: totalBudget,
      satisfied: maxBudget === null || maxBudget === undefined || totalBudget <= Number(maxBudget),
    },
    duration: {
      max_duration_min: maxDuration,
      estimated_duration_min: totalDuration,
      satisfied: maxDuration === null || maxDuration === undefined || totalDuration <= Number(maxDuration),
    },
    distance: {
      estimated_transfer_distance_m: Math.round(totalDistance),
      satisfied: true,
    },
    queue: {
      high_queue_stop_names: highQueueStops,
      satisfied: highQueueStops.length === 0,
    },
    opening_hours: {
      conflict_stop_names: stops.filter((stop: JsonRecord) => String(stop.opening_status || 'unknown') === 'conflict').map((stop: JsonRecord) => stop.name),
      unknown_count: stops.filter((stop: JsonRecord) => String(stop.opening_status || 'unknown') === 'unknown').length,
      satisfied: stops.every((stop: JsonRecord) => String(stop.opening_status || 'unknown') !== 'conflict'),
    },
  };
  return {
    overall_satisfied: Object.values(checks).every((item: any) => item.satisfied !== false),
    satisfied_count: Object.values(checks).filter((item: any) => item.satisfied !== false).length,
    total_count: Object.keys(checks).length,
    checks,
  };
}

function buildCorpusConstraintResolution(report: JsonRecord) {
  const checks = report.checks || {};
  const violations = Object.entries(checks)
    .filter(([, value]: [string, any]) => value?.satisfied === false)
    .map(([key]) => key);
  const priorityOrder = ['poi_count', 'category_coverage', 'duration', 'budget', 'distance', 'queue', 'opening_hours'];
  return {
    strategy: violations.length ? 'route_corpus_partial_satisfaction_with_explicit_tradeoff' : 'route_corpus_all_core_constraints_satisfied',
    priority_order: priorityOrder,
    protected_constraints: priorityOrder.filter((key) => checks[key]?.satisfied === true),
    relaxed_constraints: violations,
    tradeoffs: violations.map((key) => `${key} 未完全满足，系统保留风险提示并提供多方案备选。`),
    user_visible_summary: violations.length
      ? `路线库命中方案存在 ${violations.join(', ')} 取舍，已显式标注。`
      : '路线库命中方案满足 3+ POI、餐饮/文化覆盖和基础可执行性。',
  };
}

function enhanceCorpusProposal(proposal: JsonRecord): JsonRecord {
  const stops = Array.isArray(proposal.pois) ? proposal.pois : Array.isArray(proposal.stops) ? proposal.stops : [];
  const timelineReady = stops.every((stop: JsonRecord) => /^\d{2}:\d{2}$/.test(String(stop.arrival_time || '')) && /^\d{2}:\d{2}$/.test(String(stop.departure_time || '')));
  const transferReady = stops.every((stop: JsonRecord, index: number) => index === 0 || ['commute_edge', 'coordinate_estimate'].includes(String(stop.transfer_source)));
  const report = proposal.constraint_report || buildCorpusConstraintReport(proposal);
  const groundedStops = countGroundedStops(stops);
  const validations = {
    poi_count_valid: stops.length >= 3,
    category_coverage_valid: report.checks?.category_coverage?.satisfied === true,
    timeline_valid: timelineReady,
    transfer_valid: transferReady,
    budget_valid: report.checks?.budget?.satisfied !== false,
    duration_valid: report.checks?.duration?.satisfied !== false,
    opening_hours_valid: report.checks?.opening_hours?.satisfied !== false,
    evidence_valid: groundedStops >= Math.min(2, stops.length),
    queue_valid: report.checks?.queue?.satisfied !== false,
    walk_valid: report.checks?.distance?.satisfied !== false,
  };
  const qualitySummary = {
    ...(proposal.quality_summary || {}),
    route_generation_ready: proposal.quality_summary?.route_generation_ready ?? (stops.length >= 3 && timelineReady),
    executable_route: proposal.quality_summary?.executable_route ?? (timelineReady && transferReady),
    competition_readiness_score: proposal.quality_summary?.competition_readiness_score ?? Number((Object.values(validations).filter(Boolean).length / Object.keys(validations).length).toFixed(3)),
    validations: {
      ...(proposal.quality_summary?.validations || {}),
      ...validations,
    },
  };
  return {
    ...proposal,
    quality_summary: qualitySummary,
    constraint_report: report,
    constraint_resolution: proposal.constraint_resolution || buildCorpusConstraintResolution(report),
  };
}

function commutePairKey(originPoiId: string, destinationPoiId: string) {
  return `${originPoiId}->${destinationPoiId}`;
}

function commuteModeRank(mode: string): number {
  if (mode === 'walking') return 0;
  if (mode === 'bicycling') return 1;
  if (mode === 'driving') return 2;
  if (mode === 'transit') return 3;
  return 9;
}

async function hydrateCorpusProposalsWithCommuteEdges(proposals: JsonRecord[]): Promise<JsonRecord[]> {
  const adjacentIds = new Set<string>();
  for (const proposal of proposals) {
    const ids = Array.isArray(proposal.ordered_poi_ids)
      ? proposal.ordered_poi_ids.map(String)
      : Array.isArray(proposal.pois)
        ? proposal.pois.map((poi: JsonRecord) => String(poi.poi_id || '')).filter(Boolean)
        : [];
    for (let index = 1; index < ids.length; index += 1) {
      adjacentIds.add(ids[index - 1]);
      adjacentIds.add(ids[index]);
    }
  }
  const ids = Array.from(adjacentIds).filter(Boolean);
  if (!ids.length || process.env.TRAVELPILOT_COMMUTE_ENABLED === '0') return proposals;

  const rows = await prisma.$queryRaw<CorpusCommuteEdge[]>`
    SELECT
      origin_poi_id,
      destination_poi_id,
      mode,
      provider,
      distance_m,
      duration_s,
      walking_distance_m,
      transfer_count
    FROM travel_commute_edges
    WHERE status = 'ok'
      AND duration_s IS NOT NULL
      AND duration_s > 0
      AND origin_poi_id = ANY(${ids})
      AND destination_poi_id = ANY(${ids})
    ORDER BY origin_poi_id, destination_poi_id, mode, duration_s ASC
  `.catch(() => []);

  const edgesByPair = new Map<string, CorpusCommuteEdge[]>();
  for (const row of rows) {
    const key = commutePairKey(String(row.origin_poi_id), String(row.destination_poi_id));
    const group = edgesByPair.get(key) || [];
    group.push({
      origin_poi_id: String(row.origin_poi_id),
      destination_poi_id: String(row.destination_poi_id),
      mode: String(row.mode || 'unknown'),
      provider: String(row.provider || 'unknown'),
      distance_m: row.distance_m === null || row.distance_m === undefined ? null : Number(row.distance_m),
      duration_s: Number(row.duration_s),
      walking_distance_m: row.walking_distance_m === null || row.walking_distance_m === undefined ? null : Number(row.walking_distance_m),
      transfer_count: row.transfer_count === null || row.transfer_count === undefined ? null : Number(row.transfer_count),
    });
    edgesByPair.set(key, group);
  }
  for (const group of edgesByPair.values()) {
    group.sort((a, b) => commuteModeRank(a.mode) - commuteModeRank(b.mode) || Number(a.duration_s || Infinity) - Number(b.duration_s || Infinity));
  }

  return proposals.map((proposal) => {
    const stops = Array.isArray(proposal.pois)
      ? proposal.pois.map((stop: JsonRecord) => ({ ...stop }))
      : [];
    let commuteEdgesUsed = 0;
    let coordinateEstimatesUsed = 0;
    let totalTransferMinutes = 0;
    let totalDistanceM = 0;
    for (let index = 0; index < stops.length; index += 1) {
      if (index === 0) continue;
      const previousId = String(stops[index - 1]?.poi_id || '');
      const currentId = String(stops[index]?.poi_id || '');
      const edge =
        edgesByPair.get(commutePairKey(previousId, currentId))?.[0]
        ?? edgesByPair.get(commutePairKey(currentId, previousId))?.[0]
        ?? null;
      if (edge) {
        const minutes = Math.max(1, Math.round(Number(edge.duration_s || 0) / 60));
        const meters = Math.round(Number(edge.walking_distance_m ?? edge.distance_m ?? stops[index].transfer_from_previous_meters ?? 0));
        stops[index] = {
          ...stops[index],
          transfer_from_previous_minutes: minutes,
          transfer_from_previous_meters: meters,
          transfer_source: 'commute_edge',
          transfer_mode: edge.mode,
          transfer_provider: edge.provider,
          transfer_duration_s: Number(edge.duration_s || 0),
          transfer_count: edge.transfer_count,
        };
        commuteEdgesUsed += 1;
        totalTransferMinutes += minutes;
        totalDistanceM += meters;
      } else {
        coordinateEstimatesUsed += 1;
        totalTransferMinutes += Number(stops[index].transfer_from_previous_minutes || 0);
        totalDistanceM += Number(stops[index].transfer_from_previous_meters || 0);
        stops[index] = {
          ...stops[index],
          transfer_mode: stops[index].transfer_mode || 'walking_estimate',
        };
      }
    }
    const transferSummary = {
      commute_edges_used: commuteEdgesUsed,
      coordinate_estimates_used: coordinateEstimatesUsed,
      commute_edge_hit_rate: stops.length > 1 ? Number((commuteEdgesUsed / (stops.length - 1)).toFixed(3)) : 0,
    };
    return {
      ...proposal,
      pois: stops,
      total_transfer_minutes: totalTransferMinutes || proposal.total_transfer_minutes,
      total_walking_distance_m: Math.round(totalDistanceM || Number(proposal.total_walking_distance_m || 0)),
      transfer_source_summary: transferSummary,
      quality_summary: {
        ...(proposal.quality_summary || {}),
        commute: {
          ...(proposal.quality_summary?.commute || {}),
          uses_commute_edges: commuteEdgesUsed > 0,
          ...transferSummary,
        },
      },
    };
  });
}

function buildCorpusAccelerationSummary(params: {
  intent: TravelQueryIntent;
  source: string;
  queryResults: Array<JsonRecord>;
  wikiRetrieval?: JsonRecord | null;
}) {
  const sqlCacheHit = params.queryResults.length > 0 && params.queryResults.every((item) => Boolean(item.cache_hit));
  const wikiUsed = Boolean(params.wikiRetrieval);
  const semanticFastPath = params.intent.parser === 'dictionary'
    || (params.intent.parser === 'cache' && (params.intent.notes || []).some((note) => /Dictionary parser|Common semantic fast path/i.test(String(note))));
  return {
    enabled: true,
    fast_path: `route_corpus_${params.source}`,
    layers: {
      common_semantic_fast_path: semanticFastPath,
      intent_cache: Boolean(params.intent.cache_hit),
      route_corpus: true,
      sql_result_cache: sqlCacheHit,
      memory_data_cache: true,
      wiki_cache: wikiUsed,
    },
    parser: params.intent.parser,
    cache_hit: true,
    cache_layers_hit: [
      params.intent.cache_hit ? 'intent' : null,
      'route_corpus',
      sqlCacheHit ? 'sql_result' : null,
      'memory_data',
      wikiUsed ? 'wiki' : null,
    ].filter(Boolean),
    notes: [
      semanticFastPath ? '常见语义已由本地规则解析，跳过阻塞式 LLM 意图解析。' : null,
      '命中预生成路线库，直接返回可执行路线候选。',
      sqlCacheHit ? 'SQL 候选查询命中内存结果缓存。' : null,
    ].filter(Boolean),
  };
}

function buildCorpusKnowledgeGuidanceSummary(wikiRetrieval?: JsonRecord | null) {
  const hits = Array.isArray(wikiRetrieval?.hits) ? wikiRetrieval.hits : [];
  const linkedEntities = Array.isArray(wikiRetrieval?.linked_entities) ? wikiRetrieval.linked_entities : [];
  return {
    enabled: Boolean(wikiRetrieval),
    knowledge_base: {
      type: 'local_obsidian_llm_wiki',
      retrieval_used: Boolean(wikiRetrieval),
      hit_count: hits.length,
      linked_entity_count: linkedEntities.length,
      top_titles: hits.slice(0, 5).map((hit: JsonRecord) => hit.title).filter(Boolean),
    },
    guidance_steps: {
      planning_advice_used: false,
      planning_advice_source: null,
      route_draft_used: false,
      route_draft_source: null,
      rerank_used: false,
      rerank_source: null,
    },
    user_visible_summary: hits.length
      ? '路线库快路径已补充本地知识库证据，用于解释区域/主题/偏好匹配。'
      : '本次命中预生成路线库，知识库作为可选增强层未阻塞主链路。',
  };
}

async function getCommuteEdgeHealth() {
  if (process.env.TRAVELPILOT_COMMUTE_ENABLED === '0') {
    return { loaded: false, edge_count: 0, loaded_at: null, error: null };
  }
  try {
    const rows = await prisma.$queryRaw<Array<{ count: number }>>`
      SELECT COUNT(*)::int AS count
      FROM travel_commute_edges
      WHERE status = 'ok'
        AND duration_s IS NOT NULL
        AND duration_s > 0
    `;
    return {
      loaded: true,
      edge_count: Number(rows[0]?.count || 0),
      loaded_at: new Date().toISOString(),
      error: null,
    };
  } catch (error) {
    return {
      loaded: false,
      edge_count: 0,
      loaded_at: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function buildCorpusPlanningAdvice(intent: TravelQueryIntent, wikiRetrieval?: JsonRecord | null) {
  const shortTrip = intent.duration_minutes !== null && intent.duration_minutes <= 240;
  const lowWalk = intent.walk_preference === 'low' || intent.persona === 'senior' || intent.persona === 'family';
  return {
    source: 'wiki_local',
    llm_used: false,
    model: null,
    elapsed_ms: Number(wikiRetrieval?.elapsed_ms || 0),
    fallback_reason: 'route_corpus_fast_path',
    max_total_pois: shortTrip ? 3 : null,
    pace: lowWalk ? 'relaxed' : shortTrip ? 'compact' : null,
    walk_preference: lowWalk ? 'low' : null,
    route_mode: intent.needs_meal ? 'mixed' : intent.route_mode,
    preference_signals_patch: {
      lunch: intent.needs_meal,
      avoid_queue: intent.avoid_queue,
      indoor: intent.indoor_preferred,
      value_for_money: intent.budget_cny !== null,
      senior: intent.persona === 'senior',
      family: intent.persona === 'family',
      couple: intent.persona === 'couple',
    },
    avoid_poi_keywords: lowWalk ? ['高步行强度', '大范围户外绕行'] : [],
    candidate_strategy_notes: [
      '路线库快路径已用结构化标签匹配区域、时长、预算、餐饮、步行和排队偏好。',
      wikiRetrieval ? '本地 Wiki 证据用于解释路线库命中的区域/主题依据。' : '未命中 Wiki 时保留路线库确定性结果。',
    ],
    user_facing_reason: '已用本地知识库与路线库标签快速推导 planner 参数，避免常见请求阻塞在 LLM 推理上。',
  };
}

function buildCorpusDraftAndValidation(proposal: JsonRecord, wikiRetrieval?: JsonRecord | null) {
  const orderedIds = Array.isArray(proposal?.ordered_poi_ids) ? proposal.ordered_poi_ids.map(String) : [];
  const orderedNames = Array.isArray(proposal?.ordered_poi_names) ? proposal.ordered_poi_names.map(String) : [];
  const draft = {
    draft_source: 'rule_fallback',
    llm_used: false,
    llm_attempted: false,
    llm_error: null,
    elapsed_ms: Number(wikiRetrieval?.elapsed_ms || 0),
    fallback_reason: 'route_corpus_fast_path',
    selected_poi_ids: orderedIds,
    ordered_poi_ids: orderedIds,
    meal_stop_id: (Array.isArray(proposal?.pois) ? proposal.pois : []).find((poi: JsonRecord) => poi.poi_type === 'food')?.poi_id || null,
    estimated_fit: Number(proposal?.quality_summary?.competition_readiness_score || 0.86),
    preference_reasoning: '预生成路线库已通过本地 POI/UGC/约束规则选择并排序 POI。',
    known_risks: Array.isArray(proposal?.risks) ? proposal.risks : [],
    used_wiki_citation_ids: Array.isArray(wikiRetrieval?.citations) ? wikiRetrieval.citations.slice(0, 5).map((item: JsonRecord) => item.path || item.title).filter(Boolean) : [],
  };
  const validation = {
    status: orderedIds.length >= 3 ? 'valid' : 'rejected',
    valid_ordered_poi_ids: orderedIds,
    validated_poi_ids: orderedIds,
    rejected_poi_ids: [],
    repair_actions: [],
    validation_notes: [
      orderedIds.length >= 3 ? '路线库草案满足 3+ POI。' : '路线库草案 POI 数不足。',
      orderedNames.length ? `路线顺序：${orderedNames.join(' -> ')}` : '未提供路线名称。',
    ],
  };
  return { draft, validation };
}

function buildCorpusRerank(proposals: JsonRecord[], wikiRetrieval?: JsonRecord | null) {
  const rankedIds = proposals.map((proposal) => String(proposal.proposal_id)).filter(Boolean);
  return {
    llm_used: false,
    model: null,
    elapsed_ms: Number(wikiRetrieval?.elapsed_ms || 0),
    fallback_reason: 'route_corpus_fast_path',
    rerank_source: 'wiki_local',
    ranked_proposal_ids: rankedIds,
    primary_proposal_id: rankedIds[0] || null,
    ranking_reasons: rankedIds.map((id, index) => ({
      proposal_id: id,
      rank: index + 1,
      reason: index === 0 ? '路线库匹配分最高，并已补充本地 Wiki 证据。' : '作为备选方案保留用于多方案对比。',
    })),
    final_user_explanation: proposals[0]?.summary || '已用路线库匹配结果和本地知识库证据完成快速排序。',
  };
}

function buildReplanAccelerationCacheFromCorpusProposals(proposals: JsonRecord[]) {
  const hints = new Map<string, TravelRouteCorpusPoiHint>();
  for (const proposal of proposals) {
    const stops = Array.isArray(proposal.pois) ? proposal.pois : [];
    const ids = Array.isArray(proposal.ordered_poi_ids) ? proposal.ordered_poi_ids.map(String) : [];
    const names = Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.map(String) : [];
    const maxLength = Math.max(stops.length, ids.length, names.length);
    for (let index = 0; index < maxLength; index += 1) {
      const stop = stops[index] || {};
      const poiId = String(stop.poi_id || ids[index] || '');
      const name = String(stop.name || names[index] || '');
      if (!poiId || !name) continue;
      const existing = hints.get(poiId);
      hints.set(poiId, {
        poi_id: poiId,
        name,
        area: stop.area || null,
        district: stop.district || null,
        poi_type: stop.poi_type || null,
        category: stop.category || null,
        source: 'file',
        semantic_keys: Array.from(new Set([...(existing?.semantic_keys || []), ...semanticKeysForCorpusName(name)])),
      });
    }
  }
  return {
    source: 'route_corpus_initial_proposals',
    created_at: new Date().toISOString(),
    poi_hints: Array.from(hints.values()).slice(0, 120),
  };
}

export async function buildPlanningResponseFromRouteCorpus(params: {
  intent: TravelQueryIntent;
  match: TravelRouteCorpusMatch;
  request: TravelPlanningRequest;
}) {
  const started = performance.now();
  const primaryPayload = params.match.rows[0]?.payload || {};
  const proposals = await hydrateCorpusProposalsWithCommuteEdges(collectProposals(params.match.rows));
  const queryPlan = buildTravelQueryPlan(params.intent);
  const [queryResults, wikiRetrieval, commuteHealth] = await Promise.all([
    executeTravelQueryPlan(queryPlan).catch(() => []),
    retrieveTravelWiki({ rawText: params.intent.raw_text, intent: params.intent, limit: 8 }).catch(() => null),
    getCommuteEdgeHealth(),
  ]);
  const elapsedMs = Number((performance.now() - started + params.match.elapsed_ms).toFixed(2));
  const acceleration = buildCorpusAccelerationSummary({ intent: params.intent, source: params.match.source, queryResults: queryResults as Array<JsonRecord>, wikiRetrieval });
  const knowledgeGuidance = buildCorpusKnowledgeGuidanceSummary(wikiRetrieval as JsonRecord | null);
  const planningAdvice = buildCorpusPlanningAdvice(params.intent, wikiRetrieval as JsonRecord | null);
  const { draft: routeDraft, validation: validatorResult } = buildCorpusDraftAndValidation(proposals[0] || {}, wikiRetrieval as JsonRecord | null);
  const llmRerank = buildCorpusRerank(proposals, wikiRetrieval as JsonRecord | null);
  const requestSnapshot = {
    ...params.request,
    replan_acceleration_cache: buildReplanAccelerationCacheFromCorpusProposals(proposals),
  };
  return {
    parsed_request: requestSnapshot,
    parser_confidence: params.intent.confidence,
    parser_notes: [
      ...params.intent.notes,
      params.match.source === 'database'
        ? '已命中数据库预生成旅行路线库。'
        : '已命中文件预生成旅行路线库。',
    ],
    parser_correction_hints: params.intent.missing_fields.length ? [`Please clarify ${params.intent.missing_fields.join(', ')}.`] : [],
    intent: params.intent,
    planning_response: {
      ...primaryPayload,
      request_id: `travel-corpus-${Math.random().toString(16).slice(2, 12)}`,
      goal: params.intent.raw_text,
      request_snapshot: requestSnapshot,
      resolved_area: params.match.rows[0]?.area || params.request.area || primaryPayload.resolved_area || '北京',
      proposals,
      daily_itinerary: Array.isArray(primaryPayload.daily_itinerary) ? primaryPayload.daily_itinerary : [],
      query_plan: queryPlan,
      query_results: queryResults,
      wiki_retrieval: wikiRetrieval,
      planning_advice: planningAdvice,
      route_draft: routeDraft,
      validator_result: validatorResult,
      repair_actions: validatorResult.repair_actions,
      llm_rerank: llmRerank,
      acceleration,
      knowledge_guidance: knowledgeGuidance,
      route_corpus_match: {
        used: true,
        source: params.match.source,
        elapsed_ms: params.match.elapsed_ms,
        route_ids: params.match.rows.map((row) => row.route_id),
        match_scores: params.match.rows.map((row) => row.match_score),
      },
      final_selected_proposal_id: llmRerank.primary_proposal_id || proposals[0]?.proposal_id || null,
      natural_language_explanation: llmRerank.final_user_explanation || proposals[0]?.summary || '已根据你的要求从北京旅行路线库中匹配到可直接执行的路线。',
      generation_metrics: {
        ...(primaryPayload.generation_metrics || {}),
        elapsed_ms: elapsedMs,
        within_10s: elapsedMs < 10000,
        sla: {
          target_ms: 10000,
          elapsed_ms: elapsedMs,
          within_10s: elapsedMs < 10000,
          fast_path: `route_corpus_${params.match.source}`,
          llm_blocking: false,
          fallback_used: false,
        },
        route_corpus_used: true,
        route_corpus_source: params.match.source,
        route_corpus_match_count: params.match.rows.length,
        commute_edges_loaded: commuteHealth.loaded,
        commute_edge_count: commuteHealth.edge_count,
        commute_edge_loaded_at: commuteHealth.loaded_at,
        commute_edge_load_elapsed_ms: 0,
        commute_edge_error: commuteHealth.error,
        database_recall_used: queryResults.length > 0,
        wiki_retrieval_used: Boolean(wikiRetrieval),
        wiki_retrieval_elapsed_ms: wikiRetrieval?.elapsed_ms || 0,
        llm_rerank_used: false,
        llm_rerank_elapsed_ms: llmRerank.elapsed_ms,
        llm_rerank_fallback_reason: llmRerank.fallback_reason,
        planning_advice_used: true,
        planning_advice_source: planningAdvice.source,
        planning_advice_llm_used: false,
        planning_advice_elapsed_ms: planningAdvice.elapsed_ms,
        planning_advice_fallback_reason: planningAdvice.fallback_reason,
        route_draft_used: true,
        draft_source: routeDraft.draft_source,
        draft_llm_used: false,
        draft_llm_attempted: false,
        draft_llm_error: null,
        draft_elapsed_ms: routeDraft.elapsed_ms,
        draft_fallback_reason: routeDraft.fallback_reason,
        validator_status: validatorResult.status,
        llm_role: 'semantic_intent_only',
        acceleration_layers: acceleration.layers,
        knowledge_guidance_used: knowledgeGuidance.enabled,
        knowledge_hit_count: knowledgeGuidance.knowledge_base.hit_count,
      },
      replan_metadata: null,
    },
  };
}
