import type { QuantCapabilityId } from '@/lib/quant/capabilities';

export interface QuantVisualizationTemplate {
  id: string;
  name: string;
  scenario: string;
  painPoints: string[];
  requiredComponents: string[];
  optionalComponents: string[];
  dataSignals: string[];
  finalDataContract: string[];
}

export interface QuantVisualizationTemplateVariant {
  id: string;
  name: string;
  scenario: string;
  layout: string;
  density: 'dense' | 'balanced' | 'narrative';
  match: {
    keywords?: string[];
    minSymbols?: number;
    maxSymbols?: number;
    dataSignals?: string[];
  };
  requiredComponents: string[];
  optionalComponents: string[];
  firstViewport: string[];
  guidance: string[];
}

export interface QuantVisualizationTemplateSelectionContext {
  instruction?: string | null;
  symbolCount?: number | null;
  dataSignals?: string[];
  requestedVariantId?: string | null;
}

const DEFAULT_TEMPLATE_ID: QuantCapabilityId = 'stock_diagnosis';

const TEMPLATE_BY_CAPABILITY: Record<QuantCapabilityId, QuantVisualizationTemplate> = {
  stock_diagnosis: {
    id: 'single-stock-diagnosis',
    name: '个股诊断模板',
    scenario: '单只股票的行情、K 线、财务和事件综合诊断。',
    painPoints: [
      '不能把个股诊断做成大标题说明页，首屏必须露出行情和 K 线。',
      '不能只给涨跌结论，需要同时展示量价、均线、财务、公告和数据质量。',
      '投资判断必须区分事实、计算结果和推断，不输出确定性收益承诺。',
    ],
    requiredComponents: [
      '紧凑报告摘要栏',
      '实时行情指标卡',
      'K 线与成交量主图',
      '均线/波动/回撤信号摘要',
      '财务趋势或财务缺失说明',
      '公告事件时间线',
      '数据信源渠道与质量限制',
    ],
    optionalComponents: ['估值情景', '趋势模板', '最近 K 线明细表'],
    dataSignals: ['quote', 'kline.bars', 'technicalIndicators', 'financials.reports', 'announcements'],
    finalDataContract: ['symbol', 'name', 'quote', 'kline', 'technicalIndicators', 'financials', 'announcements'],
  },
  technical_analysis: {
    id: 'technical-timing',
    name: '技术择时模板',
    scenario: '围绕价格趋势、均线、成交量、波动和交易触发条件的技术分析。',
    painPoints: [
      '不能只写看多/看空，必须给出触发、失效和观察条件。',
      'K 线、成交量和均线是主内容，不能被指标卡替代。',
      '样本不足或历史接口失败时，要展示真实错误和降级视图。',
    ],
    requiredComponents: [
      '趋势结论摘要栏',
      'OHLC/K 线主图',
      '成交量副图',
      'MA5/MA10/MA20/MA60 结构',
      '回撤/波动/量能指标',
      '触发条件与失效条件',
      '最近 K 线明细表',
    ],
    optionalComponents: ['趋势模板', '支撑压力区间', '异常波动提示'],
    dataSignals: ['quote', 'kline.bars', 'technicalIndicators.summary', 'computedMetrics', 'trendTemplate'],
    finalDataContract: ['quote', 'kline.bars', 'technicalIndicators', 'computedMetrics', 'trendTemplate'],
  },
  fundamental_analysis: {
    id: 'fundamental-research',
    name: '基本面研究模板',
    scenario: '围绕财务质量、盈利能力、现金流、成长和公告事件的基本面分析。',
    painPoints: [
      '不能只展示财务表格，需要解释盈利质量、现金流和利润率变化。',
      '报告期口径必须清楚，缺失字段不能被静默忽略。',
      '估值只作为情景分析，不包装成目标价承诺。',
    ],
    requiredComponents: [
      '基本面摘要栏',
      '营收与利润趋势',
      'ROE/毛利率/净利率趋势',
      '现金流或现金流缺失说明',
      '报告期数据表',
      '公告事件摘要',
      '数据质量与缺失字段',
    ],
    optionalComponents: ['估值情景', '盈利质量评分', '同比/环比拆解'],
    dataSignals: ['financials.reports', 'fundamentalIndicators.summary', 'announcements', 'valuation'],
    finalDataContract: ['financials.reports', 'fundamentalIndicators', 'announcements', 'valuation'],
  },
  asset_comparison: {
    id: 'stock-selection',
    name: '选股分析模板',
    scenario: '横向比较多只股票、指数或 ETF 的收益、波动、回撤、估值和质量。',
    painPoints: [
      '不能只展示主标的，必须覆盖用户输入的全部候选标的。',
      '不能基于单一指标给推荐，需要展示排名依据、剔除原因和数据限制。',
      '不同标的必须使用同一时间窗口和同一指标口径。',
    ],
    requiredComponents: [
      '候选标的覆盖摘要',
      '多标的指标矩阵',
      '收益对比图',
      '波动/回撤对比图',
      '相对强弱与排名依据',
      '流动性与可交易性',
      '数据信源渠道逐项追踪',
    ],
    optionalComponents: ['估值情景对比', '趋势模板对比', '相关性结构', '候选清单/观察清单'],
    dataSignals: ['assets[]', 'comparison.rows[]', 'correlation', 'liquidity', 'valuation', 'trendTemplate'],
    finalDataContract: ['requestedSymbols', 'assets', 'comparison', 'correlation', 'liquidity'],
  },
  sector_rotation: {
    id: 'sector-rotation',
    name: '板块轮动模板',
    scenario: '指数、ETF、行业或概念之间的相对强弱、阶段回撤和轮动观察。',
    painPoints: [
      '不能把板块分析当作单个股票诊断，必须强调相对表现。',
      '指数和 ETF 不应强制展示个股财务报表。',
      '需要说明板块代理标的、样本窗口和轮动限制。',
    ],
    requiredComponents: [
      '板块/指数代理说明',
      '相对强弱矩阵',
      '收益与回撤对比图',
      '成交额/流动性对比',
      '阶段排名变化',
      '数据信源渠道与能力边界',
    ],
    optionalComponents: ['相关性结构', '趋势模板', '成分股贡献缺失说明'],
    dataSignals: ['assets[]', 'comparison.rows[]', 'correlation', 'liquidity', 'trendTemplate'],
    finalDataContract: ['requestedSymbols', 'assets', 'comparison', 'correlation', 'liquidity'],
  },
  strategy_research: {
    id: 'strategy-research',
    name: '策略研究模板',
    scenario: '把策略想法拆成信号、样本、参数、风控和待验证假设。',
    painPoints: [
      '不能把未经回测的想法写成已验证策略。',
      '必须明确入场、出场、过滤、仓位和失效条件。',
      '如果只完成历史数据准备，需要把未完成的验证项暴露出来。',
    ],
    requiredComponents: [
      '策略假设摘要',
      '信号规则卡片',
      '样本与参数说明',
      'K 线/信号叠加图',
      '待验证清单',
      '数据限制说明',
    ],
    optionalComponents: ['回测净值曲线', '参数敏感性', '交易明细'],
    dataSignals: ['kline.bars', 'technicalIndicators', 'backtest', 'trades'],
    finalDataContract: ['kline.bars', 'technicalIndicators', 'backtest'],
  },
  backtest_review: {
    id: 'backtest-review',
    name: '策略回测模板',
    scenario: '对可复现策略回测结果进行收益、回撤、胜率、交易和限制复盘。',
    painPoints: [
      '不能只展示最终收益，必须展示回撤、交易次数、胜率和样本限制。',
      '必须说明费用、滑点、停牌和分红再投资等未建模因素。',
      '必须展示参数，确保回测可以复现。',
    ],
    requiredComponents: [
      '策略参数卡片',
      '净值曲线',
      '回撤曲线或回撤指标',
      '收益/胜率/交易次数指标',
      '交易明细表',
      '样本与限制说明',
    ],
    optionalComponents: ['基准对比', '参数敏感性', '年度收益拆解'],
    dataSignals: ['backtest.summary', 'backtest.equity_curve', 'backtest.trades', 'kline.bars'],
    finalDataContract: ['backtest', 'trades', 'equityCurve', 'kline.bars'],
  },
  portfolio_risk: {
    id: 'holding-analysis',
    name: '持仓分析模板',
    scenario: '基于用户持仓、成本、可用现金和市场数据，分析仓位、风险和调仓优先级。',
    painPoints: [
      '不能把持仓当作普通股票列表，必须展示仓位、成本、盈亏、现金和集中度。',
      '调仓建议必须先处理风险约束和数据缺口，不直接输出交易指令。',
      '如果用户只上传截图，必须标注哪些字段来自截图识别、哪些字段来自行情接口。',
    ],
    requiredComponents: [
      '账户/组合摘要栏',
      '持仓矩阵',
      '仓位与集中度条形图',
      '盈亏与成本偏离表',
      '相关性/流动性/波动风险',
      '调仓优先级建议',
      '数据缺口与风险声明',
    ],
    optionalComponents: ['现金使用情景', '个股趋势模板', '估值情景', '风险贡献热力图'],
    dataSignals: ['holdings[]', 'cash', 'assets[]', 'comparison', 'correlation', 'liquidity', 'trendTemplate', 'valuation'],
    finalDataContract: ['portfolio', 'holdings', 'assets', 'comparison', 'correlation', 'liquidity'],
  },
};

