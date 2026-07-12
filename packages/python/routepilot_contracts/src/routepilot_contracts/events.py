"""Strict browser-safe RunEvent v1 contract."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import AwareDatetime, Field, TypeAdapter

from .common import (
    ArtifactRef,
    Citation,
    ContractModel,
    Identifier,
    NonEmptyText,
    Severity,
    ShortText,
)


LifecycleState: TypeAlias = Literal[
    "queued",
    "running",
    "waiting_input",
    "waiting_approval",
    "cancel_requested",
    "completed",
    "failed",
    "canceled",
]
RunPhase: TypeAlias = Literal[
    "accepted",
    "clarification",
    "research",
    "planning",
    "validation",
    "approval",
    "publishing",
    "finalizing",
    "finished",
]


class RunAcceptedData(ContractModel):
    lifecycle_state: Literal["queued"]
    phase: Literal["accepted"]
    control_version: Annotated[int, Field(ge=1)]


class LifecycleChangedData(ContractModel):
    previous_state: LifecycleState
    lifecycle_state: LifecycleState
    control_version: Annotated[int, Field(ge=1)]
    reason_code: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class PhaseChangedData(ContractModel):
    previous_phase: RunPhase
    phase: RunPhase
    progress_percent: Annotated[int, Field(ge=0, le=100)]
    label: ShortText | None = None
    control_version: Annotated[int, Field(ge=1)] | None = None


class PublicSourceSummary(ContractModel):
    kind: Literal["rag", "provider", "knowledge_base"]
    name: ShortText
    version: Annotated[str, Field(min_length=1, max_length=128)]


class AgentActivityData(ContractModel):
    agent: Literal[
        "orchestrator",
        "research",
        "planner",
        "validation",
        "semantic_verifier",
    ]
    activity: Annotated[str, Field(min_length=1, max_length=128)]
    status: Literal["started", "progress", "completed", "failed"]
    duration_ms: Annotated[int, Field(ge=0)] | None = None
    sources: list[PublicSourceSummary] = Field(default_factory=list, max_length=50)
    control_version: Annotated[int, Field(ge=1)] | None = None


class ArtifactChangedData(ContractModel):
    artifact_ref: ArtifactRef
    status: Literal[
        "generated", "candidate", "selected", "validated", "published", "superseded", "rejected", "revoked"
    ]
    control_version: Annotated[int, Field(ge=1)] | None = None


class CitationAddedData(ContractModel):
    citation: Citation
    artifact_ref: ArtifactRef
    control_version: Annotated[int, Field(ge=1)] | None = None


class RiskDetectedData(ContractModel):
    risk_id: Identifier
    severity: Severity
    message: NonEmptyText
    artifact_ref: ArtifactRef | None = None
    control_version: Annotated[int, Field(ge=1)] | None = None


class InputField(ContractModel):
    field_id: Identifier
    label: ShortText
    input_type: Literal["text", "date", "number", "single_select", "multi_select", "confirmation"]
    required: bool
    options: list[ShortText] = Field(default_factory=list, max_length=50)


class InputRequiredData(ContractModel):
    request_id: Identifier
    prompt: NonEmptyText
    fields: list[InputField] = Field(min_length=1, max_length=20)
    expires_at: AwareDatetime | None = None
    control_version: Annotated[int, Field(ge=1)] | None = None


class ApprovalRequiredData(ContractModel):
    approval_id: Identifier
    prompt: NonEmptyText
    artifact_ref: ArtifactRef
    expires_at: AwareDatetime | None = None
    control_version: Annotated[int, Field(ge=1)] | None = None


class RunCompletedData(ContractModel):
    lifecycle_state: Literal["completed"]
    snapshot_ref: ArtifactRef
    duration_ms: Annotated[int, Field(ge=0)]
    control_version: Annotated[int, Field(ge=1)] | None = None


class PublicError(ContractModel):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
    message: NonEmptyText
    retryable: bool


class RunFailedData(ContractModel):
    lifecycle_state: Literal["failed"]
    failed_phase: RunPhase
    error: PublicError
    control_version: Annotated[int, Field(ge=1)] | None = None


class RunCanceledData(ContractModel):
    lifecycle_state: Literal["canceled"]
    canceled_by: Literal["user", "system", "operator"]
    reason: NonEmptyText | None = None
    control_version: Annotated[int, Field(ge=1)] | None = None


class HeartbeatData(ContractModel):
    server_time: AwareDatetime


class RunEventBase(ContractModel):
    event_id: Identifier
    schema_version: Literal[1]
    seq: Annotated[int, Field(ge=1)]
    occurred_at: AwareDatetime
    trip_id: Identifier
    run_id: Identifier
    trace_id: Identifier
    audience: Literal["trip_members"]


class RunAcceptedEvent(RunEventBase):
    type: Literal["run.accepted"]
    data: RunAcceptedData


class RunLifecycleChangedEvent(RunEventBase):
    type: Literal["run.lifecycle_changed"]
    data: LifecycleChangedData


class RunPhaseChangedEvent(RunEventBase):
    type: Literal["run.phase_changed"]
    data: PhaseChangedData


class AgentActivityEvent(RunEventBase):
    type: Literal["agent.activity"]
    data: AgentActivityData


class ArtifactCandidateUpdatedEvent(RunEventBase):
    type: Literal["artifact.candidate_updated"]
    data: ArtifactChangedData


class ArtifactPublishedEvent(RunEventBase):
    type: Literal["artifact.published"]
    data: ArtifactChangedData


class CitationAddedEvent(RunEventBase):
    type: Literal["citation.added"]
    data: CitationAddedData


class RiskDetectedEvent(RunEventBase):
    type: Literal["risk.detected"]
    data: RiskDetectedData


class InputRequiredEvent(RunEventBase):
    type: Literal["input.required"]
    data: InputRequiredData


class ApprovalRequiredEvent(RunEventBase):
    type: Literal["approval.required"]
    data: ApprovalRequiredData


class RunCompletedEvent(RunEventBase):
    type: Literal["run.completed"]
    data: RunCompletedData


class RunFailedEvent(RunEventBase):
    type: Literal["run.failed"]
    data: RunFailedData


class RunCanceledEvent(RunEventBase):
    type: Literal["run.canceled"]
    data: RunCanceledData


class HeartbeatEvent(RunEventBase):
    type: Literal["heartbeat"]
    data: HeartbeatData


RunEvent: TypeAlias = Annotated[
    RunAcceptedEvent
    | RunLifecycleChangedEvent
    | RunPhaseChangedEvent
    | AgentActivityEvent
    | ArtifactCandidateUpdatedEvent
    | ArtifactPublishedEvent
    | CitationAddedEvent
    | RiskDetectedEvent
    | InputRequiredEvent
    | ApprovalRequiredEvent
    | RunCompletedEvent
    | RunFailedEvent
    | RunCanceledEvent
    | HeartbeatEvent,
    Field(discriminator="type"),
]

RUN_EVENT_ADAPTER: TypeAdapter[RunEvent] = TypeAdapter(RunEvent)
RUN_EVENT_MODELS = (
    RunAcceptedEvent,
    RunLifecycleChangedEvent,
    RunPhaseChangedEvent,
    AgentActivityEvent,
    ArtifactCandidateUpdatedEvent,
    ArtifactPublishedEvent,
    CitationAddedEvent,
    RiskDetectedEvent,
    InputRequiredEvent,
    ApprovalRequiredEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunCanceledEvent,
    HeartbeatEvent,
)
