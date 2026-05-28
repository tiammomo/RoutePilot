import { getAllProjects } from '@/lib/services/project';
import { getQuantCapability, type QuantCapabilityId } from '@/lib/quant/capabilities';
import { serializeProjects } from '@/lib/serializers/project';
import { Prisma } from '@prisma/client';
import { prisma } from '@/lib/db/client';
import type { Project } from '@/types';
import fs from 'fs/promises';
import path from 'path';

type StrategyStatus = 'ready' | 'planned' | 'research';
type StrategyRiskLevel = 'low' | 'medium' | 'high';

export interface StrategyParameter {
  key: string;
  label: string;
  value: string | number;
  unit?: string;
  description: string;
}

export interface StrategyParameterScan {
  id: string;
  name: string;
  status: 'available' | 'planned' | 'blocked';
  objective: string;
  grid: Array<{
    key: string;
    values: Array<string | number>;
    unit?: string;
  }>;
  metrics: string[];
  guardrails: string[];
  sampleSize: number;
}

export interface StrategyVersionRecord {
  version: string;
  status: 'active' | 'draft' | 'archived';
  updatedAt: string;
  changes: string[];
  parameterSnapshot: Record<string, string | number>;
}

export interface StrategyBacktestArchive {
  id: string;
  title: string;
  status: 'available' | 'pending' | 'missing';
  symbol: string;
  period: string;
  metrics: {
    totalReturnPct?: number;
    maxDrawdownPct?: number;
    winRatePct?: number;
    tradeCount?: number;
  };
  source: string;
  linkedWorkspaceId?: string;
  limitations: string[];
}

export interface StrategyScanRunResult {
  id: string;
  parameters: Record<string, string | number>;
  status: 'success' | 'failed' | 'skipped';
  metrics: {
    totalReturnPct?: number | null;
    maxDrawdownPct?: number | null;
    winRatePct?: number | null;
    tradeCount?: number | null;
    sharpe?: number | null;
  };
  error?: string;
}

export interface StrategyScanRun {
  id: string;
  templateId: string;
  scanId: string;
  symbol: string;
  status: 'completed' | 'failed' | 'partial';
  startedAt: string;
  completedAt: string;
  total: number;
  succeeded: number;
  failed: number;
  bestResultId?: string | null;
  objective: string;
  source: string;
  results: StrategyScanRunResult[];
}

export interface StrategyScanJob {
  id: string;
  templateId: string;
  scanId: string;
  symbol: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  completedAt?: string;
  runId?: string | null;
  error?: string | null;
}

export interface StrategyUniverseMember {
  symbol: string;
  code: string;
  name?: string | null;
  exchange: string;
  assetType: string;
  currency: string;
  timezone: string;
  secid?: string | null;
  provider: string;
  securityStatus: string;
  role: string;
  weight?: number | null;
  rowCount: number;
  firstTs?: string | null;
  lastTs?: string | null;
  dataProvider?: string | null;
  dataStatus: 'ready' | 'missing' | 'stale';
}

export interface StrategyUniverse {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  source: string;
  tags: string[];
  defaultTimeframe: string;
  defaultAdjustment: string;
  provider: string;
  members: StrategyUniverseMember[];
}

export interface StrategyDataCoverageItem {
  symbol: string;
  name?: string | null;
  timeframe: string;
  adjustment: string;
  provider: string;
  firstTs?: string | null;
  lastTs?: string | null;
  rowCount: number;
  dataStatus: 'ready' | 'missing' | 'stale';
}

export interface StrategyLocalKlineBar {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number | null;
  amplitude?: number | null;
  changePercent?: number | null;
  changeAmount?: number | null;
  turnover?: number | null;
  provider: string;
  metadata?: Record<string, unknown>;
}

export interface StrategyDividendEvent {
  symbol: string;
  name?: string | null;
  reportDate?: string | null;
  planNoticeDate?: string | null;
  equityRecordDate?: string | null;
  exDividendDate?: string | null;
  noticeDate?: string | null;
  assignProgress?: string | null;
  planProfile?: string | null;
  pretaxBonusRmb?: number | null;
  bonusRatio?: number | null;
  transferRatio?: number | null;
  dividendYield?: number | null;
}

export interface StrategyDividendEventsResponse {
  symbol: string;
  events: StrategyDividendEvent[];
  source: string;
  fetchedAt: string;
}

export interface StrategyLocalKlineSummary {
  rowCount: number;
  firstTs?: string | null;
  lastTs?: string | null;
  latestClose?: number | null;
  previousClose?: number | null;
  returnPct?: number | null;
  high?: number | null;
  low?: number | null;
  totalVolume?: number | null;
  totalAmount?: number | null;
}

export interface StrategyLocalKlineResponse {
  symbol: string;
  code?: string | null;
  name?: string | null;
  exchange: string;
  assetType: string;
  currency: string;
  timezone: string;
  secid?: string | null;
  provider?: string | null;
  dataProvider?: string | null;
  timeframe: string;
  adjustment: string;
  bars: StrategyLocalKlineBar[];
  summary: StrategyLocalKlineSummary;
  fetchedAt: string;
}

export interface StrategyIngestionPlan {
  provider: string;
  universeId: string;
  timeframe: string;
  adjustment: string;
  suggestedLimit: number;
  lookbackYears: number;
  endpoints: string[];
  guardrails: string[];
}

export interface StrategyResearchState {
  primaryUniverseId: string;
  universes: StrategyUniverse[];
  coverage: StrategyDataCoverageItem[];
  ingestionPlan: StrategyIngestionPlan;
  source: 'market-api' | 'fallback';
  error?: string | null;
}

export interface StrategyHistoryIngestionResult {
  job_id: string;
  status: 'completed' | 'partial' | 'failed';
  total_symbols: number;
  completed_symbols: number;
  failed_symbols: number;
  rows_received: number;
  rows_upserted: number;
  symbols: Array<{
    symbol: string;
    name?: string | null;
    secid?: string | null;
    status: 'success' | 'failed' | 'skipped';
    bars_received: number;
    rows_upserted: number;
    first_date?: string | null;
    last_date?: string | null;
    error?: string | null;
  }>;
}

export interface StrategyUniverseMemberAddResult {
  universe_id: string;
  member: StrategyUniverseMember;
  candidates: Array<{
    symbol: string;
    name?: string | null;
    market: string;
    asset_type: string;
    secid: string;
    source: string;
  }>;
  ingestion?: StrategyHistoryIngestionResult | null;
}

