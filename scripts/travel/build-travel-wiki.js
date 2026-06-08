#!/usr/bin/env node

const crypto = require('crypto');
const fs = require('fs/promises');
const path = require('path');
const dotenv = require('dotenv');
const { PrismaClient } = require('@prisma/client');

const rootDir = path.join(__dirname, '..', '..');
const processedDir = path.join(rootDir, 'travel-data', 'processed');
const rawSourcesDir = path.join(rootDir, 'travel-data', 'raw', 'sources');
const wikiDir = path.join(rootDir, 'travel-data', 'wiki');
const prisma = new PrismaClient();

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

const SOURCE_FILES = [
  'beijing_planner_entities.json',
  'beijing_poi_feature_aggregates.json',
  'beijing_review_records.json',
];

function slugify(value, fallback = 'page') {
  return String(value || fallback)
    .normalize('NFKC')
    .replace(/[\\/:*?"<>|#^[\]]+/g, ' ')
    .replace(/\s+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 90) || fallback;
}

function hashText(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}

function yamlString(value) {
  return JSON.stringify(String(value ?? ''));
}

function yamlArray(values) {
  const items = Array.from(new Set((values || []).filter(Boolean).map(String)));
  return `[${items.map(yamlString).join(', ')}]`;
}

function mdEscape(value) {
  return String(value ?? '').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
}

function wikiLink(title) {
  return `[[${title}]]`;
}

function firstItems(values, count) {
  return Array.isArray(values) ? values.filter(Boolean).slice(0, count) : [];
}

async function readJson(fileName) {
  return JSON.parse(await fs.readFile(path.join(processedDir, fileName), 'utf8'));
}

async function writeFile(relativePath, content) {
  const target = path.join(wikiDir, relativePath);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, `${content.trimEnd()}\n`, 'utf8');
}

async function mirrorRawSources() {
  await fs.mkdir(rawSourcesDir, { recursive: true });
  const sources = [];
  for (const fileName of SOURCE_FILES) {
    const sourcePath = path.join(processedDir, fileName);
    const raw = await fs.readFile(sourcePath);
    const targetPath = path.join(rawSourcesDir, fileName);
    await fs.writeFile(targetPath, raw);
    sources.push({
      id: hashText(`${fileName}:${raw.length}:${hashText(raw)}`).slice(0, 16),
      fileName,
      relativePath: `travel-data/raw/sources/${fileName}`,
      sha256: hashText(raw),
      bytes: raw.length,
    });
  }
  return sources;
}

function frontmatter(fields) {
  const lines = ['---'];
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) lines.push(`${key}: ${yamlArray(value)}`);
    else if (typeof value === 'number' || typeof value === 'boolean') lines.push(`${key}: ${value}`);
    else lines.push(`${key}: ${yamlString(value)}`);
  }
  lines.push('---');
  return lines.join('\n');
}

function featureMapFor(features) {
  const map = new Map();
  for (const item of features) {
    if (!map.has(item.poi_id)) map.set(item.poi_id, []);
    map.get(item.poi_id).push(item);
  }
  return map;
}

function reviewMapFor(reviews) {
  const map = new Map();
  for (const item of reviews) {
    if (!map.has(item.poi_id)) map.set(item.poi_id, []);
    map.get(item.poi_id).push(item);
  }
  return map;
}

