# 05. 评测、运维与质量门

目标：知道如何判断一个生成工作空间是否真的可用，以及失败时从哪里看原因。

![评测平台](assets/eval-platform.png)

## 评测平台

评测平台用于把“生成页面好不好、数据有没有用、能不能自修复”变成可重复检查的任务。

评测和普通测试不完全一样。普通单元测试更多验证代码函数是否符合预期；Agent 评测要验证一次完整生成行为，包括需求理解、数据获取、页面实现、证据留存和修复能力。它更像“产品级回归测试”。

| 模块 | 作用 |
| --- | --- |
| 测试用例 | 单个问题、输入、期望产物和验证规则 |
| 评测集 | 一组测试用例，支持分页和运行管理 |
| 评测器 | dry-run、用例执行、报告生成和失败分类 |
| 运行队列 | 观察等待中、运行中和失败任务 |
| 运行记录 | 保存历史结果、耗时、失败原因和修复建议 |
| 失败修复 | 把验证失败转成可执行 repair plan |

评测用例应尽量覆盖真实问题，而不是只测最容易成功的 prompt。一个好的评测用例通常包含：

- 明确的用户问题。
- 需要哪些真实数据。
- 页面必须出现哪些关键模块。
- 数据质量或证据要求。
- 失败时应该如何分类。

例如“生成贵州茅台近 5 年 K 线看板”不只检查能不能画线，还要检查是否有主 K 线、MA 指标、数据来源、时间范围、缺失字段说明和移动端可读性。

常用命令：

```bash
npm run check:benchmark-coverage
npm run check:eval-schedule
npm run eval:ci
npm run benchmark:quant
```

## 运维平台

![运维平台](assets/ops-platform.png)

运维平台用于查看工作空间健康、生成链路观测、基础环境健康和日志。

评分口径、日志阅读方式和降级模式的更完整说明见 [运维平台使用与评分指南](../ops-platform-guide.md)。

| 区域 | 关注点 |
| --- | --- |
| 工作空间健康 | 产物是否齐全、验证是否通过、预览是否可访问 |
| 生成链路观测 | 阶段事件、队列状态、trace、错误和耗时 |
| 基础环境健康 | Node、npm、Agent CLI、数据库、TimescaleDB、市场数据后端、Loki 和降级配置 |
| 日志 | 优先读取 Loki 集中日志，Loki 不可用时降级到本地 `tmp/` 和 `.next` 日志 |
| 产物检查 | run plan、data_file、evidence、validation、visual report |
| 修复记录 | repair plan、修复次数、最后失败原因 |

运维平台的价值不是“再做一个页面”，而是把生成链路里分散的事实集中起来：

- 工作空间是否缺文件。
- 最后一次验证是否过期。
- Agent 是否还在运行或已经卡住。
- 数据预取、验证、修复这些阶段各自耗时多久。
- 前端、后端、Loki、数据库这些基础组件是否可达。

如果 Loki 已启动，日志会从集中日志读取；如果没有启动，系统按降级配置读取本地日志。这样本地开发不会因为少一个组件而完全不可用，生产或 CI 又可以通过 `strict` 模式把缺组件视为失败。

## 最小质量门

平台代码：

```bash
npm run lint
npm run type-check
npm run check:skills
npm run check:validation-repair
```

生成页面：

```bash
npm run check:project-visual
```

首页视觉 smoke：

```bash
npm run check:homepage
```

质量门的基本原则是：越靠近底层的能力，越需要自动检查；越靠近视觉和交互的能力，越需要截图和人工复核结合。只跑 lint 不能证明页面好看，只看截图也不能证明数据契约正确。

市场数据后端：

```bash
cd services/market-data
uv run ruff check .
uv run pytest
```

## 常见失败判断

| 现象 | 优先检查 |
| --- | --- |
| 页面显示“看板验证未通过” | `.quantpilot/validation.json` 和 `validation-repair-plan.json` |
| 只有小趋势图，没有主图 | `visual-validation.json` 和可视化 skill 模板匹配 |
| 多股票对比横向溢出 | 页面布局、表格宽度、移动端断点 |
| K 线为空或只剩一天 | `data_file/final/dashboard-data.json` 是否只写入最新日 |
| 成交额/换手率缺失 | `quant.stock_bars` 增强字段和 Baostock 补数状态 |
| 页面编译失败 | 生成项目的 `npm run build` 输出 |

评测和运维不是两个孤立模块：评测负责持续发现问题，运维负责解释单个工作空间为什么失败。

## 排障顺序

遇到失败时建议按层次排查，不要一上来就改代码：

1. 环境层：`npm run doctor`，确认前端、后端、数据库、Loki 和 CLI 状态。
2. 数据层：确认本地库或 final data 里是否真的有需要字段。
3. 契约层：确认 `run_plan`、`data_file`、`evidence` 和 validation 是否存在。
4. 页面层：打开预览或截图，看是否布局、交互、图表渲染失败。
5. Skill 层：如果多次生成都犯同类错误，再把规则沉淀到 skill。
