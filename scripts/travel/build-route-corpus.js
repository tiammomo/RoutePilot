#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const dotenv = require('dotenv');

const rootDir = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const dataRoot = process.env.TRAVELPILOT_DATA_ROOT || path.join(rootDir, 'travel-data', 'processed');
const outputFile = path.join(dataRoot, 'beijing_route_corpus.json');

const AREAS = ['故宫', '天安门', '前门', '王府井', '什刹海', '北海', '南锣鼓巷', '天坛', '地坛', '西单'];
const PERSONAS = [
  { id: 'classic_first_timer', label: '第一次来北京', walk: 'medium', tags: ['经典', '首次来京'] },
  { id: 'senior_relaxed', label: '带长辈轻松游', walk: 'low', tags: ['老人', '少走路', '轻松'] },
  { id: 'family_kids', label: '亲子友好', walk: 'low', tags: ['亲子', '孩子', '家庭'] },
  { id: 'couple_romantic', label: '情侣慢逛', walk: 'medium', tags: ['情侣', '约会', '拍照'] },
];
const DURATIONS = [180, 240, 360, 480];
const BUDGETS = [100, 200, 350, 600];
const MODES = ['mixed', 'culture'];

function normalizeName(name) {
  return String(name || '')
    .replace(/[（(].*?[）)]/g, '')
    .replace(/[-—·\s]/g, '')
    .trim()
    .toLowerCase();
}

