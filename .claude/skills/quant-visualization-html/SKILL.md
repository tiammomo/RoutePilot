---
name: quant-visualization-html
description: Use this skill to generate a real visual Next.js/HTML quantitative dashboard after market data has been fetched or whenever the user asks for a visualization page.
---

# QuantPilot 金融可视化看板能力

这个 skill 负责把已获取的行情、财务、公告和分析结果转换为真正可运行的可视化页面。它不是“写分析说明”的 skill；触发后必须产出或更新页面文件。

视觉和交互质量必须同时参考 `quantpilot-ui-product-design` 的 UI/UX Pro Max 适配层，尤其是 Data-Dense Dashboard、Real-Time Operations、可访问性、响应式、图表可读性和反模式约束。功能正确但明显粗糙、不专业或像默认模板的页面不算完成。

## 何时必须使用

当用户希望生成、修复或增强以下内容时，必须使用本 skill：

- 可视化界面、HTML 看板、量化分析页面、行情大屏、投研 dashboard。
- K 线、趋势、量价、均线、收益、回撤、波动率、财务趋势、公告时间线。
- 已经通过 `quant-market-data`、`quant-a-share-history`、`quant-fundamental-financials` 或其他金融 skill 拿到数据后，需要呈现结果。

## 不可妥协的交付要求

1. 必须修改当前生成项目内的 `app/page.tsx`，必要时同步修改 `app/globals.css`、`app/layout.tsx` 或创建 `app/api/**/route.ts`。
2. 必须生成可访问、可交互、可刷新的页面；不能只回复文字、不能只写计划、不能留下 Next.js 默认页。
3. 如果用户问的是股票、行情或趋势，页面必须包含真实图表区域，不允许只用指标卡替代图表。
4. 如果历史 K 线接口失败，页面必须显示真实错误和降级视图，但仍要保留 K 线面板和重试能力。
5. 数据必须来自 QuantPilot 本地后端或已经获取到的真实结果，不得编造行情、财报或 K 线。
6. 完成后必须能通过平台自动验证：Next.js build、预览 HTTP 200、`data_file/final/dashboard-data.json`、`evidence/sources.json`、`evidence/data_quality.json`、金融图表存在性和 `/api/market` 代理检查。
7. 不要把当前取到的数据大段硬编码进 `app/page.tsx`；页面必须读取 `data_file/final/dashboard-data.json`，或通过同源 `/api/market/**` 刷新。
8. 生成项目默认已有金融看板模板时，必须在模板上增强，不要推倒重写成营销页、说明页或只有指标卡的静态页。
9. 如果 `dashboard-data.json` 包含 `assets[]` 或 `comparison`，这是多标的任务；页面必须展示全部标的的对比矩阵和图表，不能只展示根字段中的主标的 `quote/kline`。
10. 修改 `app/page.tsx`、`app/globals.css`、JSON 或 evidence 文件必须使用 Write/Edit 工具，不要用 Bash 的 `cat >`、`tee`、`echo >`、`printf >`、heredoc、python/node 脚本或 `touch` 写文件。
11. 必须按具体分析场景选择可视化模板，不能把持仓、选股、技术、基本面、回测都生成成同一种通用金融页面。
12. 页面必须通过 TypeScript/Next.js build。`dashboard-data.json` 是动态 JSON，读取后统一用 `JsonRecord`、`asRecord()`、`asArray()`、`numeric()` 这类守卫函数处理；不要让 `flatMap/map` 推断出过窄对象类型后再访问额外字段。
13. 多标的任务不得降级成单股模板。只要 `run_plan.symbols.length > 1`、`assets[]`、`comparison.rows[]` 或用户要求对比/矩阵/排名/推荐顺序/观察池，`run_plan.visualization.templateId`、`dashboard-data.json.visualization.template_id` 和页面都必须采用 `stock-selection`/多标的对比结构。
14. 禁止引用外部 CDN、远程脚本、远程样式、远程图片、远程字体或浏览器直连外部 API；页面必须使用本地代码、本地 CSS/SVG 和同源 `/api/market/**`。
15. 禁止留下 `MOCK_DATA`、`SAMPLE_DATA`、`STATIC_QUOTES`、示例数据、模拟数据、占位数据；如果数据不足，展示真实缺口和重试入口。
16. 禁止把 token、api key、cookie、authorization 或任何密钥写入页面、evidence、final 数据或配置文件。
17. 禁止把多个迷你 sparkline 当作主要可视化交付。Sparkline 只能作为资产卡辅助图；页面必须额外提供至少一个带坐标/日期/图例/数值标签的主图、对比图或矩阵。

