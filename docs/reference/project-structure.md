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
├── scripts/              # 运行维护、快照、质量脚本和跨平台命令入口
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
- 全仓文本默认使用 `LF`

### `.gitattributes`

统一这些 Git 行为：

- 常见文本文件按规则归一化换行
- 常见文本文件统一为 `LF`
- 图片、PDF、Zip、SQLite 以 binary 处理

### `scripts/dev.py`

这是本地最推荐的统一入口，负责收口：

- 测试
- `ruff`
- `mypy`
- docstring 覆盖率与低信息量审计
- 热点文件复杂度预算门禁
- skills market 四件套治理审计
- OpenAPI / SSE 快照导出
- release manifest
- release harness scorecard
- support bundle
- compose 渲染校验

优先命令：

```bash
python scripts/dev.py help
```

## 关键目录说明

### `agent/`

负责旅行 Agent 的推理执行链路。

重点子目录：

- `travel_agent/runtime/`
  - Web/API 层调用的应用级入口，封装 supervisor、skills、artifact 组合
  - `legacy_bridge.py` 负责把 `AgentRuntime` 与旧 `graph.builder` 的 streaming / preview / diagnostics 兼容调用收口成显式 bridge
- `travel_agent/supervisor/`
  - Phase 1 兼容层，先用 supervisor 外壳承接当前单图
- `travel_agent/subagents/`
  - Phase 2 到 Phase 3 过渡期的 subagent 实现与注册表，当前包含 research / planning / budget / verification
- `travel_agent/skills/`
  - skill registry 与领域能力契约映射；当前默认 catalog 已显式补齐 `owner / version / input / output / evidence / freshness / fallback / docs / eval` 元数据
- `travel_agent/artifacts/`
  - 结构化行程产物与 artifact builder
- `travel_agent/contracts/`
  - skills、supervisor orchestration、supervisor events、execution receipt 等上层契约模型
- `travel_agent/memory/`
  - 从 legacy graph 中逐步拆出的 memory 协作器，当前包含 `persistence.py` 与 `conflict_resolution.py`
- `travel_agent/graph/`
  - 图构建、节点、运行时配置、legacy 执行兼容入口、checkpoint
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
  - `useTravelPlanToolkitActions.ts / actionPrompts.ts` 继续承接 favorites、route、export、share 与 continue prompt 的动作编排，其中 continue/edit prompt 已优先带上 artifact 上下文，export 也会优先消费 artifact 派生标题、摘要与文件名
  - `sections/itinerary/day-card/` 继续承接单日行程卡里的风险提醒、景点决策卡与 tips 视图
  - `sections/itinerary/budget-panel/` 继续承接预算档位、预算统计、quick refine 与 confidence 风险提示视图
  - `sections/compare-tab/` 继续承接空态、对比表和继续细化动作视图
  - `sections/conflicts-tab/` 继续承接冲突摘要标签、按日冲突卡和一键修复动作视图
  - `sections/practical-tab/` 继续承接实用信息卡网格、单卡内容和 tone 标签视图
  - `sections/reminders-tab/` 继续承接提醒卡列表、单卡内容和阶段标签视图
  - `sections/checklist-tab/` 继续承接清单列表、单项行和完成状态 affordance
- `shared/` 继续承接 timeline、budget、risk、practical、reminder、checklist、content 和 subagent label helper
  - `artifact.ts` 继续承接 artifact-first 的 overview descriptor、destinations / budget / verification 摘要，以及 share payload / export descriptor 构造
- `city-explorer/`
  - 场景 prompt、筛选器、shortlist、对比池、城市网格与详情抽屉
  - `sections.tsx` 仅保留兼容导出，真实 section modules 位于 `city-explorer/sections/`
- `services/api/`
  - chat / city / map / health / session / share / artifact 等分域 client 与 stream parser

### `docs/governance/`

负责统一管理 `ADR / RFC / Design Review` 记录。

重点路径：

- [`docs/governance/README.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/README.md)
- [`docs/governance/skills-market-onboarding.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/skills-market-onboarding.md)
- [`docs/governance/adr/ADR-0001-governance-record-flow.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/adr/ADR-0001-governance-record-flow.md)
- [`docs/governance/adr/ADR-0000-template.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/adr/ADR-0000-template.md)
- [`docs/governance/rfcs/RFC-0000-template.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/rfcs/RFC-0000-template.md)
- [`docs/governance/design-reviews/DR-0000-template.md`](/D:/moyuan/moyuan-travel-agent/docs/governance/design-reviews/DR-0000-template.md)

配套的结构审计脚本是 [`scripts/decision_record_audit.py`](/D:/moyuan/moyuan-travel-agent/scripts/decision_record_audit.py)，当前已接入本地 `python scripts/dev.py infra-check` 和 CI。
配套的 skills 四件套审计脚本是 [`scripts/skills_market_audit.py`](/D:/moyuan/moyuan-travel-agent/scripts/skills_market_audit.py)，当前也已接入本地 `python scripts/dev.py infra-check` 和 CI。

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
- [`tests/conftest.py`](/D:/moyuan/moyuan-travel-agent/tests/conftest.py)
  - 统一承接 pytest fixtures、CI guard 和 repo root / `web/` 导入 bootstrap，root tests 不再各自写 `sys.path` 补丁

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
- release harness checklist / scorecard
- runtime backup / restore / prune / doctor
- OpenAPI / SSE contract snapshot export
- frontend chat runtime replay fixture export
- release manifest export
- release harness scorecard export
- support bundle export
- docstring audit
- `scripts/bootstrap_paths.py` 统一承接 repo root / `web/` 的导入初始化，benchmark、replay、runtime、snapshot 脚本不再各自写 `sys.path` 注入

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
- [`web/moyuan_web/routes/artifact.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/routes/artifact.py)
  - `GET /api/artifacts/{session_id}/latest` 与 `GET /api/artifacts/{session_id}/history`
