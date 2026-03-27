"""Base classes for minimal supervisor subagents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..contracts import SkillContract


@dataclass(slots=True)
class SkillSelectionDecision:
    """Describe one skill candidate within a subagent selection plan."""

    skill: str
    status: str
    priority: int
    matched_intent_signals: list[str] = field(default_factory=list)
    matched_preferred_context: list[str] = field(default_factory=list)
    missing_required_context: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of one selection decision."""
        return {
            "skill": self.skill,
            "status": self.status,
            "priority": self.priority,
            "matched_intent_signals": list(self.matched_intent_signals),
            "matched_preferred_context": list(self.matched_preferred_context),
            "missing_required_context": list(self.missing_required_context),
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class BaseSubagent:
    """Base object representing one domain-focused subagent."""

    name: str
    description: str
    skills: list[SkillContract] = field(default_factory=list)

    def skill_names(self) -> list[str]:
        """Return skill names owned by this subagent."""
        return [skill.name for skill in self.skills]

    def tool_names(self) -> list[str]:
        """Return tool names reachable through owned skills."""
        seen: list[str] = []
        for skill in self.skills:
            for tool_name in skill.tool_names:
                if tool_name not in seen:
                    seen.append(tool_name)
        return seen

    def selection_policy(self) -> list[dict[str, Any]]:
        """Return the static skill selection policy exposed by this subagent."""
        return [
            {
                "skill": skill.name,
                "priority": skill.selection_policy.priority,
                "intent_signals": list(skill.selection_policy.intent_signals),
                "required_context": list(skill.input_contract.required_context),
                "preferred_context": list(skill.selection_policy.preferred_context),
                "freshness_policy": skill.freshness_policy,
                "fallback_policy": skill.fallback_policy,
                "evidence_required": skill.evidence_required,
                "notes": list(skill.selection_policy.notes),
            }
            for skill in self._ordered_skills()
        ]

    def selection_plan(
        self,
        *,
        context_keys: Optional[Iterable[str]] = None,
        intent_signals: Optional[Iterable[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return a context-aware skill selection plan for one subagent run."""
        normalized_context = {_normalize_token(value) for value in context_keys or [] if _normalize_token(value)}
        normalized_signals = {_normalize_token(value) for value in intent_signals or [] if _normalize_token(value)}
        decisions: list[SkillSelectionDecision] = []
        for skill in self._ordered_skills():
            required_context = [_normalize_token(value) for value in skill.input_contract.required_context]
            preferred_context = [_normalize_token(value) for value in skill.selection_policy.preferred_context]
            policy_signals = [_normalize_token(value) for value in skill.selection_policy.intent_signals]

            missing_required_context = [
                raw_value
                for raw_value, normalized_value in zip(skill.input_contract.required_context, required_context)
                if normalized_value and normalized_value not in normalized_context
            ]
            matched_preferred_context = [
                raw_value
                for raw_value, normalized_value in zip(skill.selection_policy.preferred_context, preferred_context)
                if normalized_value and normalized_value in normalized_context
            ]
            matched_intent_signals = [
                raw_value
                for raw_value, normalized_value in zip(skill.selection_policy.intent_signals, policy_signals)
                if normalized_value and normalized_value in normalized_signals
            ]

            status = "ready"
            if missing_required_context:
                status = "blocked"
            elif normalized_signals and policy_signals and not matched_intent_signals:
                status = "standby"

            decisions.append(
                SkillSelectionDecision(
                    skill=skill.name,
                    status=status,
                    priority=skill.selection_policy.priority,
                    matched_intent_signals=matched_intent_signals,
                    matched_preferred_context=matched_preferred_context,
                    missing_required_context=missing_required_context,
                    notes=list(skill.selection_policy.notes),
                )
            )

        return [decision.to_dict() for decision in decisions]

    def start_event(
        self,
        *,
        session_id: str,
        run_id: Optional[str],
        sequence: int,
        trigger: str,
        chat_mode: Optional[str],
    ) -> dict[str, Any]:
        """Return a normalized subagent start event payload."""
        return {
            "type": "subagent_start",
            "subagent": self.name,
            "description": self.description,
            "skills": self.skill_names(),
            "tool_names": self.tool_names(),
            "session_id": session_id,
            "run_id": run_id,
            "sequence": sequence,
            "trigger": trigger,
            "chat_mode": chat_mode,
        }

    def end_event(
        self,
        *,
        session_id: str,
        run_id: Optional[str],
        sequence: int,
        status: str = "completed",
        summary: str = "",
    ) -> dict[str, Any]:
        """Return a normalized subagent end event payload."""
        return {
            "type": "subagent_end",
            "subagent": self.name,
            "session_id": session_id,
            "run_id": run_id,
            "sequence": sequence,
            "status": status,
            "summary": summary,
        }

    def artifact_patch_from_preview(self, preview: dict[str, Any]) -> dict[str, Any]:
        """Build a partial artifact patch from a plan preview payload."""
        _ = preview
        return {}

    def artifact_patch_from_done(
        self,
        done_event: dict[str, Any],
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> dict[str, Any]:
        """Build a partial artifact patch from the final done event."""
        _ = (done_event, user_message, session_id, chat_mode)
        return {}

    def _ordered_skills(self) -> list[SkillContract]:
        """Return skills in deterministic selection-policy order."""
        return sorted(
            self.skills,
            key=lambda skill: (skill.selection_policy.priority, skill.name),
        )


def _normalize_token(value: object) -> str:
    """Normalize a context key or intent signal for selection comparisons."""
    return str(value or "").strip().lower()
