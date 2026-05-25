---
name: quant-visualization-html
description: Use this skill to generate a real visual Next.js/HTML quantitative dashboard after market data has been fetched or whenever the user asks for a visualization page.
---

# QuantPilot 金融可视化看板能力

这个 skill 负责把已获取的行情、财务、公告和分析结果转换为真正可运行的可视化页面。它不是“写分析说明”的 skill；触发后必须产出或更新页面文件。

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

## 标准工作流

1. 确认用户问题需要哪些数据：实时行情、历史 K 线、财务、公告、组合对比。
2. 缺数据时先调用对应取数 skill：
   - 实时行情：`quant-market-data`
   - 历史 K 线：`quant-a-share-history`
   - 财务趋势：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 不确定数据源：`quant-data-registry`
3. 先读取现有 `app/page.tsx`、`app/globals.css` 和 `data_file/final/dashboard-data.json`，确认模板已有组件和数据字段。
4. 设计看板信息架构：先展示结论和核心指标，再展示图表、数据表、数据质量和来源。
5. 实现页面文件并确保有加载、错误、空数据、刷新状态。
6. 页面刷新数据时优先复用或创建同源 API route 代理到 `http://127.0.0.1:8000`，避免浏览器 CORS 或网络策略影响。
7. 使用 `quant-data-quality` 写入 `evidence/sources.json` 与 `evidence/data_quality.json`，记录来源、接口、时间戳、样本长度、缺失字段、警告和限制。
8. 将最终看板数据写入 `data_file/final/dashboard-data.json`，字段中保留 `symbol`、`source`、`fetched_at`、`quote_time` 或对应数据源时间。
9. 完成后简短说明修改了哪些页面和看板现在包含哪些数据视图。

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
- 页面优先保留平台标准模板的 `DATA_FILE`、`readDashboardData()`、`getBars()`、`TrendChart` 和 `data-source-file={DATA_FILE}` 结构，只在其上增强展示。
- 如果平台已经预取出 `dashboard-data.json`，不要再用空对象覆盖它，也不要把 `kline.bars` 改成只有模型自己知道的字段名。

## A 股行情看板最低标准

如果用户的问题涉及 A 股个股、指数或组合，至少包含：

- 实时行情指标卡：最新价、涨跌幅、开盘、最高、最低、昨收、成交量、成交额、市值、行情时间。
- K 线主图：蜡烛图或 OHLC 图，必须能区分涨跌；叠加 MA5、MA10、MA20 中至少两条均线。
- 成交量副图：与 K 线共用日期维度，涨跌颜色遵循 A 股习惯。
- 量化指标区：区间涨跌幅、最大回撤、年化/区间波动率、均线多空状态、放量/缩量提示、突破/跌破提示。
- 数据明细表：至少展示最近 10 根 K 线的日期、开高低收、成交额、涨跌幅、换手率。
- 数据来源：展示 `source`、`quote_time`、`fetched_at`、周期和复权方式。
- 数据质量：展示 evidence 或 final 数据中的 `data_quality`、`warnings`、缓存状态和样本长度。

## 多标的对比看板最低标准

如果最终数据包含 `assets[]` 或用户问题包含“对比/组合/相对强弱”，至少包含：

- 标的覆盖：页面显式展示 `requestedSymbols` 或 `assets[].symbol` 中的全部标的。
- 指标矩阵：每个标的展示最新价、涨跌幅、区间收益、最大回撤、波动、成交额或成交量。
- 对比图表：至少一个 SVG/canvas 图表比较区间收益；另一个图表或矩阵比较波动/回撤。
- 相对强弱摘要：展示收益领先、回撤较小、波动较低等结果，结果必须来自 `comparison.rows[]` 或 `assets[].computedMetrics`。
- 数据来源：逐只标的展示 `source`、`as_of/quote_time`、`fetched_at` 或 evidence 中对应来源。

## 财务看板最低标准

如果用户的问题涉及财务、基本面或业绩，至少包含：

- 营收、归母净利润、ROE、毛利率、EPS、同比增速指标卡。
- 趋势图：营收和净利润至少一个折线/柱状组合图，ROE/毛利率至少一个趋势图。
- 报告期表格：展示报告期、营收、净利润、ROE、毛利率、同比。
- 简短分析摘要：只总结数据事实和风险提示，不构成投资建议。

## 推荐页面结构

- 顶部工具栏：标的名称、代码、刷新按钮、数据状态。
- 左上：实时行情指标卡。
- 右上：量化信号摘要。
- 中部大图：K 线 + 均线。
- 中部副图：成交量 / 成交额。
- 下部：财务趋势、公告事件、最近 K 线表格或报告期表格。

## 图表实现建议

不要为了图表额外安装依赖。优先使用以下方式：

- 用 SVG 实现 K 线、均线、成交量、折线、柱状图。
- 用 CSS grid/table 实现数据明细和指标矩阵。
- 尺寸必须响应式，图表容器要有稳定高度，避免数据加载后布局跳动。
- A 股颜色：上涨红色，下跌绿色，中性灰色。
- 图表必须有坐标/日期/价格标签或 tooltip/悬浮信息中的至少一种。

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
3. 如果任务涉及指数或 ETF，保留 `asset_type`、缓存状态、K 线、成交量和技术指标展示。
4. 如果任务涉及个股基本面，再补充财务趋势、ROE/毛利率和公告列表。
5. 如果任务涉及多标的，优先读取 `assets[]` 和 `comparison`，保留单标的主图作为可选细节，不要把多标的页面降级成主标的页面。
6. 页面最终仍需通过平台自动验证：build、HTTP 200、final 数据、evidence、图表和 `/api/market`。

## 生成页面验收清单

提交前逐项自检：

- `app/page.tsx` 包含 `data_file/final/dashboard-data.json` 或 `/api/market` 数据入口。
- `app/page.tsx` 包含 `<svg>` 或 `<canvas>` 图表实现，且不是装饰性占位图。
- 趋势类任务包含 K 线/OHLC、成交量和至少两条均线。
- 财务类任务包含财务趋势、报告期表格和指标卡。
- 回测类任务包含净值曲线、回撤/收益/胜率、交易明细和参数假设。
- 多标的、组合或风控类任务如果 final 数据包含 `correlation`，页面必须展示相关性矩阵或 Top pairs；如果包含 `liquidity`，页面必须展示成交额、换手代理、Amihud 或流动性等级。
- 页面展示数据来源、更新时间、缓存状态或数据质量限制。
- 没有 Next.js 默认页文案，没有 `SAMPLE_DATA`、`MOCK_DATA`、`STATIC_QUOTES` 等静态样例数据。
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
