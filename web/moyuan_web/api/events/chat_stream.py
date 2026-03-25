"""Chat streaming SSE event registry and payload validators."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from ..schemas import normalize_artifact_patch, normalize_trip_plan_artifact


class _ChatStreamEventBase(BaseModel):
    """Common metadata carried by all public SSE payloads."""

    model_config = ConfigDict(extra="forbid")

    request_id: Optional[str] = None
    trace_id: Optional[str] = None


class SessionIdEvent(_ChatStreamEventBase):
    type: Literal["session_id"]
    session_id: str
    run_id: str


class ReasoningStartEvent(_ChatStreamEventBase):
    type: Literal["reasoning_start"]


class ReasoningChunkEvent(_ChatStreamEventBase):
    type: Literal["reasoning_chunk"]
    content: str


class ReasoningEndEvent(_ChatStreamEventBase):
    type: Literal["reasoning_end"]


class AnswerStartEvent(_ChatStreamEventBase):
    type: Literal["answer_start"]


class StageEvent(_ChatStreamEventBase):
    type: Literal["stage"]
    stage: Optional[str] = None
    label: Optional[str] = None
    progress: Optional[float] = None
    subagent: Optional[str] = None


class PlanPreviewEvent(_ChatStreamEventBase):
    type: Literal["plan_preview"]
    plan_id: Optional[str] = None
    intent: Optional[str] = None
    explanation: Optional[str] = None
    validation_status: Optional[str] = None
    validation_errors: list[Any] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    artifact: Optional[dict[str, Any]] = None
    artifact_patch: Optional[dict[str, Any]] = None
    subagent: Optional[str] = None
    skills: list[str] = Field(default_factory=list)

    @field_validator("artifact", mode="before")
    @classmethod
    def _normalize_artifact(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return normalize_trip_plan_artifact(value)

    @field_validator("artifact_patch", mode="before")
    @classmethod
    def _normalize_artifact_patch(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return normalize_artifact_patch(value)


class SubagentStartEvent(_ChatStreamEventBase):
    type: Literal["subagent_start"]
    subagent: str
    description: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    sequence: Optional[int] = None
    trigger: Optional[str] = None


class SubagentEndEvent(_ChatStreamEventBase):
    type: Literal["subagent_end"]
    subagent: str
    sequence: Optional[int] = None
    status: Optional[str] = None
    summary: Optional[str] = None


class ArtifactPatchEvent(_ChatStreamEventBase):
    type: Literal["artifact_patch"]
    subagent: str
    artifact_patch: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_patch", mode="before")
    @classmethod
    def _normalize_artifact_patch(cls, value: Any) -> dict[str, Any]:
        return normalize_artifact_patch(value)


class ToolStartEvent(_ChatStreamEventBase):
    type: Literal["tool_start"]
    tool: str
    subagent: Optional[str] = None


class ToolEndEvent(_ChatStreamEventBase):
    type: Literal["tool_end"]
    tool: str
    result: str = ""
    subagent: Optional[str] = None


class ChunkEvent(_ChatStreamEventBase):
    type: Literal["chunk"]
    content: str


class MetadataEvent(_ChatStreamEventBase):
    type: Literal["metadata"]
    run_id: str
    total_steps: int
    tools_used: list[str] = Field(default_factory=list)
    has_reasoning: bool
    reasoning_length: int
    answer_length: int
    plan_id: Optional[str] = None
    execution_stats: dict[str, Any] = Field(default_factory=dict)
    verification_passed: Optional[bool] = None
    stale_result_count: int = 0
    fallback_steps: int = 0
    failure_clusters: Any = None
    artifact: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact", mode="before")
    @classmethod
    def _normalize_artifact(cls, value: Any) -> dict[str, Any]:
        return normalize_trip_plan_artifact(value)


class ErrorEvent(_ChatStreamEventBase):
    type: Literal["error"]
    content: str
    run_id: Optional[str] = None


class DoneEvent(_ChatStreamEventBase):
    type: Literal["done"]
    run_id: str
    artifact: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact", mode="before")
    @classmethod
    def _normalize_artifact(cls, value: Any) -> dict[str, Any]:
        return normalize_trip_plan_artifact(value)


ChatStreamEvent = Annotated[
    Union[
        SessionIdEvent,
        ReasoningStartEvent,
        ReasoningChunkEvent,
        ReasoningEndEvent,
        AnswerStartEvent,
        StageEvent,
        PlanPreviewEvent,
        SubagentStartEvent,
        SubagentEndEvent,
        ArtifactPatchEvent,
        ToolStartEvent,
        ToolEndEvent,
        ChunkEvent,
        MetadataEvent,
        ErrorEvent,
        DoneEvent,
    ],
    Field(discriminator="type"),
]

CHAT_STREAM_EVENT_TYPES = (
    "session_id",
    "reasoning_start",
    "reasoning_chunk",
    "reasoning_end",
    "answer_start",
    "stage",
    "plan_preview",
    "subagent_start",
    "subagent_end",
    "artifact_patch",
    "tool_start",
    "tool_end",
    "chunk",
    "metadata",
    "error",
    "done",
)

_CHAT_STREAM_EVENT_ADAPTER = TypeAdapter(ChatStreamEvent)


def validate_chat_stream_payload(
    payload: dict[str, Any],
    *,
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate and normalize one public chat-stream payload."""

    normalized_payload = dict(payload)
    if request_id and "request_id" not in normalized_payload:
        normalized_payload["request_id"] = request_id
    if trace_id and "trace_id" not in normalized_payload:
        normalized_payload["trace_id"] = trace_id

    event = _CHAT_STREAM_EVENT_ADAPTER.validate_python(normalized_payload)
    return event.model_dump(exclude_none=True)


__all__ = [
    "CHAT_STREAM_EVENT_TYPES",
    "ArtifactPatchEvent",
    "ChatStreamEvent",
    "DoneEvent",
    "ErrorEvent",
    "MetadataEvent",
    "PlanPreviewEvent",
    "SessionIdEvent",
    "StageEvent",
    "SubagentEndEvent",
    "SubagentStartEvent",
    "ToolEndEvent",
    "ToolStartEvent",
    "validate_chat_stream_payload",
]
