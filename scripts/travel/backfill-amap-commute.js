#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const crypto = require('crypto');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const prisma = new PrismaClient();

const DEFAULT_DATA_ROOT = path.join(rootDir, 'travel-data', 'processed');
const DATA_ROOT = process.env.TRAVELPILOT_DATA_ROOT || DEFAULT_DATA_ROOT;
const AMAP_KEY = process.env.AMAP_API_KEY || process.env.AMAP_KEY || '';
const AMAP_BASE_URL = 'https://restapi.amap.com';
const MODES = new Set(['walking', 'driving', 'transit']);

function parseArgs(argv) {
  const result = {
    limitPois: 120,
    maxPairs: 400,
    maxPairsPerRelation: 200,
    modes: ['walking', 'driving', 'transit'],
    maxDistanceKm: 8,
    sameAreaOnly: false,
    delayMs: 333,
    dryRun: false,
    refreshExisting: false,
    pairsFile: null,
  };

  for (const arg of argv) {
    const [key, value] = arg.split('=');
    if (key === '--limit-pois') result.limitPois = Number(value);
    if (key === '--max-pairs') result.maxPairs = Number(value);
    if (key === '--max-pairs-per-relation') result.maxPairsPerRelation = Number(value);
    if (key === '--modes') result.modes = String(value || '').split(',').map((item) => item.trim()).filter((item) => MODES.has(item));
    if (key === '--max-distance-km') result.maxDistanceKm = Number(value);
    if (key === '--same-area-only') result.sameAreaOnly = value !== 'false';
    if (key === '--delay-ms') result.delayMs = Number(value);
    if (key === '--dry-run') result.dryRun = true;
    if (key === '--refresh-existing') result.refreshExisting = true;
    if (key === '--pairs-file') result.pairsFile = value ? path.resolve(rootDir, value) : null;
  }

  return result;
}

function inferPoiKind(raw) {
  const structured = [
    raw.entity_kind,
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.planning_domain,
  ].map((value) => String(value || '').toLowerCase());
  if (structured.some((value) => ['dining', 'food', 'restaurant', 'snack', 'cafe', 'coffee'].includes(value))) {
    return 'restaurant';
  }
  if (structured.some((value) => ['culture', 'museum', 'art_gallery', 'attraction', 'park', 'temple', 'landmark'].includes(value))) {
    return 'attraction';
  }

  const text = [
    raw.name,
    raw.category,
    raw.poi_type,
    raw.poi_subtype,
    raw.dining_style,
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
    ...(Array.isArray(raw.evidence_tags) ? raw.evidence_tags : []),
  ].map((value) => String(value || '').toLowerCase()).join(' ');
  const foodWords = [
    'food', 'restaurant', 'dining', 'meal', 'lunch', 'dinner', 'snack', 'cafe', 'coffee',
    '餐厅', '饭店', '菜馆', '咖啡', '茶餐厅', '小吃', '烤鸭', '烧麦', '火锅', '面馆', '包子', '甜品',
  ];
  return foodWords.some((word) => text.includes(word)) ? 'restaurant' : 'attraction';
}

async function readJsonArray(fileName) {
  const content = await fs.readFile(path.join(DATA_ROOT, fileName), 'utf8');
  const parsed = JSON.parse(content);
  return Array.isArray(parsed) ? parsed : [];
}

