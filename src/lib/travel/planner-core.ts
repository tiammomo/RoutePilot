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
import { BEIJING_AREA_ANCHORS, BEIJING_CLASSIC_DAY_AREAS, LANDMARK_FIXTURE_POIS, MAX_TRIP_DAYS } from '@/lib/travel/constants';
import { anchorForName, classicPoiIdsForArea, landmarkPoiIdsForName } from '@/lib/travel/itinerary-rules';
import {
  attractionGroupKey,
  foodPreferenceScore,
  isClassicBackbonePoi,
  isCoffeePoi,
  isFoodPoi,
  isIndoorCulturePoi,
  isLunchPoi,
  isOverSpecificCulturePoi,
  isRecommendablePoi,
  isSnackOrTeaPoi,
  mealQualityScore,
  normalizePoi,
  normalizePoiName,
  poiText,
  semanticKeysForPoiName,
  uniqueByAttractionGroup,
  uniqueByName,
} from '@/lib/travel/poi-model';
import {
  adjustmentWantsFoodChange,
  adjustmentWantsFreshPlan,
  adjustmentWantsSnack,
  parseTargetedReplacementIndex,
  stablePreservesCulture,
  stablePreservesFood,
  stablePreservesOthers,
  stableTargetedReplacementIndex,
  stableWantsAddStop,
  stableWantsFoodChange,
  stableWantsFormalMeal,
  stableWantsFreshPlan,
  stableWantsGenericAttraction,
  stableWantsIndoor,
  stableWantsSnack,
} from '@/lib/travel/replan-intent-rules';
import {
  commutePairKey,
  estimateTransfer,
  meters,
  type CommuteEdge,
  type CommuteEdgeIndex,
  type TransferSource,
} from '@/lib/travel/commute';
import type {
  Poi,
  ReviewAggregate,
  ReviewRecord,
  RouteMode,
  Strategy,
  TravelCandidateBuckets,
  TravelData,
  TravelPlanningRequest,
  TravelReplanAccelerationCache,
  TravelReplanPoiHint,
} from '@/lib/travel/planner-types';

export type {
  Poi,
  ReviewAggregate,
  ReviewRecord,
  RouteMode,
  Strategy,
  TravelCandidateBuckets,
  TravelData,
  TravelPlanningRequest,
  TravelReplanAccelerationCache,
  TravelReplanPoiHint,
} from '@/lib/travel/planner-types';

const DEFAULT_DATA_ROOT = path.resolve(process.cwd(), 'travel-data', 'processed');
const DATA_ROOT = process.env.TRAVELPILOT_DATA_ROOT || DEFAULT_DATA_ROOT;

let dataCache: Promise<TravelData> | null = null;
let dataLoadedAt: string | null = null;
let dataLoadElapsedMs: number | null = null;
let commuteEdgeCache: Promise<CommuteEdgeIndex> | null = null;
let commuteEdgeLoadedAt: string | null = null;
let commuteEdgeLoadElapsedMs: number | null = null;

async function readJsonArray<T>(fileName: string): Promise<T[]> {
  const content = await fs.readFile(path.join(DATA_ROOT, fileName), 'utf8');
  const parsed = JSON.parse(content);
  return Array.isArray(parsed) ? parsed as T[] : [];
}

async function readOptionalJsonArray<T>(fileName: string): Promise<T[]> {
  try {
    return await readJsonArray<T>(fileName);
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code === 'ENOENT') return [];
    throw error;
  }
}

function normalizeUserTravelText(text: string): string {
  return String(text || '').trim().replace(/^[/／\\]+\s*/, '').trim();
}