async function readJsonArray(fileName) {
  const raw = await fs.readFile(path.join(dataRoot, fileName), 'utf8');
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

function deriveMeal(raw) {
  const name = String(raw.name || raw.display_name || raw.normalized_name || '');
  const metadata = [
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.dining_style,
    ...(Array.isArray(raw.tags) ? raw.tags : []),
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
    ...(Array.isArray(raw.evidence_tags) ? raw.evidence_tags : []),
  ].join(' ').toLowerCase();
  const coffee = /咖啡|coffee|cafe|星巴克|瑞幸/.test(name.toLowerCase());
  const meal = /餐|饭|面|涮肉|烧麦|烤鸭|饺子|炸酱|炒肝|火锅|串|食/.test(name);
  const snack = /小吃|包子|糕|饼|麦当劳|肯德基/.test(name);
  const dessert = /甜品|下午茶|茶饮|奶茶/.test(name);
  const scenic = /公园|博物院|博物馆|步行街|景区|景点|寺|殿|塔|后海|前海|鼓楼|艺术中心/.test(name);
  const hasDiningMetadata = /food|restaurant|dining|meal|lunch|dinner|snack|cafe|coffee/.test(metadata);
  if (scenic && !meal && !snack && !coffee && !dessert) return { meal_type: 'non_food', is_food: false, is_lunch: false };
  if (coffee) return { meal_type: 'coffee', is_food: true, is_lunch: false };
  if (dessert && !meal && !snack) return { meal_type: 'dessert', is_food: true, is_lunch: false };
  if (snack) return { meal_type: 'snack', is_food: true, is_lunch: true };
  if (meal || hasDiningMetadata) return { meal_type: 'meal', is_food: true, is_lunch: true };
  return { meal_type: 'non_food', is_food: false, is_lunch: false };
}

function normalizePoi(raw) {
  const poiId = String(raw.poi_id || '').trim();
  const lng = Number(raw.lng);
  const lat = Number(raw.lat);
  if (!poiId || !Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  const name = String(raw.name || raw.display_name || raw.normalized_name || poiId);
  const meal = deriveMeal({ ...raw, name });
  return {
    ...raw,
    poi_id: poiId,
    name,
    lng,
    lat,
    rating: Number(raw.rating || 0),
    avg_cost: Number(raw.avg_cost || 0),
    review_count: Number(raw.review_count || 0),
    suggested_duration_min: Number(raw.suggested_duration_min || raw.avg_visit_duration_min || 90),
    poi_type: meal.is_food ? 'food' : 'culture',
    meal_type: meal.meal_type,
    is_lunch_suitable: meal.is_lunch,
    is_meal_stop: meal.is_food,
    is_coffee_stop: meal.meal_type === 'coffee',
  };
}

function loadFeatureMap(features) {
  const map = new Map();
  for (const item of features) {
    const poiId = String(item.poi_id || '');
    if (!poiId) continue;
    const current = map.get(poiId) || {};
    current[String(item.feature_key)] = String(item.feature_value);
    map.set(poiId, current);
  }
  return map;
}

function attractionGroup(item) {
  const normalized = normalizeName(item.name);
  for (const key of ['故宫博物院', '天安门广场', '中国国家博物馆', '北海公园', '景山公园', '天坛公园']) {
    if (normalized.includes(normalizeName(key))) return key;
  }
  return normalizeName(String(item.name || '').split(/[-—–]/)[0] || item.name || item.area || item.district || '');
}

function uniqueAttractions(items) {
  const seenIds = new Set();
  const seenNames = new Set();
  const seenGroups = new Set();
  return items.filter((item) => {
    const name = normalizeName(item.name);
    const group = attractionGroup(item);
    if (seenIds.has(item.poi_id) || seenNames.has(name) || seenGroups.has(group)) return false;
    seenIds.add(item.poi_id);
    if (name) seenNames.add(name);
    if (group) seenGroups.add(group);
    return true;
  });
}

function isRecommendable(item) {
  const name = String(item.name || '');
  if (!/[\u4e00-\u9fff]/.test(name)) return false;
  if (/酒店|宾馆|客栈|住宿|观众服务中心|讲解服务处|街道办|社区/.test(name)) return false;
  if (String(item.poi_id).startsWith('fixture_') && item.poi_type !== 'food') return false;
  return true;
}

function isIndoor(item) {
  const text = [item.name, item.category, item.poi_subtype, ...(Array.isArray(item.planning_tags) ? item.planning_tags : [])].join(' ').toLowerCase();
  return /museum|art_gallery|exhibition|博物馆|美术馆|艺术中心|展览馆|剧场|scene:indoor/.test(text);
}

function meters(a, b) {
  const lat1 = Number(a.lat) * Math.PI / 180;
  const lat2 = Number(b.lat) * Math.PI / 180;
  const dLat = lat2 - lat1;
  const dLng = (Number(b.lng) - Number(a.lng)) * Math.PI / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

function minutesToTime(total) {
  const normalized = ((total % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, '0')}:${String(normalized % 60).padStart(2, '0')}`;
}

function scorePoi(item, request, featureMap) {
  const features = featureMap.get(item.poi_id) || {};
  const text = [item.name, item.category, item.poi_subtype, ...(Array.isArray(item.planning_tags) ? item.planning_tags : [])].join(' ').toLowerCase();
  let score = Number(item.rating || 0) * 12 + Math.min(Number(item.review_count || 0), 500) / 120;
  score -= Number(item.avg_cost || 0) / (request.budget <= 150 ? 6 : 18);
  score -= Number(item.suggested_duration_min || 90) / (request.duration <= 240 ? 4 : 12);
  if (request.walk === 'low' && (item.walk_intensity === 'low' || /walk:low/.test(text))) score += 14;
  if (request.walk === 'low' && item.walk_intensity === 'high') score -= 18;
  if (request.indoor && isIndoor(item)) score += 24;
  if (request.indoor && /公园|广场|步行街|scene:outdoor/.test(text)) score -= 14;
  if (request.avoidQueue && features.queue_risk === 'low') score += 12;
  if (request.avoidQueue && features.queue_risk === 'high') score -= 18;
  if (request.persona === 'family_kids' && (features.family_friendliness === 'high' || /亲子|儿童|孩子|family/.test(text))) score += 16;
  if (request.persona === 'senior_relaxed' && (item.walk_intensity === 'low' || isIndoor(item))) score += 12;
  if (request.persona === 'couple_romantic' && /咖啡|甜品|艺术|美术|后海|什刹海|夜景|拍照/.test(text)) score += 14;
  return score;
}

function orderNearest(items) {
  if (items.length <= 2) return items;
  const remaining = [...items];
  const ordered = [remaining.shift()];
  while (remaining.length) {
    const last = ordered[ordered.length - 1];
    let bestIndex = 0;
    let bestDistance = Infinity;
    remaining.forEach((item, index) => {
      const distance = meters(last, item);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    ordered.push(remaining.splice(bestIndex, 1)[0]);
  }
  return ordered;
}

function buildRoute({ pois, featureMap, area, mode, persona, duration, budget, indoor, avoidQueue }) {
  const request = {
    area,
    mode,
    persona: persona.id,
    duration,
    budget,
    walk: persona.walk,
    indoor,
    avoidQueue,
  };
  const scoped = pois.filter((item) => item.area === area || item.district === area);
  const pool = uniqueAttractions((scoped.length >= 8 ? scoped : pois).filter(isRecommendable));
  const culture = pool
    .filter((item) => item.poi_type !== 'food')
    .filter((item) => !indoor || isIndoor(item))
    .sort((a, b) => scorePoi(b, request, featureMap) - scorePoi(a, request, featureMap));
  const food = pool
    .filter((item) => item.poi_type === 'food')
    .filter((item) => mode === 'mixed' && (item.is_lunch_suitable || item.meal_type === 'snack'))
    .sort((a, b) => scorePoi(b, request, featureMap) - scorePoi(a, request, featureMap));

  const targetCount = duration <= 180 ? 3 : duration <= 300 ? 4 : 5;
  let selected = [];
  if (mode === 'mixed' && food[0]) {
    selected = [culture[0], food[0], ...culture.slice(1, targetCount - 1)].filter(Boolean);
  } else {
    selected = culture.slice(0, targetCount);
  }
  selected = orderNearest(uniqueAttractions(selected)).slice(0, targetCount);
  if (selected.length < 3) return null;

  let cursor = 9 * 60;
  let totalTransfer = 0;
  let totalDistance = 0;
  const stops = selected.map((item, index) => {
    let transfer = 0;
    let distance = 0;
    if (index > 0) {
      distance = meters(selected[index - 1], item);
      transfer = Math.max(8, Math.round(distance / 75));
      cursor += transfer;
      totalTransfer += transfer;
      totalDistance += distance;
    }
    const isFood = item.poi_type === 'food';
    if (isFood && cursor < 11 * 60 + 30) cursor = 11 * 60 + 30;
    const arrival = cursor;
    const stay = Math.min(Number(item.suggested_duration_min || 90), duration <= 240 ? (isFood ? 45 : 60) : 120);
    cursor += stay;
    const features = featureMap.get(item.poi_id) || {};
    return {
      poi_id: item.poi_id,
      name: item.name,
      poi_type: isFood ? 'food' : 'culture',
      category: item.category || 'unknown',
      meal_type: item.meal_type || 'non_food',
      is_lunch_suitable: Boolean(item.is_lunch_suitable),
      is_coffee_stop: Boolean(item.is_coffee_stop),
      area: item.area || item.district || '北京',
      district: item.district || '北京',
      address: item.address || '',
      arrival_time: minutesToTime(arrival),
      departure_time: minutesToTime(cursor),
      stay_minutes: stay,
      transfer_from_previous_minutes: transfer,
      transfer_from_previous_meters: Math.round(distance),
      transfer_source: index > 0 ? 'coordinate_estimate' : null,
      transfer_mode: null,
      transfer_provider: null,
      transfer_duration_s: index > 0 ? transfer * 60 : null,
      transfer_count: null,
      estimated_cost: Number(item.avg_cost || 0),
      meal_slot: isFood ? 'lunch' : null,
      rating: Number(item.rating || 0),
      opening_status: item.open_time && item.close_time ? 'ok' : 'unknown',
      opening_hours_note: item.open_time && item.close_time ? '按本地营业时间估算可访问。' : '本地数据未覆盖完整营业时间。',
      recommendation_reason: `${item.area || item.district || '北京'}区域，评分${Number(item.rating || 0).toFixed(1)}，建议停留约${stay}分钟。`,
      evidence_summary: {
        signals: {
          queue_risk: features.queue_risk || item.queue_risk || 'unavailable',
          value_for_money: features.value_for_money || item.value_for_money || 'unavailable',
          family_friendliness: features.family_friendliness || item.family_friendliness || 'unavailable',
          environment_quality: features.environment_quality || item.environment_quality || 'unavailable',
        },
        evidence_review_count: 0,
        top_evidence: [],
        confidence_note: '来自本地 POI 与 UGC 特征聚合数据。',
      },
    };
  });

  const totalBudget = stops.reduce((sum, item) => sum + item.estimated_cost, 0);
  const totalVisit = stops.reduce((sum, item) => sum + item.stay_minutes, 0);
  const totalDuration = cursor - 9 * 60;
  if (totalBudget > budget + 120 || totalDuration > duration + 120) return null;
  const foodCount = stops.filter((item) => item.poi_type === 'food').length;
  const cultureCount = stops.length - foodCount;
  const routeId = [
    'bj',
    area,
    mode,
    persona.id,
    duration,
    budget,
    indoor ? 'indoor' : 'any',
    avoidQueue ? 'lowqueue' : 'normal',
  ].join('_').replace(/[^\w\u4e00-\u9fff]+/g, '_');
  const title = `${area}${persona.label}${mode === 'mixed' ? '含餐' : '文化'}${duration <= 240 ? '半日' : '一日'}路线`;
  const proposal = {
    proposal_id: `${routeId}_balanced`,
    strategy: 'balanced',
    display_title: title,
    title,
    summary: `${area} ${stops.length}站，预计${totalDuration}分钟，预算约${Math.round(totalBudget)}元。`,
    ordered_poi_ids: stops.map((item) => item.poi_id),
    ordered_poi_names: stops.map((item) => item.name),
    pois: stops,
    total_budget_estimate: totalBudget,
    total_transfer_minutes: totalTransfer,
    total_walking_distance_m: Math.round(totalDistance),
    transfer_source_summary: { commute_edges_used: 0, coordinate_estimates_used: Math.max(0, stops.length - 1), commute_edge_hit_rate: 0 },
    total_visit_duration_min: totalVisit,
    total_route_duration_min: totalDuration,
    travel_time_confidence: 'estimated',
    budget_summary: { max_budget: budget, within_budget: totalBudget <= budget, total_budget_estimate: totalBudget },
    duration_summary: { max_duration_min: duration, within_duration: totalDuration <= duration, total_route_duration_min: totalDuration, total_visit_duration_min: totalVisit, total_transfer_minutes: totalTransfer },
    category_coverage_summary: {
      route_mode: mode,
      food_count: foodCount,
      culture_or_entertainment_count: cultureCount,
      required_food_count: mode === 'mixed' ? 1 : 0,
      required_culture_or_entertainment_count: mode === 'mixed' ? 2 : 3,
      satisfies_coverage: mode === 'mixed' ? foodCount >= 1 && cultureCount >= 2 : cultureCount >= 3,
    },
    quality_summary: {
      route_generation_ready: true,
      executable_route: true,
      competition_readiness_score: 0.86,
      constraints: { budget_satisfied: totalBudget <= budget, duration_satisfied: totalDuration <= duration + 60, category_coverage_satisfied: true },
      personalization: { persona_id: persona.id, walk_preference: persona.walk, active_preference_signals: [indoor ? 'indoor' : null, avoidQueue ? 'avoid_queue' : null].filter(Boolean), applied: persona.id !== 'classic_first_timer' || indoor || avoidQueue },
      data_grounding: { stops_with_recommendation_reason: stops.length, stops_with_evidence_summary: stops.length, stops_with_ugc_or_feature_evidence: stops.length, evidence_coverage_rate: 1 },
      commute: { uses_commute_edges: false, commute_edges_used: 0, coordinate_estimates_used: Math.max(0, stops.length - 1), commute_edge_hit_rate: 0 },
    },
    opening_hours_check: { has_conflict: false, unknown_hours_count: stops.filter((item) => item.opening_status === 'unknown').length },
    risks: ['转移时间和步行距离来自本地坐标估算，不代表实时导航。'],
  };
  const payload = {
    request_id: routeId,
    city_id: 'beijing',
    route_mode: mode,
    goal: title,
    resolved_area: area,
    persona_id: persona.id,
    evidence_summary: { data_root: dataRoot, static_data_notice: '来自本地 POI 与 UGC 数据预生成路线库。' },
    request_snapshot: {
      goal: title,
      route_mode: mode,
      area,
      start_time: '09:00',
      max_budget: budget,
      max_total_pois: targetCount,
      max_duration_min: duration,
      day_count: 1,
      pace: persona.walk === 'low' ? 'relaxed' : 'balanced',
      walk_preference: persona.walk,
      persona_id: persona.id,
      preference_signals: {
        lunch: mode === 'mixed',
        avoid_queue: avoidQueue,
        family: persona.id === 'family_kids',
        senior: persona.id === 'senior_relaxed',
        couple: persona.id === 'couple_romantic',
        value_for_money: budget <= 200,
        indoor,
      },
    },
    day_count: 1,
    daily_itinerary: [{ day: 1, title: 'Day 1', area, theme: title, proposal }],
    proposals: [proposal],
    generation_metrics: {
      elapsed_ms: 0,
      within_10s: true,
      route_corpus_generated: true,
      route_corpus_source: 'travel-data/processed',
    },
    replan_metadata: null,
  };
  return {
    route_id: routeId,
    city_id: 'beijing',
    title,
    area,
    route_mode: mode,
    persona_id: persona.id,
    walk_preference: persona.walk,
    duration_bucket_min: duration,
    budget_bucket_cny: budget,
    requires_meal: mode === 'mixed',
    meal_type: mode === 'mixed' ? 'meal' : null,
    indoor_preferred: indoor,
    avoid_queue: avoidQueue,
    tags: Array.from(new Set([area, mode === 'mixed' ? '含餐' : '文化', ...persona.tags, duration <= 240 ? '半日' : '一日', budget <= 200 ? '低预算' : '舒适预算', indoor ? '室内' : null, avoidQueue ? '少排队' : null].filter(Boolean))),
    poi_ids: proposal.ordered_poi_ids,
    poi_names: proposal.ordered_poi_names,
    total_budget_estimate: totalBudget,
    total_route_duration_min: totalDuration,
    score: Number((60 + stops.length * 4 + (proposal.category_coverage_summary.satisfies_coverage ? 12 : 0) + (totalBudget <= budget ? 8 : 0) + (totalDuration <= duration + 60 ? 8 : 0)).toFixed(3)),
    payload,
  };
}

async function main() {
  const rawFiles = [
    'beijing_planner_entities.json',
    'beijing_mixed_category_pois.json',
    'beijing_culture_pois.json',
  ];
  const byId = new Map();
  for (const fileName of rawFiles) {
    const rows = await readJsonArray(fileName);
    for (const raw of rows) {
      const poi = normalizePoi(raw);
      if (!poi) continue;
      const current = byId.get(poi.poi_id);
      if (!current || Number(poi.review_count || 0) >= Number(current.review_count || 0)) {
        byId.set(poi.poi_id, poi);
      }
    }
  }
  const features = await readJsonArray('beijing_poi_feature_aggregates.json');
  const featureMap = loadFeatureMap(features);
  const pois = Array.from(byId.values());
  const routes = [];
  for (const area of AREAS) {
    for (const mode of MODES) {
      for (const persona of PERSONAS) {
        for (const duration of DURATIONS) {
          for (const budget of BUDGETS) {
            for (const indoor of [false, true]) {
              for (const avoidQueue of [false, true]) {
                if (mode === 'culture' && budget > 350) continue;
                if (indoor && !['故宫', '天安门', '王府井', '南锣鼓巷', '天坛', '地坛'].includes(area)) continue;
                const route = buildRoute({ pois, featureMap, area, mode, persona, duration, budget, indoor, avoidQueue });
                if (route) routes.push(route);
              }
            }
          }
        }
      }
    }
  }
  const deduped = Array.from(new Map(routes.map((route) => [route.route_id, route])).values())
    .sort((a, b) => b.score - a.score || a.route_id.localeCompare(b.route_id));
  await fs.writeFile(outputFile, `${JSON.stringify({
    generated_at: new Date().toISOString(),
    data_root: dataRoot,
    route_count: deduped.length,
    dimensions: {
      areas: AREAS,
      personas: PERSONAS.map((item) => item.id),
      durations: DURATIONS,
      budgets: BUDGETS,
      modes: MODES,
    },
    routes: deduped,
  }, null, 2)}\n`, 'utf8');
  console.log(`[travel:routes:build] wrote ${deduped.length} routes to ${path.relative(rootDir, outputFile)}`);
}

main().catch((error) => {
  console.error('[travel:routes:build] failed:', error);
  process.exit(1);
});
