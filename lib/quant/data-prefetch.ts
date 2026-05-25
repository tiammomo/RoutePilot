import fs from 'fs/promises';
import path from 'path';
import { ensureBaselineEvidenceFiles } from '@/lib/quant/evidence';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace, QuantRunPlan } from '@/lib/quant/workspace';

type JsonRecord = Record<string, unknown>;

interface PrefetchResult {
  skipped: boolean;
  symbol?: string;
  symbols?: string[];
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
  return [
    'stock_diagnosis',
    'technical_analysis',
    'fundamental_analysis',
    'asset_comparison',
    'sector_rotation',
    'strategy_research',
    'backtest_review',
    'portfolio_risk',
  ].includes(plan.capabilityId);
}

const SYMBOL_CODE_PATTERN = /^(?:6|0|3|5)\d{5}$/;
const GENERIC_QUESTION_WORDS = [
  '分析',
  '查询',
  '查看',
  '看看',
  '看一下',
  '帮我',
  '帮忙',
  '推荐',
  '买入',
  '卖出',
  '股票',
  '个股',
  '行情',
  '走势',
  '最近',
  '可视化',
  '看板',
  '生成',
];

function uniqueSymbols(symbols: string[]): string[] {
  return Array.from(new Set(symbols.filter((symbol) => SYMBOL_CODE_PATTERN.test(symbol))));
}

function pickSymbolCode(value: unknown): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return SYMBOL_CODE_PATTERN.test(trimmed) ? trimmed : null;
  }

  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const candidates = [
    record.symbol,
    record.code,
    record.security_code,
    record.securityCode,
    record.ticker,
    typeof record.secid === 'string' ? record.secid.split('.').at(-1) : null,
  ];

  for (const candidate of candidates) {
    if (typeof candidate !== 'string') {
      continue;
    }
    const trimmed = candidate.trim();
    if (SYMBOL_CODE_PATTERN.test(trimmed)) {
      return trimmed;
    }
  }

  return null;
}

function inferPlannedSymbols(plan: QuantRunPlan): string[] {
  const planned = Array.isArray(plan.symbols) ? plan.symbols : [];
  const codes = plan.question.match(/\b(?:6|0|3|5)\d{5}\b/g) ?? [];
  const known = KNOWN_SYMBOLS.filter((item) => plan.question.includes(item.keyword)).map((item) => item.symbol);
  return uniqueSymbols([
    ...planned.map(pickSymbolCode).filter((symbol): symbol is string => Boolean(symbol)),
    ...codes,
    ...known,
  ]).slice(0, 8);
}

function cleanCandidate(value: string): string | null {
  let candidate = value
    .replace(/\s+/g, '')
    .replace(/^(请|麻烦|帮我|帮忙|分析|查询|查看|看看|看一下|研究|诊断|评估|生成|做一个|做下|对比)+/, '')
    .replace(/(股票|个股|股份|公司)?(最近|近期|近|这段时间|的|行情|走势|K线|K线图|成交量|技术指标|技术|指标|财务|基本面|公告|怎么样|如何|怎么|可视化|看板|页面).*$/, '');

  candidate = candidate.replace(/^(?:A股|港股|美股)/, '').trim();

  if (candidate.length < 2 || candidate.length > 10) {
    return null;
  }

  if (GENERIC_QUESTION_WORDS.some((word) => candidate.includes(word))) {
    return null;
  }

  return candidate;
}

function extractNameCandidates(question: string): string[] {
  const normalized = question.replace(/\b(?:6|0|3|5)\d{5}\b/g, ' ');
  const rawParts = [
    ...normalized.split(/[，。！？?；;、,\n\r]+/),
    ...(normalized.match(/[\u4e00-\u9fffA-Za-z]{2,12}(?=(?:最近|近期|近|股票|个股|股份|行情|走势|K\s*线|成交量|技术指标|财务|基本面|公告|怎么样|如何|怎么))/g) ?? []),
  ];

  return Array.from(
    new Set(
      rawParts
        .map(cleanCandidate)
        .filter((candidate): candidate is string => Boolean(candidate))
    )
  ).slice(0, 6);
}

