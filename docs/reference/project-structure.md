# Project Structure

## 顶层目录

```text
ShuaiTravelAgent/
├── agent/                  # LangGraph Agent 逻辑
├── web/                    # FastAPI 服务
├── frontend/               # Next.js 前端
├── config/                 # YAML 配置
├── docs/                   # 文档中心
├── tests/                  # API / 集成测试
├── data/                   # 运行时数据
├── scripts/                # benchmark / replay / quality gate 等脚本
├── compose.yaml            # 根目录 Docker Compose
└── Dockerfile.backend      # Web API 容器镜像构建文件
```

## 关键目录说明

### `agent/`

负责旅行 Agent 的推理执行链路。

重点子目录：

- `travel_agent/graph/`
  - 图构建、节点、运行时配置、checkpoint
- `travel_agent/tools/`
  - 工具定义、provider 适配
- `travel_agent/llm/`
  - LLM 适配层

适合在这些场景进入：

- 改意图识别
- 改计划路由
- 改工具执行与验证逻辑
- 改记忆与 checkpoint

### `web/`

负责 Web API 路由、服务层、存储层，以及 startup validation 与 observability。

重点路径：

- [`web/shuai_web/main.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/main.py)
  - FastAPI 入口、middleware 注册、router 注册、metrics alias 注册
- [`web/shuai_web/routes/`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/routes)
  - `chat / session / city / health / model / share / map`
- [`web/shuai_web/services/`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/services)
  - 业务服务，重点是 `chat_service.py`
- [`web/shuai_web/repositories/`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/repositories)
  - 仓储接口与实现
- [`web/shuai_web/storage/`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/storage)
  - 文件或本地存储抽象
- [`web/shuai_web/observability.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/observability.py)
  - request context、结构化日志、Prometheus metrics
- [`web/shuai_web/startup_checks.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/startup_checks.py)
  - readiness snapshot 与 fail-fast 启动校验

适合在这些场景进入：

- 新增 API
- 改 session 生命周期
- 改 startup readiness
- 改 trace / metrics / middleware

### `frontend/`

负责所有用户可见的交互界面。

重点路径：

- [`frontend/src/app/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/app)
  - App Router 页面
- [`frontend/src/components/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/components)
  - 页面组件、消息列表、工具箱、城市探索
- [`frontend/src/context/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/context)
  - 全局状态
- [`frontend/src/services/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/services)
  - REST / SSE 客户端
- [`frontend/src/utils/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/utils)
  - 行程解析、预算计算、导出辅助逻辑
- [`frontend/src/types/`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/types)
  - TS 类型定义
- [`frontend/next.config.js`](/D:/projects/shuai/ShuaiTravelAgent/frontend/next.config.js)
  - Next.js rewrite 和内部 API 基址
- [`frontend/Dockerfile`](/D:/projects/shuai/ShuaiTravelAgent/frontend/Dockerfile)
  - 前端容器构建

适合在这些场景进入：

- 改对话输入 / 消息展示
- 改 request_id / trace_id 前端透传
- 改每日行程卡与预算工具
- 改城市探索卡片与对比表

### `config/`

负责配置模板和本地配置。

关键文件：

- [`config/__init__.py`](/D:/projects/shuai/ShuaiTravelAgent/config/__init__.py)
  - `ServerConfig`，统一解析 YAML + env overrides
- [`config/server_config.yaml.example`](/D:/projects/shuai/ShuaiTravelAgent/config/server_config.yaml.example)
  - 服务配置模板
- [`config/llm_config.yaml.example`](/D:/projects/shuai/ShuaiTravelAgent/config/llm_config.yaml.example)
  - 模型配置模板

### `tests/`

以 Python 测试为主，覆盖 API、Agent 行为与集成场景。

重点内容：

- SSE 行为
- guardrails
- verification / stale / fallback
- readiness / metrics / tracing
- golden eval 数据集

重点文件：