const VARIANTS_BY_TEMPLATE_ID: Record<string, QuantVisualizationTemplateVariant[]> = {
  'single-stock-diagnosis': [
    {
      id: 'single-stock-command-center',
      name: '个股综合指挥台',
      scenario: '单股综合诊断，首屏同时呈现行情、K 线、信号和数据质量。',
      layout: 'summary-left-kline-main-right-signal',
      density: 'dense',
      match: { keywords: ['综合', '诊断', '怎么看', '分析一下'], maxSymbols: 1 },
      requiredComponents: ['紧凑行情摘要', 'K 线与成交量主图', '趋势/量能/风险信号', '财务与公告摘要', '信源质量'],
      optionalComponents: ['估值情景', '最近 K 线表', '分红/公告事件'],
      firstViewport: ['行情摘要', 'K 线主图', 'MA/量能信号'],
      guidance: ['首屏不能只有标题和指标卡，K 线主图必须可见。'],
    },
    {
      id: 'single-stock-fundamental-snapshot',
      name: '个股基本面快照',
      scenario: '用户偏向财务、估值、报告期和公告解释时使用。',
      layout: 'financial-scorecard-with-price-sidebar',
      density: 'balanced',
      match: { keywords: ['基本面', '财务', '估值', '利润', '营收', 'ROE', '现金流'], maxSymbols: 1 },
      requiredComponents: ['行情侧栏', '财务质量评分', '营收利润趋势', '利润率/ROE', '公告事件', '缺失字段说明'],
      optionalComponents: ['估值情景', '同行对比入口'],
      firstViewport: ['行情侧栏', '财务质量评分', '营收利润趋势'],
      guidance: ['财务页不要被 K 线占满，重点放在报告期趋势和质量解释。'],
    },
  ],
  'technical-timing': [
    {
      id: 'technical-kline-trader',
      name: 'K 线交易观察台',
      scenario: '以 K 线、均线、成交量和触发条件为核心的技术分析。',
      layout: 'full-width-kline-with-trigger-rail',
      density: 'dense',
      match: { keywords: ['K线', 'K 线', '技术', '均线', '走势', '趋势', '成交量'], maxSymbols: 1 },
      requiredComponents: ['K 线主图', '成交量副图', 'MA5/MA10/MA20/MA60', '触发条件', '失效条件', '风险指标'],
      optionalComponents: ['支撑压力', '最近 K 线表', '异常波动提示'],
      firstViewport: ['K 线主图', '成交量副图', '触发/失效条件'],
      guidance: ['技术页主图优先，不要把 K 线挤成缩略图。'],
    },
    {
      id: 'technical-breakout-watch',
      name: '突破观察清单',
      scenario: '用户询问突破、支撑压力、买点观察和条件触发时使用。',
      layout: 'trigger-cards-over-kline-detail',
      density: 'balanced',
      match: { keywords: ['突破', '支撑', '压力', '买点', '卖点', '触发', '止损'], maxSymbols: 1 },
      requiredComponents: ['关键价位卡', '突破/失效条件', 'K 线主图', '量能确认', '风险提示'],
      optionalComponents: ['观察清单', '交易计划草案'],
      firstViewport: ['关键价位卡', 'K 线主图', '触发条件'],
      guidance: ['明确条件，不输出确定性交易指令。'],
    },
  ],
  'fundamental-research': [
    {
      id: 'fundamental-quality-scorecard',
      name: '财务质量记分卡',
      scenario: '围绕盈利质量、利润率、现金流和成长质量的基本面分析。',
      layout: 'quality-scorecard-plus-trend-table',
      density: 'balanced',
      match: { keywords: ['质量', '盈利质量', '现金流', '毛利率', '净利率', 'ROE', '基本面'], maxSymbols: 1 },
      requiredComponents: ['质量评分', '营收利润趋势', 'ROE/利润率', '现金流或缺失说明', '报告期表'],
      optionalComponents: ['估值情景', '公告解释'],
      firstViewport: ['质量评分', '营收利润趋势', '核心利润率'],
      guidance: ['先讲报告期事实，再讲推断和限制。'],
    },
    {
      id: 'fundamental-report-trend',
      name: '报告期趋势看板',
      scenario: '用户要求查看最近多个报告期、同比环比和公告事件。',
      layout: 'period-trend-with-event-timeline',
      density: 'dense',
      match: { keywords: ['报告期', '季度', '同比', '环比', '公告', '年报', '季报'], maxSymbols: 1 },
      requiredComponents: ['报告期趋势表', '同比/环比拆解', '公告事件时间线', '缺失字段说明'],
      optionalComponents: ['财务图表', '估值说明'],
      firstViewport: ['报告期趋势', '同比/环比拆解', '公告摘要'],
      guidance: ['报告期口径必须清楚，避免把不同口径混在一起。'],
    },
  ],
  'stock-selection': [
    {
      id: 'selection-ranking-matrix',
      name: '多标的排名矩阵',
      scenario: '横向比较多只股票，输出候选排序、收益/回撤/波动和质量依据。',
      layout: 'coverage-summary-matrix-main-comparison-charts',
      density: 'dense',
      match: { keywords: ['对比', '比较', '排名', '排序', '推荐', '哪只', '候选', '选股'], minSymbols: 2 },
      requiredComponents: ['候选覆盖摘要', '多标的指标矩阵', '收益对比主图', '回撤/波动主图', '排名依据', '信源追踪'],
      optionalComponents: ['财务质量', '趋势模板', '估值情景'],
      firstViewport: ['候选覆盖摘要', '多标的指标矩阵', '至少一个对比主图'],
      guidance: ['不要只展示第一只股票，必须覆盖全部候选。'],
    },
    {
      id: 'selection-correlation-risk-map',
      name: '相关性与分散风险图谱',
      scenario: '多标的用于组合观察、分散度、相关性和风险暴露判断。',
      layout: 'correlation-heatmap-risk-matrix',
      density: 'balanced',
      match: { keywords: ['相关性', '分散', '组合', '风险', '波动', '回撤', '配置'], minSymbols: 2, dataSignals: ['correlation'] },
      requiredComponents: ['相关性矩阵', '风险贡献摘要', '回撤/波动对比', '流动性矩阵', '配置观察'],
      optionalComponents: ['收益对比', '持仓权重情景'],
      firstViewport: ['相关性矩阵', '风险指标', '回撤/波动对比'],
      guidance: ['适合组合风险，不要包装成单纯推荐榜。'],
    },
    {
      id: 'selection-liquidity-trend-board',
      name: '强弱与流动性筛选台',
      scenario: '用户关注成交额、换手、趋势强弱和可交易性。',
      layout: 'liquidity-first-screen-with-strength-bars',
      density: 'dense',
      match: { keywords: ['流动性', '成交额', '换手', '量能', '强弱', '趋势模板'], minSymbols: 2, dataSignals: ['liquidity', 'trendTemplate'] },
      requiredComponents: ['强弱排序', '流动性矩阵', '趋势模板对比', '收益/回撤对比', '剔除原因'],
      optionalComponents: ['相关性结构', '行业标签'],
      firstViewport: ['强弱排序', '流动性矩阵', '趋势对比主图'],
      guidance: ['优先解释可交易性和趋势确认，不只看收益。'],
    },
  ],
  'sector-rotation': [
    {
      id: 'sector-rotation-radar',
      name: '板块轮动雷达',
      scenario: '行业、指数或 ETF 的阶段收益、回撤、趋势和轮动观察。',
      layout: 'sector-radar-with-relative-strength',
      density: 'dense',
      match: { keywords: ['板块', '行业', 'ETF', '指数', '轮动', '相对强弱'], minSymbols: 2 },
      requiredComponents: ['板块代理说明', '相对强弱矩阵', '收益/回撤对比', '阶段排名变化', '能力边界'],
      optionalComponents: ['相关性结构', '流动性对比'],
      firstViewport: ['板块代理说明', '相对强弱矩阵', '收益/回撤对比'],
      guidance: ['指数/ETF 不强制财务模块，重点讲相对表现。'],
    },
    {
      id: 'sector-capital-flow-board',
      name: '板块资金流观察台',
      scenario: '用户关注板块现金流量、主力资金方向和成交额变化。',
      layout: 'capital-flow-ranking-with-sector-table',
      density: 'dense',
      match: { keywords: ['资金流', '现金流量', '主力', '净流入', '净流出', '成交额'], minSymbols: 1, dataSignals: ['sectorCapitalFlow'] },
      requiredComponents: ['资金流排名', '净流入/净流出条形图', '成交额热度', '板块样本说明', '数据口径限制'],
      optionalComponents: ['板块 K 线', '成分贡献缺失说明'],
      firstViewport: ['资金流排名', '净流入/净流出主图', '成交额热度'],
      guidance: ['资金流必须标注代理口径，不能声称等同真实主力意图。'],
    },
  ],
  'strategy-research': [
    {
      id: 'strategy-hypothesis-canvas',
      name: '策略假设画布',
      scenario: '把策略想法拆成信号、过滤、风控、样本和待验证清单。',
      layout: 'hypothesis-canvas-with-data-readiness',
      density: 'balanced',
      match: { keywords: ['策略', '想法', '规则', '因子', '假设'] },
      requiredComponents: ['策略假设', '信号规则', '样本参数', '待验证清单', '数据限制'],
      optionalComponents: ['K 线信号叠加', '回测入口'],
      firstViewport: ['策略假设', '信号规则', '样本参数'],
      guidance: ['未回测前不要展示成收益结果。'],
    },
    {
      id: 'strategy-signal-lab',
      name: '信号实验室',
      scenario: '用户已经给出入场/出场/过滤条件，需要观察信号和参数。',
      layout: 'signal-lab-with-kline-overlay',
      density: 'dense',
      match: { keywords: ['入场', '出场', '过滤', '参数', '信号', '择时'], dataSignals: ['technicalIndicators'] },
      requiredComponents: ['信号规则卡', 'K 线信号叠加', '参数表', '风险过滤', '待回测清单'],
      optionalComponents: ['初步回测', '参数敏感性'],
      firstViewport: ['信号规则卡', 'K 线信号叠加', '参数表'],
      guidance: ['信号和参数要可复核，不能只写自然语言。'],
    },
  ],
  'backtest-review': [
    {
      id: 'backtest-performance-review',
      name: '回测绩效复盘',
      scenario: '围绕收益、净值、回撤、胜率和交易明细复盘策略。',
      layout: 'equity-curve-with-drawdown-and-trades',
      density: 'dense',
      match: { keywords: ['回测', '净值', '收益', '胜率', '交易明细'], dataSignals: ['backtest'] },
      requiredComponents: ['策略参数', '净值曲线', '回撤指标', '收益/胜率/交易次数', '交易明细', '限制说明'],
      optionalComponents: ['基准对比', '年度收益'],
      firstViewport: ['策略参数', '净值曲线', '核心绩效指标'],
      guidance: ['回测页必须可复现参数和样本，不只展示收益。'],
    },
    {
      id: 'backtest-trade-forensics',
      name: '交易行为复盘',
      scenario: '用户关注每笔交易、持仓天数、亏损来源和执行质量。',
      layout: 'trade-table-first-with-equity-sidebar',
      density: 'balanced',
      match: { keywords: ['交易', '买卖点', '持仓天数', '亏损', '复盘'], dataSignals: ['trades'] },
      requiredComponents: ['交易明细表', '收益分布', '持仓天数', '最大亏损交易', '净值侧栏'],
      optionalComponents: ['规则改进清单'],
      firstViewport: ['交易明细表', '收益分布', '净值侧栏'],
      guidance: ['适合解释策略行为，不要只看最终净值。'],
    },
  ],
  'holding-analysis': [
    {
      id: 'portfolio-risk-console',
      name: '组合风险控制台',
      scenario: '持仓、仓位、集中度、相关性和流动性风险分析。',
      layout: 'portfolio-summary-holdings-risk-grid',
      density: 'dense',
      match: { keywords: ['持仓', '仓位', '组合', '风险', '集中度', '相关性'], dataSignals: ['holdings', 'correlation'] },
      requiredComponents: ['组合摘要', '持仓矩阵', '仓位集中度', '相关性/流动性风险', '数据缺口'],
      optionalComponents: ['调仓优先级', '风险贡献'],
      firstViewport: ['组合摘要', '持仓矩阵', '仓位集中度'],
      guidance: ['持仓页不要做成普通股票列表，必须体现权重和风险。'],
    },
    {
      id: 'portfolio-rebalance-plan',
      name: '调仓计划工作台',
      scenario: '用户要求调仓、减仓、补仓或现金使用方案。',
      layout: 'rebalance-actions-with-risk-constraints',
      density: 'balanced',
      match: { keywords: ['调仓', '减仓', '补仓', '再平衡', '现金', '买入', '卖出'], dataSignals: ['portfolio'] },
      requiredComponents: ['当前持仓', '风险约束', '调仓优先级', '现金情景', '不构成交易指令声明'],
      optionalComponents: ['个股趋势卡', '估值情景'],
      firstViewport: ['当前持仓', '风险约束', '调仓优先级'],
      guidance: ['调仓建议必须带约束和风险声明，不输出确定性指令。'],
    },
  ],
};

