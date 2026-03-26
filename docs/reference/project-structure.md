# Project Structure

## 顶层目录

```text
moyuan-travel-agent/
├── .editorconfig         # 编辑器编码、换行、缩进规范
├── .gitattributes        # Git 文本归一化与二进制文件策略
├── agent/                # LangGraph Agent 逻辑
├── web/                  # FastAPI 服务
├── frontend/             # Next.js 前端
├── config/               # YAML 配置模板与解析
├── docs/                 # 文档中心
├── tests/                # API / 集成 / 质量测试
├── data/                 # 运行时数据
├── logs/                 # 本地日志
├── ops/                  # 观测与运维资产
├── scripts/              # 运行维护、快照、质量脚本
├── dev.ps1               # 本地统一命令入口
├── compose.yaml          # 根目录 Docker Compose
├── Dockerfile.backend    # Web API 镜像构建文件
├── requirements-dev.txt  # 本地开发与静态检查依赖
├── mypy.ini              # mypy 检查范围与规则
└── ruff.toml             # Ruff 检查规则
```

## 根目录规范文件

### `.editorconfig`

统一这些基础行为：

- `UTF-8`
- 默认 `LF`
- Markdown 允许保留行尾空格
- Python 4 空格缩进
- TypeScript / JSON / YAML 2 空格缩进
- PowerShell 使用 `CRLF`

### `.gitattributes`

统一这些 Git 行为：

- 常见文本文件按规则归一化换行
- `ps1/cmd/bat` 保持 `CRLF`
- 图片、PDF、Zip、SQLite 以 binary 处理

### `dev.ps1`

这是本地最推荐的统一入口，负责收口：

- 测试
- `ruff`
- `mypy`
- docstring 审计
- OpenAPI / SSE 快照导出
- release manifest
- support bundle
- compose 渲染校验

优先命令：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 help
```

## 关键目录说明

### `agent/`

负责旅行 Agent 的推理执行链路。

重点子目录：

- `travel_agent/runtime/`
  - Web/API 层调用的应用级入口，封装 supervisor、skills、artifact 组合
- `travel_agent/supervisor/`
  - Phase 1 兼容层，先用 supervisor 外壳承接当前单图
- `travel_agent/subagents/`
  - Phase 2 最小 subagent 实现与注册表，当前包含 research / planning / verification
- `travel_agent/skills/`
  - skill registry 与领域能力契约映射
- `travel_agent/artifacts/`
  - 结构化行程产物与 artifact builder
- `travel_agent/contracts/`
  - skills 等上层契约模型
- `travel_agent/graph/`
  - 图构建、节点、运行时配置、checkpoint
- `travel_agent/tools/`
  - 工具定义、provider 适配
- `travel_agent/llm/`
  - LLM 适配层

### `web/`

负责 Web API 路由、服务层、仓储层、存储层，以及 startup validation、middleware、observability。

重点路径：

- [`web/moyuan_web/main.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/main.py)
- [`web/moyuan_web/routes/`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/routes)
- [`web/moyuan_web/services/`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services)
- [`web/moyuan_web/repositories/`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/repositories)
- [`web/moyuan_web/storage/`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/storage)
- [`web/moyuan_web/observability.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/observability.py)
- [`web/moyuan_web/startup_checks.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/startup_checks.py)

### `frontend/`

负责所有用户可见的交互界面。

重点路径：

