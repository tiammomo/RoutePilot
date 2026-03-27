"""Registry that binds subagents to skills and runtime event mapping."""

from __future__ import annotations

from typing import Iterable, Optional

from ..skills import SkillRegistry
from .base import BaseSubagent
from .budget import BudgetSubagent
from .planning import PlanningSubagent
from .research import ResearchSubagent
from .verification import VerificationSubagent


class SubagentRegistry:
    """Registry for enabled supervisor subagents and their tool mappings."""

    def __init__(self, subagents: Iterable[BaseSubagent]):
        """Initialize the registry with enabled subagent instances."""
        self._subagents = {subagent.name: subagent for subagent in subagents}

    def names(self) -> list[str]:
        """Return enabled subagent names in deterministic order."""
        return [name for name in ["research", "planning", "budget", "verification"] if name in self._subagents]

    def get(self, name: str) -> Optional[BaseSubagent]:
        """Return one subagent by name."""
        return self._subagents.get(name)

    def skill_names(self, name: str) -> list[str]:
        """Return skill names owned by the requested subagent."""
        subagent = self.get(name)
        return subagent.skill_names() if subagent is not None else []

    def selection_policy(self, name: str) -> list[dict[str, object]]:
        """Return the static skill selection policy for one subagent."""
        subagent = self.get(name)
        return subagent.selection_policy() if subagent is not None else []

    def selection_plan(
        self,
        name: str,
        *,
        context_keys: Optional[Iterable[str]] = None,
        intent_signals: Optional[Iterable[str]] = None,
    ) -> list[dict[str, object]]:
        """Return the context-aware skill selection plan for one subagent."""
        subagent = self.get(name)
        if subagent is None:
            return []
        return subagent.selection_plan(
            context_keys=context_keys,
            intent_signals=intent_signals,
        )

    def resolve_subagent_for_stage(
        self,
        *,
        stage: Optional[str],
        label: Optional[str] = None,
        explicit_subagent: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve the most likely subagent for one stage event."""
        if explicit_subagent in self._subagents:
            return explicit_subagent

        label_text = str(label or "")
        lowered = label_text.lower()
        if "budget" in lowered or "cost" in lowered or "预算" in label_text:
            return "budget" if "budget" in self._subagents else None
        if "计划" in label_text or "planning" in lowered:
            return "planning" if "planning" in self._subagents else None
        if "查询" in label_text or "research" in lowered:
            return "research" if "research" in self._subagents else None
        if "验证" in label_text or "verify" in lowered:
            return "verification" if "verification" in self._subagents else None
        if stage in {"budget", "costing"} and "budget" in self._subagents:
            return "budget"
        if stage == "query" and "research" in self._subagents:
            return "research"
        return None

    def resolve_subagent_for_tool(self, tool_name: str) -> Optional[str]:
        """Resolve the enabled subagent that owns the requested tool."""
        for name in self.names():
            subagent = self._subagents[name]
            if tool_name in subagent.tool_names():
                return name
        return None

    def preview_artifact_patch(self, preview: dict[str, object]) -> dict[str, object]:
        """Return the planning subagent patch for plan-preview mode."""
        planning = self.get("planning")
        if planning is None:
            return {}
        return planning.artifact_patch_from_preview(preview)

    def done_artifact_patches(
        self,
        done_event: dict[str, object],
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> dict[str, dict[str, object]]:
        """Return per-subagent artifact patches for the final stream event."""
        patches: dict[str, dict[str, object]] = {}
        for name in self.names():
            subagent = self._subagents[name]
            patch = subagent.artifact_patch_from_done(
                done_event,
                user_message=user_message,
                session_id=session_id,
                chat_mode=chat_mode,
            )
            if patch:
                patches[name] = patch
        return patches


def build_default_subagent_registry(skill_registry: SkillRegistry) -> SubagentRegistry:
    """Build the minimal phase-3 subagent registry."""
    return SubagentRegistry(
        [
            ResearchSubagent(
                name="research",
                description="Collect destination evidence and travel signals.",
                skills=skill_registry.for_subagent("research"),
            ),
            PlanningSubagent(
                name="planning",
                description="Turn intent and evidence into itinerary drafts.",
                skills=skill_registry.for_subagent("planning"),
            ),
            BudgetSubagent(
                name="budget",
                description="Estimate cost envelopes and tradeoff ranges.",
                skills=skill_registry.for_subagent("budget"),
            ),
            VerificationSubagent(
                name="verification",
                description="Audit consistency, freshness, and quality risk.",
                skills=skill_registry.for_subagent("verification"),
            ),
        ]
    )
