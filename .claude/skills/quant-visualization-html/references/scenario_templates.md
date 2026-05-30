# QuantPilot 场景化可视化模板矩阵

本文件用于给 `quant-visualization-html` 选择页面模板。每次生成看板前，先读取 `.quantpilot/run_plan.json` 的 `visualization.templateId` 选择模板族，再读取 `visualization.variantId` 选择具体页面变体；如果没有该字段，再按用户问题和 final 数据字段推断模板和变体。

## 选择顺序

1. 优先使用 `.quantpilot/run_plan.json -> visualization.templateId` 和 `visualization.variantId`。
2. 如果 `dashboard-data.json.visualization.template_id` / `variant_id` 已存在，必须与 run plan 对齐；不一致时以 run plan 为准，并在数据质量区域说明修正。
3. 如果两者都缺失，先按字段推断模板族：
   - `holdings[]`、`portfolio`、`cash`、截图持仓、调仓：`holding-analysis`
   - `assets[]` + `comparison.rows[]`、选股、候选、横向比较：`stock-selection`
   - `backtest`、`equity_curve`、`trades`、回测：`backtest-review`
   - `financials.reports[]`、财务、基本面、业绩：`fundamental-research`
   - `trendTemplate`、K 线、均线、择时、突破：`technical-timing`
   - 指数、ETF、行业、板块轮动：`sector-rotation`
   - 单只个股综合分析：`single-stock-diagnosis`
4. 模板族确定后，再按问题意图推断变体：
   - 排名、推荐、哪只更强：`selection-ranking-matrix`
   - 组合、分散、相关性、风险暴露：`selection-correlation-risk-map`
   - 成交额、换手、量能、强弱、趋势模板：`selection-liquidity-trend-board`
   - 板块资金流、主力、净流入/净流出：`sector-capital-flow-board`
   - 突破、支撑压力、买卖点观察：`technical-breakout-watch`
   - 财务质量、现金流、ROE、利润率：`fundamental-quality-scorecard`
   - 调仓、减仓、补仓、现金使用：`portfolio-rebalance-plan`

## 通用输出契约

在 `data_file/final/dashboard-data.json` 中保留：

```json
{
  "visualization": {
    "template_id": "holding-analysis",
    "variant_id": "portfolio-risk-console",
    "name": "持仓分析模板",
    "variant_name": "组合风险控制台",
    "scenario": "基于用户持仓、成本、可用现金和市场数据，分析仓位、风险和调仓优先级。",
    "layout": "portfolio-summary-holdings-risk-grid",
    "first_viewport": [],
    "variant_guidance": [],
    "match_reasons": [],
    "pain_points": [],
    "required_components": [],
    "optional_components": [],
    "rendered_components": [],
    "missing_components": [],
    "data_signals": [],
    "final_data_contract": []
  }
}
```

页面必须渲染 `required_components` 中的核心组件；因为数据缺失无法渲染时，不允许静默跳过，要在“数据缺口/质量限制”区域列出 `missing_components` 和原因。

## holding-analysis：持仓分析模板

适用问题：调仓建议、持仓诊断、截图持仓、组合风险、仓位管理。

核心痛点：

- 不能把持仓当作普通股票列表，必须展示仓位、成本、盈亏、现金和集中度。
- 调仓建议必须先处理风险约束、数据缺口和不构成交易指令说明。
- 截图来源字段要和行情接口字段区分，识别不确定项必须可见。
- 页面不能使用巨型 hero、深色大 VaR 卡或“模板名称 + 大标题”首屏结构，应直接从账户摘要指标、持仓矩阵或核心风险面板开始。

必备组件：

- 账户/组合摘要栏：总资产、市值、现金、仓位、浮盈亏、VaR 或集中度摘要。
- 持仓矩阵：名称、代码、数量、成本、现价、市值、权重、浮盈亏。
- 仓位与集中度：单只权重、行业/资产类型暴露、Top 权重提示。
- 盈亏与成本偏离：成本/现价、浮盈亏百分比、离成本距离。
- 风险模块：相关性、流动性、波动、最大回撤、数据不足提示。
- 调仓优先级：降低风险、观察、可继续持有、补数据后再判断。
- 数据缺口与声明：截图识别字段、接口字段、缺失字段、非投资建议。

