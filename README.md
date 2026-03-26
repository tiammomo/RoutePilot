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

## 技术栈

- Frontend: Next.js 16 + React 19 + TypeScript + antd
- Web API: FastAPI
- Agent: LangChain + LangGraph
- Model: MiniMax M2.5（Anthropic 兼容接口）

## 项目结构

```text
moyuan-travel-agent/
├── .editorconfig         # 编辑器编码、换行与缩进规范
├── .gitattributes        # Git 文本归一化与二进制文件策略
├── agent/                  # Agent 图、节点、工具、记忆、checkpoint
├── web/                    # FastAPI 路由、服务、仓储、存储
├── frontend/               # Next.js 前端
├── tests/                  # 后端/集成测试
├── docs/                   # 文档中心
├── config/                 # 服务与模型配置
├── data/                   # 本地运行数据
├── scripts/                # benchmark / replay / quality gate 等脚本
├── dev.ps1                 # 本地开发、测试与基础设施命令入口
├── compose.yaml            # 根目录 Compose
├── requirements-dev.txt    # 本地开发与静态检查依赖
└── Dockerfile.backend      # Web API Dockerfile
```

当前前端已经按 harness engineering 的思路逐步薄化主入口：

- `frontend/src/components/ChatArea.tsx` 负责 chat workspace 装配，主逻辑落在 `frontend/src/components/chat-area/`
- `frontend/src/components/chat-area/useChatRuntime.ts` 已继续下沉，流缓冲、artifact 运行态、run lifecycle、share/session hydration 和 input policy 分别落在 `useStreamBuffer.ts`、`useArtifactRuntimeState.ts`、`useChatRunState.ts`、`useChatSessionHydration.ts`、`chatInputPolicy.ts`、`runtimeMessageBuilders.ts`
- `frontend/src/components/chat-area/chatRuntimeReplay.ts` 负责把后端 `chat stream golden fixture` 回放成前端最终运行时快照，作为 frontend harness 的 replay/golden 基线
- `frontend/src/context/AppContext.tsx` 现在主要保留全局 provider 装配，session cache / history recovery 与 model bootstrap 已分别下沉到 `frontend/src/context/useSessionHistoryState.ts` 和 `frontend/src/context/useModelBootstrapState.ts`
- `frontend/src/components/MessageList.tsx` 负责消息区装配，渲染与诊断逻辑落在 `frontend/src/components/message-list/`
- `frontend/src/components/TravelPlanToolkit.tsx` 负责 trip-plan workspace 装配，`travel-plan-toolkit/sections.tsx` 已退化成 facade，真实 itinerary / compare / practical 视图块落在 `frontend/src/components/travel-plan-toolkit/sections/`
- `frontend/src/components/travel-plan-toolkit/sections/itinerary/day-card/` 继续把单日行程卡拆成 `ItineraryConflictSection / ItinerarySpotDecisionGrid / ItineraryTipsBlock` 三个 view adapter，收口风险提醒、景点决策卡和 tips 区块
- `frontend/src/components/travel-plan-toolkit/sections/itinerary/budget-panel/` 继续把预算面板拆成 `BudgetModeToolbar / BudgetStatsSummary / BudgetQuickRefineBar / BudgetConfidencePanel` 四个 view adapter，收口预算档位、预算统计、quick refine 和 confidence 风险提示
- `frontend/src/components/travel-plan-toolkit/sections/compare-tab/` 继续把对比视图拆成 `CompareEmptyState / VariantComparisonTable / VariantActionBar` 三个 view adapter，收口空态、对比表和继续细化动作
- `frontend/src/components/travel-plan-toolkit/sections/conflicts-tab/` 继续把冲突检测视图拆成 `ConflictSummaryTag / ConflictCardContent / DayConflictCard` 三个 view adapter，收口摘要标签、按日冲突卡和一键修复动作
- `frontend/src/components/travel-plan-toolkit/sections/practical-tab/` 继续把实用信息视图拆成 `PracticalInfoGrid / PracticalInfoCardItem / PracticalToneTag` 三个 view adapter，收口信息卡网格、单卡内容和 tone 标签
- `frontend/src/components/CityExplorer.tsx` 负责 city-explorer workspace 装配，筛选、shortlist、对比和详情逻辑落在 `frontend/src/components/city-explorer/`
- `frontend/src/components/city-explorer/sections.tsx` 现在只保留兼容 facade，Hero / FilterBar / ComparePanel / Grid / DetailDrawer 已拆到 `frontend/src/components/city-explorer/sections/`
- `frontend/src/components/city-explorer/sections/hero/` 继续把 `HeroSection` 下沉成 `HeroSummaryHeader / CuratedPromptPanel / FavoriteShortlistPanel` 三个 view 协作器，并锁住 shortlist 的“去规划”边界
- `frontend/src/components/city-explorer/sections/grid/` 继续把 `GridSection` 下沉成 `GridSummaryBar / CityGridCard / CityGridCardMetrics / CityGridCardActions` 四个 view 协作器，并锁住城市卡的“规划”动作边界
- `frontend/src/services/api.ts` 只保留兼容 facade，真实 endpoint client 在 `frontend/src/services/api/`