- [`web/moyuan_web/services/chat_service.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services/chat_service.py)
- [`web/moyuan_web/services/artifact_service.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services/artifact_service.py)
  - persisted artifact latest/history 读取与 camelCase normalize
- [`web/moyuan_web/services/share_service.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/services/share_service.py)
- [`web/moyuan_web/observability.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/observability.py)
- [`web/moyuan_web/startup_checks.py`](/D:/moyuan/moyuan-travel-agent/web/moyuan_web/startup_checks.py)

### Agent

- [`agent/travel_agent/runtime/agent_runtime.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/runtime/agent_runtime.py)
- [`agent/travel_agent/supervisor/builder.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/supervisor/builder.py)
- [`agent/travel_agent/supervisor/nodes.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/supervisor/nodes.py)
- [`agent/travel_agent/subagents/registry.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/registry.py)
  - subagent 到 skill 的拥有关系、tool 映射，以及 `selection_policy / selection_plan`
- [`agent/travel_agent/contracts/execution_receipt.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/contracts/execution_receipt.py)
  - `subagent order / tools used / artifact patch sections / stage history` 的统一 receipt contract
- [`agent/travel_agent/contracts/supervisor_orchestration.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/contracts/supervisor_orchestration.py)
  - `SupervisorRunRequest / SupervisorPlanPreviewRequest / SupervisorRuntimeContext / SupervisorPlanPreview` 四个 contract，用来收口 `AgentRuntime -> legacy bridge -> legacy_runtime` 的编排状态与 preview 结果
- [`agent/travel_agent/contracts/supervisor_events.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/contracts/supervisor_events.py)
  - `SupervisorStageEvent / SupervisorReasoningEvent / SupervisorChunkEvent / SupervisorToolStartEvent / SupervisorToolEndEvent / SupervisorDoneEvent` 六类 contract，用来收口 legacy graph 归一化后的 runtime 事件形状
- [`agent/travel_agent/graph/legacy_runtime.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/graph/legacy_runtime.py)
  - legacy graph 的 `run / stream / stream_with_memory / plan preview / diagnostics` 兼容执行入口；现在也通过 `stream_supervisor_run()` / `generate_supervisor_plan_preview()` 直接消费 `SupervisorRunRequest / SupervisorPlanPreviewRequest / SupervisorRuntimeContext`，`builder.py` 主要保留 `TravelAgentGraph`、`build_travel_agent()` 和图编译逻辑
- [`agent/travel_agent/subagents/research.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/research.py)
- [`agent/travel_agent/subagents/planning.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/planning.py)
- [`agent/travel_agent/subagents/budget.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/budget.py)
- [`agent/travel_agent/subagents/verification.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/subagents/verification.py)
- [`agent/travel_agent/skills/registry.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/skills/registry.py)
  - 默认 skills market catalog，包含 owner、版本、输入输出 contract、selection policy、evidence/freshness/fallback 与 docs/eval 钩子
- [`docs/reference/skills-market-catalog.md`](/D:/moyuan/moyuan-travel-agent/docs/reference/skills-market-catalog.md)
  - 当前默认 skills market 的文档化视图
- [`scripts/agent_subagent_scorecard.py`](/D:/moyuan/moyuan-travel-agent/scripts/agent_subagent_scorecard.py)
  - 基于 replay fixture 生成 `research / planning / budget / verification` 的协作覆盖 scorecard 基线
- [`scripts/release_harness_scorecard.py`](/D:/moyuan/moyuan-travel-agent/scripts/release_harness_scorecard.py)
  - 收口 golden / benchmark / subagent scorecard / delivery snapshot / skills market 的 release checklist
- [`agent/travel_agent/artifacts/models.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/artifacts/models.py)
- [`agent/travel_agent/memory/conflict_resolution.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/memory/conflict_resolution.py)
- [`agent/travel_agent/memory/persistence.py`](/D:/moyuan/moyuan-travel-agent/agent/travel_agent/memory/persistence.py)
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
- `/scripts/dev.py`
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
  - session 列表过滤、localStorage 恢复、会话消息缓存、切换回放、persisted artifact 回填、diagnostics.sessionId 回补与 model recovery
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
- [`frontend/src/components/travel-plan-toolkit/useArtifactHistoryCompare.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/useArtifactHistoryCompare.ts)
  - 基于 `artifactClient.getArtifactHistory(sessionId)` 组装 compare variants，优先把 persisted artifact snapshots 送进 compare/history UI
