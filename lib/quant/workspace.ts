import fs from 'fs/promises';
import path from 'path';
import { buildQuantProjectSettings, getQuantCapability } from '@/lib/quant/capabilities';

type QuantManifest = {
  schemaVersion?: number;
  projectId?: string;
  projectName?: string;
  quant?: {
    capabilityId?: string;
    agentType?: string;
    subAgentKey?: string;
    requiredSkills?: string[];
    dataEndpoints?: string[];
    expectedArtifacts?: string[];
    validationRules?: string[];
  };
};

type RunPlanStatus = 'pending' | 'planned';

export interface QuantRunPlan {
  schemaVersion: 1;
  runId: string;
  status: RunPlanStatus;
  capabilityId: string;
  question: string;
  symbols: string[];
  timeRange: string | null;
  dataRequirements: string[];
  analysisSteps: string[];
  visualization: {
    required: boolean;
    panels: string[];
  };
  expectedArtifacts: string[];
  validationRules: string[];
  createdAt: string;
  updatedAt: string;
}

export interface QuantWorkspaceEvent {
  event_type: string;
  stage: string;
  status: 'pending' | 'success' | 'warning' | 'error';
  summary: string;
  run_id?: string;
  artifact_path?: string;
  created_at?: string;
}

const SYMBOL_CODE_PATTERN = /\b(?:6|0|3|5)\d{5}\b/g;
const KNOWN_SYMBOLS: Array<{ keyword: string; symbol: string; name: string }> = [
  { keyword: '贵州茅台', symbol: '600519', name: '贵州茅台' },
  { keyword: '茅台', symbol: '600519', name: '贵州茅台' },
  { keyword: '宁德时代', symbol: '300750', name: '宁德时代' },
  { keyword: '平安银行', symbol: '000001', name: '平安银行' },
  { keyword: '招商银行', symbol: '600036', name: '招商银行' },
  { keyword: '沪深300ETF', symbol: '510300', name: '沪深300ETF' },
  { keyword: '沪深300 ETF', symbol: '510300', name: '沪深300ETF' },
  { keyword: '300ETF', symbol: '510300', name: '沪深300ETF' },
  { keyword: '沪深300', symbol: '000300', name: '沪深300' },
  { keyword: '沪深 300', symbol: '000300', name: '沪深300' },
  { keyword: '创业板指', symbol: '399006', name: '创业板指' },
  { keyword: '创业板指数', symbol: '399006', name: '创业板指' },
  { keyword: '中证500', symbol: '000905', name: '中证500' },
  { keyword: '中证 500', symbol: '000905', name: '中证500' },
  { keyword: '科创50', symbol: '000688', name: '科创50' },
  { keyword: '科创 50', symbol: '000688', name: '科创50' },
];

function quantDir(projectPath: string) {
  return path.join(projectPath, '.quantpilot');
}

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    const content = await fs.readFile(filePath, 'utf8');
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? (parsed as T) : null;
  } catch {
    return null;
  }
}

async function readManifest(projectPath: string): Promise<QuantManifest | null> {
  return readJsonFile<QuantManifest>(path.join(quantDir(projectPath), 'manifest.json'));
}

function inferSymbols(instruction: string): string[] {
  const codes = instruction.match(SYMBOL_CODE_PATTERN) ?? [];
  const known = KNOWN_SYMBOLS.filter((item) => instruction.includes(item.keyword)).map((item) => item.symbol);
  return Array.from(new Set([...codes, ...known]));
}

function inferTimeRange(instruction: string): string | null {
  const normalized = instruction.replace(/\s+/g, '');
  const dayMatch = normalized.match(/最近(\d+)(?:个)?(?:交易日|日|天)/);
  if (dayMatch?.[1]) return `最近 ${dayMatch[1]} 个交易日`;
  const yearMatch = normalized.match(/最近(\d+)?年/);
  if (yearMatch) return yearMatch[1] ? `最近 ${yearMatch[1]} 年` : '最近 1 年';
  const quarterMatch = normalized.match(/最近(\d+)?(?:个)?(?:报告期|季度)/);
  if (quarterMatch) return quarterMatch[1] ? `最近 ${quarterMatch[1]} 个报告期` : '最近多个报告期';
  return null;
}

function wantsVisualization(instruction: string): boolean {
  return /看板|可视化|图表|页面|dashboard|html/i.test(instruction);
}

function isQuantAnalysisTask(instruction: string): boolean {
  return /股票|个股|行情|走势|K线|K 线|财务|基本面|公告|指数|对比|量化|分析|回测/i.test(instruction);
}

