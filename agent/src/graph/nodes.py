"""
================================================================================
LangGraph Agent 节点实现
================================================================================

定义 LangGraph 的各个节点函数：
- intent_node: 意图识别（使用 structured output）
- router_node: 路由决策
- plan_node: 计划构建
- execute_node: 工具执行（使用 ToolNode）
- answer_node: 答案生成

================================================================================
"""

import json
import logging
from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langchain_core.output_parsers import JsonOutputParser
from langgraph.prebuilt import ToolNode

from .state import AgentState, TRAVEL_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

class IntentResult(BaseModel):
    """意图识别结果"""
    intent: str
    confidence: float
    entities: dict
    requires_tools: bool


class PlanStep(BaseModel):
    """计划步骤"""
    step: int
    tool: str
    params: dict
    description: str


class ExecutionResult(BaseModel):
    """执行结果"""
    success: bool
    tool_name: str
    result: str
    error: Optional[str] = None


# ============================================================================
# 节点类
# ============================================================================

class AgentNodes:
    """LangGraph Agent 节点类"""

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT
    ):
        """
        初始化节点

        Args:
            llm: LangChain LLM 实例
            tools: 工具列表
            system_prompt: 系统提示词
        """
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.tool_map = {tool.name: tool for tool in tools}

        # 创建带工具的 LLM（用于工具调用）
        self.llm_with_tools = llm.bind_tools(tools)

        # 创建带 structured output 的 LLM（用于意图识别）
        try:
            self.llm_with_intent = llm.with_structured_output(IntentResult)
        except Exception as e:
            logger.warning(f"Structured output not available, using JSON parser: {e}")
            self.llm_with_intent = None
            self.intent_parser = JsonOutputParser(pydantic_object=IntentResult)

        # 创建 ToolNode（用于执行工具）
        self.tool_node = ToolNode(tools)

    def intent_node(self, state: AgentState) -> AgentState:
        """
        意图识别节点

        使用 structured output 或 JSON 解析识别用户意图
        """
        logger.info("[Intent Node] Analyzing user intent...")

        messages = state["messages"]
        last_message = messages[-1] if messages else ""

        intent_prompt = f"""请分析以下用户旅游咨询的意图。

用户消息: {last_message.content}

意图类别:
- recommend: 需要目的地推荐
- attractions: 查询景点信息
- itinerary: 需要行程规划
- budget: 需要预算计算
- tips: 需要旅行建议
- general: 一般性旅游问题
- unclear: 意图不明确

请返回 JSON 格式：
{{
    "intent": "意图类别",
    "confidence": 0.0-1.0,
    "entities": {{"key": "value"}},
    "requires_tools": true/false
}}"""

        try:
            # 尝试使用 structured output
            if self.llm_with_intent:
                result = self.llm_with_intent.invoke([
                    SystemMessage(content=intent_prompt)
                ])
                intent = result.intent
                intent_detail = {
                    "confidence": result.confidence,
                    "entities": result.entities,
                    "requires_tools": result.requires_tools
                }
            else:
                # 回退到 JSON 解析
                response = self.llm.invoke([SystemMessage(content=intent_prompt)])
                parsed = self.intent_parser.invoke(response)
                intent = parsed.get("intent", "general")
                intent_detail = {
                    "confidence": parsed.get("confidence", 0.5),
                    "entities": parsed.get("entities", {}),
                    "requires_tools": parsed.get("requires_tools", False)
                }

            logger.info(f"[Intent Node] Detected intent: {intent}")

            return {
                "intent": intent,
                "intent_detail": intent_detail
            }

        except Exception as e:
            logger.warning(f"[Intent Node] Failed to parse intent: {e}")
            return {
                "intent": "general",
                "intent_detail": {
                    "confidence": 0.5,
                    "entities": {},
                    "requires_tools": False
                }
            }

    def router_node(self, state: AgentState) -> AgentState:
        """
        路由决策节点

        根据意图决定下一步：
        - 需要工具 -> plan
        - 直接回答 -> direct
        """
        intent = state.get("intent", "general")
        intent_detail = state.get("intent_detail", {})

        requires_tools = intent_detail.get("requires_tools", False)

        if intent in ["recommend", "attractions", "itinerary", "budget", "tips"]:
            logger.info(f"[Router Node] Routing to 'plan' (intent: {intent})")
            return {" routing": "plan"}
        else:
            logger.info(f"[Router Node] Routing to 'direct' (intent: {intent})")
            return {"routing": "direct"}

    def routing_decision(self, state: AgentState) -> Literal["plan", "direct"]:
        """
        路由决策函数（用于条件边）

        返回路由目标：
        - plan: 需要工具执行
        - direct: 直接回答
        """
        routing = state.get("routing", "direct")
        return routing

    def plan_node(self, state: AgentState) -> AgentState:
        """
        计划构建节点

        根据意图构建执行计划
        """
        logger.info("[Plan Node] Building execution plan...")

        intent = state.get("intent", "general")
        intent_detail = state.get("intent_detail", {})
        entities = intent_detail.get("entities", {})

        # 根据意图构建计划
        if intent == "recommend":
            plan = [
                {"step": 1, "tool": "search_cities", "params": {"query": entities.get("query", "")}}
            ]
        elif intent == "attractions":
            plan = [
                {"step": 1, "tool": "query_attractions", "params": {
                    "city": entities.get("city", ""),
                    "category": entities.get("category")
                }}
            ]
        elif intent == "itinerary":
            plan = [
                {"step": 1, "tool": "query_attractions", "params": {"city": entities.get("city", "")}},
                {"step": 2, "tool": "plan_itinerary", "params": {
                    "destination": entities.get("city", ""),
                    "days": entities.get("days", 3),
                    "interests": entities.get("interests")
                }}
            ]
        elif intent == "budget":
            plan = [
                {"step": 1, "tool": "calculate_budget", "params": {
                    "destination": entities.get("destination", ""),
                    "days": entities.get("days", 3),
                    "people": entities.get("people", 1),
                    "accommodation_level": entities.get("level", "medium")
                }}
            ]
        elif intent == "tips":
            plan = [
                {"step": 1, "tool": "get_travel_tips", "params": {
                    "destination": entities.get("destination", ""),
                    "season": entities.get("season")
                }}
            ]
        else:
            plan = []

        logger.info(f"[Plan Node] Plan created with {len(plan)} steps")

        return {
            "plan": plan,
            "current_step": 0,
            "tools_used": [],
            "tool_results": {}
        }

    def execute_node(self, state: AgentState) -> AgentState:
        """
        工具执行节点

        执行计划中的工具（使用 ToolNode 或直接调用）
        """
        logger.info("[Execute Node] Executing tools...")

        plan = state.get("plan", [])
        current_step = state.get("current_step", 0)
        tool_results = state.get("tool_results", {})
        tools_used = state.get("tools_used", [])

        if current_step >= len(plan):
            logger.info("[Execute Node] No more steps to execute")
            return state

        # 执行当前步骤
        step = plan[current_step]
        tool_name = step.get("tool")
        params = step.get("params", {})

        logger.info(f"[Execute Node] Executing tool: {tool_name}")

        try:
            # 方式1: 使用 ToolNode（LangGraph 推荐）
            tool = self.tool_map.get(tool_name)
            if tool:
                # 构建 LangGraph 格式的消息
                from langchain_core.messages import ToolMessage
                tool_call_id = f"call_{tool_name}_{current_step}"

                # 调用工具
                result = tool.invoke(params)
                tool_results[tool_name] = result
                tools_used.append(tool_name)

                logger.info(f"[Execute Node] Tool {tool_name} executed successfully")
            else:
                logger.warning(f"[Execute Node] Tool not found: {tool_name}")
                tool_results[tool_name] = f"Tool not found: {tool_name}"

        except Exception as e:
            logger.error(f"[Execute Node] Tool execution failed: {e}")
            tool_results[tool_name] = f"Error: {str(e)}"

        return {
            "current_step": current_step + 1,
            "tools_used": tools_used,
            "tool_results": tool_results
        }

    def should_continue(self, state: AgentState) -> Literal["execute", "answer"]:
        """
        判断是否继续执行

        返回:
        - execute: 继续执行下一个工具
        - answer: 生成答案
        """
        plan = state.get("plan", [])
        current_step = state.get("current_step", 0)

        if current_step < len(plan):
            return "execute"
        return "answer"

    def answer_node(self, state: AgentState) -> AgentState:
        """
        答案生成节点

        根据工具结果生成最终回答
        """
        logger.info("[Answer Node] Generating answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else ""
        tool_results = state.get("tool_results", {})
        tools_used = state.get("tools_used", [])

        # 构建上下文
        context = ""
        if tool_results:
            context += "\n\n## 工具执行结果:\n"
            for tool_name, result in tool_results.items():
                context += f"\n### {tool_name}:\n{result}\n"

        # 构建提示词
        if tools_used:
            prompt = f"""用户问题: {last_message.content}

{context}

请根据以上工具执行结果，用友好的方式回答用户的问题。"""
        else:
            prompt = f"""用户问题: {last_message.content}

请直接回答用户的旅游相关问题。"""

        # 调用 LLM 生成回答
        response = self.llm.invoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ])

        answer = response.content

        # 添加 AI 消息到历史
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info(f"[Answer Node] Answer generated, length: {len(answer)}")

        return {
            "messages": messages,
            "answer": answer,
            "reasoning": f"使用工具: {', '.join(tools_used)}" if tools_used else "直接回答"
        }

    def direct_answer_node(self, state: AgentState) -> AgentState:
        """
        直接回答节点

        不使用工具，直接生成回答
        """
        logger.info("[Direct Answer Node] Generating direct answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else ""

        # 调用 LLM 直接回答
        response = self.llm.invoke([
            SystemMessage(content=self.system_prompt),
            last_message
        ])

        answer = response.content

        # 添加 AI 消息到历史
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info(f"[Direct Answer Node] Answer generated, length: {len(answer)}")

        return {
            "messages": messages,
            "answer": answer,
            "reasoning": "直接回答（无需工具）"
        }


def create_nodes(llm: Runnable, tools: list[Tool]) -> AgentNodes:
    """
    工厂函数：创建节点实例

    Args:
        llm: LangChain LLM 实例
        tools: 工具列表

    Returns:
        AgentNodes 实例
    """
    return AgentNodes(llm, tools)
