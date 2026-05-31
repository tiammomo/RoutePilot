# QuantPilot

QuantPilot 是面向量化投研、金融数据分析和可视化看板生成的 AI 工作台。用户用自然语言提出研究问题，平台会调度 Agent Runtime、读取真实数据、生成可运行工作空间，并通过自动验证、视觉检查、产物契约和评测链路把结果收敛到“好看、可用、可追溯”。

生成内容仅用于研究、复盘和辅助决策，不构成投资建议、收益承诺或即时交易指令。

如果你是第一次打开这个项目，不必急着把所有模块都看完。先把本地环境跑起来，再按下面的学习路径一层一层读。QuantPilot 的能力比较多，但核心脉络其实很清楚：真实数据进入本地库，Agent 基于 skills 生成工作空间，平台再用验证和评测把结果收紧。

## 核心能力

- AI 工作台：任务入口、项目聊天、工作空间预览、任务记录和自动修复链路。
- 量化数据底座：PostgreSQL + TimescaleDB + Redis，承载应用状态、时序行情、估值因子、缓存和补数任务状态。
- 市场数据服务：Python/FastAPI 后端，提供行情、K 线、财务、公告、指标、补数、基础组件和策略平台接口。
- 策略平台：股票池、ETF/指数池、策略目录、板块资金、基础组件、金融知识和后续回测入口。
- Skills 能力层：管理 `.claude/skills`，沉淀量化规划、数据质量、可视化生成和自修复能力。
- 评测与运维：评测平台、数据平台、运维平台共同覆盖生成质量、数据契约、工作空间健康、运行 trace 和集中日志。

## 快速启动

```bash
npm install
cp .env.example .env
cp .env.example .env.local
```

把 `.env` 或 `.env.local` 中的模型 token 改成自己的值，真实密钥不要提交到 Git。

```bash
npm run db:up
npm run db:init
```

如需集中日志和 Grafana 排查界面，可再启动本地可观测性组件：

```bash
npm run obs:up
```

```bash
cd services/market-data
uv sync --extra baostock --extra akshare
uv run quantpilot-market-api
```

回到项目根目录：

```bash
npm run dev
```

默认访问 `http://localhost:3000`。推荐启动顺序是数据库、可观测性组件、市场数据后端、主前端；不启动 Loki/Grafana 时，运维平台会自动降级到本地文件日志。

## 常用入口

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| AI 工作台 | `http://localhost:3000` | 创建任务、进入项目聊天和预览 |
| 策略平台 | `http://localhost:3000/strategy-platform` | 股票池、ETF/指数池、板块资金、策略目录、基础组件和金融知识 |
| Skills 管理 | `http://localhost:3000/skills` | 编辑、发布、回滚和导入核心 skills |
| 数据平台 | `http://localhost:3000/data-platform` | 查看能力域、数据接口、契约和验证边界 |
| 运维平台 | `http://localhost:3000/ops-platform` | 查看 workspace 健康、产物、队列和 trace |
| 评测平台 | `http://localhost:3000/eval-platform` | 运行评测、管理评测集、查看队列和报告 |

## 常用命令

| 场景 | 命令 |
| --- | --- |
| 前端开发 | `npm run dev` |
| 前端质量门 | `npm run lint && npm run type-check && npm run build` |
| 数据库启动 | `npm run db:up && npm run db:init` |
| 数据库检查 | `npm run db:doctor` |
| Redis CLI | `npm run redis:cli` |
| 可观测性启动 | `npm run obs:up` |
| 可观测性日志 | `npm run obs:logs` |
| Skills 检查 | `npm run check:skills` |
| 验证修复链路检查 | `npm run check:validation-repair` |
| 首页视觉 smoke | `npm run check:homepage` |
| 量化后端 | `cd services/market-data && uv run quantpilot-market-api` |
| 后端质量门 | `cd services/market-data && uv run ruff check . && uv run pytest` |

## 文档导航

项目知识集中放在 `docs/`：

