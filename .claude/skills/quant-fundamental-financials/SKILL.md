---
name: quant-fundamental-financials
description: Use this skill to fetch A-share financial summary metrics such as revenue, parent net profit, EPS, ROE, gross margin, and growth rates.
---

# QuantPilot 财务摘要能力

获取上市公司主要财务指标，用于基本面分析、估值解释和看板展示。

## API

```bash
curl 'http://127.0.0.1:8000/api/v1/fundamentals/financials/600519?limit=8'
```

返回重点字段：

- `report_date`
- `data_type`
- `basic_eps`
- `revenue`
- `parent_net_profit`
- `weighted_roe`
- `gross_margin`
- `revenue_yoy`
- `net_profit_yoy`
- `notice_date`

## 工作流程

1. 必要时先用 `quant-symbol-resolver`。
2. 获取最近多个报告期，默认 8 期。
3. 分析收入、利润、ROE、毛利率、同比增速的方向和稳定性。
4. 结合实时价格和历史行情时，分别调用对应 skill。
5. 可视化时优先展示季度趋势、同比变化和核心财务指标卡。

## 禁止事项

- 不要把财务摘要当完整三张表。
- 不要用单期数据下长期结论。
