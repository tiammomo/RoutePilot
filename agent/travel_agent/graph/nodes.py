"""Core graph nodes implementing intent, planning, tooling, and answer stages."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, ValidationError
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable
from langchain_core.tools import Tool
from langgraph.prebuilt import ToolNode

from .prompt_templates import build_answer_prompt, build_direct_prompt, build_system_prompt
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
MAX_SAME_TOOL_INVOCATIONS = 2
DEFAULT_DAY_COUNT = 3
DEFAULT_PEOPLE_COUNT = 1
DEFAULT_BUDGET_CNY = 3000
HIGH_RISK_KEYWORDS = (
    "价格",
    "票价",
    "预算",
    "费用",
    "政策",
    "签证",
    "退改",
    "机票",
    "酒店价格",
)
STALE_REFRESHABLE_TOOLS = {"get_weather", "query_hotels"}
INTENT_TOOL_POLICY: dict[str, dict[str, Any]] = {
    "recommend": {"required": ["search_cities"], "optional": ["get_weather", "query_hotels"], "verify_required": False},
    "attractions": {"required": ["query_attractions"], "optional": ["get_weather"], "verify_required": False},
    "itinerary": {"required": ["plan_itinerary"], "optional": ["query_attractions", "get_weather", "query_hotels"], "verify_required": False},
    "budget": {"required": ["calculate_budget"], "optional": ["query_hotels", "get_weather"], "verify_required": True},
    "tips": {"required": ["get_travel_tips"], "optional": ["get_weather"], "verify_required": False},
    "hotel": {"required": ["query_hotels"], "optional": ["get_weather"], "verify_required": True},
    "policy": {"required": [], "optional": ["get_travel_tips"], "verify_required": True},
    "general": {"required": [], "optional": ["search_cities"], "verify_required": False},
}
CITY_HINTS = [
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "苏州",
    "成都",
    "重庆",
    "西安",
    "武汉",
    "长沙",
    "厦门",
    "青岛",
    "大连",
    "三亚",
    "昆明",
    "丽江",
    "大理",
    "拉萨",
    "哈尔滨",
]
EN_CITY_HINTS = [
    "Beijing",
    "Shanghai",
    "Guangzhou",
    "Shenzhen",
    "Hangzhou",
    "Nanjing",
    "Suzhou",
    "Chengdu",
    "Chongqing",
    "Xi'an",
    "Wuhan",
    "Changsha",
    "Xiamen",
    "Qingdao",
    "Dalian",
    "Sanya",
    "Kunming",
    "Lijiang",
    "Dali",
    "Lhasa",
    "Harbin",
]


def _resolve_parallelism_default() -> int:
    """Resolve default tool parallelism from runtime config and fallback constants.
    
    Purpose:
        Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
    
    Returns:
        int: Result value produced by this routine.
    """
    return get_runtime_config().default_max_parallelism


class IntentResult(BaseModel):
    """Intent classifier output used to route downstream graph stages."""

    intent: str
    confidence: float
    entities: dict
    requires_tools: bool


class PlanStep(BaseModel):
    """Single executable step produced by the planner stage."""

    step: int
    tool: str
    params: dict
    description: str


class ExecutionResult(BaseModel):
    """Normalized result envelope for one tool execution attempt."""

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
    refresh_attempted: bool = False
    refresh_success: bool = False
    fallback_suggestion: Optional[str] = None


class ToolOrchestratorDecision(BaseModel):
    """Selection decision describing runnable and skipped tool steps."""

    selected: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    budget_stop_reason: Optional[str] = None


class ToolOrchestrator:
    """Central scheduler for tool execution constraints and degradation policies."""

    def __init__(self, runtime_config):
        """Initialize tool scheduling constraints used by plan execution.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            runtime_config: Input `runtime_config` consumed by this routine.
        
        Returns:
            Any: Result value produced by this routine.
        """
        self.runtime_config = runtime_config

    def select(
        self,
        runnable: list[dict[str, Any]],
        trace_counter: Counter,
        signature_getter: Callable[[dict[str, Any]], str],
        max_same_invocations: int,
        requested_parallelism: int,
        max_parallelism: int,
        budget: dict[str, Any],
    ) -> ToolOrchestratorDecision:
        """Select runnable tool steps under loop, budget, and parallelism constraints.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            runnable: Candidate runnable steps considered by scheduler.
            trace_counter: Signature counter used to detect repeated loop patterns.
            signature_getter: Callback that builds a stable signature for one plan step.
            max_same_invocations: Input `max_same_invocations` consumed by this routine.
            requested_parallelism: Input `requested_parallelism` consumed by this routine.
            max_parallelism: Input `max_parallelism` consumed by this routine.
            budget: Scheduler budget snapshot used for selection guards.
        
        Returns:
            ToolOrchestratorDecision: Result value produced by this routine.
        """
        selected: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        tool_used = int(budget.get("tools_used", 0) or 0)
        max_tools = int(budget.get("max_tools", self.runtime_config.round_max_tools) or self.runtime_config.round_max_tools)

        parallel_cap = max(1, min(requested_parallelism, max_parallelism, len(runnable)))
        for step in runnable:
            signature = signature_getter(step)
            if signature in seen_signatures:
                skipped.append({**step, "_skip_code": "LOOP_DETECTED", "_skip_reason": f"duplicated signature in round: {signature}"})
                continue
            if trace_counter.get(signature, 0) >= max_same_invocations:
                skipped.append({**step, "_skip_code": "LOOP_DETECTED", "_skip_reason": f"repeated signature exceeded limit: {signature}"})
                continue
            if tool_used >= max_tools:
                skipped.append({**step, "_skip_code": "ROUND_TOOL_BUDGET_EXCEEDED", "_skip_reason": f"max tools reached: {max_tools}"})
                continue
            seen_signatures.add(signature)
            selected.append(step)
            tool_used += 1
            if len(selected) >= parallel_cap:
                break

        budget_stop_reason = None
        if not selected and any(item.get("_skip_code") == "ROUND_TOOL_BUDGET_EXCEEDED" for item in skipped):
            budget_stop_reason = f"本轮工具预算已达上限({max_tools})，将执行降级策略。"
        return ToolOrchestratorDecision(selected=selected, skipped=skipped, budget_stop_reason=budget_stop_reason)

class StrategyResult(BaseModel):
    """Strategy planning output describing tool policy and routing mode."""

    strategy: str
    primary_intent: str = "general"
    secondary_intent: Optional[str] = None
    required_tools: list[str] = []
    optional_tools: list[str] = []
    requires_verification: bool = False
    routing: Literal["plan", "react", "direct"] = "direct"
    reason: str = ""


class VerifyIssue(BaseModel):
    """One verification issue discovered in answer/tool cross-checking."""

    issue_type: str
    message: str
    severity: Literal["low", "medium", "high"] = "medium"


class VerifyResult(BaseModel):
    """Verification summary used to decide retry vs final response."""

    passed: bool
    should_retry: bool = False
    refresh_targets: list[str] = []
    refresh_tools: list[str] = []
    issues: list[VerifyIssue] = []
    summary: str = ""


class SelfCheckResult(BaseModel):
    """Final answer completeness check result before returning to user."""

    passed: bool
    missing_items: list[str] = []
    summary: str = ""


class IntentStageOutput(BaseModel):
    """State patch produced by the intent stage."""

    intent: str
    intent_detail: dict[str, Any]


class StrategyStageOutput(BaseModel):
    """State patch produced by the strategy stage."""

    strategy: str
    strategy_detail: dict[str, Any]
    routing: Literal["plan", "react", "direct"]


class PlanStageOutput(BaseModel):
    """State patch produced by planning/execution stage."""

    plan_id: str
    plan_explanation: str
    plan: list[dict[str, Any]]
    validation_status: Literal["pass", "warn", "fail"] = "pass"
    validation_errors: list[dict[str, Any]] = []
    current_step: int
    execution_round: int
    execution_state: dict[str, Any]
    execution_stats: dict[str, Any]
    execution_summary: dict[str, Any]
    execution_trace: list[dict[str, Any]]
    execution_budget: dict[str, Any]
    fused_tool_results: Optional[dict[str, Any]] = None
    early_stop_reason: Optional[str] = None
    verify_retry_count: int = 0
    verify_result: Optional[dict[str, Any]] = None
    tools_used: list[str]
    tool_results: dict[str, Any]


class AnswerStageOutput(BaseModel):
    """State patch produced by answer synthesis stage."""

    messages: list[Any]
    answer: str
    reasoning: str
    fused_tool_results: Optional[dict[str, Any]] = None


class VerifyStageOutput(BaseModel):
    """State patch produced by verification stage."""

    verify_result: dict[str, Any]
    verify_retry_count: int
    early_stop_reason: Optional[str] = None


class SelfCheckStageOutput(BaseModel):
    """State patch produced by final self-check stage."""

    answer: str
    self_check_result: dict[str, Any]


class AgentNodes:
    """LangGraph node implementations for the travel agent."""
    _GLOBAL_TOOL_HEALTH: dict[str, dict[str, Any]] = {}

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        system_prompt: str | None = None,
        planner_hooks: Optional[dict[str, Callable[[dict], list[dict]]]] = None,
        routing_llm: Optional[Runnable] = None,
    ):
        """Initialize node runtime dependencies, model bindings, tool registry, and health trackers.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            llm: Input `llm` consumed by this routine.
            tools: Input `tools` consumed by this routine.
            system_prompt: Input `system_prompt` consumed by this routine.
            planner_hooks: Input `planner_hooks` consumed by this routine.
            routing_llm: Input `routing_llm` consumed by this routine.
        
        Returns:
            Any: Result value produced by this routine.
        """
        self.llm = llm
        self.routing_llm = routing_llm or llm
        self.tools = tools
        self.system_prompt = system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
        self.tool_map = {tool.name: tool for tool in tools}
        self._planner_hooks = planner_hooks or {}
        self.runtime_config = get_runtime_config()
        self._max_same_tool_invocations = MAX_SAME_TOOL_INVOCATIONS
        self.orchestrator = ToolOrchestrator(self.runtime_config)

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
        """Build a structured-output intent model chain and gracefully fall back when unsupported.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Returns:
            Optional[Runnable]: Result value produced by this routine.
        """
        if self._should_disable_structured_intent():
            logger.info("[Intent Node] Structured output disabled for current routing model")
            return None
        for method in self.runtime_config.intent_structured_methods:
            try:
                llm_with_intent = self.routing_llm.with_structured_output(IntentResult, method=method)
                logger.info("[Intent Node] Structured output enabled with method=%s", method)
                return llm_with_intent
            except Exception as exc:
                logger.debug("[Intent Node] Structured output method=%s unavailable: %s", method, exc)

        logger.warning("Structured output unavailable; fallback to JSON parser")
        return None

    def _should_disable_structured_intent(self) -> bool:
        """Return whether structured intent parsing should be disabled for the current model family.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Returns:
            bool: Decision flag used by guards, routing, or policy checks.
        """
        model_markers: list[str] = []
        for attr in ("model", "model_name", "name"):
            value = getattr(self.routing_llm, attr, None)
            if value:
                model_markers.append(str(value).lower())

        model_dump = " ".join(model_markers)
        if "minimax" in model_dump:
            return True
        return False

    @staticmethod
    def _validate_stage_output(model: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
        """Validate stage output payload against the expected schema model.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            model: Input `model` consumed by this routine.
            payload: Input `payload` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        validated = model.model_validate(payload)
        return validated.model_dump()

    @staticmethod
    def _coerce_llm_content_to_text(content: Any) -> str:
        """Normalize heterogeneous model output payloads into plain text.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            content: Raw text content being normalized or analyzed.
        
        Returns:
            str: Result value produced by this routine.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
                        continue
                    nested = item.get("content")
                    if isinstance(nested, str) and nested.strip():
                        parts.append(nested)
            merged = "".join(parts).strip()
            if merged:
                return merged
        return str(content or "").strip()

    def intent_node(self, state: AgentState) -> AgentState:
        """Run intent classification, parse entities, and write normalized intent fields into state.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        logger.info("[Intent Node] Analyzing user intent...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")

        intent_prompt = f"""请分析下面用户旅游咨询的意图。

用户消息: {last_message.content}

可选意图:
- recommend: 需要目的地推荐
- attractions: 查询景点信息
- itinerary: 需要行程规划
- budget: 需要预算估算
- tips: 需要旅行建议
- general: 一般旅游问答
- unclear: 意图不明确

请仅返回 JSON（不要输出多余文本）:
{{
  "intent": "recommend|attractions|itinerary|budget|tips|general|unclear",
  "confidence": 0.0,
  "entities": {{}},
  "requires_tools": false
}}"""

        try:
            intent = "general"
            intent_detail = {
                "confidence": 0.5,
                "entities": {},
                "requires_tools": False,
            }

            structured_failed = False
            if self.llm_with_intent:
                try:
                    result = self.llm_with_intent.invoke([SystemMessage(content=intent_prompt)])
                    intent = result.intent
                    intent_detail = {
                        "confidence": result.confidence,
                        "entities": result.entities,
                        "requires_tools": result.requires_tools,
                    }
                except Exception as exc:
                    structured_failed = True
                    logger.warning("[Intent Node] Structured parse failed, fallback to prompt JSON: %s", exc)

            if structured_failed or not self.llm_with_intent:
                response = self.routing_llm.invoke([SystemMessage(content=intent_prompt)])
                parsed = self._parse_intent_response_fallback(response, str(last_message.content or ""))
                intent = parsed.get("intent", "general")
                intent_detail = {
                    "confidence": parsed.get("confidence", 0.5),
                    "entities": parsed.get("entities", {}),
                    "requires_tools": parsed.get("requires_tools", False),
                }

            logger.info("[Intent Node] Detected intent=%s", intent)
            return self._validate_stage_output(
                IntentStageOutput,
                {"intent": intent, "intent_detail": intent_detail},
            )
        except Exception as exc:
            logger.warning("[Intent Node] Failed to parse intent: %s", exc)
            return self._validate_stage_output(
                IntentStageOutput,
                {
                    "intent": "general",
                    "intent_detail": {
                        "confidence": 0.5,
                        "entities": {},
                        "requires_tools": False,
                    },
                },
            )

    def _parse_intent_response_fallback(self, response: Any, user_text: str) -> dict[str, Any]:
        """Parse intent JSON fallback output when structured parsing is unavailable.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            response: Input `response` consumed by this routine.
            user_text: Input `user_text` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        try:
            return self.intent_parser.invoke(response)
        except Exception as parser_exc:
            logger.warning("[Intent Node] JSON parser fallback failed: %s", parser_exc)
            raw_text = self._coerce_llm_content_to_text(getattr(response, "content", response))
            extracted = self._extract_first_json_object(raw_text)
            if extracted:
                try:
                    parsed = json.loads(extracted)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass

        return self._infer_intent_by_keywords(user_text)

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        """Extract the first JSON object substring from mixed natural-language model output.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            text: Input `text` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        if not text:
            return ""
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return ""
        return text[start : end + 1]

    @staticmethod
    def _infer_intent_by_keywords(user_text: str) -> dict[str, Any]:
        """Infer intent using keyword heuristics when model output is invalid or missing.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            user_text: Input `user_text` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        text = (user_text or "").lower()
        intent = "general"
        requires_tools = False
        confidence = 0.55

        if any(key in text for key in ["预算", "费用", "花费", "价格", "票价"]):
            intent = "budget"
            requires_tools = True
            confidence = 0.8
        elif any(key in text for key in ["行程", "路线", "几天", "安排", "攻略"]):
            intent = "itinerary"
            requires_tools = True
            confidence = 0.8
        elif any(key in text for key in ["景点", "打卡", "必去", "门票"]):
            intent = "attractions"
            requires_tools = True
            confidence = 0.75
        elif any(key in text for key in ["推荐", "去哪", "目的地"]):
            intent = "recommend"
            requires_tools = True
            confidence = 0.72
        elif any(key in text for key in ["注意", "提醒", "建议", "避坑"]):
            intent = "tips"
            confidence = 0.65

        return {
            "intent": intent,
            "confidence": confidence,
            "entities": {},
            "requires_tools": requires_tools,
        }

    def strategy_node(self, state: AgentState) -> AgentState:
        """Decide routing strategy and required tool policy from intent and confidence signals.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        intent = state.get("intent", "general")
        intent_detail = state.get("intent_detail", {})
        requires_tools = bool(intent_detail.get("requires_tools", False))
        confidence = float(intent_detail.get("confidence", 0.0) or 0.0)
        user_text = self._last_user_text(state)
        high_risk = self._is_high_risk_query(user_text, intent)
        primary_intent = str(intent or "general").lower()
        secondary_intent = self._infer_secondary_intent(primary_intent, user_text, intent_detail)
        strategy = primary_intent if not secondary_intent else f"{primary_intent}+{secondary_intent}"
        required_tools, optional_tools = self._resolve_tool_policy(primary_intent, secondary_intent)
        policy_verify_required = self._is_verify_required(primary_intent, secondary_intent)
        reason = "default_strategy"
        if high_risk:
            logger.info("[Strategy Node] Routing to plan due to high-risk query (intent=%s)", intent)
            output = StrategyResult(
                strategy=strategy,
                primary_intent=primary_intent,
                secondary_intent=secondary_intent,
                required_tools=required_tools,
                optional_tools=optional_tools,
                requires_verification=True,
                routing="plan",
                reason="high_risk_requires_tool_verification",
            )
            return self._validate_stage_output(
                StrategyStageOutput,
                {
                    "strategy": output.strategy,
                    "strategy_detail": output.model_dump(),
                    "routing": output.routing,
                },
            )

        if requires_tools or intent in {"recommend", "attractions", "itinerary", "budget", "tips"}:
            reason = "intent_or_requires_tools"
            output = StrategyResult(
                strategy=strategy,
                primary_intent=primary_intent,
                secondary_intent=secondary_intent,
                required_tools=required_tools,
                optional_tools=optional_tools,
                requires_verification=bool(policy_verify_required),
                routing="plan",
                reason=reason,
            )
            logger.info("[Strategy Node] Routing to plan (intent=%s, requires_tools=%s)", intent, requires_tools)
            return self._validate_stage_output(
                StrategyStageOutput,
                {
                    "strategy": output.strategy,
                    "strategy_detail": output.model_dump(),
                    "routing": output.routing,
                },
            )

        if confidence >= self.runtime_config.early_stop_confidence_threshold:
            reason = "high_confidence_direct"

        logger.info("[Strategy Node] Routing to direct (intent=%s)", intent)
        output = StrategyResult(
            strategy=strategy,
            primary_intent=primary_intent,
            secondary_intent=secondary_intent,
            required_tools=required_tools,
            optional_tools=optional_tools,
            requires_verification=False,
            routing="direct",
            reason=reason,
        )
        return self._validate_stage_output(
            StrategyStageOutput,
            {
                "strategy": output.strategy,
                "strategy_detail": output.model_dump(),
                "routing": output.routing,
            },
        )

    def router_node(self, state: AgentState) -> AgentState:
        """Build lightweight routing metadata consumed by conditional graph edges.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        return self.strategy_node(state)

    def routing_decision(self, state: AgentState) -> Literal["plan", "react", "direct"]:
        """Return the strategy routing label used by LangGraph conditional edges.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            str: Conditional-edge label consumed by graph routing.
        """
        routing = state.get("routing", "direct")
        if routing != "plan":
            return "direct"

        chat_mode = str(state.get("chat_mode") or "react").strip().lower()
        if chat_mode == "plan":
            return "plan"
        return "react"

    def plan_node(self, state: AgentState) -> AgentState:
        """Build and validate executable tool plan including policy checks and diagnostics fields.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        logger.info("[Plan Node] Building execution plan...")

        intent = state.get("intent", "general")
        entities = (state.get("intent_detail") or {}).get("entities", {})
        strategy_detail = state.get("strategy_detail", {}) or {}
        primary_intent = str(strategy_detail.get("primary_intent") or intent or "general")
        secondary_intent = strategy_detail.get("secondary_intent")
        required_tools = list(strategy_detail.get("required_tools", []))
        optional_tools = list(strategy_detail.get("optional_tools", []))

        planner_hook = self._planner_hooks.get(primary_intent) or self._planner_hooks.get(intent)
        used_planner_hook = planner_hook is not None
        if planner_hook:
            try:
                plan = planner_hook(entities)
            except Exception as exc:
                logger.warning("[Plan Node] Planner hook failed (intent=%s): %s", intent, exc)
                plan = []
        else:
            plan = self._default_plan(primary_intent, entities)
            if secondary_intent and secondary_intent != primary_intent:
                secondary_plan = self._default_plan(str(secondary_intent), entities)
                plan = self._merge_plans(plan, secondary_plan)

        plan = self._enforce_tool_policy(
            plan=plan,
            required_tools=required_tools,
            optional_tools=[] if used_planner_hook else optional_tools,
            entities=entities,
        )

        normalized_plan = self._normalize_plan(plan)
        if len(normalized_plan) > self.runtime_config.max_plan_steps:
            logger.warning(
                "[Plan Node] Plan truncated from %d to %d by AGENT_MAX_PLAN_STEPS",
                len(normalized_plan),
                self.runtime_config.max_plan_steps,
            )
            normalized_plan = normalized_plan[: self.runtime_config.max_plan_steps]
        validation_status, validation_errors = self._validate_plan_steps(normalized_plan)
        validation_blocked = [str(item.get("step_id")) for item in validation_errors if item.get("code") == "TOOL_NOT_REGISTERED"]
        stats_steps = self._build_plan_validation_stats(normalized_plan, validation_errors)
        tool_results = self._build_plan_validation_tool_results(validation_errors)
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        logger.info("[Plan Node] Plan created with %d steps (plan_id=%s)", len(normalized_plan), plan_id)
        return self._validate_stage_output(
            PlanStageOutput,
            {
                "plan_id": plan_id,
                "plan_explanation": self._build_plan_explanation(intent, normalized_plan),
                "plan": normalized_plan,
                "validation_status": validation_status,
                "validation_errors": validation_errors,
                "current_step": 0,
                "execution_round": 0,
                "execution_state": {"completed": [], "failed": [], "blocked": sorted(validation_blocked)},
                "execution_stats": {"plan_id": plan_id, "started_at": datetime.now().isoformat(), "steps": stats_steps},
                "execution_summary": self._build_execution_summary(stats_steps),
                "execution_trace": [],
                "execution_budget": {
                    "max_tools": self.runtime_config.round_max_tools,
                    "max_elapsed_ms": self.runtime_config.round_max_elapsed_ms,
                    "max_tokens": self.runtime_config.round_max_tokens,
                    "tools_used": 0,
                    "elapsed_ms": 0,
                    "tokens_used": 0,
                },
                "fused_tool_results": None,
                "early_stop_reason": None,
                "verify_retry_count": 0,
                "verify_result": None,
                "tools_used": [],
                "tool_results": tool_results,
            },
        )

    def _validate_plan_steps(self, plan: list[dict[str, Any]]) -> tuple[Literal["pass", "warn", "fail"], list[dict[str, Any]]]:
        """Validate plan steps for schema completeness and tool policy compliance.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            plan: Plan step list prepared by planner stage.
        
        Returns:
            tuple[Literal['pass', 'warn', 'fail'], list[dict[str, Any]]]: Result value produced by this routine.
        """
        errors: list[dict[str, Any]] = []
        for step in plan:
            tool_name = str(step.get("tool") or "").strip()
            if not tool_name or tool_name not in self.tool_map:
                errors.append(
                    {
                        "step_id": str(step.get("step_id") or ""),
                        "tool": tool_name,
                        "code": "TOOL_NOT_REGISTERED",
                        "message": f"Tool not registered: {tool_name or '<empty>'}",
                    }
                )

        if not errors:
            return "pass", []

        invalid_steps = {
            str(item.get("step_id") or "")
            for item in errors
            if item.get("code") == "TOOL_NOT_REGISTERED"
        }
        status: Literal["pass", "warn", "fail"] = "warn"
        if invalid_steps and len(invalid_steps) >= len(plan):
            status = "fail"
        return status, errors

    def _build_plan_validation_stats(
        self,
        plan: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build summary counters describing plan validation findings.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            plan: Plan step list prepared by planner stage.
            errors: Input `errors` consumed by this routine.
        
        Returns:
            list[dict[str, Any]]: Result value produced by this routine.
        """
        error_by_step: dict[str, dict[str, Any]] = {}
        for item in errors:
            step_id = str(item.get("step_id") or "")
            if step_id:
                error_by_step[step_id] = item

        stats_steps: list[dict[str, Any]] = []
        for step in plan:
            step_id = str(step.get("step_id") or "")
            item = error_by_step.get(step_id)
            if not item:
                continue
            stats_steps.append(
                {
                    "step_id": step_id,
                    "tool": step.get("tool"),
                    "depends_on": step.get("depends_on", []),
                    "status": "blocked",
                    "attempt": 0,
                    "error_code": item.get("code"),
                    "fallback_used": False,
                    "provider_used": None,
                    "started_at": datetime.now().isoformat(),
                    "ended_at": datetime.now().isoformat(),
                    "duration_ms": 0,
                    "signature": self._step_signature(str(step.get("tool") or ""), dict(step.get("params", {}) or {})),
                }
            )
        return stats_steps

    def _build_plan_validation_tool_results(self, errors: list[dict[str, Any]]) -> dict[str, Any]:
        """Build synthetic tool results describing plan validation problems.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            errors: Input `errors` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        results: dict[str, Any] = {}
        for item in errors:
            step_id = str(item.get("step_id") or "")
            tool_name = str(item.get("tool") or "")
            code = str(item.get("code") or "PLAN_VALIDATION_ERROR")
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                attempt=0,
                error_code=code,
                error=str(item.get("message") or code),
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
            self._attach_execution_metadata(result, tool_name)
            results[f"{step_id}:{tool_name}"] = result.model_dump()
        return results

    async def execute_node(self, state: AgentState) -> AgentState:
        """Execute planned tools with retry, timeout, budget, and circuit-breaker protections.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
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
        execution_trace = list(state.get("execution_trace", []) or [])
        trace_counter = Counter(item.get("signature") for item in execution_trace if item.get("signature"))
        early_stop_reason = state.get("early_stop_reason")
        execution_round = self._safe_int(state.get("execution_round"), 0)
        execution_budget = dict(state.get("execution_budget") or {})
        execution_budget.setdefault("max_tools", self.runtime_config.round_max_tools)
        execution_budget.setdefault("max_elapsed_ms", self.runtime_config.round_max_elapsed_ms)
        execution_budget.setdefault("max_tokens", self.runtime_config.round_max_tokens)
        execution_budget.setdefault("tools_used", 0)
        execution_budget.setdefault("elapsed_ms", 0)
        execution_budget.setdefault("tokens_used", 0)
        if not self.runtime_config.cost_controls_enabled:
            execution_budget["max_tools"] = max(int(execution_budget.get("max_tools", 0) or 0), max(1, len(plan)) * 4)
            execution_budget["max_elapsed_ms"] = max(int(execution_budget.get("max_elapsed_ms", 0) or 0), 1_000_000_000)
            execution_budget["max_tokens"] = max(int(execution_budget.get("max_tokens", 0) or 0), 1_000_000_000)
        verify_result = state.get("verify_result", {}) or {}
        refresh_targets = self._resolve_refresh_targets(verify_result)
        if not self.runtime_config.timeliness_controls_enabled:
            refresh_targets = []
        refresh_target_set = set(refresh_targets)
        verify_result_update: Optional[dict[str, Any]] = None
        if refresh_target_set:
            logger.info("[Execute Node] Refresh retry requested for steps=%s", sorted(refresh_target_set))
            for sid in refresh_target_set:
                completed.discard(sid)
                failed.discard(sid)
                blocked.discard(sid)
            verify_result_update = {
                **verify_result,
                "should_retry": False,
                "refresh_targets": [],
                "refresh_tools": [],
            }

        def _with_refresh(payload: dict[str, Any]) -> dict[str, Any]:
            """Refresh stale tool result payloads using fallback params and annotate refresh metadata.
            
            Purpose:
                Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
            
            Args:
                payload: Input `payload` consumed by this routine.
            
            Returns:
                dict[str, Any]: Result value produced by this routine.
            """
            if verify_result_update is not None:
                payload["verify_result"] = verify_result_update
            return payload

        if not plan:
            logger.info("[Execute Node] No plan to execute")
            return _with_refresh(dict(state))

        pending = [s for s in plan if s["step_id"] not in completed and s["step_id"] not in failed and s["step_id"] not in blocked]
        if not pending:
            logger.info("[Execute Node] No pending plan steps")
            return _with_refresh(dict(state))
        if execution_round >= self.runtime_config.max_execution_rounds:
            logger.warning(
                "[Execute Node] Max execution rounds reached (%d)",
                self.runtime_config.max_execution_rounds,
            )
            return _with_refresh({
                "execution_round": execution_round,
                "execution_budget": execution_budget,
                "early_stop_reason": f"执行回合达到上限({self.runtime_config.max_execution_rounds})，提前结束。",
                "execution_summary": self._build_execution_summary(stats_steps),
            })

        runnable: list[dict[str, Any]] = []
        for step in pending:
            deps = set(step.get("depends_on", []))
            if deps.issubset(completed):
                runnable.append(self._apply_refresh_params(step, refresh_target_set))

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
            return _with_refresh({
                "current_step": len(completed) + len(failed) + len(blocked),
                "execution_round": execution_round + 1,
                "execution_budget": execution_budget,
                "execution_state": {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)},
                "execution_stats": {**execution_stats, "steps": stats_steps},
                "execution_summary": self._build_execution_summary(stats_steps),
                "tool_results": tool_results,
                "tools_used": tools_used,
            })

        default_parallelism = self.runtime_config.default_max_parallelism
        requested_parallelism = self._safe_int(state.get("parallelism"), default_parallelism)
        max_parallelism = self._safe_int(state.get("max_parallelism"), default_parallelism)
        decision = self.orchestrator.select(
            runnable=runnable,
            trace_counter=trace_counter,
            signature_getter=lambda s: self._step_signature(s.get("tool", ""), s.get("params", {})),
            max_same_invocations=self._max_same_tool_invocations,
            requested_parallelism=requested_parallelism,
            max_parallelism=max_parallelism,
            budget=execution_budget,
        )
        selected = decision.selected
        for step in decision.skipped:
            sid = step["step_id"]
            signature = self._step_signature(step.get("tool", ""), step.get("params", {}))
            blocked.add(sid)
            key = f"{sid}:{step.get('tool')}"
            error_code = str(step.get("_skip_code") or "ORCHESTRATOR_SKIPPED")
            error_reason = str(step.get("_skip_reason") or "Skipped by orchestrator")
            tool_results[key] = ExecutionResult(
                success=False,
                tool_name=step.get("tool", ""),
                result="",
                error_code=error_code,
                error=error_reason,
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            ).model_dump()
            stats_steps.append(
                {
                    "step_id": sid,
                    "tool": step.get("tool"),
                    "status": "blocked",
                    "error_code": error_code,
                    "duration_ms": 0,
                    "signature": signature,
                }
            )
        if decision.budget_stop_reason and not early_stop_reason:
            early_stop_reason = decision.budget_stop_reason

        if not selected:
            return _with_refresh({
                "current_step": len(completed) + len(failed) + len(blocked),
                "execution_round": execution_round + 1,
                "execution_budget": execution_budget,
                "execution_state": {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)},
                "execution_stats": {**execution_stats, "steps": stats_steps},
                "execution_summary": self._build_execution_summary(stats_steps),
                "execution_trace": execution_trace,
                "early_stop_reason": early_stop_reason,
                "tool_results": tool_results,
                "tools_used": tools_used,
            })

        tasks = [self._execute_plan_step(step, state) for step in selected]
        batch_results = await asyncio.gather(*tasks)

        for step, result_obj, elapsed_ms in batch_results:
            step_id = step["step_id"]
            result_key = f"{step_id}:{result_obj.tool_name}"
            tool_results[result_key] = result_obj.model_dump()
            tools_used.append(result_obj.tool_name)
            signature = self._step_signature(result_obj.tool_name, step.get("params", {}))
            if result_obj.success:
                completed.add(step_id)
                self._mark_tool_success(result_obj.tool_name)
            else:
                failed.add(step_id)
                self._mark_tool_failure(result_obj.tool_name)
            execution_trace.append(
                {
                    "step_id": step_id,
                    "tool": result_obj.tool_name,
                    "signature": signature,
                    "status": "success" if result_obj.success else "failed",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            trace_counter[signature] += 1

            stats_steps.append(
                {
                    "step_id": step_id,
                    "tool": result_obj.tool_name,
                    "depends_on": step.get("depends_on", []),
                    "status": "success" if result_obj.success else "failed",
                    "attempt": result_obj.attempt,
                    "error_code": result_obj.error_code,
                    "fallback_used": result_obj.fallback_used,
                    "is_stale": result_obj.is_stale,
                    "refresh_attempted": result_obj.refresh_attempted,
                    "refresh_success": result_obj.refresh_success,
                    "provider_used": result_obj.provider_used,
                    "started_at": result_obj.started_at,
                    "ended_at": result_obj.ended_at,
                    "duration_ms": elapsed_ms,
                    "signature": signature,
                }
            )
            execution_budget["tools_used"] = int(execution_budget.get("tools_used", 0) or 0) + 1
            execution_budget["elapsed_ms"] = int(execution_budget.get("elapsed_ms", 0) or 0) + int(elapsed_ms)
            execution_budget["tokens_used"] = int(execution_budget.get("tokens_used", 0) or 0) + self._estimate_result_tokens(
                result_obj.result
            )

        execution_summary = self._build_execution_summary(stats_steps)
        updated_execution_state = {"completed": sorted(completed), "failed": sorted(failed), "blocked": sorted(blocked)}
        if self.runtime_config.cost_controls_enabled:
            if int(execution_budget.get("elapsed_ms", 0) or 0) >= int(execution_budget.get("max_elapsed_ms", 0) or 0):
                early_stop_reason = early_stop_reason or f"每轮总耗时预算已达上限({execution_budget.get('max_elapsed_ms')}ms)"
            if int(execution_budget.get("tokens_used", 0) or 0) >= int(execution_budget.get("max_tokens", 0) or 0):
                early_stop_reason = early_stop_reason or f"每轮 token 预算已达上限({execution_budget.get('max_tokens')})"
        if not early_stop_reason:
            early_stop_reason = self._compute_early_stop_reason(
                state=state,
                plan=plan,
                execution_state=updated_execution_state,
                execution_summary=execution_summary,
                tool_results=tool_results,
            )

        return _with_refresh({
            "current_step": len(completed) + len(failed) + len(blocked),
            "execution_round": execution_round + 1,
            "execution_budget": execution_budget,
            "execution_state": updated_execution_state,
            "execution_stats": {**execution_stats, "steps": stats_steps},
            "execution_summary": execution_summary,
            "execution_trace": execution_trace,
            "early_stop_reason": early_stop_reason,
            "tools_used": tools_used,
            "tool_results": tool_results,
        })

    def verify_node(self, state: AgentState) -> AgentState:
        """Verify evidence freshness/completeness and determine retry or degrade decisions.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        intent = str(state.get("intent") or "general")
        strategy_detail = state.get("strategy_detail", {}) or {}
        requires_verification = bool(strategy_detail.get("requires_verification", False))
        required_tools = [str(item) for item in strategy_detail.get("required_tools", [])]
        verify_retry_count = self._safe_int(state.get("verify_retry_count"), 0)
        tool_results = state.get("tool_results", {}) or {}
        user_text = self._last_user_text(state)
        issues: list[VerifyIssue] = []

        successful_results = [
            item
            for item in tool_results.values()
            if isinstance(item, dict) and bool(item.get("success"))
        ]
        if requires_verification and not successful_results:
            issues.append(
                VerifyIssue(
                    issue_type="missing_evidence",
                    message="高风险问题缺少工具成功结果，无法验证结论。",
                    severity="high",
                )
            )
        matched_success_tools = {
            str(item.get("tool_name") or "").split(":")[-1]
            for item in successful_results
            if isinstance(item, dict)
        }
        missing_required = [name for name in required_tools if name not in matched_success_tools]
        if requires_verification and missing_required:
            issues.append(
                VerifyIssue(
                    issue_type="required_tools_missing",
                    message=f"缺少必选验证工具结果: {missing_required}",
                    severity="high",
                )
            )

        stale_count = 0
        refresh_targets: list[str] = []
        refresh_tools: list[str] = []
        for key, item in tool_results.items():
            if not isinstance(item, dict) or not bool(item.get("success")):
                continue
            if not bool(item.get("is_stale", False)):
                continue
            stale_count += 1
            tool_name = str(item.get("tool_name") or "").split(":")[-1]
            step_id = str(key).split(":", 1)[0].strip()
            if tool_name in STALE_REFRESHABLE_TOOLS and step_id:
                if step_id not in refresh_targets:
                    refresh_targets.append(step_id)
                if tool_name not in refresh_tools:
                    refresh_tools.append(tool_name)

        if stale_count > 0:
            issues.append(
                VerifyIssue(
                    issue_type="stale_data",
                    message=f"存在 {stale_count} 条过期结果，建议刷新后再回答。",
                    severity="medium",
                )
            )
            if verify_retry_count >= 1:
                issues.append(
                    VerifyIssue(
                        issue_type="stale_refresh_failed",
                        message="已尝试刷新过期数据，但仍无法得到稳定实时结果，建议按降级策略回答并标注不确定性。",
                        severity="high",
                    )
                )
            elif not refresh_targets:
                issues.append(
                    VerifyIssue(
                        issue_type="stale_unrefreshable",
                        message="存在过期结果，但缺少可刷新的天气/酒店工具步骤，建议按降级策略回答。",
                        severity="medium",
                    )
                )

        if not self.runtime_config.timeliness_controls_enabled:
            refresh_targets = []
            refresh_tools = []

        fetched_dates: list[datetime] = []
        for item in successful_results:
            raw = item.get("fetched_at")
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                fetched_dates.append(dt)
            except Exception:
                continue
        if len(fetched_dates) >= 2:
            span_seconds = (max(fetched_dates) - min(fetched_dates)).total_seconds()
            if span_seconds > 7 * 24 * 3600:
                issues.append(
                    VerifyIssue(
                        issue_type="date_inconsistency",
                        message="工具结果时间跨度过大，可能存在时效不一致。",
                        severity="medium",
                    )
                )

        if self._is_high_risk_query(user_text, intent) and not requires_verification:
            issues.append(
                VerifyIssue(
                    issue_type="verification_policy_violation",
                    message="高风险问题未开启验证策略。",
                    severity="high",
                )
            )

        stale_retryable = stale_count > 0 and bool(refresh_targets) and verify_retry_count < 1
        structural_retryable = any(item.issue_type in {"missing_evidence", "required_tools_missing"} for item in issues) and verify_retry_count < 1
        should_retry = stale_retryable or structural_retryable
        if not stale_retryable:
            refresh_targets = []
            refresh_tools = []
        passed = len(issues) == 0
        summary = "verification_passed" if passed else "; ".join(item.message for item in issues)

        result = VerifyResult(
            passed=passed,
            should_retry=should_retry,
            refresh_targets=refresh_targets,
            refresh_tools=refresh_tools,
            issues=issues,
            summary=summary,
        )
        return self._validate_stage_output(
            VerifyStageOutput,
            {
                "verify_result": result.model_dump(),
                "verify_retry_count": verify_retry_count + (1 if should_retry else 0),
                "early_stop_reason": state.get("early_stop_reason") if passed else summary,
            },
        )

    def verify_decision(self, state: AgentState) -> Literal["execute", "answer"]:
        """Return verify-stage routing label for execute-loop or final answer path.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            str: Conditional-edge label consumed by graph routing.
        """
        result = state.get("verify_result", {}) or {}
        if bool(result.get("passed", False)):
            return "answer"
        if bool(result.get("should_retry", False)):
            return "execute"
        return "answer"

    def self_check_node(self, state: AgentState) -> AgentState:
        """Run final answer quality checks and annotate missing checklist items.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        answer = str(state.get("answer") or "").strip()
        tools_used = list(state.get("tools_used", []) or [])
        missing_items: list[str] = []
        if not answer:
            missing_items.append("empty_answer")
        if answer and answer[-1] not in {"。", ".", "！", "!", "？", "?"}:
            missing_items.append("incomplete_ending")
        if tools_used and "source" not in answer.lower():
            missing_items.append("missing_source_trace")

        passed = len(missing_items) == 0
        summary = "self_check_passed" if passed else f"self_check_failed:{','.join(missing_items)}"
        checked = SelfCheckResult(passed=passed, missing_items=missing_items, summary=summary)
        patched_answer = answer
        if "incomplete_ending" in missing_items:
            patched_answer = f"{answer}。"
        return self._validate_stage_output(
            SelfCheckStageOutput,
            {
                "answer": patched_answer,
                "self_check_result": checked.model_dump(),
            },
        )

    def should_continue(self, state: AgentState) -> Literal["execute", "answer"]:
        """Return execute-loop continuation decision based on remaining steps and budget state.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            str: Conditional-edge label consumed by graph routing.
        """
        if state.get("early_stop_reason"):
            return "answer"
        if self._safe_int(state.get("execution_round"), 0) >= self.runtime_config.max_execution_rounds:
            return "answer"
        plan = state.get("plan", []) or []
        execution_state = state.get("execution_state", {}) or {}
        completed = len(execution_state.get("completed", []))
        failed = len(execution_state.get("failed", []))
        blocked = len(execution_state.get("blocked", []))
        finished = completed + failed + blocked
        return "execute" if finished < len(plan) else "answer"

    def answer_node(self, state: AgentState) -> AgentState:
        """Render final answer text, reasoning summary, and execution metadata sections.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        logger.info("[Answer Node] Generating answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")
        intent = state.get("intent")
        tool_results = state.get("tool_results", {})
        tools_used = state.get("tools_used", [])
        plan_id = state.get("plan_id")
        execution_stats = state.get("execution_stats", {}) or {}
        execution_summary = state.get("execution_summary", {}) or {}
        execution_budget = state.get("execution_budget", {}) or {}
        early_stop_reason = state.get("early_stop_reason")
        strategy_detail = state.get("strategy_detail", {}) or {}
        verify_result = state.get("verify_result", {}) or {}
        verify_required = bool(strategy_detail.get("requires_verification", False))
        verify_passed = bool(verify_result.get("passed", False)) if verify_result else False
        user_question = str(last_message.content or "")
        evidence_required = bool(verify_required or self._is_high_risk_query(user_question, str(intent or "")))
        fused_tool_results: Optional[dict[str, Any]] = None

        context = ""
        if plan_id:
            context += f"\n\n## 执行计划 ID:\n{plan_id}\n"
        if execution_stats.get("steps"):
            context += "\n## 步骤执行明细:\n"
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
                f"- 回退: {execution_summary.get('fallback_steps', 0)}\n"
                f"- 成功率: {execution_summary.get('success_rate', 0.0):.2f}\n"
                f"- 延迟P95: {(execution_summary.get('latency_percentiles_ms') or {}).get('p95', 0)}ms\n"
            )
        if execution_budget:
            context += "\n## 执行预算:\n"
            context += (
                f"- tools_used/max_tools: {execution_budget.get('tools_used', 0)}/{execution_budget.get('max_tools', 0)}\n"
                f"- elapsed_ms/max_elapsed_ms: {execution_budget.get('elapsed_ms', 0)}/{execution_budget.get('max_elapsed_ms', 0)}\n"
                f"- tokens_used/max_tokens: {execution_budget.get('tokens_used', 0)}/{execution_budget.get('max_tokens', 0)}\n"
            )
        if early_stop_reason:
            context += f"\n## 早停说明:\n- {early_stop_reason}\n"
        if tool_results:
            fused = self._fuse_tool_results(tool_results, intent=intent)
            fused_tool_results = fused
            context += "\n\n## 融合后的工具证据\n"
            context += json.dumps(fused, ensure_ascii=False, indent=2)

        prompt = build_answer_prompt(
            user_question=user_question,
            context=context,
            tools_used=tools_used,
            intent=intent,
            evidence_required=evidence_required,
        )

        response = self.llm.invoke([
            SystemMessage(content=build_system_prompt(self.system_prompt, intent)),
            HumanMessage(content=prompt),
        ])

        verify_issue_types = {
            str(item.get("issue_type") or "")
            for item in verify_result.get("issues", [])
            if isinstance(item, dict)
        }
        stale_degraded = bool(verify_issue_types & {"stale_data", "stale_refresh_failed", "stale_unrefreshable"})

        answer = self._coerce_llm_content_to_text(response.content)
        if verify_required and not verify_passed:
            prefix = (
                "当前结论尚未通过工具验证，以下内容仅为暂定建议而非确定结论。"
                "请先补充或刷新关键信息后再做最终决策。"
            )
            if stale_degraded:
                prefix += "天气/酒店实时数据刷新未完全成功，内容可能存在时效偏差。"
            answer = f"{prefix}\n\n{answer}"
        elif stale_degraded and not verify_passed:
            answer = (
                "以下建议可能包含可能过期的数据，系统已尝试刷新但尚未获得稳定实时结果，请谨慎参考。\n\n"
                + str(answer)
            )

        if evidence_required:
            answer = self._ensure_source_evidence_section(
                answer=str(answer or ""),
                tool_results=tool_results,
                intent=intent,
            )
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info("[Answer Node] Answer generated, length=%d", len(answer))
        return self._validate_stage_output(
            AnswerStageOutput,
            {
                "messages": messages,
                "answer": answer,
                "reasoning": self._render_reasoning(state, tools_used),
                "fused_tool_results": fused_tool_results,
            },
        )

    def direct_answer_node(self, state: AgentState) -> AgentState:
        """Render direct-answer path output when tool orchestration is skipped.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Partial state patch that LangGraph merges into the global state.
        """
        logger.info("[Direct Answer Node] Generating direct answer...")

        messages = state["messages"]
        last_message = messages[-1] if messages else HumanMessage(content="")
        intent = state.get("intent")
        strategy_detail = state.get("strategy_detail", {}) or {}
        if bool(strategy_detail.get("requires_verification", False)):
            answer = "该任务需要工具验证后才能给出确定性结论，请使用 ReAct 工具模式。"
            messages = list(messages)
            messages.append(AIMessage(content=answer))
            return self._validate_stage_output(
                AnswerStageOutput,
                {
                    "messages": messages,
                    "answer": answer,
                    "reasoning": "策略要求强制验证，拒绝直接给出确定性回答。",
                    "fused_tool_results": None,
                },
            )
        if self._is_high_risk_query(str(last_message.content), str(intent)):
            answer = "该问题涉及价格或政策等高风险信息，请切换到工具验证模式后我再给出结论。"
            messages = list(messages)
            messages.append(AIMessage(content=answer))
            return self._validate_stage_output(
                AnswerStageOutput,
                {
                    "messages": messages,
                    "answer": answer,
                    "reasoning": "高风险问题触发强制工具验证。",
                    "fused_tool_results": None,
                },
            )
        prompt = build_direct_prompt(str(last_message.content), intent)

        response = self.llm.invoke([
            SystemMessage(content=build_system_prompt(self.system_prompt, intent)),
            HumanMessage(content=prompt),
        ])

        answer = self._coerce_llm_content_to_text(response.content)
        messages = list(messages)
        messages.append(AIMessage(content=answer))

        logger.info("[Direct Answer Node] Answer generated, length=%d", len(answer))
        return self._validate_stage_output(
            AnswerStageOutput,
            {
                "messages": messages,
                "answer": answer,
                "reasoning": "直接回答（无需工具）",
                "fused_tool_results": None,
            },
        )

    @staticmethod
    def _default_plan(intent: str, entities: dict) -> list[dict]:
        """Build default fallback plan when no external plan is produced.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            intent: Input `intent` consumed by this routine.
            entities: Structured entities parsed from intent stage output.
        
        Returns:
            list[dict]: Result value produced by this routine.
        """
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
                    "description": "查询城市核心景点",
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
                    "description": "查询天气情况",
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
    def _merge_plans(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge generated plan with defaults and remove duplicate steps.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            primary: Input `primary` consumed by this routine.
            secondary: Input `secondary` consumed by this routine.
        
        Returns:
            list[dict[str, Any]]: Result value produced by this routine.
        """
        merged = list(primary)
        existing_signatures = {
            f"{item.get('tool')}:{json.dumps(item.get('params', {}), ensure_ascii=False, sort_keys=True)}"
            for item in merged
        }
        for item in secondary:
            signature = f"{item.get('tool')}:{json.dumps(item.get('params', {}), ensure_ascii=False, sort_keys=True)}"
            if signature not in existing_signatures:
                merged.append(item)
                existing_signatures.add(signature)
        return merged

    def _enforce_tool_policy(
        self,
        plan: list[dict[str, Any]],
        required_tools: list[str],
        optional_tools: list[str],
        entities: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Enforce required/optional tool policy against candidate plan steps.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            plan: Plan step list prepared by planner stage.
            required_tools: Input `required_tools` consumed by this routine.
            optional_tools: Input `optional_tools` consumed by this routine.
            entities: Structured entities parsed from intent stage output.
        
        Returns:
            list[dict[str, Any]]: Result value produced by this routine.
        """
        merged = list(plan)
        existing_tools = {str(item.get("tool", "")) for item in merged}
        next_step = len(merged) + 1

        for tool_name in required_tools:
            if tool_name in existing_tools:
                continue
            step = self._default_step_for_tool(step_num=next_step, tool_name=tool_name, entities=entities, required=True)
            if step:
                merged.append(step)
                existing_tools.add(tool_name)
                next_step += 1

        # Optional tools are only auto-injected when plan is very short.
        if len(merged) <= 2:
            for tool_name in optional_tools:
                if tool_name in existing_tools:
                    continue
                step = self._default_step_for_tool(step_num=next_step, tool_name=tool_name, entities=entities, required=False)
                if step:
                    merged.append(step)
                    existing_tools.add(tool_name)
                    next_step += 1
                if len(merged) >= self.runtime_config.max_plan_steps:
                    break

        return merged

    @staticmethod
    def _default_step_for_tool(step_num: int, tool_name: str, entities: dict[str, Any], required: bool) -> Optional[dict[str, Any]]:
        """Build default parameters and description for a specific tool step.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            step_num: Input `step_num` consumed by this routine.
            tool_name: Registered tool identifier from the tool map.
            entities: Structured entities parsed from intent stage output.
            required: Input `required` consumed by this routine.
        
        Returns:
            Optional[dict[str, Any]]: Result value produced by this routine.
        """
        city = entities.get("city") or entities.get("destination") or "北京"
        days = entities.get("days", 3)
        mapping: dict[str, dict[str, Any]] = {
            "search_cities": {"params": {"query": entities.get("query") or city}, "description": "补全候选目的地"},
            "query_attractions": {"params": {"city": city, "category": entities.get("category")}, "description": "补全景点信息"},
            "query_hotels": {"params": {"city": city}, "description": "补全酒店信息"},
            "get_weather": {"params": {"city": city, "days": days}, "description": "补全天气信息"},
            "plan_itinerary": {"params": {"destination": city, "days": days, "interests": entities.get("interests")}, "description": "补全行程规划"},
            "calculate_budget": {
                "params": {
                    "destination": city,
                    "days": days,
                    "people": entities.get("people", 1),
                    "accommodation_level": entities.get("level", "medium"),
                },
                "description": "补全预算测算",
            },
            "get_travel_tips": {"params": {"destination": city, "season": entities.get("season")}, "description": "补全出行建议"},
        }
        item = mapping.get(tool_name)
        if not item:
            return None
        return {
            "step": step_num,
            "step_id": f"s{step_num}",
            "tool": tool_name,
            "params": item["params"],
            "description": f"{item['description']} ({'required' if required else 'optional'})",
            "depends_on": [],
        }

    @staticmethod
    async def _invoke_tool(tool: Tool, params: dict) -> Any:
        """Invoke one tool with normalized params and collect execution metadata.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool: Tool instance or tool descriptor being processed.
            params: Normalized tool parameters after policy correction and validation.
        
        Returns:
            Any: Result value produced by this routine.
        """
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
        """Execute a tool with retry/cooldown policy and normalized error handling.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool: Tool instance or tool descriptor being processed.
            tool_name: Registered tool identifier from the tool map.
            params: Normalized tool parameters after policy correction and validation.
            timeout_seconds: Input `timeout_seconds` consumed by this routine.
            max_retries: Input `max_retries` consumed by this routine.
        
        Returns:
            ExecutionResult: Result value produced by this routine.
        """
        if not self.runtime_config.reliability_controls_enabled:
            attempts = 1
        else:
            attempts = max(1, max_retries + 1)
        last_error: Optional[Exception] = None
        start_ts = datetime.now().isoformat()

        if self.runtime_config.reliability_controls_enabled and self._is_tool_circuit_open(tool_name):
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
            if attempt < attempts and self.runtime_config.reliability_controls_enabled:
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

    async def _execute_plan_step(self, step: dict[str, Any], state: AgentState) -> tuple[dict[str, Any], ExecutionResult, int]:
        """Execute one plan step with validation, health checks, and tracing fields.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            step: Single executable plan step descriptor.
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            tuple[dict[str, Any], ExecutionResult, int]: Result value produced by this routine.
        """
        step_id = step.get("step_id", f"step-{step.get('step', 0)}")
        tool_name = str(step.get("tool", ""))
        params = dict(step.get("params", {}) or {})
        timeout_seconds = self._resolve_timeout_seconds(step, tool_name)
        max_retries = int(step.get("max_retries", self.runtime_config.default_tool_max_retries))
        started = time.perf_counter()
        corrected_params = self._auto_correct_tool_params(tool_name, params, state)
        refresh_requested = bool(corrected_params.get("refresh", False))
        step_with_params = {**step, "params": corrected_params}

        logger.info("[Execute Node] Step %s running tool=%s timeout=%ss", step_id, tool_name, timeout_seconds)
        tool = self.tool_map.get(tool_name)
        if tool is None:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                result="",
                error_code="TOOL_NOT_REGISTERED",
                error=f"Tool not registered: {tool_name}",
                started_at=datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
            result.refresh_attempted = refresh_requested
            self._attach_execution_metadata(result, tool_name)
            return step_with_params, result, int((time.perf_counter() - started) * 1000)

        validation_error = self._validate_tool_params(tool, corrected_params)
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
            result.refresh_attempted = refresh_requested
            self._attach_execution_metadata(result, tool_name)
            return step_with_params, result, int((time.perf_counter() - started) * 1000)

        unsafe_reason = None
        if self.runtime_config.security_controls_enabled:
            unsafe_reason = self._detect_unsafe_params(corrected_params)
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
            result.refresh_attempted = refresh_requested
            self._attach_execution_metadata(result, tool_name)
            return step_with_params, result, int((time.perf_counter() - started) * 1000)

        logger.info(
            "[Execute Node] Step %s invoking %s with params=%s",
            step_id,
            tool_name,
            self._sanitize_params_for_log(corrected_params),
        )

        try:
            result = await self._run_tool_with_retry(
                tool=tool,
                tool_name=tool_name,
                params=corrected_params,
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

        result.refresh_attempted = refresh_requested or bool(result.refresh_attempted)
        if refresh_requested and not result.success and not result.fallback_suggestion:
            result.fallback_suggestion = "实时刷新失败，已降级为可能非实时结果，请谨慎决策"
        if result.success:
            result.result = self._normalize_tool_result(tool_name, result.result)
        self._attach_execution_metadata(result, tool_name)
        return step_with_params, result, int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _step_signature(tool_name: str, params: dict[str, Any]) -> str:
        """Build a stable step signature used for loop detection.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
            params: Normalized tool parameters after policy correction and validation.
        
        Returns:
            str: Result value produced by this routine.
        """
        try:
            rendered = json.dumps(params, ensure_ascii=False, sort_keys=True)
        except Exception:
            rendered = str(params)
        return f"{tool_name}:{rendered}"

    def _compute_early_stop_reason(
        self,
        state: AgentState,
        plan: list[dict[str, Any]],
        execution_state: dict[str, Any],
        execution_summary: dict[str, Any],
        tool_results: dict[str, Any],
    ) -> Optional[str]:
        """Compute deterministic early-stop reason from elapsed budgets and limits.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
            plan: Plan step list prepared by planner stage.
            execution_state: Input `execution_state` consumed by this routine.
            execution_summary: Aggregated execution metrics for diagnostics and UI.
            tool_results: Input `tool_results` consumed by this routine.
        
        Returns:
            Optional[str]: Result value produced by this routine.
        """
        finished = (
            len(execution_state.get("completed", []))
            + len(execution_state.get("failed", []))
            + len(execution_state.get("blocked", []))
        )
        if finished >= len(plan):
            return None

        intent = str(state.get("intent", "general"))
        terminal_tool = self._terminal_tool_for_intent(intent)
        if not terminal_tool:
            return None

        for item in tool_results.values():
            if not isinstance(item, dict):
                continue
            if item.get("success") and item.get("tool_name") == terminal_tool:
                rate = float(execution_summary.get("success_rate", 0.0))
                return f"核心步骤已完成（{terminal_tool}），提前结束剩余低价值步骤，当前成功率 {rate:.2f}"

        return None

    @staticmethod
    def _resolve_refresh_targets(verify_result: dict[str, Any]) -> list[str]:
        """Resolve tools eligible for stale-result refresh based on verify findings.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            verify_result: Input `verify_result` consumed by this routine.
        
        Returns:
            list[str]: Result value produced by this routine.
        """
        if not isinstance(verify_result, dict):
            return []
        if not bool(verify_result.get("should_retry", False)):
            return []
        raw_targets = verify_result.get("refresh_targets", [])
        if not isinstance(raw_targets, list):
            return []
        targets: list[str] = []
        for item in raw_targets:
            step_id = str(item or "").strip()
            if not step_id:
                continue
            if step_id not in targets:
                targets.append(step_id)
        return targets

    @staticmethod
    def _apply_refresh_params(step: dict[str, Any], refresh_targets: set[str]) -> dict[str, Any]:
        """Apply refresh-specific parameter overrides before re-invoking a tool.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            step: Single executable plan step descriptor.
            refresh_targets: Input `refresh_targets` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        step_id = str(step.get("step_id") or "")
        tool_name = str(step.get("tool") or "")
        if step_id not in refresh_targets or tool_name not in STALE_REFRESHABLE_TOOLS:
            return step
        params = dict(step.get("params", {}) or {})
        params["refresh"] = True
        return {**step, "params": params}

    @staticmethod
    def _terminal_tool_for_intent(intent: str) -> Optional[str]:
        """Return the terminal tool usually sufficient for a given intent.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            intent: Input `intent` consumed by this routine.
        
        Returns:
            Optional[str]: Result value produced by this routine.
        """
        mapping = {
            "recommend": "search_cities",
            "attractions": "query_attractions",
            "itinerary": "plan_itinerary",
            "budget": "calculate_budget",
            "tips": "get_travel_tips",
            "hotel": "query_hotels",
        }
        return mapping.get(intent)

    @staticmethod
    def _resolve_tool_policy(primary_intent: str, secondary_intent: Optional[str]) -> tuple[list[str], list[str]]:
        """Resolve effective tool policy for current intent and inferred secondary intent.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            primary_intent: Input `primary_intent` consumed by this routine.
            secondary_intent: Input `secondary_intent` consumed by this routine.
        
        Returns:
            tuple[list[str], list[str]]: Result value produced by this routine.
        """
        primary = INTENT_TOOL_POLICY.get(primary_intent, INTENT_TOOL_POLICY["general"])
        required = list(primary.get("required", []))
        optional = list(primary.get("optional", []))
        if secondary_intent:
            secondary = INTENT_TOOL_POLICY.get(secondary_intent, INTENT_TOOL_POLICY["general"])
            for name in secondary.get("required", []):
                if name not in required:
                    required.append(name)
            for name in secondary.get("optional", []):
                if name not in optional and name not in required:
                    optional.append(name)
        return required, optional

    @staticmethod
    def _is_verify_required(primary_intent: str, secondary_intent: Optional[str]) -> bool:
        """Return whether verification must run for the current strategy/intent pair.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            primary_intent: Input `primary_intent` consumed by this routine.
            secondary_intent: Input `secondary_intent` consumed by this routine.
        
        Returns:
            bool: Decision flag used by guards, routing, or policy checks.
        """
        primary_required = bool(INTENT_TOOL_POLICY.get(primary_intent, {}).get("verify_required", False))
        secondary_required = bool(INTENT_TOOL_POLICY.get(str(secondary_intent), {}).get("verify_required", False)) if secondary_intent else False
        return primary_required or secondary_required

    @staticmethod
    def _infer_secondary_intent(primary_intent: str, user_text: str, intent_detail: dict[str, Any]) -> Optional[str]:
        """Infer secondary intent signals from query text and entities.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            primary_intent: Input `primary_intent` consumed by this routine.
            user_text: Input `user_text` consumed by this routine.
            intent_detail: Input `intent_detail` consumed by this routine.
        
        Returns:
            Optional[str]: Result value produced by this routine.
        """
        text = str(user_text or "")
        lowered = text.lower()
        entities = intent_detail.get("entities", {}) if isinstance(intent_detail, dict) else {}
        if primary_intent != "budget" and any(token in text for token in ("预算", "花费", "费用", "价格", "票价")):
            return "budget"
        if primary_intent != "budget" and any(token in lowered for token in ("budget", "cost", "price")):
            return "budget"
        if primary_intent != "itinerary" and any(token in text for token in ("行程", "路线", "安排", "几天", "攻略")):
            return "itinerary"
        if primary_intent != "itinerary" and any(token in lowered for token in ("itinerary", "plan", "route")):
            return "itinerary"
        if primary_intent != "hotel" and any(token in text for token in ("酒店", "住宿", "民宿")):
            return "hotel"
        if primary_intent != "attractions" and any(token in text for token in ("景点", "打卡", "门票")):
            return "attractions"
        if any(key in entities for key in ("days", "people", "budget", "budget_cny")) and primary_intent != "budget":
            return "budget"
        if primary_intent == "itinerary":
            return "budget"
        return None

    @staticmethod
    def _is_consecutive_loop(execution_trace: list[dict[str, Any]], signature: str) -> bool:
        """Detect repeated plan/tool signatures indicating a potential execution loop.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            execution_trace: Input `execution_trace` consumed by this routine.
            signature: Input `signature` consumed by this routine.
        
        Returns:
            bool: Decision flag used by guards, routing, or policy checks.
        """
        if len(execution_trace) < 2:
            return False
        latest = execution_trace[-2:]
        return all(item.get("signature") == signature for item in latest)

    @staticmethod
    def _is_high_risk_query(text: str, intent: str) -> bool:
        """Detect high-risk user queries that require stronger evidence verification.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            text: Input `text` consumed by this routine.
            intent: Input `intent` consumed by this routine.
        
        Returns:
            bool: Decision flag used by guards, routing, or policy checks.
        """
        intent_lower = str(intent or "").lower()
        if intent_lower in {"budget"}:
            return True
        lowered = str(text or "").lower()
        return any(keyword in lowered for keyword in HIGH_RISK_KEYWORDS)

    def _rank_tool_results(
        self,
        tool_results: dict[str, Any],
        intent: Optional[str],
    ) -> list[tuple[str, Any, float]]:
        """Rank tool results by reliability, freshness, and relevance score.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_results: Input `tool_results` consumed by this routine.
            intent: Input `intent` consumed by this routine.
        
        Returns:
            list[tuple[str, Any, float]]: Result value produced by this routine.
        """
        ranked: list[tuple[str, Any, float]] = []
        for tool_name, result in tool_results.items():
            score = self._score_tool_result(tool_name, result, intent=intent)
            ranked.append((tool_name, result, score))
        ranked.sort(key=lambda item: item[2], reverse=True)
        return ranked

    def _score_tool_result(self, tool_name: str, result: Any, intent: Optional[str]) -> float:
        """Compute numeric quality score for one tool result payload.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
            result: Tool output payload or normalized intermediate result.
            intent: Input `intent` consumed by this routine.
        
        Returns:
            float: Result value produced by this routine.
        """
        if not isinstance(result, dict):
            return 0.0
        if not result.get("success"):
            return 0.0

        freshness = 1.0
        ttl_seconds = result.get("ttl_seconds")
        fetched_at = result.get("fetched_at")
        is_stale = bool(result.get("is_stale", False))
        if is_stale:
            freshness = 0.2
        elif isinstance(ttl_seconds, int) and isinstance(fetched_at, str):
            try:
                fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
                if fetched_dt.tzinfo is None:
                    fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)
                else:
                    fetched_dt = fetched_dt.astimezone(timezone.utc)
                age = (datetime.now(timezone.utc) - fetched_dt).total_seconds()
                freshness = max(0.1, min(1.0, 1.0 - max(0.0, age) / max(1, ttl_seconds)))
            except Exception:
                freshness = 0.8

        credibility = 1.0
        if result.get("fallback_used"):
            credibility -= 0.2
        if result.get("error_code"):
            credibility -= 0.4
        provider_used = str(result.get("provider_used") or "")
        if provider_used.endswith("fallback"):
            credibility -= 0.1
        credibility = max(0.0, min(1.0, credibility))

        coverage = 0.6
        expected_tool = self._terminal_tool_for_intent(str(intent or ""))
        canonical_tool_name = str(result.get("tool_name") or tool_name).split(":")[-1]
        if expected_tool and expected_tool in canonical_tool_name:
            coverage = 1.0
        elif canonical_tool_name in {"query_attractions", "query_hotels", "get_weather"}:
            coverage = 0.8

        total_weight = (
            self.runtime_config.tool_score_freshness_weight
            + self.runtime_config.tool_score_credibility_weight
            + self.runtime_config.tool_score_coverage_weight
        )
        if total_weight <= 0:
            return 0.0
        score = (
            freshness * self.runtime_config.tool_score_freshness_weight
            + credibility * self.runtime_config.tool_score_credibility_weight
            + coverage * self.runtime_config.tool_score_coverage_weight
        ) / total_weight
        return round(score, 4)

    @staticmethod
    def _estimate_result_tokens(payload: Any) -> int:
        """Estimate token footprint of normalized tool results for budget tracking.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            payload: Input `payload` consumed by this routine.
        
        Returns:
            int: Result value produced by this routine.
        """
        try:
            text = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
        except Exception:
            text = str(payload)
        return max(1, len(text) // 4)

    @staticmethod
    def _tool_group(tool_name: str) -> str:
        """Map tool names into logical groups for summary and diagnostics display.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            str: Result value produced by this routine.
        """
        name = str(tool_name).split(":")[-1]
        if name in {"search_cities", "query_attractions", "query_hotels", "get_weather"}:
            return "discovery"
        if name in {"calculate_budget"}:
            return "budget"
        if name in {"plan_itinerary"}:
            return "planning"
        if name in {"get_travel_tips"}:
            return "advice"
        return "other"

    def _fuse_tool_results(self, tool_results: dict[str, Any], intent: Optional[str]) -> dict[str, Any]:
        """Fuse multi-tool outputs into a compact evidence bundle for prompt rendering.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_results: Input `tool_results` consumed by this routine.
            intent: Input `intent` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        ranked = self._rank_tool_results(tool_results, intent=intent)
        groups: dict[str, list[dict[str, Any]]] = {}
        for tool_name, result, score in ranked:
            group = self._tool_group(tool_name)
            groups.setdefault(group, [])
            if not isinstance(result, dict):
                continue
            if not result.get("success"):
                continue
            payload = result.get("result")
            if isinstance(payload, dict) and "report" in payload:
                payload = payload.get("report")
            groups[group].append(
                {
                    "tool_name": str(result.get("tool_name") or tool_name).split(":")[-1],
                    "score": score,
                    "source": result.get("source"),
                    "fetched_at": result.get("fetched_at"),
                    "is_stale": bool(result.get("is_stale", False)),
                    "summary": str(payload)[:900],
                }
            )
        fused: dict[str, Any] = {"groups": {}, "top_evidence": []}
        for group, items in groups.items():
            items.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
            fused["groups"][group] = items[:3]
        for _, result, score in ranked[:5]:
            if not isinstance(result, dict) or not result.get("success"):
                continue
            fused["top_evidence"].append(
                {
                    "tool_name": result.get("tool_name"),
                    "score": score,
                    "source": result.get("source"),
                    "fetched_at": result.get("fetched_at"),
                }
                )
        return fused

    def _build_source_evidence_entries(
        self,
        tool_results: dict[str, Any],
        intent: Optional[str],
        limit: int = 4,
    ) -> list[dict[str, str]]:
        """Build normalized source-evidence entries from tool result metadata.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_results: Input `tool_results` consumed by this routine.
            intent: Input `intent` consumed by this routine.
            limit: Input `limit` consumed by this routine.
        
        Returns:
            list[dict[str, str]]: Result value produced by this routine.
        """
        ranked = self._rank_tool_results(tool_results, intent=intent)
        entries: list[dict[str, str]] = []
        for tool_name, result, _score in ranked:
            if not isinstance(result, dict) or not bool(result.get("success")):
                continue
            source = str(result.get("source") or "").strip() or "unavailable"
            fetched_at = str(result.get("fetched_at") or "").strip() or "unavailable"
            canonical_name = str(result.get("tool_name") or tool_name).split(":")[-1]
            entries.append(
                {
                    "tool": canonical_name,
                    "source": source,
                    "fetched_at": fetched_at,
                }
            )
            if len(entries) >= limit:
                break

        if entries:
            return entries
        return [{"tool": "unavailable", "source": "unavailable", "fetched_at": "unavailable"}]

    def _ensure_source_evidence_section(
        self,
        answer: str,
        tool_results: dict[str, Any],
        intent: Optional[str],
    ) -> str:
        """Ensure final answer text contains a formatted source-evidence section.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            answer: Input `answer` consumed by this routine.
            tool_results: Input `tool_results` consumed by this routine.
            intent: Input `intent` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        lowered = str(answer or "").lower()
        if "source" in lowered and "fetched_at" in lowered:
            return str(answer or "")

        entries = self._build_source_evidence_entries(tool_results, intent=intent)
        lines = ["证据来源:"]
        for item in entries:
            lines.append(
                f"- {item['tool']}: source={item['source']}; fetched_at={item['fetched_at']}"
            )
        section = "\n".join(lines)
        base = str(answer or "").rstrip()
        if base:
            return f"{base}\n\n{section}"
        return section

    def _auto_correct_tool_params(self, tool_name: str, params: dict[str, Any], state: AgentState) -> dict[str, Any]:
        """Auto-correct invalid tool parameters using inferred entities and defaults.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
            params: Normalized tool parameters after policy correction and validation.
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        corrected = dict(params or {})
        entities = (state.get("intent_detail") or {}).get("entities", {}) or {}
        user_text = self._last_user_text(state)
        inferred_city = self._infer_city(corrected, entities, user_text)

        if tool_name == "search_cities":
            corrected["query"] = self._coalesce_text(
                corrected.get("query"),
                entities.get("query"),
                entities.get("city"),
                inferred_city,
                user_text,
                default="热门目的地",
            )
        elif tool_name in {"query_attractions", "query_hotels", "get_weather"}:
            corrected["city"] = self._coalesce_text(
                corrected.get("city"),
                entities.get("city"),
                entities.get("destination"),
                inferred_city,
                default="北京",
            )
            if tool_name == "get_weather":
                corrected["days"] = self._normalize_int(
                    corrected.get("days", entities.get("days", DEFAULT_DAY_COUNT)),
                    minimum=1,
                    maximum=15,
                    default=DEFAULT_DAY_COUNT,
                )
        elif tool_name in {"plan_itinerary", "get_travel_tips", "calculate_budget"}:
            corrected["destination"] = self._coalesce_text(
                corrected.get("destination"),
                entities.get("destination"),
                entities.get("city"),
                inferred_city,
                default="北京",
            )
            if tool_name == "plan_itinerary":
                corrected["days"] = self._normalize_int(
                    corrected.get("days", entities.get("days", DEFAULT_DAY_COUNT)),
                    minimum=1,
                    maximum=15,
                    default=DEFAULT_DAY_COUNT,
                )
                interests = corrected.get("interests") or entities.get("interests")
                if isinstance(interests, list):
                    corrected["interests"] = ",".join(str(x) for x in interests if str(x).strip())
            if tool_name == "get_travel_tips":
                season = corrected.get("season") or entities.get("season")
                if season:
                    corrected["season"] = str(season).strip()
            if tool_name == "calculate_budget":
                inferred_budget = self._infer_budget_cny(corrected, entities, user_text)
                corrected["days"] = self._normalize_int(
                    corrected.get("days", entities.get("days", DEFAULT_DAY_COUNT)),
                    minimum=1,
                    maximum=30,
                    default=DEFAULT_DAY_COUNT,
                )
                corrected["people"] = self._normalize_int(
                    corrected.get("people", entities.get("people", DEFAULT_PEOPLE_COUNT)),
                    minimum=1,
                    maximum=10,
                    default=DEFAULT_PEOPLE_COUNT,
                )
                corrected["accommodation_level"] = self._normalize_accommodation_level(
                    corrected.get("accommodation_level", entities.get("level", "medium"))
                )
                if inferred_budget is not None:
                    corrected["budget_cny"] = inferred_budget

        sanitized = {k: v for k, v in corrected.items() if v is not None}
        return sanitized

    @staticmethod
    def _infer_budget_cny(params: dict[str, Any], entities: dict[str, Any], user_text: str) -> Optional[int]:
        """Infer budget amount from entities and free-text query content.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            params: Normalized tool parameters after policy correction and validation.
            entities: Structured entities parsed from intent stage output.
            user_text: Input `user_text` consumed by this routine.
        
        Returns:
            Optional[int]: Result value produced by this routine.
        """
        for source in (params, entities):
            raw = source.get("budget_cny") or source.get("budget")
            if raw is None:
                continue
            try:
                value = int(str(raw).replace(",", "").strip())
                if value > 0:
                    return value
            except Exception:
                continue
        match = re.search(r"(预算|费用|花费)\s*[:：]?\s*(\d{3,7})", user_text or "")
        if match:
            return int(match.group(2))
        return None

    def _normalize_tool_result(self, tool_name: str, payload: Any) -> Any:
        """Normalize heterogeneous tool outputs into a consistent dict payload.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
            payload: Input `payload` consumed by this routine.
        
        Returns:
            Any: Result value produced by this routine.
        """
        if not isinstance(payload, dict):
            return payload

        normalized = dict(payload)
        report = normalized.get("report")
        if isinstance(report, str):
            normalized["report"] = self._normalize_report_text(report)

        data = normalized.get("data")
        if isinstance(data, list):
            normalized_data: list[Any] = []
            for item in data:
                if isinstance(item, dict):
                    normalized_data.append(self._normalize_result_item(item))
                else:
                    normalized_data.append(item)
            normalized["data"] = normalized_data
        elif isinstance(data, dict):
            normalized["data"] = self._normalize_result_item(data)

        return normalized

    def _normalize_report_text(self, text: str) -> str:
        """Normalize report-like text blocks for stable downstream markdown rendering.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            text: Input `text` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        normalized = text
        normalized = re.sub(r"(?<!C)NY\s*", "CNY ", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"(\d+)\s*元", r"CNY \1", normalized)
        normalized = re.sub(r"(\d+)\s*人民币", r"CNY \1", normalized)
        normalized = re.sub(r"(\d+)\s*RMB", r"CNY \1", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"(\d{1,2})\s*天", r"\1 days", normalized)
        normalized = re.sub(r"(\d{1,2})\s*人", r"\1 travelers", normalized)
        return normalized

    def _normalize_result_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize one nested result item recursively for predictable serialization.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            item: Input `item` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        normalized = dict(item)
        for key in ("price", "ticket"):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = self._normalize_report_text(value)
            elif isinstance(value, (int, float)):
                normalized[key] = f"CNY {int(value)}"

        for key in ("hours", "date", "check_in", "check_out"):
            value = normalized.get(key)
            if value is None:
                continue
            normalized[key] = str(value).strip()

        if "rating" in normalized:
            try:
                normalized["rating"] = round(float(normalized["rating"]), 1)
            except Exception:
                pass
        return normalized

    @staticmethod
    def _normalize_int(value: Any, minimum: int, maximum: int, default: int) -> int:
        """Normalize integer-like values with fallback defaults and bounds.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            value: Candidate scalar value to normalize/validate.
            minimum: Input `minimum` consumed by this routine.
            maximum: Input `maximum` consumed by this routine.
            default: Input `default` consumed by this routine.
        
        Returns:
            int: Result value produced by this routine.
        """
        try:
            parsed = int(value)
            return min(maximum, max(minimum, parsed))
        except Exception:
            return default

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        """Safely parse integer values without raising parsing exceptions.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            value: Candidate scalar value to normalize/validate.
            default: Input `default` consumed by this routine.
        
        Returns:
            int: Result value produced by this routine.
        """
        try:
            if value is None:
                return default
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _normalize_accommodation_level(value: Any) -> str:
        """Normalize accommodation level labels into allowed enum values.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            value: Candidate scalar value to normalize/validate.
        
        Returns:
            str: Result value produced by this routine.
        """
        text = str(value or "").strip().lower()
        if text in {"economy", "budget", "low"}:
            return "economy"
        if text in {"luxury", "high", "premium"}:
            return "luxury"
        return "medium"

    @staticmethod
    def _coalesce_text(*values: Any, default: str = "") -> str:
        """Return the first non-empty text candidate among multiple inputs.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            *values: Input `values` consumed by this routine.
            default: Input `default` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return default

    @staticmethod
    def _last_user_text(state: AgentState) -> str:
        """Extract latest user utterance from current graph state messages.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
        
        Returns:
            str: Result value produced by this routine.
        """
        messages = list(state.get("messages", []) or [])
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return str(msg.content or "").strip()
        return ""

    @staticmethod
    def _infer_city(params: dict[str, Any], entities: dict[str, Any], user_text: str) -> str:
        """Infer destination city from entities, query text, and city hint dictionaries.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            params: Normalized tool parameters after policy correction and validation.
            entities: Structured entities parsed from intent stage output.
            user_text: Input `user_text` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        for key in ("city", "destination", "query"):
            text = str(params.get(key) or entities.get(key) or "").strip()
            if text in CITY_HINTS:
                return text
            for city in EN_CITY_HINTS:
                if text.lower() == city.lower():
                    return city
        for city in CITY_HINTS:
            if city and city in user_text:
                return city
        lowered = (user_text or "").lower()
        for city in EN_CITY_HINTS:
            if re.search(rf"\b{re.escape(city.lower())}\b", lowered):
                return city
        match = re.search(r"([\u4e00-\u9fff]{2,6})(?:市|旅游|旅行|景点|天气)", user_text or "")
        if match:
            return match.group(1)
        english_match = re.search(
            r"\b([A-Za-z][A-Za-z\s]{1,20})(?:\s+(?:travel|trip|weather|hotel|attractions))\b",
            user_text or "",
            flags=re.IGNORECASE,
        )
        if english_match:
            return english_match.group(1).strip()
        return ""

    def _resolve_timeout_seconds(self, step: dict[str, Any], tool_name: str) -> int:
        """Resolve effective timeout for a tool by combining SLA table and runtime config.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            step: Single executable plan step descriptor.
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            int: Result value produced by this routine.
        """
        override = step.get("timeout_seconds")
        if override is not None:
            return max(1, int(override))
        return self._tool_timeout_sla.get(tool_name, self.runtime_config.default_tool_timeout_seconds)

    def _is_tool_circuit_open(self, tool_name: str) -> bool:
        """Return whether a tool is currently blocked by circuit-breaker cooldown.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            bool: Decision flag used by guards, routing, or policy checks.
        """
        if not self.runtime_config.reliability_controls_enabled:
            return False
        item = self._tool_health.get(tool_name)
        if not item:
            return False
        open_until = float(item.get("open_until", 0))
        return time.time() < open_until

    def _mark_tool_failure(self, tool_name: str) -> None:
        """Record tool failure and update circuit-breaker counters.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            None: Result value produced by this routine.
        """
        if not self.runtime_config.reliability_controls_enabled:
            return
        now = time.time()
        health = self._tool_health.setdefault(tool_name, {"consecutive_failures": 0, "open_until": 0})
        health["consecutive_failures"] = int(health.get("consecutive_failures", 0)) + 1
        if health["consecutive_failures"] >= self.runtime_config.circuit_breaker_threshold:
            health["open_until"] = now + self.runtime_config.tool_cooldown_seconds

    def _mark_tool_success(self, tool_name: str) -> None:
        """Record tool success and clear failure counters when recovery is observed.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            None: Result value produced by this routine.
        """
        if not self.runtime_config.reliability_controls_enabled:
            return
        self._tool_health[tool_name] = {"consecutive_failures": 0, "open_until": 0}

    @classmethod
    def get_global_tool_health_snapshot(cls) -> dict[str, Any]:
        """Return global tool health snapshot shared across AgentNodes instances.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
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
        """Normalize plan schema and fill defaults required by executor pipeline.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            plan: Plan step list prepared by planner stage.
        
        Returns:
            list[dict[str, Any]]: Result value produced by this routine.
        """
        normalized: list[dict[str, Any]] = []
        used_step_ids: set[str] = set()
        for idx, raw in enumerate(plan, start=1):
            step_id = str(raw.get("step_id") or f"s{idx}")
            if step_id in used_step_ids:
                step_id = f"{step_id}_{idx}"
            used_step_ids.add(step_id)
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
        """Build human-readable explanation describing how the final plan was formed.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            intent: Input `intent` consumed by this routine.
            plan: Plan step list prepared by planner stage.
        
        Returns:
            str: Result value produced by this routine.
        """
        if not plan:
            return f"intent={intent}, no tool plan required"
        steps = [f"{item['step_id']}:{item['tool']}" for item in plan]
        return f"intent={intent}, plan_steps={len(plan)}, chain={' -> '.join(steps)}"

    @staticmethod
    def _render_reasoning(state: AgentState, tools_used: list[str]) -> str:
        """Render reasoning text shown in UI reasoning panel and streaming events.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            state: Mutable LangGraph state snapshot passed between node stages.
            tools_used: Input `tools_used` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
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
        """Validate tool parameters against safety limits and schema expectations.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool: Tool instance or tool descriptor being processed.
            params: Normalized tool parameters after policy correction and validation.
        
        Returns:
            Optional[str]: Result value produced by this routine.
        """
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
        """Detect potentially unsafe parameter values (prompt injection, secrets, oversized payloads).
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            params: Normalized tool parameters after policy correction and validation.
        
        Returns:
            Optional[str]: Result value produced by this routine.
        """
        def _walk(value: Any) -> list[str]:
            """Walk nested parameter structures when scanning for unsafe payload patterns.
            
            Purpose:
                Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
            
            Args:
                value: Candidate scalar value to normalize/validate.
            
            Returns:
                list[str]: Result value produced by this routine.
            """
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
        """Sanitize tool params before logging to avoid leaking sensitive values.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            params: Normalized tool parameters after policy correction and validation.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        def _sanitize(key: Optional[str], value: Any) -> Any:
            """Mask sensitive values recursively inside nested dict/list payloads.
            
            Purpose:
                Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
            
            Args:
                key: Input `key` consumed by this routine.
                value: Candidate scalar value to normalize/validate.
            
            Returns:
                Any: Result value produced by this routine.
            """
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
        """Build per-run execution summary including success rate and latency distribution.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            stats_steps: Input `stats_steps` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        total_steps = len(stats_steps)
        success_steps = sum(1 for item in stats_steps if item.get("status") == "success")
        failed_steps = sum(1 for item in stats_steps if item.get("status") == "failed")
        blocked_steps = sum(1 for item in stats_steps if item.get("status") == "blocked")
        timeout_steps = sum(1 for item in stats_steps if item.get("error_code") == "TOOL_TIMEOUT")
        fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))
        stale_result_count = sum(1 for item in stats_steps if bool(item.get("is_stale", False)))
        duration_values = [int(item.get("duration_ms", 0) or 0) for item in stats_steps]
        avg_duration = int(sum(duration_values) / total_steps) if total_steps else 0
        success_rate = (success_steps / total_steps) if total_steps else 0.0
        fallback_rate = (fallback_steps / total_steps) if total_steps else 0.0

        retry_histogram: dict[str, int] = {}
        error_code_distribution: dict[str, int] = {}
        provider_usage_distribution: dict[str, int] = {}
        for item in stats_steps:
            attempt = int(item.get("attempt", 1) or 1)
            retry_histogram[str(attempt)] = retry_histogram.get(str(attempt), 0) + 1

            error_code = item.get("error_code")
            if error_code:
                key = str(error_code)
                error_code_distribution[key] = error_code_distribution.get(key, 0) + 1

            provider_used = item.get("provider_used")
            if provider_used:
                key = str(provider_used)
                provider_usage_distribution[key] = provider_usage_distribution.get(key, 0) + 1

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

        latency_percentiles_ms = {
            "p50": AgentNodes._percentile(duration_values, 50),
            "p95": AgentNodes._percentile(duration_values, 95),
            "p99": AgentNodes._percentile(duration_values, 99),
        }

        return {
            "total_steps": total_steps,
            "success_steps": success_steps,
            "failed_steps": failed_steps,
            "blocked_steps": blocked_steps,
            "timeout_steps": timeout_steps,
            "fallback_steps": fallback_steps,
            "stale_result_count": stale_result_count,
            "success_rate": round(success_rate, 4),
            "tool_hit_rate": round(success_rate, 4),
            "fallback_rate": round(fallback_rate, 4),
            "avg_duration_ms": avg_duration,
            "latency_percentiles_ms": latency_percentiles_ms,
            "retry_histogram": retry_histogram,
            "error_code_distribution": error_code_distribution,
            "provider_usage_distribution": provider_usage_distribution,
            "tool_metrics": tool_metrics,
        }

    @staticmethod
    def _percentile(values: list[int], percentile: int) -> int:
        """Compute percentile value for latency samples used in execution summary.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            values: Input `values` consumed by this routine.
            percentile: Input `percentile` consumed by this routine.
        
        Returns:
            int: Result value produced by this routine.
        """
        if not values:
            return 0
        sorted_values = sorted(values)
        if percentile <= 0:
            return sorted_values[0]
        if percentile >= 100:
            return sorted_values[-1]
        rank = int(round((percentile / 100) * (len(sorted_values) - 1)))
        return sorted_values[rank]

    def _attach_execution_metadata(self, result: ExecutionResult, tool_name: str) -> None:
        """Attach normalized execution metadata to state for API diagnostics output.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            result: Tool output payload or normalized intermediate result.
            tool_name: Registered tool identifier from the tool map.
        
        Returns:
            None: Result value produced by this routine.
        """
        profile = self._tool_source_profile.get(
            tool_name,
            {"source": f"tool:{tool_name}", "ttl_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS * 30},
        )
        result.source = str(profile.get("source", f"tool:{tool_name}"))
        result.ttl_seconds = int(profile.get("ttl_seconds", DEFAULT_TOOL_TIMEOUT_SECONDS * 30))
        result.fetched_at = datetime.now().isoformat()
        result.is_stale = False
        result.refresh_attempted = bool(result.refresh_attempted)
        result.refresh_success = bool(result.refresh_success)
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
            if result_meta.get("refresh_attempted") is not None:
                result.refresh_attempted = bool(result_meta.get("refresh_attempted"))
            if result_meta.get("refresh_success") is not None:
                result.refresh_success = bool(result_meta.get("refresh_success"))
        if result.refresh_attempted and result.success and not result.refresh_success:
            result.refresh_success = not bool(result.is_stale)
        if result.refresh_attempted and not result.success:
            result.refresh_success = False
        if not result.success:
            result.fallback_suggestion = self._build_fallback_suggestion(
                tool_name=tool_name,
                error_code=result.error_code,
            )
        elif result.refresh_attempted and not result.refresh_success:
            result.fallback_suggestion = "已尝试刷新实时数据但未成功，当前结果可能仍过期，建议谨慎参考"
        elif result.is_stale:
            result.fallback_suggestion = "数据可能已过期，建议刷新实时数据后再确认关键决策"

    @staticmethod
    def _extract_result_meta(result_payload: Any) -> dict[str, Any]:
        """Extract source/freshness/provider metadata from raw tool results.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            result_payload: Input `result_payload` consumed by this routine.
        
        Returns:
            dict[str, Any]: Result value produced by this routine.
        """
        if not isinstance(result_payload, dict):
            return {}
        raw_meta = result_payload.get("_meta") or result_payload.get("meta")
        if not isinstance(raw_meta, dict):
            return {}
        return raw_meta

    @staticmethod
    def _build_fallback_suggestion(tool_name: str, error_code: Optional[str]) -> str:
        """Build user-facing fallback suggestion when tool execution fails.
        
        Purpose:
            Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
        
        Args:
            tool_name: Registered tool identifier from the tool map.
            error_code: Input `error_code` consumed by this routine.
        
        Returns:
            str: Result value produced by this routine.
        """
        if error_code == "TOOL_TIMEOUT":
            return f"{tool_name} 超时，建议使用缓存信息或提供不依赖实时数据的备选方案"
        if error_code == "CIRCUIT_OPEN":
            return f"{tool_name} 当前不可用，建议切换备用数据源"
        if error_code in {"TOOL_NOT_FOUND", "TOOL_NOT_REGISTERED"}:
            return "工具配置缺失，建议使用无需工具的保守回答并提示用户补充信息"
        if error_code == "PARAM_VALIDATION_ERROR":
            return "请求参数不完整，建议向用户澄清并补充信息后重试"
        if error_code == "UNSAFE_TOOL_INPUT":
            return "输入触发安全策略，建议清理高风险指令后再执行"
        return f"{tool_name} 执行失败，建议降级为规则模板回答并标注不确定性"


def create_nodes(llm: Runnable, tools: list[Tool]) -> AgentNodes:
    """Factory helper that builds AgentNodes with default runtime wiring.
    
    Purpose:
        Clarify stage responsibilities and data contracts to reduce maintenance risk in complex backend flows.
    
    Args:
        llm: Input `llm` consumed by this routine.
        tools: Input `tools` consumed by this routine.
    
    Returns:
        AgentNodes: Result value produced by this routine.
    """
    return AgentNodes(llm, tools)