export interface StrategyTemplate {
  id: string;
  name: string;
  family: string;
  status: StrategyStatus;
  capabilityId: QuantCapabilityId;
  description: string;
  defaultSymbols: string[];
  timeframe: string;
  dataDependencies: string[];
  parameterSchema: StrategyParameter[];
  parameterScans: StrategyParameterScan[];
  versions: StrategyVersionRecord[];
  backtestArchives: StrategyBacktestArchive[];
  riskControls: string[];
  evaluationMetrics: string[];
  limitations: string[];
  promptSeed: string;
}

export interface StrategyWorkspaceRef {
  id: string;
  name: string;
  status?: string | null;
  createdAt: string;
  updatedAt?: string | null;
  capabilityId?: QuantCapabilityId | null;
  initialPrompt?: string | null;
}

export interface StrategyCatalogItem extends StrategyTemplate {
  readiness: {
    label: string;
    score: number;
    riskLevel: StrategyRiskLevel;
    summary: string;
  };
  linkedWorkspaces: StrategyWorkspaceRef[];
  latestScanRun: StrategyScanRun | null;
}

export interface StrategyDashboardData {
  generatedAt: string;
  summary: {
    templates: number;
    readyTemplates: number;
    plannedTemplates: number;
    strategyWorkspaces: number;
    backtestWorkspaces: number;
    dataDependencies: number;
    parameterScans: number;
    archivedReports: number;
    activeVersions: number;
    researchUniverses: number;
    trackedSymbols: number;
    syncedSymbols: number;
    syncedBars: number;
  };
  templates: StrategyCatalogItem[];
  workspaces: StrategyWorkspaceRef[];
  scanRuns: StrategyScanRun[];
  scanJobs: StrategyScanJob[];
  research: StrategyResearchState;
}

const ROOT = process.cwd();
const DATA_DIR = process.env.STRATEGY_SCANS_DIR || path.join(ROOT, 'data', 'strategy-scans');
const RUNS_DIR = path.join(DATA_DIR, 'runs');
const JOBS_DIR = path.join(DATA_DIR, 'jobs');
const MARKET_API_BASE_URL =
  process.env.QUANTPILOT_MARKET_API_URL ||
  process.env.QUANTPILOT_MARKET_API_BASE_URL ||
  'http://127.0.0.1:8000';
const SAMPLE_UNIVERSE_ID = 'a-share-sample-research-pool';

const SAMPLE_UNIVERSE_MEMBERS: StrategyUniverseMember[] = [
  {
    symbol: '002156.SZ',
    code: '002156',
    name: '通富微电',
    exchange: 'SZ',
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    secid: '0.002156',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: 0.2,
    rowCount: 0,
    dataStatus: 'missing',
  },
  {
    symbol: '002555.SZ',
    code: '002555',
    name: '三七互娱',
    exchange: 'SZ',
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    secid: '0.002555',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: 0.2,
    rowCount: 0,
    dataStatus: 'missing',
  },
  {
    symbol: '002624.SZ',
    code: '002624',
    name: '完美世界',
    exchange: 'SZ',
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    secid: '0.002624',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: 0.2,
    rowCount: 0,
    dataStatus: 'missing',
  },
  {
    symbol: '601398.SH',
    code: '601398',
    name: '工商银行',
    exchange: 'SH',
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    secid: '1.601398',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: 0.2,
    rowCount: 0,
    dataStatus: 'missing',
  },
  {
    symbol: '600916.SH',
    code: '600916',
    name: '中国黄金',
    exchange: 'SH',
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    secid: '1.600916',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: 0.2,
    rowCount: 0,
    dataStatus: 'missing',
  },
];

const FALLBACK_RESEARCH_STATE: StrategyResearchState = {
  primaryUniverseId: SAMPLE_UNIVERSE_ID,
  source: 'fallback',
  universes: [
    {
      id: SAMPLE_UNIVERSE_ID,
      name: 'A 股示例研究池',
      description: '用于策略平台打通本地行情覆盖、数据质量检查和回测链路的默认股票池。',
      status: 'active',
      source: 'seed',
      tags: ['A股', '东方财富', '策略回测'],
      defaultTimeframe: 'daily',
      defaultAdjustment: 'qfq',
      provider: 'eastmoney',
      members: SAMPLE_UNIVERSE_MEMBERS,
    },
  ],
  coverage: SAMPLE_UNIVERSE_MEMBERS.map(member => ({
    symbol: member.symbol,
    name: member.name,
    timeframe: 'daily',
    adjustment: 'qfq',
    provider: 'eastmoney',
    rowCount: 0,
    dataStatus: 'missing',
  })),
  ingestionPlan: {
    provider: 'eastmoney',
    universeId: SAMPLE_UNIVERSE_ID,
    timeframe: 'daily',
    adjustment: 'qfq',
    suggestedLimit: 1260,
    lookbackYears: 5,
    endpoints: [
      'GET /api/v1/research/universes',
      'GET /api/v1/research/data-coverage',
      'POST /api/v1/ingestion/eastmoney/history',
    ],
    guardrails: [
      '默认保留近 5 年前复权日线，保证策略回测读取同一价格口径。',
      '每次同步按 symbol/timeframe/adjustment/ts 幂等 upsert。',
      '同步完成后自动裁剪本股票池旧样本，避免本地行情越积越长。',
      '回测必须读取本地 TimescaleDB，避免外部行情变化影响复现。',
    ],
  },
};

