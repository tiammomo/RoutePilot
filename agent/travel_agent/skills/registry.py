"""Registry for mapping domain skills to tool capabilities."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Optional

from langchain_core.tools import Tool

from ..contracts import SkillContract, SkillInputContract, SkillMarketMetadata, SkillOutputContract

_SKILL_CATALOG_DOC = "docs/reference/skills-market-catalog.md"
_SKILL_ONBOARDING_DOC = "docs/governance/skills-market-onboarding.md"
_SKILL_PROMPT_ANCHOR = "agent/travel_agent/graph/state.py::TRAVEL_AGENT_SYSTEM_PROMPT"
_SKILL_EVAL_FIXTURE = "tests/test_skill_registry_unit.py"


class SkillRegistry:
    """Runtime registry holding enabled skill contracts."""

    def __init__(self, skills: Optional[Iterable[SkillContract]] = None):
        """Initialize the registry with zero or more preconfigured skills."""
        self._skills: dict[str, SkillContract] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: SkillContract) -> None:
        """Register or replace one skill contract by name."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[SkillContract]:
        """Return one skill contract by name."""
        return self._skills.get(name)

    def all_skills(self) -> list[SkillContract]:
        """Return all registered skills in deterministic name order."""
        return [self._skills[name] for name in sorted(self._skills)]

    def for_subagent(self, subagent: str) -> list[SkillContract]:
        """Return skills that can be consumed by the requested subagent."""
        return [skill for skill in self.all_skills() if subagent in skill.allowed_subagents]

    def to_dict(self) -> dict[str, dict[str, object]]:
        """Return a JSON-serializable skill map for diagnostics payloads."""
        return {skill.name: skill.to_dict() for skill in self.all_skills()}

    def __len__(self) -> int:
        """Return the number of registered skill contracts."""
        return len(self._skills)


def build_default_skill_registry(tools: Optional[Iterable[Tool]] = None) -> SkillRegistry:
    """Build the default skill registry from the currently available tool set."""
    available_tool_names = _resolve_tool_names(tools)
    registry = SkillRegistry()
    for spec in _default_skill_contracts():
        if available_tool_names:
            filtered_tool_names = [name for name in spec.tool_names if name in available_tool_names]
            if not filtered_tool_names:
                continue
            spec = replace(spec, tool_names=filtered_tool_names)
        registry.register(spec)
    return registry


def _resolve_tool_names(tools: Optional[Iterable[Tool]]) -> set[str]:
    """Return the available tool-name set from a LangChain tool iterable."""
    if tools is None:
        return set()
    tool_names: set[str] = set()
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name.strip():
            tool_names.add(name)
    return tool_names


