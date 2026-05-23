---
name: quant-a-share-history
description: Use this skill to fetch A-share historical K-line data for trend analysis, returns, drawdown, volatility, and dashboard visualizations.
---

# QuantPilot A 股历史行情能力

从 QuantPilot 后端获取东方财富历史 K 线。适用于趋势、收益率、回撤、成交额和波动分析。

## API

```bash
curl 'http://127.0.0.1:8000/api/v1/quotes/history/600519?period=daily&adjustment=qfq&limit=120'
curl 'http://127.0.0.1:8000/api/v1/indicators/technical/600519?period=daily&adjustment=qfq&limit=120'
curl 'http://127.0.0.1:8000/api/v1/quotes/history/000300?period=daily&adjustment=qfq&limit=240'
```

参数：

- `period`: `daily`、`weekly`、`monthly`、`minute1`、`minute5`、`minute15`、`minute30`、`minute60`
- `adjustment`: `none`、`qfq`、`hfq`
- `limit`: 1 到 1000

## 工作流程

1. 必要时先使用 `quant-symbol-resolver` 解析证券。
2. 先使用 `quant-data-registry` 确认历史行情能力状态；如果状态为 `degraded`，调用接口失败时要展示真实错误并说明外部源暂不可用。
3. 选择合适周期：默认 `daily`，长期趋势用 `weekly/monthly`，盘中分析用分钟线。
4. 默认使用前复权 `qfq`，除非用户明确要求不复权或后复权。
5. 基于返回 `bars` 计算收益、回撤、波动等指标。
6. 优先调用 `indicators/technical` 获取后端标准化技术指标，减少页面临场重复计算。
7. 指数或 ETF 任务配合 `quant-index-etf-market`，不要强制请求个股财务或公告。
8. 如果历史行情失败，可降级结合实时行情、财务摘要和公告事件做分析，但必须说明缺少历史序列。
9. 需要页面时，把 K 线和指标交给 `quant-visualization-html`。

## 禁止事项

- 不要编造历史价格。
- 不要把实时行情当历史行情使用。