async function loadTravelData(): Promise<TravelData> {
  if (!dataCache) {
    const started = performance.now();
    dataCache = Promise.all([
      readJsonArray<Poi>('beijing_culture_pois.json'),
      readJsonArray<Poi>('beijing_mixed_category_pois.json'),
      readJsonArray<Poi>('beijing_planner_entities.json'),
      readOptionalJsonArray<Poi>('beijing_hotels.json'),
      readJsonArray<ReviewAggregate>('beijing_poi_feature_aggregates.json'),
      readJsonArray<ReviewRecord>('beijing_review_records.json'),
    ]).then(([culturePois, mixedPois, plannerEntities, hotels, reviewAggregates, reviewRecords]) => {
      const landmarkFixtures = LANDMARK_FIXTURE_POIS.map((item) => normalizePoi({
        ...item,
        planning_tags: [...item.planning_tags],
        evidence_tags: [...item.evidence_tags],
      } as Poi));
      const normalizedCulturePois = [...landmarkFixtures, ...culturePois.map(normalizePoi)];
      const normalizedMixedPois = [...landmarkFixtures, ...mixedPois.map(normalizePoi)];
      const normalizedPlannerEntities = [...landmarkFixtures, ...plannerEntities.map(normalizePoi)];
      const normalizedHotels = hotels.map((item) => normalizePoi({
        ...item,
        category: item.category || 'accommodation',
        poi_type: 'accommodation',
        poi_kind: 'hotel',
        entity_kind: 'hotel',
        poi_subtype: item.poi_subtype || item.raw?.keytag || 'hotel',
        planning_tags: Array.from(new Set([...(Array.isArray(item.planning_tags) ? item.planning_tags : []), 'hotel', 'accommodation'])),
        evidence_tags: Array.from(new Set([...(Array.isArray(item.evidence_tags) ? item.evidence_tags : []), 'amap_hotel'])),
      } as Poi));
      const poiById = new Map<string, Poi>();
      for (const poi of [...normalizedMixedPois, ...normalizedCulturePois, ...normalizedPlannerEntities, ...normalizedHotels]) {
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
        hotels: normalizedHotels,
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
    hotel_count: data.hotels.length,
    cache: {
      poi_index_ready: data.poiById.size > 0,
      review_index_ready: data.reviewAggregatesByPoiId.size > 0,
      commute_edge_index_ready: commuteEdges.loaded && commuteEdges.edge_count > 0,
    },
    commute_edge_count: commuteEdges.edge_count,
    commute_edge_load_elapsed_ms: commuteEdgeLoadElapsedMs,
  };
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
  const normalized = String(name || '').trim();
  if (!normalized) return true;
  if (/^(掉|掉掉|换成|换一个)/.test(normalized)) return true;
  if (/\d+(?:\.\d+)?(?:个)?小时/.test(normalized)) return true;
  if (/^\d+(?:\.\d+)?(?:个)?小时(?:以内|以下)?$/.test(normalized)) return true;
  if (/^(北京|北京市|一个|一个点|一个景点|景点|景区|地点|地方|点|室内点|文化点|娱乐点|文化景点|好玩的|很多地方|几个地方|哪|哪里|去哪|去哪儿|不知道去哪|不知道去哪儿|午餐地点|吃饭地点|餐厅|饭店|吃饭|午餐|午饭|顺路|原来的点都保留|其他地方不变)$/.test(normalized)) return true;
  if (/^(经典)?(?:文化|亲子|情侣|老人|室内|户外|娱乐|餐饮|美食)?(?:路线|景点|点位|地点|地方|安排|结合)$/.test(normalized)) return true;
  if (/^(?:少走路|别太累|轻松一点|不想排队|少排队|预算\d+以内?|预算\d+以下?)$/.test(normalized)) return true;
  return false;
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
  const pattern = /(?:还想去|也想去|有点想去|想去|想玩|想逛|必须去|一定去|顺便去|逛|看|玩|去|加上|添加|增加|安排|能不能(?:帮我)?(?:把)?(?:安排|加上|放进去|排进去)?)([^，,。；;]+)/g;
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

type HotelRecommendation = {
  poi_id: string;
  name: string;
  area?: string | null;
  district?: string | null;
  address?: string | null;
  lng: number;
  lat: number;
  rating?: number | null;
  avg_cost?: number | null;
  poi_subtype?: string | null;
  tags: string[];
  source?: string | null;
  match_reason: string;
  estimated_outbound_minutes?: number | null;
  estimated_return_minutes?: number | null;
};

function hotelMatchScore(hotel: Poi, request: TravelPlanningRequest, selectedArea: string): { score: number; reason: string } {
  const hotelName = normalizePoiName(hotel.name);
  const hotelArea = normalizePoiName(hotel.area || hotel.district || '');
  const requestedNames = (request.accommodation_names || []).map(normalizePoiName).filter(Boolean);
  const areaKey = normalizePoiName(request.area || selectedArea || '');
  let score = 0;
  let reason = 'general_hotel_candidate';

  for (const name of requestedNames) {
    if (!name) continue;
    if (hotelName === name) {
      score += 120;
      reason = 'matched_hotel';
    } else if (hotelName.includes(name) || name.includes(hotelName)) {
      score += 90;
      reason = 'matched_hotel';
    } else if (hotelArea && (hotelArea.includes(name) || name.includes(hotelArea))) {
      score += 70;
      reason = 'matched_area_hotel';
    }
  }
  if (areaKey && hotelArea && (hotelArea.includes(areaKey) || areaKey.includes(hotelArea))) {
    score += 55;
    if (reason === 'general_hotel_candidate') reason = 'matched_area_hotel';
  }
  score += Math.min(20, Math.max(0, Number(hotel.rating || 0) * 4));
  const cost = Number(hotel.avg_cost || 0);
  if (request.max_budget && cost > 0) {
    score += cost <= Number(request.max_budget) ? 8 : -8;
  }
  return { score, reason };
}

function buildHotelRecommendations(params: {
  data: TravelData;
  request: TravelPlanningRequest;
  selectedArea: string;
  stops: Poi[] | Array<Record<string, any>>;
  commuteEdges?: CommuteEdgeIndex;
  limit?: number;
}): HotelRecommendation[] {
  const { data, request, selectedArea, stops, commuteEdges } = params;
  const limit = Math.max(1, Math.min(10, Number(params.limit || 3)));
  const firstStop = stops[0] as Poi | Record<string, any> | undefined;
  const lastStop = stops[stops.length - 1] as Poi | Record<string, any> | undefined;
  const scored = data.hotels
    .map((hotel) => {
      const match = hotelMatchScore(hotel, request, selectedArea);
      return { hotel, ...match };
    })
    .filter((item) => item.score > 0 || !request.preference_signals?.hotel_anchor)
    .sort((a, b) => b.score - a.score || Number(b.hotel.rating || 0) - Number(a.hotel.rating || 0) || Number(a.hotel.avg_cost || 0) - Number(b.hotel.avg_cost || 0));

  return scored.slice(0, limit).map(({ hotel, reason }) => {
    const outbound = firstStop ? estimateTransfer(hotel, firstStop as Poi, commuteEdges) : null;
    const returning = lastStop ? estimateTransfer(lastStop as Poi, hotel, commuteEdges) : null;
    return {
      poi_id: String(hotel.poi_id),
      name: String(hotel.name || ''),
      area: hotel.area || null,
      district: hotel.district || null,
      address: hotel.address || null,
      lng: Number(hotel.lng),
      lat: Number(hotel.lat),
      rating: hotel.rating ?? null,
      avg_cost: hotel.avg_cost ?? null,
      poi_subtype: hotel.poi_subtype || null,
      tags: Array.isArray(hotel.tags) ? hotel.tags.map(String) : [],
      source: hotel.source || null,
      match_reason: reason,
      estimated_outbound_minutes: outbound?.minutes ?? null,
      estimated_return_minutes: returning?.minutes ?? null,
    };
  });
}

function dedupeHotelRecommendations(items: HotelRecommendation[], limit = 5): HotelRecommendation[] {
  const seen = new Set<string>();
  const result: HotelRecommendation[] = [];
  for (const item of items) {
    if (!item.poi_id || seen.has(item.poi_id)) continue;
    seen.add(item.poi_id);
    result.push(item);
    if (result.length >= limit) break;
  }
  return result;
}

function accommodationAnchorForRequest(data: TravelData, request: TravelPlanningRequest, selectedArea: string): (Poi & { location_confidence: string; source_name: string }) | null {
  const requestedName = request.accommodation_names?.[0] || '';
  if (!requestedName && !request.preference_signals?.hotel_anchor) return null;
  const matchedHotel = buildHotelRecommendations({ data, request, selectedArea, stops: [], limit: 1 })[0];
  const hotelPoi = matchedHotel ? data.poiById.get(matchedHotel.poi_id) : null;
  if (hotelPoi) {
    return {
      ...hotelPoi,
      location_confidence: matchedHotel.match_reason,
      source_name: requestedName || hotelPoi.area || selectedArea,
    };
  }
  const directAnchor = requestedName ? anchorForName(requestedName) : null;
  const anchor = directAnchor || anchorForName(request.area) || anchorForName(selectedArea) || { area: selectedArea || '北京', ...BEIJING_AREA_ANCHORS.北京 };
  const displayName = requestedName
    ? (/酒店|宾馆|民宿|住宿/.test(requestedName) ? requestedName : `${requestedName}附近住宿`)
    : `${anchor.area}附近住宿`;
  const base = normalizePoi({
    poi_id: `fixture_accommodation_${normalizePoiName(displayName).slice(0, 32) || 'beijing'}`,
    name: displayName,
    district: anchor.district,
    area: anchor.area,
    category: '住宿',
    poi_type: 'accommodation',
    address: `${anchor.area}周边住宿锚点`,
    lng: anchor.lng,
    lat: anchor.lat,
    rating: 0,
    avg_cost: 0,
    review_count: 0,
    suggested_duration_min: 0,
    planning_tags: ['accommodation_anchor'],
    evidence_tags: ['用户住宿位置锚点', '用于估算每日出发和返回通勤'],
    meal_type: 'invalid',
    is_lunch_suitable: false,
    is_coffee_stop: false,
    is_meal_stop: false,
  } as Poi);
  return {
    ...base,
    location_confidence: directAnchor ? 'area_anchor' : 'fallback_area_anchor',
    source_name: requestedName || anchor.area,
  };
}

function areaForPoi(item?: Pick<Poi, 'area' | 'district' | 'name'> | null): string | null {
  if (!item) return null;
  const direct = item.area && !String(item.area).includes('未知') ? String(item.area) : item.district || null;
  return direct || anchorForName(item.name)?.area || null;
}

function resolveMustIncludePoiIds(data: TravelData, request: TravelPlanningRequest): string[] {
  const ids = new Set(request.must_include_poi_ids || []);
  const pool = [...data.plannerEntities, ...data.mixedPois, ...data.culturePois];
  for (const name of request.must_include_names || []) {
    for (const landmarkId of landmarkPoiIdsForName(name)) ids.add(landmarkId);
    const areaAnchor = anchorForName(name);
    if (areaAnchor) {
      for (const areaClassicId of classicPoiIdsForArea(areaAnchor.area)) {
        const poi = data.poiById.get(areaClassicId);
        if (poi && !String(poi.poi_id).startsWith('fixture_') && isRecommendablePoi(poi) && !hasBadUserVisiblePoiName(poi.name)) {
          ids.add(areaClassicId);
        }
      }
    }
    if (isGenericIncludeName(String(name))) continue;
    const exactOrContains = pool
      .filter((item) => matchesIncludeName(item, String(name)))
      .filter((item) => !hasBadUserVisiblePoiName(item.name))
      .filter((item) => isRecommendablePoi(item))
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
  const namedAnchor = anchorForName(normalizedName);
  const anchor = namedAnchor || { area: '用户指定地点', ...BEIJING_AREA_ANCHORS.北京 };
  const isFoodName = /餐|饭|吃|咖啡|小吃|烤鸭|涮肉|面|甜品|茶/.test(normalizedName);
  return normalizePoi({
    poi_id: `user_requested_${normalizePoiName(normalizedName) || index}`,
    name: normalizedName,
    district: anchor.district,
    area: anchor.area || '用户指定地点',
    category: isFoodName ? '餐饮' : '用户指定地点',
    poi_type: isFoodName ? 'food' : 'culture',
    address: '用户指定地点，本地 POI 库未命中，建议出发前确认精确地址',
    lng: anchor.lng,
    lat: anchor.lat,
    rating: 4.2,
    avg_cost: isFoodName ? 80 : 0,
    review_count: 0,
    suggested_duration_min: isFoodName ? 60 : 90,
    planning_tags: ['user_requested', 'needs_address_confirmation', namedAnchor ? 'area_anchor' : 'unknown_location_anchor'],
    evidence_tags: [namedAnchor ? '用户明确指定，本地 POI 库未命中，按同名区域锚点估算' : '用户明确指定，但本地 POI 库和区域锚点均未命中，需确认精确位置'],
    queue_risk: 'unknown',
    value_for_money: 'unknown',
    family_friendliness: 'unknown',
    environment_quality: 'unknown',
  } as Poi);
}

function buildAreaSupplementPoi(params: {
  selectedArea: string;
  request: TravelPlanningRequest;
  index: number;
  kind: 'food' | 'culture' | 'rest';
}): Poi | null {
  const anchor = anchorForName(params.selectedArea);
  if (!anchor) return null;
  const isFood = params.kind === 'food';
  const name = isFood
    ? `${params.selectedArea}周边午餐（需确认）`
    : params.kind === 'rest'
      ? `${params.selectedArea}周边休息点（需确认）`
      : `${params.selectedArea}周边补充游览（需确认）`;
  const offset = params.index * 0.0015;
  return normalizePoi({
    poi_id: `area_supplement_${normalizePoiName(params.selectedArea)}_${params.kind}_${params.index}`,
    name,
    district: anchor.district,
    area: params.selectedArea,
    category: isFood ? '餐饮' : '周边补充',
    poi_type: isFood ? 'food' : 'culture',
    address: `${params.selectedArea}周边，本地 POI 库覆盖不足，建议出发前确认精确地点`,
    lng: anchor.lng + offset,
    lat: anchor.lat + offset,
    rating: 4.0,
    avg_cost: isFood ? 100 : 0,
    review_count: 0,
    suggested_duration_min: isFood ? 60 : params.kind === 'rest' ? 45 : 75,
    planning_tags: ['area_supplement', 'needs_address_confirmation'],
    evidence_tags: ['本地 POI 库覆盖不足，按用户指定区域生成低置信度补充点'],
    queue_risk: 'unknown',
    value_for_money: 'unknown',
    family_friendliness: 'unknown',
    environment_quality: 'unknown',
  } as Poi);
}

function buildAreaSupplementPois(selectedArea: string, request: TravelPlanningRequest, targetCount: number): Poi[] {
  const items: Poi[] = [];
  if (request.route_mode === 'mixed') {
    const food = buildAreaSupplementPoi({ selectedArea, request, index: 1, kind: 'food' });
    if (food) items.push(food);
  }
  for (const kind of ['culture', 'rest', 'culture'] as const) {
    if (items.length >= targetCount) break;
    const item = buildAreaSupplementPoi({ selectedArea, request, index: items.length + 1, kind });
    if (item) items.push(item);
  }
  return items;
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

function normalizeRequest(payload: Partial<TravelPlanningRequest>): TravelPlanningRequest {
  const cleanedMustIncludeNames = Array.isArray(payload.must_include_names)
    ? Array.from(new Set(payload.must_include_names
      .map(String)
      .map(cleanupIncludedName)
      .filter((name) => !isGenericIncludeName(name))))
    : [];
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
    must_include_names: cleanedMustIncludeNames,
    exclude_names: Array.isArray(payload.exclude_names) ? payload.exclude_names : [],
    must_include_poi_ids: normalizeMustIncludeIds(payload),
    exclude_poi_ids: Array.isArray(payload.exclude_poi_ids) ? payload.exclude_poi_ids : [],
    route_order_poi_ids: Array.isArray(payload.route_order_poi_ids) ? payload.route_order_poi_ids : [],
    accommodation_names: Array.isArray(payload.accommodation_names) ? payload.accommodation_names.map(String).filter(Boolean).slice(0, 3) : [],
    preference_signals: payload.preference_signals || {},
    replan_acceleration_cache: replanCache,
  };
}

function extractAccommodationNames(text: string): string[] {
  const names: string[] = [];
  for (const area of Object.keys(BEIJING_AREA_ANCHORS)) {
    if (area === '北京') continue;
    if (new RegExp(`(?:住|住在|住宿在|酒店在|从)${area}(?:附近|周边|一带|出发|开始|酒店|宾馆|民宿)?`).test(text)) {
      names.push(area);
    }
  }
  const patterns = [
    /(?:住|住在|住宿在|酒店在)([^，,。；;]{2,12})(?=，|,|。|；|;|$)/g,
    /(?:住在|住宿在|酒店在|从)([^，,。；;]{2,24}?)(?:附近|周边|一带|出发|开始|酒店|宾馆|民宿)/g,
    /([^，,。；;]{2,24}?(?:酒店|宾馆|民宿))(?:附近|周边|一带|出发|开始)?/g,
  ];
  for (const pattern of patterns) {
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      const raw = String(match[1] || '')
        .replace(/^(我|我们|打算|计划|从)/, '')
        .replace(/^(在)/, '')
        .replace(/(附近|周边|一带|出发|开始)$/g, '')
        .trim();
      const cleaned = raw.replace(/^(北京)?住/, '').trim();
      if (cleaned && !/^(北京|酒店|宾馆|民宿|住宿|预算不确定)$/.test(cleaned)) names.push(cleaned);
    }
  }
  return Array.from(new Set(names)).slice(0, 3);
}

function parseGoal(goal: string, defaults: Partial<TravelPlanningRequest> = {}): TravelPlanningRequest {
  const compactGoal = goal.replace(/\s+/g, '');
  const wantsCouple = /情侣|约会|恋人|浪漫|两个人|二人/.test(goal);
  const wantsSenior = /老人|长辈|父母|爸妈|老年|别太累/.test(goal);
  const wantsKids = /亲子|孩子|小孩|儿童|带娃|遛娃|家庭/.test(goal);
  const noFood = /不吃饭|不安排吃饭|不要吃饭|不用吃饭/.test(goal);
  const explicitCulture = /文化路线|文化景点|经典文化/.test(goal);
  const asksFood = !noFood && /吃|好吃|饭|餐|美食|午餐|午饭|晚餐|咖啡|喝咖啡|烤鸭|炸酱面|小吃|吃逛|每天安排吃饭/.test(goal);
  const asksLunch = !noFood && !/晚上|夜间|夜游|晚餐/.test(goal) && /中午|午餐|午饭|午间|每天安排吃饭|好吃|美食|吃饭|烤鸭|北京菜|涮肉|炸酱面|小吃/.test(goal);
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
  const accommodationNames = Array.from(new Set([
    ...(defaults.accommodation_names || []),
    ...extractAccommodationNames(goal),
  ]));
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
    accommodation_names: accommodationNames,
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
      roast_duck: /烤鸭|北京菜/.test(goal) || Boolean(inheritedSignals.roast_duck),
      hotpot: /涮肉|铜锅|火锅/.test(goal) || Boolean(inheritedSignals.hotpot),
      zhajiangmian: /炸酱面/.test(goal) || Boolean(inheritedSignals.zhajiangmian),
      beijing_snack: /豆汁|小吃|老北京小吃/.test(goal) || Boolean(inheritedSignals.beijing_snack),
    },
  });
}

function applyStableGoalIntentPatch(goal: string, request: TravelPlanningRequest): TravelPlanningRequest {
  const text = String(goal || '');
  if (!text.trim()) return request;
  const parsed = parseGoal(text, request);
  const noFood = /不吃饭|不安排吃饭|不要吃饭|不用吃饭|不含餐/.test(text);
  const asksFood = !noFood && /吃饭|吃好|好吃|美食|餐饮|午餐|午饭|中午|晚餐|饭店|餐厅|小吃|咖啡|下午茶|烤鸭|炸酱面|涮肉|豆汁|每.?天.*吃|安排.*餐/.test(text);
  const asksCoffee = /咖啡|下午茶|甜品|奶茶/.test(text);
  const asksLunch = asksFood && !/晚上|夜间|夜游|晚餐/.test(text) && /中午|午餐|午饭|午间|吃饭|好吃|美食|餐饮|每.?天.*吃|安排.*餐|烤鸭|北京菜|涮肉|炸酱面|小吃/.test(text);
  const wantsCouple = /情侣|约会|恋人|浪漫|两个人|二人|鎯呬荆|娴极/.test(text);
  const wantsSenior = /老人|长辈|父母|爸妈|老年|别太累|不累|慢一点|鑰佷汉|闀胯緢|鐖舵瘝|鍒お绱/.test(text);
  const wantsKids = /亲子|孩子|小孩|儿童|带娃|遛娃|家庭|浜插瓙|瀛╁瓙|灏忓|鍎跨/.test(text);
  const lowWalk = /少走路|少步行|别太累|不累|轻松|老人|长辈|父母|爸妈|带娃|亲子|孩子|小孩|灏戣蛋璺|鍒お绱/.test(text);
  const qualityFood = /好吃|吃好|吃点好的|靠谱|美食|口碑|招牌|特色|不踩雷|推荐餐厅|烤鸭|炸酱面|涮肉|老北京小吃/.test(text);
  const avoidQueue = /不想排队|少排队|别排队|排队少|低排队|排队/.test(text);
  const valueForMoney = /性价比|预算|便宜|实惠|划算/.test(text);
  const accommodationNames = Array.from(new Set([
    ...(request.accommodation_names || []),
    ...extractAccommodationNames(text),
    ...(parsed.accommodation_names || []),
  ]));
  const personaId = wantsKids
    ? 'family_kids'
    : wantsSenior
      ? 'senior_relaxed'
      : wantsCouple
        ? 'couple_romantic'
        : request.persona_id;
  return normalizeRequest({
    ...request,
    area: request.area || parsed.area,
    max_budget: request.max_budget ?? parsed.max_budget,
    max_duration_min: request.max_duration_min ?? parsed.max_duration_min,
    day_count: Math.max(Number(request.day_count || 1), Number(parsed.day_count || 1)),
    must_include_names: Array.from(new Set([
      ...(request.must_include_names || []),
      ...(parsed.must_include_names || []),
    ])),
    exclude_names: Array.from(new Set([
      ...(request.exclude_names || []),
      ...(parsed.exclude_names || []),
    ])),
    accommodation_names: accommodationNames,
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
      roast_duck: noFood ? false : /烤鸭|北京菜/.test(text) || Boolean(request.preference_signals?.roast_duck),
      hotpot: noFood ? false : /涮肉|铜锅|火锅/.test(text) || Boolean(request.preference_signals?.hotpot),
      zhajiangmian: noFood ? false : /炸酱面/.test(text) || Boolean(request.preference_signals?.zhajiangmian),
      beijing_snack: noFood ? false : /豆汁|小吃|老北京小吃/.test(text) || Boolean(request.preference_signals?.beijing_snack),
      avoid_queue: avoidQueue || Boolean(request.preference_signals?.avoid_queue),
      value_for_money: valueForMoney || Boolean(request.preference_signals?.value_for_money),
      hotel_anchor: accommodationNames.length > 0 || /住宿|酒店|宾馆|民宿|住在|从.*出发/.test(text) || Boolean(request.preference_signals?.hotel_anchor),
      family: wantsKids || Boolean(request.preference_signals?.family),
      senior: wantsSenior || Boolean(request.preference_signals?.senior),
      couple: wantsCouple || Boolean(request.preference_signals?.couple),
    },
  });
}

