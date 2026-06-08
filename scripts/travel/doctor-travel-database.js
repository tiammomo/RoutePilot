#!/usr/bin/env node

const path = require('path');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const prisma = new PrismaClient();

const REQUIRED_TABLES = [
  'travel_pois',
  'travel_poi_features',
  'travel_reviews',
  'travel_areas',
  'travel_semantic_mappings',
  'travel_query_logs',
  'travel_precomputed_routes',
];

async function count(tableName) {
  const rows = await prisma.$queryRawUnsafe(`SELECT COUNT(*)::int AS count FROM ${tableName}`);
  return Number(rows[0]?.count || 0);
}

async function main() {
  const tables = await prisma.$queryRaw`
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = ANY(${REQUIRED_TABLES})
    ORDER BY table_name
  `;
  const existing = new Set(tables.map((row) => row.table_name));
  const missing = REQUIRED_TABLES.filter((table) => !existing.has(table));
  if (missing.length > 0) {
    throw new Error(`Missing travel tables: ${missing.join(', ')}. Run npm run travel:db:init.`);
  }

  const poiCount = await count('travel_pois');
  const featureCount = await count('travel_poi_features');
  const reviewCount = await count('travel_reviews');
  const areaCount = await count('travel_areas');
  const semanticCount = await count('travel_semantic_mappings');
  const routeCount = await count('travel_precomputed_routes');

  const coverageRows = await prisma.$queryRaw`
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE area IS NOT NULL AND area <> '')::int AS area_count,
      COUNT(*) FILTER (WHERE avg_cost IS NOT NULL)::int AS cost_count,
      COUNT(*) FILTER (WHERE suggested_duration_min IS NOT NULL)::int AS duration_count,
      COUNT(*) FILTER (WHERE open_time IS NOT NULL OR open_hours <> '{}'::jsonb)::int AS opening_count
    FROM travel_pois
  `;
  const coverage = coverageRows[0] || {};

  const indexes = await prisma.$queryRaw`
    SELECT indexname
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = ANY(${REQUIRED_TABLES})
    ORDER BY indexname
  `;

  const featureSamples = await prisma.$queryRaw`
    SELECT feature_key, COUNT(*)::int AS count
    FROM travel_poi_features
    GROUP BY feature_key
    ORDER BY count DESC, feature_key
    LIMIT 10
  `;

  console.log('[travel:db:doctor] tables ok:', REQUIRED_TABLES.join(', '));
  console.log(`[travel:db:doctor] counts POIs=${poiCount}, features=${featureCount}, reviews=${reviewCount}, areas=${areaCount}, semantics=${semanticCount}, routes=${routeCount}`);
  console.log(
    `[travel:db:doctor] POI coverage area=${coverage.area_count || 0}/${coverage.total || 0}, cost=${coverage.cost_count || 0}/${coverage.total || 0}, duration=${coverage.duration_count || 0}/${coverage.total || 0}, opening=${coverage.opening_count || 0}/${coverage.total || 0}`,
  );
  console.log(`[travel:db:doctor] index count=${indexes.length}`);
  console.log(`[travel:db:doctor] feature keys=${featureSamples.map((item) => `${item.feature_key}:${item.count}`).join(', ') || '-'}`);

  if (poiCount === 0) {
    throw new Error('No travel POIs found. Run npm run travel:db:import.');
  }
  if (featureCount === 0 || reviewCount === 0) {
    throw new Error('Travel features or reviews are empty. Run npm run travel:db:import.');
  }
  if (routeCount === 0) {
    throw new Error('No precomputed travel routes found. Run npm run travel:routes:build && npm run travel:db:import.');
  }
  console.log('[travel:db:doctor] passed');
}

main()
  .catch((error) => {
    console.error('[travel:db:doctor] failed:', error instanceof Error ? error.message : error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
