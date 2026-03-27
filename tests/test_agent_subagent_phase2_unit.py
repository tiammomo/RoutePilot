"""Automated tests for phase-3 subagent runtime behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.travel_agent.runtime.agent_runtime import AgentRuntime
from agent.travel_agent.skills import build_default_skill_registry
from agent.travel_agent.subagents import build_default_subagent_registry


def test_default_subagent_registry_resolves_stage_and_tool_mapping():
    skill_registry = SimpleNamespace(
        for_subagent=lambda name: {
            "research": [SimpleNamespace(name="CityResearchSkill", tool_names=["search_cities"])],
            "planning": [SimpleNamespace(name="PlanSynthesisSkill", tool_names=["plan_itinerary", "query_hotels"])],
            "budget": [SimpleNamespace(name="BudgetAggregationSkill", tool_names=["calculate_budget"])],
            "verification": [SimpleNamespace(name="RiskAuditSkill", tool_names=["get_travel_tips"])],
        }.get(name, [])
    )

    registry = build_default_subagent_registry(skill_registry)

    assert registry.names() == ["research", "planning", "budget", "verification"]
    assert registry.resolve_subagent_for_stage(stage="query", label="planning", explicit_subagent=None) == "planning"
    assert registry.resolve_subagent_for_stage(stage="budget", label="budget estimation", explicit_subagent=None) == "budget"
    assert registry.resolve_subagent_for_stage(stage="generate", label="verify", explicit_subagent=None) == "verification"
    assert registry.resolve_subagent_for_tool("search_cities") == "research"
    assert registry.resolve_subagent_for_tool("plan_itinerary") == "planning"
    assert registry.resolve_subagent_for_tool("calculate_budget") == "budget"


def test_runtime_emits_budget_subagent_events_and_artifact_patches(monkeypatch):
    runtime = AgentRuntime(
        llm=SimpleNamespace(),
        tools=[
            SimpleNamespace(name="search_cities"),
            SimpleNamespace(name="plan_itinerary"),
            SimpleNamespace(name="calculate_budget"),
            SimpleNamespace(name="query_hotels"),
            SimpleNamespace(name="get_travel_tips"),
        ],
        memory_manager=SimpleNamespace(),
    )

    async def _fake_stream(**kwargs):
        _ = kwargs
        yield {"type": "stage", "stage": "query", "label": "planning", "subagent": "planning"}
        yield {"type": "tool_start", "tool": "plan_itinerary"}
        yield {"type": "tool_end", "tool": "plan_itinerary", "result": "ok"}
        yield {"type": "stage", "stage": "query", "label": "research", "subagent": "research"}
        yield {"type": "tool_start", "tool": "search_cities"}
        yield {"type": "tool_end", "tool": "search_cities", "result": "ok"}
        yield {"type": "stage", "stage": "budget", "label": "budget estimation", "subagent": "budget"}
        yield {"type": "tool_start", "tool": "calculate_budget"}
        yield {"type": "tool_end", "tool": "calculate_budget", "result": "ok"}
        yield {"type": "stage", "stage": "generate", "label": "verify", "subagent": "verification"}
        yield {
            "type": "done",
            "answer": "hello",
            "intent": "itinerary",
            "tools_used": ["plan_itinerary", "search_cities", "calculate_budget"],
            "run_id": "run-2",
            "plan_id": "plan-2",
            "verification_passed": True,
            "stale_result_count": 0,
            "fallback_steps": 0,
            "execution_budget": {"estimated_total": 2400, "currency": "CNY"},
            "execution_stats": {"steps": []},
        }

    monkeypatch.setattr("agent.travel_agent.runtime.agent_runtime.run_travel_agent_streaming_with_memory", _fake_stream)

    async def _collect():
        return [
            event
            async for event in runtime.stream_with_memory(
                user_message="plan and verify",
                session_id="session-2",
                persist_memory=False,
                run_id="run-2",
                chat_mode="plan",
            )
        ]

    events = asyncio.run(_collect())
    event_types = [event["type"] for event in events]

    assert "subagent_start" in event_types
    assert "subagent_end" in event_types
    assert "artifact_patch" in event_types
    assert event_types[-1] == "done"

    planning_start = next(event for event in events if event["type"] == "subagent_start" and event["subagent"] == "planning")
    budget_patch = next(event for event in events if event["type"] == "artifact_patch" and event["subagent"] == "budget")
    verification_end = next(event for event in events if event["type"] == "subagent_end" and event["subagent"] == "verification")
    done_event = events[-1]

    assert "PlanSynthesisSkill" in planning_start["skills"]
    assert budget_patch["artifact_patch"]["budget"]["executionBudget"]["estimated_total"] == 2400
    assert verification_end["status"] == "completed"
    assert done_event["artifact"]["verification"]["passed"] is True
    assert done_event["artifact"]["metadata"]["budget_subagent_completed"] is True
    assert done_event["artifact"]["budget"]["summary"]["sourceTools"] == ["calculate_budget"]
    assert done_event["artifact"]["metadata"]["verification_subagent_completed"] is True


def test_subagent_registry_exposes_skill_selection_policy_and_context_plan():
    """Subagents should expose governed skill ordering and readiness decisions."""
    registry = build_default_subagent_registry(build_default_skill_registry())

    planning_policy = registry.selection_policy("planning")
    budget_plan = registry.selection_plan(
        "budget",
        context_keys=["destinations", "stay_nights", "budget_mode"],
        intent_signals=["budget"],
    )
    verification_plan = registry.selection_plan(
        "verification",
        context_keys=["destinations"],
        intent_signals=["itinerary"],
    )

    assert [item["skill"] for item in planning_policy] == [
        "PlanSynthesisSkill",
        "HotelQuoteSkill",
        "WeatherLookupSkill",
    ]
    assert planning_policy[0]["required_context"] == ["user_intent", "research_dossier"]
    assert planning_policy[0]["preferred_context"] == ["research_dossier", "budget_report"]

    assert budget_plan[0]["skill"] == "HotelQuoteSkill"
    assert budget_plan[0]["status"] == "ready"
    assert budget_plan[0]["matched_intent_signals"] == ["budget"]
    assert budget_plan[1]["skill"] == "BudgetAggregationSkill"
    assert budget_plan[1]["status"] == "blocked"
    assert budget_plan[1]["missing_required_context"] == [
        "hotel_quotes",
        "transport_estimates",
        "activity_estimates",
    ]

    assert verification_plan[0]["skill"] == "TravelTipsSkill"
    assert verification_plan[0]["status"] == "standby"