function requestFromGoalAndIntent(goal: string, defaults: Partial<TravelPlanningRequest> = {}, intent?: TravelQueryIntent | null): TravelPlanningRequest {
  const localParsed = parseGoal(goal, defaults);
  if (!intent) return applyStableGoalIntentPatch(goal, localParsed);
  const intentPatch = intentToPlannerLikeRequest(intent);
  return applyStableGoalIntentPatch(goal, normalizeRequest({
    ...localParsed,
    route_mode: intentPatch.route_mode || localParsed.route_mode,
    area: intentPatch.area || localParsed.area,
    max_budget: intentPatch.max_budget ?? localParsed.max_budget,
    max_duration_min: intentPatch.max_duration_min ?? localParsed.max_duration_min,
    day_count: Math.max(Number(localParsed.day_count || 1), Number(intentPatch.day_count || 1)),
    start_time: intentPatch.start_time || localParsed.start_time,
    walk_preference: intentPatch.walk_preference || localParsed.walk_preference,
    persona_id: intentPatch.persona_id || localParsed.persona_id,
    must_include_names: Array.from(new Set([
      ...(localParsed.must_include_names || []),
      ...(intentPatch.must_include_names || []),
    ])),
    exclude_names: Array.from(new Set([
      ...(localParsed.exclude_names || []),
      ...(intentPatch.exclude_names || []),
    ])),
    accommodation_names: Array.from(new Set([
      ...(localParsed.accommodation_names || []),
      ...(intentPatch.accommodation_names || []),
    ])),
    preference_signals: {
      ...(localParsed.preference_signals || {}),
      ...(intentPatch.preference_signals || {}),
    },
    goal,
  }));
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

function hasBadUserVisiblePoiName(name: unknown): boolean {
  const text = String(name || '');
  if (!text) return false;
  const largeScenicNames = ['故宫博物院', '天坛公园', '北海公园', '景山公园', '颐和园', '圆明园'];
  const isLargeScenicSubPoi = largeScenicNames.some((scenicName) => (
    text.startsWith(scenicName) && !['', '遗址公园'].includes(text.slice(scenicName.length))
  ));
  return /\d+号(茶馆|小食铺|酒馆|餐馆|餐厅|饭馆)/.test(text)
    || /\d+号(书吧|文创|商店|小店)/.test(text)
    || /酒店|宾馆|客栈|漫心府|花间堂|住宿/.test(text)
    || /肯德基|麦当劳|兰州牛肉拉面|臭豆腐|SLOWBOAT|悠航|精酿|酒吧|啤酒/.test(text)
    || /市民文化中心|社区|居民|街道办|金鱼展|观景平台|售票|卫生间|游客中心|观众服务中心|讲解服务处|服务中心/.test(text)
    || isLargeScenicSubPoi;
}

function isSoftCultureMismatchPoi(item: Poi, request: TravelPlanningRequest): boolean {
  if (isFoodPoi(item)) return false;
  const goal = String(request.goal || '');
  const name = String(item.name || '');
  const text = poiText(item);
  const cultureFirst = request.route_mode === 'culture'
    || /文化路线|文化景点|经典文化|博物馆|美术馆|展览|故宫附近|不吃饭/.test(goal);
  if (!cultureFirst) return false;
  if (/演出|看剧|话剧|音乐剧|剧场|戏剧|教堂|宗教|购物|逛街|步行街/.test(goal)) return false;
  return /剧场|剧院|开心麻花|脱口秀|影院|电影|教堂|主教座堂|天主教|基督教|步行街|商场|购物中心/.test(`${name} ${text}`);
}

function hasBadUserVisiblePoiInResponse(value: Record<string, any> | null | undefined): boolean {
  const proposals = Array.isArray(value?.proposals) ? value.proposals : [];
  const proposalStops = proposals.flatMap((proposal) => Array.isArray(proposal?.pois) ? proposal.pois : []);
  const dayStops = Array.isArray(value?.daily_itinerary)
    ? value.daily_itinerary.flatMap((day) => Array.isArray(day?.proposal?.pois) ? day.proposal.pois : [])
    : [];
  return [...proposalStops, ...dayStops].some((stop) => hasBadUserVisiblePoiName(stop?.name));
}

function buildRouteQualityPool(params: {
  data: TravelData;
  candidates: Poi[];
  selectedArea: string;
  request: TravelPlanningRequest;
}): Poi[] {
  const areaClassicIds = classicPoiIdsForArea(params.selectedArea);
  const classicPois = areaClassicIds.map((id) => params.data.poiById.get(id)).filter(Boolean) as Poi[];
  return uniqueByName([
    ...classicPois,
    ...params.candidates,
    ...allPlannerPois(params.data),
    ...buildAreaSupplementPois(params.selectedArea, params.request, 5),
  ]).filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat));
}

