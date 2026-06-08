#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');

const rootDir = path.join(__dirname, '..', '..');
const wikiDir = path.join(rootDir, 'travel-data', 'wiki');
const rawSourcesDir = path.join(rootDir, 'travel-data', 'raw', 'sources');
const baseUrl = process.env.TRAVELPILOT_TEST_BASE_URL || 'http://localhost:3000';

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function read(relativePath) {
  return fs.readFile(path.join(wikiDir, relativePath), 'utf8');
}

async function listMarkdown(relativeDir) {
  const dir = path.join(wikiDir, relativeDir);
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries.filter((entry) => entry.isFile() && entry.name.endsWith('.md')).map((entry) => path.join(relativeDir, entry.name));
}

function hasFrontmatter(content) {
  return /^---\n[\s\S]+?\n---\n/.test(content);
}

async function main() {
  for (const file of ['index.md', 'purpose.md', 'schema.md', 'log.md', 'manifest.json']) {
    assert(await exists(path.join(wikiDir, file)), `missing ${file}`);
  }
  for (const file of ['beijing_planner_entities.json', 'beijing_poi_feature_aggregates.json', 'beijing_review_records.json']) {
    assert(await exists(path.join(rawSourcesDir, file)), `missing raw source ${file}`);
  }

  const index = await read('index.md');
  const schema = await read('schema.md');
  const log = await read('log.md');
  const manifest = JSON.parse(await read('manifest.json'));
  assert(hasFrontmatter(index), 'index.md should include YAML frontmatter');
  assert(index.includes('[[purpose]]') && index.includes('[[schema]]') && index.includes('[[log]]'), 'index should link system pages');
  assert(schema.includes('Page Types') && schema.includes('Frontmatter') && schema.includes('[[wikilink]]'), 'schema should document llm-wiki rules');
  assert(log.includes('| time | action | status | detail |'), 'log should include parseable operation table');
  assert(manifest.llm_wiki_compatible === true, 'manifest should mark llm_wiki_compatible');
  assert(manifest.retrieval_ready === true, 'manifest should mark retrieval_ready');
  assert(Number(manifest.page_count || 0) >= 90, 'manifest should include page_count');
  assert(Number(manifest.wikilink_count || 0) > 0, 'manifest should include wikilink_count');

  const poiPages = await listMarkdown('POI');
  const areaPages = await listMarkdown('Areas');
  const topicPages = await listMarkdown('Topics');
  assert(poiPages.length >= 80, `expected >=80 POI pages, got ${poiPages.length}`);
  assert(areaPages.length >= 5, `expected >=5 area pages, got ${areaPages.length}`);
  assert(topicPages.length >= 5, `expected >=5 topic pages, got ${topicPages.length}`);

  const samplePoi = await read(poiPages[0]);
  assert(hasFrontmatter(samplePoi), 'POI page should include YAML frontmatter');
  for (const token of ['type: "poi"', 'source_ids:', 'entity_ids:', '## UGC 聚合信号', '## 评论证据', '## 通勤可达性', '[[区域 - ']) {
    assert(samplePoi.includes(token), `POI sample missing ${token}`);
  }

  const sampleArea = await read(areaPages[0]);
  assert(hasFrontmatter(sampleArea), 'area page should include YAML frontmatter');
  assert(sampleArea.includes('## 区域画像') && sampleArea.includes('[['), 'area page should include profile and wiki links');

  const topicText = (await Promise.all(topicPages.map((page) => read(page)))).join('\n');
  for (const topic of ['少排队', '老人友好', '亲子友好', '室内优先', '情侣浪漫']) {
    assert(topicText.includes(topic), `missing topic ${topic}`);
  }

  const response = await fetch(`${baseUrl}/api/v1/travel/parse-and-plan`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ goal: '王府井情侣浪漫不排队，晚上玩3小时，吃饭。' }),
  });
  if (response.ok) {
    const json = await response.json();
    const planning = json.planning_response || {};
    const retrieval = planning.wiki_retrieval || {};
    assert(planning.generation_metrics?.wiki_retrieval_used === true, 'parse-and-plan should use wiki retrieval');
    assert(Array.isArray(retrieval.hits) && retrieval.hits.length > 0, 'wiki retrieval should return hits');
    const first = retrieval.hits[0];
    for (const key of ['title', 'type', 'path', 'score', 'snippet', 'entity_ids']) {
      assert(Object.prototype.hasOwnProperty.call(first, key), `wiki hit missing ${key}`);
    }
    assert(JSON.stringify(retrieval.hits).includes('王府井') || JSON.stringify(retrieval.hits).includes('情侣浪漫'), 'wiki hits should reflect Wangfujing/couple query');
  } else {
    console.warn(`[travel-wiki] skipped API integration check: ${response.status}`);
  }

  console.log('[travel-wiki] passed');
  console.log(`vault: ${path.relative(rootDir, wikiDir)}`);
  console.log(`pages: poi=${poiPages.length}, area=${areaPages.length}, topic=${topicPages.length}`);
}

main().catch((error) => {
  console.error('[travel-wiki] failed:', error);
  process.exit(1);
});
