"""Automated tests for phase-1 supervisor runtime compatibility."""

from __future__ import annotations

import asyncio

from types import SimpleNamespace

from agent.travel_agent.artifacts import (
    build_trip_plan_artifact_from_plan_preview,
    build_trip_plan_artifact_from_state,
)
from agent.travel_agent.contracts import (
    SupervisorPlanPreview,
    SupervisorPlanPreviewRequest,
    SupervisorRunRequest,
    SupervisorRuntimeContext,
)
from agent.travel_agent.runtime.agent_runtime import AgentRuntime
from agent.travel_agent.skills import build_default_skill_registry


def test_build_default_skill_registry_filters_missing_tools():
    tools = [
        SimpleNamespace(name="search_cities"),
        SimpleNamespace(name="query_attractions"),
        SimpleNamespace(name="plan_itinerary"),
    ]

    registry = build_default_skill_registry(tools)

    assert registry.get("CityResearchSkill") is not None
    assert registry.get("AttractionResearchSkill") is not None
    assert registry.get("PlanSynthesisSkill") is not None
    assert registry.get("HotelQuoteSkill") is None
    assert len(registry.for_subagent("research")) == 2


def test_build_trip_plan_artifact_from_state_contains_phase1_views():
    artifact = build_trip_plan_artifact_from_state(
        {
            "intent": "budget",
            "intent_detail": {"confidence": 0.92, "entities": {"city": "Shanghai"}},
            "plan_id": "plan-123",
            "plan_explanation": "budget-first plan",
            "plan": [{"step": 1, "tool": "calculate_budget"}],
            "validation_status": "warn",
            "validation_errors": [{"code": "MISSING_WEATHER"}],
            "verify_result": {"passed": False, "should_retry": True, "issues": [{"message": "stale weather"}]},
            "execution_summary": {"fallback_steps": 1},
            "execution_budget": {"max_tools": 3},
            "tool_results": {"weather": {"success": True, "is_stale": True}},
            "answer": "budget answer",
            "reasoning": "reasoning text",
            "tools_used": ["calculate_budget"],
            "session_id": "s1",
            "run_id": "r1",
            "strategy": "budget",
            "routing": "plan",
            "current_step": 1,
            "execution_round": 2,
        }
    )

    assert artifact["intent"]["name"] == "budget"
    assert artifact["intent"]["entities"]["city"] == "Shanghai"
    assert artifact["itinerary"]["plan_id"] == "plan-123"
    assert artifact["budget"]["stale_result_count"] == 1
    assert artifact["verification"]["passed"] is False
    assert artifact["metadata"]["routing"] == "plan"


def test_build_trip_plan_artifact_from_plan_preview_contains_validation():
    artifact = build_trip_plan_artifact_from_plan_preview(
        {
            "plan_id": "preview-1",
            "intent": "itinerary",
            "plan_explanation": "preview",
            "validation_status": "warn",
            "validation_errors": [{"code": "TOOL_NOT_REGISTERED"}],
            "plan": [{"step": 1, "tool": "plan_itinerary"}],
        },
        user_message="plan a trip",
        session_id="s1",
    )

    assert artifact["itinerary"]["plan_id"] == "preview-1"
    assert artifact["itinerary"]["validation_status"] == "warn"
    assert artifact["verification"]["summary"] == "preview_not_executed"


def test_agent_runtime_enriches_done_stream_event():
    observed: dict[str, object] = {}

    class _LegacyBridge:
        async def stream_with_memory(self, *, request, context):
            observed["request"] = request
            observed["context"] = context
            yield {"type": "stage", "stage": "parse"}
            yield {
                "type": "done",
                "answer": "hello",
                "intent": "recommend",
                "tools_used": ["search_cities"],
                "run_id": "run-1",
                "verification_passed": True,
            }

        def generate_plan_preview_with_memory(self, **kwargs):
            raise AssertionError("preview path should not be used in this test")

        def get_tool_health_diagnostics(self):
            return {}

    runtime = AgentRuntime(
        llm=SimpleNamespace(),
        tools=[SimpleNamespace(name="search_cities")],
        memory_manager=SimpleNamespace(),
        legacy_bridge=_LegacyBridge(),
    )

    async def _collect():
        return [
            event
            async for event in runtime.stream_with_memory(
                user_message="recommend somewhere",
                session_id="session-1",
                persist_memory=False,
                run_id="run-1",
                chat_mode="react",
            )
        ]

    events = asyncio.run(_collect())

    assert events[0]["type"] == "stage"
    assert isinstance(observed["request"], SupervisorRunRequest)
    assert observed["request"].session_id == "session-1"
    assert observed["request"].persist_memory is False
    assert isinstance(observed["context"], SupervisorRuntimeContext)
    assert observed["context"].tools[0].name == "search_cities"
    done_event = next(event for event in events if event["type"] == "done")
    assert done_event["artifact"]["intent"]["name"] == "recommend"
    assert done_event["artifact"]["metadata"]["session_id"] == "session-1"
    assert any(event["type"] == "artifact_patch" for event in events)


def test_agent_runtime_preview_attaches_artifact():
    observed: dict[str, object] = {}

    class _LegacyBridge:
        async def stream_with_memory(self, *, request, context):
            _ = (request, context)
            if False:  # pragma: no cover - async generator marker
                yield {}

        def generate_plan_preview_with_memory(self, *, request, context):
            observed["request"] = request
            observed["context"] = context
            return SupervisorPlanPreview(
                plan_id="preview-2",
                intent="itinerary",
                plan_explanation="preview explain",
                validation_status="pass",
                validation_errors=[],
                plan=[{"step": 1, "tool": "plan_itinerary"}],
            )

        def get_tool_health_diagnostics(self):
            return {}

    runtime = AgentRuntime(
        llm=SimpleNamespace(),
        tools=[SimpleNamespace(name="plan_itinerary")],
        memory_manager=SimpleNamespace(),
        legacy_bridge=_LegacyBridge(),
    )

    preview = runtime.generate_plan_preview_with_memory(
        user_message="plan a trip",
        session_id="session-2",
        chat_mode="plan",
    )

    assert preview["artifact"]["itinerary"]["plan_id"] == "preview-2"
    assert preview["artifact"]["metadata"]["phase"] == "plan_preview"
    assert isinstance(observed["request"], SupervisorPlanPreviewRequest)
    assert observed["request"].session_id == "session-2"
    assert isinstance(observed["context"], SupervisorRuntimeContext)
    assert observed["context"].tools[0].name == "plan_itinerary"


def test_agent_runtime_diagnostics_merge_legacy_bridge_payload():
    class _LegacyBridge:
        async def stream_with_memory(self, *, request, context):
            _ = (request, context)
            if False:  # pragma: no cover - async generator marker
                yield {}

        def generate_plan_preview_with_memory(self, *, request, context):
            _ = (request, context)
            return {}

        def get_tool_health_diagnostics(self):
            return {"legacy_runtime": {"status": "ok"}}

    runtime = AgentRuntime(
        llm=SimpleNamespace(),
        tools=[SimpleNamespace(name="plan_itinerary")],
        memory_manager=SimpleNamespace(),
        legacy_bridge=_LegacyBridge(),
    )

    diagnostics = runtime.get_tool_health_diagnostics()

    assert diagnostics["legacy_runtime"]["status"] == "ok"
    assert diagnostics["architecture_phase"] == "phase2-supervisor-subagents"
