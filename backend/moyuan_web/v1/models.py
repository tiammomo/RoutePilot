"""Strict public models for the RoutePilot V1 product control plane."""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields at every public V1 contract boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_public_id(prefix: str) -> str:
    """Create a sortable, non-sequential public identifier."""

    millis = int(time.time() * 1000)
    return f"{prefix}_{millis:013x}_{secrets.token_hex(10)}"


class Principal(StrictModel):
    """Authenticated actor and server-derived tenant context."""

    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    roles: frozenset[str] = Field(default_factory=frozenset)
    authorization_epoch: int = Field(default=0, ge=0)

    @field_serializer("roles")
    def serialize_roles(self, roles: frozenset[str]) -> list[str]:
        """Keep authenticated responses and audit projections deterministic."""

        return sorted(roles)


class TripStatus(StrEnum):
    """Stable Trip lifecycle values."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class TripCreateRequest(StrictModel):
    """Create a user-owned travel workspace."""

    title: str = Field(min_length=1, max_length=160)
    locale: str = Field(default="zh-CN", min_length=2, max_length=32)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class TripPatchRequest(StrictModel):
    """Patch mutable Trip metadata."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    locale: str | None = Field(default=None, min_length=2, max_length=32)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_change(self) -> "TripPatchRequest":
        """Require at least one explicit field."""

        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class TripView(StrictModel):
    """Public Trip representation."""

    trip_id: str
    tenant_id: str
    owner_id: str
    title: str
    locale: str
    timezone: str
    status: TripStatus
    version: int = Field(ge=1)
    current_artifact_id: str | None = None
    current_artifact_version: int | None = Field(default=None, ge=1)
    created_at: datetime
    updated_at: datetime


class TripListResponse(StrictModel):
    """Cursor-ready Trip list response."""

    items: list[TripView]
    next_cursor: str | None = None


class TripMemberRole(StrEnum):
    """Trip-scoped authorization roles."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class TripMemberUpsertRequest(StrictModel):
    """Grant or replace one Trip membership."""

    role: Literal["editor", "viewer"]


class TripMemberView(StrictModel):
    """Public member metadata without identity-provider claims."""

    trip_id: str
    tenant_id: str
    user_id: str
    role: TripMemberRole
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class TripMemberListResponse(StrictModel):
    items: list[TripMemberView]


class RunLifecycle(StrEnum):
    """Product Run lifecycle controlled only by RunCoordinator."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_RUN_STATES = {
    RunLifecycle.COMPLETED,
    RunLifecycle.FAILED,
    RunLifecycle.CANCELED,
}


