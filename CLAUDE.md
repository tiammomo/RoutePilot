# ShuaiTravelAgent 项目说明

## 项目概述

基于 **LangChain 1.x + LangGraph** 的智能旅游助手系统，提供城市推荐、景点查询、路线规划等功能。采用 **Frontend + Web API + LangGraph Agent** 三层架构。

## 技术栈

- **前端**: Next.js 16 + React 19 + TypeScript + Zustand + antd 6
- **后端 Web**: FastAPI + Python 3.10+
- **Agent**: LangChain 1.x + LangGraph（已移除 gRPC）
- **LLM**: MiniMax M2.5 (Anthropic 兼容 API) + SiliconFlow Embedding

## 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Web API | 38000 | FastAPI 服务（整合 Agent） |
| Frontend | 33001 | Next.js 开发服务器 |

> **注意**: v3.x 已移除独立的 Agent gRPC 服务，Agent 逻辑已集成到 Web API 中

## API 端点

| 服务 | 地址 | 用途 |
|------|------|------|
| 前端 | http://localhost:33001 | Web UI |
| Web API | http://localhost:38000 | REST API + LangGraph Agent |
| API 文档 | http://localhost:38000/rapidoc | RapiDoc 文档 |
| 健康检查 | http://localhost:38000/api/health | 服务健康状态 |
| 流式聊天 | http://localhost:38000/api/chat/stream | SSE 流式响应 |

## 核心配置文件

| 文件 | 用途 |
|------|------|
| `config/server_config.yaml` | 服务端口配置 |
| `config/llm_config.yaml` | LLM 模型配置（对话+Embedding） |
| `frontend/.env.local` | 前端环境变量 |

## 项目结构

```
ShuaiTravelAgent/
├── agent/                      # AI Agent 模块（LangChain）
│   ├── src/
│   │   ├── llm/               # LLM 客户端
│   │   │   ├── client.py           # 原有客户端
│   │   │   ├── langchain_adapter.py # LangChain 适配器（新增）
│   │   │   └── factory.py
│   │   ├── tools/             # 工具系统
│   │   │   ├── travel_tools.py     # LangChain @tool 工具（新增）
│   │   │   └── registry.py
│   │   ├── graph/             # LangGraph 核心（新增）
│   │   │   ├── state.py           # 状态定义
│   │   │   ├── nodes.py           # 节点实现
│   │   │   ├── builder.py         # 图构建器
│   │   │   └── __init__.py
│   │   ├── memory/            # 记忆系统
│   │   │   ├── chat_history.py    # LangChain Memory（新增）
│   │   │   ├── manager.py
│   │   │   └── factory.py
│   │   ├── core/              # 原有 ReAct 引擎（保留）
│   │   ├── di/                # 依赖注入容器
│   │   ├── multiagent/        # 多 Agent 系统
│   │   ├── skills/            # 技能系统
│   │   └── application/       # 应用层
│   │       ├── langchain_demo.py  # LangChain 演示
│   │       └── test_langchain.py  # 测试脚本
│   └── tests/
│
├── web/                        # Web API 模块 (FastAPI, 端口 38000)
│   ├── src/
│   │   ├── main.py            # 主应用（已更新为使用 LangChain）
│   │   ├── routes/
│   │   │   ├── chat_langchain.py  # LangChain 版聊天 API
│   │   │   └── session.py         # 会话管理
│   │   └── ...
│
├── frontend/                   # 前端模块 (Next.js, 端口 33001)
├── config/                     # 配置文件
├── docs/                       # 设计文档
│   ├── LANGCHAIN_REFACTOR_PLAN.md   # LangChain 重构规划
│   └── LANGCHAIN_REFACTOR_PROGRESS.md # 重构进度
├── tests/                      # 测试
├── run_api.py                # API 启动脚本
├── install_deps.bat          # LangChain 依赖安装脚本
└── requirements.txt           # Python 依赖
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
    api_key: "sk-cp-..."
    temperature: 0.7
    max_tokens: 2000

  gpt-4o-mini:
    name: "gpt-4o-mini"
    provider: openai-compatible
    model: "gpt-4o-mini"
    api_base: "https://api.zhiercourse.com/v1"
    api_key: "sk-..."
    temperature: 0.7
    max_tokens: 2000

  bce-embedding-base_v1:
    name: "bce-embedding-base_v1"
    provider: openai-compatible
    model: "netease-youdao/bce-embedding-base_v1"
    api_base: "https://api.siliconflow.cn/v1"
    api_key: "sk-..."
    embedding_dim: 768
```

## LangChain + LangGraph 架构

### 架构图