function buildPoiPage(poi, features, reviews, commuteByPoi, nowIso) {
  const title = poi.display_name || poi.name || poi.poi_id;
  const areaTitle = `区域 - ${poi.area || poi.district || '北京'}`;
  const tags = [
    poi.area,
    poi.district,
    poi.poi_type,
    poi.poi_subtype,
    poi.walk_intensity ? `walk:${poi.walk_intensity}` : null,
    poi.queue_risk ? `queue:${poi.queue_risk}` : null,
    poi.family_friendliness ? `family:${poi.family_friendliness}` : null,
    ...(Array.isArray(poi.planning_tags) ? poi.planning_tags.slice(0, 8) : []),
  ].filter(Boolean);
  const featureRows = features.length
    ? features.map((item) => `| ${mdEscape(item.feature_key)} | ${mdEscape(item.feature_value)} | ${mdEscape(item.confidence || '-')} | ${mdEscape(item.review_count_used || 0)} |`).join('\n')
    : '| 暂无 | 暂无 | - | 0 |';
  const reviewLines = reviews.length
    ? reviews.slice(0, 5).map((item) => `- [${mdEscape(item.review_id)}] ${mdEscape(item.review_text)}（评分 ${item.rating ?? '-'}，${item.source_platform || 'unknown'}）`).join('\n')
    : '- 暂无本地评论证据。';
  const commuteLines = commuteByPoi.length
    ? commuteByPoi.slice(0, 8).map((edge) => `- 到/来自 ${wikiLink(edge.otherTitle)}：${Math.round(Number(edge.duration_s || 0) / 60)} 分钟，${edge.distance_m ?? '-'} 米，${edge.mode || '-'}，provider=${edge.provider || '-'}`).join('\n')
    : '- 暂无 travel_commute_edges 覆盖，路线规划会回退坐标估算。';

  return `${frontmatter({
    title,
    type: 'poi',
    source_ids: ['beijing_planner_entities'],
    entity_ids: [poi.poi_id],
    area: poi.area || '',
    updated_at: nowIso,
    confidence: poi.coverage_confidence || 'medium',
    tags,
  })}

# ${title}

> Obsidian Wiki 页面。来源：\`travel-data/raw/sources/beijing_planner_entities.json\`，UGC 聚合：\`beijing_poi_feature_aggregates.json\`，评论：\`beijing_review_records.json\`。

## 导航
- 所属区域：${wikiLink(areaTitle)}
- 类型：${poi.poi_type || '-'} / ${poi.poi_subtype || poi.category || '-'}
- 相关主题：${[
    poi.indoor_friendly ? wikiLink('主题 - 室内优先') : null,
    poi.senior_friendly ? wikiLink('主题 - 老人友好') : null,
    poi.family_friendly ? wikiLink('主题 - 亲子友好') : null,
    poi.queue_risk === 'low' ? wikiLink('主题 - 少排队') : null,
  ].filter(Boolean).join('、') || '暂无'}

## POI 摘要
| 字段 | 值 |
| --- | --- |
| 区域 | ${mdEscape(poi.area || '-')} |
| 地址 | ${mdEscape(poi.address || '-')} |
| 预算 | ${mdEscape(poi.avg_cost ?? '-')} 元 |
| 建议停留 | ${mdEscape(poi.suggested_duration_min ?? '-')} 分钟 |
| 营业时间 | ${mdEscape(`${poi.open_time || '-'} - ${poi.close_time || '-'}`)} |
| 评分 | ${mdEscape(poi.rating ?? '-')} |
| 步行强度 | ${mdEscape(poi.walk_intensity || '-')} |
| 排队风险 | ${mdEscape(poi.queue_risk || '-')} |
| 亲子友好 | ${mdEscape(poi.family_friendliness || (poi.family_friendly ? 'high' : '-'))} |
| 老人友好 | ${mdEscape(poi.senior_friendly ? 'yes' : 'unknown')} |

## UGC 聚合信号
| feature | value | confidence | reviews |
| --- | --- | --- | --- |
${featureRows}

## 评论证据
${reviewLines}

## 通勤可达性
${commuteLines}

## 可用于路线规划的判断
- 如果用户要求少走路，优先检查 \`walk_intensity\` 与通勤覆盖。
- 如果用户要求不排队，优先检查 \`queue_risk\` 和评论证据。
- 如果用户是老人/亲子/情侣，结合本页 tags 与区域页进行候选筛选。
`;
}

