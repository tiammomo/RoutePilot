import {
  QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
  QUANT_GENERATION_QUEUE_RELATIVE_PATH,
  QUANT_GENERATION_STATE_RELATIVE_PATH,
  QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
} from '@/lib/quant/artifacts';

export type QuantCapabilityId =
  | 'stock_diagnosis'
  | 'technical_analysis'
  | 'fundamental_analysis'
  | 'asset_comparison'
  | 'sector_rotation'
  | 'strategy_research'
  | 'backtest_review'
  | 'portfolio_risk';

export type QuantCapabilityStatus = 'ready' | 'planned';

export type QuantCapabilityGroupId = 'core_analysis' | 'market_research' | 'strategy_risk';

export interface QuantCapabilityGroup {
  id: QuantCapabilityGroupId;
  name: string;
  description: string;
}

export interface QuantCapability {
  id: QuantCapabilityId;
  name: string;
  shortName: string;
  description: string;
  inputHint: string;
  tags: string[];
  status: QuantCapabilityStatus;
  groupId: QuantCapabilityGroupId;
  agentType: 'quant_analysis' | 'quant_backtest' | 'quant_dashboard';
  subAgentKey: QuantCapabilityId;
  executionCapabilityId: QuantCapabilityId;
  requiredSkills: string[];
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
  promptGuidance: string[];
}

export interface QuantProjectSettings {
  capabilityId: QuantCapabilityId;
  agentType: QuantCapability['agentType'];
  subAgentKey: QuantCapabilityId;
  executionCapabilityId: QuantCapabilityId;
  status: QuantCapabilityStatus;
  requiredSkills: string[];
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
}

export const DEFAULT_QUANT_CAPABILITY_ID: QuantCapabilityId = 'stock_diagnosis';

export const QUANT_CAPABILITY_GROUPS: QuantCapabilityGroup[] = [
  {
    id: 'core_analysis',
    name: '核心分析',
    description: '覆盖当前已验证的数据获取、证据落盘和看板生成链路。',
  },
  {
    id: 'market_research',
    name: '横向研究',
    description: '用于多标的、指数、ETF、行业与板块方向的分析任务。',
  },
  {
    id: 'strategy_risk',
    name: '策略风控',
    description: '面向策略研究、回测复盘和组合风险的后续能力。',
  },
];

const BASE_EXPECTED_ARTIFACTS = [
  '.quantpilot/run_plan.json',
  QUANT_GENERATION_STATE_RELATIVE_PATH,
  QUANT_GENERATION_QUEUE_RELATIVE_PATH,
  '.quantpilot/events.jsonl',
  QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
  QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
  '.quantpilot/validation.json',
  'evidence/sources.json',
  'evidence/data_quality.json',
  'data_file/final/dashboard-data.json',
  'app/page.tsx',
];

function baseExpectedArtifacts() {
  return [...BASE_EXPECTED_ARTIFACTS];
}

