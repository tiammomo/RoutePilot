"""Public parsing and validation entry points for all RoutePilot contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, TypeAlias

from pydantic import BaseModel, Field, TypeAdapter

from .artifacts import (
    CandidateSet,
    ConstraintReport,
    EvidenceBundle,
    ItineraryPlan,
    SemanticRiskReport,
    ShareSnapshot,
    TripBrief,
    TripSnapshot,
    ValidationReport,
)
from .events import RUN_EVENT_ADAPTER, RunEvent


Artifact: TypeAlias = Annotated[
    TripBrief
    | EvidenceBundle
    | CandidateSet
    | ItineraryPlan
    | ConstraintReport
    | SemanticRiskReport
    | ValidationReport
    | TripSnapshot
    | ShareSnapshot,
    Field(discriminator="artifact_type"),
]

ARTIFACT_ADAPTER: TypeAdapter[Artifact] = TypeAdapter(Artifact)
CONTRACT_MODELS: Mapping[str, type[BaseModel]] = {
    "TripBrief@1": TripBrief,
    "EvidenceBundle@1": EvidenceBundle,
    "CandidateSet@1": CandidateSet,
    "ItineraryPlan@1": ItineraryPlan,
    "ConstraintReport@1": ConstraintReport,
    "SemanticRiskReport@1": SemanticRiskReport,
    "ValidationReport@1": ValidationReport,
    "TripSnapshot@1": TripSnapshot,
    "ShareSnapshot@1": ShareSnapshot,
}


def validate_artifact(payload: Any) -> Artifact:
    """Validate an artifact selected by its ``artifact_type`` discriminator."""

    return ARTIFACT_ADAPTER.validate_python(payload)


def validate_run_event(payload: Any) -> RunEvent:
    """Validate a browser-safe RunEvent v1 envelope and its type-specific data."""

    return RUN_EVENT_ADAPTER.validate_python(payload)


def validate_contract(contract: str, payload: Any) -> BaseModel:
    """Validate a payload by an explicit ``Name@major`` contract identifier.

    ``RunEvent@1`` is a discriminated union; artifact contracts are immutable
    Pydantic models. Unknown names fail closed instead of trying to infer a
    compatible version.
    """

    if contract == "RunEvent@1":
        return validate_run_event(payload)
    try:
        model = CONTRACT_MODELS[contract]
    except KeyError as exc:
        supported = ", ".join((*CONTRACT_MODELS, "RunEvent@1"))
        raise ValueError(f"unsupported contract {contract!r}; supported: {supported}") from exc
    return model.model_validate(payload)
