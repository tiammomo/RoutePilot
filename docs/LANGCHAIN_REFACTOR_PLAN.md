# LangChain + LangGraph 重构规划

## 1. 现有架构分析

### 当前问题
- 代码过于复杂，ReAct 循环手动实现
- 多层抽象导致维护困难
- 缺少标准化的 Agent 框架
- Memory 管理与业务逻辑耦合

### 现有组件（需重构）
| 组件 | 当前实现 | LangChain/LangGraph 替代 |
|------|----------|--------------------------|
| ReAct 引擎 | `core/react_agent.py` | LangGraph `create_react_agent` |
| 工具系统 | `core/travel_tools.py` | LangChain `@tool` 装饰器 |
| Memory | `memory/manager.py` | LangChain `BaseChatMessageHistory` |
| 多Agent | `multiagent/orchestrator.py` | LangGraph `MultiAgent` |
| 工作流 | `core/workflow_engine.py` | LangGraph `StateGraph` |

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Web API (FastAPI)                       │
│                     chat_simple.py                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangChain Agent                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              LangGraph StateGraph                    │   │
│  │  ┌─────────┐   ┌─────────┐   ┌─────────┐          │   │
│  │  │ Intent  │──▶│  Plan   │──▶│ Execute │──▶│ Answer │  │
│  │  │ Router  │   │ Builder │   │ Tools   │   │ Gen    │  │
│  │  └─────────┘   └─────────┘   └─────────┘          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    LangChain Components                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  LLM Chat    │  │   Tools      │  │   Memory     │   │
│  │  (ChatModel) │  │  (@tool)     │  │ (MessageHistory)│  │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 重构模块设计

### 3.1 LLM 适配层 (`agent/src/llm/`)

```python
# agent/src/llm/langchain_adapter.py
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.chat_models import BaseChatModel

class LangChainLLMAdapter:
    """适配现有配置到 LangChain"""

    def __init__(self, config: dict):
        self.config = config
        self._chat_model = self._create_chat_model()

    def _create_chat_model(self) -> BaseChatModel:
        provider = self.config.get('provider')
        if provider == 'anthropic':
            return ChatAnthropic(
                model=self.config.get('model', 'claude-3-sonnet-20240229'),
                anthropic_api_key=self.config.get('api_key'),
                base_url=self.config.get('api_base'),
                temperature=self.config.get('temperature', 0.7),
                max_tokens=self.config.get('max_tokens', 2000)
            )
        elif provider == 'openai-compatible':
            return ChatOpenAI(
                model=self.config.get('model', 'gpt-4o-mini'),
                openai_api_key=self.config.get('api_key'),
                base_url=self.config.get('api_base'),
                temperature=self.config.get('temperature', 0.7),
                max_tokens=self.config.get('max_tokens', 2000)
            )
        # ... 其他 provider
```

### 3.2 工具系统 (`agent/src/tools/`)

```python
# agent/src/tools/travel_tools.py
from langchain_core.tools import tool

@tool
def search_cities(query: str) -> str:
    """搜索旅游城市

    Args:
        query: 搜索关键词，如城市名、景点类型

    Returns:
        城市列表信息
    """
    # 实现搜索逻辑
    pass

@tool
def query_attractions(city: str, category: str = None) -> str:
    """查询城市景点

    Args:
        city: 城市名称
        category: 景点类别（可选）

    Returns:
        景点列表
    """
    pass

@tool
def plan_route(start: str, days: int, preferences: str = None) -> str:
    """规划旅行路线

    Args:
        start: 出发城市
        days: 旅行天数
        preferences: 偏好设置（可选）

    Returns:
        路线规划结果
    """
    pass

# 工具列表
TRAVEL_TOOLS = [search_cities, query_attractions, plan_route]
```

### 3.3 Memory 管理 (`agent/src/memory/`)

```python
# agent/src/memory/chat_history.py
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import BaseMessage

class SessionChatHistory:
    """会话级别的聊天历史"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._history = ChatMessageHistory()

    def add_user_message(self, message: str):
        self._history.add_user_message(message)

    def add_ai_message(self, message: str):
        self._history.add_ai_message(message)

    def get_messages(self) -> list[BaseMessage]:
        return self._history.messages

    def clear(self):
        self._history.clear()
```

### 3.4 LangGraph 状态定义

```python
# agent/src/graph/state.py
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

class AgentState(TypedDict):
    """Agent 状态定义"""
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str | None
    plan: list[dict] | None
    tools_used: list[str]
    answer: str | None
    session_id: str
```

