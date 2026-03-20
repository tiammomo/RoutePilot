"""Artifact builders for structured trip-plan payloads."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a shallow dictionary view for loose runtime payloads."""
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return a list view for loose runtime payloads."""
    return list(value) if isinstance(value, list) else []


def _coerce_text(value: Any, default: str = "") -> str:
    """Normalize optional runtime values into a string."""
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _coerce_optional_text(value: Any) -> str | None:
    """Normalize optional runtime values into text or ``None``."""
    text = _coerce_text(value)
    return text or None


def _coerce_int(value: Any, default: int = 0) -> int:
    """Normalize a loose numeric value into an integer."""
    try:
        return int(value)
    except Exception:
        return default


def _copy_value(value: Any) -> Any:
    """Return a recursive copy made only from builtin containers."""
    if isinstance(value, dict):
        return {key: _copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    return value


def _with_aliases(base: dict[str, Any], **aliases: str) -> dict[str, Any]:
    """Attach camelCase and snake_case aliases for frontend/backend compatibility."""
    payload = {key: _copy_value(value) for key, value in base.items()}
    for alias, source in aliases.items():
        if source in payload:
            payload[alias] = _copy_value(payload[source])
    return payload


def _extract_destinations(intent_entities: dict[str, Any]) -> list[str]:
    """Derive destination names from intent entities when available."""
    destinations: list[str] = []
    for key in ("city", "destination"):
        value = intent_entities.get(key)
        if isinstance(value, str) and value.strip():
            destinations.append(value.strip())
    values = intent_entities.get("destinations")
    if isinstance(values, list):
        for item in values:
            if isinstance(item, str) and item.strip():
                destinations.append(item.strip())

    deduped: list[str] = []
    for item in destinations:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _build_research_evidence_from_results(
    tool_results: dict[str, Any],
    user_message: str,
) -> list[dict[str, Any]]:
    """Build research evidence entries from tool-result maps."""
    evidence: list[dict[str, Any]] = []
    for tool_name, result in tool_results.items():
        result_dict = _as_dict(result)
        status = "collected" if result_dict.get("success") is not False else "failed"
        entry = {
            "tool": tool_name,
            "status": status,
            "query": user_message,
        }
        if result_dict:
            entry["result"] = _copy_value(result_dict)
        evidence.append(entry)
    return evidence


def _build_research_summary(evidence: list[dict[str, Any]], intent_name: str) -> str:
    """Build a short research summary for artifact-first payloads."""
    if not evidence:
        return ""
    return f"Collected {len(evidence)} research signal(s) for intent={intent_name}."


def _count_stale_results(tool_results: dict[str, Any]) -> int:
    """Count stale tool responses inside a tool-result map."""
    return sum(
        1
        for result in tool_results.values()
        if isinstance(result, dict) and bool(result.get("success")) and bool(result.get("is_stale"))
    )


def _build_refresh_targets(tool_results: dict[str, Any]) -> list[str]:
    """Return tool names that should be refreshed based on stale results."""
    targets = [
        tool_name
        for tool_name, result in tool_results.items()
        if isinstance(result, dict) and bool(result.get("success")) and bool(result.get("is_stale"))
    ]
    return list(dict.fromkeys(targets))


def _build_verification_summary(
    *,
    passed: bool | None,
    should_retry: bool,
    stale_result_count: int,
    issues: list[Any],
    preview_mode: bool = False,
) -> str:
    """Build a compact verification summary string."""
    if preview_mode:
        return "preview_not_executed"
    if passed is False:
        return "verification_failed" if issues else "verification_requires_follow_up"
    if stale_result_count > 0:
        return "verification_with_stale_results"
    if should_retry:
        return "verification_retry_suggested"
    if passed is True:
        return "verification_passed"
    return ""


def create_empty_trip_plan_artifact() -> dict[str, Any]:
    """Create the default artifact skeleton used by the runtime."""
    return {
        "intent": {
            "name": "general",
            "confidence": None,
            "entities": {},
            "detail": {},
        },
        "research": _with_aliases(
            {
                "summary": "",
                "evidence": [],
                "destinations": [],
                "source_tools": [],
            },
            sourceTools="source_tools",
        ),
        "itinerary": _with_aliases(
            {
                "plan_id": None,
                "explanation": "",
                "steps": [],
                "validation_status": "pass",
                "validation_errors": [],
            },
            planId="plan_id",
            validationStatus="validation_status",
            validationErrors="validation_errors",
        ),
        "budget": _with_aliases(
            {
                "summary": {},
                "execution_budget": {},
                "stale_result_count": 0,
                "fallback_steps": 0,
            },
            executionBudget="execution_budget",
            staleResultCount="stale_result_count",
            fallbackSteps="fallback_steps",
        ),
        "verification": _with_aliases(
            {
                "passed": None,
                "should_retry": False,
                "issues": [],
                "refresh_targets": [],
                "summary": "",
            },
            shouldRetry="should_retry",
            refreshTargets="refresh_targets",
        ),
        "answer": "",
        "reasoning": "",
        "tools_used": [],
        "toolsUsed": [],
        "metadata": {},
    }


def build_trip_plan_artifact_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Build a structured artifact from the current graph/runtime state."""
    raw_state = _as_dict(state)
    artifact = create_empty_trip_plan_artifact()

    intent_detail = _as_dict(raw_state.get("intent_detail"))
    intent_entities = _as_dict(intent_detail.get("entities"))
    tool_results = _as_dict(raw_state.get("tool_results"))
    tools_used = [str(item) for item in _as_list(raw_state.get("tools_used")) if str(item).strip()]
    evidence = _build_research_evidence_from_results(
        tool_results,
        user_message=_coerce_text(raw_state.get("user_message")),
    )
    stale_result_count = _coerce_int(
        raw_state.get("stale_result_count"),
        _coerce_int(raw_state.get("execution_summary", {}).get("stale_result_count"), _count_stale_results(tool_results))
        if isinstance(raw_state.get("execution_summary"), dict)
        else _count_stale_results(tool_results),
    )
    fallback_steps = _coerce_int(
        raw_state.get("fallback_steps"),
        _coerce_int(_as_dict(raw_state.get("execution_summary")).get("fallback_steps")),
    )
    verify_result = _as_dict(raw_state.get("verify_result"))
    passed_raw = verify_result.get("passed", raw_state.get("verification_passed"))
    passed = bool(passed_raw) if isinstance(passed_raw, bool) else None
    issues = _as_list(verify_result.get("issues"))
    should_retry = bool(verify_result.get("should_retry", False))
    refresh_targets = [
        str(item)
        for item in _as_list(verify_result.get("refresh_targets"))
        if str(item).strip()
    ] or _build_refresh_targets(tool_results)

    artifact["intent"] = {
        "name": _coerce_text(raw_state.get("intent"), "general"),
        "confidence": intent_detail.get("confidence"),
        "entities": _copy_value(intent_entities),
        "detail": _copy_value(intent_detail),
    }
    artifact["research"] = _with_aliases(
        {
            "summary": _build_research_summary(evidence, artifact["intent"]["name"]),
            "evidence": evidence,
            "destinations": _extract_destinations(intent_entities),
            "source_tools": list(dict.fromkeys(tools_used)),
        },
        sourceTools="source_tools",
    )
    artifact["itinerary"] = _with_aliases(
        {
            "plan_id": _coerce_optional_text(raw_state.get("plan_id")),
            "explanation": _coerce_text(raw_state.get("plan_explanation")),
            "steps": _copy_value(_as_list(raw_state.get("plan"))),
            "validation_status": _coerce_text(raw_state.get("validation_status"), "pass"),
            "validation_errors": _copy_value(_as_list(raw_state.get("validation_errors"))),
        },
        planId="plan_id",
        validationStatus="validation_status",
        validationErrors="validation_errors",
    )
    artifact["budget"] = _with_aliases(
        {
            "summary": _copy_value(_as_dict(raw_state.get("execution_summary"))),
            "execution_budget": _copy_value(_as_dict(raw_state.get("execution_budget"))),
            "stale_result_count": stale_result_count,
            "fallback_steps": fallback_steps,
        },
        executionBudget="execution_budget",
        staleResultCount="stale_result_count",
        fallbackSteps="fallback_steps",
    )
    artifact["verification"] = _with_aliases(
        {
            "passed": passed,
            "should_retry": should_retry,
            "issues": _copy_value(issues),
            "refresh_targets": refresh_targets,
            "summary": _build_verification_summary(
                passed=passed,
                should_retry=should_retry,
                stale_result_count=stale_result_count,
                issues=issues,
            ),
        },
        shouldRetry="should_retry",
        refreshTargets="refresh_targets",
    )
    artifact["answer"] = _coerce_text(raw_state.get("answer"))
    artifact["reasoning"] = _coerce_text(raw_state.get("reasoning"))
    artifact["tools_used"] = list(dict.fromkeys(tools_used))
    artifact["toolsUsed"] = _copy_value(artifact["tools_used"])
    artifact["metadata"] = _with_aliases(
        {
            "phase": _coerce_text(raw_state.get("phase"), "runtime_state"),
            "session_id": _coerce_optional_text(raw_state.get("session_id")),
            "run_id": _coerce_optional_text(raw_state.get("run_id")),
            "strategy": _coerce_optional_text(raw_state.get("strategy")),
            "routing": _coerce_optional_text(raw_state.get("routing")),
            "current_step": raw_state.get("current_step"),
            "execution_round": raw_state.get("execution_round"),
            "chat_mode": _coerce_optional_text(raw_state.get("chat_mode")),
        },
        sessionId="session_id",
        runId="run_id",
        currentStep="current_step",
        executionRound="execution_round",
        chatMode="chat_mode",
    )
    return artifact