function buildAreaPage(area, pois, nowIso) {
  const title = `区域 - ${area}`;
  const culture = pois.filter((item) => item.poi_type !== 'food');
  const food = pois.filter((item) => item.poi_type === 'food');
  const lowQueue = pois.filter((item) => item.queue_risk === 'low').slice(0, 10);
  const senior = pois.filter((item) => item.senior_friendly || item.walk_intensity === 'low').slice(0, 10);
  const family = pois.filter((item) => item.family_friendly || item.family_friendliness === 'high').slice(0, 10);
  const links = pois.slice(0, 30).map((item) => `- ${wikiLink(item.display_name || item.name || item.poi_id)}：${item.poi_type || '-'}，${item.avg_cost ?? '-'} 元，${item.suggested_duration_min ?? '-'} 分钟`).join('\n');

  return `${frontmatter({
    title,
    type: 'area',
    source_ids: ['beijing_planner_entities'],
    entity_ids: pois.map((item) => item.poi_id).slice(0, 80),
    updated_at: nowIso,
    confidence: 'medium',
    tags: [area, 'area', 'route_context'],
  })}

# ${title}

## 区域画像
| 指标 | 值 |
| --- | --- |
| POI 总数 | ${pois.length} |
| 文化/景点 | ${culture.length} |
| 餐饮/咖啡 | ${food.length} |
| 低排队候选 | ${lowQueue.length} |
| 老人/低步行候选 | ${senior.length} |
| 亲子候选 | ${family.length} |

## 推荐入口
- 少排队：${lowQueue.map((item) => wikiLink(item.display_name || item.name || item.poi_id)).join('、') || '暂无'}
- 老人友好：${senior.map((item) => wikiLink(item.display_name || item.name || item.poi_id)).join('、') || '暂无'}
- 亲子友好：${family.map((item) => wikiLink(item.display_name || item.name || item.poi_id)).join('、') || '暂无'}

## 区域 POI
${links || '- 暂无'}
`;
}

function buildTopicPage(topic, matcher, pois, nowIso) {
  const matched = pois.filter(matcher).slice(0, 80);
  const title = `主题 - ${topic}`;
  return `${frontmatter({
    title,
    type: 'topic',
    source_ids: ['beijing_planner_entities', 'beijing_poi_feature_aggregates'],
    entity_ids: matched.map((item) => item.poi_id),
    updated_at: nowIso,
    confidence: 'medium',
    tags: [topic, 'preference'],
  })}

# ${title}

## 使用场景
当用户表达“${topic}”相关偏好时，路线 planner 和 MiniMax rerank 应优先查看本页候选，并结合区域页、POI 页和通勤页解释原因。

## 候选 POI
${matched.map((item) => `- ${wikiLink(item.display_name || item.name || item.poi_id)}：${item.area || item.district || '-'}，${item.poi_type || '-'}，步行 ${item.walk_intensity || '-'}，排队 ${item.queue_risk || '-'}`).join('\n') || '- 暂无'}
`;
}

function buildIndex(areas, topics, pois, nowIso) {
  return `${frontmatter({
    title: 'index',
    type: 'index',
    source_ids: SOURCE_FILES.map((item) => item.replace(/\.json$/, '')),
    entity_ids: [],
    updated_at: nowIso,
    confidence: 'high',
  })}

# 北京旅游 Agent Wiki

这是一个符合 LLM Wiki 范式的 Obsidian vault：原始资料保存在 \`travel-data/raw/sources\`，Wiki 页面保存在 \`travel-data/wiki\`，所有页面使用 YAML frontmatter 与 \`[[wikilink]]\` 互联。

## 核心入口
- ${wikiLink('purpose')}
- ${wikiLink('schema')}
- ${wikiLink('log')}

## 区域
${areas.map((area) => `- ${wikiLink(`区域 - ${area}`)}`).join('\n')}

## 偏好主题
${topics.map((topic) => `- ${wikiLink(`主题 - ${topic}`)}`).join('\n')}

## 代表 POI
${pois.slice(0, 40).map((item) => `- ${wikiLink(item.display_name || item.name || item.poi_id)}`).join('\n')}
`;
}