class RunCommand(StrictModel):
    """Natural-language or structured command submitted to a Trip."""

    type: Literal[
        "trip.plan",
        "trip.replan",
        "artifact.select",
        "artifact.publish",
        "artifact.revoke",
    ]
    message: str = Field(min_length=1, max_length=20_000)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_structured_payload(self) -> "RunCommand":
        """Keep queued commands bounded and JSON-serializable."""

        try:
            encoded = json.dumps(
                self.payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("command payload must be finite JSON data") from exc
        if len(encoded) > 262_144:
            raise ValueError("command payload exceeds 256 KiB")
        return self


class ReplanDatePatch(StrictModel):
    """Optional replacement of the pinned brief's travel window."""

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_window(self) -> "ReplanDatePatch":
        if self.end_date < self.start_date:
            raise ValueError("patch date end cannot be before start")
        if (self.end_date - self.start_date).days > 30:
            raise ValueError("a V1 planning window cannot exceed 31 days")
        return self


class ReplanBudgetPatch(StrictModel):
    """Optional replacement of the pinned brief's bounded total budget."""

    min_amount: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$", max_length=32)
    max_amount: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$", max_length=32)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def validate_range(self) -> "ReplanBudgetPatch":
        from decimal import Decimal

        if Decimal(self.min_amount) > Decimal(self.max_amount):
            raise ValueError("patch budget min cannot exceed max")
        return self


class ReplanPreferencePatch(StrictModel):
    """Finite add/remove operations over the pinned brief preferences."""

    add: list[str] = Field(default_factory=list, max_length=20)
    remove: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("add", "remove")
    @classmethod
    def validate_values(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 256 for value in values):
            raise ValueError("preference values must contain 1 to 256 characters")
        if len({value.casefold() for value in values}) != len(values):
            raise ValueError("preference patch values must be unique")
        return values


class ReplanPatch(StrictModel):
    """Allowlisted structural changes applied to an immutable TripSnapshot."""

    dates: ReplanDatePatch | None = None
    budget: ReplanBudgetPatch | None = None
    preferences: ReplanPreferencePatch | None = None
    exclude_places: list[str] = Field(default_factory=list, max_length=50)
    retain_places: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("exclude_places", "retain_places")
    @classmethod
    def validate_places(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 256 for value in values):
            raise ValueError("place values must contain 1 to 256 characters")
        if len({value.casefold() for value in values}) != len(values):
            raise ValueError("place patch values must be unique")
        return values

    @model_validator(mode="after")
    def require_change(self) -> "ReplanPatch":
        if not self.model_fields_set or not any(
            (
                self.dates is not None,
                self.budget is not None,
                self.preferences is not None
                and bool(self.preferences.add or self.preferences.remove),
                bool(self.exclude_places),
                bool(self.retain_places),
            )
        ):
            raise ValueError("replan patch must contain at least one change")
        overlap = {value.casefold() for value in self.exclude_places}.intersection(
            value.casefold() for value in self.retain_places
        )
        if overlap:
            raise ValueError("a place cannot be both excluded and retained")
        return self


class RunCreateRequest(StrictModel):
    """Create a new asynchronous Product Run."""

    conversation_id: str | None = Field(default=None, max_length=128)
    command: RunCommand
    base_artifact_id: str | None = Field(default=None, min_length=3, max_length=96)
    base_artifact_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_planning_base(self) -> "RunCreateRequest":
        if self.command.type == "trip.replan":
            if self.base_artifact_id is None or self.base_artifact_version is None:
                raise ValueError("trip.replan requires base_artifact_id and base_artifact_version")
            raw_patch = self.command.payload.get("patch")
            if not isinstance(raw_patch, dict):
                raise ValueError("trip.replan requires command.payload.patch")
            ReplanPatch.model_validate(raw_patch)
        elif self.command.type == "trip.plan" and (
            self.base_artifact_id is not None or self.base_artifact_version is not None
        ):
            raise ValueError("trip.plan cannot carry a base artifact")
        return self


class RunControlRequest(StrictModel):
    """Compare-and-swap control request for cancel/resume."""

    expected_control_version: int = Field(ge=1)
    input: dict[str, Any] = Field(default_factory=dict)


class RunInputField(StrictModel):
    """One browser-safe field in a persisted Product Run interruption."""

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


class RunPendingInput(StrictModel):
    """Persisted, bounded input request safe to expose to Trip members."""

    request_id: str = Field(min_length=3, max_length=128)
    prompt: str = Field(min_length=1, max_length=1_000)
    fields: list[RunInputField] = Field(min_length=1, max_length=20)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("input expiry must include a timezone")
        return value


class RunResumeRequest(StrictModel):
    """CAS and typed values used to resume one waiting Product Run."""

    expected_control_version: int = Field(ge=1)
    request_id: str = Field(min_length=3, max_length=128)
    values: dict[str, Any] = Field(min_length=1, max_length=20)


def validate_run_input_values(
    pending: RunPendingInput,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Validate a resume payload against the exact persisted public schema."""

    import math

    fields = {field.field_id: field for field in pending.fields}
    if set(values) - set(fields):
        raise ValueError("resume input contains unknown fields")
    if any(field.required and field.field_id not in values for field in pending.fields):
        raise ValueError("resume input is missing required fields")
    normalized: dict[str, Any] = {}
    for field_id, value in values.items():
        field = fields[field_id]
        if field.input_type == "text":
            if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
                raise ValueError("text input must contain 1 to 2000 characters")
            normalized[field_id] = value.strip()
        elif field.input_type == "date":
            if not isinstance(value, str):
                raise ValueError("date input must be an ISO date")
            try:
                normalized[field_id] = date.fromisoformat(value).isoformat()
            except ValueError:
                raise ValueError("date input must be an ISO date") from None
        elif field.input_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("number input must be finite")
            if not math.isfinite(float(value)):
                raise ValueError("number input must be finite")
            normalized[field_id] = value
        elif field.input_type == "single_select":
            if not isinstance(value, str) or value not in field.options:
                raise ValueError("single-select input is not an allowed option")
            normalized[field_id] = value
        elif field.input_type == "multi_select":
            if (
                not isinstance(value, list)
                or any(not isinstance(item, str) or item not in field.options for item in value)
                or len(value) != len(set(value))
            ):
                raise ValueError("multi-select input contains invalid options")
            normalized[field_id] = value
        elif field.input_type == "confirmation":
            if not isinstance(value, bool):
                raise ValueError("confirmation input must be boolean")
            normalized[field_id] = value
    return normalized


class RunView(StrictModel):
    """Current Product Run snapshot."""

    run_id: str
    trip_id: str
    tenant_id: str
    actor_id: str
    trace_id: str
    lifecycle_state: RunLifecycle
    phase: str
    control_version: int = Field(ge=1)
    command: RunCommand
    base_artifact_id: str | None = None
    base_artifact_version: int | None = None
    pending_input: RunPendingInput | None = None
    result_artifact_id: str | None = None
    result_artifact_version: int | None = None
    public_error_code: str | None = None
    created_at: datetime
    updated_at: datetime


PUBLIC_EVENT_TYPES = Literal[
    "run.accepted",
    "run.lifecycle_changed",
    "run.phase_changed",
    "agent.activity",
    "artifact.candidate_updated",
    "artifact.published",
    "citation.added",
    "risk.detected",
    "input.required",
    "approval.required",
    "run.completed",
    "run.failed",
    "run.canceled",
    "heartbeat",
]


class RunEvent(StrictModel):
    """Strict browser-safe event projection."""

    event_id: str
    schema_version: Literal[1] = 1
    seq: int = Field(ge=1)
    type: PUBLIC_EVENT_TYPES
    occurred_at: datetime
    trip_id: str
    run_id: str
    trace_id: str
    audience: Literal["trip_members"] = "trip_members"
    data: dict[str, Any] = Field(default_factory=dict)


class ArtifactStatus(StrEnum):
    """Versioned Artifact publication states."""

    CANDIDATE = "candidate"
    SELECTED = "selected"
    VALIDATED = "validated"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class ArtifactView(StrictModel):
    """Immutable versioned product Artifact."""

    artifact_id: str
    version: int = Field(ge=1)
    trip_id: str
    tenant_id: str
    artifact_type: str
    schema_version: int = Field(ge=1)
    status: ArtifactStatus
    content: dict[str, Any]
    created_by: str
    created_at: datetime
    parent_version: int | None = Field(default=None, ge=1)


MAX_ARTIFACT_CONTENT_BYTES = 1_048_576


def _validate_artifact_content(content: dict[str, Any]) -> dict[str, Any]:
    """Accept finite JSON objects only and keep inline Artifact edits bounded."""

    try:
        encoded = json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError("artifact content must be finite JSON data") from exc
    if len(encoded) > MAX_ARTIFACT_CONTENT_BYTES:
        raise ValueError("artifact content exceeds 1 MiB")
    return content


class ArtifactPatchRequest(StrictModel):
    """Create an immutable candidate version from the latest Artifact version."""

    base_version: int = Field(ge=1)
    content: dict[str, Any]

    @model_validator(mode="after")
    def bound_content(self) -> "ArtifactPatchRequest":
        _validate_artifact_content(self.content)
        return self


class ArtifactCommandRequest(StrictModel):
    """CAS-protected Artifact lifecycle command."""

    type: Literal["artifact.select", "artifact.publish", "artifact.revoke"]
    base_version: int = Field(ge=1)

    @field_validator("type", mode="before")
    @classmethod
    def qualify_command(cls, value: Any) -> Any:
        """Normalize concise API names to canonical domain command names."""

        if value in {"select", "publish", "revoke"}:
            return f"artifact.{value}"
        return value


class ArtifactListResponse(StrictModel):
    """Artifact list for one Trip."""

    items: list[ArtifactView]


class ProblemDetail(StrictModel):
    """Stable public error detail without internal exception text."""

    code: str
    message: str
    retryable: bool = False
    trace_id: str | None = None
