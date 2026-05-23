---
name: quant-data-registry
description: Use this skill to discover QuantPilot market data capabilities and choose the right backend endpoint before fetching financial data.
---

# QuantPilot 数据源注册表

先查询 QuantPilot 本地数据注册表，再选择具体数据能力。不要凭记忆猜接口。

## API

```bash
curl http://127.0.0.1:8000/api/v1/registry
```

## 工作流程

1. 任务涉及行情、财务、公告、事件或历史数据时，先查注册表。
2. 根据用户问题选择能力：
   - 实时价格：`quant-market-data`
   - 股票代码/名称解析：`quant-symbol-resolver`
   - 历史 K 线：`quant-a-share-history`
   - 指数/ETF 行情：`quant-index-etf-market`
   - 财务摘要：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 可视化：`quant-visualization-html`
3. 输出分析时标明 `source`、`fetched_at`，并说明数据覆盖范围。

## 禁止事项

- 不要跳过注册表直接编造数据源能力。
- 不要把未接入的数据源说成已经可用。
