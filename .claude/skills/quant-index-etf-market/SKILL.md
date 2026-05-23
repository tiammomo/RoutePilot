---
name: quant-index-etf-market
description: Use this skill when the task asks for index or ETF market data such as 沪深300, 创业板指, 中证500, 科创50, or 510300 ETF.
---

# QuantPilot 指数与 ETF 行情能力

本 skill 用于获取指数和 ETF 的实时行情、历史 K 线和技术指标。适用于指数趋势、ETF 走势、市场宽基表现和指数看板。

## 常见标的

- 沪深300：`000300` 或 `1.000300`
- 创业板指：`399006` 或 `0.399006`
- 中证500：`000905` 或 `1.000905`
- 科创50：`000688` 或 `1.000688`
- 沪深300ETF：`510300` 或 `1.510300`

## API

```bash
curl 'http://127.0.0.1:8000/api/v1/symbols/resolve?query=沪深300&count=10'
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/000300'
curl 'http://127.0.0.1:8000/api/v1/quotes/history/000300?period=daily&adjustment=qfq&limit=240'
curl 'http://127.0.0.1:8000/api/v1/indicators/technical/000300?period=daily&adjustment=qfq&limit=240'
```

## 返回要点

- `asset_type` 会区分 `index`、`etf`、`stock`。
- `fetch.cache_status` 标明当前数据来自实时拉取还是本地缓存。
- 指数/ETF 默认不调用个股财务摘要和公告事件。
- 页面或结论必须显示 `source`、`as_of`、`fetched_at` 和数据质量提示。

## 工作流程

1. 先用 `quant-data-registry` 确认指数/ETF 能力可用。
2. 如标的不明确，使用 `quant-symbol-resolver` 解析名称。
3. 调用实时行情接口获取当前价格、涨跌幅、成交额。
4. 调用历史 K 线或 `indicators/technical` 获取趋势、均线、波动率和回撤。
5. 写入 `data_file/raw/<run_id>/` 与 `data_file/final/dashboard-data.json`。
6. 用 `quant-data-quality` 记录来源、缓存状态、样本长度和限制。
7. 需要页面时交给 `quant-visualization-html`，重点展示指数趋势、成交量、均线、波动率和回撤。

## 禁止事项

- 不要把指数当成个股去请求财务报表或公告。
- 不要用个股样例数据代替指数/ETF 数据。
- 不要绕过 QuantPilot 后端直接抓外部数据。
