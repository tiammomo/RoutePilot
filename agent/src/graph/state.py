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
    strategy: Optional[str]
    strategy_detail: Optional[Dict[str, Any]]
    routing: Optional[str]
    plan_id: Optional[str]
    plan_explanation: Optional[str]
    plan: Optional[List[Dict[str, Any]]]
    current_step: int
    execution_round: int
    parallelism: Optional[int]
    max_parallelism: Optional[int]
    execution_state: Optional[Dict[str, Any]]
    execution_stats: Optional[Dict[str, Any]]
    execution_summary: Optional[Dict[str, Any]]
    execution_trace: Optional[List[Dict[str, Any]]]
    execution_budget: Optional[Dict[str, Any]]
    fused_tool_results: Optional[Dict[str, Any]]
    early_stop_reason: Optional[str]
    verify_retry_count: int
    verify_result: Optional[Dict[str, Any]]
    self_check_result: Optional[Dict[str, Any]]
    tools_used: List[str]
    tool_results: Dict[str, Any]
    answer: Optional[str]
    reasoning: Optional[str]
    session_id: str
    run_id: Optional[str]
    error: Optional[str]


def create_initial_state(
    user_message: str,
    session_id: str = "default",
    system_message: Optional[str] = None,
    run_id: Optional[str] = None,
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
        strategy=None,
        strategy_detail=None,
        routing=None,
        plan_id=None,
        plan_explanation=None,
        plan=None,
        current_step=0,
        execution_round=0,
        parallelism=None,
        max_parallelism=None,
        execution_state=None,
        execution_stats=None,
        execution_summary=None,
        execution_trace=[],
        execution_budget=None,
        fused_tool_results=None,
        early_stop_reason=None,
        verify_retry_count=0,
        verify_result=None,
        self_check_result=None,
        tools_used=[],
        tool_results={},
        answer=None,
        reasoning=None,
        session_id=session_id,
        run_id=run_id,
        error=None,
    )


TRAVEL_AGENT_SYSTEM_PROMPT = """你是专业旅行助手，负责帮助用户完成旅行决策与规划。

你的职责:
1. 准确识别用户意图（推荐、景点、行程、预算、出行建议）。
2. 需要事实时调用工具，不编造工具结果。
3. 输出结构化、可执行、贴近现实的建议。

约束:
1. 遵循 ReAct：Thought -> Action -> Observation。
2. 避免重复调用同一工具同一参数。
3. 价格/政策/签证/退改类高风险信息，必须基于工具验证后回答。

回答风格:
1. 先结论，再依据，再可选方案。
2. 不确定信息要明确标注不确定性。
3. 信息不足时只提出 1-2 个澄清问题。
4. 工具失败时给降级方案，不要中断回复。
"""
