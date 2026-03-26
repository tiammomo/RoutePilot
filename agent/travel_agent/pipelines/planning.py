"""Planning pipeline extracted from graph nodes to reduce orchestration hot spots."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_DAY_COUNT = 3
DEFAULT_PEOPLE_COUNT = 1


class PlanningPipeline:
    """Build and validate execution plans independently from the graph node shell."""

    def __init__(
        self,
        *,
        runtime_config: Any,
        tool_names: set[str],
        planner_hooks: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]],
        stage_output_model: type[BaseModel],
        validate_stage_output: Callable[[type[BaseModel], dict[str, Any]], dict[str, Any]],
        build_execution_summary: Callable[[list[dict[str, Any]]], dict[str, Any]],
        validation_result_builder: Callable[..., dict[str, Any]],
        step_signature: Callable[[str, dict[str, Any]], str],
    ) -> None:
        """Store collaborators required to build one planning-stage state patch."""
        self.runtime_config = runtime_config
        self.tool_names = tool_names
        self.planner_hooks = planner_hooks
        self.stage_output_model = stage_output_model
        self.validate_stage_output = validate_stage_output
        self.build_execution_summary = build_execution_summary
        self.validation_result_builder = validation_result_builder
        self.step_signature = step_signature

    def build(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Build the validated planning-stage state patch for one graph turn."""
        logger.info("[Planning Pipeline] Building execution plan...")

        intent = str(state.get("intent", "general") or "general")
        intent_detail = self._as_dict(state.get("intent_detail"))
        entities = self._as_dict(intent_detail.get("entities"))
        strategy_detail = self._as_dict(state.get("strategy_detail"))
        primary_intent = str(strategy_detail.get("primary_intent") or intent or "general")
        secondary_intent = strategy_detail.get("secondary_intent")
        required_tools = self._as_text_list(strategy_detail.get("required_tools"))
        optional_tools = self._as_text_list(strategy_detail.get("optional_tools"))

        planner_hook = self.planner_hooks.get(primary_intent) or self.planner_hooks.get(intent)
        used_planner_hook = planner_hook is not None
        if planner_hook is not None:
            try:
                plan = planner_hook(entities)
            except Exception as exc:
                logger.warning("[Planning Pipeline] Planner hook failed (intent=%s): %s", intent, exc)
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
                "[Planning Pipeline] Plan truncated from %d to %d by AGENT_MAX_PLAN_STEPS",
                len(normalized_plan),
                self.runtime_config.max_plan_steps,
            )
            normalized_plan = normalized_plan[: self.runtime_config.max_plan_steps]

        validation_status, validation_errors = self._validate_plan_steps(normalized_plan)
        validation_blocked = [
            str(item.get("step_id"))
            for item in validation_errors
            if item.get("code") == "TOOL_NOT_REGISTERED"
        ]
        stats_steps = self._build_plan_validation_stats(normalized_plan, validation_errors)
        tool_results = self._build_plan_validation_tool_results(validation_errors)
        plan_id = f"plan-{uuid.uuid4().hex[:12]}"
        logger.info("[Planning Pipeline] Plan created with %d steps (plan_id=%s)", len(normalized_plan), plan_id)

        return self.validate_stage_output(
            self.stage_output_model,
            {
                "plan_id": plan_id,
                "plan_explanation": self._build_plan_explanation(intent, normalized_plan),
                "plan": normalized_plan,
                "validation_status": validation_status,
                "validation_errors": validation_errors,
                "current_step": 0,
                "execution_round": 0,
                "execution_state": {"completed": [], "failed": [], "blocked": sorted(validation_blocked)},
                "execution_stats": {"plan_id": plan_id, "started_at": self._timestamp(), "steps": stats_steps},
                "execution_summary": self.build_execution_summary(stats_steps),
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

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        """Coerce optional mapping-like values into a plain dict."""
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_text_list(value: Any) -> list[str]:
        """Normalize list-like values into a list of non-empty strings."""
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _timestamp() -> str:
        """Return an ISO timestamp for planning-stage bookkeeping."""
        return datetime.now().isoformat()

    def _default_plan(self, intent: str, entities: dict[str, Any]) -> list[dict[str, Any]]:
        """Build a fallback tool plan when no specialized planner hook is available."""
        if intent == "recommend":
            return [
                {
                    "step": 1,
                    "step_id": "s1",
                    "tool": "search_cities",
                    "params": {"query": entities.get("query", "")},
                    "description": "查询候选目的地",
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
                    "params": {"city": entities.get("city", ""), "days": entities.get("days", DEFAULT_DAY_COUNT)},
                    "description": "查询天气情况",
                    "depends_on": [],
                },
                {
                    "step": 3,
                    "step_id": "s3",
                    "tool": "plan_itinerary",
                    "params": {
                        "destination": entities.get("city", ""),
                        "days": entities.get("days", DEFAULT_DAY_COUNT),
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
                        "days": entities.get("days", DEFAULT_DAY_COUNT),
                        "people": entities.get("people", DEFAULT_PEOPLE_COUNT),
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
        """Append only non-duplicate secondary steps onto the primary plan."""
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
        *,
        plan: list[dict[str, Any]],
        required_tools: list[str],
        optional_tools: list[str],
        entities: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Inject required and optional tool steps that are missing from the plan."""
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

        if len(merged) <= 2:
            for tool_name in optional_tools:
                if tool_name in existing_tools:
                    continue
                step = self._default_step_for_tool(
                    step_num=next_step,
                    tool_name=tool_name,
                    entities=entities,
                    required=False,
                )
                if step:
                    merged.append(step)
                    existing_tools.add(tool_name)
                    next_step += 1
                if len(merged) >= self.runtime_config.max_plan_steps:
                    break

        return merged

    @staticmethod
    def _default_step_for_tool(
        *,
        step_num: int,
        tool_name: str,
        entities: dict[str, Any],
        required: bool,
    ) -> Optional[dict[str, Any]]:
        """Build one synthetic planning step for a required or optional tool."""
        city = entities.get("city") or entities.get("destination") or "北京"
        days = entities.get("days", DEFAULT_DAY_COUNT)
        mapping: dict[str, dict[str, Any]] = {
            "search_cities": {"params": {"query": entities.get("query") or city}, "description": "补全候选目的地"},
            "query_attractions": {"params": {"city": city, "category": entities.get("category")}, "description": "补全景点信息"},
            "query_hotels": {"params": {"city": city}, "description": "补全酒店信息"},
            "get_weather": {"params": {"city": city, "days": days}, "description": "补全天气信息"},
            "plan_itinerary": {
                "params": {"destination": city, "days": days, "interests": entities.get("interests")},
                "description": "补全行程规划",
            },
            "calculate_budget": {
                "params": {
                    "destination": city,
                    "days": days,
                    "people": entities.get("people", DEFAULT_PEOPLE_COUNT),
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

    def _validate_plan_steps(
        self,
        plan: list[dict[str, Any]],
    ) -> tuple[Literal["pass", "warn", "fail"], list[dict[str, Any]]]:
        """Validate tool references and classify the overall plan status."""
        errors: list[dict[str, Any]] = []
        for step in plan:
            tool_name = str(step.get("tool") or "").strip()
            if not tool_name or tool_name not in self.tool_names:
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
        """Build blocked-step execution stats rows for validation failures."""
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
            timestamp = self._timestamp()
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
                    "started_at": timestamp,
                    "ended_at": timestamp,
                    "duration_ms": 0,
                    "signature": self.step_signature(str(step.get("tool") or ""), dict(step.get("params", {}) or {})),
                }
            )
        return stats_steps

    def _build_plan_validation_tool_results(self, errors: list[dict[str, Any]]) -> dict[str, Any]:
        """Build synthetic tool-result payloads for plan validation errors."""
        results: dict[str, Any] = {}
        for item in errors:
            step_id = str(item.get("step_id") or "")
            tool_name = str(item.get("tool") or "")
            code = str(item.get("code") or "PLAN_VALIDATION_ERROR")
            timestamp = self._timestamp()
            results[f"{step_id}:{tool_name}"] = self.validation_result_builder(
                tool_name=tool_name,
                code=code,
                message=str(item.get("message") or code),
                timestamp=timestamp,
            )
        return results

    def _normalize_plan(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize ids, defaults, and retry settings for public plan payloads."""
        normalized: list[dict[str, Any]] = []
        used_step_ids: set[str] = set()
        for idx, raw in enumerate(plan, start=1):
            step_id = str(raw.get("step_id") or f"s{idx}")
            if step_id in used_step_ids:
                step_id = f"{step_id}_{idx}"
            used_step_ids.add(step_id)
            normalized.append(
                {
                    "step": int(raw.get("step", idx)),
                    "step_id": step_id,
                    "tool": raw.get("tool", ""),
                    "params": raw.get("params", {}),
                    "depends_on": list(raw.get("depends_on", [])),
                    "description": raw.get("description", ""),
                    "timeout_seconds": raw.get("timeout_seconds"),
                    "max_retries": raw.get("max_retries", self.runtime_config.default_tool_max_retries),
                }
            )
        return normalized

    @staticmethod
    def _build_plan_explanation(intent: str, plan: list[dict[str, Any]]) -> str:
        """Summarize the generated plan in one log-friendly explanation string."""
        if not plan:
            return f"intent={intent}, no tool plan required"
        steps = [f"{item['step_id']}:{item['tool']}" for item in plan]
        return f"intent={intent}, plan_steps={len(plan)}, chain={' -> '.join(steps)}"
__all__ = ["PlanningPipeline"]