async function resolveSymbolsFromQuestion(question: string, warnings: string[]): Promise<string[]> {
  const candidates = extractNameCandidates(question);
  const resolved: string[] = [];

  for (const candidate of candidates) {
    try {
      const response = await fetchJson(
        `/api/v1/symbols/resolve?query=${encodeURIComponent(candidate)}&count=5`
      );
      const rows = Array.isArray(response.results) ? response.results : [];
      const firstStock = rows
        .map(asRecord)
        .find((row) => {
          const symbol = pickSymbolCode(row);
          const raw = asRecord(row?.raw);
          const classify = typeof raw?.Classify === 'string' ? raw.Classify : '';
          return Boolean(symbol && (!classify || classify === 'AStock' || classify === 'Index' || classify === 'Fund'));
        });
      const symbol = pickSymbolCode(firstStock);
      if (symbol) {
        resolved.push(symbol);
        break;
      }
    } catch (error) {
      warnings.push(`证券名称 ${candidate} 解析失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return uniqueSymbols(resolved);
}

async function inferSymbols(plan: QuantRunPlan, warnings: string[]): Promise<string[]> {
  const planned = inferPlannedSymbols(plan);
  if (planned.length > 0) {
    return planned;
  }

  return resolveSymbolsFromQuestion(plan.question, warnings);
}

function inferHistoryLimit(plan: QuantRunPlan): number {
  const source = `${plan.timeRange ?? ''} ${plan.question}`.replace(/\s+/g, '');
  const dayMatch = source.match(/最近(\d+)(?:个)?(?:交易日|日|天)/);
  const rawDays = dayMatch?.[1] ? Number.parseInt(dayMatch[1], 10) : 120;
  if (!Number.isFinite(rawDays)) {
    return 120;
  }
  return Math.min(Math.max(rawDays, 20), 500);
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
  let peak = closes[0] ?? 0;
  let maxDrawdown = 0;
  for (const close of closes) {
    peak = Math.max(peak, close);
    if (peak > 0) {
      maxDrawdown = Math.min(maxDrawdown, ((close - peak) / peak) * 100);
    }
  }

  return {
    periodReturn:
      firstClose && lastClose ? round(((lastClose - firstClose) / firstClose) * 100) : null,
    periodHigh: highs.length ? round(Math.max(...highs)) : null,
    periodLow: lows.length ? round(Math.min(...lows)) : null,
    maxDrawdown: round(maxDrawdown),
    volatility20d: round(Math.sqrt(variance) * Math.sqrt(252) * 100),
    avgVolume20d: round(mean(volumes.slice(-20))),
    ma5: round(mean(closes.slice(-5))),
    ma10: round(mean(closes.slice(-10))),
    ma20: round(mean(closes.slice(-20))),
  };
}

function extractBarsFromAsset(asset: JsonRecord | null): JsonRecord[] {
  if (!asset) {
    return [];
  }
  const kline = asRecord(asset.kline) ?? asRecord(asset.history);
  const candidates = [
    kline?.bars,
    kline?.data,
    kline?.items,
    asset.bars,
    asset.klines,
    asset.candles,
  ];
  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) {
      continue;
    }
    const bars = candidate.map(asRecord).filter((item): item is JsonRecord => Boolean(item));
    if (bars.length > 0) {
      return bars;
    }
  }
  return [];
}

function dateKeyForBar(bar: JsonRecord, index: number): string {
  const raw = bar.date ?? bar.time ?? bar.trade_date ?? index;
  return String(raw).slice(0, 10);
}

function buildReturnSeries(asset: JsonRecord): Map<string, number> {
  const bars = extractBarsFromAsset(asset);
  const ordered = bars
    .map((bar, index) => ({
      date: dateKeyForBar(bar, index),
      close: numeric(bar.close),
    }))
    .filter((item): item is { date: string; close: number } => item.close !== null && item.close > 0);

  const series = new Map<string, number>();
  for (let index = 1; index < ordered.length; index += 1) {
    const previous = ordered[index - 1];
    const current = ordered[index];
    if (previous.close > 0) {
      series.set(current.date, Math.log(current.close / previous.close));
    }
  }
  return series;
}

function pearson(left: number[], right: number[]): number | null {
  if (left.length < 3 || left.length !== right.length) {
    return null;
  }
  const leftMean = mean(left);
  const rightMean = mean(right);
  if (leftMean === null || rightMean === null) {
    return null;
  }
  let numerator = 0;
  let leftVariance = 0;
  let rightVariance = 0;
  for (let index = 0; index < left.length; index += 1) {
    const leftDiff = left[index] - leftMean;
    const rightDiff = right[index] - rightMean;
    numerator += leftDiff * rightDiff;
    leftVariance += leftDiff ** 2;
    rightVariance += rightDiff ** 2;
  }
  const denominator = Math.sqrt(leftVariance * rightVariance);
  return denominator === 0 ? null : numerator / denominator;
}

function buildCorrelationSummary(assets: JsonRecord[]): JsonRecord {
  const series = new Map<string, Map<string, number>>();
  const sampleLengths: Record<string, number> = {};
  for (const asset of assets) {
    const symbol = String(asset.symbol ?? asRecord(asset.quote)?.symbol ?? '');
    if (!symbol) {
      continue;
    }
    const returns = buildReturnSeries(asset);
    if (returns.size > 0) {
      series.set(symbol, returns);
      sampleLengths[symbol] = returns.size;
    }
  }

  const symbols = Array.from(series.keys());
  const matrix: JsonRecord[] = [];
  const topPairs: JsonRecord[] = [];
  for (const left of symbols) {
    const row: JsonRecord = { symbol: left };
    for (const right of symbols) {
      const leftSeries = series.get(left)!;
      const rightSeries = series.get(right)!;
      const commonDates = Array.from(leftSeries.keys()).filter((date) => rightSeries.has(date));
      const leftValues = commonDates.map((date) => leftSeries.get(date)!);
      const rightValues = commonDates.map((date) => rightSeries.get(date)!);
      const correlation = pearson(leftValues, rightValues);
      row[right] = round(correlation, 4);
      if (left < right) {
        topPairs.push({
          left,
          right,
          correlation: round(correlation, 4),
          overlap: commonDates.length,
        });
      }
    }
    matrix.push(row);
  }

  topPairs.sort((a, b) => Math.abs(numeric(b.correlation) ?? -1) - Math.abs(numeric(a.correlation) ?? -1));
  return {
    method: 'pearson_log_return',
    symbols,
    sample_lengths: sampleLengths,
    matrix,
    top_pairs: topPairs.slice(0, 10),
    data_quality: {
      status: symbols.length >= 2 ? 'ok' : 'warning',
      warnings: symbols.length >= 2 ? [] : ['相关性计算至少需要两个有历史 K 线的标的。'],
    },
  };
}

function buildLiquiditySummary(assets: JsonRecord[]): JsonRecord {
  const rows = assets.map((asset) => {
    const quote = asRecord(asset.quote);
    const bars = extractBarsFromAsset(asset);
    const recent = bars.slice(-20);
    const volumes = recent.map((bar) => numeric(bar.volume)).filter((value): value is number => value !== null);
    const amounts = recent.map((bar) => numeric(bar.amount)).filter((value): value is number => value !== null);
    const latestAmount = numeric(quote?.amount) ?? amounts.at(-1) ?? null;
    const avgAmount20 = mean(amounts);
    const avgVolume20 = mean(volumes);
    const marketCap = numeric(quote?.float_market_cap) ?? numeric(quote?.market_cap);
    const turnoverProxyPct = marketCap && (latestAmount ?? avgAmount20)
      ? ((latestAmount ?? avgAmount20 ?? 0) / marketCap) * 100
      : null;

    let previousClose: number | null = null;
    const amihudValues: number[] = [];
    for (const bar of bars.slice(-60)) {
      const close = numeric(bar.close);
      const amount = numeric(bar.amount);
      if (close !== null && previousClose !== null && previousClose > 0 && amount !== null && amount > 0) {
        amihudValues.push(Math.abs(close / previousClose - 1) / amount);
      }
      if (close !== null) {
        previousClose = close;
      }
    }
    const amihud = mean(amihudValues);
    const warnings: string[] = [];
    if (bars.length < 20) {
      warnings.push('K 线样本少于 20 条，流动性均值稳定性较弱。');
    }
    if (avgAmount20 === null) {
      warnings.push('缺少成交额字段，无法计算 20 日平均成交额。');
    }
    if (amihud === null) {
      warnings.push('缺少连续收盘价或成交额，无法计算 Amihud 非流动性。');
    }

    return {
      symbol: String(asset.symbol ?? quote?.symbol ?? ''),
      name: String(asset.name ?? quote?.name ?? asset.symbol ?? ''),
      sample_size: bars.length,
      latest_amount: round(latestAmount),
      avg_amount_20d: round(avgAmount20),
      avg_volume_20d: round(avgVolume20),
      turnover_proxy_pct: round(turnoverProxyPct, 4),
      amihud_illiquidity_x1e9: round(amihud === null ? null : amihud * 1_000_000_000, 6),
      liquidity_score:
        avgAmount20 === null ? 'unknown' : avgAmount20 >= 1_000_000_000 ? 'high' : avgAmount20 >= 100_000_000 ? 'medium' : 'low',
      warnings,
    };
  });

  return {
    method: 'amount_volume_amihud_proxy',
    window: '20d',
    rows,
    data_quality: {
      status: rows.some((row) => Array.isArray(row.warnings) && row.warnings.length > 0) ? 'warning' : 'ok',
      warnings: rows.flatMap((row) => (Array.isArray(row.warnings) ? row.warnings : [])),
    },
  };
}

async function fetchJson(endpoint: string, init: RequestInit = {}): Promise<JsonRecord> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(`${MARKET_API_BASE_URL}${endpoint}`, {
      ...init,
      signal: controller.signal,
      cache: 'no-store',
      headers: {
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init.headers ?? {}),
      },
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
  backtest?: JsonRecord | null;
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
    backtest: params.backtest ?? null,
    financials,
    fundamentalIndicators: params.fundamentalIndicators ?? null,
    announcements,
    computedMetrics: calculateMetrics(kline),
    liquidity: buildLiquiditySummary([]),
  };
}

function buildComparisonSummary(assets: JsonRecord[]): JsonRecord {
  const rows = assets.map((asset) => {
    const metrics = asRecord(asset.computedMetrics);
    const quote = asRecord(asset.quote);
    const symbol = String(asset.symbol ?? quote?.symbol ?? '');
    return {
      symbol,
      name: asset.name ?? quote?.name ?? symbol,
      price: quote?.price ?? null,
      change_percent: quote?.change_percent ?? null,
      period_return: metrics?.periodReturn ?? null,
      max_drawdown: metrics?.maxDrawdown ?? null,
      volatility20d: metrics?.volatility20d ?? null,
      avg_volume_20d: metrics?.avgVolume20d ?? null,
      amount: quote?.amount ?? null,
      as_of: asset.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? null,
      source: asset.source ?? quote?.source ?? null,
    };
  });

  const numericRows = rows.map((row) => ({
    ...row,
    periodReturnNumber: numeric(row.period_return),
    drawdownNumber: numeric(row.max_drawdown),
    volatilityNumber: numeric(row.volatility20d),
  }));
  const bestReturn = numericRows
    .filter((row) => row.periodReturnNumber !== null)
    .sort((a, b) => (b.periodReturnNumber ?? 0) - (a.periodReturnNumber ?? 0))[0];
  const lowestDrawdown = numericRows
    .filter((row) => row.drawdownNumber !== null)
    .sort((a, b) => Math.abs(a.drawdownNumber ?? 0) - Math.abs(b.drawdownNumber ?? 0))[0];
  const lowestVolatility = numericRows
    .filter((row) => row.volatilityNumber !== null)
    .sort((a, b) => (a.volatilityNumber ?? 0) - (b.volatilityNumber ?? 0))[0];

  return {
    rows,
    leaders: {
      best_return: bestReturn
        ? { symbol: bestReturn.symbol, name: bestReturn.name, value: bestReturn.period_return }
        : null,
      lowest_drawdown: lowestDrawdown
        ? { symbol: lowestDrawdown.symbol, name: lowestDrawdown.name, value: lowestDrawdown.max_drawdown }
        : null,
      lowest_volatility: lowestVolatility
        ? { symbol: lowestVolatility.symbol, name: lowestVolatility.name, value: lowestVolatility.volatility20d }
        : null,
    },
  };
}

async function fetchSymbolDataset(params: {
  projectPath: string;
  runId: string;
  symbol: string;
  plan: QuantRunPlan;
  rawFiles: string[];
  warnings: string[];
}): Promise<JsonRecord> {
  const symbolRawDir = path.join(params.projectPath, 'data_file', 'raw', params.runId, params.symbol);
  const historyLimit = inferHistoryLimit(params.plan);
  const quote = await fetchJson(`/api/v1/quotes/realtime/${params.symbol}`);
  const assetType = typeof quote.asset_type === 'string' ? quote.asset_type : 'stock';
  const quotePath = path.join(symbolRawDir, 'quote.json');
  await writeJson(quotePath, quote);
  params.rawFiles.push(path.relative(params.projectPath, quotePath).replaceAll(path.sep, '/'));

  let kline: JsonRecord | null = null;
  let technicalIndicators: JsonRecord | null = null;
  let backtest: JsonRecord | null = null;
  let financials: JsonRecord | null = null;
  let fundamentalIndicators: JsonRecord | null = null;
  let announcements: JsonRecord | null = null;

  if (params.plan.dataRequirements.some((endpoint) => endpoint.includes('/quotes/history/'))) {
    try {
      kline = await fetchJson(`/api/v1/quotes/history/${params.symbol}?period=daily&adjustment=qfq&limit=${historyLimit}`);
      const filePath = path.join(symbolRawDir, 'kline-daily-qfq.json');
      await writeJson(filePath, kline);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 历史 K 线预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (params.plan.dataRequirements.some((endpoint) => endpoint.includes('/indicators/technical/'))) {
    try {
      technicalIndicators = await fetchJson(
        `/api/v1/indicators/technical/${params.symbol}?period=daily&adjustment=qfq&limit=${historyLimit}`
      );
      const filePath = path.join(symbolRawDir, 'technical-indicators.json');
      await writeJson(filePath, technicalIndicators);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 技术指标预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (params.plan.dataRequirements.some((endpoint) => endpoint.includes('/backtests/ma-crossover/'))) {
    try {
      backtest = await fetchJson(
        `/api/v1/backtests/ma-crossover/${params.symbol}?fast_window=20&slow_window=60&period=daily&adjustment=qfq&limit=250&fee_bps=5`
      );
      const filePath = path.join(symbolRawDir, 'backtest-ma-crossover.json');
      await writeJson(filePath, backtest);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 均线突破回测预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/fundamentals/financials/'))
  ) {
    try {
      financials = await fetchJson(`/api/v1/fundamentals/financials/${params.symbol}?limit=8`);
      const filePath = path.join(symbolRawDir, 'financials.json');
      await writeJson(filePath, financials);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 财务摘要预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/indicators/fundamental/'))
  ) {
    try {
      fundamentalIndicators = await fetchJson(`/api/v1/indicators/fundamental/${params.symbol}?limit=8`);
      const filePath = path.join(symbolRawDir, 'fundamental-indicators.json');
      await writeJson(filePath, fundamentalIndicators);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 财务衍生指标预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (
    assetType === 'stock' &&
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/events/announcements/'))
  ) {
    try {
      announcements = await fetchJson(`/api/v1/events/announcements/${params.symbol}?limit=20`);
      const filePath = path.join(symbolRawDir, 'announcements.json');
      await writeJson(filePath, announcements);
      params.rawFiles.push(path.relative(params.projectPath, filePath).replaceAll(path.sep, '/'));
    } catch (error) {
      params.warnings.push(`${params.symbol} 公告事件预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return finalDataFromResponses({
    symbol: params.symbol,
    quote,
    kline,
    technicalIndicators,
    backtest,
    financials,
    fundamentalIndicators,
    announcements,
  });
}

export async function prefetchQuantDataForRunPlan(params: {
  projectPath: string;
  plan: QuantRunPlan;
}): Promise<PrefetchResult> {
  if (params.plan.status === 'needs_clarification' || params.plan.clarification?.required) {
    return { skipped: true, summary: '任务仍需用户补充关键信息，跳过平台预取数据。' };
  }

  if (!isQuantAnalysisPlan(params.plan)) {
    return { skipped: true, summary: `能力 ${params.plan.capabilityId} 暂不需要平台预取数据。` };
  }

  const symbolResolutionWarnings: string[] = [];
  const symbols = await inferSymbols(params.plan, symbolResolutionWarnings);
  if (symbols.length === 0) {
    return {
      skipped: true,
      summary: `未识别到 A 股、指数或 ETF 标的，跳过平台预取。${symbolResolutionWarnings.length ? ` ${symbolResolutionWarnings.join('；')}` : ''}`,
    };
  }

  await ensureQuantWorkspace(params.projectPath);
  const runId = params.plan.runId;
  const rawFiles: string[] = [];
  const warnings: string[] = [...symbolResolutionWarnings];

  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'data_prefetch_started',
    stage: 'data_collection',
    status: 'pending',
    run_id: runId,
    summary: `平台开始预取 ${symbols.join('、')} 的真实行情数据。`,
  });

  const quoteMap = new Map<string, JsonRecord>();
  if (symbols.length > 1) {
    try {
      const batchQuotes = await fetchJson('/api/v1/quotes/realtime', {
        method: 'POST',
        body: JSON.stringify({ symbols }),
      });
      const quoteRows = Array.isArray(batchQuotes.quotes) ? batchQuotes.quotes : [];
      for (const row of quoteRows) {
        const record = asRecord(row);
        const symbol = typeof record?.symbol === 'string' ? record.symbol : null;
        if (symbol && record) {
          quoteMap.set(symbol, record);
        }
      }
      const batchPath = path.join(params.projectPath, 'data_file', 'raw', runId, 'batch-quotes.json');
      await writeJson(batchPath, batchQuotes);
      rawFiles.push(path.relative(params.projectPath, batchPath).replaceAll(path.sep, '/'));
    } catch (error) {
      warnings.push(`批量实时行情预取失败，降级为逐只获取：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const assets: JsonRecord[] = [];
  for (const symbol of symbols) {
    try {
      const asset = await fetchSymbolDataset({
        projectPath: params.projectPath,
        runId,
        symbol,
        plan: params.plan,
        rawFiles,
        warnings,
      });
      if (quoteMap.has(symbol)) {
        asset.quote = quoteMap.get(symbol);
      }
      assets.push(asset);
    } catch (error) {
      warnings.push(`${symbol} 预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (assets.length === 0) {
    throw new Error(`所有标的预取失败：${warnings.join('；')}`);
  }

  const primaryAsset = assets[0];
  const finalData = symbols.length === 1
    ? {
        ...primaryAsset,
        liquidity: buildLiquiditySummary([primaryAsset]),
      }
    : {
        ...primaryAsset,
        schemaVersion: 1,
        generatedAt: new Date().toISOString(),
        primarySymbol: primaryAsset.symbol,
        requestedSymbols: symbols,
        symbols: assets.map((asset) => asset.symbol),
        assetCount: assets.length,
        assets,
        comparison: buildComparisonSummary(assets),
        correlation: buildCorrelationSummary(assets),
        liquidity: buildLiquiditySummary(assets),
        warnings,
      };
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
    summary: `平台已预取 ${assets.map((asset) => asset.symbol).join('、')} 数据：raw ${rawFiles.length} 个文件，final 数据已写入。${warnings.length ? ` 警告：${warnings.join('；')}` : ''}`,
  });

  return {
    skipped: false,
    symbol: String(primaryAsset.symbol ?? symbols[0]),
    symbols: assets.map((asset) => String(asset.symbol ?? '')).filter(Boolean),
    finalDataPath,
    rawFiles,
    summary: `已预取 ${assets.map((asset) => asset.symbol).join('、')} 真实数据并生成 ${finalDataPath}。`,
  };
}
