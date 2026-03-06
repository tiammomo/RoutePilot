"""
================================================================================
LangGraph Agent 图构建器
================================================================================

使用 LangGraph 构建旅游 Agent 的状态图。

特性:
- 使用 ToolNode 执行真实工具
- 支持结构化输出意图识别
- 完整的流式输出支持
- 会话历史集成
- 对话摘要压缩

================================================================================
"""

import logging
from typing import Optional, AsyncGenerator
from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from .state import AgentState, create_initial_state, TRAVEL_AGENT_SYSTEM_PROMPT
from .nodes import AgentNodes

logger = logging.getLogger(__name__)


class TravelAgentGraph:
    """
    旅游 Agent LangGraph 构建器

    封装 LangGraph 的 StateGraph 构建逻辑
    支持：
    - 结构化输出意图识别
    - 真实工具执行
    - 异步流式输出
    """

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT
    ):
        """
        初始化

        Args:
            llm: LangChain LLM 实例
            tools: 工具列表
            system_prompt: 系统提示词
        """
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt

        # 创建节点
        self.nodes = AgentNodes(llm, tools, system_prompt)

        # 创建 ToolNode
        self.tool_node = ToolNode(tools)

        # 编译后的图
        self._graph: Optional[StateGraph] = None

    def build(self) -> StateGraph:
        """
        构建状态图

        Returns:
            编译后的 StateGraph
        """
        # 创建图
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("intent", self.nodes.intent_node)
        graph.add_node("router", self.nodes.router_node)
        graph.add_node("plan", self.nodes.plan_node)
        graph.add_node("execute", self.nodes.execute_node)
        graph.add_node("answer", self.nodes.answer_node)
        graph.add_node("direct_answer", self.nodes.direct_answer_node)

        # 设置入口点
        graph.set_entry_point("intent")

        # 添加边
        graph.add_edge("intent", "router")

        # 路由条件边
        graph.add_conditional_edges(
            "router",
            self.nodes.routing_decision,
            {
                "plan": "plan",
                "direct": "direct_answer"
            }
        )

        # 计划执行循环
        graph.add_edge("plan", "execute")

        # 判断是否继续执行
        graph.add_conditional_edges(
            "execute",
            self.nodes.should_continue,
            {
                "execute": "execute",
                "answer": "answer"
            }
        )

        # 答案生成后结束
        graph.add_edge("answer", END)
        graph.add_edge("direct_answer", END)

        # 编译图
        self._graph = graph.compile()

        logger.info("[Graph Builder] Graph built successfully")

        return self._graph

    @property
    def graph(self) -> StateGraph:
        """获取编译后的图"""
        if self._graph is None:
            self.build()
        return self._graph

    def invoke(self, state: dict) -> dict:
        """
        同步调用

        Args:
            state: 输入状态

        Returns:
            输出状态
        """
        return self.graph.invoke(state)

    async def ainvoke(self, state: dict) -> dict:
        """
        异步调用

        Args:
            state: 输入状态

        Returns:
            输出状态
        """
        return await self.graph.ainvoke(state)

    async def astream(self, state: dict):
        """
        异步流式调用

        Args:
            state: 输入状态

        Yields:
            输出状态块
        """
        async for chunk in self.graph.astream(state, stream_mode="values"):
            yield chunk

    async def astream_events(self, state: dict):
        """
        异步流式事件（包含中间步骤）

        这是更详细的流式输出，包括：
        - LLM token 生成
        - 工具调用开始/结束
        - 工具执行结果

        Args:
            state: 输入状态

        Yields:
            事件块
        """
        async for event in self.graph.astream_events(state, version="v1"):
            yield event


def build_travel_agent(
    llm: Runnable,
    tools: list[Tool],
    system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT
) -> TravelAgentGraph:
    """
    工厂函数：构建旅游 Agent

    Args:
        llm: LangChain LLM 实例
        tools: 工具列表
        system_prompt: 系统提示词

    Returns:
        TravelAgentGraph 实例
    """
    agent = TravelAgentGraph(llm, tools, system_prompt)
    return agent


async def run_travel_agent(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    system_prompt: str = None
) -> dict:
    """
    便捷函数：运行旅游 Agent

    Args:
        user_message: 用户消息
        llm: LangChain LLM 实例
        tools: 工具列表
        session_id: 会话ID
        system_prompt: 系统提示词

    Returns:
        处理结果
    """
    agent = build_travel_agent(llm, tools, system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT)

    # 创建初始状态
    initial_state = create_initial_state(
        user_message=user_message,
        session_id=session_id,
        system_message=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
    )

    # 异步调用
    result = await agent.ainvoke(initial_state)

    return {
        "success": True,
        "answer": result.get("answer", ""),
        "intent": result.get("intent"),
        "tools_used": result.get("tools_used", []),
        "reasoning": result.get("reasoning"),
        "messages": result.get("messages", [])
    }