function buildPurpose(nowIso) {
  return `${frontmatter({
    title: 'purpose',
    type: 'system',
    source_ids: [],
    entity_ids: [],
    updated_at: nowIso,
    confidence: 'high',
  })}

# purpose

本 Wiki 的目标是把北京 POI、UGC 评论、区域画像和通勤边编译成可被人类浏览、可被 Agent 检索、可被 Obsidian 展示的知识库。

## 关键问题
- 用户想在有限时间和预算内怎样串联 POI？
- 哪些 POI 适合少走路、不排队、老人、亲子、情侣、室内等偏好？
- 哪些推荐有 UGC 或通勤证据支持？
- 哪些路线风险需要明确提示？
`;
}

function buildSchema(nowIso) {
  return `${frontmatter({
    title: 'schema',
    type: 'system',
    source_ids: [],
    entity_ids: [],
    updated_at: nowIso,
    confidence: 'high',
  })}

# schema

## Page Types
- \`poi\`：单个 POI 页面，必须包含预算、停留、开放时间、UGC 信号和通勤可达性。
- \`area\`：区域/商圈画像页面，必须链接区域内代表 POI。
- \`topic\`：偏好主题页面，例如少排队、老人友好、亲子友好、室内优先。
- \`system\`：purpose、schema、log、index。

## Frontmatter
每个页面必须包含：
- \`title\`
- \`type\`
- \`source_ids\`
- \`entity_ids\`
- \`updated_at\`
- \`confidence\`

## Link Rule
页面之间使用 Obsidian 兼容的 \`[[wikilink]]\`。POI 必须链接区域页；区域和主题页必须链接代表 POI。
`;
}