export const QUANT_CAPABILITIES: QuantCapability[] = [
  {
    id: 'stock_diagnosis',
    name: '个股诊断',
    shortName: '个股',
    description: '围绕单只股票完成行情、K 线、财务和公告的综合诊断。',
    inputHint: '例如：贵州茅台最近财务怎么样？生成一个个股诊断看板。',
    tags: ['实时行情', 'K 线', '财务', '公告'],
    status: 'ready',
    groupId: 'core_analysis',
    agentType: 'quant_analysis',
    subAgentKey: 'stock_diagnosis',
    executionCapabilityId: 'stock_diagnosis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-fundamentals',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
      'GET /api/v1/fundamentals/financials/{symbol}',
      'GET /api/v1/indicators/fundamental/{symbol}',
      'GET /api/v1/events/announcements/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须先解析股票标的，再获取真实数据。',
      '必须生成数据信源渠道和质量证据文件。',
      '页面必须包含行情、K 线/量价、财务摘要和数据信源渠道。',
      '可视化必须使用 single-stock-diagnosis 模板，首屏露出行情、K 线、财务/公告和数据质量，不要生成营销式大标题页。',
      '生成后需要通过 Next.js build 与预览 HTTP 200 检查。',
    ],
    promptGuidance: [
      '默认先做单只股票综合诊断。',
      '如果用户只给中文简称，先解析为标准股票代码。',
      '结论区分事实数据、计算结果和推断。',
      '页面按个股诊断模板组织：紧凑摘要、行情卡、K 线、量化信号、财务趋势、公告和信源质量。',
    ],
  },
  {
    id: 'technical_analysis',
    name: '技术分析',
    shortName: '技术',
    description: '聚焦价格趋势、成交量、均线、波动和风险指标。',
    inputHint: '例如：宁德时代最近 120 天走势如何？生成技术分析看板。',
    tags: ['K 线', '均线', '成交量', '风险'],
    status: 'ready',
    groupId: 'core_analysis',
    agentType: 'quant_analysis',
    subAgentKey: 'technical_analysis',
    executionCapabilityId: 'technical_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-image-extraction',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须获取足够长度的历史 K 线。',
      '必须生成数据质量证据，样本不足时要明确说明。',
      '页面必须包含 K 线或明确的 K 线错误面板、成交量、至少两条均线和风险指标。',
      '可视化必须使用 technical-timing 模板，明确触发条件、失效条件和观察条件。',
      '不得用静态样例数据替代行情接口结果。',
    ],
    promptGuidance: [
      '优先围绕趋势、成交量、波动率和最大回撤进行分析。',
      'A 股图表使用红涨绿跌。',
      '样本不足时必须明确说明限制。',
      '不要只输出看多/看空结论；页面必须让用户看见 K 线、均线、量能和风险触发依据。',
    ],
  },
  {
    id: 'fundamental_analysis',
    name: '基本面分析',
    shortName: '基本面',
    description: '聚焦财务质量、盈利能力、现金流和成长趋势。',
    inputHint: '例如：对比贵州茅台最近几个报告期的盈利质量。',
    tags: ['财务', '盈利', '现金流', '成长'],
    status: 'ready',
    groupId: 'core_analysis',
    agentType: 'quant_analysis',
    subAgentKey: 'fundamental_analysis',
    executionCapabilityId: 'fundamental_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-image-extraction',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-fundamentals',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/fundamentals/financials/{symbol}',
      'GET /api/v1/indicators/fundamental/{symbol}',
      'GET /api/v1/events/announcements/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须获取最近多个报告期财务数据。',
      '必须生成数据信源渠道和质量证据，说明报告期与缺失字段。',
      '页面必须展示营收、利润、利润率、ROE 或现金流质量等核心指标。',
      '可视化必须使用 fundamental-research 模板，展示盈利质量、现金流/缺失说明、报告期和公告事件。',
      '必须显示报告期、数据信源渠道和缺失字段说明。',
    ],
    promptGuidance: [
      '优先关注增长、盈利质量、现金流和资产负债变化。',
      '不要把单期数据过度外推成确定性投资结论。',
      '财务指标缺失时给出可见的数据限制说明。',
      '页面不要停留在财务表格，要把营收利润趋势、利润率/ROE、公告和估值情景组织成研究看板。',
    ],
  },
  {
    id: 'asset_comparison',
    name: '选股分析',
    shortName: '选股',
    description: '横向比较多只股票、ETF 或指数的收益、波动、估值和财务质量。',
    inputHint: '例如：对比贵州茅台、五粮液和泸州老窖最近的行情与基本面。',
    tags: ['横向比较', '标准化评分', '多标的'],
    status: 'ready',
    groupId: 'market_research',
    agentType: 'quant_analysis',
    subAgentKey: 'asset_comparison',
    executionCapabilityId: 'asset_comparison',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-fundamentals',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/fundamentals/financials/{symbol}',
      'GET /api/v1/indicators/fundamental/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须解析全部输入标的，并为每个标的写入真实数据。',
      '最终数据必须包含 assets[] 与 comparison，且覆盖 run_plan.symbols 中的全部标的。',
      '比较维度必须包含数据时间、收益、波动、回撤、成交量或成交额口径说明。',
      '页面必须展示多标的指标矩阵和至少一个对比图表。',
      '可视化必须使用 stock-selection 模板，展示候选覆盖、排名依据、剔除原因或数据限制。',
    ],
    promptGuidance: [
      '优先把多标的拆成可比较指标表。',
      '读取 data_file/final/dashboard-data.json 中的 assets[] 和 comparison，不要只展示主标的。',
      '如果某个标的数据缺失，必须在数据质量区域说明。',
      '页面应包含候选矩阵、收益/回撤/波动对比、流动性与相对强弱，不要基于单一指标给推荐。',
    ],
  },
  {
    id: 'sector_rotation',
    name: '行业/板块分析',
    shortName: '板块',
    description: '研究指数、行业、概念、ETF 的趋势、相对强弱和成分贡献。',
    inputHint: '例如：分析沪深300和创业板指最近一年的相对强弱。',
    tags: ['指数', 'ETF', '行业轮动', '相对强弱'],
    status: 'planned',
    groupId: 'market_research',
    agentType: 'quant_analysis',
    subAgentKey: 'sector_rotation',
    executionCapabilityId: 'technical_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '指数和 ETF 必须识别 asset_type，并跳过个股财务硬性要求。',
      '页面必须展示趋势、成交量、波动和回撤。',
      '行业成分和资金流暂未接入时必须显式说明能力边界。',
      '可视化必须使用 sector-rotation 模板，强调相对强弱、阶段排名和指数/ETF 代理口径。',
    ],
    promptGuidance: [
      '优先使用指数或 ETF 作为板块代理。',
      '把相对强弱、波动和阶段回撤作为核心观察项。',
      '页面不强制个股财务模块，重点展示轮动、流动性、回撤和能力边界。',
    ],
  },
  {
    id: 'strategy_research',
    name: '策略研究',
    shortName: '策略',
    description: '把投资想法拆成因子、信号、样本、交易规则和待验证假设。',
    inputHint: '例如：研究一个基于均线突破和成交量确认的 A 股趋势策略。',
    tags: ['因子', '信号', '交易规则', '假设'],
    status: 'planned',
    groupId: 'strategy_risk',
    agentType: 'quant_backtest',
    subAgentKey: 'strategy_research',
    executionCapabilityId: 'technical_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-backtest',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
      'GET /api/v1/backtests/ma-crossover/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须先定义信号和样本口径，再讨论策略效果。',
      '未实现正式回测前，页面只能展示研究计划和真实历史数据。',
      '不得把未经回测的规则描述成已验证收益。',
      '可视化必须使用 strategy-research 模板，展示信号规则、样本参数、待验证清单和风险假设。',
    ],
    promptGuidance: [
      '把策略想法拆为入场、出场、过滤、风控和评估指标。',
      '当前阶段优先使用均线突破回测作为可执行策略研究样例。',
      '如果回测数据未准备好，页面要明确展示未验证项，不能包装成策略收益。',
    ],
  },
  {
    id: 'backtest_review',
    name: '策略回测',
    shortName: '回测',
    description: '复盘策略净值、回撤、胜率、换手、年度收益和交易明细。',
    inputHint: '例如：用最近两年的 20 日均线突破规则回测 510300。',
    tags: ['净值', '回撤', '胜率', '交易明细'],
    status: 'ready',
    groupId: 'strategy_risk',
    agentType: 'quant_backtest',
    subAgentKey: 'backtest_review',
    executionCapabilityId: 'backtest_review',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-backtest',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
      'GET /api/v1/backtests/ma-crossover/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '正式回测结果必须来自本地后端和可复现参数。',
      '必须展示收益、回撤、交易次数、胜率、样本区间和交易明细。',
      '必须说明当前回测暂未建模滑点、停牌、分红再投资等限制。',
      '可视化必须使用 backtest-review 模板，包含策略参数、净值、回撤、交易明细和限制说明。',
    ],
    promptGuidance: [
      '默认使用 20/60 日均线突破作为最小可执行回测规则。',
      '区分历史行情事实、策略回测结果和仍需人工判断的风险。',
      '页面必须让用户能复核参数、样本、费用和交易，不只看最终收益。',
    ],
  },
  {
    id: 'portfolio_risk',
    name: '持仓分析',
    shortName: '持仓',
    description: '分析持仓集中度、波动、回撤、相关性、VaR 和风险暴露。',
    inputHint: '例如：分析一个贵州茅台、招商银行、510300 的组合风险。',
    tags: ['组合', '相关性', 'VaR', '集中度'],
    status: 'ready',
    groupId: 'strategy_risk',
    agentType: 'quant_dashboard',
    subAgentKey: 'portfolio_risk',
    executionCapabilityId: 'portfolio_risk',
    requiredSkills: [
      'quant-run-planner',
      'quant-image-extraction',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-indicators',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
      'GET /api/v1/fundamentals/financials/{symbol}',
      'GET /api/v1/events/announcements/{symbol}',
    ],
    expectedArtifacts: baseExpectedArtifacts(),
    validationRules: [
      '必须说明持仓权重、样本区间和风险计算口径。',
      '最终数据必须包含 portfolio、holdings[]、assets[] 和 comparison，并覆盖用户截图或输入中的全部可识别持仓。',
      '不得把单标的波动直接等同于组合风险。',
      '可视化必须使用 holding-analysis 模板，展示持仓矩阵、仓位/集中度、盈亏/成本、流动性和调仓优先级。',
    ],
    promptGuidance: [
      '先把用户持仓转成结构化权重表。',
      '当前阶段输出风险分析计划和主标的数据证据，下一阶段补齐组合计算。',
      '如果用户来自截图或口述，页面要区分用户提供字段、行情接口字段和缺失字段；调仓建议必须先给风险约束和不构成交易指令说明。',
    ],
  },
];

