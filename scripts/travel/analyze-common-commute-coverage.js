#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const prisma = new PrismaClient();
const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';
const outDir = path.join(rootDir, 'travel-data', 'analysis');

const COMMON_CASES = [
  {
    goal: '前门附近玩4小时，中午吃饭，预算200以内，少走路，不想排队。',
    request: { route_mode: 'mixed', area: '前门', max_duration_min: 240, max_budget: 200, max_total_pois: 3, walk_preference: 'low', preference_signals: { lunch: true, avoid_queue: true, value_for_money: true } },
  },
  {
    goal: '故宫附近文化路线，不吃饭，预算100以内，少走路。',
    request: { route_mode: 'culture', area: '故宫', max_duration_min: 240, max_budget: 100, max_total_pois: 3, walk_preference: 'low', preference_signals: { avoid_queue: true } },
  },
  {
    goal: '带老人去北海，别太累，玩3小时，中午吃饭。',
    request: { route_mode: 'mixed', area: '北海', max_duration_min: 180, max_total_pois: 3, walk_preference: 'low', persona_id: 'senior_relaxed', pace: 'relaxed', preference_signals: { lunch: true, senior: true } },
  },
  {
    goal: '情侣在王府井晚上玩3小时，吃饭，想浪漫一点，不想排队。',
    request: { route_mode: 'mixed', area: '王府井', start_time: '18:00', max_duration_min: 180, max_total_pois: 3, persona_id: 'couple_romantic', preference_signals: { lunch: true, couple: true, avoid_queue: true, coffee: true } },
  },
  {
    goal: '亲子半日游，室内优先，中午吃饭，预算300以内。',
    request: { route_mode: 'mixed', max_duration_min: 240, max_budget: 300, max_total_pois: 3, persona_id: 'family_kids', walk_preference: 'low', preference_signals: { lunch: true, family: true, indoor: true } },
  },
  {
    goal: '故宫附近玩3小时，少走路，想看博物馆和美术馆。',
    request: { route_mode: 'culture', area: '故宫', max_duration_min: 180, max_total_pois: 3, walk_preference: 'low', preference_signals: { indoor: true } },
  },
  {
    goal: '王府井附近晚上玩3小时，想喝咖啡，少排队。',
    request: { route_mode: 'mixed', area: '王府井', start_time: '18:00', max_duration_min: 180, max_total_pois: 3, preference_signals: { coffee: true, avoid_queue: true } },
  },
  {
    goal: '前门到天安门周边半日游，中午吃饭，预算150以内。',
    request: { route_mode: 'mixed', area: '前门', max_duration_min: 240, max_budget: 150, max_total_pois: 3, preference_signals: { lunch: true, value_for_money: true } },
  },
  {
    goal: '什刹海和北海附近轻松玩4小时，带老人，不要太累。',
    request: { route_mode: 'culture', area: '北海', max_duration_min: 240, max_total_pois: 3, walk_preference: 'low', persona_id: 'senior_relaxed', pace: 'relaxed', preference_signals: { senior: true } },
  },
  {
    goal: '南锣鼓巷附近逛3小时，想吃小吃和咖啡，少走路。',
    request: { route_mode: 'mixed', area: '南锣鼓巷', max_duration_min: 180, max_total_pois: 3, walk_preference: 'low', preference_signals: { snack: true, coffee: true } },
  },
];