- [文档总览](docs/README.md)
- [教学路径](docs/learning/README.md)
- [项目学习地图](docs/learning/00-project-study-map.md)
- [内部组件学习指南](docs/internal-components.md)
- [文档写作风格指南](docs/documentation-style-guide.md)
- [架构总览](docs/architecture.md)
- [项目结构与分层边界](docs/project-structure.md)
- [基础设施配置](docs/infrastructure.md)
- [行情数据源采集知识库](docs/market-data-source-knowledge.md)
- [策略平台使用与设计指南](docs/strategy-platform-guide.md)
- [运维平台使用与评分指南](docs/ops-platform-guide.md)
- [生成工作空间契约](docs/generated-workspace-contract.md)
- [Skills 治理规范](docs/skills-governance.md)
- [Skills 编写与迭代教程](docs/learning/07-skills-authoring.md)
- [Agent 评测指南](docs/evals-guide.md)
- [本地产物与生成文件边界](docs/local-generated-files.md)
- [故障排查](docs/troubleshooting.md)
- [市场数据服务](services/market-data/README.md)

## 推荐学习路径

如果是第一次接触项目，建议按这个顺序读：

| 阶段 | 文档 | 目标 |
| --- | --- | --- |
| 先建立全局图 | [项目学习地图](docs/learning/00-project-study-map.md) | 知道产品、数据、生成和质量四条主线 |
| 再跑通本地环境 | [本地启动与健康检查](docs/learning/01-quick-start.md) | 拉起数据库、后端、前端和可选观测组件 |
| 理解内部组件 | [内部组件学习指南](docs/internal-components.md) | 把页面、服务、数据、Skills、验证和运维串起来 |
| 学会生成链路 | [AI 工作空间生成链路](docs/learning/02-ai-workspace-generation.md) | 理解 run plan、data、evidence、validation 和 repair plan |
| 学会数据与策略 | [市场数据与策略平台](docs/learning/03-market-data-and-strategy-platform.md) | 理解股票池、K 线、补数、因子和基础组件 |
| 学会 Skills | [Skills 编写与迭代教程](docs/learning/07-skills-authoring.md) | 知道如何修改、发布、打包和验证 skill |

文档维护也算项目能力的一部分。改代码时如果改变了页面入口、组件职责、数据字段、环境变量、SQL 或 skill 行为，请同步更新对应文档；具体写法见 [文档写作风格指南](docs/documentation-style-guide.md)。

## 本地数据与 Git 边界

以下内容默认不进入 Git：`.env`、`.env.local`、`.next/`、`node_modules/`、`data/`、`tmp/`、`public/uploads/`、`public/generated/`、`services/market-data/.venv/`、`services/**/.ruff_cache/`。

首次使用需要的 PostgreSQL / TimescaleDB SQL 放在 `sqls/`。生成工作空间源码和大产物放在 `data/projects/`，平台数据库只保存索引、状态和摘要。

## 本地可观测性

`npm run obs:up` 会拉起 Loki、Grafana 和 Grafana Alloy。Alloy 会采集 Docker 容器日志，并读取 `tmp/runtime/*.log`、评测队列日志和 Next.js dev 日志写入 Loki。Loki 默认宿主机端口是 `3100`，生成项目预览端口池从 `4100` 开始；Grafana 默认入口是 `http://localhost:3001`，默认账号密码来自 `.env`；运维平台的“日志”页会优先展示 Loki 集中日志，同时保留本地文件日志兜底。

## 降级模式

`.env` 中的 `QUANTPILOT_DEGRADATION_MODE` 控制组件缺失时的行为：`auto` 适合本地开发，可选组件缺失时自动降级；`strict` 适合 CI/生产，必需组件缺失会失败；`offline` 会跳过可选外部组件探测，优先使用文件日志、内置数据源注册表和本地兜底数据。可通过 `QUANTPILOT_DATABASE_ENABLED`、`QUANTPILOT_MARKET_API_ENABLED`、`QUANTPILOT_OBSERVABILITY_ENABLED`、`QUANTPILOT_REDIS_CACHE_ENABLED` 等开关精确控制。
