import fs from 'fs/promises';
import path from 'path';
import { prisma } from '@/lib/db/client';
import { buildTravelQueryPlan, executeTravelQueryPlan } from '@/lib/travel/sql-query';
import {
  intentToPlannerLikeRequest,
  parseTravelQueryIntentMiniMaxPreferred,
  parseTravelQueryIntent,
  type TravelQueryIntent,
} from '@/lib/travel/semantic-intent';
import { rerankTravelProposals } from '@/lib/travel/llm-rerank';
import { retrieveTravelWiki } from '@/lib/travel/wiki-retrieval';
import { applyTravelPlanningAdvice, getTravelPlanningAdvice, type TravelPlanningAdvice } from '@/lib/travel/llm-planning-advice';
import { generateTravelRouteDraft, type TravelRouteDraft, type TravelRouteDraftValidation } from '@/lib/travel/llm-route-draft';
import { buildPlanningResponseFromRouteCorpus, findPrecomputedTravelRoutes, findRouteCorpusPoiHints } from '@/lib/travel/route-corpus';

type JsonRecord = Record<string, any>;
type RouteMode = 'culture' | 'mixed';
type WalkPreference = 'low' | 'medium' | 'high';
type Pace = 'relaxed' | 'balanced' | 'compact';
type Strategy = 'balanced' | 'budget' | 'efficient';
type MealType = 'meal' | 'snack' | 'coffee' | 'dessert' | 'hotel_dining' | 'invalid' | 'non_food';
type TransferSource = 'commute_edge' | 'coordinate_estimate';
const MAX_TRIP_DAYS = Number(process.env.TRAVELPILOT_MAX_TRIP_DAYS || 7);

interface CommuteEdge {
  origin_poi_id: string;
  destination_poi_id: string;
  mode: string;
  provider: string;
  distance_m: number | null;
  duration_s: number;
  walking_distance_m: number | null;
  transfer_count: number | null;
}

interface CommuteEdgeIndex {
  edgesByPair: Map<string, CommuteEdge[]>;
  loaded: boolean;
  edge_count: number;
  loaded_at: string | null;
  error: string | null;
}

interface TransferEstimate {
  minutes: number;
  meters: number;
  source: TransferSource;
  mode: string | null;
  provider: string | null;
  duration_s: number | null;
  transfer_count: number | null;
}

export interface TravelPlanningRequest {
  goal?: string;
  route_mode?: RouteMode;
  area?: string | null;
  categories?: string[];
  start_time?: string;
  max_budget?: number | null;
  max_total_pois?: number;
  max_duration_min?: number | null;
  day_count?: number;
  pace?: Pace;
  walk_preference?: WalkPreference;
  persona_id?: string;
  must_include_names?: string[];
  exclude_names?: string[];
  must_include_poi_ids?: string[];
  exclude_poi_ids?: string[];
  route_order_poi_ids?: string[];
  preference_signals?: Record<string, boolean>;
  replan_acceleration_cache?: TravelReplanAccelerationCache | null;
}

interface TravelReplanPoiHint {
  poi_id: string;
  name: string;
  area?: string | null;
  district?: string | null;
  poi_type?: string | null;
  category?: string | null;
  source: string;
  semantic_keys: string[];
}

interface TravelReplanAccelerationCache {
  source: string;
  created_at: string;
  poi_hints: TravelReplanPoiHint[];
}

export interface TravelCandidateBuckets {
  request: TravelPlanningRequest;
  resolved_area: string;
  cultureCandidates: Poi[];
  mealCandidates: Poi[];
  snackCandidates: Poi[];
  indoorCandidates: Poi[];
}

export interface Poi extends JsonRecord {
  poi_id: string;
  name: string;
  district?: string;
  area?: string;
  category?: string;
  poi_type?: string;
  address?: string;
  lng: number;
  lat: number;
  rating?: number;
  avg_cost?: number;
  review_count?: number;
  open_time?: string;
  close_time?: string;
  suggested_duration_min?: number;
  planning_tags?: string[];
  evidence_tags?: string[];
  queue_risk?: string;
  value_for_money?: string;
  family_friendliness?: string;
  environment_quality?: string;
  meal_type?: MealType;
  is_lunch_suitable?: boolean;
  is_coffee_stop?: boolean;
  is_meal_stop?: boolean;
}

interface ReviewAggregate extends JsonRecord {
  poi_id: string;
  feature_key: string;
  feature_value: string;
  status: string;
  confidence?: number;
  evidence_refs?: string[];
  review_count_used?: number;
}

interface ReviewRecord extends JsonRecord {
  review_id: string;
  poi_id: string;
  review_text: string;
}

interface TravelData {
  culturePois: Poi[];
  mixedPois: Poi[];
  plannerEntities: Poi[];
  reviewAggregates: ReviewAggregate[];
  reviewRecordsById: Map<string, ReviewRecord>;
  poiById: Map<string, Poi>;
  reviewAggregatesByPoiId: Map<string, ReviewAggregate[]>;
}

const DEFAULT_DATA_ROOT = path.resolve(process.cwd(), 'travel-data', 'processed');
const DATA_ROOT = process.env.TRAVELPILOT_DATA_ROOT || DEFAULT_DATA_ROOT;

let dataCache: Promise<TravelData> | null = null;
let dataLoadedAt: string | null = null;
let dataLoadElapsedMs: number | null = null;
let commuteEdgeCache: Promise<CommuteEdgeIndex> | null = null;
let commuteEdgeLoadedAt: string | null = null;
let commuteEdgeLoadElapsedMs: number | null = null;

const LANDMARK_FIXTURE_POIS: Poi[] = [
  {
    poi_id: 'fixture_badaling_great_wall',
    name: '八达岭长城',
    district: '延庆区',
    area: '长城',
    category: '景区',
    poi_type: 'culture',
    address: '北京市延庆区G6京藏高速58号出口',
    lng: 116.016736,
    lat: 40.356213,
    rating: 4.8,
    avg_cost: 40,
    review_count: 12000,
    open_time: '07:30',
    close_time: '17:00',
    suggested_duration_min: 180,
    planning_tags: ['landmark', 'scene:outdoor', 'theme:great_wall', 'walk:high', 'classic_first_timer'],
    evidence_tags: ['北京经典地标', '适合半日或一日游', '与市区 POI 转场较远'],
    queue_risk: 'high',
    value_for_money: 'medium',
    family_friendliness: 'medium',
    environment_quality: 'high',
    meal_type: 'invalid',
    is_lunch_suitable: false,
    is_coffee_stop: false,
    is_meal_stop: false,
  },
];

async function readJsonArray<T>(fileName: string): Promise<T[]> {
  const content = await fs.readFile(path.join(DATA_ROOT, fileName), 'utf8');
  const parsed = JSON.parse(content);
  return Array.isArray(parsed) ? parsed as T[] : [];
}

function hasAny(text: string, words: string[]): boolean {
  return words.some((word) => text.includes(word));
}

function normalizeUserTravelText(text: string): string {
  return String(text || '').trim().replace(/^[/／\\]+\s*/, '').trim();
}