function normalizeText(value: string | null | undefined) {
  return (value ?? '').toLowerCase().replace(/\s+/g, '');
}

function getTemplateVariants(template: QuantVisualizationTemplate): QuantVisualizationTemplateVariant[] {
  return VARIANTS_BY_TEMPLATE_ID[template.id] ?? [
    {
      id: `${template.id}-default`,
      name: template.name,
      scenario: template.scenario,
      layout: 'default-data-dense-dashboard',
      density: 'dense',
      match: {},
      requiredComponents: template.requiredComponents,
      optionalComponents: template.optionalComponents,
      firstViewport: template.requiredComponents.slice(0, 3),
      guidance: template.painPoints,
    },
  ];
}

function scoreVariant(
  variant: QuantVisualizationTemplateVariant,
  context?: QuantVisualizationTemplateSelectionContext
) {
  const instruction = normalizeText(context?.instruction);
  let score = 0;

  if (context?.requestedVariantId && context.requestedVariantId === variant.id) {
    score += 1000;
  }

  const symbolCount = context?.symbolCount ?? null;
  if (symbolCount !== null && symbolCount > 0) {
    if (variant.match.minSymbols !== undefined && symbolCount < variant.match.minSymbols) return -1;
    if (variant.match.maxSymbols !== undefined && symbolCount > variant.match.maxSymbols) return -1;
    if (variant.match.minSymbols !== undefined || variant.match.maxSymbols !== undefined) score += 3;
  }

  for (const keyword of variant.match.keywords ?? []) {
    if (instruction.includes(normalizeText(keyword))) {
      score += 4;
    }
  }

  const dataSignals = new Set((context?.dataSignals ?? []).map(normalizeText));
  for (const signal of variant.match.dataSignals ?? []) {
    if (dataSignals.has(normalizeText(signal))) {
      score += 3;
    }
  }

  return score;
}

