"""Export stable SSE contract snapshot for chat streaming route regression checks."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import httpx


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.dependencies.container import get_container
from moyuan_web.main import create_app

DEFAULT_OUTPUT = ROOT / "docs" / "reference" / "sse-contract.snapshot.json"


def _decode_sse_payloads(lines: list[str]) -> list[dict[str, Any]]:
    """Decode JSON payloads from raw SSE lines."""
    decoder = json.JSONDecoder()
    events: list[dict[str, Any]] = []
    for line in lines:
        if "data:" not in line:
            continue
        for part in line.split("data:"):
            data = part.strip()
            if not data or data == "[DONE]":
                continue
            idx = 0
            while idx < len(data):
                while idx < len(data) and data[idx].isspace():
                    idx += 1
                if idx >= len(data):
                    break
                payload, end = decoder.raw_decode(data, idx)
                if isinstance(payload, dict):
                    events.append(payload)
                idx = end
    return events


def _sanitize_payload(payload: Any) -> Any:
    """Normalize dynamic or noisy payload fields while preserving contract shape."""
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"request_id", "trace_id", "run_id"}:
                normalized[key] = "<id>"
            elif key == "session_id":
                normalized[key] = "session-demo"
            elif key == "plan_id":
                normalized[key] = "plan-demo"
            elif key in {"content", "answer", "result", "message", "explanation", "label"} and isinstance(value, str):
                normalized[key] = "<text>"
            else:
                normalized[key] = _sanitize_payload(value)
        return normalized
    if isinstance(payload, list):
        return [_sanitize_payload(item) for item in payload]
    return payload


@contextmanager
def _patched_chat_service() -> Iterator[None]:
    """Patch ChatService behaviors so snapshot export stays deterministic and offline-safe."""
    container = get_container()
    service = container.resolve("ChatService")
    service_type = type(service)

    async def mock_initialize(self):
        """Mark chat service initialized without touching real providers."""
        self._initialized = True

    async def mock_ensure_session(self, session_id):
        """Return one deterministic session id for snapshot export."""
        _ = session_id
        return "session-demo"

    async def mock_save_message(self, session_id, role, content, reasoning=None):
        """Pretend message persistence succeeded without mutating real storage."""
        _ = (session_id, role, content, reasoning)
        return {"success": True}

    async def mock_write_memory(self, session_id, message):
        """Pretend memory sync succeeded without touching runtime memory files."""
        _ = (session_id, message)
        return True

    async def mock_stream_direct_response(self, session_id, message):
        """Yield deterministic direct-mode tokens for the snapshot."""
        _ = (session_id, message)
        for token in ("Direct", " reply"):
            yield token

    async def mock_stream_agent_events(self, session_id, message, mode="react", run_id=None):
        """Yield deterministic agent events shared by react and plan snapshots."""
        _ = (session_id, message, run_id)
        yield {
            "type": "subagent_start",
            "subagent": "planning",
            "skills": ["PlanSynthesisSkill"],
            "sequence": 1,
            "trigger": "stage",
        }
        yield {"type": "reasoning", "content": f"{mode} thinking"}
        yield {
            "type": "stage",
            "stage": "planning",
            "label": f"{mode} planning",
            "progress": 0.25,
            "subagent": "planning",
        }
        yield {
            "type": "artifact_patch",
            "subagent": "planning",
            "artifact_patch": {"itinerary": {"plan_id": "plan-demo"}},
        }
        yield {"type": "subagent_end", "subagent": "planning", "sequence": 1, "status": "completed"}
        yield {
            "type": "subagent_start",
            "subagent": "research",
            "skills": ["CityResearchSkill"],
            "sequence": 2,
            "trigger": "tool",
        }
        yield {"type": "tool_start", "tool": "search_cities", "subagent": "research"}
        yield {"type": "tool_end", "tool": "search_cities", "result": f"{mode} search done", "subagent": "research"}
        yield {"type": "subagent_end", "subagent": "research", "sequence": 2, "status": "completed"}
        yield {
            "type": "subagent_start",
            "subagent": "verification",
            "skills": ["BudgetAggregationSkill"],
            "sequence": 3,
            "trigger": "stage",
        }
        yield {"type": "chunk", "content": f"{mode} answer"}
        yield {
            "type": "artifact_patch",
            "subagent": "verification",
            "artifact_patch": {"verification": {"passed": True}},
        }
        yield {"type": "subagent_end", "subagent": "verification", "sequence": 3, "status": "completed"}
        yield {
            "type": "done",
            "answer": f"{mode} answer",
            "tools_used": ["search_cities"],
            "plan_id": "plan-demo" if mode == "plan" else None,
            "intent": "itinerary",
            "execution_stats": {
                "steps": [
                    {
                        "tool": "search_cities",
                        "status": "completed",
                        "fallback_used": False,
                        "is_stale": False,
                    }
                ]
            },
            "verification_passed": True,
            "stale_result_count": 0,
            "fallback_steps": 0,
            "artifact": {
                "itinerary": {"plan_id": "plan-demo"},
                "verification": {"passed": True},
            },
        }

    def mock_generate_plan_preview(self, session_id, message):
        """Return one deterministic plan preview payload for plan-mode snapshots."""
        _ = (session_id, message)
        return {
            "plan_id": "plan-demo",
            "intent": "itinerary",
            "plan_explanation": "intent=itinerary, plan_steps=2",
            "validation_status": "warn",
            "validation_errors": [
                {
                    "step_id": "s2",
                    "tool": "not_registered_tool",
                    "code": "TOOL_NOT_REGISTERED",
                    "message": "Tool not registered: not_registered_tool",
                }
            ],
            "plan": [
                {"step": 1, "tool": "search_cities", "params": {"city": "Shanghai"}},
                {"step": 2, "tool": "plan_itinerary", "params": {"destination": "Shanghai", "days": 3}},
            ],
            "artifact": {"itinerary": {"plan_id": "plan-demo"}},
            "subagent": "planning",
            "skills": ["PlanSynthesisSkill"],
            "artifact_patch": {"itinerary": {"plan_id": "plan-demo"}},
        }

    def noop_record_metrics(self, intent, execution_stats, hard_error):
        """Skip in-memory health metric updates during snapshot export."""
        _ = (intent, execution_stats, hard_error)

    def noop_emit_failure(self, session_id, run_id, mode, execution_stats, answer, hard_error=None):
        """Skip failure telemetry writes during snapshot export."""
        _ = (session_id, run_id, mode, execution_stats, answer, hard_error)

    originals = {
        "initialize": service_type.initialize,
        "_ensure_session": service_type._ensure_session,
        "save_message": service_type.save_message,
        "_write_memory_user": service_type._write_memory_user,
        "_write_memory_assistant": service_type._write_memory_assistant,
        "_stream_direct_response": service_type._stream_direct_response,
        "_stream_agent_events": service_type._stream_agent_events,
        "_generate_plan_preview": service_type._generate_plan_preview,
        "_record_run_metrics": service_type._record_run_metrics,
        "_emit_failure_telemetry": service_type._emit_failure_telemetry,
    }
    service_type.initialize = mock_initialize
    service_type._ensure_session = mock_ensure_session
    service_type.save_message = mock_save_message
    service_type._write_memory_user = mock_write_memory
    service_type._write_memory_assistant = mock_write_memory
    service_type._stream_direct_response = mock_stream_direct_response
    service_type._stream_agent_events = mock_stream_agent_events
    service_type._generate_plan_preview = mock_generate_plan_preview
    service_type._record_run_metrics = noop_record_metrics
    service_type._emit_failure_telemetry = noop_emit_failure
    try:
        yield
    finally:
        for name, original in originals.items():
            setattr(service_type, name, original)


async def _collect_mode_contract(app: Any, mode: str) -> dict[str, Any]:
    """Collect one normalized SSE exchange for the requested mode."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": f"demo request for {mode}", "mode": mode},
        ) as response:
            lines = [line async for line in response.aiter_lines()]
            events = [_sanitize_payload(payload) for payload in _decode_sse_payloads(lines)]
            return {
                "response": {
                    "status_code": response.status_code,
                    "headers": {
                        "content-type": response.headers.get("content-type", ""),
                        "x-request-id": "<id>" if response.headers.get("x-request-id") else "",
                        "x-trace-id": "<id>" if response.headers.get("x-trace-id") else "",
                    },
                },
                "event_types": [event.get("type", "unknown") for event in events],
                "events": events,
            }


async def export_sse_contract_snapshot_async(output_path: Path = DEFAULT_OUTPUT) -> Path:
    """Render stable SSE contract snapshot across supported chat modes."""
    app = create_app()
    with _patched_chat_service():
        modes = {
            "direct": await _collect_mode_contract(app, "direct"),
            "react": await _collect_mode_contract(app, "react"),
            "plan": await _collect_mode_contract(app, "plan"),
        }

    snapshot = {
        "schema_version": 1,
        "endpoint": "POST /api/chat/stream",
        "modes": modes,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def export_sse_contract_snapshot(output_path: Path = DEFAULT_OUTPUT) -> Path:
    """Synchronous wrapper for SSE contract snapshot export."""
    return asyncio.run(export_sse_contract_snapshot_async(output_path))


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for SSE contract snapshot export utility."""
    parser = argparse.ArgumentParser(description="Export current SSE contract snapshot.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output path for exported SSE snapshot.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for exporting SSE contract snapshot."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = export_sse_contract_snapshot(Path(args.output))
    print(f"SSE contract snapshot exported to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
