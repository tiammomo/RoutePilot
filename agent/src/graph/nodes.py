from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langgraph.prebuilt import ToolNode

from .state import AgentState, TRAVEL_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
DEFAULT_TOOL_TIMEOUT_SECONDS = 20
DEFAULT_TOOL_MAX_RETRIES = 1
DEFAULT_TOOL_PARALLELISM = 2
DEFAULT_TOOL_COOLDOWN_SECONDS = 45
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3


class IntentResult(BaseModel):
    intent: str
    confidence: float
    entities: dict
    requires_tools: bool


class PlanStep(BaseModel):
    step: int
    tool: str
    params: dict
    description: str


class ExecutionResult(BaseModel):
    success: bool
    tool_name: str
    result: Any
    attempt: int = 1
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error_code: Optional[str] = None
    error: Optional[str] = None


class AgentNodes:
    """LangGraph node implementations for the travel agent."""

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        system_prompt: str | None = None,
        planner_hooks: Optional[dict[str, Callable[[dict], list[dict]]]] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
        self.tool_map = {tool.name: tool for tool in tools}
        self._planner_hooks = planner_hooks or {}

        self.llm_with_tools = llm.bind_tools(tools)
        try:
            try:
                self.llm_with_intent = llm.with_structured_output(IntentResult, method="function_calling")
            except TypeError:
                self.llm_with_intent = llm.with_structured_output(IntentResult)
        except Exception as exc:
            logger.warning("Structured output unavailable; fallback to JSON parser: %s", exc)
            self.llm_with_intent = None
            self.intent_parser = JsonOutputParser(pydantic_object=IntentResult)

        self.tool_node = ToolNode(tools)
        self._tool_health: dict[str, dict[str, Any]] = {}
        self._tool_timeout_sla: dict[str, int] = {
            "search_cities": 10,
            "query_attractions": 15,
            "query_hotels": 15,
            "calculate_budget": 8,
            "plan_itinerary": 20,
            "get_travel_tips": 8,
            "get_weather": 10,
        }

    def intent_node(self, state: AgentState) -> AgentState:
        logger.info("[Intent Node] Analyzing user intent...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")

        intent_prompt = f"""请分析以下用户旅游咨询的意图。

用户消息: {last_message.content}

意图类别:
- recommend: 需要目的地推荐
- attractions: 查询景点信息
- itinerary: 需要行程规划
- budget: 需要预算估算
- tips: 需要旅行建议
- general: 一般性旅游问题
- unclear: 意图不明确

请返回 JSON 格式:
{{
    "intent": "意图类别",
    "confidence": 0.0-1.0,
    "entities": {{"key": "value"}},
    "requires_tools": true/false
}}"""

        try:
            if self.llm_with_intent:
                result = self.llm_with_intent.invoke([SystemMessage(content=intent_prompt)])
                intent = result.intent
                intent_detail = {
                    "confidence": result.confidence,
                    "entities": result.entities,
                    "requires_tools": result.requires_tools,
                }
            else:
                response = self.llm.invoke([SystemMessage(content=intent_prompt)])
                parsed = self.intent_parser.invoke(response)
                intent = parsed.get("intent", "general")
                intent_detail = {
                    "confidence": parsed.get("confidence", 0.5),
                    "entities": parsed.get("entities", {}),
                    "requires_tools": parsed.get("requires_tools", False),
                }

            logger.info("[Intent Node] Detected intent=%s", intent)
            return {"intent": intent, "intent_detail": intent_detail}
        except Exception as exc:
            logger.warning("[Intent Node] Failed to parse intent: %s", exc)
            return {
                "intent": "general",
                "intent_detail": {
                    "confidence": 0.5,
                    "entities": {},
                    "requires_tools": False,
                },
            }

    def router_node(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "general")
        intent_detail = state.get("intent_detail", {})
        requires_tools = bool(intent_detail.get("requires_tools", False))

        if requires_tools or intent in {"recommend", "attractions", "itinerary", "budget", "tips"}:
            logger.info("[Router Node] Routing to plan (intent=%s, requires_tools=%s)", intent, requires_tools)
            return {"routing": "plan"}

        logger.info("[Router Node] Routing to direct (intent=%s)", intent)
        return {"routing": "direct"}

    def routing_decision(self, state: AgentState) -> Literal["plan", "direct"]:
        return state.get("routing", "direct")

    def plan_node(self, state: AgentState) -> AgentState:
        logger.info("[Plan Node] Building execution plan...")

        intent = state.get("intent", "general")
        entities = (state.get("intent_detail") or {}).get("entities", {})

        planner_hook = self._planner_hooks.get(intent)
        if planner_hook:
            try:
                plan = planner_hook(entities)
            except Exception as exc:
                logger.warning("[Plan Node] Planner hook failed (intent=%s): %s", intent, exc)
                plan = []
        else:
            plan = self._default_plan(intent, entities)

        normalized_plan = self._normalize_plan(plan)
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        logger.info("[Plan Node] Plan created with %d steps (plan_id=%s)", len(normalized_plan), plan_id)
        return {
            "plan_id": plan_id,
            "plan_explanation": self._build_plan_explanation(intent, normalized_plan),
            "plan": normalized_plan,
            "current_step": 0,
            "execution_state": {"completed": [], "failed": [], "blocked": []},
            "execution_stats": {"plan_id": plan_id, "started_at": datetime.now().isoformat(), "steps": []},
            "tools_used": [],
            "tool_results": {},
        }

    async def execute_node(self, state: AgentState) -> AgentState:
        logger.info("[Execute Node] Executing tools...")

        plan = state.get("plan", []) or []
        execution_state = state.get("execution_state", {}) or {}
        completed = set(execution_state.get("completed", []))
        failed = set(execution_state.get("failed", []))
        blocked = set(execution_state.get("blocked", []))
        tool_results = state.get("tool_results", {})
        tools_used = state.get("tools_used", [])
        execution_stats = state.get("execution_stats", {}) or {"steps": []}
        stats_steps = list(execution_stats.get("steps", []))

        if not plan:
            logger.info("[Execute Node] No plan to execute")
            return state

        pending = [s for s in plan if s["step_id"] not in completed and s["step_id"] not in failed and s["step_id"] not in blocked]
        if not pending:
            logger.info("[Execute Node] No pending plan steps")
            return state

        runnable: list[dict[str, Any]] = []
        for step in pending:
            deps = set(step.get("depends_on", []))
            if deps.issubset(completed):
                runnable.append(step)

        if not runnable:
            blocked_steps = []
            for step in pending:
                if set(step.get("depends_on", [])) & failed:
                    blocked_steps.append(step)
            if blocked_steps:
                for step in blocked_steps:
                    sid = step["step_id"]
                    blocked.add(sid)
                    key = f"{sid}:{step.get('tool')}"
                    tool_results[key] = ExecutionResult(
                        success=False,
                        tool_name=step.get("tool", ""),
                        result="",
                        error_code="DEPENDENCY_FAILED",
                        error=f"Dependent step failed: {step.get('depends_on', [])}",
                    ).model_dump()
                    stats_steps.append(
                        {
                            "step_id": sid,
                            "tool": step.get("tool"),
                            "status": "blocked",
                            "error_code": "DEPENDENCY_FAILED",
                            "duration_ms": 0,
                        }
                    )
            return {
                "current_step": len(completed) + len(failed) + len(blocked),
                "execution_state": {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)},
                "execution_stats": {**execution_stats, "steps": stats_steps},
                "tool_results": tool_results,
                "tools_used": tools_used,
            }

        parallelism = min(
            int(state.get("parallelism", DEFAULT_TOOL_PARALLELISM)),
            int(state.get("max_parallelism", DEFAULT_TOOL_PARALLELISM)),
            len(runnable),
        )
        selected = runnable[: max(1, parallelism)]
        tasks = [self._execute_plan_step(step) for step in selected]
        batch_results = await asyncio.gather(*tasks)

        for step, result_obj, elapsed_ms in batch_results:
            step_id = step["step_id"]
            result_key = f"{step_id}:{result_obj.tool_name}"
            tool_results[result_key] = result_obj.model_dump()
            tools_used.append(result_obj.tool_name)
            if result_obj.success:
                completed.add(step_id)
                self._mark_tool_success(result_obj.tool_name)
            else:
                failed.add(step_id)
                self._mark_tool_failure(result_obj.tool_name)

            stats_steps.append(
                {
                    "step_id": step_id,
                    "tool": result_obj.tool_name,
                    "depends_on": step.get("depends_on", []),
                    "status": "success" if result_obj.success else "failed",
                    "attempt": result_obj.attempt,
                    "error_code": result_obj.error_code,
                    "started_at": result_obj.started_at,
                    "ended_at": result_obj.ended_at,
                    "duration_ms": elapsed_ms,
                }
            )

        return {
            "current_step": len(completed) + len(failed) + len(blocked),
            "execution_state": {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)},
            "execution_stats": {**execution_stats, "steps": stats_steps},
            "tools_used": tools_used,
            "tool_results": tool_results,
        }

    def should_continue(self, state: AgentState) -> Literal["execute", "answer"]:
        plan = state.get("plan", []) or []
        execution_state = state.get("execution_state", {}) or {}
        completed = len(execution_state.get("completed", []))
        failed = len(execution_state.get("failed", []))
        blocked = len(execution_state.get("blocked", []))
        finished = completed + failed + blocked
        return "execute" if finished < len(plan) else "answer"

    def answer_node(self, state: AgentState) -> AgentState:
        logger.info("[Answer Node] Generating answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")
        tool_results = state.get("tool_results", {})
        tools_used = state.get("tools_used", [])
        plan_id = state.get("plan_id")
        execution_stats = state.get("execution_stats", {}) or {}

        context = ""
        if plan_id:
            context += f"\n\n## 执行计划ID:\n{plan_id}\n"
        if execution_stats.get("steps"):
            context += "\n## 步骤执行统计:\n"
            for item in execution_stats.get("steps", []):
                context += (
                    f"- {item.get('step_id')} {item.get('tool')} {item.get('status')}"
                    f" ({item.get('duration_ms', 0)}ms)\n"
                )
        if tool_results:
            context += "\n\n## 工具执行结果:\n"
            for tool_name, result in tool_results.items():
                if isinstance(result, dict):
                    if result.get("success"):
                        rendered = result.get("result")
                    else:
                        rendered = f"[{result.get('error_code')}] {result.get('error')}"
                else:
                    rendered = result
                context += f"\n### {tool_name}:\n{rendered}\n"

        if tools_used:
            prompt = f"""用户问题: {last_message.content}

{context}

请根据以上工具执行结果，用友好的方式回答用户的问题。"""
        else:
            prompt = f"""用户问题: {last_message.content}

请直接回答用户的旅游相关问题。"""

        response = self.llm.invoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])

        answer = response.content
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info("[Answer Node] Answer generated, length=%d", len(answer))
        return {
            "messages": messages,
            "answer": answer,
            "reasoning": self._render_reasoning(state, tools_used),
        }

    def direct_answer_node(self, state: AgentState) -> AgentState:
        logger.info("[Direct Answer Node] Generating direct answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")

        response = self.llm.invoke([
            SystemMessage(content=self.system_prompt),
            last_message,
        ])

        answer = response.content
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info("[Direct Answer Node] Answer generated, length=%d", len(answer))
        return {
            "messages": messages,
            "answer": answer,
            "reasoning": "直接回答（无需工具）",
        }

    @staticmethod
    def _default_plan(intent: str, entities: dict) -> list[dict]:
        if intent == "recommend":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "search_cities",
                    "params": {"query": entities.get("query", "")},
                    "description": "根据用户偏好检索候选城市",
                    "depends_on": [],
                }
            ]
        if intent == "attractions":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "query_attractions",
                    "params": {
                        "city": entities.get("city", ""),
                        "category": entities.get("category"),
                    },
                    "description": "查询目标城市核心景点",
                    "depends_on": [],
                }
            ]
        if intent == "itinerary":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "query_attractions",
                    "params": {"city": entities.get("city", "")},
                    "description": "查询景点池",
                    "depends_on": [],
                },
                {
                    "step": 2,
                    "step_id": "s2",
                    "tool": "get_weather",
                    "params": {"city": entities.get("city", ""), "days": entities.get("days", 3)},
                    "description": "查询天气窗口",
                    "depends_on": [],
                },
                {
                    "step": 3,
                    "step_id": "s3",
                    "tool": "plan_itinerary",
                    "params": {
                        "destination": entities.get("city", ""),
                        "days": entities.get("days", 3),
                        "interests": entities.get("interests"),
                    },
                    "description": "生成按天行程建议",
                    "depends_on": ["s1", "s2"],
                },
            ]
        if intent == "budget":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "calculate_budget",
                    "params": {
                        "destination": entities.get("destination", ""),
                        "days": entities.get("days", 3),
                        "people": entities.get("people", 1),
                        "accommodation_level": entities.get("level", "medium"),
                    },
                    "description": "估算总预算",
                    "depends_on": [],
                }
            ]
        if intent == "tips":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "get_travel_tips",
                    "params": {
                        "destination": entities.get("destination", ""),
                        "season": entities.get("season"),
                    },
                    "description": "获取出行提醒",
                    "depends_on": [],
                }
            ]
        return []

    @staticmethod
    async def _invoke_tool(tool: Tool, params: dict) -> Any:
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(params)
        return await asyncio.to_thread(tool.invoke, params)

    async def _run_tool_with_retry(
        self,
        tool: Tool,
        tool_name: str,
        params: dict,
        timeout_seconds: int,
        max_retries: int,
    ) -> ExecutionResult:
        attempts = max(1, max_retries + 1)
        last_error: Optional[Exception] = None
        start_ts = datetime.now().isoformat()

        if self._is_tool_circuit_open(tool_name):
            now = datetime.now().isoformat()
            return ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                attempt=0,
                error_code="CIRCUIT_OPEN",
                error=f"Circuit breaker open for tool: {tool_name}",
                started_at=start_ts,
                ended_at=now,
            )

        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(self._invoke_tool(tool, params), timeout=timeout_seconds)
                return ExecutionResult(
                    success=True,
                    tool_name=tool_name,
                    result=result,
                    attempt=attempt,
                    started_at=start_ts,
                    ended_at=datetime.now().isoformat(),
                )
            except TimeoutError as exc:
                last_error = exc
                logger.warning("[Execute Node] Tool %s timeout on attempt=%d", tool_name, attempt)
            except Exception as exc:
                last_error = exc
                logger.warning("[Execute Node] Tool %s error on attempt=%d: %s", tool_name, attempt, exc)
            if attempt < attempts:
                await asyncio.sleep(min(1.5, 0.2 * (2 ** (attempt - 1))))

        error_code = "TOOL_TIMEOUT" if isinstance(last_error, TimeoutError) else "TOOL_EXECUTION_ERROR"
        return ExecutionResult(
            success=False,
            tool_name=tool_name,
            result="",
            attempt=attempts,
            error_code=error_code,
            error=str(last_error) if last_error else "Unknown tool execution error",
            started_at=start_ts,
            ended_at=datetime.now().isoformat(),
        )

    async def _execute_plan_step(self, step: dict[str, Any]) -> tuple[dict[str, Any], ExecutionResult, int]:
        step_id = step.get("step_id", f"step-{step.get('step', 0)}")
        tool_name = str(step.get("tool", ""))
        params = step.get("params", {}) or {}
        timeout_seconds = self._resolve_timeout_seconds(step, tool_name)
        max_retries = int(step.get("max_retries", DEFAULT_TOOL_MAX_RETRIES))
        started = time.perf_counter()

        logger.info("[Execute Node] Step %s running tool=%s timeout=%ss", step_id, tool_name, timeout_seconds)
        tool = self.tool_map.get(tool_name)
        if tool is None:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                error_code="TOOL_NOT_FOUND",
                error=f"Tool not found: {tool_name}",
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
            return step, result, int((time.perf_counter() - started) * 1000)

        try:
            result = await self._run_tool_with_retry(
                tool=tool,
                tool_name=tool_name,
                params=params,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            )
        except Exception as exc:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                error_code="UNEXPECTED_ERROR",
                error=str(exc),
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )

        return step, result, int((time.perf_counter() - started) * 1000)

    def _resolve_timeout_seconds(self, step: dict[str, Any], tool_name: str) -> int:
        override = step.get("timeout_seconds")
        if override is not None:
            return max(1, int(override))
        return self._tool_timeout_sla.get(tool_name, DEFAULT_TOOL_TIMEOUT_SECONDS)

    def _is_tool_circuit_open(self, tool_name: str) -> bool:
        item = self._tool_health.get(tool_name)
        if not item:
            return False
        open_until = float(item.get("open_until", 0))
        return time.time() < open_until

    def _mark_tool_failure(self, tool_name: str) -> None:
        now = time.time()
        health = self._tool_health.setdefault(tool_name, {"consecutive_failures": 0, "open_until": 0})
        health["consecutive_failures"] = int(health.get("consecutive_failures", 0)) + 1
        if health["consecutive_failures"] >= DEFAULT_CIRCUIT_BREAKER_THRESHOLD:
            health["open_until"] = now + DEFAULT_TOOL_COOLDOWN_SECONDS

    def _mark_tool_success(self, tool_name: str) -> None:
        self._tool_health[tool_name] = {"consecutive_failures": 0, "open_until": 0}

    @staticmethod
    def _normalize_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for idx, raw in enumerate(plan, start=1):
            step_id = raw.get("step_id") or f"s{idx}"
            depends_on = list(raw.get("depends_on", []))
            normalized.append(
                {
                    "step": int(raw.get("step", idx)),
                    "step_id": str(step_id),
                    "tool": raw.get("tool", ""),
                    "params": raw.get("params", {}),
                    "depends_on": depends_on,
                    "description": raw.get("description", ""),
                    "timeout_seconds": raw.get("timeout_seconds"),
                    "max_retries": raw.get("max_retries", DEFAULT_TOOL_MAX_RETRIES),
                }
            )
        return normalized

    @staticmethod
    def _build_plan_explanation(intent: str, plan: list[dict[str, Any]]) -> str:
        if not plan:
            return f"intent={intent}, no tool plan required"
        steps = [f"{item['step_id']}:{item['tool']}" for item in plan]
        return f"intent={intent}, plan_steps={len(plan)}, chain={' -> '.join(steps)}"

    @staticmethod
    def _render_reasoning(state: AgentState, tools_used: list[str]) -> str:
        plan_id = state.get("plan_id")
        stats = state.get("execution_stats", {}) or {}
        step_count = len(stats.get("steps", []))
        if tools_used:
            tool_str = ", ".join(tools_used)
            if plan_id:
                return f"计划 {plan_id} 执行 {step_count} 步，使用工具: {tool_str}"
            return f"使用工具: {tool_str}"
        return "直接回答"


def create_nodes(llm: Runnable, tools: list[Tool]) -> AgentNodes:
    return AgentNodes(llm, tools)