function collectVariantMatchReasons(
  variant: QuantVisualizationTemplateVariant,
  context?: QuantVisualizationTemplateSelectionContext
) {
  const reasons: string[] = [];
  const instruction = normalizeText(context?.instruction);
  const matchedKeywords = (variant.match.keywords ?? []).filter((keyword) =>
    instruction.includes(normalizeText(keyword))
  );
  const dataSignals = new Set((context?.dataSignals ?? []).map(normalizeText));
  const matchedSignals = (variant.match.dataSignals ?? []).filter((signal) =>
    dataSignals.has(normalizeText(signal))
  );

  if (context?.requestedVariantId === variant.id) {
    reasons.push(`显式指定变体 ${variant.id}`);
  }
  if (typeof context?.symbolCount === 'number') {
    reasons.push(`识别到 ${context.symbolCount} 个标的`);
  }
  if (matchedKeywords.length > 0) {
    reasons.push(`命中问题关键词：${matchedKeywords.join('、')}`);
  }
  if (matchedSignals.length > 0) {
    reasons.push(`命中数据信号：${matchedSignals.join('、')}`);
  }
  if (reasons.length === 0) {
    reasons.push('使用该模板族的默认高质量页面变体');
  }

  return reasons;
}

export function selectQuantVisualizationVariant(
  template: QuantVisualizationTemplate,
  context?: QuantVisualizationTemplateSelectionContext
): QuantVisualizationTemplateVariant {
  const variants = getTemplateVariants(template);
  const scored = variants
    .map((variant, index) => ({ variant, index, score: scoreVariant(variant, context) }))
    .filter((item) => item.score >= 0)
    .sort((left, right) => right.score - left.score || left.index - right.index);
  return scored[0]?.variant ?? variants[0];
}