- [`frontend/src/app/`](/D:/moyuan/moyuan-travel-agent/frontend/src/app)
- [`frontend/src/components/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components)
- [`frontend/src/components/chat-area/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area)
- [`frontend/src/components/message-list/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/message-list)
- [`frontend/src/components/travel-plan-toolkit/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit)
- [`frontend/src/components/city-explorer/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer)
- [`frontend/src/context/`](/D:/moyuan/moyuan-travel-agent/frontend/src/context)
- [`frontend/src/services/api/`](/D:/moyuan/moyuan-travel-agent/frontend/src/services/api)
- [`frontend/src/utils/`](/D:/moyuan/moyuan-travel-agent/frontend/src/utils)
- [`frontend/Dockerfile`](/D:/moyuan/moyuan-travel-agent/frontend/Dockerfile)

当前前端目录的职责已经明显分层：

- `ChatArea.tsx`、`MessageList.tsx`、`TravelPlanToolkit.tsx`、`CityExplorer.tsx`
  - 都是薄入口，负责 feature 装配与向后兼容
- `chat-area/`
  - 聊天运行时状态、流缓冲、artifact 运行态、input policy、send lifecycle、输入区、执行洞察与对话区协作器
- `message-list/`
  - Markdown 归一化、消息区块、诊断区块与复制/导出动作
- `travel-plan-toolkit/`
  - 行程概览、对比、checklist、practical、冲突检测等视图块
  - `sections/itinerary/day-card/` 继续承接单日行程卡里的风险提醒、景点决策卡与 tips 视图
  - `sections/itinerary/budget-panel/` 继续承接预算档位、预算统计、quick refine 与 confidence 风险提示视图
  - `sections/compare-tab/` 继续承接空态、对比表和继续细化动作视图
  - `sections/conflicts-tab/` 继续承接冲突摘要标签、按日冲突卡和一键修复动作视图
  - `sections/practical-tab/` 继续承接实用信息卡网格、单卡内容和 tone 标签视图
  - `sections/reminders-tab/` 继续承接提醒卡列表、单卡内容和阶段标签视图
- `city-explorer/`
  - 场景 prompt、筛选器、shortlist、对比池、城市网格与详情抽屉
  - `sections.tsx` 仅保留兼容导出，真实 section modules 位于 `city-explorer/sections/`
- `services/api/`
  - chat / city / map / health / session / share 等分域 client 与 stream parser

### `config/`

负责配置模板和配置解析。

关键文件：

- [`config/__init__.py`](/D:/moyuan/moyuan-travel-agent/config/__init__.py)
- [`config/server_config.yaml.example`](/D:/moyuan/moyuan-travel-agent/config/server_config.yaml.example)
- [`config/llm_config.yaml.example`](/D:/moyuan/moyuan-travel-agent/config/llm_config.yaml.example)

### `tests/`

以后端与本地 smoke 为主，同时覆盖契约、运行维护脚本、观测资产和质量门禁。

重点文件：

- [`tests/test_api_smoke_local.py`](/D:/moyuan/moyuan-travel-agent/tests/test_api_smoke_local.py)
- [`tests/test_chat_stream_local.py`](/D:/moyuan/moyuan-travel-agent/tests/test_chat_stream_local.py)
- [`tests/test_agent_runtime_phase1_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_agent_runtime_phase1_unit.py)
- [`tests/test_agent_subagent_phase2_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_agent_subagent_phase2_unit.py)
- [`tests/test_runtime_data_lifecycle_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_runtime_data_lifecycle_unit.py)
- [`tests/test_export_openapi_snapshot_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_openapi_snapshot_script_unit.py)
- [`tests/test_export_sse_contract_snapshot_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_sse_contract_snapshot_script_unit.py)
- [`tests/test_export_frontend_chat_runtime_golden_fixture_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_frontend_chat_runtime_golden_fixture_script_unit.py)
- [`tests/test_export_support_bundle_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_support_bundle_script_unit.py)

### `docs/`

项目文档中心，分为：

- `getting-started/`
- `product/`
- `architecture/`
- `reference/`
- `testing/`
- `benchmarks/`
- `assets/`
- `teaching/`

维护者最常用：

- [`docs/architecture/infrastructure-foundations.md`](/D:/moyuan/moyuan-travel-agent/docs/architecture/infrastructure-foundations.md)
- [`docs/reference/backend-maintainer-playbook.md`](/D:/moyuan/moyuan-travel-agent/docs/reference/backend-maintainer-playbook.md)
- [`docs/testing/testing-guide.md`](/D:/moyuan/moyuan-travel-agent/docs/testing/testing-guide.md)

### `scripts/`

辅助脚本与质量门禁工具。

当前主要覆盖：

- benchmark / golden eval / quality gate
- runtime backup / restore / prune / doctor
- OpenAPI / SSE contract snapshot export
- frontend chat runtime replay fixture export
- release manifest export
- support bundle export
- docstring audit

### `ops/`

基础设施运行资产目录，当前重点是 `observability/`：

- [`ops/observability/README.md`](/D:/moyuan/moyuan-travel-agent/ops/observability/README.md)
- [`ops/observability/grafana-dashboard.json`](/D:/moyuan/moyuan-travel-agent/ops/observability/grafana-dashboard.json)
- [`ops/observability/prometheus-alerts.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus-alerts.yml)
- [`ops/observability/prometheus.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus.yml)
- [`ops/observability/grafana-provisioning/`](/D:/moyuan/moyuan-travel-agent/ops/observability/grafana-provisioning)

