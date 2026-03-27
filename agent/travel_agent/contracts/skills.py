"""Skill-layer contracts bridging subagents, governance, and low-level tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class SkillInputContract:
    """Describe the context a skill expects before it is safe to run."""

    required_context: list[str] = field(default_factory=list)
    optional_context: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillOutputContract:
    """Describe the structured result shape produced by one skill."""

    artifact: Optional[str] = None
    fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillMarketMetadata:
    """Track ownership and onboarding hooks for one cataloged skill."""

    owner: str = "travel-agent-platform"
    version: str = "2026.03"
    docs_path: Optional[str] = None
    prompt_asset: Optional[str] = None
    eval_fixture: Optional[str] = None
    onboarding_requirements: list[str] = field(
        default_factory=lambda: ["schema", "tests", "docs", "eval"]
    )
    status: str = "active"
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillSelectionPolicy:
    """Describe when one subagent should prioritize a skill over its peers."""

    priority: int = 100
    intent_signals: list[str] = field(default_factory=list)
    preferred_context: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillContract:
    """Capability contract describing one reusable domain skill."""

    name: str
    description: str
    tool_names: list[str] = field(default_factory=list)
    allowed_subagents: list[str] = field(default_factory=list)
    input_contract: SkillInputContract = field(default_factory=SkillInputContract)
    output_contract: SkillOutputContract = field(default_factory=SkillOutputContract)
    freshness_policy: str = "best_effort"
    fallback_policy: str = "graceful_degrade"
    output_artifact: Optional[str] = None
    evidence_required: bool = False
    market_metadata: SkillMarketMetadata = field(default_factory=SkillMarketMetadata)
    selection_policy: SkillSelectionPolicy = field(default_factory=SkillSelectionPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Keep the legacy `output_artifact` field aligned with the structured contract."""
        if self.output_artifact and not self.output_contract.artifact:
            self.output_contract.artifact = self.output_artifact
        elif self.output_contract.artifact and self.output_artifact is None:
            self.output_artifact = self.output_contract.artifact

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary for diagnostics and docs."""
        payload = asdict(self)
        if self.output_artifact and not payload["output_contract"].get("artifact"):
            payload["output_contract"]["artifact"] = self.output_artifact
        return payload
