---
name: quant-run-planner
description: Use this skill at the beginning of every QuantPilot quantitative analysis task to create or update .quantpilot/run_plan.json before fetching data or generating dashboards.
---

# QuantPilot 运行规划能力

本 skill 用于把用户问题转换为可执行的量化分析计划。任何股票、行情、财务、公告、技术分析或可视化任务，都必须先使用本能力规划，再取数和生成页面。

## 必做产物

在当前生成项目中更新：

```text
.quantpilot/run_plan.json
.quantpilot/events.jsonl
```

`run_plan.json` 至少包含：

- `status`: `planned`
- `question`: 用户原始问题
- `capabilityId`: 当前 `.quantpilot/manifest.json` 中的能力 ID
- `symbols`: 待分析标的，未知时先留空并在下一步调用 `quant-symbol-resolver`
- `timeRange`: 用户要求或默认范围
- `dataRequirements`: 需要调用的数据接口
- `analysisSteps`: 后续执行步骤
- `visualization`: 预期图表和页面模块
- `validationRules`: 完成前必须检查的规则

`events.jsonl` 追加一行规划摘要，示例：

```json
{"event_type":"run_planned","stage":"planning","status":"success","summary":"已生成个股诊断计划，准备解析标的并获取行情、K 线、财务和公告数据。"}
```

## 标准流程

1. 读取 `.quantpilot/manifest.json`，确认当前 `capabilityId`、required skills、数据接口和验证规则。
2. 从用户问题识别：
   - 标的名称或代码
   - 时间范围
   - 分析类型
   - 是否需要可视化页面
3. 写入或更新 `.quantpilot/run_plan.json`。
4. 向 `.quantpilot/events.jsonl` 追加可见执行摘要。
5. 然后才调用后续数据 skill：
   - 标的不明确：`quant-symbol-resolver`
   - 实时行情：`quant-market-data`
   - 历史走势：`quant-a-share-history`
   - 指数/ETF：`quant-index-etf-market`
   - 基本面：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 看板生成：`quant-visualization-html`

## 禁止事项

- 不要跳过规划直接取数或生成页面。
- 不要把 `run_plan.json` 写成自然语言文档；必须是 JSON。
- 不要把未获取的数据标记为完成。
- 不要在规划阶段编造行情、财务或公告数据。