## 当前最常用的代码入口

### 前端

当前这些顶层文件大多已经退化为薄入口，阅读时建议连同对应的 feature 协作器目录一起看。

- [`frontend/src/components/ChatArea.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/ChatArea.tsx)
- [`frontend/src/components/chat-area/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area)
- [`frontend/src/components/MessageList.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/MessageList.tsx)
- [`frontend/src/components/message-list/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/message-list)
- [`frontend/src/components/TravelPlanToolkit.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/TravelPlanToolkit.tsx)
- [`frontend/src/components/travel-plan-toolkit/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit)
- [`frontend/src/components/CityExplorer.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/CityExplorer.tsx)
- [`frontend/src/components/city-explorer/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer)
- [`frontend/src/services/api/`](/D:/moyuan/moyuan-travel-agent/frontend/src/services/api)

### 后端

- [`web/moyuan_web/routes/chat.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/routes/chat.py)
- [`web/moyuan_web/routes/health.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/routes/health.py)
- [`web/moyuan_web/services/chat_service.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services/chat_service.py)
- [`web/moyuan_web/services/share_service.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services/share_service.py)
- [`web/moyuan_web/observability.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/observability.py)
- [`web/moyuan_web/startup_checks.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/startup_checks.py)

### Agent

- [`agent/travel_agent/runtime/agent_runtime.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/runtime/agent_runtime.py)
- [`agent/travel_agent/supervisor/builder.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/supervisor/builder.py)
- [`agent/travel_agent/supervisor/nodes.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/supervisor/nodes.py)
- [`agent/travel_agent/subagents/registry.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/registry.py)
- [`agent/travel_agent/subagents/research.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/research.py)
- [`agent/travel_agent/subagents/planning.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/planning.py)
- [`agent/travel_agent/subagents/verification.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/verification.py)
- [`agent/travel_agent/skills/registry.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/skills/registry.py)
- [`agent/travel_agent/artifacts/models.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/artifacts/models.py)
- [`agent/travel_agent/graph/builder.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/graph/builder.py)
- [`agent/travel_agent/graph/nodes.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/graph/nodes.py)
- [`agent/travel_agent/graph/runtime_config.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/graph/runtime_config.py)
- [`agent/travel_agent/graph/memory_integration.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/graph/memory_integration.py)
- [`agent/travel_agent/tools/travel_tools.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/tools/travel_tools.py)

## 修改时的联动建议

### 改 UI / 交互

通常需要同时关注：

- `frontend/src/components/*`
- `frontend/src/services/api/*`
- `frontend/src/utils/travelPlan.ts`
- 对应的后端接口与类型

### 改 API / startup / observability

通常需要同时关注：

- `web/moyuan_web/main.py`
- `web/moyuan_web/middleware/__init__.py`
- `web/moyuan_web/routes/*`
- `web/moyuan_web/services/*`
- `config/__init__.py`
- `tests/test_api_smoke_local.py`
- `tests/test_chat_stream_local.py`
- `docs/reference/api-reference.md`
- `docs/testing/testing-guide.md`

### 改 Agent 架构 / supervisor / skills / artifact

通常需要同时关注：

- `agent/travel_agent/runtime/*`
- `agent/travel_agent/supervisor/*`
- `agent/travel_agent/subagents/*`
- `agent/travel_agent/skills/*`
- `agent/travel_agent/artifacts/*`
- `agent/travel_agent/graph/*`
- `web/moyuan_web/services/chat_service.py`
- `tests/test_agent_runtime_phase1_unit.py`
- `tests/test_agent_subagent_phase2_unit.py`
- `docs/architecture/system-architecture.md`
- `docs/architecture/agent-subagent-skills-architecture-roadmap.md`

### 改仓库规范 / 命令入口 / Compose

通常需要同时关注：

- `/.editorconfig`
- `/.gitattributes`
- `/dev.ps1`
- `/compose.yaml`
- `/.github/workflows/ci.yml`
- `docs/getting-started/development-workflow.md`
- `docs/architecture/infrastructure-foundations.md`

## 命名与结构约定

