"""
================================================================================
LangGraph Agent 状态定义
================================================================================

定义旅游 Agent 的状态结构和类型。

State 结构:
- messages: 聊天消息历史
- intent: 用户意图识别结果
- plan: 执行计划
- current_step: 当前执行步骤
- tools_used: 已使用的工具列表
- tool_results: 工具执行结果
- answer: 最终答案
- session_id: 会话ID

使用示例:
```python
from graph.state import AgentState

# 创建初始状态
initial_state = AgentState(
    messages=[],
    session_id="default"
)
```

================================================================================
"""

from typing import TypedDict, Annotated, Optional, List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import add_messages


class AgentState(TypedDict):
    """
    Agent 状态定义

    使用 add_messages 注解实现消息自动追加
    """
    # 聊天消息历史（会自动追加新消息）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户意图
    intent: Optional[str]

    # 意图详情
    intent_detail: Optional[Dict[str, Any]]

    # 执行计划
    plan: Optional[List[Dict[str, Any]]]

    # 当前执行步骤索引
    current_step: int

    # 已使用的工具列表
    tools_used: List[str]

    # 工具执行结果
    tool_results: Dict[str, Any]

    # 最终答案
    answer: Optional[str]

    # 推理过程
    reasoning: Optional[str]

    # 会话ID
    session_id: str

    # 错误信息
    error: Optional[str]


def create_initial_state(
    user_message: str,
    session_id: str = "default",
    system_message: Optional[str] = None
) -> AgentState:
    """
    创建初始状态

    Args:
        user_message: 用户消息
        session_id: 会话ID
        system_message: 系统消息（可选）

    Returns:
        初始状态字典
    """
    messages = []

    # 添加系统消息
    if system_message:
        messages.append(SystemMessage(content=system_message))

    # 添加用户消息
    messages.append(HumanMessage(content=user_message))

    return AgentState(
        messages=messages,
        intent=None,
        intent_detail=None,
        plan=None,
        current_step=0,
        tools_used=[],
        tool_results={},
        answer=None,
        reasoning=None,
        session_id=session_id,
        error=None
    )


# 系统提示词
TRAVEL_AGENT_SYSTEM_PROMPT = """你是一个专业的旅游助手AI助手。你的职责是：

1. **理解用户需求**：分析用户的旅游相关问题，包括目的地推荐、景点查询、行程规划、预算计算等
2. **使用工具**：当需要具体信息时，使用提供的工具获取数据
3. **提供建议**：根据用户需求和工具返回的结果，提供专业、个性化的旅游建议

可用工具：
- search_cities: 搜索旅游城市
- query_attractions: 查询城市景点
- calculate_budget: 计算旅行预算
- plan_itinerary: 规划旅行路线
- get_travel_tips: 获取旅行建议

回答要求：
- 语言友好、亲切
- 内容实用、准确
- 结构清晰、条理分明
- 适当使用 emoji 增强可读性

注意：
- 如果用户问题不明确，主动询问以获取更多信息
- 如果工具调用失败，给出友好的错误提示
- 对于不确定的信息，坦诚告知用户"""
