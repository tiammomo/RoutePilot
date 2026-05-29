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
  industry?: string | null;
  region?: string | null;
  concepts: string[];
  sectorHint?: string | null;
  sectorTags: string[];
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
  latestClose?: number | null;
  latestChangePct?: number | null;
  latestAmount?: number | null;
  latestTurnover?: number | null;
  strength20dPct?: number | null;
  strength60dPct?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  trendStatus: 'bullish' | 'bearish' | 'sideways' | 'insufficient';
  avgAmount20d?: number | null;
  avgVolume20d?: number | null;
  avgTurnover20d?: number | null;
  tradeStatus?: string | null;
  isSt?: boolean | null;
  limitUp?: boolean | null;
  limitDown?: boolean | null;
  peTtm?: number | null;
  pbMrq?: number | null;
  psTtm?: number | null;
  pcfNcfTtm?: number | null;
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
  memberCount: number;
  stockCount: number;
  etfCount: number;
  indexCount: number;
  fundCount: number;
  readyCount: number;
  barCount: number;
  latestTs?: string | null;
}

export interface StrategyUniverseMembersPage {
  universeId: string;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  keyword?: string | null;
  members: StrategyUniverseMember[];
  fetchedAt: string;
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
  previousClose?: number | null;
  volume: number;
  amount?: number | null;
  amplitude?: number | null;
  changePercent?: number | null;
  changeAmount?: number | null;
  turnover?: number | null;
  tradeStatus?: string | null;
  isSt?: boolean | null;
  limitUp?: boolean | null;
  limitDown?: boolean | null;
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
  provider?: string;
  universe_id?: string | null;
  total_symbols: number;
  completed_symbols: number;
  failed_symbols: number;
  rows_received: number;
  rows_upserted: number;
  batch_offset?: number | null;
  batch_size?: number | null;
  next_offset?: number | null;
  universe_total_symbols?: number | null;
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

export interface StrategyIngestionJob {
  id: string;
  universeId?: string | null;
  provider: string;
  timeframe: string;
  adjustment: string;
  status: string;
  totalSymbols: number;
  completedSymbols: number;
  failedSymbols: number;
  rowsReceived: number;
  rowsUpserted: number;
  error?: string | null;
  metadata: Record<string, unknown>;
  batchOffset?: number | null;
  batchSize?: number | null;
  nextOffset?: number | null;
  universeTotalSymbols?: number | null;
  startedAt?: string | null;
  completedAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface StrategyIngestionJobsResponse {
  jobs: StrategyIngestionJob[];
  fetchedAt: string;
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
  backtestStrategyId: string;
  backtestLimit?: number;
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

const SAMPLE_UNIVERSE_MEMBER_SEEDS = [
  { symbol: '002156.SZ', code: '002156', name: '通富微电', exchange: 'SZ', secid: '0.002156' },
  { symbol: '002555.SZ', code: '002555', name: '三七互娱', exchange: 'SZ', secid: '0.002555' },
  { symbol: '002624.SZ', code: '002624', name: '完美世界', exchange: 'SZ', secid: '0.002624' },
  { symbol: '601398.SH', code: '601398', name: '工商银行', exchange: 'SH', secid: '1.601398' },
  { symbol: '600916.SH', code: '600916', name: '中国黄金', exchange: 'SH', secid: '1.600916' },
  { symbol: '600519.SH', code: '600519', name: '贵州茅台', exchange: 'SH', secid: '1.600519' },
  { symbol: '000858.SZ', code: '000858', name: '五粮液', exchange: 'SZ', secid: '0.000858' },
  { symbol: '000333.SZ', code: '000333', name: '美的集团', exchange: 'SZ', secid: '0.000333' },
  { symbol: '000651.SZ', code: '000651', name: '格力电器', exchange: 'SZ', secid: '0.000651' },
  { symbol: '300750.SZ', code: '300750', name: '宁德时代', exchange: 'SZ', secid: '0.300750' },
  { symbol: '002594.SZ', code: '002594', name: '比亚迪', exchange: 'SZ', secid: '0.002594' },
  { symbol: '601318.SH', code: '601318', name: '中国平安', exchange: 'SH', secid: '1.601318' },
  { symbol: '600036.SH', code: '600036', name: '招商银行', exchange: 'SH', secid: '1.600036' },
  { symbol: '601166.SH', code: '601166', name: '兴业银行', exchange: 'SH', secid: '1.601166' },
  { symbol: '601288.SH', code: '601288', name: '农业银行', exchange: 'SH', secid: '1.601288' },
  { symbol: '600900.SH', code: '600900', name: '长江电力', exchange: 'SH', secid: '1.600900' },
  { symbol: '601012.SH', code: '601012', name: '隆基绿能', exchange: 'SH', secid: '1.601012' },
  { symbol: '600276.SH', code: '600276', name: '恒瑞医药', exchange: 'SH', secid: '1.600276' },
  { symbol: '000725.SZ', code: '000725', name: '京东方A', exchange: 'SZ', secid: '0.000725' },
  { symbol: '002415.SZ', code: '002415', name: '海康威视', exchange: 'SZ', secid: '0.002415' },
  { symbol: '600050.SH', code: '600050', name: '中国联通', exchange: 'SH', secid: '1.600050' },
  { symbol: '601857.SH', code: '601857', name: '中国石油', exchange: 'SH', secid: '1.601857' },
  { symbol: '600028.SH', code: '600028', name: '中国石化', exchange: 'SH', secid: '1.600028' },
  { symbol: '601668.SH', code: '601668', name: '中国建筑', exchange: 'SH', secid: '1.601668' },
  { symbol: '601888.SH', code: '601888', name: '中国中免', exchange: 'SH', secid: '1.601888' },
  { symbol: '600030.SH', code: '600030', name: '中信证券', exchange: 'SH', secid: '1.600030' },
  { symbol: '300059.SZ', code: '300059', name: '东方财富', exchange: 'SZ', secid: '0.300059' },
  { symbol: '603259.SH', code: '603259', name: '药明康德', exchange: 'SH', secid: '1.603259' },
  { symbol: '688981.SH', code: '688981', name: '中芯国际', exchange: 'SH', secid: '1.688981' },
  { symbol: '002230.SZ', code: '002230', name: '科大讯飞', exchange: 'SZ', secid: '0.002230' },
  { symbol: '603986.SH', code: '603986', name: '兆易创新', exchange: 'SH', secid: '1.603986' },
  { symbol: '603501.SH', code: '603501', name: '韦尔股份', exchange: 'SH', secid: '1.603501' },
  { symbol: '002371.SZ', code: '002371', name: '北方华创', exchange: 'SZ', secid: '0.002371' },
  { symbol: '688012.SH', code: '688012', name: '中微公司', exchange: 'SH', secid: '1.688012' },
  { symbol: '600584.SH', code: '600584', name: '长电科技', exchange: 'SH', secid: '1.600584' },
  { symbol: '688008.SH', code: '688008', name: '澜起科技', exchange: 'SH', secid: '1.688008' },
  { symbol: '688126.SH', code: '688126', name: '沪硅产业', exchange: 'SH', secid: '1.688126' },
  { symbol: '688099.SH', code: '688099', name: '晶晨股份', exchange: 'SH', secid: '1.688099' },
  { symbol: '300223.SZ', code: '300223', name: '北京君正', exchange: 'SZ', secid: '0.300223' },
  { symbol: '603290.SH', code: '603290', name: '斯达半导', exchange: 'SH', secid: '1.603290' },
  { symbol: '300661.SZ', code: '300661', name: '圣邦股份', exchange: 'SZ', secid: '0.300661' },
  { symbol: '300782.SZ', code: '300782', name: '卓胜微', exchange: 'SZ', secid: '0.300782' },
  { symbol: '002049.SZ', code: '002049', name: '紫光国微', exchange: 'SZ', secid: '0.002049' },
  { symbol: '600745.SH', code: '600745', name: '闻泰科技', exchange: 'SH', secid: '1.600745' },
  { symbol: '605358.SH', code: '605358', name: '立昂微', exchange: 'SH', secid: '1.605358' },
  { symbol: '688396.SH', code: '688396', name: '华润微', exchange: 'SH', secid: '1.688396' },
  { symbol: '688041.SH', code: '688041', name: '海光信息', exchange: 'SH', secid: '1.688041' },
  { symbol: '688256.SH', code: '688256', name: '寒武纪', exchange: 'SH', secid: '1.688256' },
  { symbol: '688111.SH', code: '688111', name: '金山办公', exchange: 'SH', secid: '1.688111' },
  { symbol: '688036.SH', code: '688036', name: '传音控股', exchange: 'SH', secid: '1.688036' },
  { symbol: '688521.SH', code: '688521', name: '芯原股份', exchange: 'SH', secid: '1.688521' },
  { symbol: '002475.SZ', code: '002475', name: '立讯精密', exchange: 'SZ', secid: '0.002475' },
  { symbol: '601138.SH', code: '601138', name: '工业富联', exchange: 'SH', secid: '1.601138' },
  { symbol: '300308.SZ', code: '300308', name: '中际旭创', exchange: 'SZ', secid: '0.300308' },
  { symbol: '300502.SZ', code: '300502', name: '新易盛', exchange: 'SZ', secid: '0.300502' },
  { symbol: '300394.SZ', code: '300394', name: '天孚通信', exchange: 'SZ', secid: '0.300394' },
  { symbol: '000977.SZ', code: '000977', name: '浪潮信息', exchange: 'SZ', secid: '0.000977' },
  { symbol: '603019.SH', code: '603019', name: '中科曙光', exchange: 'SH', secid: '1.603019' },
  { symbol: '000938.SZ', code: '000938', name: '紫光股份', exchange: 'SZ', secid: '0.000938' },
  { symbol: '002463.SZ', code: '002463', name: '沪电股份', exchange: 'SZ', secid: '0.002463' },
  { symbol: '300033.SZ', code: '300033', name: '同花顺', exchange: 'SZ', secid: '0.300033' },
  { symbol: '600570.SH', code: '600570', name: '恒生电子', exchange: 'SH', secid: '1.600570' },
  { symbol: '600588.SH', code: '600588', name: '用友网络', exchange: 'SH', secid: '1.600588' },
  { symbol: '002410.SZ', code: '002410', name: '广联达', exchange: 'SZ', secid: '0.002410' },
  { symbol: '002236.SZ', code: '002236', name: '大华股份', exchange: 'SZ', secid: '0.002236' },
  { symbol: '002241.SZ', code: '002241', name: '歌尔股份', exchange: 'SZ', secid: '0.002241' },
  { symbol: '300124.SZ', code: '300124', name: '汇川技术', exchange: 'SZ', secid: '0.300124' },
  { symbol: '688777.SH', code: '688777', name: '中控技术', exchange: 'SH', secid: '1.688777' },
  { symbol: '300496.SZ', code: '300496', name: '中科创达', exchange: 'SZ', secid: '0.300496' },
  { symbol: '002920.SZ', code: '002920', name: '德赛西威', exchange: 'SZ', secid: '0.002920' },
  { symbol: '000063.SZ', code: '000063', name: '中兴通讯', exchange: 'SZ', secid: '0.000063' },
  { symbol: '600941.SH', code: '600941', name: '中国移动', exchange: 'SH', secid: '1.600941' },
  { symbol: '300604.SZ', code: '300604', name: '长川科技', exchange: 'SZ', secid: '0.300604' },
  { symbol: '688037.SH', code: '688037', name: '芯源微', exchange: 'SH', secid: '1.688037' },
  { symbol: '688072.SH', code: '688072', name: '拓荆科技', exchange: 'SH', secid: '1.688072' },
  { symbol: '688082.SH', code: '688082', name: '盛美上海', exchange: 'SH', secid: '1.688082' },
  { symbol: '688120.SH', code: '688120', name: '华海清科', exchange: 'SH', secid: '1.688120' },
  { symbol: '688200.SH', code: '688200', name: '华峰测控', exchange: 'SH', secid: '1.688200' },
  { symbol: '688019.SH', code: '688019', name: '安集科技', exchange: 'SH', secid: '1.688019' },
  { symbol: '688234.SH', code: '688234', name: '天岳先进', exchange: 'SH', secid: '1.688234' },
  { symbol: '300666.SZ', code: '300666', name: '江丰电子', exchange: 'SZ', secid: '0.300666' },
  { symbol: '002409.SZ', code: '002409', name: '雅克科技', exchange: 'SZ', secid: '0.002409' },
  { symbol: '688536.SH', code: '688536', name: '思瑞浦', exchange: 'SH', secid: '1.688536' },
  { symbol: '688052.SH', code: '688052', name: '纳芯微', exchange: 'SH', secid: '1.688052' },
  { symbol: '688798.SH', code: '688798', name: '艾为电子', exchange: 'SH', secid: '1.688798' },
  { symbol: '688608.SH', code: '688608', name: '恒玄科技', exchange: 'SH', secid: '1.688608' },
  { symbol: '688385.SH', code: '688385', name: '复旦微电', exchange: 'SH', secid: '1.688385' },
  { symbol: '688107.SH', code: '688107', name: '安路科技', exchange: 'SH', secid: '1.688107' },
  { symbol: '688153.SH', code: '688153', name: '唯捷创芯', exchange: 'SH', secid: '1.688153' },
  { symbol: '688213.SH', code: '688213', name: '思特威', exchange: 'SH', secid: '1.688213' },
  { symbol: '688220.SH', code: '688220', name: '翱捷科技', exchange: 'SH', secid: '1.688220' },
  { symbol: '301269.SZ', code: '301269', name: '华大九天', exchange: 'SZ', secid: '0.301269' },
  { symbol: '688262.SH', code: '688262', name: '国芯科技', exchange: 'SH', secid: '1.688262' },
  { symbol: '688047.SH', code: '688047', name: '龙芯中科', exchange: 'SH', secid: '1.688047' },
  { symbol: '688502.SH', code: '688502', name: '茂莱光学', exchange: 'SH', secid: '1.688502' },
  { symbol: '688498.SH', code: '688498', name: '源杰科技', exchange: 'SH', secid: '1.688498' },
  { symbol: '300567.SZ', code: '300567', name: '精测电子', exchange: 'SZ', secid: '0.300567' },
  { symbol: '002916.SZ', code: '002916', name: '深南电路', exchange: 'SZ', secid: '0.002916' },
  { symbol: '002938.SZ', code: '002938', name: '鹏鼎控股', exchange: 'SZ', secid: '0.002938' },
  { symbol: '002384.SZ', code: '002384', name: '东山精密', exchange: 'SZ', secid: '0.002384' },
  { symbol: '300476.SZ', code: '300476', name: '胜宏科技', exchange: 'SZ', secid: '0.300476' },
  { symbol: '603228.SH', code: '603228', name: '景旺电子', exchange: 'SH', secid: '1.603228' },
  { symbol: '603160.SH', code: '603160', name: '汇顶科技', exchange: 'SH', secid: '1.603160' },
  { symbol: '002138.SZ', code: '002138', name: '顺络电子', exchange: 'SZ', secid: '0.002138' },
  { symbol: '600183.SH', code: '600183', name: '生益科技', exchange: 'SH', secid: '1.600183' },
  { symbol: '300408.SZ', code: '300408', name: '三环集团', exchange: 'SZ', secid: '0.300408' },
  { symbol: '002402.SZ', code: '002402', name: '和而泰', exchange: 'SZ', secid: '0.002402' },
  { symbol: '002139.SZ', code: '002139', name: '拓邦股份', exchange: 'SZ', secid: '0.002139' },
  { symbol: '002050.SZ', code: '002050', name: '三花智控', exchange: 'SZ', secid: '0.002050' },
  { symbol: '002747.SZ', code: '002747', name: '埃斯顿', exchange: 'SZ', secid: '0.002747' },
  { symbol: '300024.SZ', code: '300024', name: '机器人', exchange: 'SZ', secid: '0.300024' },
  { symbol: '688017.SH', code: '688017', name: '绿的谐波', exchange: 'SH', secid: '1.688017' },
  { symbol: '301029.SZ', code: '301029', name: '怡合达', exchange: 'SZ', secid: '0.301029' },
  { symbol: '688188.SH', code: '688188', name: '柏楚电子', exchange: 'SH', secid: '1.688188' },
  { symbol: '300316.SZ', code: '300316', name: '晶盛机电', exchange: 'SZ', secid: '0.300316' },
  { symbol: '002008.SZ', code: '002008', name: '大族激光', exchange: 'SZ', secid: '0.002008' },
  { symbol: '300450.SZ', code: '300450', name: '先导智能', exchange: 'SZ', secid: '0.300450' },
  { symbol: '688187.SH', code: '688187', name: '时代电气', exchange: 'SH', secid: '1.688187' },
  { symbol: '688169.SH', code: '688169', name: '石头科技', exchange: 'SH', secid: '1.688169' },
  { symbol: '000066.SZ', code: '000066', name: '中国长城', exchange: 'SZ', secid: '0.000066' },
  { symbol: '002439.SZ', code: '002439', name: '启明星辰', exchange: 'SZ', secid: '0.002439' },
  { symbol: '300454.SZ', code: '300454', name: '深信服', exchange: 'SZ', secid: '0.300454' },
  { symbol: '300017.SZ', code: '300017', name: '网宿科技', exchange: 'SZ', secid: '0.300017' },
  { symbol: '002405.SZ', code: '002405', name: '四维图新', exchange: 'SZ', secid: '0.002405' },
  { symbol: '002212.SZ', code: '002212', name: '天融信', exchange: 'SZ', secid: '0.002212' },
  { symbol: '688568.SH', code: '688568', name: '中科星图', exchange: 'SH', secid: '1.688568' },
  { symbol: '688088.SH', code: '688088', name: '虹软科技', exchange: 'SH', secid: '1.688088' },
  { symbol: '300229.SZ', code: '300229', name: '拓尔思', exchange: 'SZ', secid: '0.300229' },
  { symbol: '300418.SZ', code: '300418', name: '昆仑万维', exchange: 'SZ', secid: '0.300418' },
  { symbol: '300413.SZ', code: '300413', name: '芒果超媒', exchange: 'SZ', secid: '0.300413' },
  { symbol: '603000.SH', code: '603000', name: '人民网', exchange: 'SH', secid: '1.603000' },
  { symbol: '601360.SH', code: '601360', name: '三六零', exchange: 'SH', secid: '1.601360' },
  { symbol: '002602.SZ', code: '002602', name: '世纪华通', exchange: 'SZ', secid: '0.002602' },
  { symbol: '300315.SZ', code: '300315', name: '掌趣科技', exchange: 'SZ', secid: '0.300315' },
  { symbol: '000001.SZ', code: '000001', name: '平安银行', exchange: 'SZ', secid: '0.000001' },
  { symbol: '600000.SH', code: '600000', name: '浦发银行', exchange: 'SH', secid: '1.600000' },
  { symbol: '601939.SH', code: '601939', name: '建设银行', exchange: 'SH', secid: '1.601939' },
  { symbol: '601988.SH', code: '601988', name: '中国银行', exchange: 'SH', secid: '1.601988' },
  { symbol: '601328.SH', code: '601328', name: '交通银行', exchange: 'SH', secid: '1.601328' },
  { symbol: '601658.SH', code: '601658', name: '邮储银行', exchange: 'SH', secid: '1.601658' },
  { symbol: '600999.SH', code: '600999', name: '招商证券', exchange: 'SH', secid: '1.600999' },
  { symbol: '601211.SH', code: '601211', name: '国泰君安', exchange: 'SH', secid: '1.601211' },
  { symbol: '601688.SH', code: '601688', name: '华泰证券', exchange: 'SH', secid: '1.601688' },
  { symbol: '000776.SZ', code: '000776', name: '广发证券', exchange: 'SZ', secid: '0.000776' },
  { symbol: '601601.SH', code: '601601', name: '中国太保', exchange: 'SH', secid: '1.601601' },
  { symbol: '601336.SH', code: '601336', name: '新华保险', exchange: 'SH', secid: '1.601336' },
  { symbol: '000568.SZ', code: '000568', name: '泸州老窖', exchange: 'SZ', secid: '0.000568' },
  { symbol: '600809.SH', code: '600809', name: '山西汾酒', exchange: 'SH', secid: '1.600809' },
  { symbol: '603369.SH', code: '603369', name: '今世缘', exchange: 'SH', secid: '1.603369' },
  { symbol: '600887.SH', code: '600887', name: '伊利股份', exchange: 'SH', secid: '1.600887' },
] as const;

const SAMPLE_UNIVERSE_MEMBERS: StrategyUniverseMember[] = SAMPLE_UNIVERSE_MEMBER_SEEDS.map(
  (member) => ({
    ...member,
    concepts: [],
    sectorTags: inferSampleSectorTags(member.name),
    assetType: 'stock',
    currency: 'CNY',
    timezone: 'Asia/Shanghai',
    provider: 'eastmoney',
    securityStatus: 'active',
    role: 'member',
    weight: Number((1 / SAMPLE_UNIVERSE_MEMBER_SEEDS.length).toFixed(8)),
    rowCount: 0,
    latestClose: null,
    latestChangePct: null,
    latestAmount: null,
    latestTurnover: null,
    strength20dPct: null,
    strength60dPct: null,
    ma20: null,
    ma60: null,
    trendStatus: 'insufficient',
    avgAmount20d: null,
    avgVolume20d: null,
    avgTurnover20d: null,
    tradeStatus: null,
    isSt: null,
    limitUp: null,
    limitDown: null,
    peTtm: null,
    pbMrq: null,
    psTtm: null,
    pcfNcfTtm: null,
    dataStatus: 'missing',
  })
);

const FALLBACK_RESEARCH_STATE: StrategyResearchState = {
  primaryUniverseId: SAMPLE_UNIVERSE_ID,
  source: 'fallback',
  universes: [
    {
      id: SAMPLE_UNIVERSE_ID,
      name: 'A 股股票池',
      description: '用于策略平台打通本地行情覆盖、数据质量检查和回测链路的默认股票池。',
      status: 'active',
      source: 'seed',
      tags: ['A股', '股票', '东方财富', '策略回测'],
      defaultTimeframe: 'daily',
      defaultAdjustment: 'qfq',
      provider: 'eastmoney',
      members: SAMPLE_UNIVERSE_MEMBERS,
      memberCount: SAMPLE_UNIVERSE_MEMBERS.length,
      stockCount: SAMPLE_UNIVERSE_MEMBERS.length,
      etfCount: 0,
      indexCount: 0,
      fundCount: 0,
      readyCount: 0,
      barCount: 0,
      latestTs: null,
    },
    {
      id: 'etf-index-pool',
      name: 'ETF/指数池',
      description: '用于指数代理、ETF 轮动和跨资产对比的独立池。',
      status: 'active',
      source: 'seed',
      tags: ['ETF', '指数', '东方财富', '轮动'],
      defaultTimeframe: 'daily',
      defaultAdjustment: 'qfq',
      provider: 'eastmoney',
      members: [],
      memberCount: 0,
      stockCount: 0,
      etfCount: 0,
      indexCount: 0,
      fundCount: 0,
      readyCount: 0,
      barCount: 0,
      latestTs: null,
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
      'GET /api/v1/research/universes/summary',
      'GET /api/v1/research/universes/{id}/members',
      'POST /api/v1/ingestion/eastmoney/history',
      'POST /api/v1/ingestion/akshare/history',
      'POST /api/v1/ingestion/baostock/history',
    ],
    guardrails: [
      '默认保留近 5 年前复权日线，保证策略回测读取同一价格口径。',
      '每次同步按 symbol/timeframe/adjustment/ts 幂等 upsert。',
      '历史样本不因后续补数被删除，回测窗口由查询条件决定。',
      '回测必须读取本地 TimescaleDB，避免外部行情变化影响复现。',
    ],
  },
};

const STRATEGY_BACKTEST_DEPENDENCIES = [
  'GET /api/v1/research/universes/{id}/members',
  'GET /api/v1/research/bars/{symbol}',
  'GET /api/v1/indicators/technical/{symbol}',
  'GET /api/v1/backtests/strategies/{strategy_id}/{symbol}',
];
const STRATEGY_COMMON_RISK_CONTROLS = [
  '单标的 long/flat，全仓或空仓，不使用杠杆',
  '所有扫描必须展示最大回撤、胜率、交易次数和夏普',
  '不把回测收益当作预测结论，必须说明滑点、停牌、冲击成本和分红再投资限制',
];
const STRATEGY_COMMON_LIMITATIONS = [
  '当前策略为日线级单标的回测，组合轮动、资金容量和撮合细节后续单独建模。',
  '交易按收盘价切换仓位，暂未建模盘中触发、涨跌停无法成交和税费差异。',
];

const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: 'ma-crossover-single-asset',
    name: '均线交叉趋势',
    family: '趋势跟随',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '用快慢均线交叉刻画趋势切换，适合先验证趋势品种和宽基 ETF 的可交易性。',
    defaultSymbols: ['002156', '510300', '601398'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'ma_crossover',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'fast_window', label: '快线窗口', value: 20, unit: '日', description: '短期趋势确认线。' },
      { key: 'slow_window', label: '慢线窗口', value: 60, unit: '日', description: '中期趋势过滤线。' },
      { key: 'fee_bps', label: '单边费用', value: 5, unit: 'bps', description: '买入和卖出分别扣减。' },
    ],
    parameterScans: [{
      id: 'ma-window-grid',
      name: '快慢均线鲁棒性扫描',
      status: 'available',
      objective: '验证趋势窗口是否对收益、回撤和换手过度敏感。',
      grid: [
        { key: 'fast_window', values: [10, 20, 30], unit: '日' },
        { key: 'slow_window', values: [50, 60, 90], unit: '日' },
        { key: 'fee_bps', values: [3, 5, 10], unit: 'bps' },
      ],
      metrics: ['总收益', '最大回撤', '夏普', '交易次数', '胜率'],
      guardrails: ['fast_window 必须小于 slow_window', '费用变化纳入对比', '拒绝只看收益最高参数'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v2.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['接入通用策略回测端点', '默认回测窗口扩展到近 5 年'],
      parameterSnapshot: { fast_window: 20, slow_window: 60, fee_bps: 5 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['总收益', '基准收益', '最大回撤', '夏普', '胜率', '交易次数', '暴露时间'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 002156 执行 20/60 均线交叉趋势回测，比较收益、回撤、夏普、交易次数和参数鲁棒性。',
  },
  {
    id: 'donchian-breakout',
    name: 'Donchian 通道突破',
    family: '突破交易',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '突破过去 N 日高点进场、跌破短通道低点退出，适合检验趋势延续和假突破成本。',
    defaultSymbols: ['002156', '300750', '510300'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'donchian_breakout',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'breakout_window', label: '突破通道', value: 20, unit: '日', description: '以前高作为入场阈值。' },
      { key: 'exit_window', label: '退出通道', value: 10, unit: '日', description: '以短低点作为失效线。' },
      { key: 'fee_bps', label: '单边费用', value: 5, unit: 'bps', description: '控制高换手策略成本。' },
    ],
    parameterScans: [{
      id: 'donchian-window-grid',
      name: '通道长度扫描',
      status: 'available',
      objective: '观察突破窗口和退出窗口对信号质量、持仓时长和回撤的影响。',
      grid: [
        { key: 'breakout_window', values: [20, 40, 60], unit: '日' },
        { key: 'exit_window', values: [10, 20, 30], unit: '日' },
        { key: 'fee_bps', values: [3, 5, 10], unit: 'bps' },
      ],
      metrics: ['总收益', '最大回撤', '夏普', '交易次数'],
      guardrails: ['退出窗口不能长于突破窗口', '检查信号过密导致的费用侵蚀', '必须展示亏损交易占比'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增 Donchian 通道实际回测引擎'],
      parameterSnapshot: { breakout_window: 20, exit_window: 10, fee_bps: 5 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['突破后收益', '最大回撤', '夏普', '平均持仓天数', '交易次数'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '用 Donchian 20/10 通道回测 002156，重点判断假突破、回撤和交易频率。',
  },
  {
    id: 'turtle-trend-following',
    name: '海龟中期趋势',
    family: '趋势跟随',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '55 日突破、20 日退出的中期趋势策略，用来评估强趋势资产的持有价值。',
    defaultSymbols: ['510300', '600519', '300750'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'turtle_trend',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'breakout_window', label: '入场通道', value: 55, unit: '日', description: '中期新高触发。' },
      { key: 'exit_window', label: '退出通道', value: 20, unit: '日', description: '趋势破坏退出。' },
      { key: 'fee_bps', label: '单边费用', value: 5, unit: 'bps', description: '长期持仓仍需扣减。' },
    ],
    parameterScans: [{
      id: 'turtle-window-grid',
      name: '海龟窗口扫描',
      status: 'available',
      objective: '比较 40/55/80 日突破和 10/20/30 日退出的趋势捕获能力。',
      grid: [
        { key: 'breakout_window', values: [40, 55, 80], unit: '日' },
        { key: 'exit_window', values: [10, 20, 30], unit: '日' },
        { key: 'fee_bps', values: [3, 5, 10], unit: 'bps' },
      ],
      metrics: ['总收益', '最大回撤', '夏普', '暴露时间'],
      guardrails: ['重点看长时间空仓风险', '不允许只用单一年份判断策略', '必须对比基准买入持有'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增海龟趋势参数口径和回测端点'],
      parameterSnapshot: { breakout_window: 55, exit_window: 20, fee_bps: 5 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['趋势捕获收益', '最大回撤', '空仓比例', '交易次数', '夏普'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 510300 执行 55/20 海龟趋势回测，说明中期突破相比买入持有是否改善回撤。',
  },
  {
    id: 'volume-price-breakout',
    name: '放量价格突破',
    family: '量价策略',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '要求价格突破同时成交量超过均量倍数，过滤无量假突破，适合个股题材行情验证。',
    defaultSymbols: ['002156', '002555', '002624'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'volume_price_breakout',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'breakout_window', label: '突破通道', value: 20, unit: '日', description: '价格突破观察窗口。' },
      { key: 'volume_ratio', label: '放量倍数', value: 1.4, description: '相对过去均量的确认阈值。' },
      { key: 'exit_window', label: '退出通道', value: 10, unit: '日', description: '跌破短低点退出。' },
    ],
    parameterScans: [{
      id: 'volume-price-grid',
      name: '量价确认扫描',
      status: 'available',
      objective: '验证放量阈值是否能减少假突破并改善回撤收益比。',
      grid: [
        { key: 'breakout_window', values: [15, 20, 30], unit: '日' },
        { key: 'volume_ratio', values: [1.2, 1.4, 1.8] },
        { key: 'exit_window', values: [8, 10, 15], unit: '日' },
      ],
      metrics: ['总收益', '最大回撤', '夏普', '信号数量'],
      guardrails: ['成交量缺失样本必须降级', '观察高换手和费用侵蚀', '避免只筛选热门股'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['接入成交量过滤的突破回测'],
      parameterSnapshot: { breakout_window: 20, volume_ratio: 1.4, exit_window: 10 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['突破胜率', '交易次数', '最大回撤', '夏普', '费用敏感性'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '回测 002156 的放量突破策略，比较 1.2/1.4/1.8 倍量能阈值对假突破的过滤效果。',
  },
  {
    id: 'atr-trailing-breakout',
    name: 'ATR 突破追踪',
    family: '波动率风控',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '突破入场后用 ATR 追踪止损，关注趋势跟随中的利润保护和波动适配。',
    defaultSymbols: ['002156', '600519', '510300'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'atr_trailing_breakout',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'breakout_window', label: '突破窗口', value: 20, unit: '日', description: '新高入场窗口。' },
      { key: 'atr_window', label: 'ATR 窗口', value: 14, unit: '日', description: '波动率估计窗口。' },
      { key: 'atr_multiplier', label: 'ATR 倍数', value: 2.5, description: '追踪止损距离。' },
    ],
    parameterScans: [{
      id: 'atr-trailing-grid',
      name: 'ATR 追踪参数扫描',
      status: 'available',
      objective: '比较止损距离对趋势持有、回撤和过早离场的影响。',
      grid: [
        { key: 'breakout_window', values: [20, 40, 60], unit: '日' },
        { key: 'atr_window', values: [10, 14, 20], unit: '日' },
        { key: 'atr_multiplier', values: [2, 2.5, 3] },
      ],
      metrics: ['总收益', '最大回撤', '夏普', '暴露时间'],
      guardrails: ['必须展示止损过紧导致的交易次数', '检查极端波动期表现', '不得忽略费用'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增 ATR 追踪止损回测'],
      parameterSnapshot: { breakout_window: 20, atr_window: 14, atr_multiplier: 2.5 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['最大回撤', '止损频率', '收益回撤比', '夏普', '暴露时间'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 002156 执行 ATR 突破追踪策略，重点解释止损倍数对回撤和收益的影响。',
  },
  {
    id: 'rsi-trend-reversion',
    name: 'RSI 趋势回撤反转',
    family: '均值回归',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '在中期趋势向上时买入 RSI 回撤，反弹到阈值或跌破趋势线退出。',
    defaultSymbols: ['601398', '600519', '002156'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'rsi_reversion',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'rsi_window', label: 'RSI 窗口', value: 14, unit: '日', description: '衡量短期超卖。' },
      { key: 'entry_rsi', label: '入场 RSI', value: 35, description: '低于阈值视作回撤。' },
      { key: 'exit_rsi', label: '退出 RSI', value: 55, description: '反弹到阈值止盈。' },
    ],
    parameterScans: [{
      id: 'rsi-reversion-grid',
      name: 'RSI 阈值扫描',
      status: 'available',
      objective: '验证超卖买入和反弹退出阈值对胜率、回撤和交易频率的影响。',
      grid: [
        { key: 'rsi_window', values: [10, 14, 20], unit: '日' },
        { key: 'entry_rsi', values: [30, 35, 40] },
        { key: 'exit_rsi', values: [50, 55, 60] },
      ],
      metrics: ['胜率', '最大回撤', '交易次数', '总收益'],
      guardrails: ['只在趋势过滤条件下入场', '检查连续下跌行情失效', '必须展示亏损交易'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增 RSI 趋势回撤回测'],
      parameterSnapshot: { rsi_window: 14, entry_rsi: 35, exit_rsi: 55 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['胜率', '平均交易收益', '最大回撤', '交易次数', '夏普'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '回测 601398 的 RSI 趋势回撤策略，判断低波动金融股是否适合超卖反弹交易。',
  },
  {
    id: 'bollinger-mean-reversion',
    name: '布林带均值回归',
    family: '均值回归',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '价格跌破下轨时买入，回归中轨附近退出，用于评估震荡品种的反转机会。',
    defaultSymbols: ['601398', '510300', '600519'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'bollinger_reversion',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'lookback_window', label: '布林窗口', value: 20, unit: '日', description: '均值和标准差估计窗口。' },
      { key: 'entry_z', label: '入场 Z 值', value: 2, description: '低于负 Z 值触发。' },
      { key: 'exit_z', label: '退出 Z 值', value: 0, description: '回到中轨附近退出。' },
    ],
    parameterScans: [{
      id: 'bollinger-grid',
      name: '布林参数扫描',
      status: 'available',
      objective: '比较均值窗口和入场偏离倍数对反转胜率与回撤的影响。',
      grid: [
        { key: 'lookback_window', values: [20, 30, 40], unit: '日' },
        { key: 'entry_z', values: [1.5, 2, 2.5] },
        { key: 'exit_z', values: [-0.2, 0, 0.3] },
      ],
      metrics: ['胜率', '最大回撤', '交易次数', '夏普'],
      guardrails: ['必须警惕趋势下跌中的接刀风险', '观察连续亏损', '比较不同波动窗口'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增布林带均值回归回测'],
      parameterSnapshot: { lookback_window: 20, entry_z: 2, exit_z: 0 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['胜率', '最大回撤', '连续亏损', '平均持仓天数', '夏普'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 510300 回测布林带均值回归策略，重点分析震荡和趋势阶段的表现差异。',
  },
  {
    id: 'momentum-trend-filter',
    name: '动量趋势过滤',
    family: '强弱动量',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '要求中期收益为正且价格在长期均线上方，适合检验强者恒强逻辑。',
    defaultSymbols: ['002156', '300750', '600519'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'momentum_trend',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'momentum_window', label: '动量窗口', value: 60, unit: '日', description: '衡量区间强弱。' },
      { key: 'trend_window', label: '趋势过滤', value: 120, unit: '日', description: '长期均线过滤。' },
      { key: 'min_momentum_pct', label: '最低动量', value: 8, unit: '%', description: '入场所需区间收益。' },
    ],
    parameterScans: [{
      id: 'momentum-trend-grid',
      name: '动量阈值扫描',
      status: 'available',
      objective: '比较动量窗口和最低动量阈值对趋势品种筛选效果的影响。',
      grid: [
        { key: 'momentum_window', values: [40, 60, 90], unit: '日' },
        { key: 'trend_window', values: [90, 120, 180], unit: '日' },
        { key: 'min_momentum_pct', values: [5, 8, 12], unit: '%' },
      ],
      metrics: ['总收益', '最大回撤', '暴露时间', '夏普'],
      guardrails: ['必须对比买入持有', '检查追高后的回撤', '观察空仓时间过长问题'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增动量趋势过滤回测'],
      parameterSnapshot: { momentum_window: 60, trend_window: 120, min_momentum_pct: 8 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['强弱收益', '最大回撤', '暴露时间', '夏普', '交易次数'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 002156 执行 60 日动量 + 120 日趋势过滤回测，比较不同动量阈值。',
  },
  {
    id: 'low-volatility-trend',
    name: '低波动趋势持有',
    family: '波动率风控',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '只在价格高于趋势均线且年化波动较低时持有，用于降低趋势策略中的噪声交易。',
    defaultSymbols: ['601398', '510300', '600519'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'low_volatility_trend',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'trend_window', label: '趋势窗口', value: 60, unit: '日', description: '持有趋势过滤。' },
      { key: 'vol_window', label: '波动窗口', value: 20, unit: '日', description: '年化波动估计。' },
      { key: 'max_volatility_pct', label: '最高波动', value: 35, unit: '%', description: '入场波动上限。' },
    ],
    parameterScans: [{
      id: 'low-vol-trend-grid',
      name: '低波趋势扫描',
      status: 'available',
      objective: '验证波动率上限是否能降低回撤，同时保留趋势收益。',
      grid: [
        { key: 'trend_window', values: [40, 60, 90], unit: '日' },
        { key: 'vol_window', values: [15, 20, 30], unit: '日' },
        { key: 'max_volatility_pct', values: [25, 35, 45], unit: '%' },
      ],
      metrics: ['最大回撤', '夏普', '暴露时间', '总收益'],
      guardrails: ['检查过度空仓', '波动阈值不可只服务单一历史区间', '必须展示基准收益'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增低波动趋势持有回测'],
      parameterSnapshot: { trend_window: 60, vol_window: 20, max_volatility_pct: 35 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['夏普', '最大回撤', '暴露时间', '波动过滤效果', '总收益'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 601398 回测低波动趋势持有策略，评估它是否能改善金融股的收益回撤比。',
  },
  {
    id: 'ma-pullback-reclaim',
    name: '均线回踩再启动',
    family: '趋势回撤',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '在长期趋势上行时等待回踩短均线后重新站上，捕捉趋势中的二次启动。',
    defaultSymbols: ['002156', '002555', '600519'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'ma_pullback_reclaim',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'pullback_window', label: '回踩均线', value: 20, unit: '日', description: '短线回踩和重新站上。' },
      { key: 'trend_window', label: '趋势均线', value: 60, unit: '日', description: '长期趋势过滤。' },
      { key: 'stop_loss_pct', label: '止损阈值', value: 8, unit: '%', description: '单笔最大容忍亏损。' },
    ],
    parameterScans: [{
      id: 'pullback-reclaim-grid',
      name: '回踩再启动扫描',
      status: 'available',
      objective: '比较回踩均线和趋势均线组合对二次启动交易的影响。',
      grid: [
        { key: 'pullback_window', values: [10, 20, 30], unit: '日' },
        { key: 'trend_window', values: [50, 60, 90], unit: '日' },
        { key: 'stop_loss_pct', values: [6, 8, 10], unit: '%' },
      ],
      metrics: ['胜率', '最大回撤', '交易次数', '平均收益'],
      guardrails: ['必须观察趋势破坏后的止损', '防止震荡市场反复交易', '费用纳入计算'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增均线回踩再启动回测'],
      parameterSnapshot: { pullback_window: 20, trend_window: 60, stop_loss_pct: 8 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['胜率', '最大回撤', '单笔亏损', '交易次数', '夏普'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 002156 回测均线回踩再启动策略，解释它和普通突破策略的差异。',
  },
  {
    id: 'gap-reversal',
    name: '跳空回补反转',
    family: '事件型反转',
    status: 'ready',
    capabilityId: 'backtest_review',
    description: '大幅低开但日内收复时买入，持有有限天数，检验恐慌低开后的短线回补。',
    defaultSymbols: ['002555', '002624', '002156'],
    timeframe: '日线 · 近 5 年',
    backtestStrategyId: 'gap_reversal',
    backtestLimit: 1260,
    dataDependencies: STRATEGY_BACKTEST_DEPENDENCIES,
    parameterSchema: [
      { key: 'gap_down_pct', label: '低开阈值', value: 3, unit: '%', description: '相对前收盘低开幅度。' },
      { key: 'max_holding_days', label: '最长持有', value: 5, unit: '日', description: '短线反转最大等待时间。' },
      { key: 'stop_loss_pct', label: '止损阈值', value: 6, unit: '%', description: '反转失败退出。' },
    ],
    parameterScans: [{
      id: 'gap-reversal-grid',
      name: '跳空回补扫描',
      status: 'available',
      objective: '验证低开幅度、最长持有天数和止损阈值对短线回补交易的影响。',
      grid: [
        { key: 'gap_down_pct', values: [2, 3, 4], unit: '%' },
        { key: 'max_holding_days', values: [3, 5, 8], unit: '日' },
        { key: 'stop_loss_pct', values: [4, 6, 8], unit: '%' },
      ],
      metrics: ['胜率', '平均收益', '最大回撤', '交易次数'],
      guardrails: ['只用于日线信号研究，不模拟盘中成交', '检查样本数量是否足够', '必须展示失败交易'],
      sampleSize: 27,
    }],
    versions: [{
      version: 'v1.0',
      status: 'active',
      updatedAt: '2026-05-29T00:00:00.000Z',
      changes: ['新增跳空回补反转回测'],
      parameterSnapshot: { gap_down_pct: 3, max_holding_days: 5, stop_loss_pct: 6 },
    }],
    backtestArchives: [],
    riskControls: STRATEGY_COMMON_RISK_CONTROLS,
    evaluationMetrics: ['胜率', '平均收益', '最大回撤', '交易次数', '持有天数'],
    limitations: STRATEGY_COMMON_LIMITATIONS,
    promptSeed: '对 002555 回测跳空回补反转策略，确认样本数量、胜率和单笔亏损是否可接受。',
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
  strategyId: string;
  limit?: number;
}): Promise<Record<string, unknown>> {
  const query = new URLSearchParams({
    fee_bps: String(params.parameters.fee_bps ?? 5),
    period: 'daily',
    adjustment: 'qfq',
    limit: String(params.limit ?? 1260),
  });
  for (const [key, value] of Object.entries(params.parameters)) {
    query.set(key, String(value));
  }
  const response = await fetch(
    `${MARKET_API_BASE_URL}/api/v1/backtests/strategies/${encodeURIComponent(params.strategyId)}/${encodeURIComponent(params.symbol)}?${query.toString()}`,
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
  return Array.isArray(value)
    ? value
      .map(item => String(item).trim())
      .filter(item => item && !['-', '--', '无', '暂无'].includes(item))
    : [];
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (value === 1) return true;
    if (value === 0) return false;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['1', 'true', 't', 'yes', 'y'].includes(normalized)) return true;
    if (['0', 'false', 'f', 'no', 'n'].includes(normalized)) return false;
  }
  return null;
}

function compactUniqueStrings(values: Array<string | null | undefined>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  values.forEach((value) => {
    const text = value?.trim();
    if (!text || seen.has(text)) return;
    seen.add(text);
    result.push(text);
  });
  return result;
}

function inferSampleSectorTags(name?: string | null): string[] {
  const value = name ?? '';
  if (/银行/.test(value)) return ['银行'];
  if (/证券|国泰君安|华泰|广发/.test(value)) return ['证券'];
  if (/保险|中国平安|太保/.test(value)) return ['保险'];
  if (/茅台|五粮液|泸州老窖|汾酒|今世缘/.test(value)) return ['白酒'];
  if (/通富|圣邦|紫光|华润微|中芯|韦尔|兆易|卓胜|汇顶/.test(value)) return ['半导体'];
  if (/三七|完美世界|世纪华通|掌趣|昆仑万维/.test(value)) return ['游戏'];
  if (/宁德|比亚迪|电池|先导智能/.test(value)) return ['新能源车'];
  if (/美的|格力|家电|三花/.test(value)) return ['家电'];
  if (/黄金/.test(value)) return ['黄金珠宝'];
  if (/联通|中兴|通信|移远|广和通/.test(value)) return ['通信服务'];
  if (/石油|石化|石化|荣盛石化|东方盛虹/.test(value)) return ['石油石化'];
  if (/医药|恒瑞/.test(value)) return ['医药'];
  if (/电力|长江电力/.test(value)) return ['电力'];
  if (/光伏|隆基/.test(value)) return ['光伏'];
  return [];
}

function dataStatus(value: unknown): StrategyUniverseMember['dataStatus'] {
  return value === 'ready' || value === 'stale' || value === 'missing' ? value : 'missing';
}

function trendStatus(value: unknown): StrategyUniverseMember['trendStatus'] {
  return value === 'bullish' || value === 'bearish' || value === 'sideways' || value === 'insufficient'
    ? value
    : 'insufficient';
}

function mapResearchMember(value: unknown): StrategyUniverseMember {
  const record = asRecord(value);
  const concepts = asStringArray(record.concepts);
  const sectorTags = asStringArray(record.sector_tags);
  const industry = typeof record.industry === 'string' ? record.industry : null;
  const region = typeof record.region === 'string' ? record.region : null;
  const sectorHint = typeof record.sector_hint === 'string' ? record.sector_hint : null;
  const name = typeof record.name === 'string' ? record.name : null;
  return {
    symbol: asString(record.symbol),
    code: asString(record.code),
    name,
    industry,
    region,
    concepts,
    sectorHint,
    sectorTags: sectorTags.length
      ? sectorTags
      : compactUniqueStrings([industry, ...concepts.slice(0, 3), region, ...inferSampleSectorTags(name)]),
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
    latestClose: asNumber(record.latest_close),
    latestChangePct: asNumber(record.latest_change_pct),
    latestAmount: asNumber(record.latest_amount),
    latestTurnover: asNumber(record.latest_turnover),
    strength20dPct: asNumber(record.strength_20d_pct),
    strength60dPct: asNumber(record.strength_60d_pct),
    ma20: asNumber(record.ma20),
    ma60: asNumber(record.ma60),
    trendStatus: trendStatus(record.trend_status),
    avgAmount20d: asNumber(record.avg_amount_20d),
    avgVolume20d: asNumber(record.avg_volume_20d),
    avgTurnover20d: asNumber(record.avg_turnover_20d),
    tradeStatus: typeof record.trade_status === 'string' ? record.trade_status : null,
    isSt: asBoolean(record.is_st),
    limitUp: asBoolean(record.limit_up),
    limitDown: asBoolean(record.limit_down),
    peTtm: asNumber(record.pe_ttm),
    pbMrq: asNumber(record.pb_mrq),
    psTtm: asNumber(record.ps_ttm),
    pcfNcfTtm: asNumber(record.pcf_ncf_ttm),
    dataStatus: dataStatus(record.data_status),
  };
}

function mapResearchUniverse(value: unknown): StrategyUniverse {
  const record = asRecord(value);
  const members = Array.isArray(record.members) ? record.members.map(mapResearchMember) : [];
  return {
    id: asString(record.id, SAMPLE_UNIVERSE_ID),
    name: asString(record.name, 'A 股股票池'),
    description: typeof record.description === 'string' ? record.description : null,
    status: asString(record.status, 'active'),
    source: asString(record.source, 'seed'),
    tags: asStringArray(record.tags),
    defaultTimeframe: asString(record.default_timeframe, 'daily'),
    defaultAdjustment: asString(record.default_adjustment, 'qfq'),
    provider: asString(record.provider, 'eastmoney'),
    members,
    memberCount: asNumber(record.member_count) ?? members.length,
    stockCount: asNumber(record.stock_count) ?? 0,
    etfCount: asNumber(record.etf_count) ?? 0,
    indexCount: asNumber(record.index_count) ?? 0,
    fundCount: asNumber(record.fund_count) ?? 0,
    readyCount: asNumber(record.ready_count) ?? 0,
    barCount: asNumber(record.bar_count) ?? 0,
    latestTs: typeof record.latest_ts === 'string' ? record.latest_ts : null,
  };
}

function mapResearchUniverseMembersPage(
  value: unknown,
  fallbackUniverseId: string,
  fallbackPage: number,
  fallbackPageSize: number
): StrategyUniverseMembersPage {
  const record = asRecord(value);
  const members = Array.isArray(record.members) ? record.members.map(mapResearchMember) : [];
  const total = asNumber(record.total) ?? members.length;
  const pageSize = asNumber(record.page_size) ?? fallbackPageSize;
  return {
    universeId: asString(record.universe_id, fallbackUniverseId),
    page: asNumber(record.page) ?? fallbackPage,
    pageSize,
    total,
    totalPages: asNumber(record.total_pages) ?? Math.max(1, Math.ceil(total / pageSize)),
    keyword: typeof record.keyword === 'string' ? record.keyword : null,
    members,
    fetchedAt: asString(record.fetched_at, new Date().toISOString()),
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
    previousClose: asNumber(record.previous_close),
    volume: asNumber(record.volume) ?? 0,
    amount: asNumber(record.amount),
    amplitude: asNumber(record.amplitude),
    changePercent: asNumber(record.change_percent),
    changeAmount: asNumber(record.change_amount),
    turnover: asNumber(record.turnover),
    tradeStatus: typeof record.trade_status === 'string' ? record.trade_status : null,
    isSt: asBoolean(record.is_st),
    limitUp: asBoolean(record.limit_up),
    limitDown: asBoolean(record.limit_down),
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

function mapIngestionJob(value: unknown): StrategyIngestionJob {
  const record = asRecord(value);
  const metadata = asRecord(record.metadata);
  return {
    id: asString(record.id),
    universeId: typeof record.universe_id === 'string' ? record.universe_id : null,
    provider: asString(record.provider, 'unknown'),
    timeframe: asString(record.timeframe, 'daily'),
    adjustment: asString(record.adjustment, 'qfq'),
    status: asString(record.status, 'unknown'),
    totalSymbols: asNumber(record.total_symbols) ?? 0,
    completedSymbols: asNumber(record.completed_symbols) ?? 0,
    failedSymbols: asNumber(record.failed_symbols) ?? 0,
    rowsReceived: asNumber(record.rows_received) ?? 0,
    rowsUpserted: asNumber(record.rows_upserted) ?? 0,
    error: typeof record.error === 'string' ? record.error : null,
    metadata,
    batchOffset: asNumber(metadata.batch_offset),
    batchSize: asNumber(metadata.batch_size),
    nextOffset: asNumber(metadata.next_offset),
    universeTotalSymbols: asNumber(metadata.universe_total_symbols),
    startedAt: typeof record.started_at === 'string' ? record.started_at : null,
    completedAt: typeof record.completed_at === 'string' ? record.completed_at : null,
    createdAt: asString(record.created_at, new Date().toISOString()),
    updatedAt: asString(record.updated_at, new Date().toISOString()),
  };
}

function mapIngestionJobsResponse(value: unknown): StrategyIngestionJobsResponse {
  const record = asRecord(value);
  return {
    jobs: Array.isArray(record.jobs) ? record.jobs.map(mapIngestionJob) : [],
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

export async function getStrategyUniverseMembersPage(params: {
  universeId?: string;
  page?: number;
  pageSize?: number;
  keyword?: string;
} = {}): Promise<StrategyUniverseMembersPage> {
  const universeId = params.universeId || SAMPLE_UNIVERSE_ID;
  const page = Math.max(1, params.page ?? 1);
  const pageSize = Math.max(1, Math.min(params.pageSize ?? 10, 100));
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const keyword = params.keyword?.trim();
  if (keyword) query.set('keyword', keyword);
  const payload = await fetchMarketApiJson<unknown>(
    `/api/v1/research/universes/${encodeURIComponent(universeId)}/members?${query.toString()}`
  );
  return mapResearchUniverseMembersPage(payload, universeId, page, pageSize);
}

export async function getStrategyIngestionJobs(params: {
  universeId?: string;
  limit?: number;
} = {}): Promise<StrategyIngestionJobsResponse> {
  const query = new URLSearchParams({
    limit: String(Math.max(1, Math.min(params.limit ?? 20, 100))),
  });
  const universeId = params.universeId?.trim();
  if (universeId) query.set('universe_id', universeId);
  const payload = await fetchMarketApiJson<unknown>(`/api/v1/ingestion/jobs?${query.toString()}`);
  return mapIngestionJobsResponse(payload);
}

async function getStrategyResearchState(): Promise<StrategyResearchState> {
  try {
    const universesPayload = asRecord(
      await fetchMarketApiJson<unknown>('/api/v1/research/universes/summary')
    );
    const universes = Array.isArray(universesPayload.universes)
      ? universesPayload.universes.map(mapResearchUniverse)
      : [];
    const primaryUniverse =
      universes.find((universe) => universe.id === SAMPLE_UNIVERSE_ID) ??
      universes.find((universe) => universe.stockCount > 0) ??
      universes[0] ??
      FALLBACK_RESEARCH_STATE.universes[0];
    const initialMembersPage = await getStrategyUniverseMembersPage({
      universeId: primaryUniverse.id,
      page: 1,
      pageSize: 10,
    });
    const hydratedUniverses = universes.map((universe) => (
      universe.id === primaryUniverse.id
        ? {
            ...universe,
            members: initialMembersPage.members,
            memberCount: initialMembersPage.total || universe.memberCount,
          }
        : { ...universe, members: [] }
    ));
    const coverage = initialMembersPage.members.map((member): StrategyDataCoverageItem => ({
      symbol: member.symbol,
      name: member.name,
      timeframe: primaryUniverse.defaultTimeframe,
      adjustment: primaryUniverse.defaultAdjustment,
      provider: member.dataProvider ?? primaryUniverse.provider,
      firstTs: member.firstTs ?? null,
      lastTs: member.lastTs ?? null,
      rowCount: member.rowCount,
      dataStatus: member.dataStatus,
    }));

    return {
      ...FALLBACK_RESEARCH_STATE,
      primaryUniverseId: primaryUniverse.id,
      source: 'market-api',
      universes: hydratedUniverses.length ? hydratedUniverses : FALLBACK_RESEARCH_STATE.universes,
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
  const projects = serializeProjects(await getAllProjects().catch(() => []));
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
    (sum, universe) => sum + universe.memberCount,
    0
  );
  const syncedSymbols = research.universes.reduce((sum, universe) => sum + universe.readyCount, 0);
  const syncedBars = research.universes.reduce((sum, universe) => sum + universe.barCount, 0);

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

export async function ingestStrategyUniverseHistoryBatch(params: {
  universeId?: string;
  offset?: number;
  batchSize?: number;
  limit?: number;
  lookbackYears?: number;
  period?: string;
  adjustment?: string;
} = {}): Promise<StrategyHistoryIngestionResult> {
  const body = {
    universe_id: params.universeId || SAMPLE_UNIVERSE_ID,
    offset: Math.max(0, params.offset ?? 0),
    batch_size: Math.max(1, Math.min(params.batchSize ?? 25, 200)),
    period: params.period || 'daily',
    adjustment: params.adjustment || 'qfq',
    limit: params.limit ?? FALLBACK_RESEARCH_STATE.ingestionPlan.suggestedLimit,
    lookback_years: params.lookbackYears ?? FALLBACK_RESEARCH_STATE.ingestionPlan.lookbackYears,
    request_delay_seconds: 1.2,
  };
  const response = await fetch(`${MARKET_API_BASE_URL}/api/v1/ingestion/baostock/history/batch`, {
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
    if (template.backtestStrategyId === 'ma_crossover' && !isValidMaCrossoverParams(parameters)) {
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
      const backtest = await fetchBacktest({
        symbol,
        parameters,
        strategyId: template.backtestStrategyId,
        limit: template.backtestLimit,
      });
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
    source: `${MARKET_API_BASE_URL}/api/v1/backtests/strategies/${template.backtestStrategyId}/{symbol}`,
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