- Python 文件使用 `snake_case.py`
- React 组件使用 `PascalCase.tsx`
- 文档文件使用 `kebab-case.md`
- 运行时数据统一放在 `data/`
- benchmark / replay 产物统一放在 `docs/benchmarks/`
- 截图等静态资源统一放在 `docs/assets/`
## Phase 3 Frontend Files

这一轮前端已经形成“薄入口 + feature 协作器 + 分域 API client”的结构：

- [`frontend/src/services/api/`](/D:/moyuan/moyuan-travel-agent/frontend/src/services/api)
  - chat / city / map / health / session / share client，以及 `chatStreamParser.ts`
- [`frontend/src/types/index.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/types/index.ts)
  - streaming artifact / subagent event contracts
- [`frontend/src/utils/agentArtifacts.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/utils/agentArtifacts.ts)
  - frontend-side artifact merge helpers
- [`frontend/src/components/chat-area/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area)
  - `useChatRuntime.ts` 作为主编排 hook，继续委托 `useStreamBuffer.ts / useArtifactRuntimeState.ts / useChatRunState.ts / useChatSessionHydration.ts / chatInputPolicy.ts / runtimeMessageBuilders.ts`
- [`frontend/src/components/chat-area/useStreamBuffer.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/useStreamBuffer.ts)
  - 流缓冲、平滑刷新与滚动同步
- [`frontend/src/components/chat-area/useArtifactRuntimeState.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/useArtifactRuntimeState.ts)
  - artifact / subagent 运行态与 reset 语义
- [`frontend/src/components/chat-area/useChatRunState.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/useChatRunState.ts)
  - waiting / thinking / tool / stage / runtime log 生命周期收口
- [`frontend/src/components/chat-area/useChatSessionHydration.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/useChatSessionHydration.ts)
  - share query 恢复、session 切换 reset、metadata ref 与 skip-next-session-reset 语义
- [`frontend/src/components/chat-area/chatRuntimeReplay.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/chatRuntimeReplay.ts)
  - 复用 `chatStreamParser.ts / runtimeMessageBuilders.ts / agentArtifacts.ts`，把后端 golden fixture 回放成前端最终运行时快照
- [`frontend/src/context/useSessionHistoryState.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/context/useSessionHistoryState.ts)
  - session 列表过滤、localStorage 恢复、会话消息缓存、切换回放与 model recovery
- [`frontend/src/context/useModelBootstrapState.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/context/useModelBootstrapState.ts)
  - 模型列表拉取、当前模型恢复、session model 同步与 bootstrap 选型回退
- [`frontend/src/components/chat-area/chatInputPolicy.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/chatInputPolicy.ts)
  - 输入校验、增强 prompt、session name 与 stopped message 规则
- [`frontend/src/components/chat-area/runtimeMessageBuilders.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/chat-area/runtimeMessageBuilders.ts)
  - completion / stopped diagnostics 与 reasoning timestamp 拼装
- [`frontend/src/components/message-list/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/message-list)
  - markdown 渲染、思考区块、诊断区块与复制/导出动作
- [`frontend/src/components/travel-plan-toolkit/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit)
  - 结构化行程概览、方案对比、checklist、practical、reminders、conflicts
- [`frontend/src/components/travel-plan-toolkit/sections/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections)
  - `ToolkitOverviewPanel / ToolkitItineraryTab / ToolkitCompareTab / ToolkitChecklistTab / ToolkitFavoritesTab / ToolkitPracticalTab / ToolkitRemindersTab / ToolkitConflictsTab` 真实 section adapters
- [`frontend/src/components/travel-plan-toolkit/sections/compare-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/compare-tab)
  - `CompareEmptyState / VariantComparisonTable / VariantActionBar` 三个 view adapters，分别承接空态、对比表和 variant action bar
- [`frontend/src/components/travel-plan-toolkit/sections/conflicts-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/conflicts-tab)
  - `ConflictSummaryTag / ConflictCardContent / DayConflictCard` 三个 view adapters，分别承接冲突摘要、按日冲突卡与一键修复动作
- [`frontend/src/components/travel-plan-toolkit/sections/practical-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/practical-tab)
  - `PracticalInfoGrid / PracticalInfoCardItem / PracticalToneTag` 三个 view adapters，分别承接信息卡网格、单卡内容与 tone 标签
