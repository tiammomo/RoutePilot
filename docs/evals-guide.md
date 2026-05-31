# Agent 评测指南

评测模块用于持续检查 Agent 生成工作空间的能力，覆盖用例管理、评测集、运行队列、报告、模型对比、Skill 版本影响和失败修复。

入口：

```text
http://localhost:3000/eval-platform
```

## 运行时

默认评测运行时：

- 执行器：`Claude Code`
- 模型：`MiniMax M2.7`
- Reasoning：不展示、不传递

可选运行时：

- 执行器：`Codex CLI`
- 模型：`GPT-5.5`
- Reasoning：`low`、`medium`、`high`、`xhigh`

## 页面分栏

| 分栏 | 作用 |
| --- | --- |
| 仪表盘 | 总体通过率、失败用例、运行队列和最新报告 |
| 测试用例 | 搜索固定用例，运行单用例或当前筛选范围 |
| 评测集 | 按能力、输入类型和专项场景组织批量回归，支持分页 |
| 评测器 | 配置运行器、模型、范围和推理强度，执行 dry-run |
| 运行队列 | 查看排队、运行中、已完成和可取消任务 |
| 运行记录 | 浏览历史报告、模型表现和 Skill 版本影响 |
| 失败修复 | 汇总失败用例、修复单和 warning 用例 |

## 评测集

评测集由平台根据固定用例自动构建：

- `全部用例`
- 按能力域分组
- 按输入/产物类型分组
- 视觉与截图专项
- 澄清链路专项

页面支持搜索、分类筛选、分页、选择当前评测集和直接运行当前评测集。

## 好用例怎么写

评测不是为了证明 Agent “大概能跑”，而是为了把真实会失败的地方固定下来。一个好的用例应该同时写清楚输入、数据、页面、证据和失败分类。

| 维度 | 应该写清楚 |
| --- | --- |
| 用户输入 | 用户会怎么说，是否带截图，是否有歧义 |
| 数据需求 | 需要哪些标的、时间范围、字段和数据源 |
| 页面要求 | 必须出现哪些图表、表格、指标或交互 |
| 证据要求 | `sources.json`、`data_quality.json` 里应能追溯什么 |
| 验证重点 | build、HTTP、视觉、契约、数据绑定还是移动端 |
| 失败分类 | 缺数据、理解错、页面丑、验证失败、运行时错误或 skill 规则缺失 |

例如“生成通富微电近 5 年 K 线分析”不能只看页面标题。它至少应该检查：真实 K 线数量、MA5/10/20/30/60、成交量、数据来源、时间范围、缺字段说明、红涨绿跌、移动端不横向炸开。

## 失败以后怎么处理

评测失败后不要急着改 prompt。先分三步看：

1. 看报告：确认失败项是数据、构建、视觉、契约还是 Agent 运行时。
2. 看产物：打开对应 workspace 的 `.quantpilot/validation.json`、`artifact-contracts.json` 和 `visual-validation.json`。
3. 看复发性：如果同类失败出现多次，再沉淀到 skill 或模板；如果是单个数据源问题，优先修数据链路。

评测的最终产物不只是分数，而是可复用的修复知识。一次失败如果只靠手工改页面解决，下次生成仍然可能再犯；一次失败如果沉淀到 skill、契约或数据源规则，后续所有工作空间都会受益。

## 评测器 dry-run

评测器的“模拟链路”不会真正启动 benchmark，它会验证：

- 选择范围是否可解析。
- 运行器和模型是否存在。
- benchmark 脚本是否可用。
- 报告目录、队列目录和修复单目录是否可写。
- 命令是否能构造。
- 报告解析和修复单存储链路是否可达。

API：

```text
POST /api/evals
action=simulate-flow
```

## 命令行运行

```bash
npm run benchmark:quant
npm run benchmark:quant -- --case stock-fundamental-maotai
npm run benchmark:quant -- --case runtime-registry-codex-gpt55 --cli codex --model gpt-5.5 --reasoning-effort low
```

相关检查：

```bash
npm run check:benchmark-coverage
npm run check:eval-schedule
npm run eval:ci
```

## 报告目录

评测报告写入：

```text
tmp/quantpilot-benchmark-reports/
tmp/quantpilot-eval-queue/
tmp/quantpilot-eval-repairs/
```

这些目录不进入 Git。

## API

```text
GET /api/evals
POST /api/evals action=start-benchmark
POST /api/evals action=simulate-flow
POST /api/evals action=cancel-benchmark
POST /api/evals action=update-schedule
POST /api/evals action=check-schedule
```

## CI 阻断策略

CI 侧建议至少保留：

- benchmark 覆盖检查。
- eval schedule 检查。
- eval ci gate。
- lint 和 type-check。

如果某次改动涉及 skills、生成契约、验证逻辑或数据后端，应优先补跑相关 benchmark。