更详细的目录说明见 [docs/reference/project-structure.md](docs/reference/project-structure.md)。

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
uv python install 3.13
uv venv .venv --python 3.13
.\.venv\Scripts\activate
uv pip install -r requirements-dev.txt

cd frontend
npm install
cd ..
```

安装完成后，建议先看一眼统一命令入口：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 help
```

### 3. 准备配置

```bash
copy config\llm_config.yaml.example config\llm_config.yaml
copy config\server_config.yaml.example config\server_config.yaml
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
.\.venv\Scripts\python.exe -m uvicorn moyuan_web.main:app --host 0.0.0.0 --port 38000 --app-dir web
```

### 5. 启动前端

```bash
cd frontend
npm run dev
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
powershell -ExecutionPolicy Bypass -File .\dev.ps1 test
powershell -ExecutionPolicy Bypass -File .\dev.ps1 infra-check
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-config
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke
```

说明：

- `test`: 后端 `unit/local` + 前端 `lint/test/build`
- `infra-check`: `ruff`、`mypy`、`docstring`、runtime doctor、契约快照、release manifest，以及在 Docker 可用时附带 compose 渲染校验
- `compose-config`: 渲染默认和 `observability` profile 的 Compose 配置
- `container-smoke`: 本地构建 backend / frontend 镜像

### 7. Docker Compose 启动

如果想以统一的前后端容器方式联调，优先使用根目录 Compose：

```bash
docker compose up --build
```

如果想连同 Prometheus 和 Grafana 一起启动本地观测栈：

```bash
docker compose --profile observability up --build
```

如果当前网络拉取 Docker Hub 基础镜像较慢，可以直接切到镜像站：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-up `
  -PythonBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" `
  -NodeBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

如果只想验证本地镜像构建：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke `
  -PythonBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" `
  -NodeBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

相关资产：

- [compose.yaml](/D:/moyuan/moyuan-travel-agent/compose.yaml)
- [Dockerfile.backend](/D:/moyuan/moyuan-travel-agent/Dockerfile.backend)
- [frontend/Dockerfile](/D:/moyuan/moyuan-travel-agent/frontend/Dockerfile)

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
python scripts/runtime_doctor.py --json
python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict
```

它会检查：

- `config/server_config.yaml` / `config/llm_config.yaml`
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

### 后端

```bash
python -m pytest tests -m "unit and not local and not external_api" -q
python -m pytest tests -m "local and not external_api" -q
python -m ruff check --config ruff.toml scripts web/moyuan_web
python scripts/docstring_audit.py --strict
mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/moyuan_web/app_meta.py web/moyuan_web/main.py web/moyuan_web/middleware/__init__.py web/moyuan_web/observability.py web/moyuan_web/routes/chat.py web/moyuan_web/routes/health.py web/moyuan_web/services/share_service.py web/moyuan_web/startup_checks.py
```

### 推荐统一入口

- `powershell -ExecutionPolicy Bypass -File .\dev.ps1 test`
- `powershell -ExecutionPolicy Bypass -File .\dev.ps1 infra-check`
- `powershell -ExecutionPolicy Bypass -File .\dev.ps1 snapshots`
- `powershell -ExecutionPolicy Bypass -File .\dev.ps1 support-bundle`
- `powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke`

### Agent 质量脚本

- `python scripts/agent_benchmark.py --output-dir docs/benchmarks`
- `python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0`
- `python scripts/agent_quality_gate.py --golden-report ... --benchmark-report ... --baseline-benchmark-report ...`

### 运行数据与契约维护脚本

- `python scripts/runtime_backup.py`
- `python scripts/runtime_restore.py --archive ...`
- `python scripts/runtime_prune.py --keep-latest-backups 10 --max-backup-age-days 14`
- `python scripts/runtime_doctor.py --json`
- `python scripts/export_openapi_snapshot.py`
- `python scripts/export_sse_contract_snapshot.py`
- `python scripts/export_frontend_chat_runtime_golden_fixture.py`
- `python scripts/export_release_manifest.py --git-sha <sha> --git-ref <ref> --owner <owner>`
- `python scripts/export_support_bundle.py --base-url http://localhost:38000`