## 标准工作流

1. 确认用户问题需要哪些数据：实时行情、历史 K 线、财务、公告、组合对比。
2. 缺数据时先调用对应取数 skill：
   - 实时行情：`quant-market-data`
   - 历史 K 线：`quant-a-share-history`
   - 财务趋势：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 不确定数据源：`quant-data-registry`
3. 先读取现有 `app/page.tsx`、`app/globals.css` 和 `data_file/final/dashboard-data.json`，确认模板已有组件和数据字段。
4. 读取 `.quantpilot/run_plan.json`，先按 `visualization.templateId` 选择模板族，再按 `visualization.variantId`、`layout`、`firstViewport` 和 `variantGuidance` 选择具体页面结构；模板说明见 `references/scenario_templates.md`。
5. 做一次 UI/UX Pro Max 风格的设计决策：金融/量化页面默认使用 Data-Dense Dashboard，不使用营销 landing；确定页面模式、语义配色、图表类型、表格 fallback、响应式策略和反模式。
6. 设计看板信息架构：先展示结论和核心指标，再展示图表、数据表、数据质量和来源。
   - 投研/量化看板不要使用营销落地页式巨型 hero。顶部应是紧凑的报告摘要栏或工具栏：小标题、核心判断、关键指标和数据状态并排展示。
   - 首屏应尽快露出核心指标、图表或持仓矩阵；`h1` 只用于页面主题，桌面端建议不超过 40px，移动端不超过 32px。
   - 结论句应放在摘要卡或状态条中，不要做成占据半屏的大字口号。
   - 首页提问生成的默认看板必须像可用的金融工作台：首屏包含真实标的名称、行情/持仓/回测/财务核心数字、更新时间、数据状态和至少一个核心图表或矩阵。
   - 单标的行情页推荐首屏顺序：紧凑数据源状态条 → 标的与价格区 → 开高低收/成交额/换手等 meta row → 2-3 条可读的趋势/量能/结论摘要 → K 线主图和信号侧栏。
   - 不要把数据信源、缓存状态、模板名称或免责声明放在首屏最显眼位置；它们应作为辅助信息放在摘要栏、信源模块或底部说明。
   - 移动端必须没有页面级横向溢出；宽表格、长代码、长接口名只能在卡片内部滚动或截断，不得撑开 `body`。
   - `holding-analysis`、调仓建议、截图持仓和组合风控页面不要生成 `hero-band`、深色大 VaR 卡、巨型标题或模板名称区；页面应直接从账户/组合摘要指标、持仓矩阵或核心风险面板开始。
   - VaR、样本口径、刷新接口和非投资建议声明应放入指标卡、风险模块、数据质量或底部说明，不要占据首屏顶部。
7. 实现页面文件并确保有加载、错误、空数据、刷新状态。
8. 页面刷新数据时优先复用或创建同源 API route 代理到 `http://127.0.0.1:8000`，避免浏览器 CORS 或网络策略影响。
9. 使用 `quant-data-quality` 写入 `evidence/sources.json` 与 `evidence/data_quality.json`，记录来源、接口、时间戳、样本长度、缺失字段、警告和限制。
10. 将最终看板数据写入 `data_file/final/dashboard-data.json`，字段中保留 `symbol`、`source`、`fetched_at`、`quote_time` 或对应数据源时间。
11. 完成后简短说明修改了哪些页面和看板现在包含哪些数据视图。

## TypeScript 稳定性规则

生成 `app/page.tsx` 时必须按严格 TypeScript 写法处理动态金融数据：

- 所有从 JSON 读取的数据先进入 `JsonRecord | null` 或 `JsonRecord[]`，不要直接把 `unknown` 当作具体对象访问。
- `assets[]`、`comparison.rows[]`、`announcements.announcements[]`、`financials.reports[]` 等动态数组必须写成 `JsonRecord[]`：

```ts
const assets = asArray(data?.assets)
  .map(asRecord)
  .filter((item): item is JsonRecord => Boolean(item));
```

- 对 `flatMap()` 里新增字段的对象必须显式标注为 `JsonRecord`，避免 TypeScript 推断成 `{ symbol: unknown; name: unknown }` 这类窄类型：