export function getQuantVisualizationTemplate(id?: string | null): QuantVisualizationTemplate {
  const byCapability = TEMPLATE_BY_CAPABILITY[(id ?? DEFAULT_TEMPLATE_ID) as QuantCapabilityId];
  if (byCapability) return byCapability;
  const byTemplateId = Object.values(TEMPLATE_BY_CAPABILITY).find((template) => template.id === id);
  return byTemplateId ?? TEMPLATE_BY_CAPABILITY[DEFAULT_TEMPLATE_ID];
}

export function serializeQuantVisualizationTemplate(
  id?: string | null,
  context?: QuantVisualizationTemplateSelectionContext
) {
  const template = getQuantVisualizationTemplate(id);
  const variant = selectQuantVisualizationVariant(template, context);
  return {
    templateId: template.id,
    name: template.name,
    scenario: template.scenario,
    variantId: variant.id,
    variantName: variant.name,
    variantScenario: variant.scenario,
    layout: variant.layout,
    density: variant.density,
    matchReasons: collectVariantMatchReasons(variant, context),
    painPoints: template.painPoints,
    requiredComponents: variant.requiredComponents,
    optionalComponents: Array.from(new Set([...variant.optionalComponents, ...template.optionalComponents])),
    firstViewport: variant.firstViewport,
    variantGuidance: variant.guidance,
    dataSignals: Array.from(new Set([...template.dataSignals, ...(variant.match.dataSignals ?? [])])),
    finalDataContract: template.finalDataContract,
    alternatives: getTemplateVariants(template).map((item) => ({
      variantId: item.id,
      name: item.name,
      scenario: item.scenario,
      layout: item.layout,
    })),
  };
}
