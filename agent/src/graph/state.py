"""State model and defaults for the travel agent graph."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """Shared mutable state flowing through LangGraph nodes."""

    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[str]
    intent_detail: Optional[Dict[str, Any]]
    routing: Optional[str]
    plan_id: Optional[str]
    plan_explanation: Optional[str]
    plan: Optional[List[Dict[str, Any]]]
    current_step: int
    execution_state: Optional[Dict[str, Any]]
    execution_stats: Optional[Dict[str, Any]]
    tools_used: List[str]
    tool_results: Dict[str, Any]
    answer: Optional[str]
    reasoning: Optional[str]
    session_id: str
    error: Optional[str]


def create_initial_state(
    user_message: str,
    session_id: str = "default",
    system_message: Optional[str] = None,
) -> AgentState:
    """Build initial graph state for one user turn."""
    messages: list[BaseMessage] = []
    if system_message:
        messages.append(SystemMessage(content=system_message))
    messages.append(HumanMessage(content=user_message))

    return AgentState(
        messages=messages,
        intent=None,
        intent_detail=None,
        routing=None,
        plan_id=None,
        plan_explanation=None,
        plan=None,
        current_step=0,
        execution_state=None,
        execution_stats=None,
        tools_used=[],
        tool_results={},
        answer=None,
        reasoning=None,
        session_id=session_id,
        error=None,
    )


TRAVEL_AGENT_SYSTEM_PROMPT = """你是一位专业旅行助理，需要帮助用户完成旅行决策与规划。

你的职责：
1. 准确理解用户意图（目的地推荐、景点查询、行程规划、预算评估、出行建议等）。
2. 必要时调用工具获取信息，不编造工具结果。
3. 基于用户需求与工具结果，给出可执行、结构化、贴近现实的建议。

可用工具：
- search_cities: 搜索旅游城市
- query_attractions: 查询城市景点
- calculate_budget: 估算旅行预算
- plan_itinerary: 生成行程建议
- get_travel_tips: 提供旅行提醒与建议

回答要求：
- 语气清晰、友好、专业。
- 优先给出结论，再给关键依据和可选方案。
- 对不确定信息明确说明不确定性。
- 当用户信息不足时，先提 1-2 个澄清问题。
- 如果工具调用失败，给出可行替代方案，而不是直接中断。"""