- [`tests/test_api_smoke_local.py`](/D:/projects/shuai/ShuaiTravelAgent/tests/test_api_smoke_local.py)
- [`tests/test_chat_stream_local.py`](/D:/projects/shuai/ShuaiTravelAgent/tests/test_chat_stream_local.py)
- [`tests/conftest.py`](/D:/projects/shuai/ShuaiTravelAgent/tests/conftest.py)

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

维护者常用参考：

- [`docs/architecture/infrastructure-foundations.md`](/D:/projects/shuai/ShuaiTravelAgent/docs/architecture/infrastructure-foundations.md)
- [`docs/reference/backend-maintainer-playbook.md`](/D:/projects/shuai/ShuaiTravelAgent/docs/reference/backend-maintainer-playbook.md)
- [`docs/reference/frontend-message-rendering.md`](/D:/projects/shuai/ShuaiTravelAgent/docs/reference/frontend-message-rendering.md)

### `scripts/`

辅助脚本与质量门禁工具，常见用途：

- benchmark
- golden eval
- replay
- quality gate
- docstring audit
- runtime backup / restore / prune / doctor
- OpenAPI / SSE contract snapshot export
- release manifest export
- support bundle export

### `ops/`

基础设施运行资产目录，当前重点放：

- [`ops/observability/README.md`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/README.md)
- [`ops/observability/grafana-dashboard.json`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/grafana-dashboard.json)
- [`ops/observability/prometheus-alerts.yml`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/prometheus-alerts.yml)
- [`ops/observability/prometheus.yml`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/prometheus.yml)
- [`ops/observability/grafana-provisioning/`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/grafana-provisioning)

## 当前最常用的文件入口

### 前端

- [`frontend/src/components/ChatArea.tsx`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/components/ChatArea.tsx)
- [`frontend/src/components/MessageList.tsx`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/components/MessageList.tsx)
- [`frontend/src/components/TravelPlanToolkit.tsx`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/components/TravelPlanToolkit.tsx)
- [`frontend/src/components/CityExplorer.tsx`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/components/CityExplorer.tsx)
- [`frontend/src/services/api.ts`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/services/api.ts)
- [`frontend/src/utils/travelPlan.ts`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/utils/travelPlan.ts)

### 后端

- [`web/shuai_web/routes/chat.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/routes/chat.py)
- [`web/shuai_web/routes/health.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/routes/health.py)
- [`web/shuai_web/services/chat_service.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/services/chat_service.py)
- [`web/shuai_web/observability.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/observability.py)
- [`web/shuai_web/startup_checks.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/startup_checks.py)

### Agent

- [`agent/travel_agent/graph/builder.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/graph/builder.py)
- [`agent/travel_agent/graph/nodes.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/graph/nodes.py)
- [`agent/travel_agent/graph/runtime_config.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/graph/runtime_config.py)
- [`agent/travel_agent/graph/memory_integration.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/graph/memory_integration.py)
- [`agent/travel_agent/tools/travel_tools.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/tools/travel_tools.py)

## 修改时的经验性建议

### 改 UI / 交互时

通常需要同时关注：

- `frontend/src/components/*`
- `frontend/src/services/api.ts`
- `frontend/src/utils/travelPlan.ts`
- 对应的后端接口与 types

### 改 API / startup / observability 时

通常需要同时关注：

- `web/shuai_web/main.py`
- `web/shuai_web/middleware/__init__.py`
- `web/shuai_web/routes/*`
- `web/shuai_web/services/*`
- `config/__init__.py`
- `tests/test_api_smoke_local.py`
- `tests/test_chat_stream_local.py`

### 改 Agent 行为时

通常需要同时关注：

- `agent/travel_agent/graph/*`
- `agent/travel_agent/tools/*`
- `tests/`
- `docs/reference/api-reference.md`

## 结构规范

- Python 文件使用 `snake_case.py`
- React 组件使用 `PascalCase.tsx`
- 文档文件使用 `kebab-case.md`
- 运行时数据放在 `data/`
- benchmark / replay 产物统一放在 `docs/benchmarks/`
- 截图等静态资源统一放在 `docs/assets/`