const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: 'ma-crossover-single-asset',
    name: '均线突破策略',
    family: '趋势跟随',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '以 20/60 日均线交叉为核心信号，验证单标的趋势跟随效果。',
    defaultSymbols: ['510300', '000300'],
    timeframe: '日线 · 近 250 个交易日',
    dataDependencies: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
      'GET /api/v1/backtests/ma-crossover/{symbol}',
    ],
    parameterSchema: [
      { key: 'fast_window', label: '快线窗口', value: 20, unit: '日', description: '用于触发入场和离场的短期均线。' },
      { key: 'slow_window', label: '慢线窗口', value: 60, unit: '日', description: '用于判断中期趋势方向。' },
      { key: 'fee_bps', label: '单边费用', value: 5, unit: 'bps', description: '回测中默认扣减的交易费用。' },
    ],
    parameterScans: [
      {
        id: 'ma-window-grid',
        name: '均线窗口扫描',
        status: 'available',
        objective: '验证快慢均线窗口对收益、回撤和交易次数的敏感性。',
        grid: [
          { key: 'fast_window', values: [10, 20, 30], unit: '日' },
          { key: 'slow_window', values: [50, 60, 90], unit: '日' },
          { key: 'fee_bps', values: [3, 5, 10], unit: 'bps' },
        ],
        metrics: ['总收益', '最大回撤', '交易次数', '胜率'],
        guardrails: ['fast_window 必须小于 slow_window', '最大回撤必须展示', '费用变化必须纳入对比'],
        sampleSize: 27,
      },
    ],
    versions: [
      {
        version: 'v1.0',
        status: 'active',
        updatedAt: '2026-05-27T00:00:00.000Z',
        changes: ['接入本地均线突破回测端点', '固化 20/60 日均线和 5bps 费用口径'],
        parameterSnapshot: { fast_window: 20, slow_window: 60, fee_bps: 5 },
      },
      {
        version: 'v0.9',
        status: 'archived',
        updatedAt: '2026-05-14T00:00:00.000Z',
        changes: ['仅保留策略研究说明，尚未绑定回测端点'],
        parameterSnapshot: { fast_window: 20, slow_window: 60 },
      },
    ],
    backtestArchives: [
      {
        id: 'ma-crossover-510300-baseline',
        title: '510300 基准回测口径',
        status: 'available',
        symbol: '510300',
        period: '近 250 个交易日',
        metrics: {
          totalReturnPct: 0,
          maxDrawdownPct: 0,
          winRatePct: 0,
          tradeCount: 0,
        },
        source: 'GET /api/v1/backtests/ma-crossover/{symbol}',
        limitations: ['具体收益指标以生成工作空间内最新回测结果为准。', '归档口径用于记录参数和报告入口，不替代实时回测。'],
      },
    ],
    riskControls: ['单标的全仓/空仓', '不加杠杆', '必须展示最大回撤', '必须说明滑点和停牌未建模'],
    evaluationMetrics: ['总收益', '最大回撤', '胜率', '交易次数', '样本区间'],
    limitations: ['当前只覆盖单标的日线级回测。', '暂未建模滑点、停牌、分红再投资和冲击成本。'],
    promptSeed: '用最近两年的 20/60 日均线突破规则回测 510300，展示净值、回撤、胜率、交易明细和限制说明。',
  },
  {
    id: 'trend-volume-confirmation',
    name: '趋势放量确认策略',
    family: '趋势跟随',
    status: 'research',
    capabilityId: 'strategy_research',
    description: '在均线趋势基础上加入成交量过滤，用于研究突破信号的质量。',
    defaultSymbols: ['宁德时代', '创业板指'],
    timeframe: '日线 · 近 120 至 250 个交易日',
    dataDependencies: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
    ],
    parameterSchema: [
      { key: 'trend_window', label: '趋势窗口', value: 20, unit: '日', description: '判断趋势突破的均线周期。' },
      { key: 'volume_ratio', label: '放量倍数', value: 1.3, description: '相对过去成交量均值的过滤阈值。' },
      { key: 'stop_loss', label: '失效阈值', value: 8, unit: '%', description: '研究阶段建议纳入的最大单笔容忍亏损。' },
    ],
    parameterScans: [
      {
        id: 'trend-volume-grid',
        name: '趋势与放量阈值扫描',
        status: 'planned',
        objective: '比较趋势窗口和放量倍数对信号密度、突破后收益和回撤的影响。',
        grid: [
          { key: 'trend_window', values: [10, 20, 30], unit: '日' },
          { key: 'volume_ratio', values: [1.2, 1.3, 1.5] },
          { key: 'stop_loss', values: [6, 8, 10], unit: '%' },
        ],
        metrics: ['信号密度', '突破后区间收益', '最大回撤'],
        guardrails: ['未正式回测前不得展示收益承诺', '必须列出信号不足样本'],
        sampleSize: 27,
      },
    ],
    versions: [
      {
        version: 'v0.2',
        status: 'draft',
        updatedAt: '2026-05-27T00:00:00.000Z',
        changes: ['加入成交量过滤参数', '补充失效阈值和待验证指标'],
        parameterSnapshot: { trend_window: 20, volume_ratio: 1.3, stop_loss: 8 },
      },
    ],
    backtestArchives: [
      {
        id: 'trend-volume-research-plan',
        title: '趋势放量研究计划',
        status: 'pending',
        symbol: '创业板指',
        period: '近 120 至 250 个交易日',
        metrics: {},
        source: '待接入参数扫描执行器',
        limitations: ['当前为研究计划归档，尚无正式回测结果。'],
      },
    ],
    riskControls: ['先定义信号再讨论收益', '未回测前只展示研究假设', '必须列出失效条件'],
    evaluationMetrics: ['突破后区间收益', '回撤', '信号密度', '成交量确认比例'],
    limitations: ['当前尚未接入参数扫描。', '需要后续补充交易执行和风控模拟。'],
    promptSeed: '研究一个基于 20 日均线突破和成交量放大确认的趋势策略，先输出信号规则、样本口径、待验证清单和风险假设。',
  },
  {
    id: 'portfolio-risk-rebalance',
    name: '组合风险再平衡策略',
    family: '组合风控',
    status: 'planned',
    capabilityId: 'portfolio_risk',
    description: '围绕持仓集中度、波动、回撤和流动性生成调仓约束与再平衡计划。',
    defaultSymbols: ['贵州茅台', '招商银行', '510300'],
    timeframe: '日线 · 近 120 个交易日',
    dataDependencies: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
    ],
    parameterSchema: [
      { key: 'max_weight', label: '单标的权重上限', value: 35, unit: '%', description: '避免组合过度集中。' },
      { key: 'rebalance_band', label: '再平衡偏离带', value: 5, unit: '%', description: '偏离目标权重后的触发阈值。' },
      { key: 'cash_buffer', label: '现金缓冲', value: 10, unit: '%', description: '保留流动性和回撤缓冲。' },
    ],
    parameterScans: [
      {
        id: 'rebalance-risk-grid',
        name: '再平衡风险阈值扫描',
        status: 'blocked',
        objective: '比较仓位上限、再平衡偏离带和现金缓冲对组合回撤和换手的影响。',
        grid: [
          { key: 'max_weight', values: [25, 35, 45], unit: '%' },
          { key: 'rebalance_band', values: [3, 5, 8], unit: '%' },
          { key: 'cash_buffer', values: [5, 10, 15], unit: '%' },
        ],
        metrics: ['集中度', '组合回撤', '换手率', '现金占用'],
        guardrails: ['需要组合收益序列和相关性计算能力', '不得输出即时调仓指令'],
        sampleSize: 27,
      },
    ],
    versions: [
      {
        version: 'v0.1',
        status: 'draft',
        updatedAt: '2026-05-27T00:00:00.000Z',
        changes: ['定义组合再平衡参数口径', '等待组合相关性和 VaR 能力接入'],
        parameterSnapshot: { max_weight: 35, rebalance_band: 5, cash_buffer: 10 },
      },
    ],
    backtestArchives: [
      {
        id: 'portfolio-risk-placeholder',
        title: '组合风险归档占位',
        status: 'missing',
        symbol: '组合',
        period: '近 120 个交易日',
        metrics: {},
        source: '待接入组合回测执行器',
        limitations: ['组合收益、换手和相关性计算尚未正式归档。'],
      },
    ],
    riskControls: ['不得直接给出交易指令', '必须标注用户输入和行情接口字段', '必须说明缺失成本和税费假设'],
    evaluationMetrics: ['集中度', '区间波动', '最大回撤', '流动性约束', '调仓优先级'],
    limitations: ['组合相关性和 VaR 仍在增强中。', '当前以风险约束和调仓计划为主。'],
    promptSeed: '分析一个贵州茅台、招商银行、510300 的组合风险，输出集中度、回撤、流动性和再平衡约束。',
  },
];