def _default_skill_contracts() -> list[SkillContract]:
    """Return the default phase-1 skill catalog used by the runtime."""
    return [
        SkillContract(
            name="CityResearchSkill",
            description="Discover and shortlist candidate destinations from user intent.",
            tool_names=["search_cities"],
            allowed_subagents=["research"],
            input_contract=SkillInputContract(
                required_context=["user_intent"],
                optional_context=["budget_preferences", "companion_profile", "season"],
            ),
            output_contract=SkillOutputContract(
                artifact="ResearchDossier",
                fields=["candidateDestinations", "selectionReasons", "citySignals"],
            ),
            output_artifact="ResearchDossier",
            market_metadata=SkillMarketMetadata(
                owner="research-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["research", "destination-discovery", "artifact-first"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="AttractionResearchSkill",
            description="Collect attraction-level evidence for candidate destinations.",
            tool_names=["query_attractions"],
            allowed_subagents=["research"],
            input_contract=SkillInputContract(
                required_context=["candidate_destinations"],
                optional_context=["travel_style", "must_visit_preferences"],
            ),
            output_contract=SkillOutputContract(
                artifact="ResearchDossier",
                fields=["attractionEvidence", "openingHours", "supportingFacts"],
            ),
            output_artifact="ResearchDossier",
            freshness_policy="prefer_recent",
            market_metadata=SkillMarketMetadata(
                owner="research-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["research", "attractions", "evidence"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="WeatherLookupSkill",
            description="Inject weather and seasonality evidence into planning decisions.",
            tool_names=["get_weather"],
            allowed_subagents=["research", "planning", "verification"],
            input_contract=SkillInputContract(
                required_context=["candidate_destinations"],
                optional_context=["travel_dates", "season", "route_constraints"],
            ),
            output_contract=SkillOutputContract(
                artifact="ResearchDossier",
                fields=["weatherSignals", "seasonalityNotes", "staleWarnings"],
            ),
            output_artifact="ResearchDossier",
            freshness_policy="must_refresh_if_stale",
            market_metadata=SkillMarketMetadata(
                owner="research-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["weather", "freshness", "cross-subagent"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="HotelQuoteSkill",
            description="Gather accommodation options used by budget and itinerary tradeoffs.",
            tool_names=["query_hotels"],
            allowed_subagents=["budget", "planning"],
            input_contract=SkillInputContract(
                required_context=["destinations", "stay_nights"],
                optional_context=["budget_mode", "hotel_preferences"],
            ),
            output_contract=SkillOutputContract(
                artifact="BudgetReport",
                fields=["hotelQuotes", "priceBands", "tradeoffNotes"],
            ),
            output_artifact="BudgetReport",
            freshness_policy="must_refresh_if_stale",
            evidence_required=True,
            market_metadata=SkillMarketMetadata(
                owner="budget-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["budget", "quotes", "evidence"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="BudgetAggregationSkill",
            description="Aggregate accommodation, transport, and activity costs into a budget view.",
            tool_names=["calculate_budget"],
            allowed_subagents=["budget"],
            input_contract=SkillInputContract(
                required_context=["hotel_quotes", "transport_estimates", "activity_estimates"],
                optional_context=["budget_mode", "group_size"],
            ),
            output_contract=SkillOutputContract(
                artifact="BudgetReport",
                fields=["executionBudget", "budgetSummary", "budgetRisks"],
            ),
            output_artifact="BudgetReport",
            evidence_required=True,
            market_metadata=SkillMarketMetadata(
                owner="budget-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["budget", "aggregation", "artifact-first"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="PlanSynthesisSkill",
            description="Transform user intent and evidence into itinerary steps.",
            tool_names=["plan_itinerary"],
            allowed_subagents=["planning"],
            input_contract=SkillInputContract(
                required_context=["user_intent", "research_dossier"],
                optional_context=["budget_report", "pace_preference", "route_constraints"],
            ),
            output_contract=SkillOutputContract(
                artifact="ItineraryDraft",
                fields=["dailySteps", "routeOutline", "planningExplanation"],
            ),
            output_artifact="ItineraryDraft",
            market_metadata=SkillMarketMetadata(
                owner="planning-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["planning", "itinerary", "artifact-first"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
        SkillContract(
            name="TravelTipsSkill",
            description="Provide destination-specific advice and policy-related reminders.",
            tool_names=["get_travel_tips"],
            allowed_subagents=["research", "verification"],
            input_contract=SkillInputContract(
                required_context=["destinations"],
                optional_context=["travel_dates", "traveler_profile", "policy_alerts"],
            ),
            output_contract=SkillOutputContract(
                artifact="ResearchDossier",
                fields=["travelTips", "policyNotes", "reminders"],
            ),
            output_artifact="ResearchDossier",
            market_metadata=SkillMarketMetadata(
                owner="verification-subagent",
                version="2026.03",
                docs_path=_SKILL_CATALOG_DOC,
                prompt_asset=_SKILL_PROMPT_ANCHOR,
                eval_fixture=_SKILL_EVAL_FIXTURE,
                tags=["verification", "tips", "policy"],
            ),
            metadata={"onboarding_doc": _SKILL_ONBOARDING_DOC},
        ),
    ]