### 3.5 LangGraph 节点

```python
# agent/src/graph/nodes.py
from langchain_core.runnables import Runnable
from langgraph.prebuilt import ToolNode

class AgentNodes:
    """LangGraph 节点定义"""

    def __init__(self, llm: Runnable, tools: list):
        self.llm = llm
        self.tools = tools
        self.tool_node = ToolNode(tools)

    def intent_router(self, state: AgentState) -> AgentState:
        """意图路由节点"""
        # 使用 LLM 判断用户意图
        # 返回路由决策
        pass

    def plan_builder(self, state: AgentState) -> AgentState:
        """计划构建节点"""
        pass

    def tool_executor(self, state: AgentState) -> AgentState:
        """工具执行节点"""
        return self.tool_node.invoke(state)

    def answer_generator(self, state: AgentState) -> AgentState:
        """答案生成节点"""
        pass
```

### 3.6 主 Agent 构建

```python
# agent/src/graph/travel_agent.py
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, END

class LangGraphTravelAgent:
    """基于 LangGraph 的旅游 Agent"""

    def __init__(self, llm, tools, memory):
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self._build_graph()

    def _build_graph(self):
        """构建 LangGraph"""
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("intent", self.intent_router)
        graph.add_node("plan", self.plan_builder)
        graph.add_node("execute", self.tool_executor)
        graph.add_node("answer", self.answer_generator)

        # 添加边
        graph.set_entry_point("intent")
        graph.add_edge("intent", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "answer")
        graph.add_edge("answer", END)

        self.graph = graph.compile()

    async def process(self, message: str, session_id: str = "default"):
        """处理用户消息"""
        # 添加用户消息到历史
        self.memory.add_user_message(message)

        # 执行图
        result = await self.graph.ainvoke({
            "messages": [HumanMessage(content=message)],
            "session_id": session_id
        })

        # 保存 AI 响应
        ai_message = result["messages"][-1].content
        self.memory.add_ai_message(ai_message)

        return {
            "success": True,
            "answer": ai_message,
            "intent": result.get("intent"),
            "tools_used": result.get("tools_used", [])
        }
```

---

## 4. 文件结构规划

```
agent/src/
├── llm/
│   ├── __init__.py
│   ├── langchain_adapter.py     # LangChain LLM 适配器
│   └── factory.py               # 工厂函数
├── tools/
│   ├── __init__.py
│   ├── travel_tools.py          # 旅游工具 (@tool)
│   ├── weather_tools.py         # 天气工具
│   └── registry.py              # 工具注册表
├── memory/
│   ├── __init__.py
│   ├── chat_history.py          # 聊天历史
│   └── factory.py               # Memory 工厂
├── graph/
│   ├── __init__.py
│   ├── state.py                 # 状态定义
│   ├── nodes.py                 # 节点实现
│   ├── edges.py                 # 边定义
│   ├── agent.py                 # 主 Agent
│   └── builder.py               # 图构建器
└── application/
    ├── __init__.py
    └── travel_app.py            # 应用层封装
```

---

## 5. 依赖更新

```txt
# requirements.txt
# LangChain 核心
langchain>=0.3.0
langchain-core>=0.3.0

# LangGraph
langgraph>=0.2.0
langgraph-prebuilt>=0.1.0

# LangChain 社区
langchain-community>=0.3.0

# 模型提供商
langchain-openai>=0.2.0
langchain-anthropic>=0.3.0

# 保留现有依赖
PyYAML>=6.0.1
python-dotenv>=1.0.0
httpx>=0.25.0

# 可选：向量存储（如需要 RAG）
# langchain-milvus
# langchain-chroma

# 测试
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

---

## 6. 实施步骤

### Phase 1: 基础设施（1-2天）
- [ ] 更新依赖
- [ ] 创建 LLM 适配器
- [ ] 创建基础工具

### Phase 2: LangGraph 核心（2-3天）
- [ ] 定义 Agent 状态
- [ ] 实现节点逻辑
- [ ] 构建状态图

### Phase 3: Memory 集成（1天）
- [ ] 实现 ChatMessageHistory
- [ ] 集成会话管理

### Phase 4: 测试与调优（1-2天）
- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能调优

---

## 7. 迁移策略

1. **并行运行**: 新旧 Agent 共存，逐步切换
2. **配置驱动**: 通过配置选择使用哪个 Agent
3. **功能兼容**: 保持 API 接口不变
4. **逐步替换**: 按模块逐步迁移