function normalizePoi(raw) {
  const poiId = String(raw.poi_id || '').trim();
  const lng = Number(raw.lng);
  const lat = Number(raw.lat);
  if (!poiId || !Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  return {
    poi_id: poiId,
    name: String(raw.name || raw.display_name || raw.normalized_name || poiId),
    city: 'beijing',
    district: raw.district ? String(raw.district) : null,
    area: raw.area ? String(raw.area) : null,
    category: raw.category ? String(raw.category) : null,
    poi_type: raw.poi_type ? String(raw.poi_type) : null,
    poi_kind: inferPoiKind(raw),
    address: raw.address ? String(raw.address) : null,
    lng,
    lat,
    rating: Number.isFinite(Number(raw.rating)) ? Number(raw.rating) : null,
    avg_cost: Number.isFinite(Number(raw.avg_cost)) ? Number(raw.avg_cost) : null,
    review_count: Number.isFinite(Number(raw.review_count)) ? Number(raw.review_count) : null,
    raw,
  };
}

async function loadPois() {
  const files = [
    'beijing_culture_pois.json',
    'beijing_mixed_category_pois.json',
    'beijing_planner_entities.json',
  ];
  const all = (await Promise.all(files.map(readJsonArray))).flat().map(normalizePoi).filter(Boolean);
  const byId = new Map();
  for (const poi of all) {
    const existing = byId.get(poi.poi_id);
    if (!existing || Number(poi.review_count || 0) > Number(existing.review_count || 0)) {
      byId.set(poi.poi_id, poi);
    }
  }
  return Array.from(byId.values())
    .sort((a, b) => Number(b.review_count || 0) - Number(a.review_count || 0));
}

function haversineKm(a, b) {
  const toRad = (value) => (value * Math.PI) / 180;
  const earthKm = 6371;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * earthKm * Math.asin(Math.sqrt(h));
}

function relationType(origin, destination) {
  if (origin.poi_kind === 'restaurant' && destination.poi_kind === 'restaurant') return 'restaurant_restaurant';
  if (origin.poi_kind === 'restaurant' || destination.poi_kind === 'restaurant') return 'attraction_restaurant';
  return 'attraction_attraction';
}

async function buildPairsFromFile(filePath, poisById, options) {
  const content = await fs.readFile(filePath, 'utf8');
  const parsed = JSON.parse(content);
  const rows = Array.isArray(parsed) ? parsed : Array.isArray(parsed.pairs) ? parsed.pairs : [];
  const pairs = [];
  for (const row of rows) {
    if (row.needs_backfill === false || row.covered === true) continue;
    const originId = String(row.origin_poi_id || '').trim();
    const destinationId = String(row.destination_poi_id || '').trim();
    const origin = poisById.get(originId);
    const destination = poisById.get(destinationId);
    if (!origin || !destination || origin.poi_id === destination.poi_id) continue;
    const straightDistanceKm = haversineKm(origin, destination);
    if (Number.isFinite(options.maxDistanceKm) && straightDistanceKm > options.maxDistanceKm) continue;
    pairs.push({
      origin,
      destination,
      relationType: relationType(origin, destination),
      straightDistanceKm,
      priority: Number(row.frequency || 1),
    });
  }
  return pairs
    .sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0) || a.straightDistanceKm - b.straightDistanceKm)
    .slice(0, options.maxPairs);
}

