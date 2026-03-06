# ShuaiTravelAgent 项目说明

## 项目概述

基于 **LangChain + LangGraph** 的智能旅游助手系统，提供城市推荐、景点查询、路线规划等功能。

## 技术栈

- **前端**: Next.js 16 + React 19 + TypeScript + Zustand + antd 6
- **后端 Web**: FastAPI + Python 3.10+
- **Agent**: LangChain + LangGraph
- **LLM**: MiniMax M2.5 (Anthropic 兼容 API)

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Web API | 38000 | FastAPI 服务 |
| Frontend | 33001 | Next.js 开发服务器 |

## API 端点

| 服务 | 地址 | 用途 |
|------|------|------|
| 前端 | http://localhost:33001 | Web UI |
| Web API | http://localhost:38000 | REST API |
| API 文档 | http://localhost:38000/rapidoc | RapiDoc 文档 |
| 健康检查 | http://localhost:38000/api/health | 服务健康状态 |

## 项目结构

```
ShuaiTravelAgent/
├── agent/src/
│   ├── config/           # 配置管理
│   ├── graph/            # LangGraph 核心
│   │   ├── state.py     # 状态定义
│   │   ├── nodes.py     # 节点实现
│   │   └── builder.py   # 图构建器
│   ├── llm/             # LLM 客户端
│   │   ├── client.py    # HTTP 客户端
│   │   └── langchain_adapter.py # LangChain 适配器
│   ├── memory/          # 记忆系统
│   │   └── chat_history.py # 对话历史
│   └── tools/           # 旅行工具
│       ├── travel_tools.py  # @tool 装饰器工具
│       └── travel_api.py   # API 客户端
├── web/src/
│   ├── main.py          # FastAPI 应用
│   ├── routes/         # API 路由
│   │   ├── chat_langchain.py
│   │   ├── session.py
│   │   └── health.py
│   └── services/       # 业务逻辑
├── frontend/           # Next.js 前端
├── config/             # 配置文件
└── run_api.py         # 启动脚本
```

## LLM 配置

```yaml
# config/llm_config.yaml
models:
  minimax-m2-5:
    name: "MiniMax M2.5"
    provider: anthropic
    model: "MiniMax-M2.5"
    api_base: "https://api.minimaxi.com/anthropic"
    api_key: "your-api-key"
```

## LangChain 工具

| 工具 | 功能 |
|------|------|
| `search_cities` | 搜索城市 |
| `query_attractions` | 查询景点 |
| `calculate_budget` | 计算预算 |
| `plan_itinerary` | 规划行程 |
| `get_travel_tips` | 旅行建议 |

## 使用示例

```python
from llm.langchain_adapter import create_from_yaml_config
from tools.travel_tools import get_travel_tools
from graph import build_travel_agent

llm = create_from_yaml_config("config/llm_config.yaml").chat_model
tools = get_travel_tools()
agent = build_travel_agent(llm, tools)
```

## 依赖

```
langchain>=0.3.0
langchain-core>=0.3.0
langgraph>=0.2.0
langchain-openai>=0.2.0
langchain-anthropic>=0.3.0
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
```

## 启动服务

```bash
# 方式1: 一键启动 (Windows)
start_all.bat

# 方式2: 分别启动
start_api.bat       # API 服务
start_frontend.bat  # 前端服务
```

## 测试

```bash
cd agent && PYTHONPATH=agent/src python -m pytest tests/ -v
```

## 对话模式

| 模式 | 说明 |
|------|------|
| `direct` | 直接回答 |
| `react` | LangGraph ReAct 推理 |
| `plan` | 计划后执行 |