```ts
const rows: JsonRecord[] = assets.flatMap((asset) => {
  const announcements = asRecord(asset.announcements);
  return asArray(announcements?.announcements)
    .map(asRecord)
    .filter((item): item is JsonRecord => Boolean(item))
    .map((item): JsonRecord => ({
      ...item,
      symbol: item.symbol ?? asset.symbol,
      name: item.name ?? asset.name,
    }));
});
```

- 排序、格式化和渲染时一律使用 `row['field']` 或 `row.field` 的 `unknown` 值进入 `String()`、`numeric()`、`formatDate()`、`formatNumber()`，不要声明不完整的结构类型。
- JSX 中不能直接渲染动态 JSON 的 unknown/object 字段；例如 `rows[0]?.period`、`row.value`、`source.metadata` 必须先进入 `String()`、`formatDate()`、`formatNumber()` 或 `pickString()` 后再渲染。
- 不能用 `as any` 扫过类型错误；如果字段不确定，增加守卫函数或把数组显式标注为 `JsonRecord[]`。
- 如果页面新增公告、财务、估值、相关性、流动性等模块，必须保证 `npm run build` 不会出现 “Property does not exist on type ...”。

## 场景模板选择

每次生成页面前必须读取：

```text
.quantpilot/run_plan.json
references/scenario_templates.md
```

按 `run_plan.visualization.templateId` 选择模板族；再按 `run_plan.visualization.variantId` 选择具体页面变体。`templateId` 解决“是什么场景”，`variantId` 解决“这一页应该长成什么结构”。如果缺失，按 final 数据字段推断模板族：

- `holding-analysis`：持仓、调仓、组合风险、截图持仓。
- `stock-selection`：选股、多标的横向比较、候选排序。
- `single-stock-diagnosis`：单只股票综合诊断。
- `technical-timing`：K 线、均线、突破、技术择时。
- `fundamental-research`：财务、基本面、盈利质量、公告。
- `backtest-review`：策略回测、净值、交易明细。
- `sector-rotation`：指数、ETF、行业和板块轮动。

选择模板后，页面必须覆盖该模板的 `required_components`。如果数据不足，组件仍要以“缺数据/待补充”的形式出现，不能直接删除。

同一模板族内可以有多个高质量变体，不要把所有问题都做成同一套万能页面：

- `single-stock-diagnosis`：综合指挥台、基本面快照。
- `technical-timing`：K 线交易观察台、突破观察清单。
- `fundamental-research`：财务质量记分卡、报告期趋势看板。
- `stock-selection`：多标的排名矩阵、相关性与分散风险图谱、强弱与流动性筛选台。
- `sector-rotation`：板块轮动雷达、板块资金流观察台。
- `strategy-research`：策略假设画布、信号实验室。
- `backtest-review`：回测绩效复盘、交易行为复盘。
- `holding-analysis`：组合风险控制台、调仓计划工作台。

如果 `dashboard-data.json.visualization.variant_id` 与 run plan 不一致，以 run plan 为准；如果没有 variant 字段，则依据用户问题、`assets[]`/`comparison.rows[]`/`holdings[]`/`backtest` 等数据形态选择最接近的变体，并在页面结构上体现该变体的 `firstViewport` 和 `variant_guidance`。

## 标准数据契约

为了让平台预取、验证和标准模板稳定工作，优先使用下面字段；字段可以补充，但不要改名或只写自定义结构：

- `.quantpilot/run_plan.json` 的 `symbols` 必须是证券代码字符串数组，例如 `["600519"]`。如果需要保存名称、市场、secid，请放在 `resolvedSymbols[]` 或 final 数据中，不要把对象写进 `symbols`。
- 单标的 final 数据必须包含：
  - `symbol`、`name`、`asset_type`、`source`、`as_of`
  - `quote.price`、`quote.change_percent`、`quote.quote_time`
  - `kline.bars[]`，每条包含 `date/open/high/low/close/volume/amount/change_percent`
  - `technicalIndicators.summary` 或 `computedMetrics`
  - 可选 `financials.reports[]`、`fundamentalIndicators.summary`、`announcements.announcements[]`