function readinessFor(template: StrategyTemplate): StrategyCatalogItem['readiness'] {
  if (template.status === 'ready') {
    return {
      label: '可回测',
      score: 92,
      riskLevel: 'medium',
      summary: '已接入本地回测端点，可生成可复现参数、净值、回撤和交易明细。',
    };
  }
  if (template.status === 'research') {
    return {
      label: '研究中',
      score: 68,
      riskLevel: 'medium',
      summary: '可生成策略研究工作空间，但收益验证前必须展示假设和待验证项。',
    };
  }
  return {
    label: '规划中',
    score: 45,
    riskLevel: 'high',
    summary: '适合沉淀策略口径和风控约束，完整自动化执行仍需补齐。',
  };
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8')) as T;
  } catch {
    return null;
  }
}

async function writeJsonFile(filePath: string, value: unknown) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

function toDate(value: string | Date | undefined | null): Date | null {
  if (!value) return null;
  if (value instanceof Date) return value;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function isScanRunStatus(value: string): StrategyScanRun['status'] {
  return value === 'completed' || value === 'failed' || value === 'partial' ? value : 'failed';
}

function isScanJobStatus(value: string): StrategyScanJob['status'] {
  return value === 'queued' || value === 'running' || value === 'completed' || value === 'failed'
    ? value
    : 'failed';
}

function scanRunResults(value: unknown): StrategyScanRunResult[] {
  return Array.isArray(value) ? value as StrategyScanRunResult[] : [];
}

function mapDbScanRun(record: {
  id: string;
  templateId: string;
  scanId: string;
  symbol: string;
  status: string;
  startedAt: Date;
  completedAt: Date;
  total: number;
  succeeded: number;
  failed: number;
  bestResultId: string | null;
  objective: string;
  source: string;
  results: unknown;
}): StrategyScanRun {
  return {
    id: record.id,
    templateId: record.templateId,
    scanId: record.scanId,
    symbol: record.symbol,
    status: isScanRunStatus(record.status),
    startedAt: record.startedAt.toISOString(),
    completedAt: record.completedAt.toISOString(),
    total: record.total,
    succeeded: record.succeeded,
    failed: record.failed,
    bestResultId: record.bestResultId,
    objective: record.objective,
    source: record.source,
    results: scanRunResults(record.results),
  };
}

function mapDbScanJob(record: {
  id: string;
  templateId: string;
  scanId: string;
  symbol: string;
  status: string;
  startedAt: Date | null;
  completedAt: Date | null;
  runId: string | null;
  error: string | null;
  createdAt: Date;
  updatedAt: Date;
}): StrategyScanJob {
  return {
    id: record.id,
    templateId: record.templateId,
    scanId: record.scanId,
    symbol: record.symbol,
    status: isScanJobStatus(record.status),
    createdAt: record.createdAt.toISOString(),
    updatedAt: record.updatedAt.toISOString(),
    startedAt: record.startedAt ? record.startedAt.toISOString() : undefined,
    completedAt: record.completedAt ? record.completedAt.toISOString() : undefined,
    runId: record.runId,
    error: record.error,
  };
}

async function listScanRunsFromDatabase(): Promise<StrategyScanRun[]> {
  const records = await prisma.strategyScanRun.findMany({
    orderBy: { completedAt: 'desc' },
  });
  return records.map(mapDbScanRun);
}

async function listScanJobsFromDatabase(): Promise<StrategyScanJob[]> {
  const records = await prisma.strategyScanJob.findMany({
    orderBy: { createdAt: 'desc' },
  });
  return records.map(mapDbScanJob);
}

async function writeScanRunToDatabase(run: StrategyScanRun) {
  const startedAt = toDate(run.startedAt) ?? new Date();
  const completedAt = toDate(run.completedAt) ?? new Date();
  const results = run.results as unknown as Prisma.InputJsonValue;
  await prisma.strategyScanRun.upsert({
    where: { id: run.id },
    update: {
      templateId: run.templateId,
      scanId: run.scanId,
      symbol: run.symbol,
      status: run.status,
      startedAt,
      completedAt,
      total: run.total,
      succeeded: run.succeeded,
      failed: run.failed,
      bestResultId: run.bestResultId ?? null,
      objective: run.objective,
      source: run.source,
      results,
    },
    create: {
      id: run.id,
      templateId: run.templateId,
      scanId: run.scanId,
      symbol: run.symbol,
      status: run.status,
      startedAt,
      completedAt,
      total: run.total,
      succeeded: run.succeeded,
      failed: run.failed,
      bestResultId: run.bestResultId ?? null,
      objective: run.objective,
      source: run.source,
      results,
    },
  });
}

async function writeScanJobToDatabase(job: StrategyScanJob) {
  await prisma.strategyScanJob.upsert({
    where: { id: job.id },
    update: {
      templateId: job.templateId,
      scanId: job.scanId,
      symbol: job.symbol,
      status: job.status,
      startedAt: toDate(job.startedAt),
      completedAt: toDate(job.completedAt),
      runId: job.runId ?? null,
      error: job.error ?? null,
      createdAt: toDate(job.createdAt) ?? new Date(),
      updatedAt: toDate(job.updatedAt) ?? new Date(),
    },
    create: {
      id: job.id,
      templateId: job.templateId,
      scanId: job.scanId,
      symbol: job.symbol,
      status: job.status,
      startedAt: toDate(job.startedAt),
      completedAt: toDate(job.completedAt),
      runId: job.runId ?? null,
      error: job.error ?? null,
      createdAt: toDate(job.createdAt) ?? new Date(),
      updatedAt: toDate(job.updatedAt) ?? new Date(),
    },
  });
}

async function listScanRuns(): Promise<StrategyScanRun[]> {
  const dbRuns = await listScanRunsFromDatabase().catch(() => []);
  try {
    const [runEntries, legacyEntries] = await Promise.all([
      fs.readdir(RUNS_DIR, { withFileTypes: true }).catch(() => []),
      fs.readdir(DATA_DIR, { withFileTypes: true }).catch(() => []),
    ]);
    const runFiles = [
      ...runEntries
        .filter(entry => entry.isFile() && entry.name.endsWith('.json'))
        .map(entry => path.join(RUNS_DIR, entry.name)),
      ...legacyEntries
        .filter(entry => entry.isFile() && entry.name.endsWith('.json'))
        .map(entry => path.join(DATA_DIR, entry.name)),
    ];
    const runs = await Promise.all(runFiles.map(filePath => readJsonFile<StrategyScanRun>(filePath)));
    const byId = new Map<string, StrategyScanRun>();
    for (const run of runs.filter((run): run is StrategyScanRun => Boolean(run?.id && run?.templateId && run?.scanId))) {
      byId.set(run.id, run);
    }
    for (const run of dbRuns) {
      byId.set(run.id, run);
    }
    return Array.from(byId.values()).sort((a, b) => b.completedAt.localeCompare(a.completedAt));
  } catch {
    return dbRuns;
  }
}

function scanRunPath(runId: string) {
  return path.join(RUNS_DIR, `${runId}.json`);
}

async function listScanJobs(): Promise<StrategyScanJob[]> {
  const dbJobs = await listScanJobsFromDatabase().catch(() => []);
  try {
    const entries = await fs.readdir(JOBS_DIR, { withFileTypes: true });
    const jobs = await Promise.all(
      entries
        .filter(entry => entry.isFile() && entry.name.endsWith('.json'))
        .map(entry => readJsonFile<StrategyScanJob>(path.join(JOBS_DIR, entry.name)))
    );
    const byId = new Map<string, StrategyScanJob>();
    for (const job of jobs.filter((job): job is StrategyScanJob => Boolean(job?.id && job?.templateId && job?.scanId))) {
      byId.set(job.id, job);
    }
    for (const job of dbJobs) {
      byId.set(job.id, job);
    }
    return Array.from(byId.values()).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } catch {
    return dbJobs;
  }
}

function scanJobPath(jobId: string) {
  return path.join(JOBS_DIR, `${jobId}.json`);
}

async function writeScanJob(job: StrategyScanJob) {
  await Promise.all([
    writeScanJobToDatabase(job),
    writeJsonFile(scanJobPath(job.id), job).catch(() => undefined),
  ]);
}

async function writeScanRun(run: StrategyScanRun) {
  await Promise.all([
    writeScanRunToDatabase(run),
    writeJsonFile(scanRunPath(run.id), run).catch(() => undefined),
  ]);
}

function findTemplate(templateId: string) {
  return STRATEGY_TEMPLATES.find(template => template.id === templateId) ?? null;
}

function findScan(template: StrategyTemplate, scanId: string) {
  return template.parameterScans.find(scan => scan.id === scanId) ?? null;
}

function expandGrid(scan: StrategyParameterScan): Array<Record<string, string | number>> {
  return scan.grid.reduce<Array<Record<string, string | number>>>((acc, item) => {
    const base = acc.length ? acc : [{}];
    return base.flatMap(existing =>
      item.values.map(value => ({
        ...existing,
        [item.key]: value,
      }))
    );
  }, []);
}

function isValidMaCrossoverParams(params: Record<string, string | number>) {
  const fast = asNumber(params.fast_window);
  const slow = asNumber(params.slow_window);
  return fast !== null && slow !== null && fast < slow;
}

async function fetchBacktest(params: {
  symbol: string;
  parameters: Record<string, string | number>;
}): Promise<Record<string, unknown>> {
  const query = new URLSearchParams({
    fast_window: String(params.parameters.fast_window ?? 20),
    slow_window: String(params.parameters.slow_window ?? 60),
    fee_bps: String(params.parameters.fee_bps ?? 5),
    period: 'daily',
    adjustment: 'qfq',
    limit: '250',
  });
  const response = await fetch(
    `${MARKET_API_BASE_URL}/api/v1/backtests/ma-crossover/${encodeURIComponent(params.symbol)}?${query.toString()}`,
    { cache: 'no-store' }
  );
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${body.slice(0, 180)}`);
  }
  return response.json() as Promise<Record<string, unknown>>;
}

function summarizeBacktest(backtest: Record<string, unknown>): StrategyScanRunResult['metrics'] {
  const summary = backtest.summary && typeof backtest.summary === 'object'
    ? backtest.summary as Record<string, unknown>
    : {};
  return {
    totalReturnPct: asNumber(summary.total_return_pct),
    maxDrawdownPct: asNumber(summary.max_drawdown_pct),
    winRatePct: asNumber(summary.win_rate_pct),
    tradeCount: asNumber(summary.trade_count),
    sharpe: asNumber(summary.sharpe),
  };
}

function chooseBestResult(results: StrategyScanRunResult[]) {
  const successful = results.filter(result => result.status === 'success');
  if (!successful.length) return null;
  return successful
    .slice()
    .sort((a, b) => {
      const aReturn = a.metrics.totalReturnPct ?? Number.NEGATIVE_INFINITY;
      const bReturn = b.metrics.totalReturnPct ?? Number.NEGATIVE_INFINITY;
      if (aReturn !== bReturn) return bReturn - aReturn;
      const aDrawdown = a.metrics.maxDrawdownPct ?? Number.POSITIVE_INFINITY;
      const bDrawdown = b.metrics.maxDrawdownPct ?? Number.POSITIVE_INFINITY;
      return aDrawdown - bDrawdown;
    })[0];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)) : [];
}

function dataStatus(value: unknown): StrategyUniverseMember['dataStatus'] {
  return value === 'ready' || value === 'stale' || value === 'missing' ? value : 'missing';
}

function mapResearchMember(value: unknown): StrategyUniverseMember {
  const record = asRecord(value);
  return {
    symbol: asString(record.symbol),
    code: asString(record.code),
    name: typeof record.name === 'string' ? record.name : null,
    exchange: asString(record.exchange, 'UNKNOWN'),
    assetType: asString(record.asset_type, 'stock'),
    currency: asString(record.currency, 'CNY'),
    timezone: asString(record.timezone, 'Asia/Shanghai'),
    secid: typeof record.secid === 'string' ? record.secid : null,
    provider: asString(record.provider, 'eastmoney'),
    securityStatus: asString(record.security_status, 'active'),
    role: asString(record.role, 'member'),
    weight: asNumber(record.weight),
    rowCount: asNumber(record.row_count) ?? 0,
    firstTs: typeof record.first_ts === 'string' ? record.first_ts : null,
    lastTs: typeof record.last_ts === 'string' ? record.last_ts : null,
    dataProvider: typeof record.data_provider === 'string' ? record.data_provider : null,
    dataStatus: dataStatus(record.data_status),
  };
}

function mapResearchUniverse(value: unknown): StrategyUniverse {
  const record = asRecord(value);
  const members = Array.isArray(record.members) ? record.members.map(mapResearchMember) : [];
  return {
    id: asString(record.id, SAMPLE_UNIVERSE_ID),
    name: asString(record.name, 'A 股示例研究池'),
    description: typeof record.description === 'string' ? record.description : null,
    status: asString(record.status, 'active'),
    source: asString(record.source, 'seed'),
    tags: asStringArray(record.tags),
    defaultTimeframe: asString(record.default_timeframe, 'daily'),
    defaultAdjustment: asString(record.default_adjustment, 'qfq'),
    provider: asString(record.provider, 'eastmoney'),
    members,
  };
}

function mapCoverageItem(value: unknown): StrategyDataCoverageItem {
  const record = asRecord(value);
  return {
    symbol: asString(record.symbol),
    name: typeof record.name === 'string' ? record.name : null,
    timeframe: asString(record.timeframe, 'daily'),
    adjustment: asString(record.adjustment, 'qfq'),
    provider: asString(record.provider, 'eastmoney'),
    firstTs: typeof record.first_ts === 'string' ? record.first_ts : null,
    lastTs: typeof record.last_ts === 'string' ? record.last_ts : null,
    rowCount: asNumber(record.row_count) ?? 0,
    dataStatus: dataStatus(record.data_status),
  };
}

function mapLocalKlineBar(value: unknown): StrategyLocalKlineBar {
  const record = asRecord(value);
  return {
    ts: asString(record.ts),
    open: asNumber(record.open) ?? 0,
    high: asNumber(record.high) ?? 0,
    low: asNumber(record.low) ?? 0,
    close: asNumber(record.close) ?? 0,
    volume: asNumber(record.volume) ?? 0,
    amount: asNumber(record.amount),
    amplitude: asNumber(record.amplitude),
    changePercent: asNumber(record.change_percent),
    changeAmount: asNumber(record.change_amount),
    turnover: asNumber(record.turnover),
    provider: asString(record.provider, 'unknown'),
    metadata: asRecord(record.metadata),
  };
}

function mapDividendEvent(value: unknown): StrategyDividendEvent {
  const record = asRecord(value);
  return {
    symbol: asString(record.symbol),
    name: typeof record.name === 'string' ? record.name : null,
    reportDate: typeof record.report_date === 'string' ? record.report_date : null,
    planNoticeDate: typeof record.plan_notice_date === 'string' ? record.plan_notice_date : null,
    equityRecordDate: typeof record.equity_record_date === 'string' ? record.equity_record_date : null,
    exDividendDate: typeof record.ex_dividend_date === 'string' ? record.ex_dividend_date : null,
    noticeDate: typeof record.notice_date === 'string' ? record.notice_date : null,
    assignProgress: typeof record.assign_progress === 'string' ? record.assign_progress : null,
    planProfile: typeof record.plan_profile === 'string' ? record.plan_profile : null,
    pretaxBonusRmb: asNumber(record.pretax_bonus_rmb),
    bonusRatio: asNumber(record.bonus_ratio),
    transferRatio: asNumber(record.transfer_ratio),
    dividendYield: asNumber(record.dividend_yield),
  };
}

function mapDividendEventsResponse(value: unknown): StrategyDividendEventsResponse {
  const record = asRecord(value);
  return {
    symbol: asString(record.symbol),
    events: Array.isArray(record.events) ? record.events.map(mapDividendEvent) : [],
    source: asString(record.source, 'eastmoney'),
    fetchedAt: asString(record.fetched_at, new Date().toISOString()),
  };
}

function mapLocalKlineResponse(value: unknown): StrategyLocalKlineResponse {
  const record = asRecord(value);
  const summary = asRecord(record.summary);
  const bars = Array.isArray(record.bars) ? record.bars.map(mapLocalKlineBar) : [];
  return {
    symbol: asString(record.symbol),
    code: typeof record.code === 'string' ? record.code : null,
    name: typeof record.name === 'string' ? record.name : null,
    exchange: asString(record.exchange, 'UNKNOWN'),
    assetType: asString(record.asset_type, 'stock'),
    currency: asString(record.currency, 'CNY'),
    timezone: asString(record.timezone, 'Asia/Shanghai'),
    secid: typeof record.secid === 'string' ? record.secid : null,
    provider: typeof record.provider === 'string' ? record.provider : null,
    dataProvider: bars.at(-1)?.provider ?? null,
    timeframe: asString(record.timeframe, 'daily'),
    adjustment: asString(record.adjustment, 'qfq'),
    bars,
    summary: {
      rowCount: asNumber(summary.row_count) ?? bars.length,
      firstTs: typeof summary.first_ts === 'string' ? summary.first_ts : null,
      lastTs: typeof summary.last_ts === 'string' ? summary.last_ts : null,
      latestClose: asNumber(summary.latest_close),
      previousClose: asNumber(summary.previous_close),
      returnPct: asNumber(summary.return_pct),
      high: asNumber(summary.high),
      low: asNumber(summary.low),
      totalVolume: asNumber(summary.total_volume),
      totalAmount: asNumber(summary.total_amount),
    },
    fetchedAt: asString(record.fetched_at, new Date().toISOString()),
  };
}

async function fetchMarketApiJson<T>(pathName: string): Promise<T> {
  const response = await fetch(`${MARKET_API_BASE_URL}${pathName}`, { cache: 'no-store' });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${body.slice(0, 180)}`);
  }
  return response.json() as Promise<T>;
}