- [`frontend/src/components/travel-plan-toolkit/sections/compare-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/compare-tab)
  - `CompareEmptyState / VariantComparisonTable / VariantActionBar` 三个 view adapters，分别承接空态、对比表和 variant action bar；`VariantComparisonTable` 现在同时支持 text-first 与 artifact-history compare
- [`frontend/src/components/travel-plan-toolkit/sections/conflicts-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/conflicts-tab)
  - `ConflictSummaryTag / ConflictCardContent / DayConflictCard` 三个 view adapters，分别承接冲突摘要、按日冲突卡与一键修复动作
- [`frontend/src/components/travel-plan-toolkit/sections/practical-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/practical-tab)
  - `PracticalInfoGrid / PracticalInfoCardItem / PracticalToneTag` 三个 view adapters，分别承接信息卡网格、单卡内容与 tone 标签
- [`frontend/src/components/travel-plan-toolkit/sections/reminders-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/reminders-tab)
  - `RemindersList / ReminderCardContent / ReminderPhaseTag` 三个 view adapters，分别承接提醒卡列表、单卡内容与阶段标签
- [`frontend/src/components/travel-plan-toolkit/sections/checklist-tab/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/sections/checklist-tab)
  - `ChecklistList / ChecklistItemRow / ChecklistStatusTag` 三个 view adapters，分别承接清单列表、单项行与完成状态 affordance
- [`frontend/src/components/travel-plan-toolkit/shared/`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/shared)
  - `timeline / budget / risk / practical / reminders / checklist / content / subagents / artifact / types` 领域 helper，`shared.tsx` 仅保留兼容 facade
- [`frontend/src/components/travel-plan-toolkit/useTravelPlanToolkitActions.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/useTravelPlanToolkitActions.ts)
  - favorites 池重做方案、variant continue、route preview、reorder、图片导出和分享动作编排；当前 share / export 已统一消费 `artifact delivery descriptor`，并把 `html_content` 一并带进 share-link contract
- [`frontend/src/components/travel-plan-toolkit/actionPrompts.ts`](/D:/moyuan/moyuan-travel-agent/frontend/src/components/travel-plan-toolkit/actionPrompts.ts)
  - `variant continue`、favorites quick refine 与 artifact-aware continue/edit prompt builder
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
- [`frontend/tests/features/`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features)
  - 前端测试当前按 `chat / app-shell / trip-plan / city-explorer / shared` 五类 feature workspace 组织，避免继续按 `components / utils / context` 漂移
- [`frontend/tests/features/chat/ChatComposer.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/ChatComposer.test.tsx)
  - 锁住发送/停止与约束展示边界
- [`frontend/tests/features/chat/runtimeMessageBuilders.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/runtimeMessageBuilders.test.ts)
  - 锁住 reasoning timestamp 与 completion/stopped diagnostics 语义
- [`frontend/tests/features/chat/useChatSessionHydration.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/useChatSessionHydration.test.tsx)
  - 锁住 share 恢复、session 切换 reset 与 skip reset 语义
- [`frontend/tests/features/chat/useChatRunState.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/useChatRunState.test.ts)
  - 锁住 waiting / thinking / tool / stage runtime lifecycle
- [`frontend/tests/features/chat/chatInputPolicy.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/chatInputPolicy.test.ts)
  - 锁住输入校验、增强 prompt 与 stopped message 语义
- [`frontend/tests/features/chat/chatRuntimeReplay.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/chat/chatRuntimeReplay.test.ts)
  - 锁住 parser / artifact merge / completion diagnostics 的最终态，以及前端 golden fixture 基线
- [`frontend/tests/features/trip-plan/TravelPlanToolkit.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/trip-plan/TravelPlanToolkit.test.tsx)
  - 锁住 tab 切换、每日行程动作、方案对比与 checklist/practical 入口
- [`frontend/tests/features/trip-plan/travelPlanActionPrompts.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/trip-plan/travelPlanActionPrompts.test.ts)
  - 锁住 favorites quick refine prompt 与 variant continue prompt builder
- [`frontend/tests/features/city-explorer/CityExplorer.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/features/city-explorer/CityExplorer.test.tsx)
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
  - 负责 session 切换、刷新恢复、当前 session id 的本地持久化、消息缓存回放，以及通过 `artifactClient` 回填最新 persisted artifact 并补回 `diagnostics.sessionId`
- `frontend/src/services/api/artifactClient.ts`
  - latest/history 两类 artifact 读取 client，供 session restore、artifact-history compare 与 compare/history UI 复用
- `frontend/src/context/useModelBootstrapState.ts`
  - 负责模型列表 bootstrap、当前模型恢复与 session model 同步
- `frontend/src/utils/sessionMessages.ts`
  - 负责把后端持久化消息标准化成前端 `Message` 结构