def build_trip_plan_artifact_from_plan_preview(
    preview: dict[str, Any],
    *,
    user_message: str,
    session_id: str,
) -> dict[str, Any]:
    """Build a structured artifact from a plan-preview payload."""
    raw_preview = _as_dict(preview)
    artifact = create_empty_trip_plan_artifact()

    artifact["intent"] = {
        "name": _coerce_text(raw_preview.get("intent"), "general"),
        "confidence": _as_dict(raw_preview.get("intent_detail")).get("confidence"),
        "entities": _copy_value(_as_dict(_as_dict(raw_preview.get("intent_detail")).get("entities"))),
        "detail": _copy_value(_as_dict(raw_preview.get("intent_detail"))),
    }
    artifact["research"] = _with_aliases(
        {
            "summary": "",
            "evidence": [],
            "destinations": _extract_destinations(artifact["intent"]["entities"]),
            "source_tools": [],
        },
        sourceTools="source_tools",
    )
    artifact["itinerary"] = _with_aliases(
        {
            "plan_id": _coerce_optional_text(raw_preview.get("plan_id")),
            "explanation": _coerce_text(raw_preview.get("plan_explanation")),
            "steps": _copy_value(_as_list(raw_preview.get("plan"))),
            "validation_status": _coerce_text(raw_preview.get("validation_status"), "pass"),
            "validation_errors": _copy_value(_as_list(raw_preview.get("validation_errors"))),
        },
        planId="plan_id",
        validationStatus="validation_status",
        validationErrors="validation_errors",
    )
    artifact["budget"] = _with_aliases(
        {
            "summary": {},
            "execution_budget": {},
            "stale_result_count": 0,
            "fallback_steps": 0,
        },
        executionBudget="execution_budget",
        staleResultCount="stale_result_count",
        fallbackSteps="fallback_steps",
    )
    artifact["verification"] = _with_aliases(
        {
            "passed": None,
            "should_retry": False,
            "issues": [],
            "refresh_targets": [],
            "summary": _build_verification_summary(
                passed=None,
                should_retry=False,
                stale_result_count=0,
                issues=[],
                preview_mode=True,
            ),
        },
        shouldRetry="should_retry",
        refreshTargets="refresh_targets",
    )
    artifact["answer"] = ""
    artifact["reasoning"] = ""
    artifact["tools_used"] = []
    artifact["toolsUsed"] = []
    artifact["metadata"] = _with_aliases(
        {
            "phase": "plan_preview",
            "session_id": session_id,
            "user_message": user_message,
            "plan_preview": True,
        },
        sessionId="session_id",
        userMessage="user_message",
    )
    return artifact


