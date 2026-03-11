# ShuaiTravelAgent

![Next.js](https://img.shields.io/badge/Next.js-16-111111?logo=next.js)
![React](https://img.shields.io/badge/React-19-149ECA?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent-4B5563)
![TypeScript](https://img.shields.io/badge/TypeScript-5.5-3178C6?logo=typescript)
![Docs](https://img.shields.io/badge/Docs-Updated-2563EB)

ShuaiTravelAgent 是一个面向真实旅行决策场景的 AI 旅行助手项目，覆盖“问问题 -> 生成方案 -> 调整预算/约束 -> 对比方案 -> 导出分享”的完整链路。

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
- 城市卡片决策信息：预算强度、步行强度、风格标签、推荐理由
- 候选池与对比池：先收藏，再进入并排对比
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
ShuaiTravelAgent/
├── agent/                  # Agent 图、节点、工具、记忆、checkpoint
├── web/                    # FastAPI 路由、服务、仓储、存储
├── frontend/               # Next.js 前端
├── tests/                  # 后端/集成测试
├── docs/                   # 文档中心
├── config/                 # 服务与模型配置
├── data/                   # 本地运行数据
└── scripts/                # benchmark / replay / quality gate 等脚本
```

更详细的目录说明见 [docs/reference/project-structure.md](docs/reference/project-structure.md)。

## 本地访问地址

- Frontend: `http://localhost:33001`
- API: `http://localhost:38000`
- API Docs: `http://localhost:38000/rapidoc`
- Health: `http://localhost:38000/api/health`

## 快速开始

### 1. 准备环境

- Python 3.13+
- Node.js 20+
- uv
- npm

### 2. 安装依赖

```bash
uv python install 3.13
uv venv .venv --python 3.13
.\.venv\Scripts\activate
uv pip install -r requirements.txt

cd frontend
npm install
cd ..
```

### 3. 准备配置

```bash
copy config\llm_config.yaml.example config\llm_config.yaml
```

根据实际模型服务填写 `api_key`、`api_base`、`model`。

### 4. 启动后端

```bash
.\.venv\Scripts\python.exe -m uvicorn shuai_web.main:app --host 0.0.0.0 --port 38000 --app-dir web
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

完整接口说明见 [docs/reference/api-reference.md](docs/reference/api-reference.md)。

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
python -m pytest tests -q
python scripts/docstring_audit.py --strict
```

### Agent 质量脚本

- `python scripts/agent_benchmark.py --output-dir docs/benchmarks`
- `python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0`
- `python scripts/agent_quality_gate.py --golden-report ... --benchmark-report ... --baseline-benchmark-report ...`

更多测试与回放说明见 [docs/testing/testing-guide.md](docs/testing/testing-guide.md)。

## 文档导航

- [docs/README.md](docs/README.md): 文档总入口
- [docs/getting-started/quick-start.md](docs/getting-started/quick-start.md): 快速启动
- [docs/getting-started/ai-travel-agent-zero-to-one.md](docs/getting-started/ai-travel-agent-zero-to-one.md): 面向新人的 AI 旅游 Agent 从 0 到 1 教学教程
- [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md): 系统架构
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
