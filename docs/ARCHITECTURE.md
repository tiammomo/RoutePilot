# 系统架构设计文档

## 1. 架构概述

小帅旅游助手采用 **五层架构设计** (Five-Layer Architecture)，从底层到顶层依次为：

1. **Infrastructure Layer (基础设施层)** - 基础服务支撑
2. **Framework Layer (框架层)** - 核心框架能力
3. **Middleware Layer (中间件层)** - 中间件服务
4. **Algorithm Layer (算法层)** - 算法和逻辑
5. **Application Layer (应用层)** - 应用入口和编排

---

## 2. 五层架构详解

### 2.1 Infrastructure Layer (基础设施层)

基础设施层提供系统运行所需的基础服务能力。

| 模块 | 职责 | 关键技术 |
|-----|------|---------|
| LLM Client | 多协议 LLM 客户端 | OpenAI、Anthropic、Gemini、Ollama、MiniMax |
| HTTP Client | HTTP 请求处理 | aiohttp、httpx、重试机制 |
| Snowflake ID | 分布式唯一 ID 生成 | Twitter Snowflake 算法 |
| Redis Queue | 消息队列 | Redis Streams、分布式锁 |
| Milvus Vector | 向量数据库 | Milvus、相似度检索 |
| Nacos Config | 配置中心 | Nacos、配置热更新 |
| SSE Streaming | SSE 流式输出 | Server-Sent Events |

**代码位置**: `agent/src/infrastructure/`

**相关文档**:
- [基础设施文档](INFRASTRUCTURE.md)
- [集成测试设计](INTEGRATION_TESTS.md)

### 2.2 Framework Layer (框架层)

框架层提供 ReAct Agent 运行所需的核心框架能力。

| 模块 | 职责 | 关键类 |
|-----|------|-------|
| ReAct Engine | 推理循环引擎 | `ReActEngine` |
| Node Types | 节点类型定义 | `ActionNode`, `AgentNode`, `LoopNode`, etc. |
| State Manager | 状态管理 | `StateManager` |
| SSE Streamer | SSE 流式输出 | `SSEStreamer` |
| Prompt Manager | Prompt 模板管理 | `PromptManager` |

**代码位置**: `agent/src/framework/`

### 2.3 Middleware Layer (中间件层)

中间件层提供高级中间件服务。

| 模块 | 职责 | 关键类 |
|-----|------|-------|
| RAG Retriever | 检索增强生成 | `RAGRetriever`, `MilvusRAGRetriever` |
| Memory System | 记忆系统 | `ShortTermMemory`, `LongTermMemory`, `RedisMemoryManager` |

**代码位置**: `agent/src/middleware/`, `agent/src/memory/`

