"""Artifact contract schemas shared by stream and route-facing payloads."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class _ArtifactModel(BaseModel):
    """Permissive base model for artifact payload validation at the API boundary."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TripIntentArtifact(_ArtifactModel):
    """Structured intent summary captured for one trip-planning run."""

    name: str = "general"
    confidence: Any = None
    entities: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


class ResearchEvidenceArtifact(_ArtifactModel):
    """One evidence item collected during research-oriented tool calls."""

    tool: Optional[str] = None
    status: Optional[str] = None
    query: Optional[str] = None


class ResearchDossierArtifact(_ArtifactModel):
    """Research summary and evidence bundle surfaced to the client."""

    summary: str = ""
    evidence: list[ResearchEvidenceArtifact] = Field(default_factory=list)
    destinations: list[str] = Field(default_factory=list)
    source_tools: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("source_tools", "sourceTools"),
        serialization_alias="sourceTools",
    )


class ItineraryDraftArtifact(_ArtifactModel):
    """Draft plan steps and validation details for the itinerary stage."""

    plan_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("plan_id", "planId"),
        serialization_alias="planId",
    )
    explanation: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    validation_status: str = Field(
        default="pass",
        validation_alias=AliasChoices("validation_status", "validationStatus"),
        serialization_alias="validationStatus",
    )
    validation_errors: list[Any] = Field(
        default_factory=list,
        validation_alias=AliasChoices("validation_errors", "validationErrors"),
        serialization_alias="validationErrors",
    )


class BudgetReportArtifact(_ArtifactModel):
    """Budget and runtime-cost summary attached to the artifact payload."""

    summary: dict[str, Any] = Field(default_factory=dict)
    execution_budget: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("execution_budget", "executionBudget"),
        serialization_alias="executionBudget",
    )
    stale_result_count: int = Field(
        default=0,
        validation_alias=AliasChoices("stale_result_count", "staleResultCount"),
        serialization_alias="staleResultCount",
    )
    fallback_steps: int = Field(
        default=0,
        validation_alias=AliasChoices("fallback_steps", "fallbackSteps"),
        serialization_alias="fallbackSteps",
    )


class VerificationReportArtifact(_ArtifactModel):
    """Verification outcome, retry hints, and issue list for one run."""

    passed: Optional[bool] = None
    should_retry: bool = Field(
        default=False,
        validation_alias=AliasChoices("should_retry", "shouldRetry"),
        serialization_alias="shouldRetry",
    )
    issues: list[Any] = Field(default_factory=list)
    refresh_targets: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("refresh_targets", "refreshTargets"),
        serialization_alias="refreshTargets",
    )
    summary: str = ""


class TripPlanArtifact(_ArtifactModel):
    """Top-level artifact envelope shared across stream and history payloads."""

    intent: TripIntentArtifact = Field(default_factory=TripIntentArtifact)
    research: ResearchDossierArtifact = Field(default_factory=ResearchDossierArtifact)
    itinerary: ItineraryDraftArtifact = Field(default_factory=ItineraryDraftArtifact)
    budget: BudgetReportArtifact = Field(default_factory=BudgetReportArtifact)
    verification: VerificationReportArtifact = Field(default_factory=VerificationReportArtifact)
    answer: str = ""
    reasoning: str = ""
    tools_used: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("tools_used", "toolsUsed"),
        serialization_alias="toolsUsed",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class TripIntentArtifactPatch(_ArtifactModel):
    """Partial update payload for the intent portion of a trip artifact."""

    name: Optional[str] = None
    confidence: Any = None
    entities: Optional[dict[str, Any]] = None
    detail: Optional[dict[str, Any]] = None


class ResearchDossierArtifactPatch(_ArtifactModel):
    """Partial update payload for research dossier fields."""

    summary: Optional[str] = None
    evidence: Optional[list[dict[str, Any]]] = None
    destinations: Optional[list[str]] = None
    source_tools: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("source_tools", "sourceTools"),
        serialization_alias="sourceTools",
    )


class ItineraryDraftArtifactPatch(_ArtifactModel):
    """Partial update payload for itinerary draft fields."""

    plan_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("plan_id", "planId"),
        serialization_alias="planId",
    )
    explanation: Optional[str] = None
    steps: Optional[list[dict[str, Any]]] = None
    validation_status: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("validation_status", "validationStatus"),
        serialization_alias="validationStatus",
    )
    validation_errors: Optional[list[Any]] = Field(
        default=None,
        validation_alias=AliasChoices("validation_errors", "validationErrors"),
        serialization_alias="validationErrors",
    )


class BudgetReportArtifactPatch(_ArtifactModel):
    """Partial update payload for budget report fields."""

    summary: Optional[dict[str, Any]] = None
    execution_budget: Optional[dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("execution_budget", "executionBudget"),
        serialization_alias="executionBudget",
    )
    stale_result_count: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("stale_result_count", "staleResultCount"),
        serialization_alias="staleResultCount",
    )
    fallback_steps: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("fallback_steps", "fallbackSteps"),
        serialization_alias="fallbackSteps",
    )


class VerificationReportArtifactPatch(_ArtifactModel):
    """Partial update payload for verification report fields."""

    passed: Optional[bool] = None
    should_retry: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices("should_retry", "shouldRetry"),
        serialization_alias="shouldRetry",
    )
    issues: Optional[list[Any]] = None
    refresh_targets: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("refresh_targets", "refreshTargets"),
        serialization_alias="refreshTargets",
    )
    summary: Optional[str] = None


class ArtifactPatch(_ArtifactModel):
    """Incremental artifact patch envelope used by streamed updates."""

    intent: Optional[TripIntentArtifactPatch] = None
    research: Optional[ResearchDossierArtifactPatch] = None
    itinerary: Optional[ItineraryDraftArtifactPatch] = None
    budget: Optional[BudgetReportArtifactPatch] = None
    verification: Optional[VerificationReportArtifactPatch] = None
    answer: Optional[str] = None
    reasoning: Optional[str] = None
    tools_used: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("tools_used", "toolsUsed"),
        serialization_alias="toolsUsed",
    )
    metadata: Optional[dict[str, Any]] = None


def normalize_trip_plan_artifact(payload: Any) -> dict[str, Any]:
    """Normalize one artifact payload into the public camelCase contract shape."""

    if not isinstance(payload, dict) or not payload:
        return {}
    return TripPlanArtifact.model_validate(payload).model_dump(by_alias=True)


def normalize_artifact_patch(payload: Any) -> dict[str, Any]:
    """Normalize one artifact patch into the public camelCase contract shape."""

    if not isinstance(payload, dict) or not payload:
        return {}
    return ArtifactPatch.model_validate(payload).model_dump(by_alias=True, exclude_none=True)


__all__ = [
    "ArtifactPatch",
    "BudgetReportArtifact",
    "ItineraryDraftArtifact",
    "ResearchDossierArtifact",
    "ResearchEvidenceArtifact",
    "TripIntentArtifact",
    "TripPlanArtifact",
    "VerificationReportArtifact",
    "normalize_artifact_patch",
    "normalize_trip_plan_artifact",
]
