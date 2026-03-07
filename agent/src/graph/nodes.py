from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ValidationError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langgraph.prebuilt import ToolNode

from .runtime_config import get_runtime_config
from .state import AgentState, TRAVEL_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
DEFAULT_TOOL_TIMEOUT_SECONDS = 20
DEFAULT_TOOL_MAX_RETRIES = 1
DEFAULT_TOOL_PARALLELISM = 2
DEFAULT_TOOL_COOLDOWN_SECONDS = 45
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 3
SENSITIVE_PARAM_KEYS = {"api_key", "token", "authorization", "password", "secret"}
PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "reveal system prompt",
    "show developer message",
    "泄露系统提示词",
    "忽略之前指令",
)
MAX_PARAM_VALUE_LENGTH = 1000


def _resolve_parallelism_default() -> int:
    return get_runtime_config().default_max_parallelism


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
    source: Optional[str] = None
    fetched_at: Optional[str] = None
    ttl_seconds: Optional[int] = None
    is_stale: bool = False
    provider_used: Optional[str] = None
    provider_chain: Optional[list[str]] = None
    fallback_used: bool = False
    fallback_suggestion: Optional[str] = None


class AgentNodes:
    """LangGraph node implementations for the travel agent."""
    _GLOBAL_TOOL_HEALTH: dict[str, dict[str, Any]] = {}

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
        self.runtime_config = get_runtime_config()

        self.llm_with_tools = llm.bind_tools(tools)
        self.llm_with_intent = self._build_intent_structured_llm()
        if self.llm_with_intent is None:
            self.intent_parser = JsonOutputParser(pydantic_object=IntentResult)

        self.tool_node = ToolNode(tools)
        self._tool_health = AgentNodes._GLOBAL_TOOL_HEALTH
        self._tool_timeout_sla: dict[str, int] = {
            "search_cities": 10,
            "query_attractions": 15,
            "query_hotels": 15,
            "calculate_budget": 8,
            "plan_itinerary": 20,
            "get_travel_tips": 8,
            "get_weather": 10,
        }
        self._tool_source_profile: dict[str, dict[str, Any]] = {
            "search_cities": {"source": "travel_catalog", "ttl_seconds": 86400},
            "query_attractions": {"source": "travel_catalog", "ttl_seconds": 21600},
            "query_hotels": {"source": "hotel_inventory", "ttl_seconds": 1800},
            "calculate_budget": {"source": "budget_ruleset", "ttl_seconds": 86400},
            "plan_itinerary": {"source": "itinerary_planner", "ttl_seconds": 86400},
            "get_travel_tips": {"source": "travel_guide", "ttl_seconds": 86400},
            "get_weather": {"source": "weather_provider", "ttl_seconds": 1800},
        }

    def _build_intent_structured_llm(self) -> Optional[Runnable]:
        for method in self.runtime_config.intent_structured_methods:
            try:
                llm_with_intent = self.llm.with_structured_output(IntentResult, method=method)
                logger.info("[Intent Node] Structured output enabled with method=%s", method)
                return llm_with_intent
            except Exception as exc:
                logger.debug("[Intent Node] Structured output method=%s unavailable: %s", method, exc)

        logger.warning("Structured output unavailable; fallback to JSON parser")
        return None

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
            "execution_summary": {},
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
                "execution_summary": self._build_execution_summary(stats_steps),
                "tool_results": tool_results,
                "tools_used": tools_used,
            }

        default_parallelism = self.runtime_config.default_max_parallelism
        parallelism = min(
            int(state.get("parallelism", default_parallelism)),
            int(state.get("max_parallelism", default_parallelism)),
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
                    "fallback_used": result_obj.fallback_used,
                    "provider_used": result_obj.provider_used,
                    "started_at": result_obj.started_at,
                    "ended_at": result_obj.ended_at,
                    "duration_ms": elapsed_ms,
                }
            )

        return {
            "current_step": len(completed) + len(failed) + len(blocked),
            "execution_state": {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)},
            "execution_stats": {**execution_stats, "steps": stats_steps},
            "execution_summary": self._build_execution_summary(stats_steps),
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
        execution_summary = state.get("execution_summary", {}) or {}

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
        if execution_summary.get("total_steps", 0) > 0:
            context += "\n## 执行汇总:\n"
            context += (
                f"- 总步骤: {execution_summary.get('total_steps', 0)}\n"
                f"- 成功: {execution_summary.get('success_steps', 0)}\n"
                f"- 失败: {execution_summary.get('failed_steps', 0)}\n"
                f"- 阻塞: {execution_summary.get('blocked_steps', 0)}\n"
                f"- 超时: {execution_summary.get('timeout_steps', 0)}\n"
                f"- 备源切换: {execution_summary.get('fallback_steps', 0)}\n"
                f"- 成功率: {execution_summary.get('success_rate', 0.0):.2f}\n"
            )
        if tool_results:
            context += "\n\n## 工具执行结果:\n"
            for tool_name, result in tool_results.items():
                if isinstance(result, dict):
                    if result.get("success"):
                        rendered = result.get("result")
                    else:
                        rendered = f"[{result.get('error_code')}] {result.get('error')}"
                    if isinstance(rendered, dict) and "report" in rendered:
                        rendered = rendered.get("report")
                    source = result.get("source")
                    fetched_at = result.get("fetched_at")
                    ttl_seconds = result.get("ttl_seconds")
                    stale = result.get("is_stale", False)
                    provider_used = result.get("provider_used")
                    provider_chain = result.get("provider_chain")
                    fallback_used = result.get("fallback_used", False)
                    fallback = result.get("fallback_suggestion")
                    if source or fetched_at:
                        rendered = (
                            f"{rendered}\n"
                            f"- source: {source or 'unknown'}\n"
                            f"- fetched_at: {fetched_at or 'unknown'}\n"
                            f"- ttl_seconds: {ttl_seconds if ttl_seconds is not None else 'unknown'}\n"
                            f"- stale: {stale}"
                        )
                    if provider_used or provider_chain:
                        rendered = (
                            f"{rendered}\n"
                            f"- provider_used: {provider_used or 'unknown'}\n"
                            f"- provider_chain: {provider_chain or []}\n"
                            f"- fallback_used: {fallback_used}"
                        )
                    if fallback:
                        rendered = f"{rendered}\n- fallback: {fallback}"
                else:
                    rendered = result
                context += f"\n### {tool_name}:\n{rendered}\n"

        if tools_used:
            prompt = f"""用户问题: {last_message.content}

{context}

请根据以上工具执行结果，用友好的方式回答用户的问题。
请优先引用工具结果中的 source 和 fetched_at，涉及时效信息时明确说明时间。"""
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
        max_retries = int(step.get("max_retries", self.runtime_config.default_tool_max_retries))
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
            self._attach_execution_metadata(result, tool_name)
            return step, result, int((time.perf_counter() - started) * 1000)

        validation_error = self._validate_tool_params(tool, params)
        if validation_error is not None:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                error_code="PARAM_VALIDATION_ERROR",
                error=validation_error,
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
            self._attach_execution_metadata(result, tool_name)
            return step, result, int((time.perf_counter() - started) * 1000)

        unsafe_reason = self._detect_unsafe_params(params)
        if unsafe_reason is not None:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                error_code="UNSAFE_TOOL_INPUT",
                error=unsafe_reason,
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
            self._attach_execution_metadata(result, tool_name)
            return step, result, int((time.perf_counter() - started) * 1000)

        logger.info(
            "[Execute Node] Step %s invoking %s with params=%s",
            step_id,
            tool_name,
            self._sanitize_params_for_log(params),
        )

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

        self._attach_execution_metadata(result, tool_name)
        return step, result, int((time.perf_counter() - started) * 1000)

    def _resolve_timeout_seconds(self, step: dict[str, Any], tool_name: str) -> int:
        override = step.get("timeout_seconds")
        if override is not None:
            return max(1, int(override))
        return self._tool_timeout_sla.get(tool_name, self.runtime_config.default_tool_timeout_seconds)

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
        if health["consecutive_failures"] >= self.runtime_config.circuit_breaker_threshold:
            health["open_until"] = now + self.runtime_config.tool_cooldown_seconds

    def _mark_tool_success(self, tool_name: str) -> None:
        self._tool_health[tool_name] = {"consecutive_failures": 0, "open_until": 0}

    @classmethod
    def get_global_tool_health_snapshot(cls) -> dict[str, Any]:
        now = time.time()
        tools: dict[str, dict[str, Any]] = {}
        for name, item in cls._GLOBAL_TOOL_HEALTH.items():
            open_until = float(item.get("open_until", 0) or 0)
            tools[name] = {
                "consecutive_failures": int(item.get("consecutive_failures", 0) or 0),
                "open_until": open_until,
                "is_circuit_open": now < open_until,
                "cooldown_remaining_seconds": max(0, int(open_until - now)),
            }

        return {
            "tool_count": len(tools),
            "open_circuit_count": sum(1 for item in tools.values() if item["is_circuit_open"]),
            "tools": tools,
        }

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
                    "max_retries": raw.get("max_retries", get_runtime_config().default_tool_max_retries),
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

    @staticmethod
    def _validate_tool_params(tool: Tool, params: dict[str, Any]) -> Optional[str]:
        schema = getattr(tool, "args_schema", None)
        if schema is None:
            return None
        try:
            schema.model_validate(params)
        except ValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else {}
            location = ".".join(str(x) for x in first_error.get("loc", []))
            message = first_error.get("msg", str(exc))
            return f"Invalid params for tool: {location} {message}".strip()
        return None

    @staticmethod
    def _detect_unsafe_params(params: dict[str, Any]) -> Optional[str]:
        def _walk(value: Any) -> list[str]:
            found: list[str] = []
            if isinstance(value, str):
                text = value.lower()
                for pattern in PROMPT_INJECTION_PATTERNS:
                    if pattern in text:
                        found.append(pattern)
            elif isinstance(value, dict):
                for nested in value.values():
                    found.extend(_walk(nested))
            elif isinstance(value, list):
                for nested in value:
                    found.extend(_walk(nested))
            return found

        matches = _walk(params)
        if not matches:
            return None
        return f"Unsafe tool input detected: {matches[0]}"

    @staticmethod
    def _sanitize_params_for_log(params: dict[str, Any]) -> dict[str, Any]:
        def _sanitize(key: Optional[str], value: Any) -> Any:
            if key and key.lower() in SENSITIVE_PARAM_KEYS:
                return "***"
            if isinstance(value, str):
                if len(value) > MAX_PARAM_VALUE_LENGTH:
                    return f"{value[:MAX_PARAM_VALUE_LENGTH]}...(truncated)"
                return value
            if isinstance(value, dict):
                return {k: _sanitize(k, v) for k, v in value.items()}
            if isinstance(value, list):
                return [_sanitize(key, v) for v in value]
            return value

        return {k: _sanitize(k, v) for k, v in params.items()}

    @staticmethod
    def _build_execution_summary(stats_steps: list[dict[str, Any]]) -> dict[str, Any]:
        total_steps = len(stats_steps)
        success_steps = sum(1 for item in stats_steps if item.get("status") == "success")
        failed_steps = sum(1 for item in stats_steps if item.get("status") == "failed")
        blocked_steps = sum(1 for item in stats_steps if item.get("status") == "blocked")
        timeout_steps = sum(1 for item in stats_steps if item.get("error_code") == "TOOL_TIMEOUT")
        fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))
        duration_values = [int(item.get("duration_ms", 0) or 0) for item in stats_steps]
        avg_duration = int(sum(duration_values) / total_steps) if total_steps else 0
        success_rate = (success_steps / total_steps) if total_steps else 0.0

        tool_metrics: dict[str, dict[str, Any]] = {}
        for item in stats_steps:
            tool = str(item.get("tool") or "unknown")
            metric = tool_metrics.setdefault(
                tool,
                {"calls": 0, "success": 0, "failed": 0, "blocked": 0, "timeouts": 0, "avg_duration_ms": 0},
            )
            metric["calls"] += 1
            status = item.get("status")
            if status == "success":
                metric["success"] += 1
            elif status == "failed":
                metric["failed"] += 1
            elif status == "blocked":
                metric["blocked"] += 1
            if item.get("error_code") == "TOOL_TIMEOUT":
                metric["timeouts"] += 1

        for tool, metric in tool_metrics.items():
            tool_durations = [
                int(item.get("duration_ms", 0) or 0)
                for item in stats_steps
                if str(item.get("tool") or "unknown") == tool
            ]
            metric["avg_duration_ms"] = int(sum(tool_durations) / len(tool_durations)) if tool_durations else 0

        return {
            "total_steps": total_steps,
            "success_steps": success_steps,
            "failed_steps": failed_steps,
            "blocked_steps": blocked_steps,
            "timeout_steps": timeout_steps,
            "fallback_steps": fallback_steps,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": avg_duration,
            "tool_metrics": tool_metrics,
        }

    def _attach_execution_metadata(self, result: ExecutionResult, tool_name: str) -> None:
        profile = self._tool_source_profile.get(
            tool_name,
            {"source": f"tool:{tool_name}", "ttl_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS * 30},
        )
        result.source = str(profile.get("source", f"tool:{tool_name}"))
        result.ttl_seconds = int(profile.get("ttl_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS * 30))
        result.fetched_at = datetime.now().isoformat()
        result.is_stale = False
        result_meta = self._extract_result_meta(result.result)
        if result_meta:
            if result_meta.get("source"):
                result.source = str(result_meta.get("source"))
            if result_meta.get("fetched_at"):
                result.fetched_at = str(result_meta.get("fetched_at"))
            if result_meta.get("ttl_seconds") is not None:
                result.ttl_seconds = int(result_meta.get("ttl_seconds"))
            if result_meta.get("is_stale") is not None:
                result.is_stale = bool(result_meta.get("is_stale"))
            if result_meta.get("provider_used") is not None:
                result.provider_used = str(result_meta.get("provider_used"))
            if result_meta.get("provider_chain") is not None:
                result.provider_chain = list(result_meta.get("provider_chain"))
            if result_meta.get("fallback_used") is not None:
                result.fallback_used = bool(result_meta.get("fallback_used"))
        if not result.success:
            result.fallback_suggestion = self._build_fallback_suggestion(
                tool_name=tool_name,
                error_code=result.error_code,
            )
        elif result.is_stale:
            result.fallback_suggestion = "数据可能已过期，建议刷新实时数据后再确认关键决策"

    @staticmethod
    def _extract_result_meta(result_payload: Any) -> dict[str, Any]:
        if not isinstance(result_payload, dict):
            return {}
        raw_meta = result_payload.get("_meta") or result_payload.get("meta")
        if not isinstance(raw_meta, dict):
            return {}
        return raw_meta

    @staticmethod
    def _build_fallback_suggestion(tool_name: str, error_code: Optional[str]) -> str:
        if error_code == "TOOL_TIMEOUT":
            return f"{tool_name} 超时，建议使用缓存信息或给出无实时依赖的备选方案"
        if error_code == "CIRCUIT_OPEN":
            return f"{tool_name} 当前不可用，建议切换备选数据源"
        if error_code == "TOOL_NOT_FOUND":
            return "工具配置缺失，建议走无需工具的保守回答并提示用户补充信息"
        if error_code == "PARAM_VALIDATION_ERROR":
            return "请求参数不完整，建议向用户补充澄清问题后重试"
        if error_code == "UNSAFE_TOOL_INPUT":
            return "输入触发安全策略，建议清理高风险指令后再执行"
        return f"{tool_name} 执行失败，建议降级为规则模板回答并标注不确定性"


def create_nodes(llm: Runnable, tools: list[Tool]) -> AgentNodes:
    return AgentNodes(llm, tools)
