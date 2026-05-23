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

## 标准工作流

1. 确认用户问题需要哪些数据：实时行情、历史 K 线、财务、公告、组合对比。
2. 缺数据时先调用对应取数 skill：
   - 实时行情：`quant-market-data`
   - 历史 K 线：`quant-a-share-history`
   - 财务趋势：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 不确定数据源：`quant-data-registry`
3. 设计看板信息架构：先展示结论和核心指标，再展示图表和数据表。
4. 实现页面文件并确保有加载、错误、空数据、刷新状态。
5. 页面刷新数据时优先创建同源 API route 代理到 `http://127.0.0.1:8000`，避免浏览器 CORS 或网络策略影响。
6. 完成后简短说明修改了哪些页面和看板现在包含哪些数据视图。

## A 股行情看板最低标准

如果用户的问题涉及 A 股个股、指数或组合，至少包含：

- 实时行情指标卡：最新价、涨跌幅、开盘、最高、最低、昨收、成交量、成交额、市值、行情时间。
- K 线主图：蜡烛图或 OHLC 图，必须能区分涨跌；叠加 MA5、MA10、MA20 中至少两条均线。
- 成交量副图：与 K 线共用日期维度，涨跌颜色遵循 A 股习惯。
- 量化指标区：区间涨跌幅、最大回撤、年化/区间波动率、均线多空状态、放量/缩量提示、突破/跌破提示。
- 数据明细表：至少展示最近 10 根 K 线的日期、开高低收、成交额、涨跌幅、换手率。
- 数据来源：展示 `source`、`quote_time`、`fetched_at`、周期和复权方式。

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

推荐在生成项目中创建同源代理，例如：

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

## 禁止事项

- 不要编造行情、财报、公告、K 线。
- 不要只写说明文字而不生成页面。
- 不要把图表做成静态截图。
- 不要只做“趋势占位区”；必须呈现真实数据或真实错误状态。
- 不要创建和任务无关的示例项目。
- 不要修改父级 QuantPilot 平台工程。
- 不要启动开发服务器；QuantPilot 会管理预览服务。