**相关文档**:
- [INFRASTRUCTURE.md#RAG-检索服务](INFRASTRUCTURE.md#rag-检索服务)
- [集成测试设计 - RAG 测试](INTEGRATION_TESTS.md#中间件测试)

### 2.4 Algorithm Layer (算法层)

算法层实现核心业务算法。

| 模块 | 职责 |
|-----|------|
| Travel Agent | 旅游助手 Agent |
| Travel Tools | 工具工厂和执行器 |
| Response Generator | 响应生成和格式化 |
| Exception Handler | 异常处理框架 |

**代码位置**: `agent/src/core/`

### 2.5 Application Layer (应用层)

应用层是系统的入口点，负责工作流编排。

| 模块 | 职责 |
|-----|------|
| Travel Application | 旅游应用入口 |
| Workflow Orchestration | 节点化工作流编排 |

**代码位置**: `agent/src/application/`

---

## 3. 节点类型设计

系统支持 6 种节点类型，构建灵活的节点化工作流。

### 3.1 节点类型列表

| 节点类型 | 枚举值 | 说明 | 执行方法 |
|---------|-------|------|---------|
| ActionNode | `action` | 动作节点，执行具体操作 | `execute_action()` |
| AgentNode | `agent` | Agent 节点，复杂推理 | `execute_agent()` |
| LoopNode | `loop` | 循环节点，重复执行 | `execute_loop()` |
| DecisionNode | `decision` | 决策节点，条件分支 | `make_decision()` |
| PreparationNode | `preparation` | 准备节点，数据准备 | `prepare()` |
| PersistenceNode | `persistence` | 持久化节点，保存状态 | `persist()` |

### 3.2 节点状态

| 状态 | 说明 |
|-----|------|
| `pending` | 等待执行 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 执行失败 |
| `skipped` | 跳过 |
| `cancelled` | 取消 |

### 3.3 工作流示例

```
用户输入
    │
    ▼
┌─────────────────┐
│ PreparationNode │  ← 准备上下文
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  DecisionNode   │  ← 判断复杂度
└────────┬────────┘
    ┌─────┴─────┐
    │           │
  简单        复杂
    │           │
    ▼           ▼
┌───────┐  ┌─────────────┐
│Action │  │ LoopNode     │  ← 循环执行
│ Node  │  └──────┬──────┘
└───┬───┘         │
    │             ▼
    │        ┌──────────┐
    │        │ AgentNode│  ← Agent 推理
    │        └────┬─────┘
    │             │
    └──────┬────┘
           │
           ▼
    ┌──────────────┐
    │ Persistence   │  ← 持久化结果
    │ Node          │
    └──────────────┘
```

---

## 4. ReAct 推理循环

### 4.1 ReAct 核心概念

ReAct (Reasoning + Acting) 是一种结合推理和行动的 AI 范式。

```
┌─────────────────────────────────────────────────────────────┐
│                      ReAct 循环                              │
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│  │  Think  │───▶│  Act    │───▶│ Observe │───▶│ Evaluate│  │
│  │  思考   │    │  行动   │    │  观察   │    │  评估   │  │
│  └─────────┘    └─────────┘    └─────────┘    └────┬────┘  │
│       ▲                                           │       │
│       │                                           │       │
│       └───────────────────────────────────────────┘       │
│                    (继续/结束)                          │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 阶段划分

| 阶段 | 说明 | 思考内容示例 |
|-----|------|-------------|
| 阶段一 | 理解任务 | 解析用户意图、提取实体 |
| 阶段二 | 制定计划 | 制定执行步骤、确定工具 |
| 阶段三 | 执行工具 | 调用工具、观察结果 |
| 阶段四 | 生成回答 | 整合结果、生成回复 |

---

## 5. 记忆系统设计

### 5.1 三层记忆架构

```
┌─────────────────────────────────────────┐
│           Working Memory (工作记忆)      │
│    当前对话的中间状态和推理过程            │
│         最大 10 条推理步骤               │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Short Term (短期记忆)            │
│      当前会话的消息历史                  │
│         最大 20 条消息                   │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│         Long Term (长期记忆)             │
│       跨会话的重要信息和偏好              │
│         最大 50 条记录                   │
└─────────────────────────────────────────┘
```

### 5.2 记忆类型

| 类型 | 存储内容 | 生命周期 |
|-----|---------|---------|
| episodic | 具体经历和事件 | 会话内 |
| semantic | 知识性信息 | 长期 |
| procedural | 操作步骤和流程 | 长期 |

---

## 6. RAG 检索增强

### 6.1 检索器类型

| 检索器 | 说明 | 使用场景 |
|-------|------|----------|
| `RAGRetriever` | 纯内存检索 | 开发测试、无外部依赖 |
| `MilvusRAGRetriever` | Milvus 向量检索 | 生产环境、大规模数据 |
| `create_milvus_retriever()` | 智能创建工厂 | 自动降级到内存模式 |

### 6.2 混合检索策略

```
┌─────────────────────────────────────────────────────────────┐
│                      RAG 查询流程                            │
│                                                             │
│  用户查询                                                   │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────┐                                             │
│  │ 查询重写   │  ← 优化查询语句                              │
│  └──────┬──────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐                                             │
│  │ 混合检索   │  ← BM25 + 向量相似度                        │
│  └──────┬──────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐                                             │
│  │ 结果融合   │  ← MMR 策略                                  │
│  └──────┬──────┘                                            │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐                                             │
│  │ 上下文注入  │  ← 注入到 Prompt                           │
│  └─────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 检索配置

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| top_k | 返回结果数量 | 5 |
| chunk_size | 文档块大小 | 200 |
| chunk_overlap | 块重叠大小 | 20 |
| weight_bm25 | BM25 权重 | 0.3 |
| weight_vector | 向量权重 | 0.7 |

---

## 7. SSE 流式输出

### 7.1 SSE 事件类型

| 事件类型 | 说明 | 数据结构 |
|---------|------|---------|
| `message` | 普通消息 | `{"type": "message", "content": "..."}` |
| `thinking` | 思考过程 | `{"type": "thinking", "thought": "..."}` |
| `tool_call` | 工具调用 | `{"type": "tool_call", "tool": "...", "parameters": {...}}` |
| `tool_result` | 工具结果 | `{"type": "tool_result", "tool": "...", "result": {...}}` |
| `done` | 完成信号 | `{"type": "done", "answer": "..."}` |
| `error` | 错误 | `{"type": "error", "message": "..."}` |
| `heartbeat` | 心跳 | `{"type": "heartbeat", "timestamp": "..."}` |

### 7.2 心跳配置

| 参数 | 说明 | 默认值 |
|-----|------|-------|
| heartbeat_interval | 心跳间隔 | 15秒 |
| reconnect_timeout | 重连超时 | 300秒 |
| max_buffer_size | 最大缓冲事件数 | 1000 |

---

## 8. 项目结构

```
agent/src/
├── application/              # 5. 应用层
│   ├── travel_app.py        # 旅游应用入口
│   └── __init__.py
├── framework/                # 4. 框架层
│   ├── node_types.py        # 节点类型定义
│   ├── state_manager.py     # 状态管理
│   └── __init__.py
├── middleware/              # 3. 中间件层
│   ├── rag.py              # RAG 检索增强
│   ├── milvus_rag.py       # Milvus 向量检索
│   └── __init__.py
├── core/                    # 核心模块
│   ├── travel_agent.py      # ReAct Agent 实现
│   ├── react_agent.py       # ReAct 引擎核心
│   ├── travel_tools.py      # 工具工厂
│   ├── response_generator.py # 响应生成
│   ├── exceptions.py        # 异常处理
│   └── __init__.py
├── di/                      # 依赖注入容器
│   └── __init__.py         # 依赖注入框架
├── memory/                  # 记忆系统 (v2.2)
│   ├── redis_memory.py      # Redis 记忆管理
│   ├── factory.py          # 记忆工厂
│   ├── manager.py           # 基础记忆管理
│   ├── orchestrator.py     # 统一记忆协调器
│   ├── importance_scorer.py  # 重要性评分
│   ├── eviction_manager.py # 淘汰管理
│   ├── summarizer.py       # 对话摘要
│   ├── user_profile.py     # 用户画像
│   ├── hierarchical_store.py # 分层存储
│   ├── consolidation.py    # 记忆整合
│   ├── attention.py         # 注意力窗口 (v2.2)
│   ├── reflection.py        # 反思机制 (v2.2)
│   ├── eviction_policy.py  # 智能淘汰策略 (v2.2)
│   ├── vectorizer.py       # 对话向量化 (v2.2)
│   ├── recirculation.py     # 记忆回流 (v2.2)
│   └── retrieval.py         # 上下文检索 (v2.2)
├── infrastructure/          # 2. 基础设施层
│   ├── streaming.py        # SSE 流式输出
│   ├── prompt_manager.py   # Prompt 模板
│   ├── snowflake.py       # Snowflake ID
│   ├── http_client.py     # HTTP 客户端
│   ├── http_pool.py       # HTTP 连接池
│   ├── infra_config.py    # 基础设施配置
│   ├── config_hot_reload.py # 配置热更新
│   ├── llm_cache.py       # LLM 响应缓存（内存）
│   └── __init__.py
└── graph/                 # LangGraph 核心
    ├── state.py           # Agent 状态定义
    ├── nodes.py          # 节点实现
    ├── builder.py        # 图构建器
    └── __init__.py
```

> **v3.x 变化**: 移除 gRPC server、Redis 队列、Milvus 向量、Nacos 客户端，集成到 LangGraph

**新增组件**:
- `di/__init__.py` - 依赖注入容器，支持单例/瞬态服务注册
- `infrastructure/http_pool.py` - HTTP 连接池，支持请求缓存和去重
- `infrastructure/llm_cache.py` - LLM 响应缓存（Redis）

**配置文件分层**:
- `config/llm_config.yaml` - LLM 模型配置
- `config/agent_config.yaml` - Agent 行为配置
- `config/infrastructure_config.yaml` - 基础设施配置
- `memory/redis_memory.py` - Redis 记忆存储
- `memory/factory.py` - 记忆管理器工厂
- `middleware/milvus_rag.py` - Milvus RAG 检索器
- `infrastructure/config_hot_reload.py` - 配置热更新

---

## 9. 通信协议

### 9.1 服务间通信

| 服务 | 协议 | 端口 | 说明 |
|-----|------|------|------|
| Web API | HTTP + SSE | 38000 | REST API + LangGraph Agent |
| Agent | (已集成) | - | LangGraph 推理引擎 |

### 9.2 SSE vs WebSocket

| 特性 | SSE | WebSocket |
|-----|-----|-----------|
| 协议 | HTTP | TCP |
| 方向 | 服务器推送 | 双向 |
| 自动重连 | 原生支持 | 需手动实现 |
| 浏览器支持 | 广泛 | 广泛 |
| 适用场景 | 服务器单向推送 | 实时双向通信 |

---

## 10. 配置管理

### 10.1 配置文件

```
config/
├── llm_config.yaml           # 实际配置 (git 忽略)
└── llm_config.yaml.example   # 配置模板
```

### 10.2 配置层次

| 层级 | 说明 | 文件 |
|-----|------|------|
| 全局配置 | 默认配置 | 代码中的默认值 |
| 用户配置 | 用户自定义 | config/llm_config.yaml |
| 环境变量 | 运行时配置 | 环境变量覆盖 |

---

## 11. 扩展指南

### 11.1 添加新工具

1. 在 `core/tools/` 中创建工具类
2. 继承 `BaseTool` 基类
3. 实现 `execute()` 方法
4. 注册到工具工厂

### 11.2 添加新节点类型

1. 在 `framework/node_types.py` 中定义节点类
2. 继承 `BaseNode` 基类
3. 实现 `execute()` 方法
4. 在 `NodeCategory` 枚举中添加类型

### 11.3 添加新 LLM Provider

1. 在 `infrastructure/llm_client.py` 中实现 Provider 类
2. 继承 `BaseLLMClient` 基类
3. 实现 `chat()` 和 `stream_chat()` 方法
4. 在 Provider 注册表中注册

---

## 12. 组件速查表

### 12.1 Agent 模块组件清单

| 组件 | 文件路径 | 作用 | 关键类/函数 |
|------|----------|------|------------|
| **ReAct 引擎** | `core/react_agent.py` | 推理循环核心 | `ReActAgent.execute()` |
| **旅游 Agent** | `core/travel_agent.py` | 旅游领域逻辑 | `TravelAgent` |
| **LLM 客户端** | `llm/client.py` | LLM 调用 | `LLMClient` |
| **模型管理器** | `llm/manager.py` | 模型配置管理 | `ModelManager` |
| **工具系统** | `core/travel_tools.py` | 工具注册执行 | `_register_tools()` |
| **意图识别** | `core/intent_recognizer.py` | 用户意图分析 | `IntentRecognizer` |
| **响应生成** | `core/response_generator.py` | 格式化响应 | `ResponseGenerator` |
| **RAG 检索器** | `middleware/milvus_rag.py` | 向量检索 | `MilvusRAGRetriever` |
| **Redis 记忆** | `memory/redis_memory.py` | Redis 记忆存储 | `RedisMemoryManager` |
| **配置管理** | `config/config_manager.py` | 多配置文件管理 | `ConfigManager` |
| **配置热更新** | `infrastructure/config_hot_reload.py` | Nacos 配置 | `ConfigHotReload` |
| **依赖注入** | `di/__init__.py` | 依赖注入容器 | `Container` |
| **HTTP 连接池** | `infrastructure/http_pool.py` | HTTP 连接复用 | `HTTPConnectionPool` |
| **LLM 缓存** | `infrastructure/llm_cache.py` | LLM 响应缓存 | `LLMResponseCache` |
| **LangGraph** | `graph/` | Agent 推理引擎 | `build_travel_agent()` |

### 12.2 Web 模块组件清单

| 组件 | 文件路径 | 作用 | 关键函数 |
|------|----------|------|----------|
| **FastAPI 应用** | `main.py` | 应用入口 | `create_app()` |
| **聊天路由** | `routes/chat.py` | SSE 流式接口 | `/api/chat/stream` |
| **会话路由** | `routes/session.py` | 会话 CRUD | `/api/sessions` |
| **模型路由** | `routes/model.py` | 模型列表 | `/api/models` |
| **LangGraph 调用** | `routes/chat_langchain.py` | Agent 推理 | `run_travel_agent()` |

### 12.3 Frontend 模块组件清单

| 组件 | 文件路径 | 作用 |
|------|----------|------|
| **AppContext** | `context/AppContext.tsx` | 全局状态管理 |
| **API 服务** | `services/api.ts` | HTTP/SSE 客户端 |
| **聊天区域** | `components/ChatArea.tsx` | 主聊天界面 |
| **消息列表** | `components/MessageList.tsx` | 消息气泡 |
| **侧边栏** | `components/Sidebar.tsx` | 会话管理 |
| **思考步骤** | `components/TaskSteps.tsx` | 推理展示 |

### 12.4 快速定位指南

| 需求 | 修改文件 |
|------|----------|
| 添加新工具 | `agent/src/core/travel_tools.py` |
| 修改 Agent 逻辑 | `agent/src/core/travel_agent.py` |
| 调整 LLM 调用 | `agent/src/llm/client.py` |
| 添加 API 接口 | `web/src/routes/*.py` |
| 修改前端界面 | `frontend/src/components/*.tsx` |
| 调整全局状态 | `frontend/src/context/AppContext.tsx` |
| 修改配置格式 | `agent/src/config/config_manager.py` |
| 添加 RAG 逻辑 | `agent/src/middleware/milvus_rag.py` |
| 依赖注入配置 | `agent/src/di/__init__.py` |
| HTTP 连接池调优 | `agent/src/infrastructure/http_pool.py` |
| LLM 响应缓存 | `agent/src/infrastructure/llm_cache.py` |

---

## 13. Docker 全栈部署

### 13.1 容器化架构

项目支持 Docker Compose 一键部署全部服务，包括应用服务和基础设施服务。

```
v3.x 架构（推荐）
├── Web API + Agent (38000)        - FastAPI + LangGraph
└── Frontend (33001)              - Next.js 前端

> v3.x 移除 Docker Compose，Agent 集成到 Web API
│
├── 基础设施服务
│   ├── redis         (6379)       - 消息队列/缓存
│   ├── milvus        (19530)      - 向量数据库
│   ├── milvus-etcd   (2379)       - Milvus 元数据
│   ├── milvus-minio  (9001)       - Milvus 存储
│   ├── nacos         (38848)      - 配置中心
│   └── mysql         (3306)       - Nacos 数据库
│
└── 网络: shuai-network (bridge)
```

### 13.2 多阶段构建

所有应用服务使用多阶段 Dockerfile 构建，优化镜像大小：

| 服务 | 基础镜像 | 构建策略 |
|------|----------|----------|
| Agent | python:3.10-slim | 虚拟环境 + 二阶段构建 |
| Web | python:3.10-slim | 虚拟环境 + 二阶段构建 |
| Frontend | node:20-alpine | deps → builder → runner 三阶段 (standalone 模式) |

### 13.3 服务依赖关系

```
frontend → web → agent → redis, milvus
                   └──→ milvus → milvus-etcd, milvus-minio
            nacos → mysql
```

### 13.4 启动命令

```bash
# 一键启动所有服务
docker-compose up -d

# 仅启动基础设施
docker-compose up -d redis milvus-etcd milvus-minio milvus nacos mysql

# 构建并启动应用服务
docker-compose up -d --build agent web frontend

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f agent web frontend
```

### 13.5 相关文件

| 文件 | 说明 |
|------|------|
| `docker-compose.yml` | 全栈服务编排 |
| `agent/Dockerfile` | Agent 多阶段构建 |
| `web/Dockerfile` | Web API 多阶段构建 |
| `frontend/Dockerfile` | Frontend 多阶段构建 (Next.js standalone) |

---

## 14. LangChain + LangGraph 架构 (v3.x)

> **重要更新**: v3.x 已迁移到 LangChain 1.x + LangGraph 框架

### 14.1 新架构概览

```
┌─────────────────────────────────────────┐
│           Web API (FastAPI)              │
│         chat_langchain.py                │
│    (SSE 流式响应, Session 持久化)        │
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

### 14.2 新增组件

| 组件 | 文件路径 | 说明 |
|------|----------|------|
| LangChain 适配器 | `agent/src/llm/langchain_adapter.py` | 适配现有配置到 LangChain |
| LangGraph 状态 | `agent/src/graph/state.py` | AgentState 状态定义 |
| LangGraph 节点 | `agent/src/graph/nodes.py` | 意图识别、路由、执行、答案生成 |
| LangGraph 构建器 | `agent/src/graph/builder.py` | 图构建和运行 |
| LangChain 工具 | `agent/src/tools/travel_tools.py` | @tool 装饰器工具 |
| LangChain Memory | `agent/src/memory/chat_history.py` | 会话历史管理 |

### 14.3 LangGraph 节点流程

```
用户输入 → Intent(意图识别) → Router(路由决策)
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
        Plan 模式              Direct 模式              其他
              │                       │                       │
              ▼                       ▼                       ▼
        计划构建              直接生成答案            直接生成答案
              │                       │                       │
              ▼                       │                       │
        工具执行 ────────────────────┘                       │
              │                                               │
              ▼                                               │
        判断是否继续 ◀───────────────────────────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
  继续执行          生成答案
     │                 │
     └────────┬────────┘
              ▼
           结束
```

### 14.4 新工具系统

使用 LangChain `@tool` 装饰器定义：

| 工具 | 功能 |
|------|------|
| `search_cities` | 搜索旅游城市 |
| `query_attractions` | 查询城市景点 |
| `calculate_budget` | 计算旅行预算 |
| `plan_itinerary` | 规划旅行路线 |
| `get_travel_tips` | 获取旅行建议 |

### 14.5 服务架构变化

| 对比项 | v2.x | v3.x |
|--------|------|------|
| Agent 服务 | 独立 gRPC (50051) | 集成到 Web API |
| Agent 框架 | 自定义 ReAct | LangChain + LangGraph |
| 工具定义 | 函数注册 | @tool 装饰器 |
| 状态管理 | 手动管理 | LangGraph StateGraph |
| Memory | 纯 Python | LangChain Memory |

### 14.6 快速开始

```bash
# 安装依赖
install_deps.bat

# 测试 LangChain Agent
cd agent
PYTHONPATH=src python application/test_langchain.py

# 启动服务（只需 Web API）
python run_api.py
```

### 14.7 相关文档

- [LangChain 重构规划](LANGCHAIN_REFACTOR_PLAN.md)
- [LangChain 重构进度](LANGCHAIN_REFACTOR_PROGRESS.md)
