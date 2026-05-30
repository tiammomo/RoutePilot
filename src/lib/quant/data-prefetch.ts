import { createHash } from 'crypto';
import fs from 'fs/promises';
import path from 'path';
import { ensureBaselineEvidenceFiles } from '@/lib/quant/evidence';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace, QuantRunPlan } from '@/lib/quant/workspace';
import { serializeQuantVisualizationTemplate } from '@/lib/quant/visualization-templates';

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
  { keyword: '通富微电', symbol: '002156' },
  { keyword: '平安银行', symbol: '000001' },
  { keyword: '招商银行', symbol: '600036' },
  { keyword: '杭钢股份', symbol: '600126' },
  { keyword: '京沪高铁', symbol: '601816' },
  { keyword: '三七互娱', symbol: '002555' },
  { keyword: '中国黄金', symbol: '600916' },
  { keyword: '完美世界', symbol: '002624' },
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

function sum(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0);
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
  const amounts = bars.map((bar) => numeric(bar.amount)).filter((value): value is number => value !== null);
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
    return20d: calculateWindowReturn(closes, 20),
    return60d: calculateWindowReturn(closes, 60),
    return120d: calculateWindowReturn(closes, 120),
    periodHigh: highs.length ? round(Math.max(...highs)) : null,
    periodLow: lows.length ? round(Math.min(...lows)) : null,
    maxDrawdown: round(maxDrawdown),
    volatility20d: round(Math.sqrt(variance) * Math.sqrt(252) * 100),
    avgVolume20d: round(mean(volumes.slice(-20))),
    avgAmount20d: round(mean(amounts.slice(-20))),
    ma5: round(mean(closes.slice(-5))),
    ma10: round(mean(closes.slice(-10))),
    ma20: round(mean(closes.slice(-20))),
  };
}

function calculateWindowReturn(closes: number[], windowSize: number): number | null {
  const latest = closes.at(-1);
  const baseline = closes.length > windowSize ? closes.at(-1 - windowSize) : closes[0];
  if (!latest || !baseline || baseline <= 0) {
    return null;
  }
  return round(((latest - baseline) / baseline) * 100);
}

function firstDateFromBars(bars: JsonRecord[]): string | null {
  const first = bars[0];
  const value = first?.date ?? first?.time ?? first?.trade_date;
  return typeof value === 'string' ? value.slice(0, 10) : null;
}

function lastDateFromBars(bars: JsonRecord[]): string | null {
  const last = bars.at(-1);
  const value = last?.date ?? last?.time ?? last?.trade_date;
  return typeof value === 'string' ? value.slice(0, 10) : null;
}

function ensureTechnicalSummary(asset: JsonRecord): JsonRecord {
  const quote = asRecord(asset.quote);
  const kline = asRecord(asset.kline) ?? asRecord(asset.history);
  const bars = extractBarsFromAsset(asset);
  const metrics = asRecord(asset.computedMetrics) ?? calculateMetrics(kline);
  const technicalIndicators = asRecord(asset.technicalIndicators) ?? {};
  const existingSummary = asRecord(technicalIndicators.summary) ?? {};
  const latestClose = numeric(existingSummary.latest_close) ?? numeric(quote?.price) ?? numeric(bars.at(-1)?.close);
  const ma5 = numeric(existingSummary.ma5) ?? numeric(metrics.ma5);
  const ma10 = numeric(existingSummary.ma10) ?? numeric(metrics.ma10);
  const ma20 = numeric(existingSummary.ma20) ?? numeric(metrics.ma20);
  const return20d = numeric(existingSummary.return_20d_pct) ?? numeric(metrics.return20d);
  const return60d = numeric(existingSummary.return_60d_pct) ?? numeric(metrics.return60d);
  const return120d =
    numeric(existingSummary.return_120d_pct) ??
    numeric(existingSummary.period_return_pct) ??
    numeric(metrics.return120d) ??
    numeric(metrics.periodReturn);
  const maxDrawdown = numeric(existingSummary.max_drawdown_pct) ?? numeric(metrics.maxDrawdown);
  const volatility = numeric(existingSummary.volatility_20d_annualized_pct) ?? numeric(existingSummary.volatility_annualized_pct) ?? numeric(metrics.volatility20d);
  const avgVolume = numeric(existingSummary.avg_volume20) ?? numeric(metrics.avgVolume20d);
  const symbol = String(asset.symbol ?? quote?.symbol ?? '');
  const name = String(asset.name ?? quote?.name ?? symbol);

  let trendState = '趋势待确认：K 线或均线样本不足。';
  if (latestClose !== null && ma5 !== null && ma10 !== null && ma20 !== null) {
    if (latestClose >= ma5 && latestClose >= ma10 && latestClose >= ma20) {
      trendState = '短中期强势：最新价站上 MA5/MA10/MA20。';
    } else if (latestClose < ma5 && latestClose < ma10 && latestClose < ma20) {
      trendState = '短中期偏弱：最新价低于 MA5/MA10/MA20。';
    } else {
      trendState = '震荡观察：最新价处于均线区间内，需要等待方向确认。';
    }
  }

  const summary = {
    symbol,
    name,
    sample_window: bars.length
      ? `${firstDateFromBars(bars) ?? '-'} 至 ${lastDateFromBars(bars) ?? '-'}，${bars.length} 根日 K`
      : '暂无历史 K 线样本',
    return_20d_pct: round(return20d),
    return_60d_pct: round(return60d),
    return_120d_pct: round(return120d),
    period_return_pct: round(numeric(existingSummary.period_return_pct) ?? numeric(metrics.periodReturn)),
    max_drawdown_pct: round(maxDrawdown),
    volatility_20d_annualized_pct: round(volatility),
    ma5: round(ma5),
    ma10: round(ma10),
    ma20: round(ma20),
    latest_close: round(latestClose),
    trend_state: String(existingSummary.trend_state ?? trendState),
    volume_note: avgVolume === null
      ? '缺少连续成交量，量能指标待补充。'
      : `20 日均量约 ${round(avgVolume, 0)} 手。`,
  };

  asset.technicalIndicators = {
    ...technicalIndicators,
    summary,
    computedMetrics: metrics,
    data_quality: technicalIndicators.data_quality ?? {
      status: bars.length >= 20 ? 'ok' : 'warning',
      warnings: bars.length >= 20 ? [] : ['历史 K 线样本少于 20 条，技术指标稳定性较弱。'],
    },
  };
  return summary;
}

