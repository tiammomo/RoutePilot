"""Strict application models around the official A2A 1.0 wire types."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from .constants import MAX_ARTIFACTS_PER_MESSAGE, MAX_GOAL_CHARACTERS


ContractName: TypeAlias = Literal[
    "TripBrief@1",
    "EvidenceBundle@1",
    "CandidateSet@1",
    "ItineraryPlan@1",
    "ConstraintReport@1",
    "SemanticRiskReport@1",
    "ValidationReport@1",
    "TripSnapshot@1",
    "ShareSnapshot@1",
]


class StrictModel(BaseModel):
    """Reject unknown fields at the RoutePilot A2A application boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class A2AActor(StrictModel):
    """Server-derived caller identity; protocol tenant fields never grant access."""

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    roles: frozenset[str] = Field(default_factory=frozenset)
    authorization_epoch: int = Field(default=0, ge=0)


class DispatchMetadata(StrictModel):
    """RoutePilot extension metadata required on an initial A2A dispatch."""

    dispatch_id: str = Field(min_length=36, max_length=36)
    run_id: str = Field(min_length=3, max_length=160)
    deadline: AwareDatetime | None = None


class ArtifactInput(StrictModel):
    """A fully versioned input Artifact embedded in a structured Part."""

    contract: ContractName
    payload: dict[str, JsonValue]


class AgentInvocation(StrictModel):
    """Common, bounded invocation envelope used by all curated travel agents."""

    goal: str = Field(min_length=1, max_length=MAX_GOAL_CHARACTERS)
    artifacts: list[ArtifactInput] = Field(
        min_length=1,
        max_length=MAX_ARTIFACTS_PER_MESSAGE,
    )
    options: dict[str, JsonValue] = Field(default_factory=dict)


class InputField(StrictModel):
    """One typed field requested by an interrupted task."""

    field_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    label: str = Field(min_length=1, max_length=160)
    input_type: Literal[
        "text",
        "date",
        "number",
        "single_select",
        "multi_select",
        "confirmation",
    ]
    required: bool = True
    options: list[str] = Field(default_factory=list, max_length=50)


class TypedInputRequest(StrictModel):
    """Safe task interruption contract, never a model scratchpad."""

    request_id: str = Field(min_length=3, max_length=128)
    prompt: str = Field(min_length=1, max_length=1_000)
    fields: list[InputField] = Field(min_length=1, max_length=20)
    expires_at: AwareDatetime | None = None


class InputResponse(StrictModel):
    """Strict response to the current input-required interruption."""

    request_id: str = Field(min_length=3, max_length=128)
    values: dict[str, JsonValue] = Field(min_length=1, max_length=20)


class ArtifactOutput(StrictModel):
    """Validated structured Artifact emitted by an agent executor."""

    contract: ContractName
    payload: dict[str, JsonValue]
    artifact_id: str | None = Field(default=None, min_length=3, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class CompletedExecution(StrictModel):
    """Successful executor proposal; TaskService validates before publication."""

    kind: Literal["completed"] = "completed"
    artifacts: list[ArtifactOutput] = Field(min_length=1, max_length=8)


class InputRequiredExecution(StrictModel):
    """Executor interruption requesting typed caller input."""

    kind: Literal["input_required"] = "input_required"
    request: TypedInputRequest


class AuthRequiredExecution(StrictModel):
    """Dependency-auth interruption, distinct from ordinary user approval."""

    kind: Literal["auth_required"] = "auth_required"
    dependency: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=500)


class FailedExecution(StrictModel):
    """Safe public failure proposal with no exception or tool payload."""

    kind: Literal["failed"] = "failed"
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=500)


ExecutionResult: TypeAlias = Annotated[
    CompletedExecution | InputRequiredExecution | AuthRequiredExecution | FailedExecution,
    Field(discriminator="kind"),
]


class AgentExecutionContext(StrictModel):
    """Least-privilege execution context passed to one professional agent."""

    tenant_id: str
    actor_id: str
    agent_interface_id: str
    task_id: str
    context_id: str
    run_id: str
    dispatch_id: str
    deadline: AwareDatetime
    reference_task_ids: tuple[str, ...] = ()


class RunTaskRef(StrictModel):
    """Explicit Product Run to A2A Task mapping."""

    run_id: str
    tenant_id: str
    agent_interface_id: str
    task_id: str
    context_id: str
    dispatch_id: str
    status: str
    version: int = Field(ge=1)
    deadline: AwareDatetime


ContractValidator: TypeAlias = Callable[[str, dict[str, Any]], Any]


def default_contract_validator(contract: str, payload: dict[str, Any]) -> Any:
    """Validate against the shared contract package, failing closed if unavailable."""

    try:
        from routepilot_contracts.validation import validate_contract
    except ImportError:
        # Repository-source fallback used by tests before workspace packages are installed.
        from packages.python.routepilot_contracts.src.routepilot_contracts.validation import (
            validate_contract,
        )

    return validate_contract(contract, payload)


def ensure_aware_future(value: datetime, *, now: datetime) -> datetime:
    """Validate an aware future deadline without silently assuming a timezone."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("deadline must include a timezone")
    if value <= now:
        raise ValueError("deadline must be in the future")
    return value