## stock-selection：选股分析模板

适用问题：推荐候选、多个标的横向比较、谁更强、哪个更值得研究。

核心痛点：

- 不能只展示主标的，必须覆盖全部候选。
- 不能用单因子给结论，需要说明排名依据、剔除原因和数据限制。
- 所有候选必须使用同一窗口、同一复权和同一指标口径。

必备组件：

- 候选覆盖摘要：输入标的、成功/失败、数据时间。
- 多标的指标矩阵：价格、涨跌、区间收益、回撤、波动、成交额。
- 收益对比图和波动/回撤对比图。
- 相对强弱排序：领先项、落后项、观察项。
- 流动性与可交易性：成交额、换手代理、Amihud 或等级。
- 估值/基本面/趋势补充：有数据时展示，没有数据时说明。
- 数据信源渠道逐项追踪：展示渠道名称、数据集类型、接口类型、行情时间和样本量，不把缓存状态或文件路径作为主要来源信息。

## single-stock-diagnosis：个股诊断模板

适用问题：某只股票怎么样、行情/K 线/财务/公告综合分析。

核心痛点：

- 首屏不能被巨型标题占满，要快速露出行情和图表。
- 不能只给涨跌观点，必须把量价、均线、财务、公告和质量放在同一报告中。
- 结论分为事实、计算和推断，不给确定性收益承诺。

必备组件：

- 紧凑报告摘要栏：标的、时间、数据信源渠道、核心状态。
- 实时行情指标卡。
- K 线与成交量主图，至少两条均线。
- 量化信号摘要：均线位置、量能、波动、回撤。
- 财务趋势或财务缺失说明。
- 公告事件时间线。
- 最近 K 线明细和数据质量。

## technical-timing：技术择时模板

适用问题：走势、K 线、技术指标、突破、买卖时点观察。

核心痛点：

- 不输出笼统看多/看空；必须给触发、失效和观察条件。
- K 线、成交量、均线是主内容，不能被指标卡替代。
- 样本不足或接口失败时，要展示真实错误和降级视图。

必备组件：

- 趋势结论摘要栏。
- OHLC/K 线主图和成交量副图。
- MA5/MA10/MA20/MA60 结构。
- 区间收益、最大回撤、波动率、量能比。
- 趋势模板：确认、减仓、观察触发条件。
- 最近 K 线明细表。

## fundamental-research：基本面研究模板

适用问题：财务怎么样、盈利质量、现金流、估值、公告事件。

核心痛点：

- 不能只贴财务表格，要解释增长、利润率、现金流和质量。
- 报告期口径必须清楚，缺失字段要可见。
- 估值情景是研究假设，不是目标价承诺。

必备组件：

- 基本面摘要栏。
- 营收与利润趋势。
- ROE、毛利率、净利率趋势。
- 现金流质量或缺失说明。
- 报告期数据表。
- 公告事件摘要。
- 估值情景和数据质量。

## backtest-review：策略回测模板

适用问题：回测、策略复盘、均线规则、交易明细、胜率。

核心痛点：

- 不能只展示最终收益，要展示回撤、胜率、交易次数和样本限制。
- 必须显示参数，保证回测可以复现。
- 费用、滑点、停牌、分红再投资等未建模因素必须说明。

必备组件：

- 策略参数卡片。
- 净值曲线。
- 回撤曲线或回撤指标。
- 收益、胜率、交易次数、样本区间。
- 交易明细表。
- 样本与限制说明。

## sector-rotation：板块轮动模板

适用问题：指数、ETF、行业、板块、相对强弱、轮动。

核心痛点：

- 不把指数/ETF 当作个股诊断，不强制个股财务模块。
- 必须说明代理标的和轮动口径。
- 暂未接入成分贡献或资金流时，要说明能力边界。

必备组件：

- 板块/指数代理说明。
- 相对强弱矩阵。
- 收益与回撤对比图。
- 成交额/流动性对比。
- 阶段排名变化。
- 数据信源渠道与能力边界。
