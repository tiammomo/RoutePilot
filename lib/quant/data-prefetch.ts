import fs from 'fs/promises';
import path from 'path';
import { ensureBaselineEvidenceFiles } from '@/lib/quant/evidence';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace, QuantRunPlan } from '@/lib/quant/workspace';

type JsonRecord = Record<string, unknown>;

interface PrefetchResult {
  skipped: boolean;
  symbol?: string;
  finalDataPath?: string;
  rawFiles?: string[];
  summary: string;
}

const MARKET_API_BASE_URL = process.env.QUANTPILOT_MARKET_API_URL ?? 'http://127.0.0.1:8000';
const FETCH_TIMEOUT_MS = Number.parseInt(process.env.QUANTPILOT_MARKET_PREFETCH_TIMEOUT_MS ?? '', 10) || 12_000;

const KNOWN_SYMBOLS: Array<{ keyword: string; symbol: string }> = [
  { keyword: '贵州茅台', symbol: '600519' },
  { keyword: '茅台', symbol: '600519' },
  { keyword: '宁德时代', symbol: '300750' },
  { keyword: '平安银行', symbol: '000001' },
  { keyword: '招商银行', symbol: '600036' },
  { keyword: '沪深300ETF', symbol: '510300' },
  { keyword: '沪深300 ETF', symbol: '510300' },
  { keyword: '300ETF', symbol: '510300' },
  { keyword: '沪深300', symbol: '000300' },
  { keyword: '沪深 300', symbol: '000300' },
  { keyword: '创业板指', symbol: '399006' },
  { keyword: '创业板指数', symbol: '399006' },
  { keyword: '中证500', symbol: '000905' },
  { keyword: '中证 500', symbol: '000905' },
  { keyword: '科创50', symbol: '000688' },
  { keyword: '科创 50', symbol: '000688' },
];

function isQuantAnalysisPlan(plan: QuantRunPlan): boolean {
  return ['stock_diagnosis', 'technical_analysis', 'fundamental_analysis'].includes(plan.capabilityId);
}

