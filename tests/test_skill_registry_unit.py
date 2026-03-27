"""Unit tests for the governed skills market registry."""

from __future__ import annotations

from types import SimpleNamespace

from agent.travel_agent.runtime.agent_runtime import AgentRuntime
from agent.travel_agent.skills import build_default_skill_registry


def test_default_skill_registry_exposes_governed_metadata():
    """Default skills should expose structured market metadata and contracts."""
    registry = build_default_skill_registry()

    city_skill = registry.get("CityResearchSkill")

    assert city_skill is not None
    assert city_skill.market_metadata.owner == "research-subagent"
    assert city_skill.market_metadata.version == "2026.03"
    assert city_skill.market_metadata.docs_path == "docs/reference/skills-market-catalog.md"
    assert city_skill.market_metadata.eval_fixture == "tests/test_skill_registry_unit.py"
    assert city_skill.market_metadata.onboarding_requirements == ["schema", "tests", "docs", "eval"]
    assert city_skill.input_contract.required_context == ["user_intent"]
    assert city_skill.output_contract.artifact == "ResearchDossier"
    assert "candidateDestinations" in city_skill.output_contract.fields
    assert city_skill.metadata["onboarding_doc"] == "docs/governance/skills-market-onboarding.md"

    payload = city_skill.to_dict()

    assert payload["market_metadata"]["owner"] == "research-subagent"
    assert payload["input_contract"]["required_context"] == ["user_intent"]
    assert payload["output_contract"]["artifact"] == "ResearchDossier"


def test_build_default_skill_registry_filters_tools_without_losing_market_contracts():
    """Tool filtering should preserve structured metadata for enabled skills."""
    tools = [
        SimpleNamespace(name="search_cities"),
        SimpleNamespace(name="plan_itinerary"),
        SimpleNamespace(name="calculate_budget"),
    ]

    registry = build_default_skill_registry(tools)

    assert [skill.name for skill in registry.all_skills()] == [
        "BudgetAggregationSkill",
        "CityResearchSkill",
        "PlanSynthesisSkill",
    ]
    assert registry.get("WeatherLookupSkill") is None
    assert registry.get("PlanSynthesisSkill").market_metadata.owner == "planning-subagent"
    assert registry.get("BudgetAggregationSkill").output_contract.fields == [
        "executionBudget",
        "budgetSummary",
        "budgetRisks",
    ]


def test_agent_runtime_health_diagnostics_include_skill_market_contracts():
    """Runtime diagnostics should expose the governed skills catalog to operators."""
    runtime = AgentRuntime(
        llm=SimpleNamespace(),
        tools=[
            SimpleNamespace(name="search_cities"),
            SimpleNamespace(name="plan_itinerary"),
            SimpleNamespace(name="calculate_budget"),
        ],
        memory_manager=SimpleNamespace(),
    )

    diagnostics = runtime.get_tool_health_diagnostics()

    assert diagnostics["architecture_phase"] == "phase2-supervisor-subagents"
    assert diagnostics["skills"]["CityResearchSkill"]["market_metadata"]["owner"] == "research-subagent"
    assert diagnostics["skills"]["PlanSynthesisSkill"]["output_contract"]["artifact"] == "ItineraryDraft"
    assert diagnostics["skills"]["BudgetAggregationSkill"]["input_contract"]["required_context"] == [
        "hotel_quotes",
        "transport_estimates",
        "activity_estimates",
    ]
