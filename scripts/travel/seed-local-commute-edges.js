#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const crypto = require('crypto');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
const dataRoot = process.env.TRAVELPILOT_DATA_ROOT || path.join(rootDir, 'travel-data', 'processed');
const provider = 'local_estimate';
const prisma = new PrismaClient();

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

async function readJson(fileName) {
  const raw = await fs.readFile(path.join(dataRoot, fileName), 'utf8');
  return JSON.parse(raw);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizePoi(raw) {
  const poiId = String(raw.poi_id || '').trim();
  const lng = Number(raw.lng);
  const lat = Number(raw.lat);
  if (!poiId || !Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  return {
    poi_id: poiId,
    name: String(raw.name || raw.display_name || raw.normalized_name || poiId),
    area: raw.area ? String(raw.area) : null,
    poi_kind: isFoodPoi(raw) ? 'restaurant' : 'attraction',
    lng,
    lat,
  };
}

function isFoodPoi(raw) {
  const text = [
    raw.name,
    raw.display_name,
    raw.poi_type,
    raw.poi_kind,
    raw.category,
    raw.meal_type,
    ...(Array.isArray(raw.tags) ? raw.tags : []),
    ...(Array.isArray(raw.planning_tags) ? raw.planning_tags : []),
  ].join(' ').toLowerCase();
  return /food|restaurant|dining|meal|snack|coffee|cafe|餐|饭|咖啡|小吃|美食|茶馆/.test(text);
}

function relationType(origin, destination) {
  if (origin.poi_kind === 'restaurant' && destination.poi_kind === 'restaurant') return 'restaurant_restaurant';
  if (origin.poi_kind === 'restaurant' || destination.poi_kind === 'restaurant') return 'attraction_restaurant';
  return 'attraction_attraction';
}

function haversineMeters(a, b) {
  const toRad = (value) => (value * Math.PI) / 180;
  const earthM = 6371000;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * earthM * Math.asin(Math.sqrt(h));
}

function edgeId(originId, destinationId, mode, rel) {
  const hash = crypto.createHash('sha1').update(`${originId}:${destinationId}:${mode}:${rel}:${provider}`).digest('hex').slice(0, 24);
  return `local_commute_${hash}`;
}

function estimateByMode(origin, destination, mode) {
  const straightM = haversineMeters(origin, destination);
  const roadDistanceM = Math.max(120, Math.round(straightM * (mode === 'walking' ? 1.22 : mode === 'bicycling' ? 1.28 : 1.45)));
  const speedMps = mode === 'walking' ? 1.15 : mode === 'bicycling' ? 3.6 : 6.8;
  const overheadS = mode === 'walking' ? 120 : mode === 'bicycling' ? 180 : 300;
  return {
    distance_m: roadDistanceM,
    duration_s: Math.max(180, Math.round(roadDistanceM / speedMps + overheadS)),
    cost_cny: mode === 'driving' ? Number(Math.max(13, roadDistanceM * 0.003).toFixed(1)) : 0,
    walking_distance_m: mode === 'walking' ? roadDistanceM : mode === 'bicycling' ? Math.min(300, Math.round(roadDistanceM * 0.08)) : Math.min(500, Math.round(roadDistanceM * 0.12)),
    transfer_count: 0,
    route_summary: `本地坐标估算${mode === 'walking' ? '步行' : mode === 'bicycling' ? '骑行' : '驾车'} ${Math.round(roadDistanceM)} 米，约 ${Math.round(Math.max(180, roadDistanceM / speedMps + overheadS) / 60)} 分钟。`,
    raw: {
      source: 'local_coordinate_estimate',
      straight_distance_m: Math.round(straightM),
      road_factor: mode === 'walking' ? 1.22 : mode === 'bicycling' ? 1.28 : 1.45,
      speed_mps: speedMps,
      generated_by: 'scripts/travel/seed-local-commute-edges.js',
    },
  };
}

function addPair(pairs, origin, destination, reason, maxDistanceM = 8000) {
  if (!origin || !destination || origin.poi_id === destination.poi_id) return;
  const distanceM = haversineMeters(origin, destination);
  if (distanceM > maxDistanceM) return;
  const key = `${origin.poi_id}->${destination.poi_id}`;
  if (!pairs.has(key)) pairs.set(key, { origin, destination, reason, distanceM });
}

async function loadPoisById() {
  const files = ['beijing_planner_entities.json', 'beijing_culture_pois.json', 'beijing_mixed_category_pois.json'];
  const byId = new Map();
  for (const file of files) {
    const rows = asArray(await readJson(file).catch(() => []));
    for (const raw of rows) {
      const poi = normalizePoi(raw);
      if (poi && !byId.has(poi.poi_id)) byId.set(poi.poi_id, poi);
    }
  }
  return byId;
}

async function buildPairs(poisById) {
  const pairs = new Map();
  const corpus = await readJson('beijing_route_corpus.json').catch(() => null);
  for (const route of asArray(corpus?.routes || corpus).slice(0, 4000)) {
    const ids = asArray(route.poi_ids).map(String);
    for (let index = 1; index < ids.length; index += 1) {
      const origin = poisById.get(ids[index - 1]);
      const destination = poisById.get(ids[index]);
      addPair(pairs, origin, destination, 'route_corpus_adjacent', 9000);
      addPair(pairs, destination, origin, 'route_corpus_adjacent_reverse', 9000);
    }
  }

  const requiredPairs = [
    ['amap_B0H65CPLW1', 'amap_B000A9LF82', 'check_travel_commute'],
    ['amap_B000A9LF82', 'amap_B0H65CPLW1', 'check_travel_commute_reverse'],
  ];
  for (const [originId, destinationId, reason] of requiredPairs) {
    addPair(pairs, poisById.get(originId), poisById.get(destinationId), reason, 12000);
  }

  const byArea = new Map();
  for (const poi of poisById.values()) {
    if (!poi.area) continue;
    const group = byArea.get(poi.area) || [];
    group.push(poi);
    byArea.set(poi.area, group);
  }
  for (const group of byArea.values()) {
    const sample = group.slice(0, 16);
    for (const origin of sample) {
      const nearest = sample
        .filter((candidate) => candidate.poi_id !== origin.poi_id)
        .map((candidate) => ({ candidate, distanceM: haversineMeters(origin, candidate) }))
        .filter((item) => item.distanceM <= 3500)
        .sort((a, b) => a.distanceM - b.distanceM)
        .slice(0, 3);
      for (const item of nearest) addPair(pairs, origin, item.candidate, 'area_nearest_seed', 3500);
    }
  }
  return Array.from(pairs.values()).sort((a, b) => a.distanceM - b.distanceM);
}

async function upsertPoi(poi) {
  await prisma.$executeRaw`
    INSERT INTO travel_pois (poi_id, name, city, area, poi_kind, lng, lat, source, raw, updated_at)
    VALUES (
      ${poi.poi_id}, ${poi.name}, 'beijing', ${poi.area}, ${poi.poi_kind},
      ${poi.lng}, ${poi.lat}, 'travel-data/processed', CAST(${JSON.stringify({ seeded_for_commute: true })} AS jsonb), NOW()
    )
    ON CONFLICT (poi_id) DO NOTHING
  `;
}

async function upsertEdge(pair, mode) {
  const rel = relationType(pair.origin, pair.destination);
  const estimate = estimateByMode(pair.origin, pair.destination, mode);
  await prisma.$executeRaw`
    INSERT INTO travel_commute_edges (
      id, origin_poi_id, destination_poi_id, mode, relation_type, provider, status,
      distance_m, duration_s, cost_cny, walking_distance_m, transfer_count,
      route_summary, raw, fetched_at, updated_at
    ) VALUES (
      ${edgeId(pair.origin.poi_id, pair.destination.poi_id, mode, rel)},
      ${pair.origin.poi_id},
      ${pair.destination.poi_id},
      ${mode},
      ${rel},
      ${provider},
      'ok',
      ${estimate.distance_m},
      ${estimate.duration_s},
      ${estimate.cost_cny},
      ${estimate.walking_distance_m},
      ${estimate.transfer_count},
      ${estimate.route_summary},
      CAST(${JSON.stringify({ ...estimate.raw, seed_reason: pair.reason })} AS jsonb),
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

async function main() {
  const limit = Math.max(1, Number(process.env.TRAVELPILOT_LOCAL_COMMUTE_LIMIT || 1200));
  const modes = String(process.env.TRAVELPILOT_LOCAL_COMMUTE_MODES || 'walking,bicycling,driving')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const poisById = await loadPoisById();
  const pairs = (await buildPairs(poisById)).slice(0, limit);
  for (const pair of pairs) {
    await upsertPoi(pair.origin);
    await upsertPoi(pair.destination);
    for (const mode of modes) await upsertEdge(pair, mode);
  }
  const edgeCount = pairs.length * modes.length;
  console.log(`[travel:commute:seed-local] pairs=${pairs.length}, modes=${modes.join(',')}, upserted_edges=${edgeCount}`);
}

main()
  .catch((error) => {
    console.error('[travel:commute:seed-local] failed:', error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
