"""Unit tests for the explicit contract seam around the legacy runtime shim."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.travel_agent.contracts import (
    SupervisorPlanPreview,
    SupervisorPlanPreviewRequest,
    SupervisorRunRequest,
    SupervisorRuntimeContext,
)
from agent.travel_agent.graph import legacy_runtime
from agent.travel_agent.runtime.legacy_bridge import DefaultLegacyRuntimeBridge


def test_stream_supervisor_run_uses_explicit_contract(monkeypatch):
    """Legacy runtime stream shim should consume supervisor request/context directly."""
    observed: dict[str, object] = {}

    async def _fake_run_travel_agent_streaming_with_memory(**kwargs):
        observed.update(kwargs)
        yield {"type": "done", "answer": "ok"}

    monkeypatch.setattr(
        legacy_runtime,
        "run_travel_agent_streaming_with_memory",
        _fake_run_travel_agent_streaming_with_memory,
    )

    request = SupervisorRunRequest(
        user_message="plan a trip",
        session_id="session-1",
        system_prompt="system",
        persist_memory=False,
        run_id="run-1",
        chat_mode="plan",
    )
    context = SupervisorRuntimeContext(
        llm=SimpleNamespace(name="llm"),
        tools=[SimpleNamespace(name="search_cities")],
        memory_manager=SimpleNamespace(name="memory"),
        routing_llm=SimpleNamespace(name="router"),
    )

    async def _collect():
        return [event async for event in legacy_runtime.stream_supervisor_run(request=request, context=context)]

    events = asyncio.run(_collect())

    assert events == [{"type": "done", "answer": "ok"}]
    assert observed["user_message"] == "plan a trip"
    assert observed["session_id"] == "session-1"
    assert observed["system_prompt"] == "system"
    assert observed["persist_memory"] is False
    assert observed["run_id"] == "run-1"
    assert observed["chat_mode"] == "plan"
    assert observed["llm"] is context.llm
    assert observed["tools"] == context.tools
    assert observed["memory_manager"] is context.memory_manager
    assert observed["routing_llm"] is context.routing_llm


def test_generate_supervisor_plan_preview_uses_explicit_contract(monkeypatch):
    """Legacy runtime preview shim should consume supervisor request/context directly."""
    observed: dict[str, object] = {}

    def _fake_generate_plan_preview_with_memory(**kwargs):
        observed.update(kwargs)
        return {"plan_id": "preview-1"}

    monkeypatch.setattr(
        legacy_runtime,
        "generate_plan_preview_with_memory",
        _fake_generate_plan_preview_with_memory,
    )

    request = SupervisorPlanPreviewRequest(
        user_message="preview trip",
        session_id="session-2",
        system_prompt="system-preview",
        chat_mode="react",
    )
    context = SupervisorRuntimeContext(
        llm=SimpleNamespace(name="llm"),
        tools=[SimpleNamespace(name="plan_itinerary")],
        memory_manager=SimpleNamespace(name="memory"),
        routing_llm=SimpleNamespace(name="router"),
    )

    preview = legacy_runtime.generate_supervisor_plan_preview(request=request, context=context)

    assert isinstance(preview, SupervisorPlanPreview)
    assert preview.to_dict() == {
        "plan_id": "preview-1",
        "intent": None,
        "intent_detail": {},
        "plan_explanation": "",
        "validation_status": "pass",
        "validation_errors": [],
        "plan": [],
    }
    assert observed["user_message"] == "preview trip"
    assert observed["session_id"] == "session-2"
    assert observed["system_prompt"] == "system-preview"
    assert observed["chat_mode"] == "react"
    assert observed["llm"] is context.llm
    assert observed["tools"] == context.tools
    assert observed["memory_manager"] is context.memory_manager
    assert observed["routing_llm"] is context.routing_llm


def test_default_legacy_runtime_bridge_delegates_to_contract_shim(monkeypatch):
    """Bridge should delegate to contract-based legacy runtime entrypoints without re-packing kwargs."""
    observed: dict[str, object] = {}

    async def _fake_stream_supervisor_run(*, request, context):
        observed["stream_request"] = request
        observed["stream_context"] = context
        yield {"type": "done", "answer": "ok"}

    def _fake_generate_supervisor_plan_preview(*, request, context):
        observed["preview_request"] = request
        observed["preview_context"] = context
        return SupervisorPlanPreview(plan_id="preview-2", intent="itinerary")

    monkeypatch.setattr(legacy_runtime, "stream_supervisor_run", _fake_stream_supervisor_run)
    monkeypatch.setattr(
        legacy_runtime,
        "generate_supervisor_plan_preview",
        _fake_generate_supervisor_plan_preview,
    )

    bridge = DefaultLegacyRuntimeBridge()
    request = SupervisorRunRequest(
        user_message="bridge trip",
        session_id="session-3",
        system_prompt="bridge-system",
        persist_memory=True,
        run_id="run-3",
        chat_mode="plan",
    )
    preview_request = SupervisorPlanPreviewRequest(
        user_message="bridge preview",
        session_id="session-4",
        system_prompt="bridge-preview-system",
        chat_mode="plan",
    )
    context = SupervisorRuntimeContext(
        llm=SimpleNamespace(name="llm"),
        tools=[SimpleNamespace(name="search_cities")],
        memory_manager=SimpleNamespace(name="memory"),
        routing_llm=SimpleNamespace(name="router"),
    )

    async def _collect():
        return [event async for event in bridge.stream_with_memory(request=request, context=context)]

    events = asyncio.run(_collect())
    preview = bridge.generate_plan_preview_with_memory(request=preview_request, context=context)

    assert events == [{"type": "done", "answer": "ok"}]
    assert isinstance(preview, SupervisorPlanPreview)
    assert preview.to_dict()["plan_id"] == "preview-2"
    assert preview.to_dict()["intent"] == "itinerary"
    assert observed["stream_request"] is request
    assert observed["stream_context"] is context
    assert observed["preview_request"] is preview_request
    assert observed["preview_context"] is context