function buildFinancialQuality(asset: JsonRecord): JsonRecord {
  const quote = asRecord(asset.quote);
  const symbol = String(asset.symbol ?? quote?.symbol ?? '');
  const name = String(asset.name ?? quote?.name ?? symbol);
  const fundamental = asRecord(asset.fundamentalIndicators);
  const financials = asRecord(asset.financials);
  const summary = asRecord(fundamental?.summary);
  const firstReport = Array.isArray(financials?.reports)
    ? asRecord(financials.reports[0])
    : null;
  const source = summary ?? firstReport ?? {};
  const roe = numeric(source.latest_weighted_roe ?? source.weighted_roe);
  const grossMargin = numeric(source.latest_gross_margin ?? source.gross_margin);
  const netMargin = numeric(source.latest_net_margin ?? source.net_margin);
  const revenueYoy = numeric(source.latest_revenue_yoy ?? source.revenue_yoy);
  const profitYoy = numeric(source.latest_net_profit_yoy ?? source.net_profit_yoy);
  const scoreParts = [
    roe === null ? null : Math.min(Math.max(roe * 3, 0), 30),
    grossMargin === null ? null : Math.min(Math.max(grossMargin / 2, 0), 25),
    netMargin === null ? null : Math.min(Math.max(netMargin / 2, 0), 25),
    revenueYoy === null ? null : Math.min(Math.max(revenueYoy / 2, -10), 15),
    profitYoy === null ? null : Math.min(Math.max(profitYoy / 4, -10), 15),
  ].filter((value): value is number => value !== null);
  const qualityScore = scoreParts.length ? Math.max(0, Math.min(100, round(sum(scoreParts), 0) ?? 0)) : null;
  let qualityLabel = '财务质量待确认';
  if (qualityScore !== null) {
    if (qualityScore >= 75) {
      qualityLabel = '盈利质量较强';
    } else if (qualityScore >= 60) {
      qualityLabel = '质量与成长较均衡';
    } else if (qualityScore >= 40) {
      qualityLabel = '质量约束较明显';
    } else {
      qualityLabel = '财务质量偏弱或缺失较多';
    }
  }

  const strengths: string[] = [];
  const watchItems: string[] = [];
  if ((grossMargin ?? 0) >= 40) strengths.push('毛利率处于较高水平。');
  if ((netMargin ?? 0) >= 15) strengths.push('净利率表现较好。');
  if ((revenueYoy ?? 0) > 20 || (profitYoy ?? 0) > 20) strengths.push('最近报告期仍有增长弹性。');
  if ((roe ?? 0) < 5) watchItems.push('ROE 偏低，需要关注资产回报效率。');
  if ((netMargin ?? 0) < 8) watchItems.push('净利率偏低，盈利质量约束更强。');
  if ((revenueYoy ?? 0) < 0 || (profitYoy ?? 0) < 0) watchItems.push('收入或利润同比为负，需要关注基本面压力。');
  if (strengths.length === 0) strengths.push('可作为候选池横向比较样本。');
  if (watchItems.length === 0) watchItems.push('仍需结合现金流、负债结构和行业景气度复核。');

  const quality = {
    symbol,
    name,
    latest_report_date: source.latest_report_date ?? source.report_date ?? null,
    roe_pct: round(roe, 4),
    gross_margin_pct: round(grossMargin, 4),
    net_margin_pct: round(netMargin, 4),
    revenue_yoy_pct: round(revenueYoy, 4),
    net_profit_yoy_pct: round(profitYoy, 4),
    quality_score: qualityScore,
    quality_label: qualityLabel,
    strengths,
    watch_items: watchItems,
  };

  asset.financialQuality = quality;
  return quality;
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

async function readJson(filePath: string): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    return asRecord(JSON.parse(content));
  } catch {
    return null;
  }
}