async function getStrategyResearchState(): Promise<StrategyResearchState> {
  try {
    const universesPayload = asRecord(
      await fetchMarketApiJson<unknown>('/api/v1/research/universes')
    );
    const universes = Array.isArray(universesPayload.universes)
      ? universesPayload.universes.map(mapResearchUniverse)
      : [];
    const primaryUniverse = universes[0] ?? FALLBACK_RESEARCH_STATE.universes[0];
    const coveragePayload = asRecord(
      await fetchMarketApiJson<unknown>(
        `/api/v1/research/data-coverage?universe_id=${encodeURIComponent(primaryUniverse.id)}`
      )
    );
    const coverage = Array.isArray(coveragePayload.items)
      ? coveragePayload.items.map(mapCoverageItem)
      : [];

    return {
      ...FALLBACK_RESEARCH_STATE,
      primaryUniverseId: primaryUniverse.id,
      source: 'market-api',
      universes: universes.length ? universes : FALLBACK_RESEARCH_STATE.universes,
      coverage: coverage.length ? coverage : FALLBACK_RESEARCH_STATE.coverage,
      ingestionPlan: {
        ...FALLBACK_RESEARCH_STATE.ingestionPlan,
        universeId: primaryUniverse.id,
        timeframe: primaryUniverse.defaultTimeframe,
        adjustment: primaryUniverse.defaultAdjustment,
        provider: primaryUniverse.provider,
        lookbackYears: FALLBACK_RESEARCH_STATE.ingestionPlan.lookbackYears,
      },
      error: null,
    };
  } catch (error) {
    return {
      ...FALLBACK_RESEARCH_STATE,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function isStrategyCapability(capabilityId?: string | null): capabilityId is QuantCapabilityId {
  return capabilityId === 'strategy_research' || capabilityId === 'backtest_review' || capabilityId === 'portfolio_risk';
}

function toWorkspaceRef(project: Project): StrategyWorkspaceRef {
  return {
    id: project.id,
    name: project.name,
    status: project.status ?? null,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt ?? null,
    capabilityId: project.quantCapabilityId ?? null,
    initialPrompt: project.initialPrompt ?? null,
  };
}

function matchesTemplate(project: StrategyWorkspaceRef, template: StrategyTemplate) {
  if (project.capabilityId === template.capabilityId) return true;
  const prompt = `${project.name} ${project.initialPrompt ?? ''}`.toLowerCase();
  return template.defaultSymbols.some(symbol => prompt.includes(symbol.toLowerCase())) ||
    template.parameterSchema.some(param => prompt.includes(param.key.toLowerCase()));
}

export async function getStrategyDashboardData(): Promise<StrategyDashboardData> {
  const projects = serializeProjects(await getAllProjects());
  const [scanRuns, scanJobs, research] = await Promise.all([
    listScanRuns(),
    listScanJobs(),
    getStrategyResearchState(),
  ]);
  const strategyWorkspaces = projects
    .filter(project => isStrategyCapability(project.quantCapabilityId))
    .map(toWorkspaceRef);

  const templates = STRATEGY_TEMPLATES.map((template): StrategyCatalogItem => ({
    ...template,
    readiness: readinessFor(template),
    linkedWorkspaces: strategyWorkspaces.filter(project => matchesTemplate(project, template)),
    latestScanRun: scanRuns.find(run => run.templateId === template.id) ?? null,
  }));

  const dependencySet = new Set(templates.flatMap(template => template.dataDependencies));
  const parameterScans = templates.reduce((sum, template) => sum + template.parameterScans.length, 0);
  const archivedReports = templates.reduce((sum, template) => sum + template.backtestArchives.length, 0);
  const activeVersions = templates.reduce(
    (sum, template) => sum + template.versions.filter(version => version.status === 'active').length,
    0
  );
  const trackedSymbols = research.universes.reduce(
    (sum, universe) => sum + universe.members.length,
    0
  );
  const syncedSymbols = research.coverage.filter(item => item.dataStatus === 'ready').length;
  const syncedBars = research.coverage.reduce((sum, item) => sum + item.rowCount, 0);

  return {
    generatedAt: new Date().toISOString(),
    summary: {
      templates: templates.length,
      readyTemplates: templates.filter(template => template.status === 'ready').length,
      plannedTemplates: templates.filter(template => template.status === 'planned').length,
      strategyWorkspaces: strategyWorkspaces.length,
      backtestWorkspaces: strategyWorkspaces.filter(project => project.capabilityId === 'backtest_review').length,
      dataDependencies: dependencySet.size,
      parameterScans,
      archivedReports,
      activeVersions,
      researchUniverses: research.universes.length,
      trackedSymbols,
      syncedSymbols,
      syncedBars,
    },
    templates,
    workspaces: strategyWorkspaces,
    scanRuns,
    scanJobs,
    research,
  };
}

export function buildStrategyPrompt(templateId: string, symbol?: string) {
  const template = STRATEGY_TEMPLATES.find(item => item.id === templateId) ?? STRATEGY_TEMPLATES[0];
  const target = symbol?.trim() || template.defaultSymbols[0];
  const capability = getQuantCapability(template.capabilityId);
  return {
    name: `${template.name} · ${target}`,
    prompt: `${template.promptSeed}\n\n策略模板：${template.name}\n目标标的：${target}\n能力模块：${capability.name}\n必须展示参数、数据来源、风险限制和验证结论边界。`,
    capabilityId: capability.id,
  };
}

export async function ingestStrategyUniverseHistory(params: {
  universeId?: string;
  symbols?: string[];
  limit?: number;
  lookbackYears?: number;
  period?: string;
  adjustment?: string;
} = {}): Promise<StrategyHistoryIngestionResult> {
  const body = {
    universe_id: params.universeId || SAMPLE_UNIVERSE_ID,
    symbols: params.symbols?.length ? params.symbols : undefined,
    period: params.period || 'daily',
    adjustment: params.adjustment || 'qfq',
    limit: params.limit ?? FALLBACK_RESEARCH_STATE.ingestionPlan.suggestedLimit,
    lookback_years: params.lookbackYears ?? FALLBACK_RESEARCH_STATE.ingestionPlan.lookbackYears,
  };
  const response = await fetch(`${MARKET_API_BASE_URL}/api/v1/ingestion/eastmoney/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${text.slice(0, 200)}`);
  }
  return response.json() as Promise<StrategyHistoryIngestionResult>;
}

export async function addStrategyUniverseMember(params: {
  universeId?: string;
  query: string;
  syncHistory?: boolean;
}): Promise<StrategyUniverseMemberAddResult> {
  const universeId = params.universeId || SAMPLE_UNIVERSE_ID;
  const response = await fetch(
    `${MARKET_API_BASE_URL}/api/v1/research/universes/${encodeURIComponent(universeId)}/members`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: params.query }),
      cache: 'no-store',
    }
  );
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${text.slice(0, 200)}`);
  }

  const payload = asRecord(await response.json());
  const member = mapResearchMember(payload.member);
  let ingestion: StrategyHistoryIngestionResult | null = null;
  if (params.syncHistory === true) {
    ingestion = await ingestStrategyUniverseHistory({
      universeId,
      symbols: [member.symbol],
    });
  }

  return {
    universe_id: asString(payload.universe_id, universeId),
    member,
    candidates: Array.isArray(payload.candidates)
      ? payload.candidates.map(candidate => asRecord(candidate)).map(candidate => ({
        symbol: asString(candidate.symbol),
        name: typeof candidate.name === 'string' ? candidate.name : null,
        market: asString(candidate.market, 'UNKNOWN'),
        asset_type: asString(candidate.asset_type, 'stock'),
        secid: asString(candidate.secid),
        source: asString(candidate.source, 'eastmoney'),
      }))
      : [],
    ingestion,
  };
}

export async function getStrategySymbolBars(params: {
  symbol: string;
  timeframe?: string;
  adjustment?: string;
  provider?: string | null;
  limit?: number;
}): Promise<StrategyLocalKlineResponse> {
  const query = new URLSearchParams({
    timeframe: params.timeframe || 'daily',
    adjustment: params.adjustment || 'qfq',
    limit: String(params.limit ?? 240),
  });
  if (params.provider) query.set('provider', params.provider);
  const response = await fetch(
    `${MARKET_API_BASE_URL}/api/v1/research/bars/${encodeURIComponent(params.symbol)}?${query.toString()}`,
    { cache: 'no-store' }
  );
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${text.slice(0, 200)}`);
  }
  return mapLocalKlineResponse(await response.json());
}