function replaceBadRoutePois(params: {
  ordered: Poi[];
  request: TravelPlanningRequest;
  strategy: Strategy;
  selectedArea: string;
  candidates: Poi[];
  data: TravelData;
}): Poi[] {
  const mustIds = new Set(params.request.must_include_poi_ids || []);
  const mustNames = new Set(unresolvedMustIncludeNames(params.data, params.request));
  const isLocked = (item: Poi) => {
    if (hasBadUserVisiblePoiName(item.name)) return false;
    if (mustIds.has(item.poi_id)) return true;
    if (!isRecommendablePoi(item)) return false;
    const normalizedName = normalizePoiName(item.name);
    return [...mustNames].some((name) => {
      const normalizedMust = normalizePoiName(name);
      return Boolean(normalizedMust && (normalizedName.includes(normalizedMust) || normalizedMust.includes(normalizedName)));
    });
  };
  const qualityPool = buildRouteQualityPool(params);
  const selectedGroups = new Set(params.ordered.map((item) => attractionGroupKey(item)).filter(Boolean));
  const selectedIds = new Set(params.ordered.map((item) => item.poi_id));
  const scoreReplacement = (candidate: Poi, bad: Poi) => {
    let score = scorePoi(candidate, params.request, params.strategy, params.data);
    if (candidate.area === bad.area || candidate.district === bad.district) score += 24;
    if (candidate.area === params.selectedArea || candidate.district === params.selectedArea) score += 12;
    if (isFoodPoi(candidate) === isFoodPoi(bad)) score += 18;
    if (!isFoodPoi(candidate) && isClassicBackbonePoi(candidate)) score += 18;
    if (isFoodPoi(candidate)) score += foodPreferenceScore(candidate, params.request);
    return score;
  };

  return params.ordered.map((item) => {
    const softMismatch = isSoftCultureMismatchPoi(item, params.request);
    if ((isRecommendablePoi(item) && !hasBadUserVisiblePoiName(item.name) && !softMismatch) || isLocked(item)) return item;
    const replacement = qualityPool
      .filter((candidate) => candidate.poi_id !== item.poi_id)
      .filter((candidate) => !selectedIds.has(candidate.poi_id))
      .filter(isRecommendablePoi)
      .filter((candidate) => !hasBadUserVisiblePoiName(candidate.name))
      .filter((candidate) => !isSoftCultureMismatchPoi(candidate, params.request))
      .filter((candidate) => isFoodPoi(candidate) === isFoodPoi(item))
      .filter((candidate) => !selectedGroups.has(attractionGroupKey(candidate)))
      .sort((a, b) => scoreReplacement(b, item) - scoreReplacement(a, item))[0];
    if (!replacement) return item;
    selectedIds.add(replacement.poi_id);
    selectedGroups.add(attractionGroupKey(replacement));
    return replacement;
  });
}