- [`frontend/src/components/travel-plan-toolkit/sections/reminders-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/reminders-tab)
  - `RemindersList / ReminderCardContent / ReminderPhaseTag` 三个 view adapters，分别承接提醒卡列表、单卡内容与阶段标签
- [`frontend/src/components/travel-plan-toolkit/sections/itinerary/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/itinerary)
  - `ItineraryBudgetPanel / ItineraryDayCard` 继续承接每日行程里的预算控制与单日卡片
- [`frontend/src/components/travel-plan-toolkit/sections/itinerary/budget-panel/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/itinerary/budget-panel)
  - `BudgetModeToolbar / BudgetStatsSummary / BudgetQuickRefineBar / BudgetConfidencePanel` 四个 view adapters，分别承接预算档位、预算统计、quick refine 动作和 confidence 风险提示
- [`frontend/src/components/travel-plan-toolkit/sections/itinerary/day-card/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/itinerary/day-card)
  - `ItineraryConflictSection / ItinerarySpotDecisionGrid / ItineraryTipsBlock` 三个 view adapters，分别承接风险提醒、景点决策卡与 tips 区块
- [`frontend/src/components/city-explorer/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer)
  - 场景 prompt、筛选器、shortlist、城市网格、对比池与详情抽屉
- [`frontend/src/components/city-explorer/sections/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer/sections)
  - `HeroSection / FilterBarSection / ComparePanelSection / GridSection / DetailDrawerSection` 五个 section modules，`sections.tsx` 只保留 facade
- [`frontend/src/components/city-explorer/sections/hero/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer/sections/hero)
  - `HeroSummaryHeader / CuratedPromptPanel / FavoriteShortlistPanel` 三个 view 协作器，继续承接 `HeroSection` 的 header、场景卡和 shortlist
- [`frontend/src/components/city-explorer/sections/grid/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/city-explorer/sections/grid)
  - `GridSummaryBar / CityGridCard / CityGridCardMetrics / CityGridCardActions` 四个 view 协作器，继续承接 `GridSection` 的统计条、城市卡、指标区和操作条
- [`frontend/tests/unit/components/ChatComposer.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/ChatComposer.test.tsx)
  - 锁住发送/停止与约束展示边界
- [`frontend/tests/unit/components/runtimeMessageBuilders.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/runtimeMessageBuilders.test.ts)
  - 锁住 reasoning timestamp 与 completion/stopped diagnostics 语义
- [`frontend/tests/unit/components/useChatSessionHydration.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/useChatSessionHydration.test.tsx)
  - 锁住 share 恢复、session 切换 reset 与 skip reset 语义
- [`frontend/tests/unit/components/useChatRunState.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/useChatRunState.test.ts)
  - 锁住 waiting / thinking / tool / stage runtime lifecycle
- [`frontend/tests/unit/components/chatInputPolicy.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/chatInputPolicy.test.ts)
  - 锁住输入校验、增强 prompt 与 stopped message 语义
- [`frontend/tests/unit/components/chatRuntimeReplay.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/chatRuntimeReplay.test.ts)
  - 锁住 parser / artifact merge / completion diagnostics 的最终态，以及前端 golden fixture 基线
- [`frontend/tests/unit/components/TravelPlanToolkit.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/TravelPlanToolkit.test.tsx)
  - 锁住 tab 切换、每日行程动作、方案对比与 checklist/practical 入口
- [`frontend/tests/unit/components/CityExplorer.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/CityExplorer.test.tsx)
  - 锁住场景 prompt、shortlist 规划、城市卡规划、详情抽屉加载与对比 prompt 边界

## Session Hydration Additions

- `web/moyuan_web/routes/session.py`
  - 新增 `GET /session/{session_id}/messages`，作为前端恢复会话消息的公开入口
- `web/moyuan_web/services/chat_service.py`
  - assistant 消息现在会把 `diagnostics.artifact` 与 `diagnostics.subagentEvents` 一并落盘
  - user 消息支持 `display_message` / `model_content` 分离
- `frontend/src/context/AppContext.tsx`
  - 现在主要负责 provider 装配与流式全局状态
- `frontend/src/context/useSessionHistoryState.ts`
  - 负责 session 切换、刷新恢复、当前 session id 的本地持久化与消息缓存回放
- `frontend/src/context/useModelBootstrapState.ts`
  - 负责模型列表 bootstrap、当前模型恢复与 session model 同步
- `frontend/src/utils/sessionMessages.ts`
  - 负责把后端持久化消息标准化成前端 `Message` 结构