function buildAnalysisSteps(capabilityId: string, hasSymbols: boolean): string[] {
  const common = [
    hasSymbols ? '确认输入标的并标准化证券代码。' : '使用 quant-symbol-resolver 解析用户问题中的证券名称或代码。',
    '查询 quant-data-registry，确认本地数据能力可用。',
  ];

  if (capabilityId === 'technical_analysis') {
    return [
      ...common,
      '获取实时行情和历史 K 线。',
      '计算区间涨跌、均线、波动率、最大回撤等技术指标。',
      '检查数据质量并写入 evidence/sources.json 与 evidence/data_quality.json。',
      '生成技术分析数据文件和可视化页面。',
      '验证页面、图表和数据来源。',
    ];
  }

  if (capabilityId === 'fundamental_analysis') {
    return [
      ...common,
      '获取实时行情、财务摘要和公告事件。',
      '分析营收、利润、ROE、毛利率、现金流质量和增长变化。',
      '检查数据质量并写入 evidence/sources.json 与 evidence/data_quality.json。',
      '生成基本面分析数据文件和可视化页面。',
      '验证页面、报告期、数据来源和缺失字段说明。',
    ];
  }

  return [
    ...common,
    '获取实时行情、历史 K 线、财务摘要和公告事件。',
    '综合分析价格趋势、量价、财务质量和事件风险。',
    '检查数据质量并写入 evidence/sources.json 与 evidence/data_quality.json。',
    '生成个股诊断数据文件和可视化页面。',
    '验证页面、图表、数据来源和更新时间。',
  ];
}

function buildVisualizationPanels(capabilityId: string): string[] {
  if (capabilityId === 'technical_analysis') {
    return ['实时行情卡片', 'K 线与均线', '成交量', '波动率与最大回撤', '最近 K 线表格'];
  }
  if (capabilityId === 'fundamental_analysis') {
    return ['实时行情卡片', '营收与利润趋势', 'ROE/毛利率趋势', '公告事件摘要', '报告期数据表'];
  }
  return ['实时行情卡片', 'K 线与成交量', '财务摘要', '公告事件时间线', '数据明细表'];
}

export async function ensureQuantWorkspace(projectPath: string) {
  await Promise.all([
    fs.mkdir(quantDir(projectPath), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'data_file', 'raw'), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'data_file', 'intermediate'), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'data_file', 'final'), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'evidence'), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'scripts'), { recursive: true }),
    fs.mkdir(path.join(projectPath, 'dashboard'), { recursive: true }),
  ]);
}

export async function appendQuantWorkspaceEvent(projectPath: string, event: QuantWorkspaceEvent) {
  await ensureQuantWorkspace(projectPath);
  const line = {
    ...event,
    created_at: event.created_at ?? new Date().toISOString(),
  };
  await fs.appendFile(path.join(quantDir(projectPath), 'events.jsonl'), `${JSON.stringify(line)}\n`, 'utf8');
}

export async function writeInitialRunPlan(params: {
  projectPath: string;
  instruction: string;
  requestId: string;
  capabilityId?: string | null;
}) {
  await ensureQuantWorkspace(params.projectPath);
  const manifest = await readManifest(params.projectPath);
  const manifestQuant = manifest?.quant;
  const capability = getQuantCapability(params.capabilityId ?? manifestQuant?.capabilityId);
  const quantSettings = buildQuantProjectSettings(capability.id);
  const now = new Date().toISOString();
  const symbols = inferSymbols(params.instruction);
  const dataRequirements = Array.from(
    new Set([
      ...capability.dataEndpoints,
      ...(manifestQuant?.dataEndpoints ?? []),
      ...(quantSettings.dataEndpoints ?? []),
    ])
  );
  const expectedArtifacts = Array.from(
    new Set([
      ...capability.expectedArtifacts,
      ...(manifestQuant?.expectedArtifacts ?? []),
      ...(quantSettings.expectedArtifacts ?? []),
    ])
  );
  const validationRules = Array.from(
    new Set([
      ...capability.validationRules,
      ...(manifestQuant?.validationRules ?? []),
      ...(quantSettings.validationRules ?? []),
    ])
  );

  const plan: QuantRunPlan = {
    schemaVersion: 1,
    runId: params.requestId,
    status: 'planned',
    capabilityId: capability.id,
    question: params.instruction,
    symbols,
    timeRange: inferTimeRange(params.instruction),
    dataRequirements,
    analysisSteps: buildAnalysisSteps(capability.id, symbols.length > 0),
    visualization: {
      required: wantsVisualization(params.instruction) || isQuantAnalysisTask(params.instruction),
      panels: buildVisualizationPanels(capability.id),
    },
    expectedArtifacts,
    validationRules,
    createdAt: now,
    updatedAt: now,
  };

  await fs.writeFile(
    path.join(quantDir(params.projectPath), 'run_plan.json'),
    `${JSON.stringify(plan, null, 2)}\n`,
    'utf8'
  );

  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'run_planned',
    stage: 'planning',
    status: 'success',
    run_id: params.requestId,
    artifact_path: '.quantpilot/run_plan.json',
    summary: `已生成${capability.name}计划，下一步将按计划解析标的、获取真实数据并生成可视化产物。`,
    created_at: now,
  });

  return plan;
}