async def run_travel_agent_streaming(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    system_prompt: str = None,
    on_token: callable = None,
    on_tool_start: callable = None,
    on_tool_end: callable = None
) -> dict:
    """
    带流式回调的便捷函数

    Args:
        user_message: 用户消息
        llm: LangChain LLM 实例
        tools: 工具列表
        session_id: 会话ID
        system_prompt: 系统提示词
        on_token: token 回调 (token: str)
        on_tool_start: 工具开始回调 (tool_name: str)
        on_tool_end: 工具结束回调 (tool_name: str, result: str)

    Returns:
        处理结果
    """
    agent = build_travel_agent(llm, tools, system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT)

    # 创建初始状态
    initial_state = create_initial_state(
        user_message=user_message,
        session_id=session_id,
        system_message=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
    )

    # 使用事件流获取详细输出
    answer = ""
    tools_used = []

    async for event in agent.astream_events(initial_state):
        event_type = event["event"]

        # LLM token
        if event_type == "on_chat_model_stream":
            if on_token and event["data"]["chunk"].content:
                await on_token(event["data"]["chunk"].content)
            answer += event["data"]["chunk"].content or ""

        # 工具调用开始
        elif event_type == "on_tool_start":
            tool_name = event["name"]
            tools_used.append(tool_name)
            if on_tool_start:
                await on_tool_start(tool_name)

        # 工具调用结束
        elif event_type == "on_tool_end":
            tool_name = event["name"]
            result = event["data"]["output"]
            if on_tool_end:
                await on_tool_end(tool_name, result)

    return {
        "success": True,
        "answer": answer,
        "tools_used": tools_used
    }


async def run_travel_agent_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str = None,
    on_token: callable = None,
    on_tool_start: callable = None,
    on_tool_end: callable = None
) -> dict:
    """
    带记忆的完整 Agent 调用

    集成会话历史和对话摘要：
    - 自动加载历史对话
    - 长对话自动摘要
    - 流式输出

    Args:
        user_message: 用户消息
        llm: LangChain LLM 实例
        tools: 工具列表
        session_id: 会话ID
        memory_manager: 记忆管理器（可选）
        system_prompt: 系统提示词
        on_token: token 回调
        on_tool_start: 工具开始回调
        on_tool_end: 工具结束回调

    Returns:
        处理结果
    """
    from .memory_integration import (
        get_agent_memory_manager,
        AgentStateWithMemory,
        ConversationSummarizer
    )

    # 获取或创建记忆管理器
    if memory_manager is None:
        summarizer = ConversationSummarizer(llm=llm, summary_threshold=15)
        memory_manager = get_agent_memory_manager(
            llm=llm,
            max_history=10,
            summary_threshold=15
        )

    # 使用 AgentStateWithMemory 创建状态（包含历史上下文）
    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
    )

    # 构建 Agent
    agent = build_travel_agent(llm, tools, system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT)

    # 执行结果
    answer = ""
    tools_used = []

    # 使用事件流
    async for event in agent.astream_events(initial_state):
        event_type = event["event"]

        # LLM token
        if event_type == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                answer += content
                if on_token:
                    await on_token(content)

        # 工具调用开始
        elif event_type == "on_tool_start":
            tool_name = event["name"]
            tools_used.append(tool_name)
            if on_tool_start:
                await on_tool_start(tool_name)

        # 工具调用结束
        elif event_type == "on_tool_end":
            tool_name = event["name"]
            result = event["data"]["output"]
            if on_tool_end:
                await on_tool_end(tool_name, result)

    # 保存对话到历史
    await memory_manager.add_message(session_id, "user", user_message)
    await memory_manager.add_message(session_id, "assistant", answer)

    return {
        "success": True,
        "answer": answer,
        "tools_used": tools_used,
        "session_id": session_id
    }


async def run_travel_agent_streaming_with_memory(
    user_message: str,
    llm: Runnable,
    tools: list[Tool],
    session_id: str = "default",
    memory_manager=None,
    system_prompt: str = None
):
    """
    带记忆的流式 Agent 调用（生成器版本）

    逐步 yield 各种事件，便于前端展示
    """
    from .memory_integration import (
        get_agent_memory_manager,
        AgentStateWithMemory
    )

    # 获取记忆管理器
    if memory_manager is None:
        memory_manager = get_agent_memory_manager(llm=llm)

    # 创建状态
    initial_state = AgentStateWithMemory.create(
        user_message=user_message,
        session_id=session_id,
        memory_manager=memory_manager,
        system_prompt=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
    )

    # 构建 Agent
    agent = build_travel_agent(llm, tools, system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT)

    answer = ""
    tools_used = []

    # 事件流
    async for event in agent.astream_events(initial_state):
        event_type = event["event"]

        if event_type == "on_node_start":
            node_name = event.get("name", "")
            if node_name == "intent":
                yield {"type": "reasoning", "content": "分析用户意图..."}
            elif node_name == "plan":
                yield {"type": "reasoning", "content": "制定执行计划..."}
            elif node_name == "execute":
                yield {"type": "reasoning", "content": "执行工具..."}

        elif event_type == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                answer += content
                yield {"type": "chunk", "content": content}

        elif event_type == "on_tool_start":
            tool_name = event["name"]
            tools_used.append(tool_name)
            yield {"type": "tool_start", "tool": tool_name}

        elif event_type == "on_tool_end":
            tool_name = event["name"]
            result = event["data"]["output"]
            yield {"type": "tool_end", "tool": tool_name, "result": str(result)[:100]}

    # 保存历史
    await memory_manager.add_message(session_id, "user", user_message)
    await memory_manager.add_message(session_id, "assistant", answer)

    yield {
        "type": "done",
        "answer": answer,
        "tools_used": tools_used,
        "session_id": session_id
    }