async function post(pathname, body) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${pathname} failed: ${response.status} ${text}`);
  return text ? JSON.parse(text) : null;
}

function getPlanning(result) {
  return result?.planning_response || result || {};
}

function getPairKey(originPoiId, destinationPoiId) {
  return `${originPoiId}->${destinationPoiId}`;
}

function collectPairs(caseText, planning) {
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const pairs = [];
  for (const proposal of proposals) {
    const stops = Array.isArray(proposal.pois) ? proposal.pois : [];
    for (let index = 1; index < stops.length; index += 1) {
      const origin = stops[index - 1];
      const destination = stops[index];
      if (!origin?.poi_id || !destination?.poi_id) continue;
      pairs.push({
        case_text: caseText,
        proposal_id: proposal.proposal_id || null,
        strategy: proposal.strategy || null,
        origin_poi_id: origin.poi_id,
        origin_name: origin.name,
        destination_poi_id: destination.poi_id,
        destination_name: destination.name,
        planner_source: destination.transfer_source || null,
        planner_minutes: destination.transfer_from_previous_minutes ?? null,
        planner_meters: destination.transfer_from_previous_meters ?? null,
      });
    }
  }
  return pairs;
}

async function loadExistingEdges(pairRows) {
  const ids = Array.from(new Set(pairRows.flatMap((pair) => [pair.origin_poi_id, pair.destination_poi_id])));
  if (ids.length === 0) return new Map();
  const rows = await prisma.$queryRaw`
    SELECT origin_poi_id, destination_poi_id, mode, provider, duration_s, distance_m, walking_distance_m, status
    FROM travel_commute_edges
    WHERE status = 'ok'
      AND origin_poi_id = ANY(${ids})
      AND destination_poi_id = ANY(${ids})
  `;
  const byPair = new Map();
  for (const row of rows) {
    const key = getPairKey(String(row.origin_poi_id), String(row.destination_poi_id));
    const group = byPair.get(key) || [];
    group.push({
      mode: row.mode,
      provider: row.provider,
      duration_s: Number(row.duration_s || 0),
      distance_m: row.distance_m === null ? null : Number(row.distance_m),
      walking_distance_m: row.walking_distance_m === null ? null : Number(row.walking_distance_m),
    });
    byPair.set(key, group);
  }
  return byPair;
}

function summarizePairs(pairRows, edgesByPair) {
  const aggregate = new Map();
  for (const pair of pairRows) {
    const key = getPairKey(pair.origin_poi_id, pair.destination_poi_id);
    const reverseKey = getPairKey(pair.destination_poi_id, pair.origin_poi_id);
    const existing = edgesByPair.get(key) || [];
    const reverseExisting = edgesByPair.get(reverseKey) || [];
    const current = aggregate.get(key) || {
      ...pair,
      frequency: 0,
      cases: new Set(),
      proposal_ids: new Set(),
      has_direct_edge: false,
      has_reverse_edge: false,
      best_duration_s: null,
      best_mode: null,
      best_provider: null,
    };
    current.frequency += 1;
    current.cases.add(pair.case_text);
    if (pair.proposal_id) current.proposal_ids.add(pair.proposal_id);
    current.has_direct_edge = current.has_direct_edge || existing.length > 0;
    current.has_reverse_edge = current.has_reverse_edge || reverseExisting.length > 0;
    const best = [...existing, ...reverseExisting].sort((a, b) => Number(a.duration_s || Infinity) - Number(b.duration_s || Infinity))[0];
    if (best && (!current.best_duration_s || best.duration_s < current.best_duration_s)) {
      current.best_duration_s = best.duration_s;
      current.best_mode = best.mode;
      current.best_provider = best.provider;
    }
    aggregate.set(key, current);
  }
  return Array.from(aggregate.values())
    .map((item) => ({
      ...item,
      cases: Array.from(item.cases),
      proposal_ids: Array.from(item.proposal_ids),
      covered: item.has_direct_edge || item.has_reverse_edge,
      needs_backfill: !(item.has_direct_edge || item.has_reverse_edge),
    }))
    .sort((a, b) => Number(b.needs_backfill) - Number(a.needs_backfill) || b.frequency - a.frequency);
}

function buildMarkdown(summary) {
  const missing = summary.pairs.filter((pair) => pair.needs_backfill);
  const lines = [
    '# 常见问法通勤覆盖报告',
    '',
    `- 生成时间：${summary.generated_at}`,
    `- 常见问法数：${summary.case_count}`,
    `- 唯一相邻 POI pair：${summary.pair_count}`,
    `- 已覆盖 pair：${summary.covered_pair_count}`,
    `- 缺失 pair：${summary.missing_pair_count}`,
    `- 覆盖率：${Math.round(summary.coverage_rate * 100)}%`,
    '',
    '## 优先补采 Top 缺失边',
    '',
    '| 优先级 | 频次 | 起点 | 终点 | planner 回退 | 涉及问法 |',
    '| --- | ---: | --- | --- | --- | --- |',
    ...missing.slice(0, 40).map((pair, index) => (
      `| ${index + 1} | ${pair.frequency} | ${pair.origin_name} (${pair.origin_poi_id}) | ${pair.destination_name} (${pair.destination_poi_id}) | ${pair.planner_minutes ?? '-'} 分钟 / ${pair.planner_meters ?? '-'} 米 | ${pair.cases.length} |`
    )),
    '',
    '## 补采建议',
    '',
    '- 这些 pair 来自比赛/演示高频问法的前三个候选方案，相比全量补采更能提升可见效果。',
    '- 如果缺失边很多，优先补 `frequency` 高、出现在王府井/故宫/前门/北海的 pair。',
    '- 补采后重启 web 服务，避免内存里的 commute edge cache 继续使用旧索引。',
  ];
  return lines.join('\n');
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  const allPairs = [];
  const cases = [];
  for (const commonCase of COMMON_CASES) {
    const result = await post('/api/v1/travel/plan', commonCase.request);
    const planning = getPlanning(result);
    const pairs = collectPairs(commonCase.goal, planning);
    cases.push({
      goal: commonCase.goal,
      request: commonCase.request,
      resolved_area: planning.resolved_area || null,
      proposal_count: Array.isArray(planning.proposals) ? planning.proposals.length : 0,
      pair_count: pairs.length,
    });
    allPairs.push(...pairs);
  }

  const edgesByPair = await loadExistingEdges(allPairs);
  const pairs = summarizePairs(allPairs, edgesByPair);
  const coveredPairCount = pairs.filter((pair) => pair.covered).length;
  const summary = {
    generated_at: new Date().toISOString(),
    base_url: baseUrl,
    case_count: cases.length,
    pair_count: pairs.length,
    covered_pair_count: coveredPairCount,
    missing_pair_count: pairs.length - coveredPairCount,
    coverage_rate: pairs.length ? Number((coveredPairCount / pairs.length).toFixed(3)) : 0,
    cases,
    pairs,
  };

  const jsonPath = path.join(outDir, 'common-commute-coverage.json');
  const mdPath = path.join(outDir, 'common-commute-coverage.md');
  await fs.writeFile(jsonPath, JSON.stringify(summary, null, 2), 'utf8');
  await fs.writeFile(mdPath, buildMarkdown(summary), 'utf8');

  console.log('[common-commute-coverage] generated');
  console.log(`coverage=${summary.covered_pair_count}/${summary.pair_count} (${Math.round(summary.coverage_rate * 100)}%)`);
  console.log(`missing=${summary.missing_pair_count}`);
  console.log(`json=${path.relative(rootDir, jsonPath)}`);
  console.log(`markdown=${path.relative(rootDir, mdPath)}`);
}

main().catch(async (error) => {
  console.error('[common-commute-coverage] failed:', error);
  await prisma.$disconnect();
  process.exit(1);
}).finally(async () => {
  await prisma.$disconnect();
});
