# moyuan-travel-agent

![Next.js](https://img.shields.io/badge/Next.js-16-111111?logo=next.js)
![React](https://img.shields.io/badge/React-19-149ECA?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent-4B5563)
![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178C6?logo=typescript)
![Docs](https://img.shields.io/badge/Docs-Updated-2563EB)

moyuan-travel-agent 是一个面向真实旅行决策场景的 AI 旅行助手项目，覆盖“问问题 -> 生成方案 -> 调整预算/约束 -> 对比方案 -> 导出分享”的完整链路。

它不是只输出一段长文本，而是尽量把旅行建议整理成可继续操作的结构化结果：每日行程卡、预算联动、候选城市探索、对比模式、冲突检测、导出图片与分享链接。

## 目录

- [快速演示](#快速演示)
- [产品预览](#产品预览)
- [当前核心能力](#当前核心能力)
- [北京旅游数据 Demo](#北京旅游数据-demo)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [本地访问地址](#本地访问地址)
- [快速开始](#快速开始)
- [常用接口](#常用接口)
- [测试与质量](#测试与质量)
- [文档导航](#文档导航)
- [适合继续优化的方向](#适合继续优化的方向)

## 快速演示

![Quick Demo](docs/assets/readme-demo.gif)

## 产品预览

### 1. 对话与流式执行

![对话页](docs/assets/readme-home.png)

### 2. 城市探索与决策卡片

![城市探索](docs/assets/readme-city-explorer.png)

### 3. 行程工具箱与结果整理

![行程结果](docs/assets/readme-itinerary-result.png)

## 当前核心能力

### 对话与 Agent

- 三种对话模式：`direct`、`react`、`plan`
- SSE 流式输出：阶段、工具调用、推理片段、最终答案、执行元数据
- 会话管理：新建、清空、删除、重命名、切换模型
- 高风险问题保护：时效校验、fallback 标记、可信度与风险提示

### 行程结果增强

- 长文本自动拆成每日行程卡
- 行程卡内置预算展示、路线信息、时间段结构化展示
- 预算滑杆：省钱 / 均衡 / 舒适
- 多方案对比：并排比较后继续细化
- 冲突检测：时间冲突、路程过长、闭馆风险，并给出一键修复建议
- Checklist、出发提醒、可信度条、风险提示
- 结果导出：图片长图、分享短链

### 城市探索

- 100+ 城市探索池（当前内置 150+）
- 快速筛选：周末、预算、亲子、少走路、雨天、美食
- 场景入口：`周末快闪 / 亲子省心 / 预算吃好`
- 城市卡片决策信息：预算强度、步行强度、风格标签、推荐理由
- shortlist、收藏池、对比池与详情抽屉：先收集候选，再进入并排对比
- 一键以某座城市继续生成完整旅行方案

### 地图与路线

- 支持真实路线距离预览
- 行程卡中可触发“真实路线”与“按距离重排”
- 当前路线能力基于高德方案接入

## 北京旅游数据 Demo

`feature/hotel-data-demo-ready` 合入后，仓库同时包含一个北京旅游数据工作台 demo。它基于本地 POI、酒店、餐饮、文化地点、UGC 评论特征、高德通勤补全数据和预生成路线库，提供可解释、可调整的北京本地路线规划能力。

核心入口：

- 根目录 Next.js 工作台：`src/app/`
- 旅游规划 API：`src/app/api/v1/travel/`
- 数据平台页面：`/data-platform`
- 旅游规划逻辑：`src/lib/travel/`
- 本地数据：`travel-data/processed/`、`travel-data/wiki/`
- 数据库脚本：`scripts/travel/`、`sqls/`

主要能力：

- 自然语言解析成结构化区域、时长、预算、餐饮和偏好约束
- 优先命中 PostgreSQL 中的 `travel_precomputed_routes` 预生成路线库
- 支持从本地 POI、酒店、UGC 和 Wiki 数据兜底检索
- 支持追加、删除、替换、保留地点等动态重规划
- 支持通勤边补全与高德 API 离线回填

快速启动 demo：

```bash
npm install
cp .env.example .env
npm run db:up
npm run travel:db:seed
npm run travel:db:doctor
npm run dev
```

默认访问：

```text
http://localhost:3000
```

## 技术栈

- Frontend: Next.js 16 + React 19 + TypeScript + antd
- Backend API: FastAPI
- Agent: LangChain + LangGraph
- Model: MiniMax M2.5（Anthropic 兼容接口）
- Data demo: PostgreSQL + Prisma + root Next.js workspace

## 项目结构

```text
moyuan-travel-agent/
├── .github/              # GitHub workflows、仓库治理入口与平台识别文件
├── .editorconfig         # 编辑器编码、换行与缩进规范
├── .gitattributes        # Git 文本归一化与二进制文件策略
├── agent/                 # Agent 图、节点、工具、记忆、checkpoint
├── backend/               # FastAPI 路由、服务、仓储、配置
├── frontend/              # Next.js 前端
├── src/                   # 北京旅游数据 demo 的根目录 Next.js 工作台
├── extend/                # 观测可视化等扩展能力
├── deploy/                # Compose、Dockerfile、migration、安全扫描等发版资产
├── docs/                  # 文档中心
├── prisma/                # demo 数据库 ORM schema
├── sqls/                  # 北京旅游数据表与路线库 SQL
├── travel-data/           # 北京 POI、酒店、UGC、路线语料与 Wiki
├── tests/                 # 后端/集成测试
├── scripts/               # benchmark / replay / quality gate 等脚本和跨平台开发入口
├── data/                  # 本地运行数据
├── package.json           # 根目录 demo 工作台脚本
├── pyproject.toml         # 根目录 pytest / mypy / Ruff 统一工具配置
├── requirements-dev.txt   # 本地开发与静态检查依赖
└── requirements.txt       # 运行时依赖与安全审计输入
```

当前维护基线只需要先记住 5 条：

- 前端主链已经收口成 workspace 结构：`ChatArea.tsx`、`MessageList.tsx`、`TravelPlanToolkit.tsx`、`CityExplorer.tsx` 负责装配，细节分别下沉到 `chat-area/`、`message-list/`、`travel-plan-toolkit/`、`city-explorer/`。
- 前端 API 入口已经收口成目录化 client：`frontend/src/services/api.ts` 只保留聚合导出，真实 endpoint client 位于 `frontend/src/services/api/`，artifact 历史读取走 `artifactClient.ts`。
- Backend 与脚本入口已经统一：`backend/moyuan_web/bootstrap.py` 和 `scripts/bootstrap_paths.py` 负责 repo root / `backend/` 导入准备，`scripts/dev.py` 是本地开发、回归、容器和运维统一入口。
- Agent 运行时主链已经固定：`AgentRuntime -> runtime_driver -> runtime_flow -> runtime_sources / runtime_event_emitters`；skills market、execution receipt、tool health diagnostics 都通过显式 contract 暴露。
- 运维与治理已经收口：`runtime_doctor / support bundle / release manifest / release harness scorecard` 共用 typed ops contracts，默认门禁由 `docstring / complexity / decision-records / skills-market / runtime-contracts` 组成。

高频维护入口：

| 场景 | 最短入口 |
| --- | --- |
| 前端聊天与 artifact UI | `frontend/src/components/chat-area/`、`frontend/src/components/message-list/`、`frontend/src/components/travel-plan-toolkit/` |
| Backend API 与持久化 | `backend/moyuan_web/routes/`、`backend/moyuan_web/services/`、`backend/moyuan_web/repositories/`、`backend/config/` |
| Agent runtime 与 graph | `agent/travel_agent/runtime/`、`agent/travel_agent/graph/`、`agent/travel_agent/contracts/` |
| 本地命令与运维脚本 | `scripts/dev.py`、`scripts/runtime_*`、`scripts/export_*` |
| 发版与容器资产 | `deploy/compose/`、`deploy/docker/`、`deploy/migrations/`、`deploy/security/` |

根目录规范也已经收口到当前布局：

- Python 工具链统一放在 `pyproject.toml`
- migration 配置下沉到 `deploy/migrations/`
- 仓库治理资产放在 `.github/`
- 发版与安全资产放在 `deploy/`
- `.venv` 保留在根目录，`pytest / mypy / Ruff` 缓存统一放到 `.cache/`

更细的目录说明看 [docs/reference/project-structure.md](docs/reference/project-structure.md)，运行与部署约束看 [docs/architecture/infrastructure-foundations.md](docs/architecture/infrastructure-foundations.md)。

## 本地访问地址

- Frontend: `http://localhost:33001`
- API: `http://localhost:38000`
- API Docs: `http://localhost:38000/rapidoc`
- Health: `http://localhost:38000/api/health`
- Ready: `http://localhost:38000/api/ready`
- Metrics: `http://localhost:38000/api/metrics`
- Prometheus: `http://localhost:39090` (`observability` profile)
- Grafana: `http://localhost:33002` (`observability` profile)

## 快速开始

### 1. 准备环境

- Python 3.13+
- Node.js 20+
- uv
- npm
- Docker / Docker Compose（可选，但推荐用于联调）

### 2. 安装依赖

```bash
python scripts/bootstrap.py
```

安装完成后，建议先看一眼统一命令入口：

```bash
python scripts/dev.py help
python scripts/dev.py backend-dev
python scripts/dev.py frontend-dev
```

### 3. 准备配置

```bash
python scripts/bootstrap.py --skip-frontend
```

根据实际模型服务填写 `api_key`、`api_base`、`model`。

`server_config.yaml` 负责统一：

- `web.host / web.port`
- `frontend.port`
- `cors_origins`
- `request_timeout_seconds`
- `rate_limit_max_requests`
- `metrics_enabled / metrics_path`
- `structured_logging`
- `fail_fast_validation`

如果只是运行服务、完全不做开发，也可以只安装：

```bash
uv pip install -r requirements.txt
```

### 4. 启动后端

```bash
python scripts/dev.py backend-dev
```

### 5. 启动前端

```bash
python scripts/dev.py frontend-dev
```

### 6. 开始体验

1. 打开 `http://localhost:33001`
2. 选择模型与对话模式
3. 在“行程约束”里补充亲子/预算/无车等前置条件
4. 输入旅行需求，等待流式生成
5. 在结果区继续调整预算、查看多方案、检测冲突、导出图片或分享

更完整的启动说明见 [docs/getting-started/quick-start.md](docs/getting-started/quick-start.md)。

### 6.1 常用统一命令入口

```bash
python scripts/dev.py backend-dev
python scripts/dev.py frontend-dev
python scripts/dev.py test
python scripts/dev.py infra-check
python scripts/dev.py compose-config
python scripts/dev.py container-smoke
```

### 6.2 北京旅游数据 demo 常用命令

```bash
npm run dev
npm run build
npm run lint
npm run type-check

npm run db:up
npm run db:down
npm run db:init
npm run db:doctor
npm run db:psql

npm run travel:db:init
npm run travel:routes:build
npm run travel:db:seed
npm run travel:db:import
npm run travel:db:doctor
npm run travel:wiki:build
npm run travel:amap:backfill
```

说明：

- `test`: 后端 `unit/local` + 前端 `lint/test/build`
- `infra-check`: `ruff`、`mypy`、`docstring`、`complexity budget`、`decision records`、runtime doctor、契约快照、release harness scorecard、release manifest，以及在 Docker 可用时附带 compose 渲染校验
  同时会执行 `runtime_contract_audit --strict`，固定 supervisor/runtime seam 的显式 contract
  当前 `runtime_doctor` 遇到被占用的 runtime 文件会返回 `degraded` 检查项，而不是直接中断整条治理链
- `compose-config`: 渲染默认和 `observability` profile 的 Compose 配置
- `container-smoke`: 本地构建 backend / frontend 镜像

### 7. Docker Compose 启动

如果想以统一的前后端容器方式联调，优先使用根目录 Compose：

```bash
docker compose --file deploy/compose/compose.yaml up --build
```

如果想连同 Prometheus 和 Grafana 一起启动本地观测栈：

```bash
docker compose --file deploy/compose/compose.yaml --profile observability up --build
```

如果当前网络拉取 Docker Hub 基础镜像较慢，可以直接切到镜像站：

```bash
python scripts/dev.py compose-up \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

如果只想验证本地镜像构建：

```bash
python scripts/dev.py container-smoke \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

相关资产：

- [deploy/compose/compose.yaml](deploy/compose/compose.yaml)
- [deploy/docker/backend.Dockerfile](deploy/docker/backend.Dockerfile)
- [deploy/docker/frontend.Dockerfile](deploy/docker/frontend.Dockerfile)

## 常用接口

### Chat

- `POST /api/chat/stream`

请求示例：

```json
{
  "message": "请给我一个上海周末两日游建议，预算 1500 元以内",
  "session_id": "optional-session-id",
  "mode": "react"
}
```

### Session

- `POST /api/session/new`
- `GET /api/sessions`
- `PUT /api/session/{session_id}/name`
- `PUT /api/session/{session_id}/model`
- `DELETE /api/session/{session_id}`
- `POST /api/clear?session_id=...`

### Artifacts

- `GET /api/artifacts/{session_id}/latest`
  - 前端 session restore 会优先用它补齐 persisted artifact，避免刷新后只能回退到纯文本恢复
- `GET /api/artifacts/{session_id}/history?limit=10`
  - 返回当前 session 中 newest-first 的 artifact 快照列表；现在 compare/history UI 会直接消费这条 contract，不再继续扫描原始 session messages 来拼对比方案

### Share Links

- `POST /api/share-links`
  - 现在会同时持久化兼容字段 `title / content / html_content` 和结构化 `delivery_bundle`，把 `artifact + executionReceipt + htmlContent + share` 元数据一次性落盘
- `GET /api/share-links/{share_id}`
  - 现在会优先把持久化 `delivery_bundle` 回放给前端 share/session hydration，使分享页继续走 artifact-first 渲染，而不是只剩 raw assistant text

### City Explorer

- `GET /api/cities`
- `GET /api/cities/{city_id}`
- `GET /api/cities/{city_id}/attractions`
- `GET /api/regions`
- `GET /api/tags`

### Health

- `GET /api/health`
- `GET /api/health/llm`
- `GET /api/health/tools`
- `GET /api/health/tools/intents`
- `GET /api/ready`
- `GET /api/live`
- `GET /api/metrics`

完整接口说明见 [docs/reference/api-reference.md](docs/reference/api-reference.md)。

## 部署与观测

### readiness 与启动校验

后端启动时会执行真实 startup checks，并把结果暴露到 `/api/ready`。当前会检查：

- `server_config` 是否可解析
- `data/` 是否可写
- `llm_config` 是否存在且至少有一个 active model
- 依赖容器能否 resolve
- Chat runtime 是否能初始化

如果希望启动失败时直接退出，可设置：

```bash
set MOYUAN_FAIL_FAST_STARTUP_VALIDATION=true
```

### request_id / trace_id

前端 REST 与 SSE 请求都会自动携带：

- `X-Request-ID`
- `X-Trace-ID`

后端会把它们写入：

- 响应头
- 结构化日志
- SSE payload 的 `request_id / trace_id`

### runtime doctor

运行维护时，推荐先跑一遍：

```bash
python scripts/dev.py runtime-doctor --runtime-doctor-json
python scripts/dev.py runtime-doctor --base-url http://localhost:38000 --runtime-doctor-strict
python scripts/export_runtime_doctor_snapshot.py
```

它会检查：

- `backend/config/server_config.yaml` / `backend/config/llm_config.yaml`
- `data/` 可写性与运行态文件
- 备份归档目录
- OpenAPI / SSE 契约快照
- 可选的 live `/api/health`、`/api/ready`、`/api/metrics`

### Prometheus metrics

当前默认暴露：

- `GET /api/metrics`

主要指标包括：

- `moyuan_http_requests_total`
- `moyuan_http_request_duration_seconds`
- `moyuan_http_in_flight_requests`
- `moyuan_chat_stream_requests_total`
- `moyuan_sse_events_total`
- `moyuan_readiness_state`

## 测试与质量

### 前端

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```

当前前端默认验证入口已经做过跨平台稳定化处理：

- `npm run test:run` 会通过 `frontend/vitest.config.ts` 把 `vitest` worker 数限制为 `2`
- `npm run build` 默认走 `next build --webpack`，避免当前 `Next.js 16` 默认构建路径在部分本地环境里出现 worker init 失败
- `python scripts/dev.py test / infra-check` 现在会在 Windows 上自动解析 `npm.cmd`，不再因为 `subprocess` 直接找 `npm` 而中断

### 后端

```bash
python scripts/dev.py backend-test --pytest-slice unit
python scripts/dev.py backend-test --pytest-slice local
python scripts/dev.py backend-test --pytest-slice runtime
python scripts/dev.py backend-test --pytest-slice ops
python scripts/dev.py ruff
python scripts/dev.py mypy
python scripts/dev.py docstring
python scripts/dev.py complexity
python scripts/dev.py decision-records
python scripts/dev.py skills-market
python scripts/dev.py runtime-contracts
python scripts/dev.py snapshots
```

其中 `python scripts/docstring_audit.py --strict` 当前会同时检查两类问题：

- 缺失 docstring
- 新增低信息量 docstring（历史存量由 `docs/reference/docstring-audit.low-info-baseline.json` 管理）
- 热点文件超出复杂度预算（由 `python scripts/complexity_budget.py --strict` 检查）
- 治理记录缺失必填章节（由 `python scripts/decision_record_audit.py --strict` 检查）

### 推荐统一入口

- `python scripts/dev.py test`
- `python scripts/dev.py backend-test --pytest-slice <unit|local|runtime|ops|all>`
- `python scripts/dev.py infra-check`
- `python scripts/dev.py snapshots`
- `python scripts/dev.py benchmark-report`
- `python scripts/dev.py golden-report`
- `python scripts/dev.py benchmark-trend`
- `python scripts/dev.py quality-gate`
- `python scripts/dev.py runtime-backup`
- `python scripts/dev.py runtime-restore --restore-archive <archive.zip>`
- `python scripts/dev.py runtime-prune --prune-keep-latest-backups 10 --prune-max-backup-age-days 14`
- `python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-dry-run`
- `python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10 --prune-max-backup-age-days 14`
- `python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id> --prune-checkpoint-backend postgres --prune-checkpoint-db 'postgresql://user:password@localhost:5432/moyuan'`
- `python scripts/dev.py runtime-doctor --runtime-doctor-json`
- `python scripts/dev.py release-manifest --git-sha <sha> --git-ref <ref> --owner <owner>`
- `python scripts/dev.py support-bundle`
- `python scripts/dev.py container-smoke`

### Agent 质量脚本

- `python scripts/dev.py benchmark-report`
- `uv run --offline python scripts/agent_subagent_scorecard.py --output-dir docs/benchmarks`
- `python scripts/dev.py release-scorecard`
- `python scripts/dev.py golden-report`
- `python scripts/dev.py benchmark-trend`
- `python scripts/dev.py quality-gate`

### 运行数据与契约维护脚本

- `python scripts/dev.py runtime-backup`
- `python scripts/dev.py runtime-restore --restore-archive <archive.zip>`
- `python scripts/dev.py runtime-prune --prune-keep-latest-backups 10 --prune-max-backup-age-days 14`
- `python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-dry-run`
- `python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10 --prune-max-backup-age-days 14`
- `python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id> --prune-vacuum-checkpoints`
- `python scripts/dev.py runtime-doctor --runtime-doctor-json`
- `python scripts/export_openapi_snapshot.py`
- `python scripts/export_sse_contract_snapshot.py`
- `python scripts/export_runtime_doctor_snapshot.py`
- `python scripts/export_frontend_chat_runtime_golden_fixture.py`
- `python scripts/dev.py release-manifest --git-sha <sha> --git-ref <ref> --owner <owner>`
- `python scripts/dev.py support-bundle --base-url http://localhost:38000`

组合任务约定：

- `python scripts/dev.py runtime-maintenance`
  - 固定顺序是 `runtime-backup -> runtime-doctor --json -> runtime-prune`
- `python scripts/dev.py checkpoint-maintenance`
  - 固定顺序是 `runtime-prune --vacuum-checkpoints -> optional agent-replay --dry-run -> runtime-doctor --json`
  - 如果显式传 `--replay-session-id`，会自动把 replay 收敛为 dry-run，避免维护流程里误写运行态数据

### 契约与安全基线

- OpenAPI snapshot: [docs/reference/openapi.snapshot.json](docs/reference/openapi.snapshot.json)
- SSE snapshot: [docs/reference/sse-contract.snapshot.json](docs/reference/sse-contract.snapshot.json)
- Runtime doctor snapshot: [docs/reference/runtime-doctor.snapshot.json](docs/reference/runtime-doctor.snapshot.json)
- Chat stream replay fixture: [tests/golden/chat_stream_golden_fixture.json](tests/golden/chat_stream_golden_fixture.json)
- Frontend chat runtime replay fixture: [tests/golden/frontend_chat_runtime_golden_fixture.json](tests/golden/frontend_chat_runtime_golden_fixture.json)
- Subagent scorecard report: [docs/benchmarks/agent_subagent_scorecard_latest.md](docs/benchmarks/agent_subagent_scorecard_latest.md)
- Release harness scorecard: [docs/benchmarks/release_harness_scorecard_latest.md](docs/benchmarks/release_harness_scorecard_latest.md)
- CI dependency audit: `pip-audit -r requirements.txt`
- CI secret scan: Dockerized `gitleaks` with [`deploy/security/gitleaks.toml`](deploy/security/gitleaks.toml)

### 发布与观测资产

- Release workflow: [`.github/workflows/release.yml`](.github/workflows/release.yml)
- Release manifest: [`scripts/export_release_manifest.py`](scripts/export_release_manifest.py)
- Release harness checklist: [`scripts/release_harness_scorecard.py`](scripts/release_harness_scorecard.py)
- Support bundle: [`scripts/export_support_bundle.py`](scripts/export_support_bundle.py)
  - support bundle manifest 现在也会复用 typed release evidence，带出 release manifest 的 `git_sha/git_ref`、release harness scorecard 的 `status`，并在压缩包内附带 `release-harness-scorecard.json`
- Grafana dashboard: [`extend/observability/grafana-dashboard.json`](extend/observability/grafana-dashboard.json)
- Prometheus alerts: [`extend/observability/prometheus-alerts.yml`](extend/observability/prometheus-alerts.yml)
- Local Prometheus config: [`extend/observability/prometheus.yml`](extend/observability/prometheus.yml)

### 仓库规范与容器校验

- 编辑器规范：[`/.editorconfig`](.editorconfig)
- Git 文本归一化：[`/.gitattributes`](.gitattributes)
- 仓库协作规范：[`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md)
- 安全上报入口：[`.github/SECURITY.md`](.github/SECURITY.md)
- secret scan 配置：[`deploy/security/gitleaks.toml`](deploy/security/gitleaks.toml)
- 本地命令入口：[`/scripts/dev.py`](scripts/dev.py)
- CI 的 `container-validate` 会执行 `docker compose --file deploy/compose/compose.yaml config`、`docker compose --file deploy/compose/compose.yaml --profile observability config`、后端镜像 smoke build、前端镜像 smoke build，并上传 `deployment-validation-artifacts`

更多测试与回放说明见 [docs/testing/testing-guide.md](docs/testing/testing-guide.md)。

## 文档导航

### 教学入口：按任务场景跳转

- 系统学习整个项目：
  先看 [docs/teaching/README.md](docs/teaching/README.md)
- `30 分钟速览`：
  看 [docs/teaching/01-total-plan-and-learning-method.md](docs/teaching/01-total-plan-and-learning-method.md)
- `半天上手`：
  依次看 [docs/teaching/01-total-plan-and-learning-method.md](docs/teaching/01-total-plan-and-learning-method.md)、[docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md)、[docs/teaching/03-backend-api-session-and-persistence.md](docs/teaching/03-backend-api-session-and-persistence.md)
- `改 Bug 前先找主链`：
  先看 [docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md)，再按故障落点跳到 [docs/teaching/03-backend-api-session-and-persistence.md](docs/teaching/03-backend-api-session-and-persistence.md)、[docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md)、[docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改前端`：
  优先看 [docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Backend API`：
  优先看 [docs/teaching/03-backend-api-session-and-persistence.md](docs/teaching/03-backend-api-session-and-persistence.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Agent`：
  优先看 [docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要做 Agent 架构升级 / agent-subagent-skills 规划`：
  优先看 [docs/architecture/agent-subagent-skills-architecture-roadmap.md](docs/architecture/agent-subagent-skills-architecture-roadmap.md)、[docs/architecture/system-architecture.md](docs/architecture/system-architecture.md)、[docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md)
- `我要看部署 / 配置 / readiness / trace / CI`：
  优先看 [docs/architecture/infrastructure-foundations.md](docs/architecture/infrastructure-foundations.md)、[docs/reference/configuration-reference.md](docs/reference/configuration-reference.md)、[docs/testing/testing-guide.md](docs/testing/testing-guide.md)
- `我要发起大改动 / 补 ADR / 写设计评审`：
  优先看 [docs/governance/README.md](docs/governance/README.md)、[docs/architecture/harness-engineering-runtime-source-roadmap.md](docs/architecture/harness-engineering-runtime-source-roadmap.md)
- `我要接一个新的 skill / 看 skills market 约束`：
  优先看 [docs/reference/skills-market-catalog.md](docs/reference/skills-market-catalog.md)、[docs/governance/skills-market-onboarding.md](docs/governance/skills-market-onboarding.md)、[docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md)
- `面试前 2 小时复习`：
  优先看 [docs/teaching/01-total-plan-and-learning-method.md](docs/teaching/01-total-plan-and-learning-method.md)、[docs/teaching/06-interview-highlights-and-system-evolution.md](docs/teaching/06-interview-highlights-and-system-evolution.md)、[docs/teaching/07-thinking-questions-homework-and-answers.md](docs/teaching/07-thinking-questions-homework-and-answers.md)

### 其他文档入口

- [docs/README.md](docs/README.md): 文档总入口
- [docs/getting-started/quick-start.md](docs/getting-started/quick-start.md): 快速启动
- [docs/getting-started/ai-travel-agent-zero-to-one.md](docs/getting-started/ai-travel-agent-zero-to-one.md): 面向新人的 AI 旅游 Agent 从 0 到 1 教学教程
- [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md): 系统架构
- [docs/architecture/agent-subagent-skills-architecture-roadmap.md](docs/architecture/agent-subagent-skills-architecture-roadmap.md): Agent 应用层与 `Supervisor -> Subagents -> Skills` 演进路线图
- [docs/architecture/infrastructure-foundations.md](docs/architecture/infrastructure-foundations.md): 运行与部署、配置、readiness、CI、trace、metrics 总览
- [docs/architecture/data-storage.md](docs/architecture/data-storage.md): 运行数据、备份、恢复与清理策略
- [docs/governance/README.md](docs/governance/README.md): ADR / RFC / Design Review 统一入口
- [docs/reference/api-reference.md](docs/reference/api-reference.md): API 参考
- [docs/reference/project-structure.md](docs/reference/project-structure.md): 目录结构
- [docs/reference/backend-maintainer-playbook.md](docs/reference/backend-maintainer-playbook.md): 后端维护与排障手册
- [docs/reference/frontend-message-rendering.md](docs/reference/frontend-message-rendering.md): 前端消息渲染与 `<think>` 折叠机制
- [docs/testing/testing-guide.md](docs/testing/testing-guide.md): 测试与回放

## 适合继续优化的方向

- 把地图预览继续升级为更完整的路线编辑体验
- 补更多真实 provider 的酒店/门票/交通数据源
- 为城市探索加入热度排序、季节排序和更多主题榜单
- 为分享页增加更轻量的外部只读浏览体验