function isInside(parent: string, candidate: string): boolean {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function resolveInsideProject(projectPath: string, inputPath: string): string {
  const resolved = path.isAbsolute(inputPath)
    ? path.resolve(inputPath)
    : path.resolve(projectPath, inputPath);
  if (!isInside(projectPath, resolved)) {
    throw new Error(`附件路径必须位于当前生成项目内：${inputPath}`);
  }
  return resolved;
}

function inferImageMimeType(filePath: string, buffer: Buffer): string {
  const lower = filePath.toLowerCase();
  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) || lower.endsWith('.png')) {
    return 'image/png';
  }
  if ((buffer[0] === 0xff && buffer[1] === 0xd8) || lower.endsWith('.jpg') || lower.endsWith('.jpeg')) {
    return 'image/jpeg';
  }
  if (buffer.subarray(0, 3).toString('ascii') === 'GIF' || lower.endsWith('.gif')) {
    return 'image/gif';
  }
  if (buffer.subarray(0, 4).toString('ascii') === 'RIFF' && buffer.subarray(8, 12).toString('ascii') === 'WEBP') {
    return 'image/webp';
  }
  return 'application/octet-stream';
}

function readImageSize(buffer: Buffer, mimeType: string): { width: number | null; height: number | null } {
  if (mimeType === 'image/png' && buffer.length >= 24) {
    return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
  }

  if (mimeType === 'image/gif' && buffer.length >= 10) {
    return { width: buffer.readUInt16LE(6), height: buffer.readUInt16LE(8) };
  }

  if (mimeType === 'image/jpeg' && buffer.length > 4) {
    let offset = 2;
    while (offset + 9 < buffer.length) {
      if (buffer[offset] !== 0xff) {
        offset += 1;
        continue;
      }
      const marker = buffer[offset + 1];
      const length = buffer.readUInt16BE(offset + 2);
      const isSofMarker = [
        0xc0,
        0xc1,
        0xc2,
        0xc3,
        0xc5,
        0xc6,
        0xc7,
        0xc9,
        0xca,
        0xcb,
        0xcd,
        0xce,
        0xcf,
      ].includes(marker);
      if (isSofMarker && offset + 8 < buffer.length) {
        return {
          height: buffer.readUInt16BE(offset + 5),
          width: buffer.readUInt16BE(offset + 7),
        };
      }
      offset += Math.max(2 + length, 2);
    }
  }

  return { width: null, height: null };
}

const PORTFOLIO_IMAGE_FIELDS = [
  'account_total_asset',
  'cash_available',
  'market_value',
  'daily_pnl',
  'total_pnl',
  'position_ratio',
  'holdings[].name',
  'holdings[].quantity',
  'holdings[].cost_price',
  'holdings[].current_price',
  'holdings[].market_value',
  'holdings[].pnl',
  'holdings[].pnl_percent',
];

