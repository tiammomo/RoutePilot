export type QuantCapabilityId =
  | 'stock_diagnosis'
  | 'technical_analysis'
  | 'fundamental_analysis';

export interface QuantCapability {
  id: QuantCapabilityId;
  name: string;
  shortName: string;
  description: string;
  inputHint: string;
  tags: string[];
  agentType: 'quant_analysis';
  subAgentKey: QuantCapabilityId;
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
  requiredSkills: string[];
  dataEndpoints: string[];
  expectedArtifacts: string[];
  validationRules: string[];
}

export const DEFAULT_QUANT_CAPABILITY_ID: QuantCapabilityId = 'stock_diagnosis';

export const QUANT_CAPABILITIES: QuantCapability[] = [
  {
    id: 'stock_diagnosis',
    name: '个股诊断',
    shortName: '个股',
    description: '围绕单只股票完成行情、K 线、财务和公告的综合诊断。',
    inputHint: '例如：贵州茅台最近财务怎么样？生成一个个股诊断看板。',
    tags: ['实时行情', 'K 线', '财务', '公告'],
    agentType: 'quant_analysis',
    subAgentKey: 'stock_diagnosis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-a-share-history',
      'quant-index-etf-market',
      'quant-technical-indicators',
      'quant-fundamental-financials',
      'quant-fundamental-indicators',
      'quant-announcement-events',
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
    expectedArtifacts: [
      '.quantpilot/run_plan.json',
      '.quantpilot/events.jsonl',
      '.quantpilot/validation.json',
      'evidence/sources.json',
      'evidence/data_quality.json',
      'data_file/final/dashboard-data.json',
      'app/page.tsx',
    ],
    validationRules: [
      '必须先解析股票标的，再获取真实数据。',
      '必须生成数据来源和质量证据文件。',
      '页面必须包含行情、K 线/量价、财务摘要和数据来源。',
      '生成后需要通过 Next.js build 与预览 HTTP 200 检查。',
    ],
    promptGuidance: [
      '默认先做单只股票综合诊断。',
      '如果用户只给中文简称，先解析为标准股票代码。',
      '结论区分事实数据、计算结果和推断。',
    ],
  },
  {
    id: 'technical_analysis',
    name: '技术分析',
    shortName: '技术',
    description: '聚焦价格趋势、成交量、均线、波动和风险指标。',
    inputHint: '例如：宁德时代最近 120 天走势如何？生成技术分析看板。',
    tags: ['K 线', '均线', '成交量', '风险'],
    agentType: 'quant_analysis',
    subAgentKey: 'technical_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-a-share-history',
      'quant-index-etf-market',
      'quant-technical-indicators',
      'quant-data-quality',
      'quant-visualization-html',
    ],
    dataEndpoints: [
      'GET /api/v1/symbols/resolve',
      'GET /api/v1/quotes/realtime/{symbol}',
      'GET /api/v1/quotes/history/{symbol}',
      'GET /api/v1/indicators/technical/{symbol}',
    ],
    expectedArtifacts: [
      '.quantpilot/run_plan.json',
      '.quantpilot/events.jsonl',
      '.quantpilot/validation.json',
      'evidence/sources.json',
      'evidence/data_quality.json',
      'data_file/final/dashboard-data.json',
      'app/page.tsx',
    ],
    validationRules: [
      '必须获取足够长度的历史 K 线。',
      '必须生成数据质量证据，样本不足时要明确说明。',
      '页面必须包含 K 线或明确的 K 线错误面板、成交量、至少两条均线和风险指标。',
      '不得用静态样例数据替代行情接口结果。',
    ],
    promptGuidance: [
      '优先围绕趋势、成交量、波动率和最大回撤进行分析。',
      'A 股图表使用红涨绿跌。',
      '样本不足时必须明确说明限制。',
    ],
  },
  {
    id: 'fundamental_analysis',
    name: '基本面分析',
    shortName: '基本面',
    description: '聚焦财务质量、盈利能力、现金流和成长趋势。',
    inputHint: '例如：对比贵州茅台最近几个报告期的盈利质量。',
    tags: ['财务', '盈利', '现金流', '成长'],
    agentType: 'quant_analysis',
    subAgentKey: 'fundamental_analysis',
    requiredSkills: [
      'quant-run-planner',
      'quant-symbol-resolver',
      'quant-market-data',
      'quant-fundamental-financials',
      'quant-fundamental-indicators',
      'quant-announcement-events',
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
    expectedArtifacts: [
      '.quantpilot/run_plan.json',
      '.quantpilot/events.jsonl',
      '.quantpilot/validation.json',
      'evidence/sources.json',
      'evidence/data_quality.json',
      'data_file/final/dashboard-data.json',
      'app/page.tsx',
    ],
    validationRules: [
      '必须获取最近多个报告期财务数据。',
      '必须生成数据来源和质量证据，说明报告期与缺失字段。',
      '页面必须展示营收、利润、利润率、ROE 或现金流质量等核心指标。',
      '必须显示报告期、数据来源和缺失字段说明。',
    ],
    promptGuidance: [
      '优先关注增长、盈利质量、现金流和资产负债变化。',
      '不要把单期数据过度外推成确定性投资结论。',
      '财务指标缺失时给出可见的数据限制说明。',
    ],
  },
];

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
  return {
    capabilityId: capability.id,
    agentType: capability.agentType,
    subAgentKey: capability.subAgentKey,
    requiredSkills: capability.requiredSkills,
    dataEndpoints: capability.dataEndpoints,
    expectedArtifacts: capability.expectedArtifacts,
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
  }));
}