function deriveMealSemantics(raw: Partial<Poi>) {
  const name = String(raw.name || '');
  const lowerName = name.toLowerCase();
  const metadata = [
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.dining_style,
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
    ...(Array.isArray(raw.evidence_tags) ? raw.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');

  const coffeeWords = ['咖啡', 'coffee', 'cafe', '星巴克', '瑞幸'];
  const mealWords = ['餐', '饭', '面', '涮肉', '烧麦', '烤鸭', '饺子', '炸酱', '炒肝', '火锅', '串', '食'];
  const snackWords = ['小吃', '麦当劳', '肯德基', '包子', '驴打滚', '糕', '饼'];
  const dessertWords = ['甜品', '下午茶', '茶饮', '奶茶'];
  const hotelWords = ['酒店', '宾馆', '漫心府', '亚朵', '主题酒店'];
  const scenicWords = ['公园', '博物院', '博物馆', '步行街', '景区', '景点', '寺', '殿', '塔', '后海', '前海', '鼓楼', '艺术中心', '探索中心'];

  coffeeWords.push('咖啡', '星巴克', '瑞幸');
  mealWords.push('餐', '饭', '面', '涮肉', '烤鸭', '烧鸭', '饺子', '炸酱', '炒肝', '火锅');
  snackWords.push('小吃', '麦当劳', '肯德基', '包子', '驴打滚', '茶馆', '夜市', '档口', '小食铺');
  dessertWords.push('甜品', '下午茶', '茶饮', '奶茶');
  hotelWords.push('酒店', '宾馆', '客栈', '漫心府', '住宿', '亚朵');
  scenicWords.push('公园', '博物馆', '博物院', '美术馆', '艺术中心', '文化中心', '展览馆', '步行街', '景区', '景点', '寺', '殿', '塔', '后海', '前海', '鼓楼', '售票处', '讲解服务处');

  const hasDiningMetadata = /(^|\s)(dining|food|restaurant|meal|lunch|dinner|snack|cafe|coffee)(\s|$)/.test(metadata);
  const coffee = hasAny(lowerName, coffeeWords);
  const mealName = hasAny(name, mealWords);
  const snackName = hasAny(name, snackWords);
  const dessertName = hasAny(name, dessertWords);
  const hotelName = hasAny(name, hotelWords);
  const scenicName = hasAny(name, scenicWords) || name === '什刹海';

  if (scenicName && !mealName && !snackName && !coffee && !dessertName) {
    return { meal_type: 'invalid' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (!hasDiningMetadata && !mealName && !snackName && !coffee && !dessertName) {
    return { meal_type: 'non_food' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (hotelName && !mealName && !snackName) {
    return { meal_type: 'hotel_dining' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
  }
  if (coffee) {
    return { meal_type: 'coffee' as MealType, is_lunch_suitable: false, is_coffee_stop: true, is_meal_stop: true };
  }
  if (dessertName && !mealName && !snackName) {
    return { meal_type: 'dessert' as MealType, is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: true };
  }
  if (snackName) {
    return { meal_type: 'snack' as MealType, is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
  }
  return { meal_type: 'meal' as MealType, is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
}

function normalizePoi(raw: Poi): Poi {
  const name = String(raw.name || raw.display_name || raw.normalized_name || raw.poi_id);
  const meal = deriveMealSemantics({ ...raw, name });
  return {
    ...raw,
    poi_id: String(raw.poi_id),
    name,
    lng: Number(raw.lng),
    lat: Number(raw.lat),
    rating: Number(raw.rating || 0),
    avg_cost: Number(raw.avg_cost || 0),
    review_count: Number(raw.review_count || 0),
    suggested_duration_min: Number(raw.suggested_duration_min || raw.avg_visit_duration_min || 90),
    poi_type: meal.is_meal_stop || meal.is_coffee_stop ? 'food' : 'culture',
    ...meal,
  };
}

async function loadTravelData(): Promise<TravelData> {
  if (!dataCache) {
    const started = performance.now();
    dataCache = Promise.all([
      readJsonArray<Poi>('beijing_culture_pois.json'),
      readJsonArray<Poi>('beijing_mixed_category_pois.json'),
      readJsonArray<Poi>('beijing_planner_entities.json'),
      readJsonArray<ReviewAggregate>('beijing_poi_feature_aggregates.json'),
      readJsonArray<ReviewRecord>('beijing_review_records.json'),
    ]).then(([culturePois, mixedPois, plannerEntities, reviewAggregates, reviewRecords]) => {
      const landmarkFixtures = LANDMARK_FIXTURE_POIS.map(normalizePoi);
      const normalizedCulturePois = [...landmarkFixtures, ...culturePois.map(normalizePoi)];
      const normalizedMixedPois = [...landmarkFixtures, ...mixedPois.map(normalizePoi)];
      const normalizedPlannerEntities = [...landmarkFixtures, ...plannerEntities.map(normalizePoi)];
      const poiById = new Map<string, Poi>();
      for (const poi of [...normalizedMixedPois, ...normalizedCulturePois, ...normalizedPlannerEntities]) {
        poiById.set(poi.poi_id, poi);
      }
      const reviewAggregatesByPoiId = new Map<string, ReviewAggregate[]>();
      for (const item of reviewAggregates) {
        const group = reviewAggregatesByPoiId.get(item.poi_id) || [];
        group.push(item);
        reviewAggregatesByPoiId.set(item.poi_id, group);
      }
      const result = {
        culturePois: normalizedCulturePois,
        mixedPois: normalizedMixedPois,
        plannerEntities: normalizedPlannerEntities,
        reviewAggregates,
        reviewRecordsById: new Map(reviewRecords.map((item) => [String(item.review_id), item])),
        poiById,
        reviewAggregatesByPoiId,
      };
      dataLoadedAt = new Date().toISOString();
      dataLoadElapsedMs = Number((performance.now() - started).toFixed(2));
      return result;
    });
  }
  return dataCache;
}

function commutePairKey(originPoiId: string, destinationPoiId: string): string {
  return `${originPoiId}->${destinationPoiId}`;
}

function commuteModeRank(mode: string): number {
  if (mode === 'walking') return 0;
  if (mode === 'driving') return 1;
  if (mode === 'transit') return 2;
  return 9;
}

async function loadCommuteEdges(): Promise<CommuteEdgeIndex> {
  if (process.env.TRAVELPILOT_COMMUTE_ENABLED === '0') {
    return { edgesByPair: new Map(), loaded: false, edge_count: 0, loaded_at: null, error: null };
  }
  if (!commuteEdgeCache) {
    const started = performance.now();
    commuteEdgeCache = prisma.$queryRaw<CommuteEdge[]>`
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
      ORDER BY origin_poi_id, destination_poi_id, mode
    `.then((rows) => {
      const edgesByPair = new Map<string, CommuteEdge[]>();
      for (const row of rows) {
        const edge: CommuteEdge = {
          origin_poi_id: String(row.origin_poi_id),
          destination_poi_id: String(row.destination_poi_id),
          mode: String(row.mode || 'unknown'),
          provider: String(row.provider || 'unknown'),
          distance_m: row.distance_m === null || row.distance_m === undefined ? null : Number(row.distance_m),
          duration_s: Number(row.duration_s),
          walking_distance_m: row.walking_distance_m === null || row.walking_distance_m === undefined ? null : Number(row.walking_distance_m),
          transfer_count: row.transfer_count === null || row.transfer_count === undefined ? null : Number(row.transfer_count),
        };
        const key = commutePairKey(edge.origin_poi_id, edge.destination_poi_id);
        const group = edgesByPair.get(key) || [];
        group.push(edge);
        edgesByPair.set(key, group);
      }
      for (const group of edgesByPair.values()) {
        group.sort((a, b) => commuteModeRank(a.mode) - commuteModeRank(b.mode) || a.duration_s - b.duration_s);
      }
      commuteEdgeLoadedAt = new Date().toISOString();
      commuteEdgeLoadElapsedMs = Number((performance.now() - started).toFixed(2));
      return { edgesByPair, loaded: true, edge_count: rows.length, loaded_at: commuteEdgeLoadedAt, error: null };
    }).catch((error) => {
      commuteEdgeLoadedAt = null;
      commuteEdgeLoadElapsedMs = Number((performance.now() - started).toFixed(2));
      return {
        edgesByPair: new Map(),
        loaded: false,
        edge_count: 0,
        loaded_at: null,
        error: error instanceof Error ? error.message : String(error),
      };
    });
  }
  return commuteEdgeCache;
}

export async function warmTravelData() {
  const [data, commuteEdges] = await Promise.all([
    loadTravelData(),
    loadCommuteEdges(),
  ]);
  return {
    status: 'ok',
    data_loaded: true,
    data_loaded_at: dataLoadedAt,
    data_load_elapsed_ms: dataLoadElapsedMs,
    data_root: DATA_ROOT,
    poi_count: data.plannerEntities.length,
    cache: {
      poi_index_ready: data.poiById.size > 0,
      review_index_ready: data.reviewAggregatesByPoiId.size > 0,
      commute_edge_index_ready: commuteEdges.loaded && commuteEdges.edge_count > 0,
    },
    commute_edge_count: commuteEdges.edge_count,
    commute_edge_load_elapsed_ms: commuteEdgeLoadElapsedMs,
  };
}

function normalizePoiName(name?: string): string {
  return String(name || '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[-—·\s]/g, '')
    .trim()
    .toLowerCase();
}

function semanticKeysForPoiName(name?: string): string[] {
  const raw = String(name || '').trim();
  const normalized = normalizePoiName(raw);
  const keys = new Set<string>();
  if (raw) keys.add(raw);
  if (normalized) keys.add(normalized);
  const withoutSuffix = normalizePoiName(raw.replace(/[（(].*?[）)]/g, '').replace(/(公园|博物院|博物馆|景区|景点|店|门店|餐厅|饭店|咖啡|茶馆|小食铺|小吃)$/g, ''));
  if (withoutSuffix && withoutSuffix.length >= 2) keys.add(withoutSuffix);
  if (/长城|八达岭|慕田峪|居庸关|greatwall|badaling/i.test(normalized)) keys.add('长城');
  return Array.from(keys).filter(Boolean);
}

function buildReplanAccelerationCacheFromProposals(proposals: Array<Record<string, any>> = []): TravelReplanAccelerationCache {
  const hints = new Map<string, TravelReplanPoiHint>();
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
      const semanticKeys = Array.from(new Set([...(existing?.semantic_keys || []), ...semanticKeysForPoiName(name)]));
      hints.set(poiId, {
        poi_id: poiId,
        name,
        area: stop.area || null,
        district: stop.district || null,
        poi_type: stop.poi_type || null,
        category: stop.category || null,
        source: existing?.source || 'initial_route_proposals',
        semantic_keys: semanticKeys,
      });
    }
  }
  return {
    source: 'initial_route_proposals',
    created_at: new Date().toISOString(),
    poi_hints: Array.from(hints.values()).slice(0, 80),
  };
}

function mergeReplanAccelerationCaches(
  current?: TravelReplanAccelerationCache | null,
  next?: TravelReplanAccelerationCache | null,
): TravelReplanAccelerationCache | null {
  const hints = new Map<string, TravelReplanPoiHint>();
  for (const cache of [current, next]) {
    for (const hint of cache?.poi_hints || []) {
      if (!hint.poi_id || !hint.name) continue;
      const existing = hints.get(hint.poi_id);
      hints.set(hint.poi_id, {
        ...hint,
        semantic_keys: Array.from(new Set([...(existing?.semantic_keys || []), ...(hint.semantic_keys || []), ...semanticKeysForPoiName(hint.name)])),
        source: existing?.source ? `${existing.source}+${hint.source}` : hint.source,
      });
    }
  }
  if (!hints.size) return current || next || null;
  return {
    source: 'merged_route_replan_cache',
    created_at: new Date().toISOString(),
    poi_hints: Array.from(hints.values()).slice(0, 120),
  };
}

function applyReplanAccelerationCache<T extends { proposals?: Array<Record<string, any>>; request_snapshot?: Record<string, any> }>(response: T): T {
  const cache = buildReplanAccelerationCacheFromProposals(response.proposals || []);
  const existing = response.request_snapshot?.replan_acceleration_cache || null;
  return {
    ...response,
    request_snapshot: {
      ...(response.request_snapshot || {}),
      replan_acceleration_cache: mergeReplanAccelerationCaches(existing, cache),
    },
  } as T;
}

function resolveIdsFromReplanAccelerationCache(request: TravelPlanningRequest): string[] {
  const names = (request.must_include_names || []).filter((name) => !isGenericIncludeName(String(name)));
  if (!names.length) return [];
  const ids = new Set<string>();
  const hints = request.replan_acceleration_cache?.poi_hints || [];
  for (const includeName of names) {
    const include = normalizePoiName(includeName);
    if (!include) continue;
    const best = hints
      .filter((hint) => {
        const hintKeys = [hint.name, ...(hint.semantic_keys || [])];
        return hintKeys.some((key) => {
          const normalizedKey = normalizePoiName(key);
          return Boolean(normalizedKey && (normalizedKey.includes(include) || include.includes(normalizedKey)));
        });
      })
      .sort((a, b) => {
        const aName = normalizePoiName(a.name);
        const bName = normalizePoiName(b.name);
        const aExact = aName === include ? 1 : 0;
        const bExact = bName === include ? 1 : 0;
        const aParent = aName.startsWith(include) && !aName.includes('-') ? 1 : 0;
        const bParent = bName.startsWith(include) && !bName.includes('-') ? 1 : 0;
        return bExact - aExact
          || bParent - aParent
          || aName.length - bName.length;
      })[0];
    if (best?.poi_id) ids.add(best.poi_id);
  }
  return Array.from(ids);
}

function filterBestCorpusHintsForNames(hints: Array<{
  poi_id: string;
  name: string;
  area?: string | null;
  district?: string | null;
  poi_type?: string | null;
  category?: string | null;
  source?: string;
  semantic_keys?: string[];
}>, names: string[]) {
  const selected = new Map<string, typeof hints[number]>();
  for (const includeName of names.filter((name) => !isGenericIncludeName(String(name)))) {
    const include = normalizePoiName(includeName);
    if (!include) continue;
    const best = hints
      .filter((hint) => {
        const hintKeys = [hint.name, ...(hint.semantic_keys || [])];
        return hintKeys.some((key) => {
          const normalizedKey = normalizePoiName(key);
          return Boolean(normalizedKey && (normalizedKey.includes(include) || include.includes(normalizedKey)));
        });
      })
      .sort((a, b) => {
        const aName = normalizePoiName(a.name);
        const bName = normalizePoiName(b.name);
        const aExact = aName === include ? 1 : 0;
        const bExact = bName === include ? 1 : 0;
        const aParent = aName.startsWith(include) && !aName.includes('-') ? 1 : 0;
        const bParent = bName.startsWith(include) && !bName.includes('-') ? 1 : 0;
        return bExact - aExact
          || bParent - aParent
          || aName.length - bName.length;
      })[0];
    if (best?.poi_id) selected.set(best.poi_id, best);
  }
  return Array.from(selected.values());
}

function replanCacheFromCorpusHints(hints: Array<{
  poi_id: string;
  name: string;
  area?: string | null;
  district?: string | null;
  poi_type?: string | null;
  category?: string | null;
  source?: string;
  semantic_keys?: string[];
}>): TravelReplanAccelerationCache | null {
  if (!hints.length) return null;
  return {
    source: 'route_corpus_poi_hint',
    created_at: new Date().toISOString(),
    poi_hints: hints.map((hint) => ({
      poi_id: String(hint.poi_id),
      name: String(hint.name),
      area: hint.area ?? null,
      district: hint.district ?? null,
      poi_type: hint.poi_type ?? null,
      category: hint.category ?? null,
      source: String(hint.source || 'route_corpus_poi_hint'),
      semantic_keys: Array.from(new Set([...(hint.semantic_keys || []), ...semanticKeysForPoiName(hint.name)])),
    })),
  };
}

function landmarkPoiIdsForName(name: string): string[] {
  const normalized = normalizePoiName(name);
  if (/(长城|八达岭|慕田峪|居庸关|greatwall|badaling)/i.test(normalized)) {
    return ['fixture_badaling_great_wall'];
  }
  return [];
}

function requestHasLandmarkInclude(request: TravelPlanningRequest): boolean {
  return (request.must_include_names || []).some((name) => landmarkPoiIdsForName(name).length > 0)
    || (request.must_include_poi_ids || []).some((id) => id === 'fixture_badaling_great_wall');
}

function requestHasNamedInclude(request: TravelPlanningRequest): boolean {
  return (request.must_include_names || []).length > 0 || (request.must_include_poi_ids || []).length > 0;
}

function normalizeMustIncludeIds(payload: Partial<TravelPlanningRequest>): string[] {
  const ids = Array.isArray(payload.must_include_poi_ids) ? payload.must_include_poi_ids.map(String) : [];
  const names = Array.isArray(payload.must_include_names) ? payload.must_include_names : [];
  for (const name of names) ids.push(...landmarkPoiIdsForName(String(name)));
  return Array.from(new Set(ids));
}

function extractExcludedNames(text: string): string[] {
  const names: string[] = [];
  const normalizedText = normalizeUserTravelText(text);
  const pattern = /(?:不去|别去|不要去?|去掉|排除|取消|避开|别安排|不要安排)([^，,。；;]+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(normalizedText)) !== null) {
    const raw = String(match[1] || '')
      .replace(/^(这个|那个|这里|那里|它|他|她)/, '')
      .replace(/^(地方|地点|景点|餐厅|饭店|点位|这个地方|那个地方|这个景点|那个景点)/, '')
      .replace(/^(了|吧|呀|啊|呢)/, '')
      .trim();
    if (!raw) continue;
    if (/^(吃饭|午餐|午饭|晚餐|餐饮|饭|餐)$/.test(raw)) continue;
    for (const part of raw.split(/[、和]/).map((item) => item.trim()).filter(Boolean)) {
      names.push(part);
    }
  }
  return Array.from(new Set(names));
}

function isGenericIncludeName(name: string): boolean {
  return /^(一个|一个点|一个景点|景点|景区|地点|地方|点|室内点|文化点|好玩的|午餐地点|吃饭地点|餐厅|饭店|吃饭|午餐|午饭|顺路|原来的点都保留|其他地方不变)$/.test(name);
}

function cleanupIncludedName(rawName: string): string {
  return String(rawName || '')
    .replace(/^(把|去|到|一个|一处|一家|顺路的|附近的|新的|这个|那个)/, '')
    .replace(/^(景点|景区|地点|地方|点位|地方吧|景点吧)/, '')
    .replace(/(也)?(?:放进去|排进去|安排进去|加进去|加上|安排一下|安排|进去|也想去|想去)$/g, '')
    .replace(/(吧|呀|啊|呢|了|原来的点都保留|其他地方不变)$/g, '')
    .trim();
}

function splitIncludedNameParts(rawName: string): string[] {
  const coarseParts = rawName.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
  const parts: string[] = [];
  for (const coarse of coarseParts) {
    const connectiveParts = coarse.split(/(?:以及|跟|和)/).map((item) => item.trim()).filter(Boolean);
    const shouldSplitConnective = connectiveParts.length > 1 && connectiveParts.every((item) => item.length >= 2);
    parts.push(...(shouldSplitConnective ? connectiveParts : [coarse]));
  }
  return parts;
}

function extractIncludedNames(text: string): string[] {
  const names: string[] = [];
  const normalizedText = normalizeUserTravelText(text);
  const pattern = /(?:还想去|也想去|有点想去|想去|必须去|一定去|加上|添加|增加|安排|顺便去|能不能(?:帮我)?(?:把)?(?:安排|加上|放进去|排进去)?)([^，,。；;]+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(normalizedText)) !== null) {
    const raw = cleanupIncludedName(String(match[1] || ''));
    if (!raw) continue;
    for (const part of splitIncludedNameParts(raw).map(cleanupIncludedName).filter(Boolean)) {
      if (!isGenericIncludeName(part)) names.push(part);
    }
  }
  return Array.from(new Set(names));
}

function matchesExcludedName(item: Pick<Poi, 'name'>, excludedNames: string[]): boolean {
  const name = normalizePoiName(item.name);
  return excludedNames.some((excluded) => {
    const normalizedExcluded = normalizePoiName(excluded);
    return Boolean(normalizedExcluded && (name.includes(normalizedExcluded) || normalizedExcluded.includes(name)));
  });
}

function matchesIncludeName(item: Pick<Poi, 'name'>, includeName: string): boolean {
  const name = normalizePoiName(item.name);
  const include = normalizePoiName(includeName);
  return Boolean(include && (name.includes(include) || include.includes(name)));
}

function resolveMustIncludePoiIds(data: TravelData, request: TravelPlanningRequest): string[] {
  const ids = new Set(request.must_include_poi_ids || []);
  const pool = [...data.plannerEntities, ...data.mixedPois, ...data.culturePois];
  for (const name of request.must_include_names || []) {
    for (const landmarkId of landmarkPoiIdsForName(name)) ids.add(landmarkId);
    if (isGenericIncludeName(String(name))) continue;
    const exactOrContains = pool
      .filter((item) => matchesIncludeName(item, String(name)))
      .sort((a, b) => {
        const aExact = normalizePoiName(a.name) === normalizePoiName(name) ? 1 : 0;
        const bExact = normalizePoiName(b.name) === normalizePoiName(name) ? 1 : 0;
        return bExact - aExact
          || Number(b.rating || 0) - Number(a.rating || 0)
          || Number(b.review_count || 0) - Number(a.review_count || 0);
      })[0];
    if (exactOrContains) ids.add(exactOrContains.poi_id);
  }
  return Array.from(ids);
}

function unresolvedMustIncludeNames(data: TravelData, request: TravelPlanningRequest): string[] {
  const ids = new Set(resolveMustIncludePoiIds(data, request));
  const pool = [...data.plannerEntities, ...data.mixedPois, ...data.culturePois];
  return (request.must_include_names || [])
    .filter((name) => !isGenericIncludeName(String(name)))
    .filter((name) => landmarkPoiIdsForName(String(name)).length === 0)
    .filter((name) => !pool.some((item) => ids.has(item.poi_id) && matchesIncludeName(item, String(name))));
}

function buildFallbackPoiForIncludeName(name: string, request: TravelPlanningRequest, index: number): Poi {
  const normalizedName = String(name || '').trim() || '用户指定地点';
  const anchorByArea: Record<string, { lng: number; lat: number; district: string }> = {
    前门: { lng: 116.3976, lat: 39.9006, district: '东城区' },
    故宫: { lng: 116.3972, lat: 39.9163, district: '东城区' },
    什刹海: { lng: 116.3844, lat: 39.9417, district: '西城区' },
    天坛: { lng: 116.4108, lat: 39.8819, district: '东城区' },
    颐和园: { lng: 116.2755, lat: 39.9999, district: '海淀区' },
    王府井: { lng: 116.4114, lat: 39.9149, district: '东城区' },
  };
  const anchor = (request.area && anchorByArea[request.area]) || { lng: 116.4074, lat: 39.9042, district: '北京市' };
  const isFoodName = /餐|饭|吃|咖啡|小吃|烤鸭|涮肉|面|甜品|茶/.test(normalizedName);
  return normalizePoi({
    poi_id: `user_requested_${normalizePoiName(normalizedName) || index}`,
    name: normalizedName,
    district: anchor.district,
    area: request.area || '用户指定地点',
    category: isFoodName ? '餐饮' : '用户指定地点',
    poi_type: isFoodName ? 'food' : 'culture',
    address: '用户指定地点，本地 POI 库未命中，建议出发前确认精确地址',
    lng: anchor.lng + index * 0.002,
    lat: anchor.lat + index * 0.002,
    rating: 4.2,
    avg_cost: isFoodName ? 80 : 0,
    review_count: 0,
    suggested_duration_min: isFoodName ? 60 : 90,
    planning_tags: ['user_requested', 'needs_address_confirmation'],
    evidence_tags: ['用户明确指定，但本地 POI 库未命中'],
    queue_risk: 'unknown',
    value_for_money: 'unknown',
    family_friendliness: 'unknown',
    environment_quality: 'unknown',
  } as Poi);
}

function uniqueByName(items: Poi[]): Poi[] {
  const seenIds = new Set<string>();
  const seenNames = new Set<string>();
  return items.filter((item) => {
    const name = normalizePoiName(item.name);
    if (seenIds.has(item.poi_id) || seenNames.has(name)) return false;
    seenIds.add(item.poi_id);
    if (name) seenNames.add(name);
    return true;
  });
}

function attractionGroupKey(item: Pick<Poi, 'name' | 'area' | 'district'>): string {
  const normalizedName = normalizePoiName(item.name);
  if (normalizedName.includes('\u6545\u5bab\u535a\u7269\u9662')) return '\u6545\u5bab\u535a\u7269\u9662';
  if (normalizedName.includes('\u5929\u5b89\u95e8\u5e7f\u573a')) return '\u5929\u5b89\u95e8\u5e7f\u573a';
  if (normalizedName.includes('\u4e2d\u56fd\u56fd\u5bb6\u535a\u7269\u9986')) return '\u4e2d\u56fd\u56fd\u5bb6\u535a\u7269\u9986';
  if (normalizedName.includes('\u5317\u6d77\u516c\u56ed')) return '\u5317\u6d77\u516c\u56ed';
  if (normalizedName.includes('\u666f\u5c71\u516c\u56ed')) return '\u666f\u5c71\u516c\u56ed';
  if (normalizedName.includes('故宫博物院')) return '故宫博物院';
  if (normalizedName.includes('天安门广场')) return '天安门广场';
  if (normalizedName.includes('中国国家博物馆')) return '中国国家博物馆';
  if (normalizedName.includes('北海公园')) return '北海公园';
  if (normalizedName.includes('景山公园')) return '景山公园';
  const baseName = String(item.name || '').split(/[-—–]/)[0]?.trim();
  return normalizePoiName(baseName || item.name || item.area || item.district || '');
}

function uniqueByAttractionGroup(items: Poi[]): Poi[] {
  const seenIds = new Set<string>();
  const seenGroups = new Set<string>();
  return items.filter((item) => {
    const group = attractionGroupKey(item);
    if (seenIds.has(item.poi_id) || (group && seenGroups.has(group))) return false;
    seenIds.add(item.poi_id);
    if (group) seenGroups.add(group);
    return true;
  });
}

function isFoodPoi(item: Poi): boolean {
  const mealType = String(item.meal_type || '').toLowerCase();
  if (mealType === 'invalid' || mealType === 'non_food' || mealType === 'hotel_dining') return false;
  const text = poiText(item);
  const name = String(item.name || '');
  if (/\u9152\u5e97|\u5bbe\u9986|\u5ba2\u6808|\u6f2b\u5fc3\u5e9c|\u4f4f\u5bbf/.test(name)) return false;
  if (/\u552e\u7968\u5904|\u8bb2\u89e3|\u670d\u52a1\u4e2d\u5fc3|\u5e02\u6c11\u6587\u5316\u4e2d\u5fc3/.test(name)) return false;
  return ['meal', 'snack', 'coffee', 'dessert'].includes(mealType)
    || /(^|\s)(food|dining|restaurant|meal|snack|coffee|cafe)(\s|$)/.test(text)
    || Boolean(item.is_lunch_suitable || item.is_coffee_stop);
}

function isLunchPoi(item: Poi): boolean {
  return Boolean(item.is_lunch_suitable);
}

function isCoffeePoi(item: Poi): boolean {
  return Boolean(item.is_coffee_stop);
}

function isSnackOrTeaPoi(item: Poi): boolean {
  return item.meal_type === 'snack'
    || item.meal_type === 'coffee'
    || item.meal_type === 'dessert'
    || /茶馆|夜市|档口|小食铺|小吃/.test(String(item.name || ''));
}

function isRecommendablePoi(item: Poi): boolean {
  if (isFoodPoi(item)) return true;
  const name = String(item.name || '');
  const text = poiText(item);
  const hasChinese = /[\u4e00-\u9fff]/.test(name);
  const latinCount = (name.match(/[A-Za-z]/g) || []).length;
  const weakEvidence = Number(item.review_count || 0) <= 0 && !/museum|art_gallery|attraction|scene:indoor|theme:museum|theme:art/.test(text);
  if (!hasChinese) return false;
  if (latinCount >= 4 && weakEvidence) return false;
  if (/\u9152\u5e97|\u5bbe\u9986|\u6f2b\u5fc3\u5e9c|\u5ba2\u6808|\u4f4f\u5bbf/.test(name)) return false;
  if (/\u5e02\u6c11\u6587\u5316\u4e2d\u5fc3|\u793e\u533a|\u5c45\u6c11|\u8857\u9053\u529e/.test(name)) return false;
  if (/\u5efa\u8bbe\u4e2d|\u89c2\u4f17\u670d\u52a1\u4e2d\u5fc3|\u8bb2\u89e3\u670d\u52a1\u5904/.test(name)) return false;
  return true;
}

function isIndoorCulturePoi(item: Poi): boolean {
  if (isFoodPoi(item)) return false;
  const text = poiText(item);
  return /museum|art_gallery|exhibition|theme:museum|theme:art|\u535a\u7269\u9986|\u7f8e\u672f\u9986|\u827a\u672f\u4e2d\u5fc3|\u5c55\u89c8\u9986|\u79d1\u6559\u6587\u5316/.test(text);
}

function mealQualityScore(item: Poi): number {
  let score = 0;
  if (item.meal_type === 'meal') score += 12;
  if (item.meal_type === 'snack') score += 10;
  if (item.meal_type === 'coffee') score -= 6;
  if (item.meal_type === 'dessert') score -= 8;
  if (item.meal_type === 'hotel_dining' || item.meal_type === 'invalid') score -= 20;
  if (Number(item.avg_cost || 0) > 0) score += 3;
  return score;
}

function adjustmentWantsFreshPlan(text: string): boolean {
  return /全新|重新来|不保留|重新安排所有|全部重排/.test(text);
}

function adjustmentWantsFoodChange(text: string): boolean {
  return /(午餐|午饭|中午吃|吃饭|餐饮|餐厅|饭店|小吃|咖啡|正餐|美食|把午餐|换午餐|午餐换|换成.*(?:午餐|午饭|小吃|咖啡|餐厅|饭店|正餐|美食)|改成.*(?:午餐|午饭|小吃|咖啡|餐厅|饭店|正餐|美食))/.test(text);
}

function adjustmentWantsSnack(text: string): boolean {
  return /小吃|下午茶|甜品|茶饮|奶茶|咖啡|预算\s*\d+\s*以内的小吃|换成.*(?:小吃|下午茶|甜品|茶饮|奶茶|咖啡)/.test(text);
}

function parseTargetedReplacementIndex(text: string, total: number): number | null {
  if (!total || !/(换成|换一个|替换|改成|更换)/.test(text)) return null;
  if (/最后一个|最后1个|末尾|最后一站|最后1站/.test(text)) return total - 1;
  const chineseNumbers: Record<string, number> = {
    一: 0,
    二: 1,
    两: 1,
    三: 2,
    四: 3,
    五: 4,
    六: 5,
  };
  const chineseMatch = text.match(/第\s*([一二两三四五六])\s*(?:个|站|处)?(?:点|景点|地点|餐厅|饭店|POI)?/);
  if (chineseMatch?.[1] && chineseMatch[1] in chineseNumbers) {
    const index = chineseNumbers[chineseMatch[1]];
    return index >= 0 && index < total ? index : null;
  }
  const digitMatch = text.match(/第\s*(\d+)\s*(?:个|站|处)?(?:点|景点|地点|餐厅|饭店|POI)?/i);
  if (digitMatch?.[1]) {
    const index = Number(digitMatch[1]) - 1;
    return index >= 0 && index < total ? index : null;
  }
  return null;
}

function shouldPreservePoiOnReplan(params: {
  poi: Poi;
  adjustmentText: string;
  excludedNames: string[];
  excludedIds: Set<string>;
}): boolean {
  if (params.excludedIds.has(params.poi.poi_id)) return false;
  if (matchesExcludedName(params.poi, params.excludedNames)) return false;
  if (adjustmentWantsFreshPlan(params.adjustmentText)) return false;
  if (adjustmentWantsFoodChange(params.adjustmentText) && isFoodPoi(params.poi)) return false;
  return true;
}

function stableWantsFreshPlan(text: string): boolean {
  return /\u5168\u65b0|\u91cd\u65b0\u6765|\u4e0d\u4fdd\u7559|\u91cd\u65b0\u5b89\u6392\u6240\u6709|\u5168\u90e8\u91cd\u6392/.test(text);
}

function stableWantsFoodChange(text: string): boolean {
  return /(\u5348\u9910|\u5348\u996d|\u4e2d\u5348\u5403|\u5403\u996d|\u9910\u996e|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u6b63\u9910|\u7f8e\u98df|\u6362\u6210.*(?:\u5348\u9910|\u5348\u996d|\u5c0f\u5403|\u5496\u5561|\u9910\u5385|\u996d\u5e97|\u6b63\u9910|\u7f8e\u98df)|\u6539\u6210.*(?:\u5348\u9910|\u5348\u996d|\u5c0f\u5403|\u5496\u5561|\u9910\u5385|\u996d\u5e97|\u6b63\u9910|\u7f8e\u98df))/.test(text);
}

function stableWantsSnack(text: string): boolean {
  return /\u5c0f\u5403|\u4e0b\u5348\u8336|\u751c\u54c1|\u8336\u996e|\u5976\u8336|\u5496\u5561|\u9884\u7b97\s*\d+\s*\u4ee5\u5185\u7684\u5c0f\u5403|\u6362\u6210.*(?:\u5c0f\u5403|\u4e0b\u5348\u8336|\u751c\u54c1|\u8336\u996e|\u5976\u8336|\u5496\u5561)/.test(text);
}

function stableWantsFormalMeal(text: string): boolean {
  return /\u6b63\u9910|\u9910\u5385|\u996d\u5e97|\u9002\u5408\u5348\u9910|\u4e0d\u8981\u5496\u5561|\u522b\u8981\u5496\u5561/.test(text);
}

function stablePreservesFood(text: string): boolean {
  return /\u5348\u9910\u4e0d\u53d8|\u9910\u996e\u4e0d\u53d8|\u5403\u996d\u4e0d\u53d8|\u996d\u5e97\u4e0d\u53d8|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u5348\u9910|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u9910\u996e|\u4fdd\u7559(?:\u5f53\u524d|\u539f\u6765|\u539f\u6709)?\u996d\u5e97/.test(text);
}

function stablePreservesCulture(text: string): boolean {
  return /\u666f\u70b9\u4e0d\u53d8|\u6587\u5316\u70b9\u4e0d\u53d8|\u5176\u4ed6\u666f\u70b9\u4e0d\u53d8|\u4fdd\u7559\u666f\u70b9|\u4fdd\u7559\u6587\u5316\u70b9/.test(text);
}

function stablePreservesOthers(text: string): boolean {
  return /\u5176\u4ed6\u5730\u65b9\u4e0d\u53d8|\u5176\u4ed6\u5730\u70b9\u4e0d\u53d8|\u5176\u4ed6\u4e0d\u53d8|\u4e0d\u53d8|\u4fdd\u7559\u5176\u4ed6/.test(text);
}

function stableWantsIndoor(text: string): boolean {
  return /\u5ba4\u5185|\u4e0d\u6652|\u4e0b\u96e8|\u5c55\u9986|\u535a\u7269\u9986|\u7f8e\u672f\u9986|\u827a\u672f\u4e2d\u5fc3/.test(text);
}

function stableWantsAddStop(text: string): boolean {
  return /\u52a0\u4e00\u4e2a|\u6dfb\u52a0|\u52a0\u4e0a|\u987a\u8def\u52a0|\u518d\u5b89\u6392\u4e00\u4e2a|\u591a\u4e00\u4e2a|\u589e\u52a0\u4e00\u4e2a|\u518d\u52a0|\u8fd8\u60f3|\u4e5f\u60f3|\u60f3\u53bb|\u6709\u70b9\u60f3\u53bb|\u987a\u4fbf|\u653e\u8fdb\u53bb|\u6392\u8fdb\u53bb/.test(text);
}

function stableWantsGenericAttraction(text: string): boolean {
  return /\u666f\u70b9|\u666f\u533a|\u5730\u70b9|\u5730\u65b9|\u6587\u5316\u70b9|\u597d\u73a9\u7684|\u987a\u8def/.test(text);
}

function stableTargetedReplacementIndex(text: string, total: number): number | null {
  if (!total || !/(\u6362\u6210|\u6362\u4e00\u4e2a|\u66ff\u6362|\u6539\u6210|\u66f4\u6362)/.test(text)) return null;
  if (/\u6700\u540e\u4e00\u4e2a|\u6700\u540e1\u4e2a|\u672b\u5c3e|\u6700\u540e\u4e00\u7ad9|\u6700\u540e1\u7ad9/.test(text)) return total - 1;
  const chineseNumbers: Record<string, number> = {
    '\u4e00': 0,
    '\u4e8c': 1,
    '\u4e24': 1,
    '\u4e09': 2,
    '\u56db': 3,
    '\u4e94': 4,
    '\u516d': 5,
  };
  const chineseMatch = text.match(/\u7b2c\s*([\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d])\s*(?:\u4e2a|\u7ad9|\u5904)?(?:\u70b9|\u666f\u70b9|\u5730\u70b9|\u9910\u5385|\u996d\u5e97|POI)?/);
  if (chineseMatch?.[1] && chineseMatch[1] in chineseNumbers) {
    const index = chineseNumbers[chineseMatch[1]];
    return index >= 0 && index < total ? index : null;
  }
  const digitMatch = text.match(/\u7b2c\s*(\d+)\s*(?:\u4e2a|\u7ad9|\u5904)?(?:\u70b9|\u666f\u70b9|\u5730\u70b9|\u9910\u5385|\u996d\u5e97|POI)?/i);
  if (digitMatch?.[1]) {
    const index = Number(digitMatch[1]) - 1;
    return index >= 0 && index < total ? index : null;
  }
  return null;
}

function normalizeRequest(payload: Partial<TravelPlanningRequest>): TravelPlanningRequest {
  const replanCache = payload.replan_acceleration_cache && Array.isArray(payload.replan_acceleration_cache.poi_hints)
    ? {
        source: String(payload.replan_acceleration_cache.source || 'request_snapshot'),
        created_at: String(payload.replan_acceleration_cache.created_at || new Date().toISOString()),
        poi_hints: payload.replan_acceleration_cache.poi_hints
          .map((hint) => ({
            poi_id: String(hint.poi_id || ''),
            name: String(hint.name || ''),
            area: hint.area ?? null,
            district: hint.district ?? null,
            poi_type: hint.poi_type ?? null,
            category: hint.category ?? null,
            source: String(hint.source || 'request_snapshot'),
            semantic_keys: Array.isArray(hint.semantic_keys) ? hint.semantic_keys.map(String).filter(Boolean) : semanticKeysForPoiName(hint.name),
          }))
          .filter((hint) => hint.poi_id && hint.name)
          .slice(0, 120),
      }
    : null;
  return {
    goal: String(payload.goal || ''),
    route_mode: payload.route_mode === 'culture' ? 'culture' : 'mixed',
    area: payload.area || null,
    categories: Array.isArray(payload.categories) ? payload.categories : [],
    start_time: payload.start_time || '09:00',
    max_budget: payload.max_budget === undefined ? null : payload.max_budget,
    max_total_pois: Math.max(3, Math.min(8, Number(payload.max_total_pois || 4))),
    max_duration_min: payload.max_duration_min === undefined ? null : payload.max_duration_min,
    day_count: Math.max(1, Math.min(MAX_TRIP_DAYS, Number(payload.day_count || 1))),
    pace: payload.pace || 'balanced',
    walk_preference: payload.walk_preference || 'medium',
    persona_id: payload.persona_id || 'classic_first_timer',
    must_include_names: Array.isArray(payload.must_include_names) ? payload.must_include_names : [],
    exclude_names: Array.isArray(payload.exclude_names) ? payload.exclude_names : [],
    must_include_poi_ids: normalizeMustIncludeIds(payload),
    exclude_poi_ids: Array.isArray(payload.exclude_poi_ids) ? payload.exclude_poi_ids : [],
    route_order_poi_ids: Array.isArray(payload.route_order_poi_ids) ? payload.route_order_poi_ids : [],
    preference_signals: payload.preference_signals || {},
    replan_acceleration_cache: replanCache,
  };
}

function parseGoal(goal: string, defaults: Partial<TravelPlanningRequest> = {}): TravelPlanningRequest {
  const compactGoal = goal.replace(/\s+/g, '');
  const wantsCouple = /情侣|约会|恋人|浪漫|两个人|二人/.test(goal);
  const wantsSenior = /老人|长辈|父母|爸妈|老年|别太累/.test(goal);
  const wantsKids = /亲子|孩子|小孩|儿童|带娃|遛娃|家庭/.test(goal);
  const noFood = /不吃饭|不安排吃饭|不要吃饭|不用吃饭/.test(goal);
  const explicitCulture = /文化路线|文化景点|经典文化/.test(goal);
  const asksFood = !noFood && /吃|好吃|饭|餐|美食|午餐|午饭|晚餐|咖啡|喝咖啡|烤鸭|炸酱面|小吃|吃逛|每天安排吃饭/.test(goal);
  const asksLunch = !noFood && !/晚上|夜间|夜游|晚餐/.test(goal) && /中午|午餐|午饭|午间|每天安排吃饭|好吃|美食/.test(goal);
  const routeMode: RouteMode = noFood || (explicitCulture && !asksFood) ? 'culture' : defaults.route_mode ?? (asksFood ? 'mixed' : 'culture');
  const areas = ['前门', '故宫', '什刹海', '后海', '南锣鼓巷', '王府井', '天坛', '天安门', '西单', '地坛', '建国门', '宣武门', '北海', '景山', '颐和园', '圆明园', '雍和宫', '三里屯', '798', '奥林匹克公园'];
  const budgetMatch = goal.match(/预算(?:降到|控制在|不超|不超过|以内)?(\d+)/) ?? goal.match(/(\d+)元?(?:以内|以下|内)/);
  const durationMatch = goal.match(/(\d+(?:\.\d+)?)(?:个)?小时/);
  const dayMatch = goal.match(/(\d+)(?:天|日)/);
  const poiMatch = goal.match(/(\d+)(?:个|处|站|家)?(?:POI|点|景点|地方)/i);
  const parsedExcludedNames = extractExcludedNames(goal);
  const parsedIncludedNames = extractIncludedNames(goal);
  const chineseDayMatch = goal.match(/([一二两三四五六七八九十])(?:天|日)/)?.[1];
  const chineseDayCount = chineseDayMatch
    ? ({ 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 } as Record<string, number>)[chineseDayMatch]
    : null;
  const dayCount = dayMatch?.[1]
    ? Math.max(1, Math.min(MAX_TRIP_DAYS, Number(dayMatch[1])))
    : chineseDayCount
      ? Math.max(1, Math.min(MAX_TRIP_DAYS, chineseDayCount))
      : /整天|全天/.test(goal)
        ? 1
        : defaults.day_count ?? 1;
  const maxDuration = durationMatch?.[1]
    ? Math.round(Number(durationMatch[1]) * 60)
    : /半日|半天/.test(goal)
      ? 4 * 60
      : defaults.max_duration_min ?? (dayCount > 1 ? dayCount * 8 * 60 : dayCount >= 1 && /(天|日|整天|全天)/.test(goal) ? 8 * 60 : null);
  const excludeNames = [...(defaults.exclude_names || [])];
  excludeNames.push(...parsedExcludedNames);
  const coffeeWanted = /咖啡|喝咖啡/.test(goal) && !/(去掉|不要|排除)[^，,。；;]*咖啡/.test(goal);
  const inheritedSignals = defaults.preference_signals || {};
  const personaId = wantsKids
    ? 'family_kids'
    : wantsSenior
      ? 'senior_relaxed'
      : wantsCouple
        ? 'couple_romantic'
        : defaults.persona_id ?? 'classic_first_timer';

  return normalizeRequest({
    ...defaults,
    goal,
    route_mode: routeMode,
    area: areas.find((item) => compactGoal.includes(item)) ?? defaults.area ?? null,
    start_time: defaults.start_time ?? (/晚上|夜间|夜游|晚餐/.test(goal) ? '18:00' : asksLunch && maxDuration && maxDuration <= 300 ? '10:00' : undefined),
    max_budget: budgetMatch?.[1] ? Number(budgetMatch[1]) : defaults.max_budget ?? null,
    max_duration_min: maxDuration,
    max_total_pois: poiMatch?.[1] ? Number(poiMatch[1]) : defaults.max_total_pois ?? (maxDuration && maxDuration <= 270 ? 3 : dayCount > 1 ? 4 : 4),
    day_count: dayCount,
    persona_id: personaId,
    walk_preference: /少走路|少步行|别太累|老人|轻松|长辈|父母|带娃|亲子|孩子|小孩/.test(goal) ? 'low' : defaults.walk_preference ?? 'medium',
    pace: /紧凑|多逛|效率/.test(goal) ? 'compact' : /轻松|慢|老人|长辈|父母|带娃|亲子|孩子|小孩|别太累/.test(goal) ? 'relaxed' : defaults.pace ?? 'balanced',
    exclude_names: excludeNames,
    must_include_names: Array.from(new Set([
      ...(defaults.must_include_names || []),
      ...parsedIncludedNames,
      ...(areas.find((item) => compactGoal.includes(item)) && /(去|玩|逛|看|附近|周边|路线)/.test(goal)
        ? [areas.find((item) => compactGoal.includes(item)) as string]
        : []),
    ])),
    preference_signals: {
      avoid_queue: /不想排队|少排队|排队/.test(goal) || Boolean(inheritedSignals.avoid_queue),
      value_for_money: /性价比|预算|便宜|实惠/.test(goal) || Boolean(inheritedSignals.value_for_money),
      quality_food: /好吃|吃好|吃点好的|靠谱|美食|口碑|招牌|特色|不踩雷|推荐餐厅/.test(goal) || Boolean(inheritedSignals.quality_food),
      hotel_anchor: /住宿|酒店|宾馆|民宿|住在|从.*出发/.test(goal) || Boolean(inheritedSignals.hotel_anchor),
      family: wantsKids || Boolean(inheritedSignals.family),
      senior: wantsSenior || Boolean(inheritedSignals.senior),
      couple: wantsCouple || Boolean(inheritedSignals.couple),
      lunch: asksLunch || Boolean(inheritedSignals.lunch),
      formal_meal: asksFood && !/咖啡|甜品|下午茶|小吃/.test(goal) || Boolean(inheritedSignals.formal_meal),
      coffee: coffeeWanted,
    },
  });
}

function applyStableGoalIntentPatch(goal: string, request: TravelPlanningRequest): TravelPlanningRequest {
  const text = String(goal || '');
  if (!text.trim()) return request;
  const noFood = /不吃饭|不安排吃饭|不要吃饭|不用吃饭|不含餐/.test(text);
  const asksFood = !noFood && /吃饭|吃好|好吃|美食|餐饮|午餐|午饭|中午|晚餐|饭店|餐厅|小吃|咖啡|下午茶|每.?天.*吃|安排.*餐/.test(text);
  const asksCoffee = /咖啡|下午茶|甜品|奶茶/.test(text);
  const asksLunch = asksFood && !/晚上|夜间|夜游|晚餐/.test(text) && /中午|午餐|午饭|午间|吃饭|好吃|美食|餐饮|每.?天.*吃|安排.*餐/.test(text);
  const wantsCouple = /情侣|约会|恋人|浪漫|两个人|二人|鎯呬荆|娴极/.test(text);
  const wantsSenior = /老人|长辈|父母|爸妈|老年|别太累|不累|慢一点|鑰佷汉|闀胯緢|鐖舵瘝|鍒お绱/.test(text);
  const wantsKids = /亲子|孩子|小孩|儿童|带娃|遛娃|家庭|浜插瓙|瀛╁瓙|灏忓|鍎跨/.test(text);
  const lowWalk = /少走路|少步行|别太累|不累|轻松|老人|长辈|父母|爸妈|带娃|亲子|孩子|小孩|灏戣蛋璺|鍒お绱/.test(text);
  const qualityFood = /好吃|吃好|吃点好的|靠谱|美食|口碑|招牌|特色|不踩雷|推荐餐厅/.test(text);
  const avoidQueue = /不想排队|少排队|别排队|排队少|低排队|排队/.test(text);
  const valueForMoney = /性价比|预算|便宜|实惠|划算/.test(text);
  const personaId = wantsKids
    ? 'family_kids'
    : wantsSenior
      ? 'senior_relaxed'
      : wantsCouple
        ? 'couple_romantic'
        : request.persona_id;
  return normalizeRequest({
    ...request,
    route_mode: noFood ? 'culture' : asksFood ? 'mixed' : request.route_mode,
    persona_id: personaId,
    walk_preference: lowWalk ? 'low' : request.walk_preference,
    pace: lowWalk || wantsSenior || wantsKids ? 'relaxed' : request.pace,
    route_order_poi_ids: wantsKids || wantsSenior || wantsCouple ? [] : request.route_order_poi_ids,
    preference_signals: {
      ...(request.preference_signals || {}),
      lunch: noFood ? false : asksLunch || Boolean(request.preference_signals?.lunch),
      formal_meal: noFood ? false : (asksFood && !asksCoffee) || Boolean(request.preference_signals?.formal_meal),
      quality_food: noFood ? false : qualityFood || Boolean(request.preference_signals?.quality_food),
      coffee: noFood ? false : asksCoffee || Boolean(request.preference_signals?.coffee),
      avoid_queue: avoidQueue || Boolean(request.preference_signals?.avoid_queue),
      value_for_money: valueForMoney || Boolean(request.preference_signals?.value_for_money),
      family: wantsKids || Boolean(request.preference_signals?.family),
      senior: wantsSenior || Boolean(request.preference_signals?.senior),
      couple: wantsCouple || Boolean(request.preference_signals?.couple),
    },
  });
}

function meters(a: Poi, b: Poi): number {
  const rad = Math.PI / 180;
  const lat1 = a.lat * rad;
  const lat2 = b.lat * rad;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

function transferMinutes(distanceMeters: number): number {
  return Math.max(4, Math.round(distanceMeters / 70));
}

function estimateCoordinateFallback(distanceMeters: number) {
  if (distanceMeters <= 800) {
    return {
      minutes: transferMinutes(distanceMeters),
      mode: 'walking_estimate',
    };
  }
  if (distanceMeters <= 3000) {
    // Shared-bike style local fallback: includes unlock/parking buffer.
    return {
      minutes: Math.max(6, Math.round(distanceMeters / 180) + 4),
      mode: 'bike_estimate',
    };
  }
  return {
    minutes: Math.max(10, Math.round(distanceMeters / 260) + 8),
    mode: 'driving_estimate',
  };
}

function estimateTransfer(a: Poi, b: Poi, commuteEdges?: CommuteEdgeIndex): TransferEstimate {
  const edge =
    commuteEdges?.edgesByPair.get(commutePairKey(a.poi_id, b.poi_id))?.[0]
    ?? commuteEdges?.edgesByPair.get(commutePairKey(b.poi_id, a.poi_id))?.[0];
  if (edge && Number.isFinite(edge.duration_s) && edge.duration_s > 0) {
    const metersValue = edge.walking_distance_m ?? edge.distance_m ?? meters(a, b);
    return {
      minutes: Math.max(1, Math.round(edge.duration_s / 60)),
      meters: Math.round(Number(metersValue || 0)),
      source: 'commute_edge',
      mode: edge.mode,
      provider: edge.provider,
      duration_s: edge.duration_s,
      transfer_count: edge.transfer_count,
    };
  }
  const distance = meters(a, b);
  const fallback = estimateCoordinateFallback(distance);
  return {
    minutes: fallback.minutes,
    meters: Math.round(distance),
    source: 'coordinate_estimate',
    mode: fallback.mode,
    provider: null,
    duration_s: null,
    transfer_count: null,
  };
}

function parseMinutes(value?: string): number | null {
  if (!value) return null;
  const match = String(value).match(/(\d{1,2}):?(\d{2})?/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2] || 0);
}

function minutesToTime(total: number): string {
  const normalized = ((total % 1440) + 1440) % 1440;
  return `${Math.floor(normalized / 60).toString().padStart(2, '0')}:${(normalized % 60).toString().padStart(2, '0')}`;
}

function aggregateMap(data: TravelData, poiId: string) {
  const claims = data.reviewAggregatesByPoiId.get(poiId) || [];
  const values = Object.fromEntries(claims.map((item) => [item.feature_key, item.feature_value]));
  return { claims, values };
}

function poiText(item: Poi): string {
  return [
    item.name,
    item.category,
    item.poi_type,
    item.family_friendliness,
    ...(Array.isArray(item.planning_tags) ? item.planning_tags : []),
    ...(Array.isArray(item.evidence_tags) ? item.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');
}

function isFamilyCulturePoi(item: Poi): boolean {
  if (isFoodPoi(item)) return false;
  const text = poiText(item);
  return item.family_friendliness === 'high'
    || /family|children|child|kids|kid|museum|science|nature|theater|low_stress|scene:family|theme:museum|category:museum|亲子|儿童|孩子|小孩|带娃|博物馆|博物院|科技|自然|剧院|剧场|妇女儿童/.test(text)
    || /浜插瓙|鍎跨|瀛╁瓙|灏忓|鍗氱墿棣|鍗氱墿闄|绉戞妧|鑷劧|鍓ч櫌/.test(text);
}

function familyCulturePriority(item: Poi): number {
  const text = poiText(item);
  let priority = Number(item.rating || 0) * 10 + Math.min(Number(item.review_count || 0), 600) / 100;
  if (/儿童|亲子|妇女儿童|children|family|scene:family|浜插瓙|鍎跨/.test(text)) priority += 60;
  if (/博物馆|museum|theme:museum|category:museum|鍗氱墿棣/.test(text)) priority += 55;
  if (/博物院|鍗氱墿闄/.test(text)) priority += 28;
  if (/科技|自然|science|nature|绉戞妧|鑷劧/.test(text)) priority += 35;
  if (/教堂|步行街|售票处|酒店|宾馆|漫心府|鏁欏爞|姝ヨ琛|鍞エ|閰掑簵|婕績搴/.test(text)) priority -= 80;
  if (item.walk_intensity === 'low') priority += 10;
  if (item.walk_intensity === 'high') priority -= 20;
  return priority;
}

function familyAssertionPriority(item: Poi): number {
  const name = String(item.name || '');
  if (/儿童|亲子|妇女儿童|剧院|博物馆/.test(name)) return 3;
  if (/children|family|theater|museum/i.test(poiText(item))) return 2;
  if (/博物院/.test(name)) return 1;
  return 0;
}

function isStrongFamilyCulturePoi(item: Poi): boolean {
  return familyAssertionPriority(item) >= 3;
}

function allPlannerPois(data: TravelData): Poi[] {
  return uniqueByName([...data.culturePois, ...data.mixedPois, ...data.plannerEntities]);
}

function scorePoi(item: Poi, request: TravelPlanningRequest, strategy: Strategy, data: TravelData): number {
  const { values } = aggregateMap(data, item.poi_id);
  let score = Number(item.rating || 0) * 12 + Math.min(Number(item.review_count || 0), 500) / 100;
  const cost = Number(item.avg_cost || 0);
  const duration = Number(item.suggested_duration_min || 90);
  const text = poiText(item);
  if (strategy === 'budget') score -= cost / 8;
  else score -= cost / 25;
  if (strategy === 'efficient') score -= duration / 5;
  else score -= duration / 14;
  if (request.preference_signals?.avoid_queue && values.queue_risk === 'low') score += 10;
  if (request.preference_signals?.avoid_queue && values.queue_risk === 'high') score -= 18;
  if (request.preference_signals?.value_for_money && values.value_for_money === 'high') score += 8;
  if (request.preference_signals?.family && values.family_friendliness === 'high') score += 8;
  if (values.environment_quality === 'high') score += 2;
  if (request.walk_preference === 'low' && item.walk_intensity === 'high') score -= 8;
  if (request.preference_signals?.lunch && isFoodPoi(item) && !isLunchPoi(item)) score -= 20;
  if (request.preference_signals?.quality_food && isFoodPoi(item)) {
    score += Number(item.rating || 0) * 8 + Math.min(Number(item.review_count || 0), 800) / 80;
    if (values.value_for_money === 'low') score -= 4;
    if (item.meal_type === 'hotel_dining' || item.meal_type === 'invalid') score -= 28;
  }
  if (request.preference_signals?.indoor) {
    if (/scene:indoor|museum|art_gallery|theme:museum|theme:art|\u535a\u7269\u9986|\u7f8e\u672f\u9986|\u827a\u672f\u4e2d\u5fc3|\u5c55\u89c8\u9986/.test(text)) score += 28;
    if (/博物馆|美术馆|艺术中心|展览馆/.test(item.name)) score += 42;
    if (/博物院/.test(item.name) && !/博物馆|美术馆|艺术中心|展览馆/.test(item.name)) score -= 24;
    if (/scene:outdoor|park|\u516c\u56ed|\u5e7f\u573a|\u6b65\u884c\u8857/.test(text)) score -= 18;
  }

  if (request.persona_id === 'couple_romantic' || request.preference_signals?.couple) {
    if (/coffee|cafe|咖啡|甜品|下午茶/.test(text)) score += 14;
    if (/art|gallery|美术|艺术|展览|theater|剧场|电影|音乐|scene:indoor/.test(text)) score += 9;
    if (/park|公园|什刹海|后海|前海|夜景|landmark/.test(text)) score += 4;
    if (/family|儿童|亲子/.test(text)) score -= 8;
  }

  if (request.persona_id === 'senior_relaxed' || request.preference_signals?.senior) {
    if (item.walk_intensity === 'low' || /walk:low/.test(text)) score += 14;
    if (/need:short_stop|need:indoor_backup|scene:indoor|rain_friendly|low_stress/.test(text)) score += 8;
    if (/museum|博物馆|美术|艺术|公园|attraction|景点/.test(text)) score += 6;
    if (/family|children|儿童|亲子|妇女儿童|scene:family/.test(text)) score -= 16;
    if (item.walk_intensity === 'medium') score -= 6;
    if (item.walk_intensity === 'high') score -= 18;
    if (cost > 180) score -= 10;
  }

  if (request.persona_id === 'family_kids' || request.preference_signals?.family) {
    if (values.family_friendliness === 'high' || item.family_friendliness === 'high') score += 18;
    if (/family|children|儿童|亲子|孩子|科技|自然|museum|博物馆|博物院|science|nature|low_stress|scene:family/.test(text)) score += 28;
    if (/教堂|步行街|售票处|酒店|漫心府/.test(text)) score -= 12;
    if (/coffee|cafe|咖啡/.test(text) && request.preference_signals?.lunch) score -= 12;
    if (item.walk_intensity === 'low' || /walk:low/.test(text)) score += 6;
    if (item.walk_intensity === 'high') score -= 14;
    if (isFamilyCulturePoi(item)) score += 22;
  }
  return score;
}

function selectAdditionalStop(params: {
  data: TravelData;
  request: TravelPlanningRequest;
  selectedPois: Poi[];
  excludedIds: Set<string>;
  excludedNames: string[];
  wantsFood: boolean;
  wantsSnack: boolean;
  wantsIndoor: boolean;
}): Poi | null {
  const selectedIds = new Set(params.selectedPois.map((item) => item.poi_id));
  const selectedGroups = new Set(params.selectedPois.map((item) => attractionGroupKey(item)).filter(Boolean));
  const selectedAreas = new Set(params.selectedPois.flatMap((item) => [item.area, item.district]).filter(Boolean).map(String));
  const pool = candidatePool(params.data, params.request)
    .filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat))
    .filter((item) => !selectedIds.has(item.poi_id))
    .filter((item) => !params.excludedIds.has(item.poi_id))
    .filter((item) => !matchesExcludedName(item, params.excludedNames))
    .filter(isRecommendablePoi)
    .filter((item) => {
      if (params.wantsSnack) return isSnackOrTeaPoi(item);
      if (params.wantsFood) return isFoodPoi(item);
      if (isFoodPoi(item)) return false;
      if (params.wantsIndoor) return isIndoorCulturePoi(item);
      return true;
    })
    .filter((item) => !selectedGroups.has(attractionGroupKey(item)));

  const scored = pool.map((item) => {
    const nearest = params.selectedPois.length
      ? Math.min(...params.selectedPois.map((selected) => meters(selected, item)))
      : 0;
    const sameAreaBoost = selectedAreas.has(String(item.area || '')) || selectedAreas.has(String(item.district || '')) ? 28 : 0;
    const proximityBoost = nearest > 0 ? Math.max(0, 30 - nearest / 120) : 0;
    const indoorBoost = !params.wantsSnack && isIndoorCulturePoi(item) ? 8 : 0;
    const snackBoost = params.wantsSnack && isSnackOrTeaPoi(item) ? 40 : 0;
    const lowWalkBoost = params.request.walk_preference === 'low' && item.walk_intensity === 'low' ? 8 : 0;
    return {
      item,
      score: scorePoi(item, params.request, 'balanced', params.data) + sameAreaBoost + proximityBoost + indoorBoost + snackBoost + lowWalkBoost,
    };
  });

  return scored.sort((a, b) => b.score - a.score)[0]?.item || null;
}

function selectArea(request: TravelPlanningRequest, candidates: Poi[]): string {
  if (request.area && candidates.some((item) => item.area === request.area || item.district === request.area)) return request.area;
  const counts = new Map<string, number>();
  for (const item of candidates) {
    const area = item.area && item.area !== '未知' ? item.area : item.district || '故宫';
    counts.set(area, (counts.get(area) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '故宫';
}

function selectPopularAreas(candidates: Poi[], limit: number): string[] {
  const counts = new Map<string, number>();
  for (const item of candidates) {
    const area = item.area && !String(item.area).includes('未知') ? item.area : item.district;
    if (!area || String(area).includes('未知')) continue;
    counts.set(area, (counts.get(area) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([area]) => area).slice(0, Math.max(1, limit));
}

function orderNearest(items: Poi[], commuteEdges?: CommuteEdgeIndex): Poi[] {
  if (items.length <= 2) return items;
  const remaining = [...items];
  const ordered = [remaining.shift()!];
  while (remaining.length) {
    const last = ordered[ordered.length - 1];
    let bestIndex = 0;
    let bestScore = Infinity;
    remaining.forEach((item, index) => {
      const estimate = estimateTransfer(last, item, commuteEdges);
      const score = estimate.source === 'commute_edge' ? estimate.meters * 0.6 : estimate.meters;
      if (score < bestScore) {
        bestScore = score;
        bestIndex = index;
      }
    });
    ordered.push(remaining.splice(bestIndex, 1)[0]);
  }
  return ordered;
}

function buildStopEvidence(item: Poi, data: TravelData) {
  const { claims, values } = aggregateMap(data, item.poi_id);
  const topEvidence = claims.slice(0, 4).map((claim) => {
    const refs = Array.isArray(claim.evidence_refs) ? claim.evidence_refs : [];
    const review = refs.map((ref) => data.reviewRecordsById.get(String(ref))).find(Boolean);
    return {
      feature_key: claim.feature_key,
      feature_value: claim.feature_value,
      status: claim.status,
      confidence: claim.confidence ?? null,
      review_text: review?.review_text || null,
    };
  });
  return {
    signals: {
      queue_risk: values.queue_risk || item.queue_risk || 'unavailable',
      value_for_money: values.value_for_money || item.value_for_money || 'unavailable',
      family_friendliness: values.family_friendliness || item.family_friendliness || 'unavailable',
      environment_quality: values.environment_quality || item.environment_quality || 'unavailable',
    },
    evidence_review_count: claims.reduce((sum, claim) => sum + Number(claim.review_count_used || 0), 0),
    top_evidence: topEvidence,
    confidence_note: topEvidence.length ? 'UGC signals are aggregated from local review features.' : 'No local review evidence for this POI yet.',
  };
}

function buildReason(item: Poi, request: TravelPlanningRequest, data: TravelData): string {
  const { values } = aggregateMap(data, item.poi_id);
  const parts = [`${item.area || item.district || '北京'} area`, `rating ${Number(item.rating || 0).toFixed(1)}`, `stay about ${Number(item.suggested_duration_min || 90)} min`];
  if (request.preference_signals?.avoid_queue && values.queue_risk) parts.push(`queue ${values.queue_risk}`);
  if (request.preference_signals?.value_for_money && values.value_for_money) parts.push(`value ${values.value_for_money}`);
  if (item.meal_type && item.meal_type !== 'non_food') parts.push(`meal type ${item.meal_type}`);
  return parts.join('; ');
}

function translateRisk(risk: unknown): string {
  const text = String(risk || '');
  if (text.includes('Estimated budget')) {
    const match = text.match(/Estimated budget (\d+) exceeds requested (\d+)/);
    return match ? `预算估算 ${match[1]} 元，超过用户要求 ${match[2]} 元。` : '预算估算超过用户要求。';
  }
  if (text.includes('Estimated route duration')) {
    const match = text.match(/Estimated route duration is (\d+) minutes, above requested (\d+)/);
    return match ? `路线总时长估算 ${match[1]} 分钟，超过用户要求 ${match[2]} 分钟。` : '路线总时长超过用户要求。';
  }
  if (text.includes('opening-hours data')) return '部分点位可能与本地营业时间数据冲突。';
  if (text.includes('complete opening-hours coverage')) {
    const match = text.match(/(\d+) stop/);
    return `${match?.[1] || '部分'} 个点位缺少完整营业时间覆盖。`;
  }
  if (text.includes('Walking distance')) return '步行距离和转移时间为本地坐标估算，不代表实时导航。';
  return text;
}

function summarizeProposalTransfers(proposals: Array<{ transfer_source_summary?: { commute_edges_used?: number; coordinate_estimates_used?: number } }>) {
  const commuteEdgesUsed = proposals.reduce((sum, proposal) => sum + Number(proposal.transfer_source_summary?.commute_edges_used || 0), 0);
  const coordinateEstimatesUsed = proposals.reduce((sum, proposal) => sum + Number(proposal.transfer_source_summary?.coordinate_estimates_used || 0), 0);
  const totalTransfers = commuteEdgesUsed + coordinateEstimatesUsed;
  return {
    commute_edges_used: commuteEdgesUsed,
    coordinate_estimates_used: coordinateEstimatesUsed,
    commute_edge_hit_rate: totalTransfers > 0 ? Number((commuteEdgesUsed / totalTransfers).toFixed(3)) : 0,
  };
}

function countGroundedStops(stops: Array<Record<string, any>>): number {
  return stops.filter((stop) => {
    const evidence = stop.evidence_summary || {};
    return Number(evidence.evidence_review_count || 0) > 0
      || (Array.isArray(evidence.top_evidence) && evidence.top_evidence.length > 0)
      || Boolean(evidence.signals && Object.keys(evidence.signals).length > 0);
  }).length;
}

function buildQualitySummary(params: {
  request: TravelPlanningRequest;
  stops: Array<Record<string, any>>;
  totalBudget: number;
  totalDuration: number;
  totalDistance: number;
  transferSummary: { commute_edges_used: number; coordinate_estimates_used: number; commute_edge_hit_rate: number };
  categorySatisfied: boolean;
}) {
  const { request, stops, totalBudget, totalDuration, totalDistance, transferSummary, categorySatisfied } = params;
  const budgetSatisfied = request.max_budget === null || request.max_budget === undefined || totalBudget <= Number(request.max_budget);
  const durationSatisfied = request.max_duration_min === null || request.max_duration_min === undefined || totalDuration <= Number(request.max_duration_min);
  const timelineReady = stops.every((stop) => /^\d{2}:\d{2}$/.test(String(stop.arrival_time || '')) && /^\d{2}:\d{2}$/.test(String(stop.departure_time || '')));
  const transferReady = stops.every((stop, index) => index === 0 || ['commute_edge', 'coordinate_estimate'].includes(String(stop.transfer_source)));
  const openingHoursSatisfied = stops.every((stop) => String(stop.opening_status || 'unknown') !== 'conflict');
  const groundedStops = countGroundedStops(stops);
  const hasQueueConflict = stops.some((stop) => /high|高|long|排队久/i.test(String(stop.evidence_summary?.signals?.queue_risk || '')));
  const queueSatisfied = !request.preference_signals?.avoid_queue || !hasQueueConflict;
  const walkSatisfied = request.walk_preference !== 'low' || totalDistance <= 3000;
  const activeSignals = Object.entries(request.preference_signals || {})
    .filter(([, enabled]) => Boolean(enabled))
    .map(([key]) => key);
  const validations = {
    poi_count_valid: stops.length >= 3,
    category_coverage_valid: categorySatisfied,
    timeline_valid: timelineReady,
    transfer_valid: transferReady,
    budget_valid: budgetSatisfied,
    duration_valid: durationSatisfied,
    opening_hours_valid: openingHoursSatisfied,
    evidence_valid: groundedStops >= Math.min(2, stops.length),
    queue_valid: queueSatisfied,
    walk_valid: walkSatisfied,
  };
  const readinessChecks = [
    validations.poi_count_valid,
    validations.timeline_valid,
    validations.transfer_valid,
    validations.budget_valid,
    validations.duration_valid,
    validations.category_coverage_valid,
    validations.evidence_valid,
    validations.queue_valid,
    stops.every((stop) => String(stop.recommendation_reason || '').length > 0),
  ];
  const passedChecks = readinessChecks.filter(Boolean).length;
  return {
    route_generation_ready: stops.length >= 3 && timelineReady && transferReady,
    executable_route: timelineReady && transferReady,
    competition_readiness_score: Number((passedChecks / readinessChecks.length).toFixed(3)),
    constraints: {
      budget_satisfied: budgetSatisfied,
      duration_satisfied: durationSatisfied,
      category_coverage_satisfied: categorySatisfied,
      queue_satisfied: queueSatisfied,
      walk_satisfied: walkSatisfied,
      opening_hours_satisfied: openingHoursSatisfied,
    },
    validations,
    personalization: {
      persona_id: request.persona_id || 'classic_first_timer',
      walk_preference: request.walk_preference || 'medium',
      active_preference_signals: activeSignals,
      applied: Boolean(request.persona_id && request.persona_id !== 'classic_first_timer') || activeSignals.length > 0,
    },
    data_grounding: {
      stops_with_recommendation_reason: stops.filter((stop) => String(stop.recommendation_reason || '').length > 0).length,
      stops_with_evidence_summary: stops.filter((stop) => Boolean(stop.evidence_summary)).length,
      stops_with_ugc_or_feature_evidence: groundedStops,
      evidence_coverage_rate: stops.length ? Number((groundedStops / stops.length).toFixed(3)) : 0,
    },
    commute: {
      uses_commute_edges: transferSummary.commute_edges_used > 0,
      ...transferSummary,
    },
  };
}

function buildConstraintReport(params: {
  request: TravelPlanningRequest;
  stops: Array<Record<string, any>>;
  totalBudget: number;
  totalDuration: number;
  totalDistance: number;
  categorySatisfied: boolean;
}) {
  const { request, stops, totalBudget, totalDuration, totalDistance, categorySatisfied } = params;
  const foodCount = stops.filter((stop) => stop.poi_type === 'food').length;
  const cultureCount = stops.length - foodCount;
  const highQueueStops = stops
    .filter((stop) => /high|高|long|排队久/i.test(String(stop.evidence_summary?.signals?.queue_risk || '')))
    .map((stop) => stop.name);
  const openingConflicts = stops
    .filter((stop) => String(stop.opening_status || 'unknown') === 'conflict')
    .map((stop) => stop.name);
  const checks = {
    poi_count: {
      required_min: 3,
      actual: stops.length,
      satisfied: stops.length >= 3,
    },
    category_coverage: {
      route_mode: request.route_mode,
      food_count: foodCount,
      culture_or_entertainment_count: cultureCount,
      required_food_count: request.route_mode === 'mixed' ? 1 : 0,
      required_culture_or_entertainment_count: request.route_mode === 'mixed' ? 2 : 3,
      satisfied: categorySatisfied,
    },
    budget: {
      max_budget: request.max_budget ?? null,
      estimated_budget: totalBudget,
      satisfied: request.max_budget === null || request.max_budget === undefined || totalBudget <= Number(request.max_budget),
    },
    duration: {
      max_duration_min: request.max_duration_min ?? null,
      estimated_duration_min: totalDuration,
      satisfied: request.max_duration_min === null || request.max_duration_min === undefined || totalDuration <= Number(request.max_duration_min),
    },
    distance: {
      walk_preference: request.walk_preference || 'medium',
      estimated_transfer_distance_m: Math.round(totalDistance),
      satisfied: request.walk_preference !== 'low' || totalDistance <= 3000,
    },
    queue: {
      avoid_queue_requested: Boolean(request.preference_signals?.avoid_queue),
      high_queue_stop_names: highQueueStops,
      satisfied: !request.preference_signals?.avoid_queue || highQueueStops.length === 0,
    },
    opening_hours: {
      conflict_stop_names: openingConflicts,
      unknown_count: stops.filter((stop) => String(stop.opening_status || 'unknown') === 'unknown').length,
      satisfied: openingConflicts.length === 0,
    },
    personalization: {
      persona_id: request.persona_id || 'classic_first_timer',
      active_preference_signals: Object.entries(request.preference_signals || {})
        .filter(([, enabled]) => Boolean(enabled))
        .map(([key]) => key),
      applied: Boolean(request.persona_id && request.persona_id !== 'classic_first_timer') || Object.values(request.preference_signals || {}).some(Boolean),
    },
  };
  const satisfiedCount = Object.values(checks).filter((item: any) => item.satisfied !== false).length;
  return {
    overall_satisfied: Object.values(checks).every((item: any) => item.satisfied !== false),
    satisfied_count: satisfiedCount,
    total_count: Object.keys(checks).length,
    checks,
  };
}

function buildConstraintResolution(report: Record<string, any>) {
  const checks = report.checks || {};
  const violations = Object.entries(checks)
    .filter(([, value]: [string, any]) => value?.satisfied === false)
    .map(([key]) => key);
  const priorityOrder = ['poi_count', 'category_coverage', 'duration', 'budget', 'distance', 'queue', 'opening_hours'];
  const protectedConstraints = priorityOrder.filter((key) => checks[key]?.satisfied === true);
  const tradeoffs = violations.map((key) => {
    if (key === 'duration') return '时长约束偏紧，系统优先保留 3+ POI 与餐饮/文化覆盖，并在风险中提示可能超时。';
    if (key === 'budget') return '预算约束偏紧，系统优先保留可执行路线，并通过预算优先方案提供更低成本备选。';
    if (key === 'distance') return '少走路偏好与点位覆盖存在冲突，系统优先使用同片区与本地通勤边降低转场。';
    if (key === 'queue') return '少排队偏好无法完全保证，系统基于本地 UGC 排队风险规避明显高风险点。';
    if (key === 'opening_hours') return '本地营业时间存在不确定或冲突，系统显式标注风险，建议出发前复核。';
    if (key === 'category_coverage') return '当前数据召回未完全覆盖餐饮/文化组合，系统保留多方案用于替换。';
    return `${key} 未完全满足，系统已在方案风险中显式提示。`;
  });
  return {
    strategy: violations.length ? 'partial_satisfaction_with_explicit_tradeoff' : 'all_core_constraints_satisfied',
    priority_order: priorityOrder,
    protected_constraints: protectedConstraints,
    relaxed_constraints: violations,
    tradeoffs,
    user_visible_summary: violations.length
      ? `已优先保证 ${protectedConstraints.join(', ') || '核心可执行性'}，但 ${violations.join(', ')} 需要取舍。`
      : '路线满足 3+ POI、餐饮/文化覆盖、时间轴、预算/时长等核心约束。',
  };
}

function buildSlaMetrics(params: {
  started: number;
  fastPath: string;
  llmBlocking: boolean;
  fallbackUsed?: boolean;
}) {
  const elapsedMs = Number((performance.now() - params.started).toFixed(2));
  return {
    elapsed_ms: elapsedMs,
    within_10s: elapsedMs < 10000,
    sla: {
      target_ms: 10000,
      elapsed_ms: elapsedMs,
      within_10s: elapsedMs < 10000,
      fast_path: params.fastPath,
      llm_blocking: params.llmBlocking,
      fallback_used: Boolean(params.fallbackUsed),
    },
  };
}

function buildRoutePatchSummary(params: {
  beforeIds: string[];
  beforeNames: string[];
  afterProposal?: Record<string, any> | null;
  adjustmentText?: string;
}) {
  const afterIds = ((params.afterProposal?.ordered_poi_ids || []) as unknown[]).map(String);
  const afterNames = ((params.afterProposal?.ordered_poi_names || []) as unknown[]).map(String);
  const beforeIdSet = new Set(params.beforeIds.map(String));
  const afterIdSet = new Set(afterIds);
  return {
    adjustment_text: params.adjustmentText || '',
    before_poi_count: params.beforeIds.length,
    after_poi_count: afterIds.length,
    preserved_poi_ids: afterIds.filter((id) => beforeIdSet.has(id)),
    removed_poi_ids: params.beforeIds.filter((id) => !afterIdSet.has(String(id))),
    added_poi_ids: afterIds.filter((id) => !beforeIdSet.has(id)),
    before_route_names: params.beforeNames,
    after_route_names: afterNames,
    kept: params.beforeNames.filter((name) => afterNames.includes(name)),
    removed: params.beforeNames.filter((name) => !afterNames.includes(name)),
    added: afterNames.filter((name) => !params.beforeNames.includes(name)),
    changed: params.beforeIds.join('|') !== afterIds.join('|'),
  };
}

function mergeIntentIntoReplanRequest(request: TravelPlanningRequest, intent: TravelQueryIntent | null): TravelPlanningRequest {
  if (!intent) return request;
  const patch = intentToPlannerLikeRequest(intent);
  return normalizeRequest({
    ...request,
    route_mode: patch.route_mode || request.route_mode,
    area: patch.area ?? request.area,
    max_budget: patch.max_budget ?? request.max_budget,
    max_duration_min: patch.max_duration_min ?? request.max_duration_min,
    walk_preference: patch.walk_preference || request.walk_preference,
    persona_id: patch.persona_id || request.persona_id,
    must_include_names: Array.from(new Set([
      ...(request.must_include_names || []),
      ...(patch.must_include_names || []),
    ])),
    exclude_names: Array.from(new Set([
      ...(request.exclude_names || []),
      ...(patch.exclude_names || []),
    ])),
    preference_signals: {
      ...(request.preference_signals || {}),
      ...(patch.preference_signals || {}),
    },
  });
}

function poiFromProposalStop(stop: Record<string, any>): Poi | null {
  const id = String(stop.poi_id || '').trim();
  const name = String(stop.name || '').trim();
  const lng = Number(stop.lng ?? stop.longitude);
  const lat = Number(stop.lat ?? stop.latitude);
  if (!id || !name) return null;
  return normalizePoi({
    poi_id: id,
    name,
    district: String(stop.district || stop.area || '未知'),
    area: String(stop.area || stop.district || '未知'),
    category: String(stop.category || 'unknown'),
    poi_type: stop.poi_type === 'food' ? 'food' : 'culture',
    address: String(stop.address || ''),
    lng: Number.isFinite(lng) ? lng : 116.4074,
    lat: Number.isFinite(lat) ? lat : 39.9042,
    rating: Number(stop.rating || 0),
    avg_cost: Number(stop.estimated_cost ?? stop.avg_cost ?? 0),
    review_count: Number(stop.review_count || 0),
    open_time: stop.open_time || undefined,
    close_time: stop.close_time || undefined,
    suggested_duration_min: Number(stop.stay_minutes || stop.suggested_duration_min || 90),
    planning_tags: Array.isArray(stop.planning_tags) ? stop.planning_tags.map(String) : [],
    evidence_tags: Array.isArray(stop.evidence_tags) ? stop.evidence_tags.map(String) : [],
    queue_risk: stop.evidence_summary?.signals?.queue_risk || stop.queue_risk || 'unknown',
    value_for_money: stop.evidence_summary?.signals?.value_for_money || stop.value_for_money || 'unknown',
    family_friendliness: stop.evidence_summary?.signals?.family_friendliness || stop.family_friendliness || 'unknown',
    environment_quality: stop.evidence_summary?.signals?.environment_quality || stop.environment_quality || 'unknown',
    is_meal_stop: stop.poi_type === 'food' || stop.meal_slot === 'lunch',
    is_lunch_suitable: stop.meal_slot === 'lunch' || stop.is_lunch_suitable,
    is_coffee_stop: Boolean(stop.is_coffee_stop),
    meal_type: stop.meal_type || (stop.poi_type === 'food' ? 'meal' : 'non_food'),
  } as Poi);
}

function selectedPoisFromProposal(data: TravelData, selectedProposal?: Record<string, any> | null): Poi[] {
  const ids = Array.isArray(selectedProposal?.ordered_poi_ids) ? selectedProposal?.ordered_poi_ids.map(String) : [];
  const stops = Array.isArray(selectedProposal?.pois) ? selectedProposal?.pois : [];
  const fromStops = new Map<string, Poi>();
  for (const stop of stops) {
    const poi = poiFromProposalStop(stop);
    if (poi) fromStops.set(poi.poi_id, poi);
  }
  return ids
    .map((id) => data.poiById.get(id) || fromStops.get(id))
    .filter(Boolean) as Poi[];
}

function resolveIncrementalMustPois(data: TravelData, request: TravelPlanningRequest): Poi[] {
  const byId = new Map<string, Poi>();
  for (const id of request.must_include_poi_ids || []) {
    const poi = data.poiById.get(String(id));
    if (poi) byId.set(poi.poi_id, poi);
  }
  const unresolvedNames = unresolvedMustIncludeNames(data, request);
  for (const name of unresolvedNames) {
    const fallback = buildFallbackPoiForIncludeName(name, request, byId.size + 1);
    byId.set(fallback.poi_id, fallback);
  }
  return [...byId.values()];
}

async function buildIncrementalReplanPatch(params: {
  started: number;
  previous: TravelPlanningRequest;
  parsed: TravelPlanningRequest;
  selectedProposal?: Record<string, any> | null;
  selectedPois: Poi[];
  selectedIds: string[];
  selectedNames: string[];
  adjustmentText: string;
  excludedIds: Set<string>;
  replanAccelerationHit: 'request_snapshot' | 'route_corpus_poi_hint' | null;
  routeCorpusPoiHintElapsedMs: number;
  targetReplacementIndex: number | null;
  wantsNamedInclude: boolean;
  wantsAddStop: boolean;
  wantsIndoor: boolean;
  wantsGenericAttraction: boolean;
  wantsFoodChange: boolean;
  wantsSnack: boolean;
}) {
  if (params.selectedPois.length < 3 || params.selectedPois.length !== params.selectedIds.length) return null;
  if (params.excludedIds.size > 0 && params.targetReplacementIndex === null) return null;

  const data = await loadTravelData();
  const commuteEdges = await loadCommuteEdges();
  const selectedIdSet = new Set(params.selectedIds);
  const excludedIds = params.excludedIds;
  let orderedPois = params.selectedPois.filter((poi) => !excludedIds.has(poi.poi_id));
  let fastPath: 'incremental_named_add' | 'incremental_generic_add' | 'incremental_target_replace' | null = null;

  if (params.targetReplacementIndex !== null) {
    const targetPoi = params.selectedPois[params.targetReplacementIndex];
    if (!targetPoi) return null;
    const replacementRequest = normalizeRequest({
      ...params.parsed,
      must_include_poi_ids: [],
      must_include_names: [],
      area: targetPoi.area || targetPoi.district || params.previous.area || null,
      max_total_pois: 3,
      route_mode: params.wantsFoodChange ? 'mixed' : params.parsed.route_mode,
      preference_signals: {
        ...(params.parsed.preference_signals || {}),
        indoor: params.wantsIndoor || Boolean(params.parsed.preference_signals?.indoor),
      },
    });
    const replacement = selectAdditionalStop({
      data,
      request: replacementRequest,
      selectedPois: params.selectedPois.filter((_, index) => index !== params.targetReplacementIndex),
      excludedIds: new Set([...excludedIds, ...params.selectedIds]),
      excludedNames: params.parsed.exclude_names || [],
      wantsFood: params.wantsFoodChange,
      wantsSnack: params.wantsSnack,
      wantsIndoor: params.wantsIndoor,
    });
    if (!replacement) return null;
    orderedPois = params.selectedPois.map((poi, index) => index === params.targetReplacementIndex ? replacement : poi);
    fastPath = 'incremental_target_replace';
  } else if (params.wantsNamedInclude) {
    const additions = resolveIncrementalMustPois(data, params.parsed)
      .filter((poi) => !selectedIdSet.has(poi.poi_id) && !excludedIds.has(poi.poi_id));
    if (additions.length) {
      orderedPois = [...orderedPois, ...additions].slice(0, 8);
      fastPath = 'incremental_named_add';
    }
  }

  if (!fastPath && params.wantsAddStop && (params.wantsGenericAttraction || params.wantsIndoor || params.wantsFoodChange || params.wantsSnack)) {
    const additional = selectAdditionalStop({
      data,
      request: params.parsed,
      selectedPois: params.selectedPois,
      excludedIds,
      excludedNames: params.parsed.exclude_names || [],
      wantsFood: params.wantsFoodChange,
      wantsSnack: params.wantsSnack,
      wantsIndoor: params.wantsIndoor,
    });
    if (!additional || selectedIdSet.has(additional.poi_id)) return null;
    orderedPois = [...orderedPois, additional].slice(0, 8);
    fastPath = 'incremental_generic_add';
  }

  if (!fastPath || orderedPois.length < 3) return null;

  const request = normalizeRequest({
    ...params.parsed,
    area: params.previous.area || params.selectedPois[0]?.area || params.selectedPois[0]?.district || null,
    max_total_pois: orderedPois.length,
    must_include_poi_ids: orderedPois.map((poi) => poi.poi_id),
    route_order_poi_ids: orderedPois.map((poi) => poi.poi_id),
    must_include_names: [],
  });
  const selectedArea = request.area || orderedPois[0]?.area || orderedPois[0]?.district || '北京';
  const proposals = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => buildProposal({
    request,
    strategy,
    selectedArea,
    candidates: orderedPois,
    data,
    commuteEdges,
  }));
  const transferSummary = summarizeProposalTransfers(proposals);
  const routePatchSummary = buildRoutePatchSummary({
    beforeIds: params.selectedIds,
    beforeNames: params.selectedNames,
    afterProposal: proposals[0],
    adjustmentText: params.adjustmentText,
  });
  const slaMetrics = buildSlaMetrics({ started: params.started, fastPath, llmBlocking: false });
  const response = applyReplanAccelerationCache({
    request_id: `travel-replan-fast-${Math.random().toString(16).slice(2, 12)}`,
    city_id: 'beijing',
    route_mode: request.route_mode,
    goal: request.goal,
    resolved_area: selectedArea,
    persona_id: request.persona_id,
    evidence_summary: {
      data_root: DATA_ROOT,
      poi_count: data.plannerEntities.length,
      review_feature_count: data.reviewAggregates.length,
      static_data_notice: 'UGC and opening hours come from local static data, not realtime queue or realtime operations.',
    },
    request_snapshot: request,
    day_count: 1,
    daily_itinerary: [{ day: 1, title: 'Day 1', area: selectedArea, theme: 'Incremental replan patch', proposal: proposals[0] }],
    proposals,
    generation_metrics: {
      ...slaMetrics,
      commute_edges_loaded: commuteEdges.loaded,
      commute_edge_count: commuteEdges.edge_count,
      commute_edge_loaded_at: commuteEdges.loaded_at,
      commute_edge_load_elapsed_ms: commuteEdgeLoadElapsedMs,
      commute_edge_error: commuteEdges.error,
      ...transferSummary,
      replan_acceleration_hit: params.replanAccelerationHit,
      route_corpus_poi_hint_elapsed_ms: params.routeCorpusPoiHintElapsedMs,
      route_corpus_poi_hint_used: params.replanAccelerationHit === 'route_corpus_poi_hint',
      acceleration_layers: {
        incremental_replan_patch: true,
        replan_request_snapshot_cache: params.replanAccelerationHit === 'request_snapshot',
        route_corpus_poi_hint: params.replanAccelerationHit === 'route_corpus_poi_hint',
        memory_data_cache: true,
        commute_edge_cache: commuteEdges.loaded,
      },
    },
    route_patch_summary: routePatchSummary,
    replan_metadata: {
      source_request_applied: true,
      adjustment_text: params.adjustmentText,
      locked_poi_ids: request.must_include_poi_ids,
      route_patch_summary: routePatchSummary,
      applied_adjustments: [
        'Incremental replan patch reused the previous route skeleton.',
        fastPath === 'incremental_named_add' ? 'Named stop inserted without full route regeneration.' : null,
        fastPath === 'incremental_generic_add' ? 'Generic additional stop inserted near the existing route.' : null,
        fastPath === 'incremental_target_replace' ? 'Target stop replaced without rebuilding unrelated stops.' : null,
        params.replanAccelerationHit === 'request_snapshot' ? 'Added stop resolved from previous route acceleration cache.' : null,
        params.replanAccelerationHit === 'route_corpus_poi_hint' ? 'Added stop resolved from precomputed route corpus POI hints.' : null,
      ].filter(Boolean),
    },
  });
  return response;
}

function buildAccelerationSummary(params: {
  intent?: TravelQueryIntent | null;
  fastPath: string;
  routeCorpusUsed?: boolean;
  databaseRecallUsed?: boolean;
  wikiRetrievalUsed?: boolean;
  planningAdviceUsed?: boolean;
  sqlResults?: Array<Record<string, any>>;
}) {
  const sqlResults = Array.isArray(params.sqlResults) ? params.sqlResults : [];
  const sqlCacheHit = sqlResults.length > 0 && sqlResults.every((item) => Boolean(item.cache_hit));
  const parser = params.intent?.parser || null;
  const semanticFastPath = parser === 'dictionary'
    || (parser === 'cache' && (params.intent?.notes || []).some((note) => /Dictionary parser|Common semantic fast path/i.test(String(note))));
  return {
    enabled: true,
    fast_path: params.fastPath,
    layers: {
      common_semantic_fast_path: semanticFastPath,
      intent_cache: Boolean(params.intent?.cache_hit),
      route_corpus: Boolean(params.routeCorpusUsed),
      sql_result_cache: sqlCacheHit,
      memory_data_cache: true,
      wiki_cache: Boolean(params.wikiRetrievalUsed),
    },
    parser,
    cache_hit: Boolean(params.intent?.cache_hit) || sqlCacheHit || Boolean(params.routeCorpusUsed),
    cache_layers_hit: [
      params.intent?.cache_hit ? 'intent' : null,
      params.routeCorpusUsed ? 'route_corpus' : null,
      sqlCacheHit ? 'sql_result' : null,
      'memory_data',
      params.wikiRetrievalUsed ? 'wiki' : null,
    ].filter(Boolean),
    notes: [
      semanticFastPath ? '常见语义已由本地规则解析，跳过阻塞式 LLM 意图解析。' : null,
      params.routeCorpusUsed ? '命中预生成路线库，直接返回可执行路线候选。' : '未命中路线库时使用本地 POI/UGC planner 即时规划。',
      sqlCacheHit ? 'SQL 候选查询命中内存结果缓存。' : null,
    ].filter(Boolean),
  };
}

function buildKnowledgeGuidanceSummary(params: {
  wikiRetrieval?: Record<string, any> | null;
  planningAdvice?: TravelPlanningAdvice | null;
  routeDraft?: TravelRouteDraft | null;
  llmRerank?: Record<string, any> | null;
}) {
  const hits = Array.isArray(params.wikiRetrieval?.hits) ? params.wikiRetrieval?.hits : [];
  const linkedEntities = Array.isArray(params.wikiRetrieval?.linked_entities) ? params.wikiRetrieval?.linked_entities : [];
  return {
    enabled: Boolean(params.wikiRetrieval || params.planningAdvice || params.routeDraft || params.llmRerank),
    knowledge_base: {
      type: 'local_obsidian_llm_wiki',
      retrieval_used: Boolean(params.wikiRetrieval),
      hit_count: hits.length,
      linked_entity_count: linkedEntities.length,
      top_titles: hits.slice(0, 5).map((hit: Record<string, any>) => hit.title).filter(Boolean),
    },
    guidance_steps: {
      planning_advice_used: Boolean(params.planningAdvice),
      planning_advice_source: params.planningAdvice?.source || null,
      route_draft_used: Boolean(params.routeDraft),
      route_draft_source: params.routeDraft?.draft_source || null,
      rerank_used: Boolean(params.llmRerank),
      rerank_source: params.llmRerank?.rerank_source || null,
    },
    user_visible_summary: hits.length
      ? '已用本地知识库召回区域/主题/POI 证据，并将其用于参数建议、草案生成或方案重排。'
      : '本次主链路以本地路线库/规划器为主，知识库作为可选增强层。',
  };
}

function candidatePool(data: TravelData, request: TravelPlanningRequest): Poi[] {
  const source = request.route_mode === 'culture' ? data.culturePois : data.plannerEntities.length ? data.plannerEntities : data.mixedPois;
  const requiredById = (request.must_include_poi_ids || [])
    .map((id) => data.poiById.get(String(id)))
    .filter(Boolean) as Poi[];
  const fallbackPois = unresolvedMustIncludeNames(data, request).map((name, index) => buildFallbackPoiForIncludeName(name, request, index + 1));
  return uniqueByName([...requiredById, ...fallbackPois, ...source]).filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat));
}

function preparePlanningRequest(data: TravelData, payload: Partial<TravelPlanningRequest>): TravelPlanningRequest {
  const request = normalizeRequest(payload);
  request.must_include_poi_ids = Array.from(new Set([
    ...(request.must_include_poi_ids || []),
    ...resolveMustIncludePoiIds(data, request),
  ]));
  if (requestHasNamedInclude(request)) {
    request.max_total_pois = Math.max(Number(request.max_total_pois || 4), new Set(request.must_include_poi_ids || []).size, 3);
  }
  return request;
}

function buildProposal(params: {
  request: TravelPlanningRequest;
  strategy: Strategy;
  selectedArea: string;
  candidates: Poi[];
  data: TravelData;
  commuteEdges?: CommuteEdgeIndex;
}) {
  const { request, strategy, selectedArea, candidates, data, commuteEdges } = params;
  const requestedMustCount = new Set(request.must_include_poi_ids || []).size + unresolvedMustIncludeNames(data, request).length;
  const targetCount = Math.max(3, request.max_total_pois || 4, requestedMustCount);
  const sameArea = candidates.filter((item) => item.area === selectedArea || item.district === selectedArea);
  const sameAreaDiversified = uniqueByAttractionGroup(uniqueByName(sameArea));
  const basePool = sameAreaDiversified.length >= targetCount
    ? sameAreaDiversified
    : uniqueByAttractionGroup(uniqueByName(candidates));
  const effectiveMustNames = unresolvedMustIncludeNames(data, request);
  const requiredCandidates = candidates.filter((item) => {
    return (request.must_include_poi_ids || []).includes(item.poi_id)
      || effectiveMustNames.some((name) => matchesIncludeName(item, String(name)));
  });
  const familyCultureCandidates = request.persona_id === 'family_kids' || request.preference_signals?.family
    ? candidates
      .filter((item) => !isFoodPoi(item))
      .filter((item) => /family|children|儿童|亲子|孩子|科技|自然|museum|博物馆|博物院|science|nature|low_stress|scene:family/.test(poiText(item)))
      .sort((a, b) => scorePoi(b, request, strategy, data) - scorePoi(a, request, strategy, data))
      .slice(0, 12)
    : [];
  const stableFamilyCultureCandidates = request.persona_id === 'family_kids' || request.preference_signals?.family
    ? uniqueByName([...candidates, ...allPlannerPois(data)])
      .filter(isFamilyCulturePoi)
      .sort((a, b) => familyAssertionPriority(b) - familyAssertionPriority(a) || familyCulturePriority(b) - familyCulturePriority(a))
      .slice(0, 12)
    : [];
  const pool = uniqueByName([...requiredCandidates, ...basePool, ...familyCultureCandidates, ...stableFamilyCultureCandidates]);
  const excludedIds = new Set(request.exclude_poi_ids || []);
  const excludedNames = (request.exclude_names || []).map(normalizePoiName);
  const available = pool.filter((item) => {
    if (excludedIds.has(item.poi_id)) return false;
    return !matchesExcludedName(item, request.exclude_names || []);
  }).filter((item) => {
    const required = (request.must_include_poi_ids || []).includes(item.poi_id)
      || effectiveMustNames.some((name) => matchesIncludeName(item, String(name)));
    if (required) return true;
    return !String(item.poi_id).startsWith('fixture_') && !String(item.name).includes('未知');
  });

  const recommendable = available.filter(isRecommendablePoi);
  const scopedRecommendable = request.preference_signals?.indoor && request.route_mode === 'culture'
    ? recommendable.filter((item) => isIndoorCulturePoi(item) || (request.must_include_poi_ids || []).includes(item.poi_id))
    : recommendable;
  const food = scopedRecommendable.filter(isFoodPoi);
  const lunchFood = food.filter(isLunchPoi);
  const culture = scopedRecommendable.filter((item) => !isFoodPoi(item));
  const isRealLunchCandidate = (item: Poi) => isFoodPoi(item) && (item.meal_type === 'meal' || item.meal_type === 'snack' || item.is_lunch_suitable) && !isCoffeePoi(item);
  const ranked = (items: Poi[]) => [...items]
    .filter((item) => request.max_budget === null || request.max_budget === undefined || Number(item.avg_cost || 0) <= Number(request.max_budget))
    .sort((a, b) => scorePoi(b, request, strategy, data) - scorePoi(a, request, strategy, data));
  const foodRanked = (items: Poi[]) => ranked(items).sort((a, b) => {
    if (request.preference_signals?.coffee) {
      const aCoffee = isCoffeePoi(a) ? 1 : 0;
      const bCoffee = isCoffeePoi(b) ? 1 : 0;
      if (aCoffee !== bCoffee) return bCoffee - aCoffee;
    }
    if (request.preference_signals?.lunch) {
      const quality = mealQualityScore(b) - mealQualityScore(a);
      if (quality !== 0) return quality;
    }
    if (request.preference_signals?.quality_food) {
      const rating = Number(b.rating || 0) - Number(a.rating || 0);
      if (rating !== 0) return rating;
      const reviews = Number(b.review_count || 0) - Number(a.review_count || 0);
      if (reviews !== 0) return reviews;
    }
    return 0;
  });

  let selected: Poi[] = [];
  if (request.route_mode === 'mixed') {
    const budgetLimit = request.max_budget === null || request.max_budget === undefined ? null : Number(request.max_budget);
    const mealPool = request.preference_signals?.formal_meal
      ? food.filter(isRealLunchCandidate)
      : request.preference_signals?.lunch
        ? lunchFood.filter((item) => !isCoffeePoi(item))
        : food;
    const lockedCultureCost = available
      .filter((item) => (request.must_include_poi_ids || []).includes(item.poi_id) && !isFoodPoi(item))
      .reduce((sum, item) => sum + Number(item.avg_cost || 0), 0);
    const foodBudgetCap = budgetLimit === null ? null : Math.max(0, budgetLimit - lockedCultureCost);
    const requiredFood = foodRanked(mealPool).find((item) => (request.must_include_poi_ids || []).includes(item.poi_id))
      ?? foodRanked(food).find((item) => (request.must_include_poi_ids || []).includes(item.poi_id));
    const foodCandidates = budgetLimit
      ? foodRanked(mealPool).filter((item) => Number(item.avg_cost || 0) <= Math.max(0, foodBudgetCap ?? budgetLimit))
      : foodRanked(mealPool);
    const selectedFood = requiredFood ?? foodCandidates[0] ?? foodRanked(mealPool)[0] ?? foodRanked(food.filter((item) => !isCoffeePoi(item)))[0] ?? foodRanked(food)[0];
    if (selectedFood) selected.push(selectedFood);
    const remainingBudget = budgetLimit === null ? null : Math.max(0, budgetLimit - Number(selectedFood?.avg_cost || 0));
    const cultureSlots = Math.max(2, targetCount - 1);
    const cultureBudgetCap = remainingBudget === null ? null : Math.max(0, remainingBudget / cultureSlots);
    const cultureDurationCap = request.persona_id === 'family_kids' || request.persona_id === 'senior_relaxed' ? 120 : 100;
    const cultureCandidates = ranked(culture)
      .filter((item) => Number(item.suggested_duration_min || 90) <= cultureDurationCap)
      .filter((item) => cultureBudgetCap === null || Number(item.avg_cost || 0) <= cultureBudgetCap);
    selected.push(...cultureCandidates.slice(0, cultureSlots));
    if (selected.length < targetCount) {
      selected.push(...ranked(culture).filter((item) => !selected.some((chosen) => chosen.poi_id === item.poi_id)).slice(0, targetCount - selected.length));
    }
  } else {
    selected.push(...ranked(culture).slice(0, targetCount));
  }

  const mustIds = new Set(request.must_include_poi_ids || []);
  const mustNames = new Set(effectiveMustNames);
  const requiredFoodIds = new Set(candidates
    .filter((item) => mustIds.has(item.poi_id) && isFoodPoi(item))
    .map((item) => item.poi_id));
  for (const required of candidates.filter((item) => {
    if (excludedIds.has(item.poi_id) || matchesExcludedName(item, request.exclude_names || [])) return false;
    const normalizedName = normalizePoiName(item.name);
    const matchesMustName = [...mustNames].some((name) => {
      const normalizedMust = normalizePoiName(name);
      return Boolean(normalizedMust && (normalizedName.includes(normalizedMust) || normalizedMust.includes(normalizedName)));
    });
    return mustIds.has(item.poi_id) || matchesMustName;
  })) {
    if (!selected.some((item) => item.poi_id === required.poi_id)) selected.unshift(required);
  }
  if (request.route_mode === 'mixed' && requiredFoodIds.size > 0) {
    selected = selected.filter((item) => !isFoodPoi(item) || requiredFoodIds.has(item.poi_id));
  }

  const selectedUnique = uniqueByName(selected);
  const isMustSelected = (item: Poi) => {
    const normalizedName = normalizePoiName(item.name);
    return mustIds.has(item.poi_id) || [...mustNames].some((name) => {
      const normalizedMust = normalizePoiName(name);
      return Boolean(normalizedMust && (normalizedName.includes(normalizedMust) || normalizedMust.includes(normalizedName)));
    });
  };
  const mustSelected = selectedUnique.filter(isMustSelected);
  const optionalSelected = selectedUnique.filter((item) => !isMustSelected(item));
  let ordered = orderNearest([...mustSelected, ...optionalSelected].slice(0, targetCount), commuteEdges);
  if (request.route_mode === 'mixed' && !ordered.some(isFoodPoi)) {
    const fallbackFood = foodRanked(
      request.preference_signals?.lunch || request.preference_signals?.formal_meal
        ? food.filter(isRealLunchCandidate)
        : food,
    )[0] ?? foodRanked(food)[0];
    if (fallbackFood) {
      const cultureOnly = ordered.filter((item) => !isFoodPoi(item));
      ordered = [fallbackFood, ...cultureOnly].slice(0, Math.max(3, targetCount));
    }
  }
  if (request.route_order_poi_ids?.length) {
    const byId = new Map(ordered.map((item) => [item.poi_id, item]));
    const remaining = ordered.filter((item) => !request.route_order_poi_ids?.includes(item.poi_id));
    const templateOrdered: Poi[] = [];
    for (const id of request.route_order_poi_ids) {
      const exact = byId.get(id);
      if (exact) {
        templateOrdered.push(exact);
      } else {
        const replacement = remaining.shift();
        if (replacement) templateOrdered.push(replacement);
      }
    }
    ordered = [...templateOrdered, ...remaining].slice(0, targetCount);
  }
  if (request.persona_id === 'family_kids' || request.preference_signals?.family) {
    const familyPattern = /family|children|儿童|亲子|孩子|科技|自然|museum|博物馆|博物院|science|nature|low_stress|scene:family/;
    if (!ordered.some((item) => !isFoodPoi(item) && familyPattern.test(poiText(item)))) {
      const familyReplacement = ranked(candidates.filter((item) => !isFoodPoi(item) && familyPattern.test(poiText(item))))
        .find((item) => !ordered.some((chosen) => chosen.poi_id === item.poi_id));
      if (familyReplacement) {
        const replaceIndex = ordered.findIndex((item, index) => index > 0 && !isFoodPoi(item));
        if (replaceIndex >= 0) ordered[replaceIndex] = familyReplacement;
      }
    }
  }
  if ((request.persona_id === 'family_kids' || request.preference_signals?.family) && !ordered.some(isStrongFamilyCulturePoi)) {
    const stableFamilyReplacement = uniqueByName([...candidates, ...allPlannerPois(data)])
      .filter(isFamilyCulturePoi)
      .filter((item) => familyAssertionPriority(item) >= 3)
      .filter(isRecommendablePoi)
      .sort((a, b) => familyAssertionPriority(b) - familyAssertionPriority(a) || familyCulturePriority(b) - familyCulturePriority(a))
      .find((item) => !ordered.some((chosen) => chosen.poi_id === item.poi_id));
    if (stableFamilyReplacement) {
      const replaceIndex = ordered.findIndex((item, index) => index > 0 && !isFoodPoi(item) && !isMustSelected(item));
      if (replaceIndex >= 0) ordered[replaceIndex] = stableFamilyReplacement;
      else if (ordered.length < targetCount) ordered.push(stableFamilyReplacement);
    }
  }
  if (request.route_mode === 'mixed') {
    const cultureStops = ordered.filter((item) => !isFoodPoi(item));
    const foodStops = ordered
      .filter(isFoodPoi)
      .sort((a, b) => {
        if (!request.preference_signals?.snack) return 0;
        const aSnack = isSnackOrTeaPoi(a) ? 1 : 0;
        const bSnack = isSnackOrTeaPoi(b) ? 1 : 0;
        return aSnack - bSnack;
      });
    const lunchFirst = request.preference_signals?.lunch && (parseMinutes(request.start_time) ?? 9 * 60) >= 11 * 60;
    ordered = lunchFirst ? [...foodStops, ...cultureStops] : [...cultureStops.slice(0, 1), ...foodStops, ...cultureStops.slice(1)];
  }

  const start = parseMinutes(request.start_time) ?? 9 * 60;
  let cursor = start;
  let totalTransfer = 0;
  let totalDistance = 0;
  let commuteEdgesUsed = 0;
  let coordinateEstimatesUsed = 0;
  let unknownHours = 0;
  let hasOpeningConflict = false;
  const stops = ordered.map((item, index) => {
    let transfer = 0;
    let distance = 0;
    let transferSource: TransferSource = 'coordinate_estimate';
    let transferMode: string | null = null;
    let transferProvider: string | null = null;
    let transferDurationSeconds: number | null = null;
    let transferCount: number | null = null;
    if (index > 0) {
      const estimate = estimateTransfer(ordered[index - 1], item, commuteEdges);
      distance = estimate.meters;
      transfer = estimate.minutes;
      transferSource = estimate.source;
      transferMode = estimate.mode;
      transferProvider = estimate.provider;
      transferDurationSeconds = estimate.duration_s;
      transferCount = estimate.transfer_count;
      if (estimate.source === 'commute_edge') commuteEdgesUsed += 1;
      else coordinateEstimatesUsed += 1;
      totalTransfer += transfer;
      totalDistance += distance;
      cursor += transfer;
    }
    const isFoodStop = isFoodPoi(item);
    const isSnackStop = Boolean(request.preference_signals?.snack && isSnackOrTeaPoi(item));
    if (request.preference_signals?.lunch && isFoodStop && !isSnackStop && cursor < 11 * 60 + 30) cursor = 11 * 60 + 30;
    if (isSnackStop && cursor < 13 * 60) cursor = 13 * 60;
    const arrival = cursor;
    const rawStay = Number(item.suggested_duration_min || 90);
    const shortRoute = Boolean(request.max_duration_min && request.max_duration_min <= 270);
    const relaxedLowWalk = request.walk_preference === 'low' && request.pace === 'relaxed';
    const stay = request.max_duration_min && request.max_duration_min <= 180
      ? Math.min(rawStay, isFoodStop ? 35 : 45)
      : shortRoute
        ? Math.min(rawStay, isFoodStop ? 50 : relaxedLowWalk ? 55 : 65)
        : rawStay;
    const open = parseMinutes(item.open_time);
    const close = parseMinutes(item.close_time);
    let openingStatus = 'unknown';
    if (open !== null && close !== null) {
      openingStatus = arrival >= open && arrival + stay <= close ? 'ok' : 'conflict';
      if (openingStatus === 'conflict') hasOpeningConflict = true;
    } else {
      unknownHours += 1;
    }
    cursor += stay;
    return {
      poi_id: item.poi_id,
      name: item.name,
      poi_type: isFoodStop ? 'food' : 'culture',
      category: item.category || 'unknown',
      meal_type: item.meal_type || 'non_food',
      is_lunch_suitable: Boolean(item.is_lunch_suitable),
      is_coffee_stop: Boolean(item.is_coffee_stop),
      area: item.area || item.district || '未知',
      district: item.district || '未知',
      address: item.address || '',
      planning_tags: Array.isArray(item.planning_tags) ? item.planning_tags : [],
      evidence_tags: Array.isArray(item.evidence_tags) ? item.evidence_tags : [],
      arrival_time: minutesToTime(arrival),
      departure_time: minutesToTime(cursor),
      stay_minutes: stay,
      transfer_from_previous_minutes: transfer,
      transfer_from_previous_meters: Math.round(distance),
      transfer_source: index > 0 ? transferSource : null,
      transfer_mode: transferMode,
      transfer_provider: transferProvider,
      transfer_duration_s: transferDurationSeconds,
      transfer_count: transferCount,
      estimated_cost: Number(item.avg_cost || 0),
      meal_slot: isSnackStop ? 'snack' : request.preference_signals?.lunch && isFoodStop ? 'lunch' : null,
      rating: Number(item.rating || 0),
      opening_status: openingStatus,
      opening_hours_note: openingStatus === 'unknown' ? '本地数据未覆盖完整营业时间。' : openingStatus === 'ok' ? '按本地营业时间估算可访问。' : '按本地营业时间估算存在冲突。',
      recommendation_reason: buildReason(item, request, data),
      evidence_summary: buildStopEvidence(item, data),
    };
  });

  const totalBudget = stops.reduce((sum, item) => sum + item.estimated_cost, 0);
  const totalVisit = stops.reduce((sum, item) => sum + item.stay_minutes, 0);
  const totalDuration = cursor - start;
  const foodCount = stops.filter((item) => item.poi_type === 'food').length;
  const cultureCount = stops.length - foodCount;
  const categorySatisfied = request.route_mode === 'mixed' ? foodCount >= 1 && cultureCount >= 2 : cultureCount >= 3;
  const transferSummary = {
    commute_edges_used: commuteEdgesUsed,
    coordinate_estimates_used: coordinateEstimatesUsed,
    commute_edge_hit_rate: ordered.length > 1 ? Number((commuteEdgesUsed / (ordered.length - 1)).toFixed(3)) : 0,
  };
  const risks = [
    request.max_budget !== null && request.max_budget !== undefined && totalBudget > Number(request.max_budget) ? `Estimated budget ${totalBudget} exceeds requested ${request.max_budget}.` : null,
    request.max_duration_min !== null && request.max_duration_min !== undefined && totalDuration > Number(request.max_duration_min) ? `Estimated route duration is ${totalDuration} minutes, above requested ${request.max_duration_min}.` : null,
    hasOpeningConflict ? 'One or more stops may conflict with local opening-hours data.' : null,
    unknownHours ? `${unknownHours} stop(s) do not have complete opening-hours coverage in the local dataset.` : null,
    commuteEdgesUsed > 0
      ? 'Walking distance and transfer time use local commute-edge data when available, not real-time navigation.'
      : 'Walking distance and transfer time are local coordinate estimates, not real-time navigation.',
  ].filter(Boolean).map(translateRisk);
  const title = strategy === 'balanced' ? '均衡体验方案' : strategy === 'budget' ? '预算优先方案' : '效率优先方案';
  const constraintReport = buildConstraintReport({ request, stops, totalBudget, totalDuration, totalDistance, categorySatisfied });
  return {
    proposal_id: `${strategy}-${Math.random().toString(16).slice(2, 10)}`,
    strategy,
    display_title: title,
    title,
    summary: `${selectedArea} area, ${stops.length} POIs, about ${totalDuration} min, ${totalBudget} CNY.`,
    ordered_poi_ids: stops.map((item) => item.poi_id),
    ordered_poi_names: stops.map((item) => item.name),
    pois: stops,
    total_budget_estimate: totalBudget,
    total_transfer_minutes: totalTransfer,
    total_walking_distance_m: Math.round(totalDistance),
    transfer_source_summary: transferSummary,
    total_visit_duration_min: totalVisit,
    total_route_duration_min: totalDuration,
    travel_time_confidence: 'estimated',
    budget_summary: { max_budget: request.max_budget, within_budget: request.max_budget === null || request.max_budget === undefined || totalBudget <= Number(request.max_budget), total_budget_estimate: totalBudget },
    duration_summary: { max_duration_min: request.max_duration_min, within_duration: request.max_duration_min === null || request.max_duration_min === undefined || totalDuration <= Number(request.max_duration_min), total_route_duration_min: totalDuration, total_visit_duration_min: totalVisit, total_transfer_minutes: totalTransfer },
    category_coverage_summary: {
      route_mode: request.route_mode,
      food_count: foodCount,
      culture_or_entertainment_count: cultureCount,
      required_food_count: request.route_mode === 'mixed' ? 1 : 0,
      required_culture_or_entertainment_count: request.route_mode === 'mixed' ? 2 : 3,
      satisfies_coverage: categorySatisfied,
    },
    quality_summary: buildQualitySummary({ request, stops, totalBudget, totalDuration, totalDistance, transferSummary, categorySatisfied }),
    constraint_report: constraintReport,
    constraint_resolution: buildConstraintResolution(constraintReport),
    opening_hours_check: { has_conflict: hasOpeningConflict, unknown_hours_count: unknownHours },
    risks,
  };
}

export async function travelHealth() {
  const data = await loadTravelData();
  const commuteEdges = await loadCommuteEdges();
  const databaseSkipped = process.env.SKIP_DB_SYNC === '1';
  return {
    status: 'ok',
    city_id: 'beijing',
    data_root: DATA_ROOT,
    data_source: 'local_json',
    data_loaded: Boolean(dataLoadedAt),
    data_loaded_at: dataLoadedAt,
    data_load_elapsed_ms: dataLoadElapsedMs,
    poi_count: data.plannerEntities.length,
    database: {
      required_for_planning: false,
      skipped: databaseSkipped,
      mode: databaseSkipped ? 'local_demo_no_postgres' : 'postgres_optional',
      note: databaseSkipped
        ? 'POI/UGC planning uses local JSON files; chat persistence is best-effort and does not require Postgres.'
        : 'POI/UGC planning uses local JSON files; Postgres is only used for platform persistence when available.',
    },
    cache: {
      poi_index_ready: data.poiById.size > 0,
      review_index_ready: data.reviewAggregatesByPoiId.size > 0,
      commute_edge_index_ready: commuteEdges.loaded && commuteEdges.edge_count > 0,
    },
    commute: {
      enabled: process.env.TRAVELPILOT_COMMUTE_ENABLED !== '0',
      loaded: commuteEdges.loaded,
      edge_count: commuteEdges.edge_count,
      loaded_at: commuteEdges.loaded_at,
      load_elapsed_ms: commuteEdgeLoadElapsedMs,
      error: commuteEdges.error,
      source_table: 'travel_commute_edges',
    },
    counts: {
      culture_pois: data.culturePois.length,
      mixed_pois: data.mixedPois.length,
      planner_entities: data.plannerEntities.length,
      review_aggregates: data.reviewAggregates.length,
      review_pois: new Set(data.reviewAggregates.map((item) => item.poi_id)).size,
    },
    limitations: [
      'No realtime map, realtime queue, or external review API is used.',
      'Transfer time prefers local travel_commute_edges when available, then falls back to coordinate estimates.',
      'Postgres is required only for commute-edge and query-plan knowledge-base enhancements; JSON planner fallback remains available.',
    ],
  };
}

export async function travelOptions() {
  const data = await loadTravelData();
  const areas = new Map<string, { culture_count: number; mixed_count: number }>();
  for (const item of data.culturePois) {
    const area = item.area || item.district;
    if (!area || area === '未知') continue;
    areas.set(area, { culture_count: (areas.get(area)?.culture_count || 0) + 1, mixed_count: areas.get(area)?.mixed_count || 0 });
  }
  for (const item of data.plannerEntities) {
    const area = item.area || item.district;
    if (!area || area === '未知') continue;
    areas.set(area, { culture_count: areas.get(area)?.culture_count || 0, mixed_count: (areas.get(area)?.mixed_count || 0) + 1 });
  }
  return {
    city_id: 'beijing',
    route_modes: [
      { value: 'culture', label: '北京文化路线' },
      { value: 'mixed', label: '餐饮 + 文化混排' },
    ],
    areas: [...areas.entries()].map(([value, counts]) => ({ value, label: value, ...counts })).sort((a, b) => b.mixed_count - a.mixed_count).slice(0, 30),
    walk_options: [
      { value: 'low', label: '少走路' },
      { value: 'medium', label: '可接受步行' },
      { value: 'high', label: '愿意多走' },
    ],
    demo_goals: [
      '前门附近玩4小时，中午吃饭，想吃好但不想排队，预算200以内，少走路',
      '故宫附近安排4小时文化路线，少走路，预算100以内，不吃饭',
      '预算降到100，保留第一个点，重新规划',
    ],
  };
}

export async function listTravelPois(query: { area?: string | null; route_mode?: RouteMode; limit?: number }) {
  const data = await loadTravelData();
  const request = normalizeRequest({ route_mode: query.route_mode || 'mixed', area: query.area || null });
  const items = candidatePool(data, request)
    .filter((item) => !query.area || item.area === query.area || item.district === query.area)
    .slice(0, Math.min(Number(query.limit || 100), 500));
  return { items, count: items.length, data_root: DATA_ROOT };
}

export async function getTravelEvidence(poiId: string) {
  const data = await loadTravelData();
  const poi = data.poiById.get(poiId);
  return {
    poi,
    evidence_summary: poi ? buildStopEvidence(poi, data) : null,
    claims: data.reviewAggregatesByPoiId.get(poiId) || [],
  };
}

export async function getTravelCandidateBuckets(payload: Partial<TravelPlanningRequest>): Promise<TravelCandidateBuckets> {
  const data = await loadTravelData();
  const request = preparePlanningRequest(data, payload);
  const pool = candidatePool(data, request);
  const resolvedArea = selectArea(request, pool);
  const scoped = pool
    .filter((item) => item.area === resolvedArea || item.district === resolvedArea)
    .filter(isRecommendablePoi)
    .sort((a, b) => scorePoi(b, request, 'balanced', data) - scorePoi(a, request, 'balanced', data));
  const cultureCandidates = scoped.filter((item) => !isFoodPoi(item)).slice(0, 24);
  const mealCandidates = scoped.filter((item) => isFoodPoi(item) && (item.meal_type === 'meal' || item.meal_type === 'snack')).slice(0, 18);
  const snackCandidates = scoped.filter((item) => isSnackOrTeaPoi(item)).slice(0, 18);
  const indoorCandidates = scoped.filter((item) => isIndoorCulturePoi(item)).slice(0, 18);
  return {
    request,
    resolved_area: resolvedArea,
    cultureCandidates,
    mealCandidates,
    snackCandidates,
    indoorCandidates,
  };
}

export async function parseGoalToTravelRequest(goal: string, defaults?: Partial<TravelPlanningRequest>) {
  const parsed = applyStableGoalIntentPatch(goal, parseGoal(goal, defaults || {}));
  return {
    parsed_request: parsed,
    parser_confidence: goal.trim() ? 0.86 : 0.2,
    parser_notes: ['Local rules parsed area, budget, duration, meal, queue, and walking preferences.'],
    parser_correction_hints: goal.trim() ? [] : ['Please describe area, duration, budget, or preference.'],
  };
}

async function executeDatabaseRecall(intent: TravelQueryIntent | null) {
  if (!intent || intent.missing_fields.length > 0) {
    return {
      query_plan: intent ? buildTravelQueryPlan(intent) : null,
      results: [],
      used: false,
    };
  }
  const queryPlan = buildTravelQueryPlan(intent);
  try {
    const results = await executeTravelQueryPlan(queryPlan);
    return {
      query_plan: queryPlan,
      results,
      used: true,
    };
  } catch (error) {
    return {
      query_plan: queryPlan,
      results: [],
      used: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function reorderProposalsByIds(proposals: Array<Record<string, any>>, rankedIds: string[]) {
  const byId = new Map(proposals.map((proposal) => [String(proposal.proposal_id), proposal]));
  const ordered = rankedIds.map((id) => byId.get(String(id))).filter(Boolean) as Array<Record<string, any>>;
  const leftovers = proposals.filter((proposal) => !rankedIds.includes(String(proposal.proposal_id)));
  return [...ordered, ...leftovers];
}

async function enrichPlanningResponseWithLlm(params: {
  rawText: string | null;
  planningResponse: Record<string, any>;
  plannerRequest: TravelPlanningRequest;
  intent?: TravelQueryIntent | null;
  planningAdvice?: TravelPlanningAdvice | null;
  routeDraft?: TravelRouteDraft | null;
  routeDraftValidation?: TravelRouteDraftValidation | null;
  parsedMeta?: { parser_confidence?: number; parser_notes?: string[]; parser_correction_hints?: string[] } | null;
}) {
  const intent =
    params.intent
    ?? (params.rawText
      ? await parseTravelQueryIntentMiniMaxPreferred(params.rawText).catch(() => null)
      : null);

  const wikiRetrieval = params.rawText
    ? await retrieveTravelWiki({ rawText: params.rawText, intent, limit: 8 }).catch(() => null)
    : null;
  const databaseRecall = await executeDatabaseRecall(intent);
  const proposals = Array.isArray(params.planningResponse.proposals) ? params.planningResponse.proposals : [];
  const llmRerank = intent ? await rerankTravelProposals({ intent, proposals, wikiRetrieval }) : null;
  const reorderedProposals = llmRerank ? reorderProposalsByIds(proposals, llmRerank.ranked_proposal_ids) : proposals;
  const finalSelectedProposalId = llmRerank?.primary_proposal_id || reorderedProposals[0]?.proposal_id || null;
  const acceleration = buildAccelerationSummary({
    intent,
    fastPath: params.planningResponse.generation_metrics?.sla?.fast_path || 'local_planner',
    routeCorpusUsed: Boolean(params.planningResponse.generation_metrics?.route_corpus_used),
    databaseRecallUsed: databaseRecall.used,
    wikiRetrievalUsed: Boolean(wikiRetrieval),
    planningAdviceUsed: Boolean(params.planningAdvice),
    sqlResults: databaseRecall.results as Array<Record<string, any>>,
  });
  const knowledgeGuidance = buildKnowledgeGuidanceSummary({
    wikiRetrieval,
    planningAdvice: params.planningAdvice || null,
    routeDraft: params.routeDraft || null,
    llmRerank,
  });

  return {
    parsed_request: params.plannerRequest,
    parser_confidence: params.parsedMeta?.parser_confidence ?? intent?.confidence ?? 0.86,
    parser_notes: params.parsedMeta?.parser_notes ?? intent?.notes ?? ['MiniMax-first intent parsing completed.'],
    parser_correction_hints: params.parsedMeta?.parser_correction_hints ?? (intent?.missing_fields.length ? [`Please clarify ${intent.missing_fields.join(', ')}.`] : []),
    intent,
    planning_response: {
      ...params.planningResponse,
      proposals: reorderedProposals,
      query_plan: databaseRecall.query_plan,
      query_results: databaseRecall.results,
      wiki_retrieval: wikiRetrieval,
      planning_advice: params.planningAdvice || null,
      route_draft: params.routeDraft || null,
      validator_result: params.routeDraftValidation || null,
      repair_actions: params.routeDraftValidation?.repair_actions || [],
      llm_rerank: llmRerank,
      acceleration,
      knowledge_guidance: knowledgeGuidance,
      final_selected_proposal_id: finalSelectedProposalId,
      natural_language_explanation: llmRerank?.final_user_explanation || reorderedProposals[0]?.summary || '',
      generation_metrics: {
        ...(params.planningResponse.generation_metrics || {}),
        wiki_retrieval_used: Boolean(wikiRetrieval),
        wiki_retrieval_elapsed_ms: wikiRetrieval?.elapsed_ms || 0,
        database_recall_used: databaseRecall.used,
        llm_rerank_used: Boolean(llmRerank?.llm_used),
        llm_rerank_elapsed_ms: llmRerank?.elapsed_ms || 0,
        llm_rerank_fallback_reason: llmRerank?.fallback_reason || null,
        planning_advice_used: Boolean(params.planningAdvice),
        planning_advice_source: params.planningAdvice?.source || null,
        planning_advice_llm_used: Boolean(params.planningAdvice?.llm_used),
        planning_advice_elapsed_ms: params.planningAdvice?.elapsed_ms || 0,
        planning_advice_fallback_reason: params.planningAdvice?.fallback_reason || null,
        route_draft_used: Boolean(params.routeDraft),
        draft_source: params.routeDraft?.draft_source || null,
        draft_llm_used: Boolean(params.routeDraft?.llm_used),
        draft_llm_attempted: Boolean(params.routeDraft?.llm_attempted),
        draft_llm_error: params.routeDraft?.llm_error || null,
        draft_elapsed_ms: params.routeDraft?.elapsed_ms || 0,
        draft_fallback_reason: params.routeDraft?.fallback_reason || null,
        validator_status: params.routeDraftValidation?.status || null,
        acceleration_layers: acceleration.layers,
        knowledge_guidance_used: knowledgeGuidance.enabled,
        knowledge_hit_count: knowledgeGuidance.knowledge_base.hit_count,
      },
    },
  };
}

export async function planTravelRoute(payload: Partial<TravelPlanningRequest>) {
  const started = performance.now();
  const data = await loadTravelData();
  const commuteEdges = await loadCommuteEdges();
  const request = preparePlanningRequest(data, payload);
  const pool = candidatePool(data, request);
  const selectedArea = selectArea(request, pool);
  const proposals = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => buildProposal({ request, strategy, selectedArea, candidates: pool, data, commuteEdges }));
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(request.day_count || 1)));
  const popularAreas = selectPopularAreas(pool, dayCount + 2).filter((area) => area !== selectedArea);
  const dayAreas = request.area ? [selectedArea, ...popularAreas] : selectPopularAreas(pool, dayCount);
  const usedDailyPoiIds = new Set<string>();
  const dailyItinerary = Array.from({ length: dayCount }, (_, index) => {
    const dayArea = dayAreas[index % dayAreas.length] || selectedArea;
    const dayRequest = preparePlanningRequest(data, {
      ...request,
      area: dayArea,
      max_total_pois: request.max_duration_min && request.max_duration_min >= 420 ? 4 : request.max_total_pois,
      must_include_names: index === 0 ? request.must_include_names : [],
      must_include_poi_ids: index === 0 ? request.must_include_poi_ids : [],
      route_order_poi_ids: index === 0 ? request.route_order_poi_ids : [],
      exclude_poi_ids: [...(request.exclude_poi_ids || []), ...Array.from(usedDailyPoiIds)],
    });
    const dayProposal = buildProposal({ request: dayRequest, strategy: index % 3 === 0 ? 'balanced' : index % 3 === 1 ? 'efficient' : 'budget', selectedArea: dayArea, candidates: pool, data, commuteEdges });
    for (const id of dayProposal.ordered_poi_ids || []) usedDailyPoiIds.add(String(id));
    return { day: index + 1, title: `第 ${index + 1} 天`, area: dayArea, theme: index === 0 ? '核心目的地体验' : index === 1 ? '餐饮与文化扩展' : '顺路补充与轻松探索', proposal: dayProposal };
  });
  const transferSummary = summarizeProposalTransfers(proposals);
  const slaMetrics = buildSlaMetrics({ started, fastPath: 'local_planner', llmBlocking: false });
  const baseResponse = {
    request_id: `travel-${Math.random().toString(16).slice(2, 12)}`,
    city_id: 'beijing',
    route_mode: request.route_mode,
    goal: request.goal,
    resolved_area: selectedArea,
    persona_id: request.persona_id,
    evidence_summary: {
      data_root: DATA_ROOT,
      poi_count: data.plannerEntities.length,
      review_feature_count: data.reviewAggregates.length,
      static_data_notice: 'UGC and opening hours come from local static data, not realtime queue or realtime operations.',
    },
    request_snapshot: request,
    day_count: dayCount,
    daily_itinerary: dailyItinerary,
    proposals,
    generation_metrics: {
      ...slaMetrics,
      commute_edges_loaded: commuteEdges.loaded,
      commute_edge_count: commuteEdges.edge_count,
      commute_edge_loaded_at: commuteEdges.loaded_at,
      commute_edge_load_elapsed_ms: commuteEdgeLoadElapsedMs,
      commute_edge_error: commuteEdges.error,
      ...transferSummary,
    },
    replan_metadata: null,
  };
  if (payload.goal) {
    const enriched = await enrichPlanningResponseWithLlm({
      rawText: String(payload.goal || ''),
      planningResponse: baseResponse,
      plannerRequest: request,
    });
    return enriched.planning_response;
  }
  return baseResponse;
}

export async function buildStaticTravelRoute(payload: Partial<TravelPlanningRequest>) {
  const started = performance.now();
  const data = await loadTravelData();
  const commuteEdges = await loadCommuteEdges();
  const request = normalizeRequest(payload);
  const pool = candidatePool(data, request);
  const selectedArea = selectArea(request, pool);
  const proposals = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => buildProposal({ request, strategy, selectedArea, candidates: pool, data, commuteEdges }));
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(request.day_count || 1)));
  const popularAreas = selectPopularAreas(pool, dayCount + 2).filter((area) => area !== selectedArea);
  const dayAreas = request.area ? [selectedArea, ...popularAreas] : selectPopularAreas(pool, dayCount);
  const usedDailyPoiIds = new Set<string>();
  const dailyItinerary = Array.from({ length: dayCount }, (_, index) => {
    const dayArea = dayAreas[index % dayAreas.length] || selectedArea;
    const dayRequest = normalizeRequest({
      ...request,
      area: dayArea,
      max_total_pois: request.max_duration_min && request.max_duration_min >= 420 ? 4 : request.max_total_pois,
      must_include_names: index === 0 ? request.must_include_names : [],
      must_include_poi_ids: index === 0 ? request.must_include_poi_ids : [],
      route_order_poi_ids: index === 0 ? request.route_order_poi_ids : [],
      exclude_poi_ids: [...(request.exclude_poi_ids || []), ...Array.from(usedDailyPoiIds)],
    });
    const dayProposal = buildProposal({ request: dayRequest, strategy: index % 3 === 0 ? 'balanced' : index % 3 === 1 ? 'efficient' : 'budget', selectedArea: dayArea, candidates: pool, data, commuteEdges });
    for (const id of dayProposal.ordered_poi_ids || []) usedDailyPoiIds.add(String(id));
    return { day: index + 1, title: `第 ${index + 1} 天`, area: dayArea, theme: index === 0 ? '核心目的地体验' : index === 1 ? '餐饮与文化扩展' : '顺路补充与轻松探索', proposal: dayProposal };
  });
  const transferSummary = summarizeProposalTransfers(proposals);
  const slaMetrics = buildSlaMetrics({ started, fastPath: 'static_local_planner', llmBlocking: false });
  return {
    request_id: `travel-static-${Math.random().toString(16).slice(2, 12)}`,
    city_id: 'beijing',
    route_mode: request.route_mode,
    goal: request.goal,
    resolved_area: selectedArea,
    persona_id: request.persona_id,
    evidence_summary: {
      data_root: DATA_ROOT,
      poi_count: data.plannerEntities.length,
      review_feature_count: data.reviewAggregates.length,
      static_data_notice: 'UGC and opening hours come from local static data, not realtime queue or realtime operations.',
    },
    request_snapshot: request,
    day_count: dayCount,
    daily_itinerary: dailyItinerary,
    proposals,
    generation_metrics: {
      ...slaMetrics,
      commute_edges_loaded: commuteEdges.loaded,
      commute_edge_count: commuteEdges.edge_count,
      commute_edge_loaded_at: commuteEdges.loaded_at,
      commute_edge_load_elapsed_ms: commuteEdgeLoadElapsedMs,
      commute_edge_error: commuteEdges.error,
      ...transferSummary,
    },
    replan_metadata: null,
  };
}

export async function parseAndPlanTravel(payload: { goal?: string; defaults?: Partial<TravelPlanningRequest>; debug_route_draft_mock?: string }) {
  const rawGoal = String(payload.goal || '');
  const intent = await parseTravelQueryIntentMiniMaxPreferred(rawGoal).catch(() => null);
  if (intent && intent.missing_fields.length === 0 && !payload.debug_route_draft_mock) {
    const corpusRequest = applyStableGoalIntentPatch(rawGoal, normalizeRequest({
      ...payload.defaults,
      ...intentToPlannerLikeRequest(intent),
      goal: rawGoal,
    }));
    const shouldUseStaticFastPath = corpusRequest.persona_id === 'classic_first_timer'
      && !corpusRequest.preference_signals?.family
      && !corpusRequest.preference_signals?.senior
      && !corpusRequest.preference_signals?.couple;
    if (shouldUseStaticFastPath) {
      const corpusMatch = await findPrecomputedTravelRoutes(intent);
      if (corpusMatch.matched) {
        return buildPlanningResponseFromRouteCorpus({ intent, match: corpusMatch, request: corpusRequest });
      }
      const planningResponse = applyReplanAccelerationCache(await buildStaticTravelRoute(corpusRequest));
    const databaseRecall = await executeDatabaseRecall(intent);
    const acceleration = buildAccelerationSummary({
      intent,
      fastPath: planningResponse.generation_metrics?.sla?.fast_path || 'static_local_planner',
      routeCorpusUsed: false,
      databaseRecallUsed: databaseRecall.used,
      sqlResults: databaseRecall.results as Array<Record<string, any>>,
    });
    const knowledgeGuidance = buildKnowledgeGuidanceSummary({});
    return {
      parsed_request: corpusRequest,
      parser_confidence: intent.confidence,
      parser_notes: [
        ...intent.notes,
        '未命中预生成路线库，已使用本地 POI/UGC 数据即时生成路线。',
      ],
      parser_correction_hints: [],
      intent,
      planning_response: {
        ...planningResponse,
        query_plan: databaseRecall.query_plan,
        query_results: databaseRecall.results,
        acceleration,
        knowledge_guidance: knowledgeGuidance,
        route_corpus_match: {
          used: false,
          source: 'none',
          elapsed_ms: corpusMatch.elapsed_ms,
          reason: corpusMatch.reason,
        },
        natural_language_explanation: planningResponse.proposals?.[0]?.summary || '已根据本地北京旅行数据生成路线。',
        generation_metrics: {
          ...(planningResponse.generation_metrics || {}),
          route_corpus_used: false,
          database_recall_used: databaseRecall.used,
          llm_role: 'semantic_intent_only',
          acceleration_layers: acceleration.layers,
          knowledge_guidance_used: knowledgeGuidance.enabled,
        },
      },
    };
  }
  }
  const preWikiRetrieval = rawGoal
    ? await retrieveTravelWiki({ rawText: rawGoal, intent, limit: 8 }).catch(() => null)
    : null;
  const parsed = intent
    ? {
        parsed_request: applyStableGoalIntentPatch(rawGoal, normalizeRequest({
          ...payload.defaults,
          ...intentToPlannerLikeRequest(intent),
          goal: rawGoal,
        })),
        parser_confidence: intent.confidence,
        parser_notes: intent.notes,
        parser_correction_hints: intent.missing_fields.length ? [`Please clarify ${intent.missing_fields.join(', ')}.`] : [],
      }
    : await parseGoalToTravelRequest(rawGoal, payload.defaults);
  const stableParsedRequest = applyStableGoalIntentPatch(rawGoal, parsed.parsed_request);
  const planningAdvice = intent
    ? await getTravelPlanningAdvice({ intent, request: stableParsedRequest, wikiRetrieval: preWikiRetrieval }).catch(() => null)
    : null;
  const advisedRequest = applyStableGoalIntentPatch(rawGoal, applyTravelPlanningAdvice(stableParsedRequest, planningAdvice));
  const draftResult = intent
    ? await getTravelCandidateBuckets(advisedRequest)
      .then((buckets) => generateTravelRouteDraft({
        intent,
        request: advisedRequest,
        buckets,
        wikiRetrieval: preWikiRetrieval,
        mockResponse: payload.debug_route_draft_mock,
      }))
      .catch(() => null)
    : null;
  const draftOrderedIds = draftResult?.validation.status === 'rejected' ? [] : draftResult?.validation.valid_ordered_poi_ids || [];
  const allowDraftOrder = draftOrderedIds.length >= 3 && advisedRequest.persona_id === 'classic_first_timer';
  const draftConstrainedRequest = applyStableGoalIntentPatch(rawGoal, allowDraftOrder
    ? normalizeRequest({
        ...advisedRequest,
        must_include_poi_ids: Array.from(new Set([...(advisedRequest.must_include_poi_ids || []), ...draftOrderedIds])),
        route_order_poi_ids: draftOrderedIds,
        max_total_pois: Math.max(Number(advisedRequest.max_total_pois || 3), draftOrderedIds.length),
      })
    : advisedRequest);
  const planningRequest = { ...draftConstrainedRequest };
  delete planningRequest.goal;
  const planningResponse = applyReplanAccelerationCache(await planTravelRoute(planningRequest));
  return await enrichPlanningResponseWithLlm({
    rawText: rawGoal,
    planningResponse,
    plannerRequest: draftConstrainedRequest,
    intent,
    planningAdvice,
    routeDraft: draftResult?.draft || null,
    routeDraftValidation: draftResult?.validation || null,
    parsedMeta: {
      parser_confidence: parsed.parser_confidence,
      parser_notes: parsed.parser_notes,
      parser_correction_hints: parsed.parser_correction_hints,
    },
  });
}

async function stableReplanTravelRoute(payload: {
  previous_request?: Partial<TravelPlanningRequest>;
  selected_proposal?: Record<string, any> & { ordered_poi_ids?: string[]; ordered_poi_names?: string[] };
  adjustment_text?: string;
  locked_poi_ids?: string[];
}) {
  const started = performance.now();
  const data = await loadTravelData();
  const previous = normalizeRequest(payload.previous_request || {});
  const adjustmentText = payload.adjustment_text || '';
  const llmIntent = await parseTravelQueryIntent(adjustmentText, { timeoutMs: Number(process.env.TRAVELPILOT_REPLAN_INTENT_TIMEOUT_MS || 3500) }).catch(() => null);
  const parsed = mergeIntentIntoReplanRequest(parseGoal(adjustmentText, previous), llmIntent);
  const selectedIds = payload.selected_proposal?.ordered_poi_ids || [];
  const selectedFirst = selectedIds[0];
  const selectedPois = selectedPoisFromProposal(data, payload.selected_proposal);
  const selectedNames = (payload.selected_proposal?.ordered_poi_names || selectedPois.map((poi) => poi.name)).map(String);
  let targetedReplacementIndex = stableTargetedReplacementIndex(adjustmentText, selectedIds.length) ?? parseTargetedReplacementIndex(adjustmentText, selectedIds.length);
  let targetedReplacementId = targetedReplacementIndex === null ? null : selectedIds[targetedReplacementIndex];
  const excludedNames = (parsed.exclude_names || []).map(normalizePoiName);
  const excludedIds = new Set(parsed.exclude_poi_ids || []);
  const locked = [...(payload.locked_poi_ids || [])];
  const explicitFoodChangeText = /(\u53bb\u6389|\u5220\u9664|\u4e0d\u8981|\u4e0d\u53bb|\u6362\u6389|\u6362\u6210|\u6362\u4e00\u4e2a|\u66ff\u6362|\u6539\u6210).*(\u5403\u996d|\u9910\u996e|\u5348\u9910|\u5348\u996d|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u4e0b\u5348\u8336)|(\u5403\u996d|\u9910\u996e|\u5348\u9910|\u5348\u996d|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u4e0b\u5348\u8336).*(\u53bb\u6389|\u5220\u9664|\u4e0d\u8981|\u4e0d\u53bb|\u6362\u6389|\u6362\u6210|\u6362\u4e00\u4e2a|\u66ff\u6362|\u6539\u6210)/.test(adjustmentText);
  const explicitFoodAdditionText = /(\u518d\u52a0|\u52a0\u4e00\u4e2a|\u6dfb\u52a0|\u589e\u52a0|\u987a\u8def).*(\u5403\u996d|\u9910\u996e|\u5348\u9910|\u5348\u996d|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u4e0b\u5348\u8336)|(\u5403\u996d|\u9910\u996e|\u5348\u9910|\u5348\u996d|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u4e0b\u5348\u8336).*(\u518d\u52a0|\u52a0\u4e00\u4e2a|\u6dfb\u52a0|\u589e\u52a0|\u987a\u8def)/.test(adjustmentText);
  const wantsFoodChange = (explicitFoodChangeText || explicitFoodAdditionText) && (stableWantsFoodChange(adjustmentText) || adjustmentWantsFoodChange(adjustmentText));
  const hasExplicitFoodTerm = /(\u5403\u996d|\u9910\u996e|\u5348\u9910|\u5348\u996d|\u9910\u5385|\u996d\u5e97|\u5c0f\u5403|\u5496\u5561|\u4e0b\u5348\u8336|\u6b63\u9910|\u7f8e\u98df)/.test(adjustmentText);
  const rawWantsSnack = stableWantsSnack(adjustmentText) || adjustmentWantsSnack(adjustmentText);
  const wantsFormalMeal = stableWantsFormalMeal(adjustmentText);
  const preserveFood = stablePreservesFood(adjustmentText);
  const effectiveFoodChange = wantsFoodChange && hasExplicitFoodTerm && !preserveFood;
  const wantsSnack = rawWantsSnack && hasExplicitFoodTerm;
  const preserveCulture = stablePreservesCulture(adjustmentText);
  const preserveOthers = stablePreservesOthers(adjustmentText) || /鍘熸潵鐨勭偣閮戒繚鐣|鍏朵粬鍦版柟涓嶅彉|鍏朵粬涓嶅彉/.test(adjustmentText);
  const wantsFreshPlan = stableWantsFreshPlan(adjustmentText) || adjustmentWantsFreshPlan(adjustmentText);
  const wantsIndoor = stableWantsIndoor(adjustmentText) || /瀹ゅ唴|缇庢湳棣唡鍗氱墿棣唡鑹烘湳涓績|灞曡棣?/.test(adjustmentText);
  const wantsAddStop = stableWantsAddStop(adjustmentText) || /鍐嶅姞|鍔犱竴涓|娣诲姞|澧炲姞|椤鸿矾|鏀捐繘鍘|鎺掕繘鍘/.test(adjustmentText);
  const wantsGenericAttraction = stableWantsGenericAttraction(adjustmentText)
    || /鏅偣|缇庢湳棣唡鍗氱墿棣唡鑹烘湳涓績|灞曡棣?/.test(adjustmentText)
    || (wantsAddStop && (preserveOthers || preserveCulture) && !hasExplicitFoodTerm);
  const unreadableAdjustmentText = Boolean(adjustmentText) && !/[\u4e00-\u9fffA-Za-z0-9]/.test(adjustmentText);
  if (preserveFood && targetedReplacementIndex !== null && isFoodPoi(selectedPois[targetedReplacementIndex])) {
    const replacementIndex = selectedPois.map((poi, index) => ({ poi, index })).reverse().find(({ poi }) => !isFoodPoi(poi))?.index;
    if (replacementIndex !== undefined) {
      targetedReplacementIndex = replacementIndex;
      targetedReplacementId = selectedIds[targetedReplacementIndex];
    }
  }
  let replanAccelerationHit: 'request_snapshot' | 'route_corpus_poi_hint' | null = null;
  let routeCorpusPoiHintElapsedMs = 0;
  parsed.must_include_poi_ids = Array.from(new Set([
    ...(parsed.must_include_poi_ids || []),
    ...resolveIdsFromReplanAccelerationCache(parsed),
    ...resolveMustIncludePoiIds(data, parsed),
  ]));
  if (resolveIdsFromReplanAccelerationCache(parsed).length > 0) {
    replanAccelerationHit = 'request_snapshot';
  }
  if (!replanAccelerationHit && (parsed.must_include_names || []).length > 0) {
    const corpusHints = await findRouteCorpusPoiHints(parsed.must_include_names || [], 16).catch(() => null);
    routeCorpusPoiHintElapsedMs = Number(corpusHints?.elapsed_ms || 0);
    if (corpusHints?.matched) {
      const bestCorpusHints = filterBestCorpusHintsForNames(corpusHints.hints, parsed.must_include_names || []);
      parsed.replan_acceleration_cache = mergeReplanAccelerationCaches(
        parsed.replan_acceleration_cache,
        replanCacheFromCorpusHints(bestCorpusHints.length ? bestCorpusHints : corpusHints.hints.slice(0, 1)),
      );
      const corpusHintIds = resolveIdsFromReplanAccelerationCache(parsed);
      if (corpusHintIds.length > 0) {
        parsed.must_include_poi_ids = Array.from(new Set([...(parsed.must_include_poi_ids || []), ...corpusHintIds]));
        replanAccelerationHit = 'route_corpus_poi_hint';
      }
    }
  }
  const wantsNamedInclude = requestHasNamedInclude(parsed);

  if (selectedFirst && /(\u4fdd\u7559|\u9501\u5b9a|\u4e0d\u8981\u5220)/.test(adjustmentText)) locked.push(selectedFirst);
  if (preserveFood) {
    for (const poi of selectedPois.filter(isFoodPoi)) locked.push(poi.poi_id);
  }
  if (targetedReplacementId) excludedIds.add(targetedReplacementId);
  for (const poi of selectedPois) {
    if (matchesExcludedName(poi, excludedNames)) excludedIds.add(poi.poi_id);
  }
  if (effectiveFoodChange) {
    for (const poi of selectedPois.filter(isFoodPoi)) excludedIds.add(poi.poi_id);
  }
  const selectedFoodIds = new Set(selectedPois.filter(isFoodPoi).map((poi) => poi.poi_id));
  parsed.must_include_poi_ids = (parsed.must_include_poi_ids || []).filter((id) => {
    if (excludedIds.has(id)) return false;
    return !(effectiveFoodChange && selectedFoodIds.has(id));
  });
  for (const poi of selectedPois) {
    const targetPoi = targetedReplacementId === poi.poi_id;
    const shouldLockFood = preserveFood && isFoodPoi(poi);
    const shouldLockCulture = preserveCulture && !isFoodPoi(poi);
    const shouldLockOther = (preserveOthers || wantsAddStop) && !targetPoi;
    if (targetPoi || wantsFreshPlan) continue;
    if (shouldLockFood || shouldLockCulture || shouldLockOther || shouldPreservePoiOnReplan({ poi, adjustmentText, excludedNames, excludedIds })) locked.push(poi.poi_id);
  }
  parsed.exclude_poi_ids = Array.from(new Set([...(parsed.exclude_poi_ids || []), ...excludedIds]));
  if (effectiveFoodChange || wantsSnack || wantsFormalMeal) {
    parsed.route_mode = 'mixed';
    parsed.preference_signals = {
      ...(parsed.preference_signals || {}),
      lunch: true,
      coffee: effectiveFoodChange ? false : Boolean(parsed.preference_signals?.coffee),
      formal_meal: wantsFormalMeal,
      snack: wantsSnack,
    };
  }
  if (wantsIndoor) {
    parsed.preference_signals = { ...(parsed.preference_signals || {}), indoor: true };
  }
  if (wantsNamedInclude) {
    locked.push(...(parsed.must_include_poi_ids || []));
    parsed.max_total_pois = Math.min(8, Math.max(Number(previous.max_total_pois || selectedIds.length || 3), selectedIds.length + 1));
    parsed.area = null;
  }
  if (unreadableAdjustmentText && wantsNamedInclude && selectedIds.length > 0 && !hasExplicitFoodTerm) {
    parsed.route_mode = previous.route_mode === 'culture' ? 'culture' : parsed.route_mode;
    parsed.max_total_pois = Math.max(3, selectedIds.length);
    parsed.preference_signals = {
      ...(parsed.preference_signals || {}),
      lunch: false,
      coffee: false,
      snack: false,
      formal_meal: false,
    };
  }
  if (wantsAddStop && selectedIds.length > 0) {
    parsed.max_total_pois = Math.min(8, Math.max(Number(previous.max_total_pois || selectedIds.length), selectedIds.length) + 1);
    const explicitFoodAdd = effectiveFoodChange || wantsSnack;
    const additionalStop = selectAdditionalStop({
      data,
      request: parsed,
      selectedPois,
      excludedIds,
      excludedNames: parsed.exclude_names || [],
      wantsFood: explicitFoodAdd,
      wantsSnack,
      wantsIndoor,
    });
    if (additionalStop && (wantsGenericAttraction || wantsIndoor || explicitFoodAdd) && !wantsNamedInclude) {
      locked.push(additionalStop.poi_id);
    }
  }
  parsed.must_include_poi_ids = Array.from(new Set([...(parsed.must_include_poi_ids || []), ...locked]))
    .filter((id) => !excludedIds.has(id));
  const orderedLockedIds = [
    ...selectedIds.filter((id) => parsed.must_include_poi_ids?.includes(id)),
    ...(parsed.must_include_poi_ids || []).filter((id) => !selectedIds.includes(id)),
  ];
  parsed.route_order_poi_ids = wantsAddStop || wantsNamedInclude
    ? orderedLockedIds
    : selectedIds.filter((id) => targetedReplacementId === id || parsed.must_include_poi_ids?.includes(id));

  const incrementalPatch = await buildIncrementalReplanPatch({
    started,
    previous,
    parsed,
    selectedProposal: payload.selected_proposal,
    selectedPois,
    selectedIds: selectedIds.map(String),
    selectedNames,
    adjustmentText,
    excludedIds,
    replanAccelerationHit,
    routeCorpusPoiHintElapsedMs,
    targetReplacementIndex: targetedReplacementIndex,
    wantsNamedInclude,
    wantsAddStop,
    wantsIndoor,
    wantsGenericAttraction,
    wantsFoodChange: effectiveFoodChange,
    wantsSnack,
  });
  if (incrementalPatch) {
    return {
      ...incrementalPatch,
      generation_metrics: {
        ...(incrementalPatch.generation_metrics || {}),
        replan_intent_parser: llmIntent?.parser || 'rule_fallback',
        replan_intent_llm_used: Boolean(llmIntent?.llm_used),
        replan_intent_llm_attempted: Boolean(llmIntent?.llm_attempted),
        replan_intent_llm_elapsed_ms: llmIntent?.llm_elapsed_ms || 0,
        replan_intent_confidence: llmIntent?.confidence ?? null,
        replan_intent_action: llmIntent?.replan_action || null,
        replan_intent_must_include_names: llmIntent?.must_include_names || [],
        replan_intent_exclude_names: llmIntent?.exclude_names || [],
        replan_intent_error: llmIntent?.llm_error || null,
        acceleration_layers: {
          ...(incrementalPatch.generation_metrics?.acceleration_layers || {}),
          replan_llm_semantic_patch: Boolean(llmIntent?.llm_used),
          replan_semantic_cache: Boolean(llmIntent?.cache_hit),
        },
      },
    };
  }

  let result = applyReplanAccelerationCache(await planTravelRoute(parsed));
  const leakedNames = result.proposals
    .flatMap((proposal) => proposal.pois || [])
    .filter((poi: Pick<Poi, 'poi_id' | 'name'>) => excludedIds.has(poi.poi_id) || matchesExcludedName(poi, parsed.exclude_names || []))
    .map((poi: Pick<Poi, 'name'>) => poi.name);
  if (leakedNames.length > 0) {
    parsed.must_include_poi_ids = (parsed.must_include_poi_ids || []).filter((id) => !excludedIds.has(id));
    parsed.route_order_poi_ids = selectedIds.filter((id) => parsed.must_include_poi_ids?.includes(id));
    result = applyReplanAccelerationCache(await planTravelRoute(parsed));
  }
  const afterIds = new Set((result.proposals?.[0]?.ordered_poi_ids || []).map(String));
  const expectedPreservedIds = selectedIds
    .map(String)
    .filter((id) => id !== String(targetedReplacementId || '') && !excludedIds.has(id));
  const preserveIntentViolated = !wantsFreshPlan
    && (preserveOthers || preserveCulture || wantsAddStop || targetedReplacementId)
    && expectedPreservedIds.some((id) => !afterIds.has(id));
  const routePatchSummary = buildRoutePatchSummary({
    beforeIds: selectedIds.map(String),
    beforeNames: selectedNames,
    afterProposal: result.proposals?.[0] || null,
    adjustmentText,
  });
  return {
    ...result,
    generation_metrics: {
      ...(result.generation_metrics || {}),
      replan_acceleration_hit: replanAccelerationHit,
      replan_intent_parser: llmIntent?.parser || 'rule_fallback',
      replan_intent_llm_used: Boolean(llmIntent?.llm_used),
      replan_intent_llm_attempted: Boolean(llmIntent?.llm_attempted),
      replan_intent_llm_elapsed_ms: llmIntent?.llm_elapsed_ms || 0,
      replan_intent_confidence: llmIntent?.confidence ?? null,
      replan_intent_action: llmIntent?.replan_action || null,
      replan_intent_must_include_names: llmIntent?.must_include_names || [],
      replan_intent_exclude_names: llmIntent?.exclude_names || [],
      replan_intent_error: llmIntent?.llm_error || null,
      route_corpus_poi_hint_elapsed_ms: routeCorpusPoiHintElapsedMs,
      route_corpus_poi_hint_used: replanAccelerationHit === 'route_corpus_poi_hint',
      acceleration_layers: {
        ...(result.generation_metrics?.acceleration_layers || {}),
        replan_llm_semantic_patch: Boolean(llmIntent?.llm_used),
        replan_semantic_cache: Boolean(llmIntent?.cache_hit),
        replan_request_snapshot_cache: replanAccelerationHit === 'request_snapshot',
        route_corpus_poi_hint: replanAccelerationHit === 'route_corpus_poi_hint',
      },
    },
    route_patch_summary: routePatchSummary,
    replan_metadata: {
      source_request_applied: Boolean(payload.previous_request),
      adjustment_text: payload.adjustment_text || '',
      locked_poi_ids: parsed.must_include_poi_ids,
      route_patch_summary: routePatchSummary,
      applied_adjustments: [
        parsed.max_budget !== previous.max_budget ? 'Budget constraint updated.' : null,
        parsed.walk_preference !== previous.walk_preference ? 'Walking preference updated.' : null,
        parsed.max_duration_min !== previous.max_duration_min ? 'Duration constraint updated.' : null,
        targetedReplacementId ? `Targeted replacement applied for stop ${Number(targetedReplacementIndex) + 1}.` : null,
        parsed.must_include_poi_ids?.length ? 'Unchanged POIs preserved for local replan.' : null,
        llmIntent?.llm_used ? 'MiniMax semantic patch applied before deterministic route validation.' : null,
        llmIntent?.llm_attempted && !llmIntent.llm_used ? 'MiniMax semantic patch unavailable; deterministic parser handled replan.' : null,
        effectiveFoodChange ? 'Food stop replacement applied without rebuilding the full route.' : null,
        wantsAddStop ? 'Additional stop inserted near the existing route.' : null,
        replanAccelerationHit === 'request_snapshot' ? 'Added stop resolved from previous route acceleration cache.' : null,
        replanAccelerationHit === 'route_corpus_poi_hint' ? 'Added stop resolved from precomputed route corpus POI hints.' : null,
        leakedNames.length ? 'Excluded POI leak prevented by final guard.' : null,
        preserveIntentViolated ? 'Incremental route skeleton fallback was unavailable; global planner may have changed preserved stops.' : null,
      ].filter(Boolean),
    },
  };
}

export async function replanTravelRoute(payload: {
  previous_request?: Partial<TravelPlanningRequest>;
  selected_proposal?: { ordered_poi_ids?: string[]; ordered_poi_names?: string[] };
  adjustment_text?: string;
  locked_poi_ids?: string[];
}) {
  return stableReplanTravelRoute(payload);
  /*
  const data = await loadTravelData();
  const previous = normalizeRequest(payload.previous_request || {});
  const parsed = parseGoal(payload.adjustment_text || '', previous);
  const locked = [...(payload.locked_poi_ids || [])];
  const selectedFirst = payload.selected_proposal?.ordered_poi_ids?.[0];
  const adjustmentText = payload.adjustment_text || '';
  if (selectedFirst && /保留|锁定|不要删/.test(adjustmentText)) locked.push(selectedFirst);
  const selectedIds = payload.selected_proposal?.ordered_poi_ids || [];
  const targetedReplacementIndex = parseTargetedReplacementIndex(adjustmentText, selectedIds.length);
  const targetedReplacementId = targetedReplacementIndex === null ? null : selectedIds[targetedReplacementIndex];
  const selectedPois = selectedIds
    .map((id) => data.plannerEntities.find((item) => item.poi_id === id) || data.culturePois.find((item) => item.poi_id === id) || data.mixedPois.find((item) => item.poi_id === id))
    .filter(Boolean) as Poi[];
  const excludedNames = (parsed.exclude_names || []).map(normalizePoiName);
  const excludedIds = new Set(parsed.exclude_poi_ids || []);
  if (targetedReplacementId) excludedIds.add(targetedReplacementId);
  for (const poi of selectedPois) {
    if (matchesExcludedName(poi, excludedNames)) {
      excludedIds.add(poi.poi_id);
    }
  }
  if (adjustmentWantsFoodChange(adjustmentText)) {
    for (const poi of selectedPois.filter(isFoodPoi)) excludedIds.add(poi.poi_id);
  }
  const selectedFoodIds = new Set(selectedPois.filter(isFoodPoi).map((poi) => poi.poi_id));
  parsed.must_include_poi_ids = (parsed.must_include_poi_ids || []).filter((id) => {
    if (excludedIds.has(id)) return false;
    return !(adjustmentWantsFoodChange(adjustmentText) && selectedFoodIds.has(id));
  });
  for (const poi of selectedPois) {
    if (shouldPreservePoiOnReplan({ poi, adjustmentText, excludedNames, excludedIds })) locked.push(poi.poi_id);
  }
  parsed.exclude_poi_ids = Array.from(new Set([...(parsed.exclude_poi_ids || []), ...excludedIds]));
  if (adjustmentWantsSnack(adjustmentText)) {
    parsed.preference_signals = { ...(parsed.preference_signals || {}), lunch: true, coffee: false };
  }
  parsed.must_include_poi_ids = Array.from(new Set([...(parsed.must_include_poi_ids || []), ...locked]))
    .filter((id) => !excludedIds.has(id));
  let result = await planTravelRoute(parsed);
  const leakedNames = result.proposals
    .flatMap((proposal) => proposal.pois || [])
    .filter((poi: Pick<Poi, 'poi_id' | 'name'>) => excludedIds.has(poi.poi_id) || matchesExcludedName(poi, parsed.exclude_names || []))
    .map((poi: Pick<Poi, 'name'>) => poi.name);
  if (leakedNames.length > 0) {
    parsed.must_include_poi_ids = (parsed.must_include_poi_ids || []).filter((id) => !excludedIds.has(id));
    result = await planTravelRoute(parsed);
  }
  return {
    ...result,
    replan_metadata: {
      source_request_applied: Boolean(payload.previous_request),
      adjustment_text: payload.adjustment_text || '',
      locked_poi_ids: parsed.must_include_poi_ids,
      applied_adjustments: [
        parsed.max_budget !== previous.max_budget ? 'Budget constraint updated.' : null,
        parsed.walk_preference !== previous.walk_preference ? 'Walking preference updated.' : null,
        parsed.max_duration_min !== previous.max_duration_min ? 'Duration constraint updated.' : null,
        targetedReplacementId ? `Targeted replacement applied for stop ${Number(targetedReplacementIndex) + 1}.` : null,
        parsed.must_include_poi_ids?.length ? 'Unchanged POIs preserved for local replan.' : null,
        adjustmentWantsFoodChange(adjustmentText) ? 'Food stop replacement applied without rebuilding the full route.' : null,
        leakedNames.length ? 'Excluded POI leak prevented by final guard.' : null,
      ].filter(Boolean),
    },
  };
  */
}