export async function getStrategySymbolDividends(params: {
  symbol: string;
  limit?: number;
}): Promise<StrategyDividendEventsResponse> {
  const query = new URLSearchParams({
    limit: String(params.limit ?? 20),
  });
  const response = await fetch(
    `${MARKET_API_BASE_URL}/api/v1/events/dividends/${encodeURIComponent(params.symbol)}?${query.toString()}`,
    { cache: 'no-store' }
  );
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`market API ${response.status}: ${text.slice(0, 200)}`);
  }
  return mapDividendEventsResponse(await response.json());
}

export async function runStrategyParameterScan(params: {
  templateId: string;
  scanId: string;
  symbol?: string;
}): Promise<StrategyScanRun> {
  const template = findTemplate(params.templateId);
  if (!template) {
    throw new Error(`Unknown strategy template: ${params.templateId}`);
  }
  const scan = findScan(template, params.scanId);
  if (!scan) {
    throw new Error(`Unknown parameter scan: ${params.scanId}`);
  }
  const startedAt = new Date().toISOString();
  const symbol = params.symbol?.trim() || template.defaultSymbols[0] || '510300';
  const combinations = expandGrid(scan).slice(0, 64);
  const results: StrategyScanRunResult[] = [];

  if (scan.status !== 'available') {
    const run: StrategyScanRun = {
      id: `scan-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      templateId: template.id,
      scanId: scan.id,
      symbol,
      status: 'failed',
      startedAt,
      completedAt: new Date().toISOString(),
      total: combinations.length,
      succeeded: 0,
      failed: combinations.length,
      bestResultId: null,
      objective: scan.objective,
      source: scan.status === 'planned' ? 'parameter scan is planned' : 'parameter scan is blocked',
      results: combinations.map((parameters, index) => ({
        id: `${scan.id}-${index + 1}`,
        parameters,
        status: 'skipped',
        metrics: {},
        error: scan.status === 'planned' ? '扫描仍在规划中' : '扫描被依赖阻断',
      })),
    };
    await writeScanRun(run);
    return run;
  }

  for (const [index, parameters] of combinations.entries()) {
    const id = `${scan.id}-${index + 1}`;
    if (template.id === 'ma-crossover-single-asset' && !isValidMaCrossoverParams(parameters)) {
      results.push({
        id,
        parameters,
        status: 'skipped',
        metrics: {},
        error: 'fast_window 必须小于 slow_window',
      });
      continue;
    }

    try {
      const backtest = await fetchBacktest({ symbol, parameters });
      results.push({
        id,
        parameters,
        status: 'success',
        metrics: summarizeBacktest(backtest),
      });
    } catch (error) {
      results.push({
        id,
        parameters,
        status: 'failed',
        metrics: {},
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  const best = chooseBestResult(results);
  const succeeded = results.filter(result => result.status === 'success').length;
  const failed = results.filter(result => result.status === 'failed').length;
  const run: StrategyScanRun = {
    id: `scan-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    templateId: template.id,
    scanId: scan.id,
    symbol,
    status: succeeded === 0 ? 'failed' : failed > 0 ? 'partial' : 'completed',
    startedAt,
    completedAt: new Date().toISOString(),
    total: results.length,
    succeeded,
    failed,
    bestResultId: best?.id ?? null,
    objective: scan.objective,
    source: `${MARKET_API_BASE_URL}/api/v1/backtests/ma-crossover/{symbol}`,
    results,
  };
  await writeScanRun(run);
  return run;
}

async function executeScanJob(job: StrategyScanJob) {
  const runningJob: StrategyScanJob = {
    ...job,
    status: 'running',
    startedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    error: null,
  };
  await writeScanJob(runningJob);

  try {
    const run = await runStrategyParameterScan({
      templateId: job.templateId,
      scanId: job.scanId,
      symbol: job.symbol,
    });
    await writeScanJob({
      ...runningJob,
      status: run.status === 'failed' ? 'failed' : 'completed',
      runId: run.id,
      completedAt: run.completedAt,
      updatedAt: new Date().toISOString(),
      error: run.status === 'failed' ? '扫描未产生成功结果' : null,
    });
  } catch (error) {
    await writeScanJob({
      ...runningJob,
      status: 'failed',
      completedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

export async function enqueueStrategyParameterScan(params: {
  templateId: string;
  scanId: string;
  symbol?: string;
}): Promise<StrategyScanJob> {
  const template = findTemplate(params.templateId);
  if (!template) {
    throw new Error(`Unknown strategy template: ${params.templateId}`);
  }
  const scan = findScan(template, params.scanId);
  if (!scan) {
    throw new Error(`Unknown parameter scan: ${params.scanId}`);
  }

  const now = new Date().toISOString();
  const job: StrategyScanJob = {
    id: `scan-job-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    templateId: template.id,
    scanId: scan.id,
    symbol: params.symbol?.trim() || template.defaultSymbols[0] || '510300',
    status: 'queued',
    createdAt: now,
    updatedAt: now,
    runId: null,
    error: null,
  };
  await writeScanJob(job);

  setTimeout(() => {
    void executeScanJob(job);
  }, 0);

  return job;
}