- 多标的 final 数据必须包含 `requestedSymbols`、`assets[]`、`comparison.rows[]`；每个 `assets[]` 元素继续使用同样的单标的结构。
- 多标的页面如果只拿到 4/5 只等部分标的，仍要展示覆盖摘要、缺失标的、失败原因和已成功标的对比；不能退回单股页，也不能只展示第一只标的。
- final 数据应包含 `visualization.template_id`、`visualization.variant_id`、`visualization.layout`、`visualization.first_viewport`、`visualization.required_components`、`visualization.rendered_components`、`visualization.missing_components`、`visualization.pain_points`。
- 多标的页面展示指标时优先使用 `comparison.rows[]` 的标准字段：`period_return`、`max_drawdown`、`volatility20d`、`avg_amount_20d/amount`、`turnover`、`composite_score`、`selection_view`；不要只从 `assets[].technicalIndicators.summary.return_120d_pct` 推断，避免字段名不一致导致页面显示错误排序。
- 页面优先保留平台标准模板的 `DATA_FILE`、`readDashboardData()`、`getBars()`、`TrendChart` 和 `data-source-file={DATA_FILE}` 结构，只在其上增强展示。
- 如果平台已经预取出 `dashboard-data.json`，不要再用空对象覆盖它，也不要把 `kline.bars` 改成只有模型自己知道的字段名。
- 页面展示实时行情字段时优先级必须正确：`quote.previous_close/open/high/low/amount/turnover/volume` 优先，只有 quote 缺失时才降级到 `kline.bars.at(-1)`；不要用最新收盘价冒充昨收，不要因为 K 线 amount/turnover 缺失而忽略 quote 中的成交额和换手率。
- 当 K 线字段来自不同 provider 且部分字段缺失时，应在数据质量或表格中真实显示缺口；可以用实时 quote 补充“今日”指标卡，但不能把补充字段反写成历史 K 线事实。
- 缺数据不是半成品。不要把大量 `-` 直接散落在首屏；关键指标缺失时使用“待接入/待确认/等待数据写入”等明确状态，并在图表区域保留专业空态，说明已预留 OHLC、均线、成交量或矩阵渲染区域。
- 空态也必须有设计质量：首屏仍要呈现标的、数据源、更新时间状态、指标框架、图表/矩阵占位和下一步可执行线索；不能退化成 Next.js 默认页、纯说明页或一堆灰色占位。

## A 股行情看板最低标准

如果用户的问题涉及 A 股个股、指数或组合，至少包含：

- 实时行情指标卡：最新价、涨跌幅、开盘、最高、最低、昨收、成交量、成交额、市值、行情时间。
- K 线主图：蜡烛图或 OHLC 图，必须能区分涨跌；叠加 MA5、MA10、MA20 中至少两条均线。
- 成交量副图：与 K 线共用日期维度，涨跌颜色遵循 A 股习惯。
- 量化指标区：区间涨跌幅、最大回撤、年化/区间波动率、均线多空状态、放量/缩量提示、突破/跌破提示。
- 数据明细表：至少展示最近 10 根 K 线的日期、开高低收、成交额、涨跌幅、换手率。
- 数据信源渠道：展示本次使用的外部或本地渠道，例如东方财富实时行情接口、东方财富历史 K 线接口、东方财富财务数据接口、公告事件接口、用户上传截图或 QuantPilot 后端预取；不要把 `cache_status`、`dashboard-data.json` 路径、内部文件路径当成主要“数据来源”展示。
- 数据质量：展示 evidence 或 final 数据中的 `data_quality`、`warnings`、样本长度、更新时间和限制说明；缓存状态只可作为技术证据附注，不作为核心信源。

## 多标的对比看板最低标准

如果最终数据包含 `assets[]` 或用户问题包含“对比/组合/相对强弱”，至少包含：

- 标的覆盖：页面显式展示 `requestedSymbols` 或 `assets[].symbol` 中的全部标的。
- 指标矩阵：每个标的展示最新价、涨跌幅、区间收益、最大回撤、波动、成交额或成交量。
- 对比图表：至少一个 SVG/canvas 图表比较区间收益；另一个图表或矩阵比较波动/回撤。
- 多标的对比图必须有统一尺度、数值标签和正负方向；收益/回撤/波动条不能只画相对宽度而没有基线或数值。资产卡内 K 线缩略图不算必备对比图。
- 相对强弱摘要：展示收益领先、回撤较小、波动较低等结果，结果必须来自 `comparison.rows[]` 或 `assets[].computedMetrics`。
- 数据信源渠道：逐只标的展示渠道名称、数据集类型、接口类型、行情时间和样本量，例如“东方财富实时行情接口 / 实时行情 / 行情时间 ...”。技术文件路径只放到证据附注，不要作为用户可读的来源卡片主信息。

## 财务看板最低标准

如果用户的问题涉及财务、基本面或业绩，至少包含：

