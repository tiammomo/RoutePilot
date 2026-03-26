"""Export deterministic frontend chat-runtime golden fixture from SSE stream baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "tests" / "golden" / "chat_stream_golden_fixture.json"
DEFAULT_OUTPUT = ROOT / "tests" / "golden" / "frontend_chat_runtime_golden_fixture.json"

ARRAY_EVENT_KEYS = {
    "artifact_patch": "artifact_patches",
    "chunk": "answer_chunks",
    "reasoning_chunk": "reasoning_chunks",
    "stage": "stages",
    "subagent_end": "subagent_ends",
    "subagent_start": "subagent_starts",
    "tool_end": "tool_ends",
    "tool_start": "tool_starts",
}

SINGLE_EVENT_KEYS = {
    "done": "done",
    "metadata": "metadata",
    "plan_preview": "plan_preview",
    "session_id": "session_id",
}


def _clone_payload(value: Any) -> Any:
    """Deep-clone JSON-compatible payloads via serialization round-trip."""
    return json.loads(json.dumps(value))


def _create_empty_trip_plan_artifact() -> dict[str, Any]:
    """Build the empty artifact shape used before any streamed patches arrive."""
    return {
        "intent": {
            "name": "general",
            "confidence": None,
            "entities": {},
            "detail": {},
        },
        "research": {
            "summary": "",
            "evidence": [],
            "destinations": [],
            "sourceTools": [],
        },
        "itinerary": {
            "planId": None,
            "explanation": "",
            "steps": [],
            "validationStatus": "pass",
            "validationErrors": [],
        },
        "budget": {
            "summary": {},
            "executionBudget": {},
            "staleResultCount": 0,
            "fallbackSteps": 0,
        },
        "verification": {
            "passed": None,
            "shouldRetry": False,
            "issues": [],
            "refreshTargets": [],
            "summary": "",
        },
        "answer": "",
        "reasoning": "",
        "toolsUsed": [],
        "metadata": {},
    }


def _merge_records(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge nested record payloads while cloning leaf values."""
    merged = dict(target)
    for key, value in patch.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_records(current, value)
            continue
        merged[key] = _clone_payload(value)
    return merged


def _merge_trip_plan_artifact(base_artifact: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any] | None:
    """Merge one artifact patch into the accumulated trip-plan artifact."""
    if patch is None:
        return _clone_payload(base_artifact) if base_artifact else None
    next_base = _clone_payload(base_artifact) if base_artifact else _create_empty_trip_plan_artifact()
    return _merge_records(next_base, patch)


def _build_final_reasoning(reasoning: str, timestamp: str | None) -> str:
    """Prefix reasoning text with its terminal timestamp when one is available."""
    if not timestamp:
        return reasoning
    return f"[Timestamp: {timestamp}]\n\n{reasoning}"