### 契约与安全基线

- OpenAPI snapshot: [docs/reference/openapi.snapshot.json](docs/reference/openapi.snapshot.json)
- SSE snapshot: [docs/reference/sse-contract.snapshot.json](docs/reference/sse-contract.snapshot.json)
- Chat stream replay fixture: [tests/golden/chat_stream_golden_fixture.json](/D:/moyuan/moyuan-travel-agent/tests/golden/chat_stream_golden_fixture.json)
- Frontend chat runtime replay fixture: [tests/golden/frontend_chat_runtime_golden_fixture.json](/D:/moyuan/moyuan-travel-agent/tests/golden/frontend_chat_runtime_golden_fixture.json)
- CI dependency audit: `pip-audit -r requirements.txt`
- CI secret scan: Dockerized `gitleaks` with [`.gitleaks.toml`](/D:/moyuan/moyuan-travel-agent/.gitleaks.toml)

### 发布与观测资产

- Release workflow: [`.github/workflows/release.yml`](/D:/moyuan/moyuan-travel-agent/.github/workflows/release.yml)
- Release manifest: [`scripts/export_release_manifest.py`](/D:/moyuan/moyuan-travel-agent/scripts/export_release_manifest.py)
- Support bundle: [`scripts/export_support_bundle.py`](/D:/moyuan/moyuan-travel-agent/scripts/export_support_bundle.py)
- Grafana dashboard: [`ops/observability/grafana-dashboard.json`](/D:/moyuan/moyuan-travel-agent/ops/observability/grafana-dashboard.json)
- Prometheus alerts: [`ops/observability/prometheus-alerts.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus-alerts.yml)
- Local Prometheus config: [`ops/observability/prometheus.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus.yml)

### 仓库规范与容器校验

- 编辑器规范：[`/.editorconfig`](/D:/moyuan/moyuan-travel-agent/.editorconfig)
- Git 文本归一化：[`/.gitattributes`](/D:/moyuan/moyuan-travel-agent/.gitattributes)
- 本地命令入口：[`/dev.ps1`](/D:/moyuan/moyuan-travel-agent/dev.ps1)
- CI 的 `container-validate` 会执行 `docker compose config`、`docker compose --profile observability config`、后端镜像 smoke build、前端镜像 smoke build，并上传 `deployment-validation-artifacts`

更多测试与回放说明见 [docs/testing/testing-guide.md](docs/testing/testing-guide.md)。

## 文档导航

### 教学入口：按任务场景跳转

- 系统学习整个项目：
  先看 [docs/teaching/README.md](docs/teaching/README.md)
- `30 分钟速览`：
  看 [docs/teaching/01-total-plan-and-learning-method.md](docs/teaching/01-total-plan-and-learning-method.md)
- `半天上手`：
  依次看 [docs/teaching/01-total-plan-and-learning-method.md](docs/teaching/01-total-plan-and-learning-method.md)、[docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md)、[docs/teaching/03-web-api-session-and-storage.md](docs/teaching/03-web-api-session-and-storage.md)
- `改 Bug 前先找主链`：
  先看 [docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md)，再按故障落点跳到 [docs/teaching/03-web-api-session-and-storage.md](docs/teaching/03-web-api-session-and-storage.md)、[docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md)、[docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改前端`：
  优先看 [docs/teaching/02-chat-mainline-and-frontend.md](docs/teaching/02-chat-mainline-and-frontend.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Web API`：
  优先看 [docs/teaching/03-web-api-session-and-storage.md](docs/teaching/03-web-api-session-and-storage.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Agent`：
  优先看 [docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md) 和 [docs/teaching/05-testing-debugging-and-change-practice.md](docs/teaching/05-testing-debugging-and-change-practice.md)
- `我要做 Agent 架构升级 / agent-subagent-skills 规划`：
  优先看 [docs/architecture/agent-subagent-skills-architecture-roadmap.md](docs/architecture/agent-subagent-skills-architecture-roadmap.md)、[docs/architecture/system-architecture.md](docs/architecture/system-architecture.md)、[docs/teaching/04-agent-core-tools-memory-checkpoint.md](docs/teaching/04-agent-core-tools-memory-checkpoint.md)
- `我要看部署 / 配置 / readiness / trace / CI`：
  优先看 [docs/architecture/infrastructure-foundations.md](docs/architecture/infrastructure-foundations.md)、[docs/reference/configuration-reference.md](docs/reference/configuration-reference.md)、[docs/testing/testing-guide.md](docs/testing/testing-guide.md)
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
