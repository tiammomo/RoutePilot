# LangChain + LangGraph 重构进度

## 重构概述

本项目已基于 **LangChain 1.x** 和 **LangGraph** 完成了 Agent 系统的重构。

## 已完成

### Phase 1: 基础设施 ✅

| 模块 | 文件 | 状态 |
|------|------|------|
| 依赖 | `requirements.txt` | ✅ |
| LLM 适配 | `llm/langchain_adapter.py` | ✅ |
| 工具系统 | `tools/travel_tools.py` | ✅ |
| 真实 API | `tools/travel_api.py` | ✅ 新增 |
| 状态定义 | `graph/state.py` | ✅ |
| 节点实现 | `graph/nodes.py` | ✅ |
| 图构建器 | `graph/builder.py` | ✅ |
| Memory | `memory/chat_history.py` | ✅ |

### Phase 2: Web API 集成 ✅

| 模块 | 文件 | 说明 |
|------|------|------|
| API 路由 | `web/src/routes/chat_langchain.py` | LangChain 版聊天接口 |
| 主应用 | `web/src/main.py` | 更新为使用新路由 |

### Phase 3: 错误处理与重试机制 ✅

| 模块 | 文件 | 说明 |
|------|------|------|
| 异常类 | `graph/error_handling.py` | AgentError、ToolExecutionError 等 |
| 重试装饰器 | `graph/error_handling.py` | retry_with_backoff 指数退避 |
| 恢复策略 | `graph/error_handling.py` | ErrorRecoveryStrategy |
| 错误中间件 | `graph/error_handling.py` | AgentErrorMiddleware |

### Phase 4: 单元测试 ✅

| 模块 | 文件 | 说明 |
|------|------|------|
| LangGraph 测试 | `tests/test_langchain_graph.py` | 状态、节点、图、工具测试 |

### Phase 5: 性能优化 ✅

| 模块 | 文件 | 说明 |
|------|------|------|
| LRU 缓存 | `graph/performance.py` | LRUCache 支持 TTL |
| 语义缓存 | `graph/performance.py` | SemanticCache 相似度缓存 |
| 并发控制 | `graph/performance.py` | ConcurrencyLimiter、RateLimiter |
| 性能监控 | `graph/performance.py` | PerformanceMonitor |

### Phase 6: v3.3 记忆与完整 Agent ✅

| 模块 | 文件 | 说明 |
|------|------|------|
| 记忆集成 | `graph/memory_integration.py` | 跨会话记忆 |
| 对话摘要 | `graph/memory_integration.py` | 长对话自动压缩 |
| 完整 Agent | `graph/builder.py` | run_travel_agent_with_memory |
| Web API 集成 | `web/src/routes/chat_langchain.py` | 使用完整 Agent |

---

## v3.3 新功能

### 1. 会话历史集成

自动加载历史对话，保持上下文连贯性。

```python
from graph import get_agent_memory_manager

# 创建记忆管理器
memory_mgr = get_agent_memory_manager(llm)

# 获取历史上下文
context = memory_mgr.get_context("session_123")
# [HumanMessage(content="我想去北京"), AIMessage(content="北京是个不错的选择...")]
```

### 2. 对话摘要压缩

当对话超过阈值（默认20条）时自动生成摘要，压缩 token 使用。

```python
from graph import ConversationSummarizer

summarizer = ConversationSummarizer(
    llm=llm,
    summary_threshold=15  # 超过15条消息时触发摘要
)

# 检查是否需要摘要
if summarizer.should_summarize(messages):
    summary = await summarizer.summarize(messages)
```

### 3. 完整 Agent 调用

使用 `AgentStateWithMemory` 创建包含历史的状态：

```python
from graph import (
    build_travel_agent,
    AgentStateWithMemory,
    get_agent_memory_manager
)

# 创建记忆管理器
memory_mgr = get_agent_memory_manager(llm)

# 创建带记忆的状态
state = AgentStateWithMemory.create(
    user_message="推荐一个城市",
    session_id="session_123",
    memory_manager=memory_mgr
)

# 使用 Agent 执行
agent = build_travel_agent(llm, tools)
async for event in agent.astream_events(state):
    print(event)
```

---

## 当前架构

```
┌─────────────────────────────────────────┐
│           Web API (FastAPI)              │
│         chat_langchain.py                │
│    (SSE 流式, Session 记忆, 摘要)       │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│         LangGraph StateGraph             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Intent  │─▶│  Plan   │─▶│ Execute │ │
│  │(struct) │  │ Builder │  │(ToolNode)│ │
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
│     记忆管理层 (AgentMemoryManager)      │
│  ┌──────────┐  ┌──────────┐            │
│  │ ChatHistory│  │ Summarizer│           │
│  │(持久化)  │  │(自动压缩) │            │
│  └──────────┘  └──────────┘            │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│     错误处理 & 性能优化                   │
│  ┌──────────┐  ┌──────────┐            │
│  │ErrorHandle│  │Performance│           │
│  │(retry)   │  │(cache)    │            │
│  └──────────┘  └──────────┘            │
└─────────────────────────────────────────┘
```

---

## 新增 SSE 事件类型

| 事件 | 说明 | 数据结构 |
|------|------|---------|
| `tool_start` | 工具调用开始 | `{"type": "tool_start", "tool": "search_cities"}` |
| `tool_end` | 工具调用结束 | `{"type": "tool_end", "tool": "search_cities", "result": "..."}` |
| `reasoning` | 推理过程 | `{"type": "reasoning", "content": "分析用户意图..."}` |

---

## 使用示例

### 方式1: 简单调用

```python
from graph import run_travel_agent

result = await run_travel_agent("推荐一个城市", llm, tools)
print(result["answer"])
```

### 方式2: 流式调用

```python
from graph import run_travel_agent_streaming

result = await run_travel_agent_streaming(
    "推荐一个城市",
    llm,
    tools,
    on_token=lambda t: print(t, end="")
)
```

### 方式3: 带记忆的完整 Agent

```python
from graph import run_travel_agent_with_memory, get_agent_memory_manager

# 创建记忆管理器
memory_mgr = get_agent_memory_manager(llm)

# 带记忆调用
result = await run_travel_agent_with_memory(
    "推荐一个海边城市",
    llm,
    tools,
    session_id="user123",
    memory_manager=memory_mgr,
    on_token=lambda t: print(t, end="")
)

print(result["answer"])
# 后续对话会自动包含历史上下文
```

### 方式4: 生成器版本

```python
# 逐步获取事件，便于前端展示
async for event in run_travel_agent_streaming_with_memory(
    "推荐城市",
    llm,
    tools,
    session_id="123"
):
    if event["type"] == "chunk":
        print(event["content"], end="")
    elif event["type"] == "tool_start":
        print(f"\n[调用工具: {event['tool']}]")
    elif event["type"] == "done":
        print(f"\n[完成] 使用了 {event['tools_used']} 个工具")
```

---

## 依赖

```txt
langchain>=0.3.0
langchain-core>=0.3.0
langgraph>=0.2.0
langgraph-prebuilt>=0.1.0
langchain-community>=0.3.0
langchain-openai>=0.2.0
langchain-anthropic>=0.3.0
pydantic>=2.0
pytest>=7.0
pytest-asyncio>=0.21
```

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python run_api.py

# 打开前端
cd frontend && npm run dev
```

---

## v3.4 规划

- [ ] Human-in-the-loop（工具执行确认）
- [ ] 断点续话（支持暂停/恢复）
- [ ] 动态工具选择
- [ ] 多轮对话规划
