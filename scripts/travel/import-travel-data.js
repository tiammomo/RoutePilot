#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
const DEFAULT_DATA_ROOT = path.join(rootDir, 'travel-data', 'processed');
const dataRoot = process.env.TRAVELPILOT_DATA_ROOT || DEFAULT_DATA_ROOT;

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const prisma = new PrismaClient();

async function readJsonArray(fileName) {
  const raw = await fs.readFile(path.join(dataRoot, fileName), 'utf8');
  const parsed = JSON.parse(raw);
  return Array.isArray(parsed) ? parsed : [];
}

async function readOptionalJsonArray(fileName) {
  try {
    return await readJsonArray(fileName);
  } catch (error) {
    if (error?.code === 'ENOENT') return [];
    throw error;
  }
}

function asTextArray(value) {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function inferPoiKind(raw) {
  if (raw.poi_kind === 'hotel' || raw.poi_type === 'accommodation' || raw.entity_kind === 'hotel') return 'hotel';
  const text = [
    raw.poi_type,
    raw.poi_subtype,
    raw.category,
    raw.meal_type,
    ...(Array.isArray(raw.tags) ? raw.tags : []),
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
  ].join(' ').toLowerCase();
  if (/food|restaurant|dining|meal|snack|coffee|cafe|餐|饭|咖啡|小吃|美食/.test(text)) return 'restaurant';
  return 'attraction';
}

function deriveMealSemantics(raw) {
  const name = String(raw.name || raw.display_name || raw.normalized_name || '');
  const metadata = [
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.dining_style,
    ...(Array.isArray(raw.tags) ? raw.tags : []),
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
    ...(Array.isArray(raw.evidence_tags) ? raw.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');
  const coffee = /咖啡|coffee|cafe|星巴克|瑞幸/.test(name.toLowerCase());
  const meal = /餐|饭|面|涮肉|烧麦|烤鸭|饺子|炸酱|炒肝|火锅|串|食/.test(name);
  const snack = /小吃|包子|糕|饼|麦当劳|肯德基/.test(name);
  const dessert = /甜品|下午茶|茶饮|奶茶/.test(name);
  const hasDiningMetadata = /food|restaurant|dining|meal|lunch|dinner|snack|cafe|coffee/.test(metadata);
  if (coffee) return { meal_type: 'coffee', is_lunch_suitable: false, is_coffee_stop: true, is_meal_stop: true };
  if (dessert && !meal && !snack) return { meal_type: 'dessert', is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: true };
  if (snack) return { meal_type: 'snack', is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
  if (meal || hasDiningMetadata) return { meal_type: 'meal', is_lunch_suitable: true, is_coffee_stop: false, is_meal_stop: true };
  return { meal_type: 'non_food', is_lunch_suitable: false, is_coffee_stop: false, is_meal_stop: false };
}

function normalizePoi(raw) {
  const poiId = String(raw.poi_id || '').trim();
  if (!poiId) return null;
  const lng = Number(raw.lng);
  const lat = Number(raw.lat);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  const name = String(raw.name || raw.display_name || raw.normalized_name || poiId);
  const meal = deriveMealSemantics({ ...raw, name });
  const isHotel = raw.poi_kind === 'hotel' || raw.poi_type === 'accommodation' || raw.entity_kind === 'hotel';
  return {
    poi_id: poiId,
    name,
    city: String(raw.city || 'beijing'),
    district: raw.district ? String(raw.district) : null,
    area: raw.area ? String(raw.area) : null,
    category: raw.category ? String(raw.category) : isHotel ? 'accommodation' : null,
    poi_type: isHotel ? 'accommodation' : meal.is_meal_stop ? 'food' : String(raw.poi_type || 'culture'),
    poi_kind: inferPoiKind(raw),
    address: raw.address ? String(raw.address) : null,
    lng,
    lat,
    rating: raw.rating === undefined || raw.rating === null ? null : Number(raw.rating),
    avg_cost: raw.avg_cost === undefined || raw.avg_cost === null ? null : Number(raw.avg_cost),
    review_count: raw.review_count === undefined || raw.review_count === null ? null : Number(raw.review_count),
    source: String(raw.source || 'travel-data/processed'),
    source_poi_id: raw.source_poi_id ? String(raw.source_poi_id) : null,
    entity_kind: raw.entity_kind ? String(raw.entity_kind) : isHotel ? 'hotel' : null,
    display_name: raw.display_name ? String(raw.display_name) : name,
    normalized_name: raw.normalized_name ? String(raw.normalized_name) : name,
    alias_names: JSON.stringify(asTextArray(raw.alias_names)),
    area_key: raw.area_key ? String(raw.area_key) : null,
    poi_subtype: raw.poi_subtype ? String(raw.poi_subtype) : isHotel ? 'hotel' : null,
    tags: JSON.stringify(asTextArray(raw.tags)),
    suggested_duration_min: isHotel ? 0 : raw.suggested_duration_min === undefined || raw.suggested_duration_min === null ? null : Number(raw.suggested_duration_min),
    open_time: raw.open_time ? String(raw.open_time) : null,
    close_time: raw.close_time ? String(raw.close_time) : null,
    open_hours: JSON.stringify(raw.open_hours || {}),
    meal_type: isHotel ? 'hotel_dining' : meal.meal_type,
    is_lunch_suitable: isHotel ? false : meal.is_lunch_suitable,
    is_coffee_stop: isHotel ? false : meal.is_coffee_stop,
    is_meal_stop: isHotel ? false : meal.is_meal_stop,
    walk_intensity: raw.walk_intensity ? String(raw.walk_intensity) : null,
    raw: JSON.stringify(raw),
  };
}

async function loadPois() {
  const files = [
    'beijing_planner_entities.json',
    'beijing_mixed_category_pois.json',
    'beijing_culture_pois.json',
  ];
  const byId = new Map();
  for (const fileName of files) {
    const items = await readJsonArray(fileName);
    for (const raw of items) {
      const poi = normalizePoi(raw);
      if (!poi) continue;
      const existing = byId.get(poi.poi_id);
      if (!existing || Number(poi.review_count || 0) >= Number(existing.review_count || 0)) {
        byId.set(poi.poi_id, poi);
      }
    }
  }
  const hotels = await readOptionalJsonArray('beijing_hotels.json');
  for (const raw of hotels) {
    const poi = normalizePoi({
      ...raw,
      category: raw.category || 'accommodation',
      poi_type: 'accommodation',
      poi_kind: 'hotel',
      entity_kind: 'hotel',
      poi_subtype: raw.poi_subtype || raw.raw?.keytag || 'hotel',
      tags: ['hotel', 'accommodation', raw.raw?.keytag, raw.raw?.business_area].filter(Boolean),
    });
    if (!poi) continue;
    byId.set(poi.poi_id, poi);
  }
  return Array.from(byId.values());
}

async function upsertPois(pois) {
  for (const poi of pois) {
    await prisma.$executeRaw`
      INSERT INTO travel_pois (
        poi_id, name, city, district, area, category, poi_type, poi_kind, address,
        lng, lat, rating, avg_cost, review_count, source, source_poi_id, entity_kind,
        display_name, normalized_name, alias_names, area_key, poi_subtype, tags,
        suggested_duration_min, open_time, close_time, open_hours, meal_type,
        is_lunch_suitable, is_coffee_stop, is_meal_stop, walk_intensity, raw, updated_at
      )
      VALUES (
        ${poi.poi_id}, ${poi.name}, ${poi.city}, ${poi.district}, ${poi.area}, ${poi.category},
        ${poi.poi_type}, ${poi.poi_kind}, ${poi.address}, ${poi.lng}, ${poi.lat}, ${poi.rating},
        ${poi.avg_cost}, ${poi.review_count}, ${poi.source}, ${poi.source_poi_id}, ${poi.entity_kind},
        ${poi.display_name}, ${poi.normalized_name}, CAST(${poi.alias_names} AS jsonb), ${poi.area_key},
        ${poi.poi_subtype}, CAST(${poi.tags} AS jsonb), ${poi.suggested_duration_min}, ${poi.open_time},
        ${poi.close_time}, CAST(${poi.open_hours} AS jsonb), ${poi.meal_type}, ${poi.is_lunch_suitable},
        ${poi.is_coffee_stop}, ${poi.is_meal_stop}, ${poi.walk_intensity}, CAST(${poi.raw} AS jsonb), NOW()
      )
      ON CONFLICT (poi_id) DO UPDATE SET
        name = EXCLUDED.name,
        city = EXCLUDED.city,
        district = EXCLUDED.district,
        area = EXCLUDED.area,
        category = EXCLUDED.category,
        poi_type = EXCLUDED.poi_type,
        poi_kind = EXCLUDED.poi_kind,
        address = EXCLUDED.address,
        lng = EXCLUDED.lng,
        lat = EXCLUDED.lat,
        rating = EXCLUDED.rating,
        avg_cost = EXCLUDED.avg_cost,
        review_count = EXCLUDED.review_count,
        source = EXCLUDED.source,
        source_poi_id = EXCLUDED.source_poi_id,
        entity_kind = EXCLUDED.entity_kind,
        display_name = EXCLUDED.display_name,
        normalized_name = EXCLUDED.normalized_name,
        alias_names = EXCLUDED.alias_names,
        area_key = EXCLUDED.area_key,
        poi_subtype = EXCLUDED.poi_subtype,
        tags = EXCLUDED.tags,
        suggested_duration_min = EXCLUDED.suggested_duration_min,
        open_time = EXCLUDED.open_time,
        close_time = EXCLUDED.close_time,
        open_hours = EXCLUDED.open_hours,
        meal_type = EXCLUDED.meal_type,
        is_lunch_suitable = EXCLUDED.is_lunch_suitable,
        is_coffee_stop = EXCLUDED.is_coffee_stop,
        is_meal_stop = EXCLUDED.is_meal_stop,
        walk_intensity = EXCLUDED.walk_intensity,
        raw = EXCLUDED.raw,
        updated_at = NOW()
    `;
  }
}

async function upsertFeatures() {
  const features = await readJsonArray('beijing_poi_feature_aggregates.json');
  let count = 0;
  for (const raw of features) {
    const poiId = String(raw.poi_id || '').trim();
    const key = String(raw.feature_key || '').trim();
    const value = String(raw.feature_value || '').trim();
    if (!poiId || !key || !value) continue;
    const id = `${poiId}:${key}`;
    await prisma.$executeRaw`
      INSERT INTO travel_poi_features (
        id, poi_id, feature_key, feature_value, status, confidence, evidence_refs,
        review_count_used, source_platforms, source_weight, ugc_coverage_level,
        evidence_quality, extraction_version, last_computed, raw, updated_at
      )
      VALUES (
        ${id}, ${poiId}, ${key}, ${value}, ${raw.status ? String(raw.status) : null},
        ${raw.confidence ? String(raw.confidence) : null}, ${asTextArray(raw.evidence_refs)},
        ${raw.review_count_used === undefined ? null : Number(raw.review_count_used)},
        ${asTextArray(raw.source_platforms)}, ${raw.source_weight === undefined ? null : Number(raw.source_weight)},
        ${raw.ugc_coverage_level ? String(raw.ugc_coverage_level) : null},
        ${raw.evidence_quality ? String(raw.evidence_quality) : null},
        ${raw.extraction_version ? String(raw.extraction_version) : null},
        ${raw.last_computed ? new Date(raw.last_computed) : null},
        CAST(${JSON.stringify(raw)} AS jsonb), NOW()
      )
      ON CONFLICT (poi_id, feature_key) DO UPDATE SET
        feature_value = EXCLUDED.feature_value,
        status = EXCLUDED.status,
        confidence = EXCLUDED.confidence,
        evidence_refs = EXCLUDED.evidence_refs,
        review_count_used = EXCLUDED.review_count_used,
        source_platforms = EXCLUDED.source_platforms,
        source_weight = EXCLUDED.source_weight,
        ugc_coverage_level = EXCLUDED.ugc_coverage_level,
        evidence_quality = EXCLUDED.evidence_quality,
        extraction_version = EXCLUDED.extraction_version,
        last_computed = EXCLUDED.last_computed,
        raw = EXCLUDED.raw,
        updated_at = NOW()
    `;
    count += 1;
  }
  return count;
}

async function upsertReviews() {
  const reviews = await readJsonArray('beijing_review_records.json');
  let count = 0;
  for (const raw of reviews) {
    const reviewId = String(raw.review_id || '').trim();
    const poiId = String(raw.poi_id || '').trim();
    const text = String(raw.review_text || '').trim();
    if (!reviewId || !poiId || !text) continue;
    await prisma.$executeRaw`
      INSERT INTO travel_reviews (
        review_id, poi_id, source_platform, source_review_id, review_text, rating,
        review_time, author_name, evidence_source, raw, last_updated, updated_at
      )
      VALUES (
        ${reviewId}, ${poiId}, ${raw.source_platform ? String(raw.source_platform) : null},
        ${raw.source_review_id ? String(raw.source_review_id) : null}, ${text},
        ${raw.rating === undefined ? null : Number(raw.rating)},
        ${raw.review_time ? new Date(raw.review_time) : null},
        ${raw.author_name ? String(raw.author_name) : null},
        CAST(${JSON.stringify(raw.evidence_source || [])} AS jsonb),
        CAST(${JSON.stringify(raw.raw || raw)} AS jsonb),
        ${raw.last_updated ? new Date(raw.last_updated) : null}, NOW()
      )
      ON CONFLICT (review_id) DO UPDATE SET
        poi_id = EXCLUDED.poi_id,
        source_platform = EXCLUDED.source_platform,
        source_review_id = EXCLUDED.source_review_id,
        review_text = EXCLUDED.review_text,
        rating = EXCLUDED.rating,
        review_time = EXCLUDED.review_time,
        author_name = EXCLUDED.author_name,
        evidence_source = EXCLUDED.evidence_source,
        raw = EXCLUDED.raw,
        last_updated = EXCLUDED.last_updated,
        updated_at = NOW()
    `;
    count += 1;
  }
  return count;
}

async function rebuildAreas() {
  await prisma.$executeRaw`
    INSERT INTO travel_areas (
      area_key, area_name, city, district, poi_count, culture_count, food_count,
      avg_rating, avg_cost, top_tags, raw, updated_at
    )
    SELECT
      COALESCE(area_key, lower(regexp_replace(COALESCE(area, district, 'beijing'), '\\s+', '_', 'g'))) AS area_key,
      COALESCE(area, district, '北京') AS area_name,
      COALESCE(MAX(city), 'beijing') AS city,
      MAX(district) AS district,
      COUNT(*)::int AS poi_count,
      COUNT(*) FILTER (WHERE poi_type <> 'food' AND poi_type <> 'accommodation')::int AS culture_count,
      COUNT(*) FILTER (WHERE poi_type = 'food' OR poi_kind = 'restaurant')::int AS food_count,
      AVG(rating) AS avg_rating,
      AVG(NULLIF(avg_cost, 0)) AS avg_cost,
      '[]'::jsonb AS top_tags,
      jsonb_build_object('source', 'import-travel-data') AS raw,
      NOW()
    FROM travel_pois
    GROUP BY 1, 2
    ON CONFLICT (area_key) DO UPDATE SET
      area_name = EXCLUDED.area_name,
      city = EXCLUDED.city,
      district = EXCLUDED.district,
      poi_count = EXCLUDED.poi_count,
      culture_count = EXCLUDED.culture_count,
      food_count = EXCLUDED.food_count,
      avg_rating = EXCLUDED.avg_rating,
      avg_cost = EXCLUDED.avg_cost,
      raw = EXCLUDED.raw,
      updated_at = NOW()
  `;
  const rows = await prisma.$queryRaw`SELECT COUNT(*)::int AS count FROM travel_areas`;
  return Number(rows[0]?.count || 0);
}

async function readRouteCorpus() {
  const file = path.join(dataRoot, 'beijing_route_corpus.json');
  try {
    const raw = await fs.readFile(file, 'utf8');
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed.routes) ? parsed.routes : [];
  } catch {
    return [];
  }
}

async function upsertRouteCorpus() {
  const routes = await readRouteCorpus();
  let count = 0;
  for (const route of routes) {
    const routeId = String(route.route_id || '').trim();
    if (!routeId) continue;
    await prisma.$executeRaw`
      INSERT INTO travel_precomputed_routes (
        route_id, city_id, title, area, route_mode, persona_id, walk_preference,
        duration_bucket_min, budget_bucket_cny, requires_meal, meal_type,
        indoor_preferred, avoid_queue, tags, poi_ids, poi_names,
        total_budget_estimate, total_route_duration_min, score, payload, source, updated_at
      )
      VALUES (
        ${routeId}, ${String(route.city_id || 'beijing')}, ${String(route.title || '北京旅行路线')},
        ${route.area ? String(route.area) : null}, ${String(route.route_mode || 'mixed')},
        ${String(route.persona_id || 'classic_first_timer')}, ${String(route.walk_preference || 'medium')},
        ${Number(route.duration_bucket_min || 0)}, ${route.budget_bucket_cny === null || route.budget_bucket_cny === undefined ? null : Number(route.budget_bucket_cny)},
        ${Boolean(route.requires_meal)}, ${route.meal_type ? String(route.meal_type) : null},
        ${Boolean(route.indoor_preferred)}, ${Boolean(route.avoid_queue)},
        ${Array.isArray(route.tags) ? route.tags.map(String) : []},
        ${Array.isArray(route.poi_ids) ? route.poi_ids.map(String) : []},
        ${Array.isArray(route.poi_names) ? route.poi_names.map(String) : []},
        ${Number(route.total_budget_estimate || 0)}, ${Number(route.total_route_duration_min || 0)},
        ${Number(route.score || 0)}, CAST(${JSON.stringify(route.payload || {})} AS jsonb),
        'travel-data/processed/beijing_route_corpus.json', NOW()
      )
      ON CONFLICT (route_id) DO UPDATE SET
        city_id = EXCLUDED.city_id,
        title = EXCLUDED.title,
        area = EXCLUDED.area,
        route_mode = EXCLUDED.route_mode,
        persona_id = EXCLUDED.persona_id,
        walk_preference = EXCLUDED.walk_preference,
        duration_bucket_min = EXCLUDED.duration_bucket_min,
        budget_bucket_cny = EXCLUDED.budget_bucket_cny,
        requires_meal = EXCLUDED.requires_meal,
        meal_type = EXCLUDED.meal_type,
        indoor_preferred = EXCLUDED.indoor_preferred,
        avoid_queue = EXCLUDED.avoid_queue,
        tags = EXCLUDED.tags,
        poi_ids = EXCLUDED.poi_ids,
        poi_names = EXCLUDED.poi_names,
        total_budget_estimate = EXCLUDED.total_budget_estimate,
        total_route_duration_min = EXCLUDED.total_route_duration_min,
        score = EXCLUDED.score,
        payload = EXCLUDED.payload,
        source = EXCLUDED.source,
        updated_at = NOW()
    `;
    count += 1;
  }
  return count;
}

async function main() {
  console.log(`[travel:db:import] data root: ${dataRoot}`);
  const pois = await loadPois();
  console.log(`[travel:db:import] upserting POIs: ${pois.length}`);
  await upsertPois(pois);
  const featureCount = await upsertFeatures();
  const reviewCount = await upsertReviews();
  const areaCount = await rebuildAreas();
  const routeCount = await upsertRouteCorpus();
  console.log(`[travel:db:import] done POIs=${pois.length}, features=${featureCount}, reviews=${reviewCount}, areas=${areaCount}, routes=${routeCount}`);
}

main()
  .catch((error) => {
    console.error('[travel:db:import] failed:', error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
