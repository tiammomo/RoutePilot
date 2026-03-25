"""Local ASGI smoke test for chat streaming route."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.dependencies.container import get_container  # noqa: E402
from moyuan_web.main import create_app  # noqa: E402
from moyuan_web.services.chat.plan_preview_coordinator import ChatPlanPreviewCoordinator  # noqa: E402
from moyuan_web.services.chat.stream_mixin import ChatStreamMixin, _StreamRunState  # noqa: E402
from moyuan_web.services.chat_service import ChatService  # noqa: E402


class _StreamHelperHarness(ChatStreamMixin):
    def _extract_failure_clusters(self, execution_stats):
        return execution_stats.get("failure_clusters", [])

    @staticmethod
    def _get_timestamp() -> str:
        return "2026-03-25T00:00:00Z"


@pytest.mark.asyncio
async def test_chat_stream_sse_smoke(monkeypatch):
    app = create_app()
    container = get_container()
    service = container.resolve("ChatService")

    async def mock_initialize(self):
        self._initialized = True

    async def mock_stream_agent_events(
        self,
        session_id: str,
        message: str,
        mode: str = "react",
        run_id: str | None = None,
    ):
        yield {"type": "reasoning", "content": "analyzing"}
        yield {"type": "tool_start", "tool": "search_cities"}
        yield {"type": "tool_end", "tool": "search_cities", "result": "ok"}
        yield {"type": "chunk", "content": "Hello"}
        yield {"type": "chunk", "content": " world"}
        yield {"type": "done", "answer": "Hello world", "tools_used": ["search_cities"]}

    monkeypatch.setattr(type(service), "initialize", mock_initialize, raising=True)
    monkeypatch.setattr(type(service), "_stream_agent_events", mock_stream_agent_events, raising=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "message": "recommend a travel destination\n\nformat as structured itinerary",
                "display_message": "recommend a travel destination",
                "mode": "react",
            },
        ) as response:
            assert response.status_code == 200
            assert response.headers.get("X-Request-ID")
            assert response.headers.get("X-Trace-ID")

            events = []
            async for line in response.aiter_lines():
                if "data:" in line:
                    for part in line.split("data:"):
                        data = part.strip()
                        if not data or data == "[DONE]":
                            continue

                        decoder = json.JSONDecoder()
                        idx = 0
                        while idx < len(data):
                            while idx < len(data) and data[idx].isspace():
                                idx += 1
                            if idx >= len(data):
                                break
                            try:
                                payload, end = decoder.raw_decode(data, idx)
                            except json.JSONDecodeError:
                                break
                            events.append(payload)
                            idx = end

            event_types = [item.get("type") for item in events]
            assert "session_id" in event_types
            assert "reasoning_start" in event_types
            assert "reasoning_chunk" in event_types
            assert "answer_start" in event_types
            assert "chunk" in event_types
            assert "metadata" in event_types
            assert "done" in event_types

            chunks = [item.get("content", "") for item in events if item.get("type") == "chunk"]
            assert "".join(chunks) == "Hello world"

            session_event = next(item for item in events if item.get("type") == "session_id")
            metadata_event = next(item for item in events if item.get("type") == "metadata")
            done_event = next(item for item in events if item.get("type") == "done")
            assert session_event.get("run_id")
            assert session_event.get("request_id")
            assert session_event.get("trace_id")
            assert metadata_event.get("run_id") == session_event.get("run_id")
            assert done_event.get("run_id") == session_event.get("run_id")
            assert metadata_event.get("request_id") == session_event.get("request_id")
            assert done_event.get("trace_id") == session_event.get("trace_id")
            assert metadata_event.get("verification_passed") is True
            assert metadata_event.get("stale_result_count") == 0
            assert metadata_event.get("fallback_steps") == 0

            persisted = await service.get_messages(session_event["session_id"])
            user_messages = [item for item in persisted.get("messages", []) if item.get("role") == "user"]
            assert user_messages[0].get("content") == "recommend a travel destination"


@pytest.mark.asyncio
async def test_chat_stream_plan_mode_emits_plan_preview(monkeypatch):
    app = create_app()
    container = get_container()
    service = container.resolve("ChatService")

    async def mock_initialize(self):
        self._initialized = True

    async def mock_stream_agent_events(
        self,
        session_id: str,
        message: str,
        mode: str = "react",
        run_id: str | None = None,
    ):
        yield {"type": "reasoning", "content": "planning"}
        yield {"type": "chunk", "content": "final"}
        yield {"type": "done", "answer": "final", "tools_used": ["search_cities"]}

    def mock_generate_plan_preview(self, session_id: str, message: str):
        return {
            "plan_id": "plan-abc123",
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
                {"step": 1, "tool": "query_attractions", "params": {"city": "Shanghai"}},
                {"step": 2, "tool": "plan_itinerary", "params": {"destination": "Shanghai", "days": 3}},
            ],
        }

    monkeypatch.setattr(type(service), "initialize", mock_initialize, raising=True)
    monkeypatch.setattr(type(service), "_stream_agent_events", mock_stream_agent_events, raising=True)
    monkeypatch.setattr(type(service), "_generate_plan_preview", mock_generate_plan_preview, raising=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "plan a 3-day trip in Shanghai", "mode": "plan"},
        ) as response:
            assert response.status_code == 200

            events = []
            async for line in response.aiter_lines():
                if "data:" not in line:
                    continue
                for part in line.split("data:"):
                    data = part.strip()
                    if not data or data == "[DONE]":
                        continue

                    decoder = json.JSONDecoder()
                    idx = 0
                    while idx < len(data):
                        while idx < len(data) and data[idx].isspace():
                            idx += 1
                        if idx >= len(data):
                            break
                        try:
                            payload, end = decoder.raw_decode(data, idx)
                        except json.JSONDecodeError:
                            break
                        events.append(payload)
                        if payload.get("type") == "done":
                            break
                        idx = end

    event_types = [item.get("type") for item in events]
    assert "plan_preview" in event_types
    plan_event = next(item for item in events if item.get("type") == "plan_preview")
    assert plan_event.get("plan_id") == "plan-abc123"
    assert "plan_steps=2" in plan_event.get("explanation", "")
    assert plan_event.get("intent") == "itinerary"
    assert plan_event.get("validation_status") == "warn"
    assert len(plan_event.get("validation_errors", [])) == 1
    assert plan_event.get("validation_errors", [])[0].get("code") == "TOOL_NOT_REGISTERED"
    assert len(plan_event.get("steps", [])) == 2


@pytest.mark.asyncio
async def test_chat_stream_emits_subagent_events(monkeypatch):
    app = create_app()
    container = get_container()
    service = container.resolve("ChatService")

    async def mock_initialize(self):
        self._initialized = True

    async def mock_stream_agent_events(
        self,
        session_id: str,
        message: str,
        mode: str = "react",
        run_id: str | None = None,
    ):
        _ = (session_id, message, mode, run_id)
        yield {"type": "subagent_start", "subagent": "planning", "skills": ["PlanSynthesisSkill"], "sequence": 1}
        yield {"type": "stage", "stage": "query", "label": "生成计划", "subagent": "planning"}
        yield {"type": "artifact_patch", "subagent": "planning", "artifact_patch": {"itinerary": {"plan_id": "plan-local"}}}
        yield {"type": "subagent_end", "subagent": "planning", "status": "completed", "sequence": 1}
        yield {"type": "chunk", "content": "done"}
        yield {
            "type": "done",
            "answer": "done",
            "tools_used": ["plan_itinerary"],
            "artifact": {"itinerary": {"plan_id": "plan-local"}},
        }

    monkeypatch.setattr(type(service), "initialize", mock_initialize, raising=True)
    monkeypatch.setattr(type(service), "_stream_agent_events", mock_stream_agent_events, raising=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "plan a trip", "mode": "react"},
        ) as response:
            assert response.status_code == 200

            events = []
            async for line in response.aiter_lines():
                if "data:" not in line:
                    continue
                for part in line.split("data:"):
                    data = part.strip()
                    if not data or data == "[DONE]":
                        continue
                    decoder = json.JSONDecoder()
                    idx = 0
                    while idx < len(data):
                        while idx < len(data) and data[idx].isspace():
                            idx += 1
                        if idx >= len(data):
                            break
                        try:
                            payload, end = decoder.raw_decode(data, idx)
                        except json.JSONDecodeError:
                            break
                        events.append(payload)
                        idx = end

    event_types = [item.get("type") for item in events]
    assert "subagent_start" in event_types
    assert "artifact_patch" in event_types
    assert "subagent_end" in event_types
    metadata_event = next(item for item in events if item.get("type") == "metadata")
    done_event = next(item for item in events if item.get("type") == "done")
    assert metadata_event.get("artifact", {}).get("itinerary", {}).get("planId") == "plan-local"
    assert done_event.get("artifact", {}).get("itinerary", {}).get("planId") == "plan-local"

    session_event = next(item for item in events if item.get("type") == "session_id")
    persisted = await service.get_messages(session_event["session_id"])
    assert persisted.get("success") is True
    assistant_messages = [item for item in persisted.get("messages", []) if item.get("role") == "assistant"]
    assert len(assistant_messages) == 1
    diagnostics = assistant_messages[0].get("diagnostics", {})
    assert diagnostics.get("artifact", {}).get("itinerary", {}).get("planId") == "plan-local"
    assert len(diagnostics.get("subagentEvents", [])) >= 2
    assert diagnostics.get("runId") == session_event.get("run_id")


def test_sse_formatter_uses_real_newlines():
    event = ChatService._sse({"type": "chunk", "content": "ok"})
    assert event.endswith("\n\n")
    assert "\\n\\n" not in event


def test_runtime_chunk_normalization_emits_boundaries():
    harness = _StreamHelperHarness()
    state = _StreamRunState(requested_session_id="session-1")

    payloads = harness._normalize_runtime_event(state, {"type": "chunk", "content": "hello"})

    assert [item.get("type") for item in payloads] == ["reasoning_end", "answer_start", "chunk"]
    assert payloads[-1].get("content") == "hello"
    assert state.reasoning_ended is True
    assert state.answer_started is True
    assert state.answer_content == "hello"


def test_batch_sse_serializer_wraps_multiple_payloads():
    harness = _StreamHelperHarness()

    envelopes = harness._serialize_sse_payloads(
        [
            {"type": "chunk", "content": "a"},
            {"type": "done", "run_id": "run-1"},
        ]
    )

    assert len(envelopes) == 2
    assert all(item.startswith("data: ") for item in envelopes)
    assert all(item.endswith("\n\n") for item in envelopes)


def test_success_terminal_payloads_include_derived_metadata():
    harness = _StreamHelperHarness()
    state = _StreamRunState(requested_session_id="session-1")
    state.run_id = "run-1"
    state.answer_content = "hello world"
    state.reasoning_content = "analyzing"
    state.tools_used = ["search_cities", "search_cities", "plan_itinerary"]
    state.plan_id = "plan-1"
    state.execution_stats = {
        "steps": [
            {"fallback_used": True, "is_stale": False},
            {"fallback_used": False, "is_stale": True},
        ],
        "failure_clusters": [{"code": "timeout", "count": 1}],
    }
    state.final_artifact = {"itinerary": {"plan_id": "plan-1"}}

    harness._finalize_stream_state(state, mode="react")
    payloads = harness._build_success_terminal_payloads(state)

    metadata_event = payloads[0]
    done_event = payloads[1]
    assert metadata_event.get("type") == "metadata"
    assert metadata_event.get("total_steps") == 2
    assert metadata_event.get("fallback_steps") == 1
    assert metadata_event.get("stale_result_count") == 1
    assert metadata_event.get("verification_passed") is False
    assert metadata_event.get("failure_clusters") == [{"code": "timeout", "count": 1}]
    assert done_event.get("type") == "done"
    assert done_event.get("artifact", {}).get("itinerary", {}).get("plan_id") == "plan-1"


def test_plan_preview_coordinator_merges_preview_artifacts():
    preview = {
        "plan_id": "plan-abc123",
        "intent": "itinerary",
        "plan_explanation": "intent=itinerary, plan_steps=2",
        "validation_status": "warn",
        "validation_errors": [{"code": "TOOL_NOT_REGISTERED"}],
        "plan": [
            {"step": 1, "tool": "query_attractions"},
            {"step": 2, "tool": "plan_itinerary"},
        ],
        "artifact": {"intent": {"name": "itinerary"}},
        "subagent": "planning",
        "skills": ["PlanSynthesisSkill"],
        "artifact_patch": {"itinerary": {"plan_id": "plan-abc123"}},
    }
    coordinator = ChatPlanPreviewCoordinator(
        generate_plan_preview=lambda session_id, message: preview,
        get_timestamp=lambda: "2026-03-25T00:00:00Z",
        logger=logging.getLogger("test.plan_preview"),
    )
    state = _StreamRunState(requested_session_id="session-1")

    payloads = asyncio.run(
        coordinator.normalize(
            state,
            session_id="session-1",
            message="plan a 3-day trip",
        )
    )

    assert [item.get("type") for item in payloads] == [
        "reasoning_chunk",
        "subagent_start",
        "plan_preview",
        "artifact_patch",
        "subagent_end",
        "reasoning_chunk",
    ]
    assert state.final_artifact.get("intent", {}).get("name") == "itinerary"
    assert state.final_artifact.get("itinerary", {}).get("plan_id") == "plan-abc123"
    assert len(state.subagent_events) == 2
    assert "开始制定旅行计划..." in state.reasoning_content
    assert "识别意图：itinerary，共 2 步。" in state.reasoning_content
