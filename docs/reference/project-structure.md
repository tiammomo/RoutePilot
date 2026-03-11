# Project Structure

## 顶层目录

```text
ShuaiTravelAgent/
├── agent/        # LangGraph Agent 逻辑
├── web/          # FastAPI 服务
├── frontend/     # Next.js 前端
├── config/       # YAML 配置
├── docs/         # 文档中心
├── tests/        # API / 集成测试
├── data/         # 运行时数据
└── scripts/      # benchmark / replay / quality gate 等脚本
```

## 关键目录说明

### `agent/`

负责旅行 Agent 的推理执行链路。

重点子目录：

- `travel_agent/graph/`: 图构建、节点、运行时配置、checkpoint
- `travel_agent/tools/`: 工具定义、provider 适配
- `travel_agent/llm/`: LLM 适配层

适合在这些场景进入：

- 改意图识别
- 改计划路由
- 改工具执行与验证逻辑
- 改记忆与 checkpoint

### `web/`

负责 Web API 路由、服务层与存储层。

重点路径：

- `web/shuai_web/main.py`: FastAPI 入口
- `web/shuai_web/routes/`: chat / session / city / health / model / share / map
- `web/shuai_web/services/`: 业务服务
- `web/shuai_web/repositories/`: 仓储接口与实现
- `web/shuai_web/storage/`: 文件或本地存储抽象

适合在这些场景进入：

- 新增 API
- 改 session 生命周期
- 改城市探索数据
- 改分享或地图接口

### `frontend/`

负责所有用户可见的交互界面。

重点路径：

- `frontend/src/app/`: App Router 页面
- `frontend/src/components/`: 页面组件、消息列表、工具箱、城市探索
- `frontend/src/context/`: 全局状态
- `frontend/src/services/`: REST / SSE 客户端
- `frontend/src/utils/`: 行程解析、预算计算、导出辅助逻辑
- `frontend/src/types/`: TS 类型定义

适合在这些场景进入：

- 改对话输入/消息展示
- 改每日行程卡与预算工具
- 改城市探索卡片与对比表
- 改导出图片、分享、地图联动

### `tests/`

以 Python 测试为主，覆盖 API、Agent 行为与集成场景。

重点内容：

- SSE 行为
- guardrails
- verification / stale / fallback
- golden eval 数据集

### `docs/`

项目文档中心，分为：

- `getting-started/`
- `product/`
- `architecture/`
- `reference/`
- `testing/`
- `benchmarks/`
- `assets/`

维护者常用参考：

- `reference/backend-maintainer-playbook.md`
- `reference/frontend-message-rendering.md`

### `scripts/`

辅助脚本与质量门禁工具，常见用途：

- benchmark
- golden eval
- replay
- quality gate
- 启动/联调辅助

## 当前最常用的文件入口

### 前端

- `frontend/src/components/ChatArea.tsx`
- `frontend/src/components/MessageList.tsx`
- `frontend/src/components/TravelPlanToolkit.tsx`
- `frontend/src/components/CityExplorer.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/utils/travelPlan.ts`

### 后端

- `web/shuai_web/routes/chat.py`
- `web/shuai_web/services/chat_service.py`
- `web/shuai_web/routes/city.py`
- `web/shuai_web/services/city_service.py`
- `web/shuai_web/services/map_service.py`
- `web/shuai_web/services/share_service.py`

### Agent

- `agent/travel_agent/graph/builder.py`
- `agent/travel_agent/graph/nodes.py`
- `agent/travel_agent/graph/runtime_config.py`
- `agent/travel_agent/graph/memory_integration.py`
- `agent/travel_agent/tools/travel_tools.py`

## 修改时的经验性建议

### 改 UI / 交互时

通常需要同时关注：

- `frontend/src/components/*`
- `frontend/src/services/api.ts`
- `frontend/src/utils/travelPlan.ts`
- 对应的后端接口与 types

### 改 API 时

通常需要同时关注：

- `web/shuai_web/routes/*`
- `web/shuai_web/services/*`
- `frontend/src/services/api.ts`
- `frontend/src/types/index.ts`

### 改 Agent 行为时

通常需要同时关注：

- `agent/travel_agent/graph/*`
- `agent/travel_agent/tools/*`
- `tests/`
- `docs/reference/api-reference.md` 中的事件与元数据说明

## 结构规范

- Python 文件使用 `snake_case.py`
- React 组件使用 `PascalCase.tsx`
- 文档文件使用 `kebab-case.md`
- 运行时数据放在 `data/`
- benchmark / replay 产物统一放在 `docs/benchmarks/`
- 截图等静态资源统一放在 `docs/assets/`