async function buildImageExtractionEvidence(
  projectPath: string,
  runId: string,
  warnings: string[]
): Promise<JsonRecord | null> {
  const contextPath = path.join(projectPath, '.quantpilot', 'attachments.json');
  const context = await readJson(contextPath);
  const attachments = Array.isArray(context?.attachments)
    ? context.attachments.map(asRecord).filter((item): item is JsonRecord => Boolean(item))
    : [];

  if (attachments.length === 0) {
    return null;
  }

  const images: JsonRecord[] = [];
  for (let index = 0; index < attachments.length; index += 1) {
    const attachment = attachments[index];
    const sourcePath =
      typeof attachment.absolutePath === 'string'
        ? attachment.absolutePath
        : typeof attachment.path === 'string'
          ? attachment.path
          : null;

    if (!sourcePath) {
      warnings.push(`上传图片附件 ${String(attachment.name ?? index + 1)} 缺少 path/absolutePath。`);
      continue;
    }

    try {
      const absolutePath = resolveInsideProject(projectPath, sourcePath);
      const buffer = await fs.readFile(absolutePath);
      const stat = await fs.stat(absolutePath);
      const mimeType =
        typeof attachment.mimeType === 'string' && attachment.mimeType.trim()
          ? attachment.mimeType.trim()
          : inferImageMimeType(absolutePath, buffer);
      const size = readImageSize(buffer, mimeType);
      images.push({
        id: String(attachment.id ?? `image-${index + 1}`),
        name: String(attachment.name ?? path.basename(absolutePath)),
        path: path.relative(projectPath, absolutePath).replaceAll(path.sep, '/'),
        url: typeof attachment.url === 'string' ? attachment.url : null,
        publicUrl: typeof attachment.publicUrl === 'string' ? attachment.publicUrl : null,
        mimeType,
        size: stat.size,
        width: size.width,
        height: size.height,
        sha256: createHash('sha256').update(buffer).digest('hex'),
      });
    } catch (error) {
      warnings.push(
        `上传图片附件 ${String(attachment.name ?? sourcePath)} 检查失败：${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  if (images.length === 0) {
    return null;
  }

  const now = new Date().toISOString();
  const payload = {
    schemaVersion: 1,
    tool: 'quant-image-extraction',
    status: 'metadata_ready',
    createdAt: now,
    runId,
    attachmentContextPath: '.quantpilot/attachments.json',
    images,
    visualRecognition: {
      status: 'requires_vision_provider',
      reason: '平台已确认图片文件、格式、尺寸和哈希；若当前模型或工具不能直接 OCR，必须保留截图字段缺口并要求用户确认。',
      fallbackRule: '不得编造持仓数量、成本、现金、盈亏和仓位比例；未识别字段必须写入 data_gaps 和 evidence/data_quality.json。',
    },
    imageExtraction: {
      source: 'uploaded_image',
      extracted_at: now,
      extractedFields: {
        account_total_asset: null,
        cash_available: null,
        market_value: null,
        daily_pnl: null,
        total_pnl: null,
        position_ratio: null,
        holdings: [],
      },
      needs_manual_confirmation: true,
      manual_confirmation_fields: PORTFOLIO_IMAGE_FIELDS,
    },
    dashboardContract: {
      requiredFinalDataFields: ['portfolio', 'holdings', 'assets', 'comparison', 'imageExtraction'],
      evidenceFiles: ['evidence/image_extraction.json', 'evidence/data_quality.json', 'evidence/sources.json'],
    },
  };

  await writeJson(path.join(projectPath, 'evidence', 'image_extraction.json'), payload);
  await appendQuantWorkspaceEvent(projectPath, {
    event_type: 'image_attachment_evidence_created',
    stage: 'data_collection',
    status: 'warning',
    run_id: runId,
    artifact_path: 'evidence/image_extraction.json',
    summary: '已为上传图片生成附件证据和截图识别契约；未确认字段需要在看板中标注。',
    created_at: now,
  });
  warnings.push('上传图片已建立附件证据；截图 OCR 字段未完全确认，页面必须展示数据缺口和人工确认要求。');
  return payload;
}

async function augmentEvidenceWithImageExtraction(projectPath: string, imageExtractionEvidence: JsonRecord) {
  const createdAt = typeof imageExtractionEvidence.createdAt === 'string'
    ? imageExtractionEvidence.createdAt
    : new Date().toISOString();
  const images = Array.isArray(imageExtractionEvidence.images) ? imageExtractionEvidence.images : [];
  const qualityPath = path.join(projectPath, 'evidence', 'data_quality.json');
  const sourcesPath = path.join(projectPath, 'evidence', 'sources.json');
  const quality = (await readJson(qualityPath)) ?? {};
  const sources = (await readJson(sourcesPath)) ?? {};
  const dataset = {
    id: 'uploaded_image_attachment',
    name: '用户上传持仓截图',
    source: 'uploaded_image',
    endpoint: 'UPLOAD .quantpilot/attachments.json',
    artifact_path: 'evidence/image_extraction.json',
    row_count: images.length,
    fetched_at: createdAt,
    as_of: createdAt,
    missing_fields: PORTFOLIO_IMAGE_FIELDS,
    warnings: ['截图文件已确认，但 OCR 字段需要模型或用户继续确认，不允许编造持仓明细。'],
    status: 'warning',
    required: true,
  };

  quality.status = quality.status === 'error' ? 'error' : 'warning';
  const qualityDatasets = Array.isArray(quality.datasets) ? quality.datasets : [];
  if (!qualityDatasets.some((item) => asRecord(item)?.id === dataset.id)) {
    qualityDatasets.push(dataset);
  }
  quality.datasets = qualityDatasets;

  const qualityChecks = Array.isArray(quality.checks) ? quality.checks : [];
  if (!qualityChecks.some((item) => asRecord(item)?.id === 'uploaded_image_attachment_quality')) {
    qualityChecks.push({
      id: 'uploaded_image_attachment_quality',
      dataset: dataset.id,
      status: 'warning',
      row_count: images.length,
      missing_fields: PORTFOLIO_IMAGE_FIELDS,
      summary: '用户上传截图已进入证据链，关键持仓字段仍需 OCR 或用户确认。',
    });
  }
  quality.checks = qualityChecks;

  const qualityWarnings = Array.isArray(quality.warnings) ? quality.warnings : [];
  qualityWarnings.push('用户上传截图字段未完全结构化，调仓分析需显式标注截图识别边界。');
  quality.warnings = qualityWarnings;

  const qualityLimitations = Array.isArray(quality.limitations) ? quality.limitations : [];
  qualityLimitations.push('截图类任务必须区分图片元数据、行情接口数据和模型推断，不能把未确认字段当作真实持仓。');
  quality.limitations = qualityLimitations;

  const sourceRows = Array.isArray(sources.sources) ? sources.sources : [];
  if (!sourceRows.some((item) => asRecord(item)?.id === dataset.id)) {
    sourceRows.push({
      id: dataset.id,
      dataset: dataset.name,
      source: dataset.source,
      endpoint: dataset.endpoint,
      artifact_path: dataset.artifact_path,
      row_count: dataset.row_count,
      fetched_at: dataset.fetched_at,
      as_of: dataset.as_of,
      status: dataset.status,
    });
  }
  sources.sources = sourceRows;

  await Promise.all([
    writeJson(qualityPath, quality),
    writeJson(sourcesPath, sources),
  ]);
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
  const financialQualityRows = assets.map((asset) => asRecord(asset.financialQuality) ?? buildFinancialQuality(asset));
  const rows = assets.map((asset) => {
    const metrics = asRecord(asset.computedMetrics);
    const quote = asRecord(asset.quote);
    const symbol = String(asset.symbol ?? quote?.symbol ?? '');
    const bars = extractBarsFromAsset(asset);
    const technicalSummary = asRecord(asRecord(asset.technicalIndicators)?.summary) ?? ensureTechnicalSummary(asset);
    const financialQuality = asRecord(asset.financialQuality) ?? financialQualityRows.find((row) => row?.symbol === symbol);
    const avgAmount20d = numeric(metrics?.avgAmount20d);
    const amount = numeric(quote?.amount);
    return {
      symbol,
      name: asset.name ?? quote?.name ?? symbol,
      price: quote?.price ?? null,
      change_percent: quote?.change_percent ?? null,
      period_return: metrics?.periodReturn ?? null,
      max_drawdown: metrics?.maxDrawdown ?? null,
      volatility20d: metrics?.volatility20d ?? null,
      avg_volume_20d: metrics?.avgVolume20d ?? null,
      avg_amount_20d: avgAmount20d,
      amount: quote?.amount ?? null,
      as_of: asset.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? null,
      source: asset.source ?? quote?.source ?? null,
      sample_size: bars.length,
      period_start: firstDateFromBars(bars),
      period_end: lastDateFromBars(bars),
      return_20d_pct: technicalSummary.return_20d_pct ?? metrics?.return20d ?? null,
      return_60d_pct: technicalSummary.return_60d_pct ?? metrics?.return60d ?? null,
      return_120d_pct: technicalSummary.return_120d_pct ?? metrics?.return120d ?? metrics?.periodReturn ?? null,
      financial_quality_score: financialQuality?.quality_score ?? null,
      financial_quality_label: financialQuality?.quality_label ?? null,
      liquidity_note: avgAmount20d !== null
        ? `20 日均成交额 ${round(avgAmount20d / 100_000_000, 2)} 亿元`
        : amount !== null
          ? `最新成交额 ${round(amount / 100_000_000, 2)} 亿元`
          : '成交额缺失，使用成交量代理。',
    };
  });

  const numericRows = rows.map((row) => ({
    ...row,
    periodReturnNumber: numeric(row.period_return),
    return120dNumber: numeric(row.return_120d_pct ?? row.period_return),
    drawdownNumber: numeric(row.max_drawdown),
    volatilityNumber: numeric(row.volatility20d),
    liquidityNumber: numeric(row.avg_amount_20d ?? row.amount),
    qualityNumber: numeric(row.financial_quality_score),
  }));
  const bestReturn = numericRows
    .filter((row) => row.return120dNumber !== null)
    .sort((a, b) => (b.return120dNumber ?? 0) - (a.return120dNumber ?? 0))[0];
  const lowestDrawdown = numericRows
    .filter((row) => row.drawdownNumber !== null)
    .sort((a, b) => Math.abs(a.drawdownNumber ?? 0) - Math.abs(b.drawdownNumber ?? 0))[0];
  const lowestVolatility = numericRows
    .filter((row) => row.volatilityNumber !== null)
    .sort((a, b) => (a.volatilityNumber ?? 0) - (b.volatilityNumber ?? 0))[0];
  const rankedReturns = rankRows(numericRows, 'return120dNumber', 'desc');
  const rankedDrawdown = rankRows(numericRows.map((row) => ({ ...row, drawdownAbs: Math.abs(row.drawdownNumber ?? Number.POSITIVE_INFINITY) })), 'drawdownAbs', 'asc');
  const rankedVolatility = rankRows(numericRows, 'volatilityNumber', 'asc');
  const rankedLiquidity = rankRows(numericRows, 'liquidityNumber', 'desc');
  const rankedQuality = rankRows(numericRows, 'qualityNumber', 'desc');
  const enrichedRows = numericRows.map((row) => {
    const returnRank = rankedReturns.get(row.symbol);
    const drawdownRank = rankedDrawdown.get(row.symbol);
    const volatilityRank = rankedVolatility.get(row.symbol);
    const liquidityRank = rankedLiquidity.get(row.symbol);
    const qualityRank = rankedQuality.get(row.symbol);
    const validRanks = [returnRank, drawdownRank, volatilityRank, liquidityRank, qualityRank]
      .filter((rank): rank is number => typeof rank === 'number');
    const compositeScore = validRanks.length
      ? round(validRanks.reduce((score, rank) => score + (assets.length - rank + 1), 0) / (validRanks.length * assets.length) * 100, 0)
      : null;
    return {
      ...row,
      rank_return: returnRank ?? null,
      rank_drawdown: drawdownRank ?? null,
      rank_volatility: volatilityRank ?? null,
      rank_liquidity: liquidityRank ?? null,
      rank_quality: qualityRank ?? null,
      composite_score: compositeScore,
      relative_strength: row.return120dNumber === null
        ? '待确认'
        : row === bestReturn
          ? '收益领先'
          : row.return120dNumber > 0
            ? '阶段为正'
            : '阶段偏弱',
      selection_view: compositeScore === null
        ? '数据待补齐'
        : compositeScore >= 72
          ? '优先研究'
          : compositeScore >= 55
            ? '观察候选'
            : '谨慎观察',
      ranking_reason: [
        returnRank ? `收益排名 ${returnRank}` : null,
        drawdownRank ? `回撤排名 ${drawdownRank}` : null,
        qualityRank ? `质量排名 ${qualityRank}` : null,
      ].filter(Boolean).join('，') || '关键指标仍需补齐。',
      exclusion_reason: compositeScore !== null && compositeScore < 55
        ? '综合排名靠后，需等待趋势、质量或流动性改善。'
        : null,
    };
  });

  return {
    rows: enrichedRows,
    leaders: {
      best_return: bestReturn
        ? { symbol: bestReturn.symbol, name: bestReturn.name, value: bestReturn.return_120d_pct ?? bestReturn.period_return }
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

function rankRows(
  rows: Array<JsonRecord & { symbol: string }>,
  field: string,
  direction: 'asc' | 'desc'
): Map<string, number> {
  const ranked = rows
    .map((row) => ({ symbol: row.symbol, value: numeric(row[field]) }))
    .filter((row): row is { symbol: string; value: number } => Boolean(row.symbol) && row.value !== null)
    .sort((left, right) => direction === 'asc' ? left.value - right.value : right.value - left.value);
  return new Map(ranked.map((row, index) => [row.symbol, index + 1]));
}

function buildFinancialQualitySummary(assets: JsonRecord[]): JsonRecord {
  const rows = assets.map((asset) => asRecord(asset.financialQuality) ?? buildFinancialQuality(asset));
  const ranked = rankRows(
    rows.map((row) => ({ ...row, symbol: String(row.symbol ?? '') })),
    'quality_score',
    'desc'
  );
  return {
    method: 'latest_report_profitability_growth_score',
    latest_report_date: rows.find((row) => row.latest_report_date)?.latest_report_date ?? null,
    rows: rows.map((row) => ({
      ...row,
      rank_quality: ranked.get(String(row.symbol ?? '')) ?? null,
    })),
    limitations: [
      '财务质量评分用于横向研究，不构成估值目标价或买卖建议。',
      '当前仅使用接口可得的最近报告期、盈利率和同比指标，未纳入现金流、负债结构和行业景气度。',
    ],
  };
}

function buildSelectionRanking(comparison: JsonRecord, assets: JsonRecord[]): JsonRecord {
  const rows = Array.isArray(comparison.rows)
    ? comparison.rows.map(asRecord).filter((row): row is JsonRecord => Boolean(row))
    : [];
  const ranked = rows
    .slice()
    .sort((left, right) => (numeric(right.composite_score) ?? -1) - (numeric(left.composite_score) ?? -1));
  return {
    method: 'multi_factor_research_priority',
    description: '综合收益、回撤、波动、流动性代理和财务质量后的研究优先级；不是交易指令。',
    rows: ranked.map((row, index) => ({
      rank: index + 1,
      symbol: row.symbol,
      name: row.name,
      score: row.composite_score,
      view: row.selection_view,
      reason: row.ranking_reason,
      exclusion_reason: row.exclusion_reason,
    })),
    coverage: {
      requested: assets.length,
      ranked: ranked.length,
    },
  };
}

function buildConclusion(params: {
  comparison: JsonRecord;
  selectionRanking: JsonRecord;
  financialQuality: JsonRecord;
}): JsonRecord {
  const leaders = asRecord(params.comparison.leaders);
  const top = asRecord(Array.isArray(params.selectionRanking.rows) ? params.selectionRanking.rows[0] : null);
  const qualityRows = Array.isArray(params.financialQuality.rows)
    ? params.financialQuality.rows.map(asRecord).filter((row): row is JsonRecord => Boolean(row))
    : [];
  const qualityLeader = qualityRows
    .slice()
    .sort((left, right) => (numeric(right.quality_score) ?? -1) - (numeric(left.quality_score) ?? -1))[0];
  return {
    summary: [
      top ? `综合研究优先级第一：${String(top.name ?? top.symbol)}，原因：${String(top.reason ?? '多因子得分领先')}` : '综合研究优先级仍待补齐。',
      asRecord(leaders?.best_return)
        ? `阶段收益领先：${String(asRecord(leaders?.best_return)?.name ?? asRecord(leaders?.best_return)?.symbol)}。`
        : '阶段收益领先标的待确认。',
      asRecord(leaders?.lowest_drawdown)
        ? `回撤控制相对较好：${String(asRecord(leaders?.lowest_drawdown)?.name ?? asRecord(leaders?.lowest_drawdown)?.symbol)}。`
        : '回撤控制指标待确认。',
      qualityLeader ? `财务质量相对占优：${String(qualityLeader.name ?? qualityLeader.symbol)}。` : '财务质量数据仍需补齐。',
      '排序仅用于横向研究，不构成交易指令；仍需结合仓位、风险偏好、交易成本和后续基本面变化。',
    ],
    primary_view: top
      ? `${String(top.name ?? top.symbol)} 当前综合研究优先级最高；其余候选应结合趋势、质量和风险约束分层观察。`
      : '候选排序待确认。',
    risk_disclaimer: '公开行情和财务接口可能存在延迟或字段缺失，本结果不构成投资建议、收益承诺或即时交易指令。',
  };
}

function buildHoldingRows(assets: JsonRecord[]): JsonRecord[] {
  const equalWeight = assets.length > 0 ? 1 / assets.length : 0;
  return assets.map((asset) => {
    const quote = asRecord(asset.quote);
    const symbol = String(asset.symbol ?? quote?.symbol ?? '');
    const price = numeric(quote?.price);
    const marketValue = price === null ? null : round(price * equalWeight * 10_000);
    return {
      symbol,
      name: String(asset.name ?? quote?.name ?? symbol),
      shares: null,
      cost_price: null,
      current_price: price,
      market_value: marketValue,
      weight: round(equalWeight * 100, 2),
      pnl: null,
      pnl_pct: null,
      source: 'market_prefetch',
      data_gaps: ['shares', 'cost_price', 'actual_market_value'],
    };
  });
}

function buildPortfolioSummary(assets: JsonRecord[]): JsonRecord {
  const holdings = buildHoldingRows(assets);
  const weights = holdings.map((holding) => numeric(holding.weight)).filter((value): value is number => value !== null);
  const maxWeight = weights.length ? Math.max(...weights) : null;
  return {
    generated_from: 'symbols_without_broker_position_detail',
    total_asset: null,
    market_value: null,
    cash: null,
    position_pct: null,
    floating_pnl: null,
    floating_pnl_pct: null,
    concentration: {
      max_weight_pct: maxWeight,
      top3_weight_pct: round(weights.sort((a, b) => b - a).slice(0, 3).reduce((sum, value) => sum + value, 0)),
      method: 'equal_weight_proxy_until_user_position_fields_are_confirmed',
    },
    data_gaps: ['total_asset', 'cash', 'shares', 'cost_price', 'actual_weight'],
    warnings: [
      '平台只能从用户问题和行情接口预取标的，真实持仓数量、成本、现金和权重需要用户补充或由截图识别后确认。',
    ],
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

  if (
    params.plan.dataRequirements.some((endpoint) => endpoint.includes('/indicators/technical/')) ||
    params.plan.capabilityId === 'asset_comparison' ||
    params.plan.requestedCapabilityId === 'asset_comparison'
  ) {
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
  const imageExtractionEvidence = await buildImageExtractionEvidence(params.projectPath, runId, warnings);
  const imageExtraction = asRecord(imageExtractionEvidence?.imageExtraction);

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
      ensureTechnicalSummary(asset);
      buildFinancialQuality(asset);
      assets.push(asset);
    } catch (error) {
      warnings.push(`${symbol} 预取失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (assets.length === 0) {
    throw new Error(`所有标的预取失败：${warnings.join('；')}`);
  }

  const primaryAsset = assets[0];
  const visualizationTemplate = serializeQuantVisualizationTemplate(
    params.plan.requestedCapabilityId ?? params.plan.capabilityId,
    {
      instruction: params.plan.question,
      symbolCount: assets.length || symbols.length,
      requestedVariantId: params.plan.visualization?.variantId,
      dataSignals: params.plan.visualization?.dataSignals,
    }
  );
  const visualization = {
    template_id: visualizationTemplate.templateId,
    name: visualizationTemplate.name,
    scenario: visualizationTemplate.scenario,
    variant_id: visualizationTemplate.variantId,
    variant_name: visualizationTemplate.variantName,
    variant_scenario: visualizationTemplate.variantScenario,
    layout: visualizationTemplate.layout,
    density: visualizationTemplate.density,
    first_viewport: visualizationTemplate.firstViewport,
    variant_guidance: visualizationTemplate.variantGuidance,
    match_reasons: visualizationTemplate.matchReasons,
    alternatives: visualizationTemplate.alternatives,
    pain_points: visualizationTemplate.painPoints,
    required_components: visualizationTemplate.requiredComponents,
    optional_components: visualizationTemplate.optionalComponents,
    data_signals: visualizationTemplate.dataSignals,
    final_data_contract: visualizationTemplate.finalDataContract,
    rendered_components: visualizationTemplate.requiredComponents,
    missing_components: [],
  };
  const comparison = buildComparisonSummary(assets);
  const financialQuality = buildFinancialQualitySummary(assets);
  const selectionRanking = buildSelectionRanking(comparison, assets);
  const conclusion = buildConclusion({ comparison, selectionRanking, financialQuality });
  const finalData = symbols.length === 1
    ? {
        ...primaryAsset,
        ...(params.plan.requestedCapabilityId === 'portfolio_risk' || params.plan.capabilityId === 'portfolio_risk'
          ? {
              portfolio: buildPortfolioSummary(assets),
              holdings: buildHoldingRows(assets),
              assets,
              comparison: buildComparisonSummary(assets),
            }
          : {}),
        ...(imageExtraction ? { imageExtraction } : {}),
        visualization,
        liquidity: buildLiquiditySummary([primaryAsset]),
        financialQuality,
        selectionRanking,
        conclusion,
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
        ...(params.plan.requestedCapabilityId === 'portfolio_risk' || params.plan.capabilityId === 'portfolio_risk'
          ? {
              portfolio: buildPortfolioSummary(assets),
              holdings: buildHoldingRows(assets),
            }
          : {}),
        ...(imageExtraction ? { imageExtraction } : {}),
        comparison,
        correlation: buildCorrelationSummary(assets),
        liquidity: buildLiquiditySummary(assets),
        financialQuality,
        selectionRanking,
        visualization,
        conclusion,
        warnings,
      };
  const finalPath = path.join(params.projectPath, 'data_file', 'final', 'dashboard-data.json');
  await writeJson(finalPath, finalData);

  await ensureBaselineEvidenceFiles(params.projectPath, { force: true });
  if (imageExtractionEvidence) {
    await augmentEvidenceWithImageExtraction(params.projectPath, imageExtractionEvidence);
  }

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
