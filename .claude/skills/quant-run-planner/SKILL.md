---
name: quant-run-planner
description: Use this skill at the beginning of every QuantPilot quantitative analysis task to create or update .quantpilot/run_plan.json before fetching data or generating dashboards.
---

# QuantPilot 运行规划能力

本 skill 用于把用户问题转换为可执行的量化分析计划。任何股票、行情、财务、公告、技术分析或可视化任务，都必须先使用本能力规划，再取数和生成页面。

## 意图澄清门禁

规划前先判断用户问题是否已经具备执行所需的关键输入。可以运行辅助脚本：

```bash
python .claude/skills/quant-run-planner/scripts/intent_clarifier.py --question "<用户问题>" --capability "<capabilityId>"
```

如果脚本或人工判断发现缺少关键输入，必须先写入 `status: "needs_clarification"` 的 `run_plan.json`，再向用户追问，停止后续取数和页面生成。

需要追问的典型情况：

- 缺少标的：例如“帮我分析一下”“这个股票怎么样”。
- 对比任务缺少至少两个标的：例如“帮我对比一下哪个更好”。
- 投资建议类问题缺少周期、风险偏好或市场范围：例如“推荐一个可以买的股票”。
- 只有标的但没有分析方向：例如“宁德时代”。

不需要追问的情况：

- 已给出标的和方向，例如“贵州茅台最近财务怎么样？”。
- 已给出标的但问题是泛化诊断，例如“通富微电的股票怎么样”，可默认做综合诊断。
- 只缺时间范围或输出形式时，使用默认值：趋势默认最近 120 个交易日，财务默认最近报告期，输出默认可验证看板。

如果任务文本包含“承接上一轮澄清”“原始问题”“用户补充”，必须把原始问题和补充信息合并成一个完整任务来判断。补充后已经足够明确时，直接把 `run_plan.json` 改回 `status: "planned"` 并继续取数；如果仍缺少信息，只追问剩余缺口。

## 必做产物

在当前生成项目中更新：

```text
.quantpilot/run_plan.json
.quantpilot/events.jsonl
```

`run_plan.json` 至少包含：

- `status`: `planned` 或 `needs_clarification`
- `question`: 用户原始问题
- `capabilityId`: 当前 `.quantpilot/manifest.json` 中的能力 ID
- `symbols`: 待分析标的，未知时先留空并在下一步调用 `quant-symbol-resolver`
- `timeRange`: 用户要求或默认范围
- `dataRequirements`: 需要调用的数据接口
- `analysisSteps`: 后续执行步骤
- `visualization`: 预期图表和页面模块
- `validationRules`: 完成前必须检查的规则
- `clarification`: 仅在 `needs_clarification` 时写入，包含 `required`、`reason`、`missing` 和 `questions`

`visualization` 必须包含场景模板字段，避免后续页面生成退化成通用看板：

- `templateId`: 例如 `holding-analysis`、`stock-selection`、`technical-timing`
- `name`: 模板中文名
- `scenario`: 模板适用场景
- `panels`: 必备页面组件
- `painPoints`: 这个场景必须解决的用户痛点
- `optionalPanels`: 有数据时增强的组件
- `dataSignals`: 页面应优先使用的数据字段
- `finalDataContract`: 最终数据应保留的关键结构

`events.jsonl` 追加一行规划摘要，示例：

```json
{"event_type":"run_planned","stage":"planning","status":"success","summary":"已生成个股诊断计划，准备解析标的并获取行情、K 线、财务和公告数据。"}
```

需要澄清时追加：

```json
{"event_type":"intent_clarification_required","stage":"planning","status":"warning","summary":"任务缺少标的，需要先向用户确认股票、指数或 ETF。"}
```

## 标准流程

1. 读取 `.quantpilot/manifest.json`，确认当前 `capabilityId`、required skills、数据接口和验证规则。
2. 从用户问题识别：
   - 标的名称或代码
   - 时间范围
   - 分析类型
   - 是否需要可视化页面
3. 如果缺少关键输入，写入 `needs_clarification`，输出 1-3 个追问问题并停止。
4. 如果意图足够明确，写入或更新 `.quantpilot/run_plan.json`。
5. 向 `.quantpilot/events.jsonl` 追加可见执行摘要。
6. 然后才调用后续数据 skill：
   - 标的不明确：`quant-symbol-resolver`
   - 实时行情：`quant-market-data`
   - 历史走势：`quant-a-share-history`
   - 指数/ETF：`quant-index-etf-market`
   - 基本面：`quant-fundamental-financials`
   - 公告事件：`quant-announcement-events`
   - 看板生成：`quant-visualization-html`

## 可见过程叙述要求

使用本 skill 时，必须在对话中输出用户能复盘的中文执行日志，不要只展示工具流水账。

推荐格式：

```markdown
现在使用 `quant-run-planner` 建立本次分析计划：先确认标的、时间范围、所需数据和验收规则。

• Todo List (0/5 completed)
1. ⏳ 解析标的和时间范围
2. ⏳ 获取行情、K 线和指标数据
3. ⏳ 生成 sources/data_quality/final 数据
4. ⏳ 生成可视化看板
5. ⏳ 自动验证 build、HTTP、数据文件和图表
```

每完成一个阶段后，都要补一句清晰的结果摘要，例如：

- `run_plan.json` 已写入，确认需要实时行情、90 日 K 线、成交量和技术指标。
- 已解析到通富微电 `002156`，下一步请求东方财富行情和历史 K 线。
- 数据质量检查通过，最终数据文件覆盖 quote、history、indicators 和 sources。

## 禁止事项

- 不要跳过规划直接取数或生成页面。
- 不要在 `needs_clarification` 状态下取数、写 final 数据或生成页面。
- 不要把 `run_plan.json` 写成自然语言文档；必须是 JSON。
- 不要把未获取的数据标记为完成。
- 不要在规划阶段编造行情、财务或公告数据。