```
┌─────────────────────────────────────────┐
│           Web API (FastAPI)              │
│         chat_langchain.py                │
│    (SSE 流式响应, Session 持久化)         │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         LangGraph StateGraph             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Intent  │─▶│  Plan   │─▶│ Execute │ │
│  │ Router  │  │ Builder │  │ Tools   │ │
│  └─────────┘  └─────────┘  └─────────┘ │
│                          │              │
│                          ▼              │
│                   ┌─────────────┐       │
│                   │    Answer   │       │
│                   └─────────────┘       │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│           LangChain 组件                  │
│  ┌──────────┐  ┌──────────┐            │
│  │    LLM   │  │  @tool   │            │
│  │ ChatModel│  │  Tools   │            │
│  └──────────┘  └──────────┘            │
└─────────────────────────────────────────┘
```

### LangGraph 节点流程

```
用户输入 → 意图识别(Intent) → 路由决策(Router)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              Plan 模式           Direct 模式          其他
                    │                   │                   │
                    ▼                   ▼                   ▼
              计划构建          直接生成答案          直接生成答案
                    │                   │                   │
                    ▼                   │                   │
              工具执行 ───────────────┘                   │
                    │                                       │
                    ▼                                       │
              判断是否继续 ◀──────────────────────────────┘
                    │
           ┌────────┴────────┐
           ▼                 ▼
        继续执行           生成答案
           │                 │
           └────────┬────────┘
                    ▼
                 结束
```

## LangChain 工具

| 工具 | 功能 | 描述 |
|------|------|------|
| `search_cities` | 搜索城市 | 根据关键词搜索旅游城市 |
| `query_attractions` | 查询景点 | 获取城市景点信息，支持分类筛选 |
| `calculate_budget` | 计算预算 | 估算旅行费用 |
| `plan_itinerary` | 规划行程 | 生成每日行程安排 |
| `get_travel_tips` | 旅行建议 | 获取目的地旅行小贴士 |

## 使用示例

### 方式1: 使用便捷函数

```python
from llm.langchain_adapter import create_from_yaml_config
from tools.travel_tools import get_travel_tools
from graph import run_travel_agent

# 初始化
llm = create_from_yaml_config("config/llm_config.yaml").chat_model
tools = get_travel_tools()

# 处理请求
result = await run_travel_agent("推荐一个城市", llm, tools)
print(result["answer"])
```

### 方式2: 构建 Agent 对象

```python
from llm.langchain_adapter import create_from_yaml_config
from tools.travel_tools import get_travel_tools
from graph import build_travel_agent, create_initial_state

llm = create_from_yaml_config("config/llm_config.yaml").chat_model
tools = get_travel_tools()
agent = build_travel_agent(llm, tools)

# 调用
state = create_initial_state("推荐一个城市", session_id="test")
result = await agent.ainvoke(state)
print(result["answer"])
```

## 依赖

```txt
# LangChain 核心
langchain>=0.3.0
langchain-core>=0.3.0

# LangGraph
langgraph>=0.2.0
langgraph-prebuilt.0

#>=0.1 LangChain 社区
langchain-community>=0.3.0

# 模型提供商
langchain-openai>=0.2.0
langchain-anthropic>=0.3.0

# Web 框架
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
```

## Python 环境

项目使用 Anaconda 虚拟环境：

- **环境名称**: `agents`
- **环境路径**: `D:\anaconda\envs\agents`
- **Python 版本**: 3.10+

### 激活环境

```bash
conda activate agents
```

## 启动服务

```bash
# 0. 激活 Python 环境
conda activate agents

# 1. 安装 LangChain 依赖（首次）
install_deps.bat

# 或手动安装
pip install langchain langgraph langchain-openai langchain-anthropic

# 2. 启动 Web API 服务
python run_api.py

# 3. 启动前端
cd frontend && npm run dev
```

## 测试

```bash
# LangChain Agent 测试
cd agent
PYTHONPATH=src python application/test_langchain.py

# LangChain 演示
PYTHONPATH=src python application/langchain_demo.py
```

## Session 持久化

- Session 数据保存在 `data/sessions/sessions.json`
- 自动清理 24 小时过期的 Session
- 支持 Web API 重启后恢复会话

## 对话模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| `direct` | 直接回答，无推理循环 | 简单问题 |
| `react` | LangGraph ReAct 推理 | 需要工具调用的复杂问题 |
| `plan` | 计划后执行 | 长途旅行规划、多日行程 |

## 已移除的组件

| 组件 | 原用途 | 现状 |
|------|--------|------|
| gRPC 服务 | Agent 通信 | 已移除，Agent 集成到 Web API |
| Redis | 消息队列、会话存储 | 内存存储 |
| Milvus | 向量检索 | 内存版本 RAG |
| Nacos | 配置中心 | 本地 YAML 配置 |

## 迁移指南

### 从 gRPC 版迁移

1. 不再需要单独启动 `run_agent.py`
2. Agent 逻辑已集成到 `web/src/routes/chat_langchain.py`
3. 只需启动 `python run_api.py` 即可

### 更新依赖

```bash
# 安装新依赖
pip install langchain langgraph langchain-openai langchain-anthropic

# 或使用安装脚本
install_deps.bat
```