- 营收、归母净利润、ROE、毛利率、EPS、同比增速指标卡。
- 趋势图：营收和净利润至少一个折线/柱状组合图，ROE/毛利率至少一个趋势图。
- 报告期表格：展示报告期、营收、净利润、ROE、毛利率、同比。
- 简短分析摘要：只总结数据事实和风险提示，不构成投资建议。

## 推荐页面结构

通用结构只作为兜底。优先使用 `references/scenario_templates.md` 中对应场景的组件矩阵：

- 顶部：紧凑报告摘要、数据状态和场景结论。
- 中上：该场景最关键的痛点组件，例如持仓矩阵、候选矩阵、K 线主图、财务趋势或回测净值。
- 中部：图表、指标矩阵、风险或质量解释。
- 下部：明细表、数据信源渠道、缺失字段、限制和非投资建议声明。

## 图表实现建议

不要为了图表额外安装依赖。优先使用以下方式：

- 用 SVG 实现 K 线、均线、成交量、折线、柱状图。
- 用 CSS grid/table 实现数据明细和指标矩阵。
- 尺寸必须响应式，图表容器要有稳定高度，避免数据加载后布局跳动。
- A 股颜色：上涨红色，下跌绿色，中性灰色。
- 所有涨跌、收益、回撤、风险和质量状态必须使用语义染色，不允许只靠文字表达。A 股涨跌使用红涨绿跌；回撤、风险暴露、亏损、缺失和失败要用绿色/红色/琥珀色等明确区分，且颜色含义在同一页面保持一致。
- K 线/OHLC 图必须有背景网格、价格刻度、日期刻度、MA 图例和 hover `title` 或等效 tooltip；成交量副图必须和 K 线共用涨跌颜色。
- 多标的柱状/横向对比图必须按正负或有利/不利分色，并展示数值标签，不能只给灰色进度条。
- 数据质量、信源、缺失字段和限制说明要有状态色：`ok`/可用为绿色，`warning`/缺失为琥珀色，`error`/失败为红色。
- 图表必须有坐标/日期/价格标签或 tooltip/悬浮信息中的至少一种；金融主图建议同时具备坐标标签和 tooltip。
- 图表旁边必须有数值摘要或表格 fallback。K 线/OHLC 的可访问性天然较弱，必须提供最近数据表和关键数值面板。
- 多标的页中的 K 线缩略图必须保留足够宽度，数字不要被挤压成竖排；如果卡片宽度不足，隐藏次要指标或改成横向滚动/表格，而不是让金额、MA 和百分比逐字断行。
- 实时/大量时序图表一次可见点位要克制；蜡烛图桌面建议不超过 500 根可见，移动端优先缩短窗口或分页/切换时间范围。
- 趋势、收益、风险、质量状态不能只靠颜色区分；同时使用文本、图例、图标、填充/描边差异或表格列。

## 视觉质量门槛

生成页面必须看起来像专业金融/量化工作台：

- 默认风格是 Data-Dense Dashboard：中性底、清晰边框、紧凑指标、稳定网格、可扫描表格。
- 首屏必须出现真实金融数据或可执行操作，不要用大 slogan、模板名、深色空卡或品牌 hero 占位。
- 首屏桌面端必须在 900px 高度内同时看到：核心结论/摘要、至少 4 个真实指标、一个图表/矩阵/表格入口和更新时间或数据状态。
- 当真实指标暂缺时，至少 4 个核心指标位置必须显示明确的“待接入/待确认”状态，图表区域必须显示有信息量的空态文案，而不是只显示空坐标轴或 `-`。
- 常规卡片圆角不超过 8px，避免大面积渐变、装饰背景、单色调页面和“报告封面式”布局。
- 关键数字使用 tabular/monospace 风格；长标题、长公告、长信源名称必须能换行、截断或在内部滚动，不得撑爆卡片。
- 颜色必须语义化：A 股涨跌可红涨绿跌；运行/信息用蓝，缺失/警告用 amber，失败/风险用 red，成功/可用用 emerald。
- 字体层级克制，工具型页面标题不要过大；数字使用 tabular/monospace 风格以减少跳动。
- 交互动效只用于 hover、展开、过滤、刷新、sheet/modal 进入退出；默认 150-300ms，尊重 reduced-motion。
- 375px、768px、1440px 下不能有文字重叠、按钮挤爆、表格遮挡或图表高度塌陷。
- 375px 移动端 `documentElement.scrollWidth` 不得大于 `clientWidth`；如果表格很宽，给 `.table-wrap` 设置 `overflow-x:auto; max-width:100%`，同时给 grid 子项设置 `min-width:0`。