function scorePoi(item: Poi, request: TravelPlanningRequest, strategy: Strategy, data: TravelData): number {
  const { values } = aggregateMap(data, item.poi_id);
  let score = Number(item.rating || 0) * 12 + Math.min(Number(item.review_count || 0), 500) / 100;
  const cost = Number(item.avg_cost || 0);
  const duration = Number(item.suggested_duration_min || 90);
  const text = poiText(item);
  const hasSpecificInclude = requestHasNamedInclude(request);
  if (!isFoodPoi(item) && isClassicBackbonePoi(item)) score += hasSpecificInclude ? 12 : 34;
  if (!isFoodPoi(item) && isOverSpecificCulturePoi(item)) score -= hasSpecificInclude ? 8 : 30;
  if (isSoftCultureMismatchPoi(item, request)) score -= request.max_duration_min && request.max_duration_min <= 300 ? 80 : 45;
  if (!isFoodPoi(item) && request.route_mode === 'culture') {
    if (/故宫博物院|景山公园|北海公园|天安门广场|中国国家博物馆|北京市规划展览馆|北京嘉德艺术中心|南池子美术馆/.test(String(item.name || ''))) score += 28;
    if (/博物馆|博物院|美术馆|艺术中心|展览馆/.test(String(item.name || ''))) score += 18;
  }
  if (strategy === 'budget') score -= cost / 8;
  else score -= cost / 25;
  if (strategy === 'efficient') score -= duration / 5;
  else score -= duration / 14;
  if (strategy === 'budget' && cost <= 40) score += 10;
  if (strategy === 'budget' && cost >= 120) score -= 12;
  if (strategy === 'efficient' && duration <= 75) score += 8;
  if (strategy === 'balanced' && duration >= 75 && duration <= 120) score += 4;
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
  if (shouldUseClassicBackbone(request)) return '故宫';
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

function selectClassicAreas(candidates: Poi[], limit: number): string[] {
  const availableAreas = new Set(candidates
    .flatMap((item) => [item.area, item.district])
    .filter(Boolean)
    .map(String));
  return BEIJING_CLASSIC_DAY_AREAS
    .filter((area) => availableAreas.has(area) || Boolean(BEIJING_AREA_ANCHORS[area]))
    .slice(0, Math.max(1, limit));
}

function shouldUseClassicBackbone(request: TravelPlanningRequest): boolean {
  const text = String(request.goal || '');
  const dayCount = Number(request.day_count || 1);
  const beijingTrip = /北京|故宫|颐和园|天坛|长城|什刹海|北海|南锣鼓巷|环球影城|北京环球/.test(text)
    || (request.must_include_names || []).some((name) => /故宫|颐和园|天坛|长城|什刹海|北海|南锣鼓巷|环球影城|北京环球/.test(String(name)))
    || (request.must_include_poi_ids || []).some((id) => /fixture_summer_palace|fixture_badaling|fixture_universal|amap_B000A8UIN8|amap_B000A81CB2/.test(String(id)));
  if (request.area && dayCount <= 1) return false;
  if (dayCount > 1 && beijingTrip) return true;
  if (dayCount > 1 && (request.preference_signals?.senior || request.preference_signals?.family || request.walk_preference === 'low')) return true;
  return !request.area
    && !requestHasNamedInclude(request)
    && (/北京|不知道去哪|随便|推荐|经典|第一次|初次|好玩|玩/.test(text) || dayCount > 1);
}

function distributeMustIncludeIdsByDay(data: TravelData, request: TravelPlanningRequest, dayCount: number): string[][] {
  const ids = Array.from(new Set(request.must_include_poi_ids || []));
  const result = Array.from({ length: dayCount }, () => [] as string[]);
  ids.forEach((id, index) => {
    result[Math.min(index, dayCount - 1)].push(id);
  });
  const unresolved = unresolvedMustIncludeNames(data, request);
  unresolved.forEach((name, index) => {
    const fallback = buildFallbackPoiForIncludeName(name, request, index + 1);
    result[Math.min(ids.length + index, dayCount - 1)].push(fallback.poi_id);
  });
  return result;
}

function resolveDayAreas(params: {
  data: TravelData;
  request: TravelPlanningRequest;
  pool: Poi[];
  selectedArea: string;
  dayCount: number;
}) {
  const { data, request, pool, selectedArea, dayCount } = params;
  const areas: string[] = [];
  for (const id of request.must_include_poi_ids || []) {
    const area = areaForPoi(data.poiById.get(id));
    if (area && !areas.includes(area)) areas.push(area);
  }
  for (const name of unresolvedMustIncludeNames(data, request)) {
    const area = anchorForName(name)?.area || request.area || selectedArea;
    if (area && !areas.includes(area)) areas.push(area);
  }
  if (request.area && !request.preference_signals?.hotel_anchor && !areas.includes(request.area)) areas.unshift(request.area);
  if (!areas.includes(selectedArea)) areas.push(selectedArea);
  const supplementalAreas = shouldUseClassicBackbone(request)
    ? selectClassicAreas(pool, dayCount + 4)
    : selectPopularAreas(pool, dayCount + 4);
  const popularAreas = supplementalAreas.filter((area) => !areas.includes(area));
  return [...areas, ...popularAreas].slice(0, Math.max(1, dayCount));
}

function perDayBudget(request: TravelPlanningRequest, dayCount: number): number | null {
  if (request.max_budget === null || request.max_budget === undefined) return null;
  return Math.max(80, Math.ceil(Number(request.max_budget) / Math.max(1, dayCount)));
}

function perDayDuration(request: TravelPlanningRequest, dayCount: number): number | null {
  if (request.max_duration_min === null || request.max_duration_min === undefined) return null;
  const total = Number(request.max_duration_min);
  if (!Number.isFinite(total) || total <= 0) return null;
  return Math.max(240, Math.min(540, Math.ceil(total / Math.max(1, dayCount))));
}

function dayThemeForArea(area: string, index: number, dayCount: number, hasMust: boolean): string {
  if (/颐和园|圆明园/.test(area)) return '皇家园林西北线';
  if (/故宫|景山|北海|天安门/.test(area)) return '故宫中轴线';
  if (/天坛|前门/.test(area)) return '老北京与中轴线';
  if (/什刹海|后海|南锣鼓巷/.test(area)) return '胡同烟火与老北京';
  if (/环球影城|北京环球/.test(area)) return '环球影城主题乐园日';
  if (/长城|八达岭/.test(area)) return '长城远郊一日线';
  if (index === dayCount - 1 && dayCount > 1) return '轻松收尾与顺路补充';
  return hasMust ? '用户指定目的地体验' : '经典北京体验';
}

function dayPlanningNote(area: string, index: number, dayCount: number, request: TravelPlanningRequest): string {
  const foodText = request.preference_signals?.quality_food
    ? '餐饮优先匹配京味、烤鸭、涮肉或本地口碑店'
    : '餐饮按顺路和预算控制';
  if (/颐和园|圆明园/.test(area)) return `集中在海淀西北，颐和园适合上午做主体验，下午顺接圆明园，${foodText}。`;
  if (/故宫|景山|北海|天安门/.test(area)) return `以故宫为上午主线，午后顺接景山、北海或什刹海，故宫需提前预约，${foodText}。`;
  if (/天坛|前门/.test(area)) return `上午安排天坛或中轴线景点，午餐适合补一顿京味，下午接前门/大栅栏会更像轻松收尾。`;
  if (/环球影城|北京环球/.test(area)) return '环球影城建议单独成日，午餐放在园区或城市大道中段解决，不再叠加市区重行程。';
  if (/长城|八达岭/.test(area)) return '长城属于远郊线，建议单独成日，控制市区补充点，避免当天过度跨区。';
  if (index === dayCount - 1 && dayCount > 1) return '最后一天默认降低强度，适合安排顺路景点、餐饮和可替换的轻量活动。';
  return `当天围绕${area || '北京'}展开，控制跨区转场，${foodText}。`;
}

function transferModeLabel(mode?: string | null, minutes?: number | null, metersValue?: number | null): string {
  const value = String(mode || '');
  if (/walk/.test(value)) return '步行';
  if (/subway|metro|transit/.test(value)) return '地铁/公交';
  if (/drive|taxi|car/.test(value)) return '打车/驾车';
  if (Number(metersValue || 0) <= 1200 || Number(minutes || 0) <= 15) return '步行';
  if (Number(metersValue || 0) >= 5000 || Number(minutes || 0) >= 35) return '地铁/打车';
  return '步行或短途打车';
}

function buildDayUserSummary(day: Record<string, any>, request: TravelPlanningRequest): string {
  const proposal = day.proposal || {};
  const names = Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names : [];
  const route = names.slice(0, 4).join(' → ');
  const commute = Number(proposal.total_transfer_minutes || 0);
  const budget = Number(proposal.total_budget_estimate || 0);
  return `${day.theme || '北京行程'}：${route}。预计转场约 ${commute} 分钟，预算约 ${budget} 元。${day.planning_note || dayPlanningNote(String(day.area || ''), Number(day.day || 1) - 1, Number(request.day_count || 1), request)}`;
}

function buildDailyItinerary(params: {
  data: TravelData;
  request: TravelPlanningRequest;
  pool: Poi[];
  selectedArea: string;
  commuteEdges?: CommuteEdgeIndex;
  prepare: (data: TravelData, payload: Partial<TravelPlanningRequest>) => TravelPlanningRequest;
  strategies?: Strategy[];
}) {
  const { data, request, pool, selectedArea, commuteEdges, prepare } = params;
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(request.day_count || 1)));
  const dayAreas = resolveDayAreas({ data, request, pool, selectedArea, dayCount });
  const mustIdsByDay = distributeMustIncludeIdsByDay(data, request, dayCount);
  const dailyBudget = perDayBudget(request, dayCount);
  const dailyDuration = perDayDuration(request, dayCount) ?? (dayCount > 1 ? 480 : request.max_duration_min ?? null);
  const usedDailyPoiIds = new Set<string>();

  return Array.from({ length: dayCount }, (_, index) => {
    const dayMustIds = mustIdsByDay[index] || [];
    const firstMustArea = areaForPoi(data.poiById.get(dayMustIds[0]));
    const dayArea = firstMustArea || dayAreas[index % dayAreas.length] || selectedArea;
    const classicCompanionTarget = Math.max(0, 3 - dayMustIds.length);
    const classicDayMustIds = shouldUseClassicBackbone(request)
      ? classicPoiIdsForArea(dayArea)
        .filter((id) => data.poiById.has(id))
        .filter((id) => !dayMustIds.includes(id))
        .filter((id) => !usedDailyPoiIds.has(id))
        .slice(0, classicCompanionTarget || (dayMustIds.length ? 1 : 3))
      : [];
    const classicSkeletonCount = dayMustIds.length + classicDayMustIds.length;
    const classicSkeletonHasFood = [...dayMustIds, ...classicDayMustIds]
      .map((id) => data.poiById.get(id))
      .some((poi) => poi && isFoodPoi(poi));
    const heavyDay = /环球影城|北京环球|长城|八达岭/.test(dayArea);
    const finalRelaxedDay = dayCount > 2 && index === dayCount - 1 && request.pace !== 'compact';
    const dayTargetCount = heavyDay
      ? Math.max(3, classicSkeletonCount || 3)
      : classicSkeletonCount >= 3
      ? classicSkeletonCount + (request.route_mode === 'mixed' && !classicSkeletonHasFood ? 1 : 0)
      : finalRelaxedDay
        ? 3
      : request.max_duration_min && request.max_duration_min >= 420
        ? 4
        : request.max_total_pois;
    const dayRequest = prepare(data, {
      ...request,
      goal: '',
      area: dayArea,
      max_budget: dailyBudget,
      max_duration_min: dailyDuration,
      max_total_pois: dayTargetCount,
      must_include_names: [],
      must_include_poi_ids: [...dayMustIds, ...classicDayMustIds],
      route_order_poi_ids: [...(index === 0 ? request.route_order_poi_ids || [] : []), ...dayMustIds, ...classicDayMustIds],
      exclude_poi_ids: [...(request.exclude_poi_ids || []), ...Array.from(usedDailyPoiIds).filter((id) => !dayMustIds.includes(id))],
    });
    dayRequest.goal = request.goal;
    const strategy = params.strategies?.[index] || (index % 3 === 0 ? 'balanced' : index % 3 === 1 ? 'efficient' : 'budget');
    const dayProposal = buildProposal({ request: dayRequest, strategy, selectedArea: dayArea, candidates: pool, data, commuteEdges });
    for (const id of dayProposal.ordered_poi_ids || []) usedDailyPoiIds.add(String(id));
    const theme = dayThemeForArea(dayArea, index, dayCount, dayMustIds.length > 0);
    const day = {
      day: index + 1,
      title: `第 ${index + 1} 天`,
      area: dayArea,
      theme,
      planning_note: dayPlanningNote(dayArea, index, dayCount, request),
      accommodation: dayProposal.accommodation || null,
      proposal: dayProposal,
    };
    return {
      ...day,
      user_summary: buildDayUserSummary(day, request),
    };
  });
}