export function getExecutionQuantCapability(id?: string | null): QuantCapability {
  const capability = getQuantCapability(id);
  if (capability.status === 'ready') {
    return capability;
  }
  return getQuantCapability(capability.executionCapabilityId);
}

export function getQuantCapability(id?: string | null): QuantCapability {
  return (
    QUANT_CAPABILITIES.find((capability) => capability.id === id) ??
    QUANT_CAPABILITIES.find((capability) => capability.id === DEFAULT_QUANT_CAPABILITY_ID)!
  );
}

export function isQuantCapabilityId(value: unknown): value is QuantCapabilityId {
  return typeof value === 'string' && QUANT_CAPABILITIES.some((capability) => capability.id === value);
}

export function buildQuantProjectSettings(id?: string | null): QuantProjectSettings {
  const capability = getQuantCapability(id);
  const executionCapability = getExecutionQuantCapability(capability.id);
  return {
    capabilityId: capability.id,
    agentType: capability.agentType,
    subAgentKey: capability.subAgentKey,
    executionCapabilityId: executionCapability.id,
    status: capability.status,
    requiredSkills: capability.requiredSkills,
    dataEndpoints: executionCapability.dataEndpoints,
    expectedArtifacts: executionCapability.expectedArtifacts,
    validationRules: capability.validationRules,
  };
}

export function serializeQuantCapabilities() {
  return QUANT_CAPABILITIES.map((capability) => ({
    id: capability.id,
    name: capability.name,
    shortName: capability.shortName,
    description: capability.description,
    inputHint: capability.inputHint,
    tags: capability.tags,
    status: capability.status,
    groupId: capability.groupId,
    agentType: capability.agentType,
    subAgentKey: capability.subAgentKey,
    executionCapabilityId: capability.executionCapabilityId,
    requiredSkills: capability.requiredSkills,
    dataEndpoints: getExecutionQuantCapability(capability.id).dataEndpoints,
    expectedArtifacts: getExecutionQuantCapability(capability.id).expectedArtifacts,
    validationRules: capability.validationRules,
  }));
}