def build_trip_plan_artifact_from_stream_event(
    event: dict[str, Any],
    *,
    user_message: str,
    session_id: str,
    chat_mode: str | None,
) -> dict[str, Any]:
    """Build a structured artifact from the runtime ``done`` stream event."""
    raw_event = _as_dict(event)
    state = {
        "intent": raw_event.get("intent"),
        "intent_detail": raw_event.get("intent_detail"),
        "plan_id": raw_event.get("plan_id"),
        "plan_explanation": user_message,
        "plan": raw_event.get("plan", []),
        "validation_status": raw_event.get("validation_status", "pass"),
        "validation_errors": raw_event.get("validation_errors", []),
        "verify_result": {
            "passed": raw_event.get("verification_passed"),
            "should_retry": False,
            "issues": raw_event.get("verification_issues", []),
            "refresh_targets": raw_event.get("refresh_targets", []),
        },
        "execution_summary": {
            "fallback_steps": raw_event.get("fallback_steps", 0),
        },
        "execution_budget": raw_event.get("execution_budget", {}),
        "tool_results": raw_event.get("tool_results", {}),
        "answer": raw_event.get("answer", ""),
        "reasoning": raw_event.get("reasoning", ""),
        "tools_used": raw_event.get("tools_used", []),
        "session_id": session_id,
        "run_id": raw_event.get("run_id"),
        "strategy": raw_event.get("strategy") or raw_event.get("intent"),
        "routing": chat_mode or raw_event.get("routing"),
        "chat_mode": chat_mode,
        "phase": "stream_done",
        "stale_result_count": raw_event.get("stale_result_count", 0),
        "fallback_steps": raw_event.get("fallback_steps", 0),
    }
    artifact = build_trip_plan_artifact_from_state(state)
    metadata = _as_dict(artifact.get("metadata"))
    metadata["stream_event_type"] = _coerce_text(raw_event.get("type"), "done")
    artifact["metadata"] = metadata
    return artifact


__all__ = [
    "build_trip_plan_artifact_from_plan_preview",
    "build_trip_plan_artifact_from_state",
    "build_trip_plan_artifact_from_stream_event",
    "create_empty_trip_plan_artifact",
]