def _build_completion_diagnostics(
    *,
    artifact: dict[str, Any] | None,
    completion: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    subagent_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Assemble the final diagnostics payload consumed by the frontend replay."""
    if not metadata and not artifact and not subagent_events:
        return None

    artifact_budget = artifact.get("budget", {}) if isinstance(artifact, dict) else {}
    artifact_itinerary = artifact.get("itinerary", {}) if isinstance(artifact, dict) else {}
    artifact_verification = artifact.get("verification", {}) if isinstance(artifact, dict) else {}
    artifact_tools = artifact.get("toolsUsed", []) if isinstance(artifact, dict) else []

    return {
        "toolsUsed": list(metadata.get("toolsUsed", artifact_tools) if metadata else artifact_tools),
        "verificationPassed": metadata.get("verificationPassed") if metadata and "verificationPassed" in metadata else artifact_verification.get("passed"),
        "staleResultCount": metadata.get("staleResultCount") if metadata and "staleResultCount" in metadata else artifact_budget.get("staleResultCount", 0),
        "fallbackSteps": metadata.get("fallbackSteps") if metadata and "fallbackSteps" in metadata else artifact_budget.get("fallbackSteps", 0),
        "planId": metadata.get("planId") if metadata and metadata.get("planId") is not None else artifact_itinerary.get("planId"),
        "executionStats": metadata.get("executionStats") if metadata and metadata.get("executionStats") is not None else artifact_budget.get("summary"),
        "artifact": artifact,
        "subagentEvents": subagent_events,
        "runId": (completion or {}).get("runId") or (metadata or {}).get("runId"),
        "requestId": (completion or {}).get("requestId") or (metadata or {}).get("requestId"),
        "traceId": (completion or {}).get("traceId") or (metadata or {}).get("traceId"),
    }


def _string_array(value: Any) -> list[str]:
    """Normalize array payloads into a list of strings."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _record_array(value: Any) -> list[dict[str, Any]]:
    """Normalize array payloads into a list of dict records."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unknown_array(value: Any) -> list[Any]:
    """Normalize array payloads while preserving item types."""
    return list(value) if isinstance(value, list) else []


def _normalize_plan_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert one plan preview event into the frontend replay shape."""
    return {
        "planId": payload.get("plan_id") if isinstance(payload.get("plan_id"), str) else None,
        "intent": payload.get("intent") if isinstance(payload.get("intent"), str) else None,
        "explanation": payload.get("explanation") if isinstance(payload.get("explanation"), str) else None,
        "validationStatus": payload.get("validation_status") if isinstance(payload.get("validation_status"), str) else None,
        "validationErrors": _unknown_array(payload.get("validation_errors")),
        "steps": _record_array(payload.get("steps")),
        "artifact": payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None,
        "artifactPatch": payload.get("artifact_patch") if isinstance(payload.get("artifact_patch"), dict) else None,
        "subagent": payload.get("subagent") if isinstance(payload.get("subagent"), str) else None,
        "skills": _string_array(payload.get("skills")),
    }


def _normalize_stage(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert one stage event into the frontend replay shape."""
    return {
        "stage": payload.get("stage") if isinstance(payload.get("stage"), str) else None,
        "label": payload.get("label") if isinstance(payload.get("label"), str) else None,
        "progress": float(payload["progress"]) if payload.get("progress") is not None else None,
        "subagent": payload.get("subagent") if isinstance(payload.get("subagent"), str) else None,
    }


def _normalize_subagent_start(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert one subagent-start event into the frontend replay shape."""
    return {
        "subagent": payload.get("subagent"),
        "description": payload.get("description") if isinstance(payload.get("description"), str) else None,
        "skills": _string_array(payload.get("skills")),
        "toolNames": _string_array(payload.get("tool_names")),
        "sequence": int(payload["sequence"]) if payload.get("sequence") is not None else None,
        "trigger": payload.get("trigger") if isinstance(payload.get("trigger"), str) else None,
    }


def _normalize_subagent_end(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert one subagent-end event into the frontend replay shape."""
    return {
        "subagent": payload.get("subagent"),
        "sequence": int(payload["sequence"]) if payload.get("sequence") is not None else None,
        "status": payload.get("status") if isinstance(payload.get("status"), str) else None,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), str) else None,
    }


def _normalize_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert terminal metadata events into the frontend replay shape."""
    return {
        "totalSteps": int(payload.get("total_steps") or 0),
        "toolsUsed": _string_array(payload.get("tools_used")),
        "hasReasoning": bool(payload.get("has_reasoning")),
        "reasoningLength": int(payload.get("reasoning_length") or 0),
        "answerLength": int(payload.get("answer_length") or 0),
        "verificationPassed": None if payload.get("verification_passed") is None else bool(payload.get("verification_passed")),
        "staleResultCount": int(payload.get("stale_result_count") or 0),
        "fallbackSteps": int(payload.get("fallback_steps") or 0),
        "planId": payload.get("plan_id") if isinstance(payload.get("plan_id"), str) else None,
        "executionStats": payload.get("execution_stats") if isinstance(payload.get("execution_stats"), dict) else None,
        "runId": payload.get("run_id") if isinstance(payload.get("run_id"), str) else "",
        "requestId": payload.get("request_id") if isinstance(payload.get("request_id"), str) else "",
        "traceId": payload.get("trace_id") if isinstance(payload.get("trace_id"), str) else "",
        "artifact": payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None,
    }


def _normalize_completion(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert one done event into the frontend replay completion shape."""
    return {
        "artifact": payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None,
        "runId": payload.get("run_id") if isinstance(payload.get("run_id"), str) else "",
        "requestId": payload.get("request_id") if isinstance(payload.get("request_id"), str) else "",
        "traceId": payload.get("trace_id") if isinstance(payload.get("trace_id"), str) else "",
    }


def _build_replay_events(mode_fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """Replay event_sequence entries against keyed payload fixtures."""
    key_events = mode_fixture.get("key_events", {})
    array_queues: dict[str, list[dict[str, Any]]] = {}
    used_singles: set[str] = set()

    for event_type, event_key in ARRAY_EVENT_KEYS.items():
        items = key_events.get(event_key)
        if isinstance(items, list):
            array_queues[event_key] = _clone_payload(items)
        elif isinstance(items, dict):
            array_queues[event_key] = [_clone_payload(items)]
        else:
            array_queues[event_key] = []

    replay_events: list[dict[str, Any]] = []
    for event_type in mode_fixture.get("event_sequence", []):
        array_key = ARRAY_EVENT_KEYS.get(event_type)
        if array_key:
            queue = array_queues.get(array_key, [])
            replay_events.append(queue.pop(0) if queue else {"type": event_type})
            continue

        single_key = SINGLE_EVENT_KEYS.get(event_type)
        if single_key and single_key not in used_singles:
            used_singles.add(single_key)
            payload = key_events.get(single_key)
            if isinstance(payload, dict):
                replay_events.append(_clone_payload(payload))
                continue

        replay_events.append({"type": event_type})

    return replay_events


def replay_frontend_chat_runtime_mode(mode_fixture: dict[str, Any]) -> dict[str, Any]:
    """Replay one mode fixture into the final frontend runtime snapshot."""
    artifact: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    plan_preview: dict[str, Any] | None = None
    session_id: str | None = None
    answer = ""
    reasoning = ""
    reasoning_timestamp = ""
    completion: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None
    stage_history: list[dict[str, Any]] = []
    subagent_events: list[dict[str, Any]] = []
    connection_status = "idle"

    for event in _build_replay_events(mode_fixture):
        event_type = event.get("type")
        if event_type == "session_id" and isinstance(event.get("session_id"), str):
            session_id = event["session_id"]
        elif event_type == "stage":
            stage_history.append(_normalize_stage(event))
        elif event_type == "plan_preview":
            plan_preview = _normalize_plan_preview(event)
            artifact = _merge_trip_plan_artifact(artifact, plan_preview.get("artifact") or plan_preview.get("artifactPatch"))
        elif event_type == "subagent_start":
            subagent_events.append(_normalize_subagent_start(event))
        elif event_type == "subagent_end":
            subagent_events.append(_normalize_subagent_end(event))
        elif event_type == "artifact_patch" and isinstance(event.get("artifact_patch"), dict):
            artifact = _merge_trip_plan_artifact(artifact, event.get("artifact_patch"))
        elif event_type == "reasoning_chunk" and isinstance(event.get("content"), str):
            reasoning += event["content"]
        elif event_type == "chunk" and isinstance(event.get("content"), str):
            answer += event["content"]
        elif event_type == "metadata":
            metadata = _normalize_metadata(event)
            artifact = _merge_trip_plan_artifact(artifact, metadata.get("artifact"))
        elif event_type == "done":
            completion = _normalize_completion(event)
            artifact = _merge_trip_plan_artifact(artifact, completion.get("artifact"))
            diagnostics = _build_completion_diagnostics(
                artifact=artifact,
                completion=completion,
                metadata=metadata,
                subagent_events=subagent_events,
            )
            connection_status = "idle"
        elif event_type == "error":
            connection_status = "error"
        elif event_type == "reasoning_timestamp" and isinstance(event.get("timestamp"), str):
            reasoning_timestamp = event["timestamp"]

    return {
        "request": _clone_payload(mode_fixture.get("request", {})),
        "response": _clone_payload(mode_fixture.get("response", {})),
        "assistant_message": {
            "content": answer,
            "reasoning": _build_final_reasoning(reasoning, reasoning_timestamp or None),
            "diagnostics": diagnostics,
        }
        if completion
        else None,
        "runtime_state": {
            "session_id": session_id,
            "connection_status": connection_status,
            "stage_history": stage_history,
            "plan_preview": plan_preview,
            "artifact": artifact,
            "metadata": metadata,
            "subagent_events": subagent_events,
        },
    }


def build_frontend_chat_runtime_golden_fixture(source_fixture: dict[str, Any]) -> dict[str, Any]:
    """Build the full frontend golden fixture from the backend stream baseline."""
    return {
        "schema_version": 1,
        "source_fixture_schema_version": source_fixture.get("schema_version"),
        "endpoint": source_fixture.get("endpoint"),
        "modes": {
            mode: replay_frontend_chat_runtime_mode(mode_fixture)
            for mode, mode_fixture in source_fixture.get("modes", {}).items()
        },
    }


def export_frontend_chat_runtime_golden_fixture(
    source_path: Path = DEFAULT_SOURCE,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    """Persist the generated frontend golden fixture to disk."""
    source_fixture = json.loads(source_path.read_text(encoding="utf-8"))
    payload = build_frontend_chat_runtime_golden_fixture(source_fixture)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for frontend replay fixture export options."""
    parser = argparse.ArgumentParser(description="Export frontend chat-runtime golden fixture.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source chat-stream golden fixture path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path for frontend chat-runtime golden fixture.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the fixture export CLI and report the output path."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = export_frontend_chat_runtime_golden_fixture(Path(args.source), Path(args.output))
    print(f"Frontend chat-runtime golden fixture exported to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
