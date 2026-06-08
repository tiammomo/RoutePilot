import fs from 'fs/promises';
import path from 'path';
import type { TravelQueryIntent } from '@/lib/travel/semantic-intent';

export interface TravelWikiHit {
  title: string;
  type: string;
  path: string;
  score: number;
  match_reasons: string[];
  snippet: string;
  entity_ids: string[];
  source_ids: string[];
  wikilinks: string[];
}

export interface TravelWikiRetrievalResult {
  query: string;
  hits: TravelWikiHit[];
  citations: Array<{ title: string; path: string; type: string; snippet: string }>;
  linked_entities: string[];
  graph_expansions: Array<{ from: string; to: string; reason: string }>;
  elapsed_ms: number;
  vault_path: string;
}

interface WikiPage {
  title: string;
  type: string;
  relativePath: string;
  body: string;
  searchText: string;
  entityIds: string[];
  sourceIds: string[];
  wikilinks: string[];
}

const WIKI_DIR = path.resolve(process.cwd(), 'travel-data', 'wiki');
const CACHE_TTL_MS = Number(process.env.TRAVEL_WIKI_CACHE_TTL_MS || 2 * 60 * 1000);
let wikiCache: Promise<{ loadedAt: number; pages: WikiPage[]; byTitle: Map<string, WikiPage> }> | null = null;

function parseFrontmatter(content: string) {
  const match = content.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!match) return { fields: {} as Record<string, unknown>, body: content };
  const fields: Record<string, unknown> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const index = line.indexOf(':');
    if (index <= 0) continue;
    const key = line.slice(0, index).trim();
    const raw = line.slice(index + 1).trim();
    if (raw.startsWith('[') && raw.endsWith(']')) {
      fields[key] = raw.slice(1, -1).split(',').map((item) => item.trim().replace(/^"|"$/g, '')).filter(Boolean);
    } else {
      fields[key] = raw.replace(/^"|"$/g, '');
    }
  }
  return { fields, body: content.slice(match[0].length) };
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function extractWikiLinks(content: string): string[] {
  return Array.from(content.matchAll(/\[\[([^\]]+)\]\]/g)).map((match) => String(match[1] || '').trim()).filter(Boolean);
}

async function listMarkdownFiles(dir: string): Promise<string[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await listMarkdownFiles(fullPath));
    if (entry.isFile() && entry.name.endsWith('.md')) files.push(fullPath);
  }
  return files;
}

async function loadWikiPages() {
  if (wikiCache) {
    const cached = await wikiCache;
    if (Date.now() - cached.loadedAt < CACHE_TTL_MS) return cached;
  }
  wikiCache = (async () => {
    const files = await listMarkdownFiles(WIKI_DIR);
    const pages: WikiPage[] = [];
    for (const file of files) {
      const content = await fs.readFile(file, 'utf8');
      const { fields, body } = parseFrontmatter(content);
      const title = String(fields.title || path.basename(file, '.md'));
      const type = String(fields.type || 'page');
      const wikilinks = extractWikiLinks(content);
      pages.push({
        title,
        type,
        relativePath: path.relative(WIKI_DIR, file).replace(/\\/g, '/'),
        body,
        searchText: `${title}\n${type}\n${body}\n${wikilinks.join('\n')}`.toLowerCase(),
        entityIds: asStringArray(fields.entity_ids),
        sourceIds: asStringArray(fields.source_ids),
        wikilinks,
      });
    }
    return { loadedAt: Date.now(), pages, byTitle: new Map(pages.map((page) => [page.title, page])) };
  })();
  return wikiCache;
}