## Next.js 代理示例

QuantPilot 新建项目默认已经预置同源代理和基础金融看板。如果下列文件已存在，优先复用并增强，不要重复创建冲突目录：

- `app/api/market/[...path]/route.ts`
- `app/page.tsx`
- `app/globals.css`

如果代理缺失，按下面示例创建：

```ts
// app/api/market/[...path]/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const target = new URL(`http://127.0.0.1:8000/api/v1/${path.join('/')}`);
  url.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  const response = await fetch(target, { cache: 'no-store' });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { 'Content-Type': response.headers.get('Content-Type') ?? 'application/json' },
  });
}
```

前端调用：

```ts
await fetch('/api/market/quotes/realtime/600519', { cache: 'no-store' });
await fetch('/api/market/quotes/history/600519?period=daily&adjustment=qfq&limit=120', { cache: 'no-store' });
```

## 预置模板增强规则

1. 优先保留 `data_file/final/dashboard-data.json` 的读取逻辑。
2. 可以扩展 `TrendChart`、指标卡片、数据表和来源说明，但不要退回静态样例页。
3. 如果任务涉及指数或 ETF，保留 `asset_type`、信源渠道、K 线、成交量和技术指标展示。
4. 如果任务涉及个股基本面，再补充财务趋势、ROE/毛利率和公告列表。
5. 如果任务涉及多标的，优先读取 `assets[]` 和 `comparison`，保留单标的主图作为可选细节，不要把多标的页面降级成主标的页面。
6. 页面最终仍需通过平台自动验证：build、HTTP 200、final 数据、evidence、图表和 `/api/market`。
7. 页面必须通过产物策略验证：无外部 CDN/远程资源、无 mock/static 数据、无明文密钥，且保留 `.quantpilot/run_plan.json`、final 数据和 evidence 标准产物。

## 生成页面验收清单

提交前逐项自检：

- `app/page.tsx` 包含 `data_file/final/dashboard-data.json` 或 `/api/market` 数据入口。
- `app/page.tsx` 包含 `<svg>` 或 `<canvas>` 图表实现，且不是装饰性占位图。
- 趋势类任务包含 K 线/OHLC、成交量和至少两条均线。
- 财务类任务包含财务趋势、报告期表格和指标卡。
- 回测类任务包含净值曲线、回撤/收益/胜率、交易明细和参数假设。
- 多标的、组合或风控类任务如果 final 数据包含 `correlation`，页面必须展示相关性矩阵或 Top pairs；如果包含 `liquidity`，页面必须展示成交额、换手代理、Amihud 或流动性等级。
- 如果 final 数据包含 `valuation`，页面必须展示防守/中性/进攻估值情景、核心假设和缺失字段 warning，不要把情景价包装成承诺收益。
- 如果 final 数据包含 `trendTemplate`，页面必须展示趋势状态、样本长度、MA20/MA60、回撤、量能比和确认/减仓/观察触发条件。
- 页面必须展示或隐式覆盖 `visualization.required_components`，并把无法渲染的组件写入数据质量或缺口说明。
- 页面展示数据信源渠道、更新时间、样本量或数据质量限制；缓存状态和文件路径只作为证据附注。
- 没有 Next.js 默认页文案，没有 `SAMPLE_DATA`、`MOCK_DATA`、`STATIC_QUOTES` 等静态样例数据。
- 没有 `https://cdn...`、`unpkg`、`jsdelivr`、`cdnjs`、远程 `<script>`、远程 `<link>`、远程字体或浏览器直连 `http(s)` 接口。
- 不修改父级 QuantPilot 平台工程，只修改当前生成项目。

## 禁止事项

- 不要编造行情、财报、公告、K 线。
- 不要只写说明文字而不生成页面。
- 不要把图表做成静态截图。
- 不要只做“趋势占位区”；必须呈现真实数据或真实错误状态。
- 不要创建和任务无关的示例项目。
- 不要修改父级 QuantPilot 平台工程。
- 不要启动开发服务器；QuantPilot 会管理预览服务。
- 不要通过 Bash 重定向或 heredoc 写源码文件；这会破坏平台的过程记录和自动验证。
- 不要通过 CDN 或远程 npm 模块加载图表库；金融图表优先用平台模板内置的 SVG/CSS/React 组件实现。