function buildPairs(pois, options) {
  const buckets = {
    attraction_attraction: [],
    attraction_restaurant: [],
    restaurant_restaurant: [],
  };
  for (let i = 0; i < pois.length; i += 1) {
    for (let j = 0; j < pois.length; j += 1) {
      if (i === j) continue;
      const origin = pois[i];
      const destination = pois[j];
      if (options.sameAreaOnly && origin.area && destination.area && origin.area !== destination.area) continue;
      const distanceKm = haversineKm(origin, destination);
      if (distanceKm > options.maxDistanceKm) continue;
      const relation = relationType(origin, destination);
      buckets[relation].push({ origin, destination, relationType: relation, straightDistanceKm: distanceKm });
    }
  }
  const balancedPairs = Object.values(buckets)
    .flatMap((items) => items.sort((a, b) => a.straightDistanceKm - b.straightDistanceKm).slice(0, options.maxPairsPerRelation));
  return balancedPairs.sort((a, b) => a.straightDistanceKm - b.straightDistanceKm).slice(0, options.maxPairs);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function edgeId(originPoiId, destinationPoiId, mode) {
  return crypto.createHash('sha1').update(`${originPoiId}:${destinationPoiId}:${mode}:amap`).digest('hex');
}

function routeSummaryFromTransit(transit) {
  const segments = Array.isArray(transit?.segments) ? transit.segments : [];
  return segments
    .map((segment) => {
      const buslines = Array.isArray(segment.bus?.buslines) ? segment.bus.buslines : [];
      const busName = buslines[0]?.name;
      if (busName) return busName;
      if (segment.walking?.distance) return `步行${segment.walking.distance}米`;
      return null;
    })
    .filter(Boolean)
    .slice(0, 5)
    .join(' -> ');
}

function parseAmapResponse(mode, json) {
  if (json.status !== '1') {
    return {
      status: 'error',
      distance_m: null,
      duration_s: null,
      cost_cny: null,
      walking_distance_m: null,
      transfer_count: null,
      route_summary: json.info || json.infocode || 'amap error',
      raw: json,
    };
  }

  if (mode === 'walking') {
    const pathItem = json.route?.paths?.[0] || {};
    return {
      status: 'ok',
      distance_m: Number(pathItem.distance || 0) || null,
      duration_s: Number(pathItem.duration || 0) || null,
      cost_cny: null,
      walking_distance_m: Number(pathItem.distance || 0) || null,
      transfer_count: 0,
      route_summary: '步行',
      raw: json,
    };
  }

  if (mode === 'driving') {
    const pathItem = json.route?.paths?.[0] || {};
    return {
      status: 'ok',
      distance_m: Number(pathItem.distance || 0) || null,
      duration_s: Number(pathItem.duration || 0) || null,
      cost_cny: Number(pathItem.tolls || 0) || null,
      walking_distance_m: null,
      transfer_count: 0,
      route_summary: pathItem.strategy || '驾车',
      raw: json,
    };
  }

  const transit = json.route?.transits?.[0] || {};
  return {
    status: 'ok',
    distance_m: Number(transit.distance || 0) || null,
    duration_s: Number(transit.duration || 0) || null,
    cost_cny: Number(transit.cost || 0) || null,
    walking_distance_m: Number(transit.walking_distance || 0) || null,
    transfer_count: Number(transit.segments?.length || 1) - 1,
    route_summary: routeSummaryFromTransit(transit) || '公交/地铁',
    raw: json,
  };
}

async function fetchAmapRoute(origin, destination, mode) {
  const endpoint = mode === 'transit' ? '/v3/direction/transit/integrated' : `/v3/direction/${mode}`;
  const url = new URL(endpoint, AMAP_BASE_URL);
  url.searchParams.set('key', AMAP_KEY);
  url.searchParams.set('origin', `${origin.lng},${origin.lat}`);
  url.searchParams.set('destination', `${destination.lng},${destination.lat}`);
  if (mode === 'transit') {
    url.searchParams.set('city', '北京');
    url.searchParams.set('cityd', '北京');
    url.searchParams.set('strategy', '0');
  }
  const response = await fetch(url);
  const json = await response.json();
  return parseAmapResponse(mode, json);
}

async function upsertPois(pois) {
  for (const poi of pois) {
    await prisma.$executeRaw`
      INSERT INTO travel_pois (
        poi_id, name, city, district, area, category, poi_type, poi_kind, address,
        lng, lat, rating, avg_cost, review_count, raw, updated_at
      ) VALUES (
        ${poi.poi_id}, ${poi.name}, ${poi.city}, ${poi.district}, ${poi.area}, ${poi.category}, ${poi.poi_type}, ${poi.poi_kind}, ${poi.address},
        ${poi.lng}, ${poi.lat}, ${poi.rating}, ${poi.avg_cost}, ${poi.review_count}, CAST(${JSON.stringify(poi.raw)} AS jsonb), NOW()
      )
      ON CONFLICT (poi_id) DO UPDATE SET
        name = EXCLUDED.name,
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
        raw = EXCLUDED.raw,
        updated_at = NOW()
    `;
  }
}

async function upsertEdge(pair, mode, parsed) {
  await prisma.$executeRaw`
    INSERT INTO travel_commute_edges (
      id, origin_poi_id, destination_poi_id, mode, relation_type, provider, status,
      distance_m, duration_s, cost_cny, walking_distance_m, transfer_count,
      route_summary, raw, fetched_at, updated_at
    ) VALUES (
      ${edgeId(pair.origin.poi_id, pair.destination.poi_id, mode)},
      ${pair.origin.poi_id},
      ${pair.destination.poi_id},
      ${mode},
      ${pair.relationType},
      'amap',
      ${parsed.status},
      ${parsed.distance_m},
      ${parsed.duration_s},
      ${parsed.cost_cny},
      ${parsed.walking_distance_m},
      ${parsed.transfer_count},
      ${parsed.route_summary},
      CAST(${JSON.stringify(parsed.raw)} AS jsonb),
      NOW(),
      NOW()
    )
    ON CONFLICT (origin_poi_id, destination_poi_id, mode, provider, relation_type) DO UPDATE SET
      status = EXCLUDED.status,
      distance_m = EXCLUDED.distance_m,
      duration_s = EXCLUDED.duration_s,
      cost_cny = EXCLUDED.cost_cny,
      walking_distance_m = EXCLUDED.walking_distance_m,
      transfer_count = EXCLUDED.transfer_count,
      route_summary = EXCLUDED.route_summary,
      raw = EXCLUDED.raw,
      fetched_at = NOW(),
      updated_at = NOW()
  `;
}

async function hasExistingEdge(pair, mode) {
  const rows = await prisma.$queryRaw`
    SELECT 1
    FROM travel_commute_edges
    WHERE origin_poi_id = ${pair.origin.poi_id}
      AND destination_poi_id = ${pair.destination.poi_id}
      AND mode = ${mode}
      AND provider = 'amap'
      AND relation_type = ${pair.relationType}
    LIMIT 1
  `;
  return Array.isArray(rows) && rows.length > 0;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!AMAP_KEY && !options.dryRun) {
    throw new Error('AMAP_API_KEY is required. Put it in .env.local instead of hard-coding it.');
  }

  const allPois = await loadPois();
  const pois = allPois.slice(0, options.limitPois);
  const poisById = new Map(allPois.map((poi) => [poi.poi_id, poi]));
  const pairs = options.pairsFile
    ? await buildPairsFromFile(options.pairsFile, poisById, options)
    : buildPairs(pois, options);
  const runId = `amap-${Date.now()}`;

  const relationCounts = pairs.reduce((acc, pair) => {
    acc[pair.relationType] = (acc[pair.relationType] || 0) + 1;
    return acc;
  }, {});
  console.log(`[travel:amap] POIs=${options.pairsFile ? allPois.length : pois.length}, attractions=${pois.filter((poi) => poi.poi_kind === 'attraction').length}, restaurants=${pois.filter((poi) => poi.poi_kind === 'restaurant').length}, pairs=${pairs.length}, modes=${options.modes.join(',')}`);
  if (options.pairsFile) console.log(`[travel:amap] pairs file=${path.relative(rootDir, options.pairsFile)}`);
  console.log(`[travel:amap] relation counts=${JSON.stringify(relationCounts)}`);
  if (options.dryRun) {
    console.log('[travel:amap] dry run sample pairs:');
    for (const pair of pairs.slice(0, 10)) {
      console.log(`- [${pair.relationType}] ${pair.origin.name} -> ${pair.destination.name} (${pair.straightDistanceKm.toFixed(2)}km)`);
    }
    return;
  }

  const upsertPoiList = options.pairsFile
    ? Array.from(new Map(pairs.flatMap((pair) => [pair.origin, pair.destination]).map((poi) => [poi.poi_id, poi])).values())
    : pois;
  await upsertPois(upsertPoiList);
  await prisma.$executeRaw`
    INSERT INTO travel_commute_fetch_runs (id, provider, mode_list, poi_count, pair_count, options)
    VALUES (${runId}, 'amap', ${options.modes}, ${upsertPoiList.length}, ${pairs.length}, CAST(${JSON.stringify(options)} AS jsonb))
  `;

  let successCount = 0;
  let failedCount = 0;
  let skippedCount = 0;

  for (const pair of pairs) {
    for (const mode of options.modes) {
      try {
        if (!options.refreshExisting && await hasExistingEdge(pair, mode)) {
          skippedCount += 1;
          console.log(`[travel:amap] skip existing ${mode} ${pair.origin.name} -> ${pair.destination.name}`);
          continue;
        }
        const parsed = await fetchAmapRoute(pair.origin, pair.destination, mode);
        await upsertEdge(pair, mode, parsed);
        if (parsed.status === 'ok') successCount += 1;
        else failedCount += 1;
        console.log(`[travel:amap] ${mode} ${pair.origin.name} -> ${pair.destination.name}: ${parsed.status}, ${parsed.duration_s || '-'}s`);
      } catch (error) {
        failedCount += 1;
        console.warn(`[travel:amap] failed ${mode} ${pair.origin.name} -> ${pair.destination.name}: ${error.message}`);
      }
      await sleep(options.delayMs);
    }
  }

  await prisma.$executeRaw`
    UPDATE travel_commute_fetch_runs
    SET success_count = ${successCount},
        failed_count = ${failedCount},
        skipped_count = ${skippedCount},
        completed_at = NOW()
    WHERE id = ${runId}
  `;

  console.log(`[travel:amap] done success=${successCount}, failed=${failedCount}, skipped=${skippedCount}`);
}

main()
  .catch((error) => {
    console.error('[travel:amap] failed:', error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