function buildTripProposalFromDaily(strategy: Strategy, dailyItinerary: Array<Record<string, any>>) {
  const title = strategy === 'balanced' ? '均衡体验方案' : strategy === 'budget' ? '预算优先方案' : '效率优先方案';
  const dayProposals = dailyItinerary.map((day) => day.proposal || {});
  const allStops = dayProposals.flatMap((proposal, dayIndex) =>
    (Array.isArray(proposal.pois) ? proposal.pois : []).map((stop: Record<string, any>) => ({
      ...stop,
      day: dayIndex + 1,
    })),
  );
  const totalBudget = dayProposals.reduce((sum, proposal) => sum + Number(proposal.total_budget_estimate || 0), 0);
  const totalTransfer = dayProposals.reduce((sum, proposal) => sum + Number(proposal.total_transfer_minutes || 0), 0);
  const totalDistance = dayProposals.reduce((sum, proposal) => sum + Number(proposal.total_walking_distance_m || 0), 0);
  const totalVisit = dayProposals.reduce((sum, proposal) => sum + Number(proposal.total_visit_duration_min || 0), 0);
  const totalDuration = dayProposals.reduce((sum, proposal) => sum + Number(proposal.total_route_duration_min || 0), 0);
  const transferSummary = summarizeProposalTransfers(dayProposals);
  const accommodation = dayProposals.find((proposal) => proposal.accommodation)?.accommodation || null;
  const hotelRecommendations = dedupeHotelRecommendations(
    dayProposals.flatMap((proposal) => Array.isArray(proposal.hotel_recommendations) ? proposal.hotel_recommendations : []),
    5,
  );
  const orderedNames = allStops.map((stop) => String(stop.name || '')).filter(Boolean);
  const daySummaries = dailyItinerary.map((day) => day.user_summary).filter(Boolean);
  return {
    proposal_id: `${strategy}-trip-${Math.random().toString(16).slice(2, 10)}`,
    strategy,
    display_title: title,
    title,
    summary: `${dailyItinerary.length} 天北京行程，${allStops.length} 个停留点，预计 ${totalDuration} 分钟，预算约 ${totalBudget} 元。${strategy === 'budget' ? '偏省钱和顺路。' : strategy === 'efficient' ? '偏少转场和片区集中。' : '兼顾经典景点、餐饮和节奏。'}`,
    day_count: dailyItinerary.length,
    daily_itinerary: dailyItinerary,
    day_summaries: daySummaries,
    user_visible_summary: daySummaries.join('\n'),
    accommodation,
    hotel_recommendations: hotelRecommendations,
    ordered_poi_ids: allStops.map((stop) => stop.poi_id).filter(Boolean),
    ordered_poi_names: orderedNames,
    pois: allStops,
    total_budget_estimate: totalBudget,
    total_transfer_minutes: totalTransfer,
    total_walking_distance_m: Math.round(totalDistance),
    transfer_source_summary: transferSummary,
    total_visit_duration_min: totalVisit,
    total_route_duration_min: totalDuration,
    travel_time_confidence: 'estimated',
    budget_summary: { total_budget_estimate: totalBudget },
    duration_summary: { total_route_duration_min: totalDuration, total_visit_duration_min: totalVisit, total_transfer_minutes: totalTransfer },
    risks: Array.from(new Set(dayProposals.flatMap((proposal) => Array.isArray(proposal.risks) ? proposal.risks : []))).slice(0, 6),
  };
}

function buildMultiDayPlanSet(params: {
  data: TravelData;
  request: TravelPlanningRequest;
  pool: Poi[];
  selectedArea: string;
  commuteEdges?: CommuteEdgeIndex;
  prepare: (data: TravelData, payload: Partial<TravelPlanningRequest>) => TravelPlanningRequest;
}) {
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(params.request.day_count || 1)));
  const variantParams = (strategy: Strategy) => {
    if (strategy === 'budget') {
      return {
        ...params,
        request: normalizeRequest({
          ...params.request,
          preference_signals: {
            ...(params.request.preference_signals || {}),
            value_for_money: true,
          },
        }),
        selectedArea: params.selectedArea,
      };
    }
    if (strategy === 'efficient') {
      return {
        ...params,
        request: normalizeRequest({
          ...params.request,
          walk_preference: params.request.walk_preference === 'low' ? 'low' : 'medium',
          pace: 'balanced',
        }),
        selectedArea: params.selectedArea,
      };
    }
    return params;
  };
  const variants = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => {
    const dailyItinerary = buildDailyItinerary({
      ...variantParams(strategy),
      strategies: Array.from({ length: dayCount }, () => strategy),
    });
    return buildTripProposalFromDaily(strategy, dailyItinerary);
  });
  return {
    dailyItinerary: variants[0]?.daily_itinerary || [],
    proposals: variants,
  };
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