function inferSymbol(plan: QuantRunPlan): string | null {
  const planned = plan.symbols.find((symbol) => /^(?:6|0|3|5)\d{5}$/.test(symbol));
  if (planned) {
    return planned;
  }

  const code = plan.question.match(/\b(?:6|0|3|5)\d{5}\b/)?.[0];
  if (code) {
    return code;
  }

  return KNOWN_SYMBOLS.find((item) => plan.question.includes(item.keyword))?.symbol ?? null;
}

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as JsonRecord;
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function mean(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function round(value: number | null, digits = 2): number | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function calculateMetrics(kline: JsonRecord | null): JsonRecord {
  const bars = Array.isArray(kline?.bars) ? kline.bars.map(asRecord).filter(Boolean) as JsonRecord[] : [];
  const closes = bars.map((bar) => numeric(bar.close)).filter((value): value is number => value !== null);
  const volumes = bars.map((bar) => numeric(bar.volume)).filter((value): value is number => value !== null);
  const highs = bars.map((bar) => numeric(bar.high)).filter((value): value is number => value !== null);
  const lows = bars.map((bar) => numeric(bar.low)).filter((value): value is number => value !== null);

  const firstClose = closes[0] ?? null;
  const lastClose = closes.at(-1) ?? null;
  const returns = closes.slice(1).map((close, index) => {
    const previous = closes[index];
    return previous ? (close - previous) / previous : 0;
  });
  const avgReturn = mean(returns) ?? 0;
  const variance = returns.length
    ? mean(returns.map((value) => (value - avgReturn) ** 2)) ?? 0
    : 0;

  return {
    periodReturn:
      firstClose && lastClose ? round(((lastClose - firstClose) / firstClose) * 100) : null,
    periodHigh: highs.length ? round(Math.max(...highs)) : null,
    periodLow: lows.length ? round(Math.min(...lows)) : null,
    volatility20d: round(Math.sqrt(variance) * Math.sqrt(252) * 100),
    avgVolume20d: round(mean(volumes.slice(-20))),
    ma5: round(mean(closes.slice(-5))),
    ma10: round(mean(closes.slice(-10))),
    ma20: round(mean(closes.slice(-20))),
  };
}

async function fetchJson(endpoint: string): Promise<JsonRecord> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(`${MARKET_API_BASE_URL}${endpoint}`, {
      signal: controller.signal,
      cache: 'no-store',
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${endpoint} 返回 HTTP ${response.status}: ${text.slice(0, 500)}`);
    }
    const parsed = JSON.parse(text);
    const record = asRecord(parsed);
    if (!record) {
      throw new Error(`${endpoint} 未返回 JSON 对象。`);
    }
    return record;
  } finally {
    clearTimeout(timeout);
  }
}

async function writeJson(filePath: string, value: unknown) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function finalDataFromResponses(params: {
  symbol: string;
  quote: JsonRecord;
  kline?: JsonRecord | null;
  technicalIndicators?: JsonRecord | null;
  financials?: JsonRecord | null;
  fundamentalIndicators?: JsonRecord | null;
  announcements?: JsonRecord | null;
}): JsonRecord {
  const quote = params.quote;
  const assetType = typeof quote.asset_type === 'string' ? quote.asset_type : 'stock';
  const kline = params.kline ?? {
    symbol: params.symbol,
    asset_type: assetType,
    bars: [],
    fetched_at: quote.fetched_at,
    data_quality: { status: 'warning', missing_fields: ['bars'], warnings: ['未获取历史 K 线。'] },
  };
  const financials = params.financials ?? {
    symbol: params.symbol,
    asset_type: assetType,
    reports: [],
    fetched_at: quote.fetched_at,
    data_quality: {
      status: assetType === 'stock' ? 'warning' : 'ok',
      missing_fields: assetType === 'stock' ? ['reports'] : [],
      warnings: assetType === 'stock' ? ['未获取财务摘要。'] : [`${assetType} 标的默认不获取个股财务摘要。`],
    },
  };
  const announcements = params.announcements ?? {
    symbol: params.symbol,
    asset_type: assetType,
    announcements: [],
    fetched_at: quote.fetched_at,
    data_quality: {
      status: assetType === 'stock' ? 'warning' : 'ok',
      missing_fields: assetType === 'stock' ? ['announcements'] : [],
      warnings: assetType === 'stock' ? ['未获取公告事件。'] : [`${assetType} 标的默认不获取个股公告事件。`],
    },
  };

  return {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    symbol: String(quote.symbol ?? params.symbol),
    name: typeof quote.name === 'string' ? quote.name : null,
    secid: quote.secid,
    market: quote.market,
    asset_type: assetType,
    source: quote.source ?? 'eastmoney',
    currency: quote.currency ?? 'CNY',
    timezone: quote.timezone ?? 'Asia/Shanghai',
    as_of: quote.as_of ?? quote.quote_time ?? quote.fetched_at,
    quote,
    kline,
    technicalIndicators: params.technicalIndicators ?? null,
    financials,
    fundamentalIndicators: params.fundamentalIndicators ?? null,
    announcements,
    computedMetrics: calculateMetrics(kline),
  };
}

export async function prefetchQuantDataForRunPlan(params: {
  projectPath: string;
  plan: QuantRunPlan;
}): Promise<PrefetchResult> {
  if (!isQuantAnalysisPlan(params.plan)) {
    return { skipped: true, summary: `能力 ${params.plan.capabilityId} 暂不需要平台预取数据。` };
  }

  const symbol = inferSymbol(params.plan);
  if (!symbol) {
    return { skipped: true, summary: '未识别到单只 A 股标的，跳过平台预取。' };
  }

  await ensureQuantWorkspace(params.projectPath);
  const runId = params.plan.runId;
  const rawDir = path.join(params.projectPath, 'data_file', 'raw', runId);
  const rawFiles: string[] = [];

  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'data_prefetch_started',
    stage: 'data_collection',
    status: 'pending',
    run_id: runId,
    summary: `平台开始预取 ${symbol} 的真实行情数据。`,
  });

  const quote = await fetchJson(`/api/v1/quotes/realtime/${symbol}`);
  const assetType = typeof quote.asset_type === 'string' ? quote.asset_type : 'stock';
  const quotePath = path.join(rawDir, 'quote.json');
  await writeJson(quotePath, quote);
  rawFiles.push(path.relative(params.projectPath, quotePath).replaceAll(path.sep, '/'));

  let kline: JsonRecord | null = null;
  let technicalIndicators: JsonRecord | null = null;
  let financials: JsonRecord | null = null;
  let fundamentalIndicators: JsonRecord | null = null;
  let announcements: JsonRecord | null = null;
  const warnings: string[] = [];

  if (params.plan.dataRequirements.some((endpoint) => endpoint.includes('/quotes/history/'))) {
    try {
      kline = await fetchJson(`/api/v1/quotes/history/${symbol}?period=daily&adjustment=qfq&limit=120`);
      const filePath = path.join(rawDir, 'kline-daily-qfq.json');
      await writeJson(filePath, kline);
      rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`历史 K 线预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (params.plan.dataRequirements.some((endpoint) => endpoint.includes('/indicators/technical/'))) {
    try {
      technicalIndicators = await fetchJson(
        `/api/v1/indicators/technical/${symbol}?period=daily&adjustment=qfq&limit=120`
      );
      const filePath = path.join(rawDir, 'technical-indicators.json');
      await writeJson(filePath, technicalIndicators);
      rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`技术指标预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/fundamentals/financials/'))
  ) {
    try {
      financials = await fetchJson(`/api/v1/fundamentals/financials/${symbol}?limit=8`);
      const filePath = path.join(rawDir, 'financials.json');
      await writeJson(filePath, financials);
      rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`财务摘要预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/indicators/fundamental/'))
  ) {
    try {
      fundamentalIndicators = await fetchJson(`/api/v1/indicators/fundamental/${symbol}?limit=8`);
      const filePath = path.join(rawDir, 'fundamental-indicators.json');
      await writeJson(filePath, fundamentalIndicators);
      rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`财务衍生指标预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/events/announcements/'))
  ) {
    try {
      announcements = await fetchJson(`/api/v1/events/announcements/${symbol}?limit=20`);
      const filePath = path.join(rawDir, 'announcements.json');
      await writeJson(filePath, announcements);
      rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`公告事件预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const finalData = finalDataFromResponses({
    symbol,
    quote,
    kline,
    technicalIndicators,
    financials,
    fundamentalIndicators,
    announcements,
  });
  const finalPath = path.join(params.projectPath, 'data_file', 'final', 'dashboard-data.json');
  await writeJson(finalPath, finalData);

  await ensureBaselineEvidenceFiles(params.projectPath, { force: true });

  const finalDataPath = path.relative(params.projectPath, finalPath).replaceAll(path.sep, '/');
  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'data_prefetched',
    stage: 'data_collection',
    status: warnings.length > 0 ? 'warning' : 'success',
    run_id: runId,
    artifact_path: finalDataPath,
    summary: `平台已预取 ${symbol} 数据：raw ${rawFiles.length} 个文件，final 数据已写入。${warnings.length ? ` 警告：${warnings.join('；')}` : ''}`,
  });

  return {
    skipped: false,
    symbol,
    finalDataPath,
    rawFiles,
    summary: `已预取 ${symbol} 真实数据并生成 ${finalDataPath}。`,
  };
}