function buildLog(nowIso, stats, sources) {
  return `${frontmatter({
    title: 'log',
    type: 'system',
    source_ids: sources.map((item) => item.id),
    entity_ids: [],
    updated_at: nowIso,
    confidence: 'high',
  })}

# log

| time | action | status | detail |
| --- | --- | --- | --- |
| ${nowIso} | ingest | ok | generated ${stats.poiPages} POI pages, ${stats.areaPages} area pages, ${stats.topicPages} topic pages from ${sources.length} raw sources |

## Sources
${sources.map((item) => `- ${item.id}: \`${item.relativePath}\`, sha256=${item.sha256}, bytes=${item.bytes}`).join('\n')}
`;
}

async function loadCommuteEdges(poisById) {
  try {
    const rows = await prisma.$queryRaw`
      SELECT origin_poi_id, destination_poi_id, mode, provider, distance_m, duration_s, route_summary
      FROM travel_commute_edges
      WHERE status = 'ok'
      ORDER BY duration_s ASC
      LIMIT 2000
    `;
    const map = new Map();
    for (const row of rows) {
      const origin = poisById.get(row.origin_poi_id);
      const destination = poisById.get(row.destination_poi_id);
      if (!origin || !destination) continue;
      const pairs = [
        [row.origin_poi_id, destination],
        [row.destination_poi_id, origin],
      ];
      for (const [poiId, other] of pairs) {
        if (!map.has(poiId)) map.set(poiId, []);
        map.get(poiId).push({ ...row, otherTitle: other.display_name || other.name || other.poi_id });
      }
    }
    return map;
  } catch {
    return new Map();
  }
}

async function main() {
  const nowIso = new Date().toISOString();
  await fs.mkdir(wikiDir, { recursive: true });
  const sources = await mirrorRawSources();
  const [poisRaw, features, reviews] = await Promise.all([
    readJson('beijing_planner_entities.json'),
    readJson('beijing_poi_feature_aggregates.json'),
    readJson('beijing_review_records.json'),
  ]);
  const pois = poisRaw
    .filter((item) => item && item.poi_id && (item.display_name || item.name))
    .sort((a, b) => Number(b.review_count || 0) - Number(a.review_count || 0) || String(a.display_name || a.name).localeCompare(String(b.display_name || b.name), 'zh-Hans-CN'));
  const poisById = new Map(pois.map((item) => [item.poi_id, item]));
  const featuresByPoi = featureMapFor(features);
  const reviewsByPoi = reviewMapFor(reviews);
  const commuteByPoi = await loadCommuteEdges(poisById);

  const pageLimit = Number(process.env.TRAVEL_WIKI_POI_LIMIT || 260);
  const selectedPois = pois.slice(0, pageLimit);
  const selectedIds = new Set(selectedPois.map((item) => item.poi_id));
  const areaMap = new Map();
  for (const poi of selectedPois) {
    const area = poi.area || poi.district || '北京';
    if (!areaMap.has(area)) areaMap.set(area, []);
    areaMap.get(area).push(poi);
  }

  for (const poi of selectedPois) {
    const title = poi.display_name || poi.name || poi.poi_id;
    await writeFile(`POI/${slugify(title)}.md`, buildPoiPage(
      poi,
      featuresByPoi.get(poi.poi_id) || [],
      reviewsByPoi.get(poi.poi_id) || [],
      commuteByPoi.get(poi.poi_id) || [],
      nowIso,
    ));
  }

  const areas = [...areaMap.keys()].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
  for (const area of areas) {
    await writeFile(`Areas/${slugify(`区域 - ${area}`)}.md`, buildAreaPage(area, areaMap.get(area), nowIso));
  }

  const topics = [
    ['少排队', (poi) => poi.queue_risk === 'low' || firstItems(poi.evidence_tags, 20).some((tag) => String(tag).includes('queue'))],
    ['老人友好', (poi) => poi.senior_friendly || poi.walk_intensity === 'low'],
    ['亲子友好', (poi) => poi.family_friendly || poi.family_friendliness === 'high'],
    ['室内优先', (poi) => poi.indoor_friendly || ['museum', 'gallery', 'theater'].includes(String(poi.poi_subtype || poi.category))],
    ['情侣浪漫', (poi) => /咖啡|艺术|美术|剧场|夜|王府井/.test(`${poi.display_name || poi.name || ''}${poi.tags || ''}${poi.area || ''}`)],
  ];
  for (const [topic, matcher] of topics) {
    await writeFile(`Topics/${slugify(`主题 - ${topic}`)}.md`, buildTopicPage(topic, matcher, selectedPois, nowIso));
  }

  await writeFile('index.md', buildIndex(areas, topics.map(([topic]) => topic), selectedPois, nowIso));
  await writeFile('purpose.md', buildPurpose(nowIso));
  await writeFile('schema.md', buildSchema(nowIso));
  await writeFile('log.md', buildLog(nowIso, {
    poiPages: selectedPois.length,
    areaPages: areas.length,
    topicPages: topics.length,
  }, sources));

  const manifest = {
    generated_at: nowIso,
    vault_path: path.relative(rootDir, wikiDir).replace(/\\/g, '/'),
    raw_sources_path: path.relative(rootDir, rawSourcesDir).replace(/\\/g, '/'),
    poi_pages: selectedPois.length,
    area_pages: areas.length,
    topic_pages: topics.length,
    page_count: selectedPois.length + areas.length + topics.length + 4,
    wikilink_count: selectedPois.length + areas.reduce((sum, area) => sum + (areaMap.get(area)?.length || 0), 0),
    topic_count: topics.length,
    retrieval_ready: true,
    sources,
    obsidian_entry: 'index.md',
    llm_wiki_compatible: true,
  };
  await writeFile('manifest.json', JSON.stringify(manifest, null, 2));
  console.log(`[travel:wiki:build] generated Obsidian vault at ${path.relative(rootDir, wikiDir)}`);
  console.log(`[travel:wiki:build] poi=${manifest.poi_pages}, area=${manifest.area_pages}, topic=${manifest.topic_pages}`);
}

main()
  .catch((error) => {
    console.error('[travel:wiki:build] failed:', error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect().catch(() => {});
  });