function isLocalBeijingFoodPoi(item: Poi): boolean {
  return /四季民福|便宜坊|大董|全聚德|利群|明园|紫光园|烤鸭|北京菜|京味|涮肉|铜锅|南门|鸦儿李记|烤肉季|炸酱面|爆肚|卤煮|护国寺|门钉肉饼|烧麦/.test(String(item.name || ''));
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
    preference_signals: {
      ...(params.parsed.preference_signals || {}),
      preserve_route_order: true,
    },
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
  const explicitPayloadMustIds = new Set(Array.isArray(payload.must_include_poi_ids) ? payload.must_include_poi_ids.map(String) : []);
  const request = payload.goal
    ? applyStableGoalIntentPatch(String(payload.goal), parseGoal(String(payload.goal), payload))
    : normalizeRequest(payload);
  if (request.preference_signals?.hotel_anchor && request.area && (request.accommodation_names || []).some((name) => normalizePoiName(name) === normalizePoiName(request.area || ''))) {
    request.area = null;
  }
  request.must_include_poi_ids = Array.from(new Set([
    ...(request.must_include_poi_ids || []),
    ...resolveMustIncludePoiIds(data, request),
  ])).filter((id) => {
    if (explicitPayloadMustIds.has(id)) return true;
    const poi = data.poiById.get(id);
    return !poi || (isRecommendablePoi(poi) && !hasBadUserVisiblePoiName(poi.name));
  });
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
  const selectedAnchor = anchorForName(selectedArea);
  const nearbyCandidates = selectedAnchor
    ? candidates
      .filter((item) => meters({ ...item, lat: selectedAnchor.lat, lng: selectedAnchor.lng }, item) <= 5000)
      .filter((item) => item.area === selectedArea || isFoodPoi(item))
    : [];
  const nearbyDiversified = uniqueByAttractionGroup(uniqueByName([...sameAreaDiversified, ...nearbyCandidates]));
  const scopedPool = nearbyDiversified.length >= Math.min(targetCount, 3)
    ? nearbyDiversified
    : uniqueByName([...nearbyDiversified, ...buildAreaSupplementPois(selectedArea, request, targetCount)]);
  const basePool = scopedPool.length >= targetCount
    ? scopedPool
    : sameAreaDiversified.length >= targetCount
    ? sameAreaDiversified
    : uniqueByAttractionGroup(uniqueByName(candidates));
  const effectiveMustNames = unresolvedMustIncludeNames(data, request);
  const requiredCandidates = uniqueByName([...candidates, ...allPlannerPois(data)]).filter((item) => {
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
  const available = pool.filter((item) => {
    if (excludedIds.has(item.poi_id)) return false;
    return !matchesExcludedName(item, request.exclude_names || []);
  }).filter((item) => {
    const required = (request.must_include_poi_ids || []).includes(item.poi_id)
      || effectiveMustNames.some((name) => matchesIncludeName(item, String(name)));
    if (required) return true;
    return !String(item.poi_id).startsWith('fixture_') && !String(item.name).includes('未知');
  });

  const recommendable = available.filter((item) => (request.must_include_poi_ids || []).includes(item.poi_id) || isRecommendablePoi(item));
  const scopedRecommendable = request.preference_signals?.indoor && request.route_mode === 'culture'
    ? recommendable.filter((item) => isIndoorCulturePoi(item) || (request.must_include_poi_ids || []).includes(item.poi_id))
    : recommendable;
  const food = scopedRecommendable.filter(isFoodPoi);
  const lunchFood = food.filter(isLunchPoi);
  const culture = scopedRecommendable.filter((item) => !isFoodPoi(item));
  const isRealLunchCandidate = (item: Poi) => isFoodPoi(item) && (item.meal_type === 'meal' || item.meal_type === 'snack' || item.is_lunch_suitable) && !isCoffeePoi(item);
  const areaProximityScore = (item: Poi) => {
    if (!selectedAnchor) return 0;
    const distance = meters({ ...item, lat: selectedAnchor.lat, lng: selectedAnchor.lng }, item);
    if (distance <= 1000) return 18;
    if (distance <= 2500) return 10;
    if (distance <= 5000) return 2;
    return -Math.min(30, distance / 500);
  };
  const ranked = (items: Poi[]) => [...items]
    .filter((item) => request.max_budget === null || request.max_budget === undefined || Number(item.avg_cost || 0) <= Number(request.max_budget))
    .sort((a, b) => (scorePoi(b, request, strategy, data) + areaProximityScore(b)) - (scorePoi(a, request, strategy, data) + areaProximityScore(a)));
  const strategyRankOffset = (items: Poi[]) => {
    if (items.length <= 3) return 0;
    if (strategy === 'balanced') return 0;
    if (strategy === 'budget') return Math.min(1, items.length - 1);
    return Math.min(2, items.length - 1);
  };
  const takeStrategySlice = (items: Poi[], count: number) => {
    const offset = strategyRankOffset(items);
    const sliced = items.slice(offset, offset + count);
    return sliced.length >= count ? sliced : [...sliced, ...items.slice(0, count - sliced.length)];
  };
  const foodRanked = (items: Poi[]) => ranked(items).sort((a, b) => {
    if (request.preference_signals?.quality_food && /北京|故宫|颐和园|天坛|什刹海|前门|王府井|本地|特色|好吃|美食|吃/.test(String(request.goal || ''))) {
      const local = (isLocalBeijingFoodPoi(b) ? 1 : 0) - (isLocalBeijingFoodPoi(a) ? 1 : 0);
      if (local !== 0) return local;
    }
    const preference = foodPreferenceScore(b, request) - foodPreferenceScore(a, request);
    if (preference !== 0) return preference;
    if (strategy === 'budget') {
      const cost = Number(a.avg_cost || 0) - Number(b.avg_cost || 0);
      if (cost !== 0) return cost;
    }
    if (strategy === 'efficient') {
      const proximity = areaProximityScore(b) - areaProximityScore(a);
      if (Math.abs(proximity) > 1) return proximity;
    }
    const proximity = areaProximityScore(b) - areaProximityScore(a);
    if (Math.abs(proximity) > 1) return proximity;
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
    const selectedFood = requiredFood
      ?? takeStrategySlice(foodCandidates, 1)[0]
      ?? takeStrategySlice(foodRanked(mealPool), 1)[0]
      ?? takeStrategySlice(foodRanked(food.filter((item) => !isCoffeePoi(item))), 1)[0]
      ?? foodRanked(food)[0];
    if (selectedFood) selected.push(selectedFood);
    const remainingBudget = budgetLimit === null ? null : Math.max(0, budgetLimit - Number(selectedFood?.avg_cost || 0));
    const cultureSlots = Math.max(2, targetCount - 1);
    const cultureBudgetCap = remainingBudget === null ? null : Math.max(0, remainingBudget / cultureSlots);
    const cultureDurationCap = request.persona_id === 'family_kids' || request.persona_id === 'senior_relaxed' ? 120 : 100;
    const cultureCandidates = ranked(culture)
      .filter((item) => Number(item.suggested_duration_min || 90) <= cultureDurationCap)
      .filter((item) => cultureBudgetCap === null || Number(item.avg_cost || 0) <= cultureBudgetCap);
    selected.push(...takeStrategySlice(cultureCandidates, cultureSlots));
    if (selected.length < targetCount) {
      selected.push(...takeStrategySlice(ranked(culture).filter((item) => !selected.some((chosen) => chosen.poi_id === item.poi_id)), targetCount - selected.length));
    }
  } else {
    selected.push(...takeStrategySlice(ranked(culture), targetCount));
  }

  const mustIds = new Set(request.must_include_poi_ids || []);
  const mustNames = new Set(effectiveMustNames);
  const requiredFoodIds = new Set(requiredCandidates
    .filter((item) => mustIds.has(item.poi_id) && isFoodPoi(item))
    .map((item) => item.poi_id));
  for (const required of requiredCandidates.filter((item) => {
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
  const routeOrderIds = Array.isArray(request.route_order_poi_ids) ? request.route_order_poi_ids.map(String).filter(Boolean) : [];
  const exactRouteOrder = routeOrderIds
    .map((id) => available.find((item) => item.poi_id === id) || requiredCandidates.find((item) => item.poi_id === id) || data.poiById.get(id))
    .filter(Boolean) as Poi[];
  const shouldPreserveExactRouteOrder = routeOrderIds.length > 0
    && exactRouteOrder.length >= Math.min(targetCount, 2)
    && exactRouteOrder.every((item) => mustIds.has(item.poi_id) || routeOrderIds.includes(item.poi_id));
  let ordered = shouldPreserveExactRouteOrder
    ? exactRouteOrder.slice(0, targetCount)
    : orderNearest([...mustSelected, ...optionalSelected].slice(0, targetCount), commuteEdges);
  if (request.route_mode === 'mixed' && !ordered.some(isFoodPoi)) {
    const fallbackFood = foodRanked(
      request.preference_signals?.lunch || request.preference_signals?.formal_meal
        ? food.filter(isRealLunchCandidate)
        : food,
    )[0] ?? foodRanked(food)[0] ?? buildAreaSupplementPoi({ selectedArea, request, index: 1, kind: 'food' });
    if (fallbackFood) {
      const cultureOnly = ordered.filter((item) => !isFoodPoi(item));
      ordered = [fallbackFood, ...cultureOnly].slice(0, Math.max(3, targetCount));
    }
  }
  if (!shouldPreserveExactRouteOrder && routeOrderIds.length) {
    const byId = new Map(ordered.map((item) => [item.poi_id, item]));
    const remaining = ordered.filter((item) => !routeOrderIds.includes(item.poi_id));
    const templateOrdered: Poi[] = [];
    for (const id of routeOrderIds) {
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
  const minimumStops = Math.min(targetCount, 3);
  while (ordered.length < minimumStops) {
    const next = ranked(scopedRecommendable)
      .filter((item) => !ordered.some((chosen) => chosen.poi_id === item.poi_id))
      .filter((item) => isRecommendablePoi(item))
      .find((item) => {
        if (request.route_mode === 'mixed' && !ordered.some(isFoodPoi)) return isFoodPoi(item);
        return !isFoodPoi(item);
      })
      ?? ranked(scopedRecommendable)
        .filter((item) => !ordered.some((chosen) => chosen.poi_id === item.poi_id))
        .find(isRecommendablePoi);
    if (!next) break;
    ordered.push(next);
  }
  ordered = replaceBadRoutePois({ ordered, request, strategy, selectedArea, candidates, data });
  if (routeOrderIds.length) {
    const lockedOrder = routeOrderIds
      .map((id) => data.poiById.get(id) || requiredCandidates.find((item) => item.poi_id === id))
      .filter((item): item is Poi => Boolean(item))
      .filter((item) => !excludedIds.has(item.poi_id) && !matchesExcludedName(item, request.exclude_names || []));
    if (lockedOrder.length) {
      const lockedIds = new Set(lockedOrder.map((item) => item.poi_id));
      ordered = [...lockedOrder, ...ordered.filter((item) => !lockedIds.has(item.poi_id))].slice(0, targetCount);
    }
  }

  const accommodationAnchor = accommodationAnchorForRequest(data, request, selectedArea);
  const originTransfer = accommodationAnchor && ordered[0] ? estimateTransfer(accommodationAnchor, ordered[0], commuteEdges) : null;
  const returnTransfer = accommodationAnchor && ordered.length > 0 ? estimateTransfer(ordered[ordered.length - 1], accommodationAnchor, commuteEdges) : null;
  const start = parseMinutes(request.start_time) ?? 9 * 60;
  let cursor = start;
  let totalTransfer = originTransfer?.minutes || 0;
  let totalDistance = originTransfer?.meters || 0;
  let commuteEdgesUsed = originTransfer?.source === 'commute_edge' ? 1 : 0;
  let coordinateEstimatesUsed = originTransfer?.source === 'coordinate_estimate' ? 1 : 0;
  let unknownHours = 0;
  let hasOpeningConflict = false;
  const stops = ordered.map((item, index) => {
    const inboundEstimate = index === 0 && originTransfer
      ? originTransfer
      : index > 0
        ? estimateTransfer(ordered[index - 1], item, commuteEdges)
        : null;
    const transfer = inboundEstimate?.minutes || 0;
    const distance = inboundEstimate?.meters || 0;
    const transferSource: TransferSource = inboundEstimate?.source || 'coordinate_estimate';
    const transferMode: string | null = inboundEstimate?.mode || null;
    const transferProvider: string | null = inboundEstimate?.provider || null;
    const transferDurationSeconds: number | null = inboundEstimate?.duration_s || null;
    const transferCount: number | null = inboundEstimate?.transfer_count || null;
    if (index > 0) {
      if (inboundEstimate?.source === 'commute_edge') commuteEdgesUsed += 1;
      else coordinateEstimatesUsed += 1;
      totalTransfer += transfer;
      totalDistance += distance;
      cursor += transfer;
    } else if (originTransfer) {
      cursor += transfer;
    }
    const isFoodStop = isFoodPoi(item);
    const isSnackStop = Boolean(request.preference_signals?.snack && isSnackOrTeaPoi(item));
    if (request.preference_signals?.lunch && isFoodStop && !isSnackStop && cursor < 11 * 60 + 30) cursor = 11 * 60 + 30;
    if (index === 0 && request.preference_signals?.lunch && isFoodStop && !isSnackStop && cursor > 14 * 60) cursor = 13 * 60;
    if (isSnackStop && cursor < 13 * 60) cursor = 13 * 60;
    const arrival = cursor;
    const rawStay = Number(item.suggested_duration_min || 90);
    const shortRoute = Boolean(request.max_duration_min && request.max_duration_min <= 270);
    const relaxedLowWalk = request.walk_preference === 'low' && request.pace === 'relaxed';
    let stay = request.max_duration_min && request.max_duration_min <= 180
      ? Math.min(rawStay, isFoodStop ? 35 : 45)
      : shortRoute
        ? Math.min(rawStay, isFoodStop ? 50 : relaxedLowWalk ? 55 : 65)
        : rawStay;
    const nextItem = ordered[index + 1];
    const nextIsLunch = nextItem && request.preference_signals?.lunch && isFoodPoi(nextItem) && !isSnackOrTeaPoi(nextItem);
    if (!isFoodStop && nextIsLunch && arrival < 11 * 60 + 30 && arrival + stay > 12 * 60) {
      stay = Math.max(75, Math.min(stay, 11 * 60 + 30 - arrival));
    }
    if (isFoodStop && !isSnackStop && request.preference_signals?.lunch) {
      stay = Math.max(60, Math.min(stay, 90));
    }
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
      transfer_source: index > 0 || originTransfer ? transferSource : null,
      transfer_from_label: index === 0 && accommodationAnchor ? accommodationAnchor.name : null,
      transfer_mode: transferMode,
      transfer_mode_label: transferModeLabel(transferMode, transfer, distance),
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

  if (returnTransfer) {
    totalTransfer += returnTransfer.minutes;
    totalDistance += returnTransfer.meters;
    if (returnTransfer.source === 'commute_edge') commuteEdgesUsed += 1;
    else coordinateEstimatesUsed += 1;
  }
  const totalBudget = stops.reduce((sum, item) => sum + item.estimated_cost, 0);
  const totalVisit = stops.reduce((sum, item) => sum + item.stay_minutes, 0);
  const totalDuration = cursor - start + (returnTransfer?.minutes || 0);
  const foodCount = stops.filter((item) => item.poi_type === 'food').length;
  const cultureCount = stops.length - foodCount;
  const categorySatisfied = request.route_mode === 'mixed' ? foodCount >= 1 && cultureCount >= 2 : cultureCount >= 3;
  const transferSummary = {
    commute_edges_used: commuteEdgesUsed,
    coordinate_estimates_used: coordinateEstimatesUsed,
    commute_edge_hit_rate: Math.max(0, stops.length - 1 + (originTransfer ? 1 : 0) + (returnTransfer ? 1 : 0)) > 0
      ? Number((commuteEdgesUsed / Math.max(1, stops.length - 1 + (originTransfer ? 1 : 0) + (returnTransfer ? 1 : 0))).toFixed(3))
      : 0,
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
  const hotelRecommendations = buildHotelRecommendations({ data, request, selectedArea, stops: ordered, commuteEdges, limit: 3 });
  return {
    proposal_id: `${strategy}-${Math.random().toString(16).slice(2, 10)}`,
    strategy,
    display_title: title,
    title,
    summary: `${selectedArea} area, ${stops.length} POIs, about ${totalDuration} min, ${totalBudget} CNY.`,
    ordered_poi_ids: stops.map((item) => item.poi_id),
    ordered_poi_names: stops.map((item) => item.name),
    pois: stops,
    hotel_recommendations: hotelRecommendations,
    accommodation: accommodationAnchor ? {
      name: accommodationAnchor.name,
      area: accommodationAnchor.area,
      district: accommodationAnchor.district,
      address: accommodationAnchor.address,
      location_confidence: accommodationAnchor.location_confidence,
      source_name: accommodationAnchor.source_name,
      outbound_transfer_minutes: originTransfer?.minutes ?? null,
      outbound_transfer_meters: originTransfer?.meters ?? null,
      outbound_transfer_mode: originTransfer?.mode ?? null,
      outbound_transfer_source: originTransfer?.source ?? null,
      return_transfer_minutes: returnTransfer?.minutes ?? null,
      return_transfer_meters: returnTransfer?.meters ?? null,
      return_transfer_mode: returnTransfer?.mode ?? null,
      return_transfer_source: returnTransfer?.source ?? null,
      note: '住宿位置按用户描述解析为区域锚点，用于估算每日出发和返回通勤；真实酒店地址和实时导航需出发前确认。',
    } : null,
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
      hotel_pois: data.hotels.length,
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
  const hotelAreas = new Map<string, { hotel_count: number; rating_sum: number; cost_sum: number }>();
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
  for (const item of data.hotels) {
    const area = item.area || item.district;
    if (!area || area === '未知') continue;
    const current = hotelAreas.get(area) || { hotel_count: 0, rating_sum: 0, cost_sum: 0 };
    hotelAreas.set(area, {
      hotel_count: current.hotel_count + 1,
      rating_sum: current.rating_sum + Number(item.rating || 0),
      cost_sum: current.cost_sum + Number(item.avg_cost || 0),
    });
  }
  return {
    city_id: 'beijing',
    route_modes: [
      { value: 'culture', label: '北京文化路线' },
      { value: 'mixed', label: '餐饮 + 文化混排' },
    ],
    areas: [...areas.entries()].map(([value, counts]) => ({ value, label: value, ...counts })).sort((a, b) => b.mixed_count - a.mixed_count).slice(0, 30),
    hotel_areas: [...hotelAreas.entries()]
      .map(([value, counts]) => ({
        value,
        label: value,
        hotel_count: counts.hotel_count,
        avg_rating: counts.hotel_count ? Number((counts.rating_sum / counts.hotel_count).toFixed(2)) : 0,
        avg_cost: counts.hotel_count ? Math.round(counts.cost_sum / counts.hotel_count) : 0,
      }))
      .sort((a, b) => b.hotel_count - a.hotel_count)
      .slice(0, 30),
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
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(request.day_count || 1)));
  const singleDayProposals = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => buildProposal({ request, strategy, selectedArea, candidates: pool, data, commuteEdges }));
  const multiDayPlanSet = dayCount > 1
    ? buildMultiDayPlanSet({ data, request, pool, selectedArea, commuteEdges, prepare: preparePlanningRequest })
    : null;
  const dailyItinerary = multiDayPlanSet?.dailyItinerary
    || buildDailyItinerary({ data, request, pool, selectedArea, commuteEdges, prepare: preparePlanningRequest });
  const proposals = multiDayPlanSet?.proposals || singleDayProposals;
  const hotelRecommendations = dedupeHotelRecommendations(
    proposals.flatMap((proposal) => Array.isArray(proposal.hotel_recommendations) ? proposal.hotel_recommendations : []),
    5,
  );
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
    hotel_recommendations: hotelRecommendations,
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
  const dayCount = Math.max(1, Math.min(MAX_TRIP_DAYS, Number(request.day_count || 1)));
  const singleDayProposals = (['balanced', 'budget', 'efficient'] as Strategy[]).map((strategy) => buildProposal({ request, strategy, selectedArea, candidates: pool, data, commuteEdges }));
  const multiDayPlanSet = dayCount > 1
    ? buildMultiDayPlanSet({ data, request, pool, selectedArea, commuteEdges, prepare: (_data, value) => normalizeRequest(value) })
    : null;
  const dailyItinerary = multiDayPlanSet?.dailyItinerary
    || buildDailyItinerary({ data, request, pool, selectedArea, commuteEdges, prepare: (_data, value) => normalizeRequest(value) });
  const proposals = multiDayPlanSet?.proposals || singleDayProposals;
  const hotelRecommendations = dedupeHotelRecommendations(
    proposals.flatMap((proposal) => Array.isArray(proposal.hotel_recommendations) ? proposal.hotel_recommendations : []),
    5,
  );
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
    hotel_recommendations: hotelRecommendations,
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
    const corpusRequest = requestFromGoalAndIntent(rawGoal, payload.defaults, intent);
    const shouldUseStaticFastPath = corpusRequest.persona_id === 'classic_first_timer'
      && !corpusRequest.preference_signals?.family
      && !corpusRequest.preference_signals?.senior
      && !corpusRequest.preference_signals?.couple;
    if (shouldUseStaticFastPath) {
      const corpusMatch = await findPrecomputedTravelRoutes(intent);
      if (corpusMatch.matched) {
        const corpusResponse = await buildPlanningResponseFromRouteCorpus({ intent, match: corpusMatch, request: corpusRequest });
        if (!hasBadUserVisiblePoiInResponse(corpusResponse.planning_response)) return corpusResponse;
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
        parsed_request: requestFromGoalAndIntent(rawGoal, payload.defaults, intent),
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
  if (previous.route_mode === 'culture' && !hasExplicitFoodTerm) {
    parsed.route_mode = 'culture';
    parsed.preference_signals = {
      ...(parsed.preference_signals || {}),
      lunch: false,
      formal_meal: false,
      coffee: false,
      snack: false,
    };
  }
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
}