function queryTerms(rawText: string, intent?: TravelQueryIntent | null): string[] {
  const seed = [
    rawText,
    intent?.area,
    intent?.persona === 'couple' ? '情侣浪漫' : null,
    intent?.persona === 'family' ? '亲子友好' : null,
    intent?.persona === 'senior' ? '老人友好' : null,
    intent?.avoid_queue ? '少排队 不排队 低排队' : null,
    intent?.indoor_preferred ? '室内优先' : null,
    intent?.walk_preference === 'low' ? '低步行 少走路 别太累' : null,
    intent?.needs_meal ? '餐饮 午餐 咖啡' : null,
    ...(intent?.must_include_names || []),
  ].filter(Boolean).join(' ');
  return Array.from(new Set(seed.toLowerCase().split(/[\s,，。；;、/|]+/).map((item) => item.trim()).filter((item) => item.length >= 2)));
}

function scorePage(page: WikiPage, terms: string[], intent?: TravelQueryIntent | null) {
  let score = 0;
  const reasons: string[] = [];
  const title = page.title.toLowerCase();
  for (const term of terms) {
    if (title.includes(term)) {
      score += 8;
      reasons.push(`title:${term}`);
    } else if (page.searchText.includes(term)) {
      score += 2;
      reasons.push(`content:${term}`);
    }
  }
  if (intent?.area && page.title.includes(intent.area)) {
    score += page.type === 'area' ? 18 : 6;
    reasons.push(`area:${intent.area}`);
  }
  if (intent?.persona === 'couple' && page.title.includes('情侣浪漫')) score += 20;
  if (intent?.persona === 'senior' && page.title.includes('老人友好')) score += 20;
  if (intent?.persona === 'family' && page.title.includes('亲子友好')) score += 20;
  if (intent?.avoid_queue && page.title.includes('少排队')) score += 18;
  if (intent?.indoor_preferred && page.title.includes('室内优先')) score += 18;
  if (page.type === 'topic') score += 1;
  return { score, reasons: Array.from(new Set(reasons)).slice(0, 6) };
}

function snippetFor(page: WikiPage, terms: string[]) {
  const plain = page.body.replace(/[#>*_|`-]/g, ' ').replace(/\s+/g, ' ').trim();
  const lower = plain.toLowerCase();
  const found = terms.map((term) => lower.indexOf(term)).find((index) => index >= 0) ?? 0;
  return plain.slice(Math.max(0, found - 50), Math.max(0, found - 50) + 180) || page.title;
}

export async function retrieveTravelWiki(params: { rawText: string; intent?: TravelQueryIntent | null; limit?: number }): Promise<TravelWikiRetrievalResult> {
  const started = performance.now();
  const { pages, byTitle } = await loadWikiPages();
  const terms = queryTerms(params.rawText, params.intent);
  const scored = pages
    .map((page) => ({ page, ...scorePage(page, terms, params.intent) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.page.relativePath.localeCompare(b.page.relativePath))
    .slice(0, Math.max(1, params.limit || 8));

  const linked = new Set<string>();
  const graph: TravelWikiRetrievalResult['graph_expansions'] = [];
  for (const item of scored.slice(0, 5)) {
    for (const entity of item.page.entityIds) linked.add(entity);
    for (const link of item.page.wikilinks.slice(0, 8)) {
      if (byTitle.has(link)) graph.push({ from: item.page.title, to: link, reason: 'wikilink' });
    }
  }

  const hits = scored.map(({ page, score, reasons }) => ({
    title: page.title,
    type: page.type,
    path: page.relativePath,
    score: Number(score.toFixed(3)),
    match_reasons: reasons,
    snippet: snippetFor(page, terms),
    entity_ids: page.entityIds.slice(0, 20),
    source_ids: page.sourceIds,
    wikilinks: page.wikilinks.slice(0, 12),
  }));

  return {
    query: params.rawText,
    hits,
    citations: hits.slice(0, 5).map((hit) => ({ title: hit.title, path: hit.path, type: hit.type, snippet: hit.snippet })),
    linked_entities: Array.from(linked).slice(0, 40),
    graph_expansions: graph.slice(0, 30),
    elapsed_ms: Number((performance.now() - started).toFixed(2)),
    vault_path: path.relative(process.cwd(), WIKI_DIR).replace(/\\/g, '/'),
  };
}
