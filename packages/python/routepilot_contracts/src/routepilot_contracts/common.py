"""Shared value objects for RoutePilot version-one contracts."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)


class ContractModel(BaseModel):
    """Strict, immutable base class used by every public contract object."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_:-]{2,127}$", min_length=3, max_length=128),
]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=2_000)]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=256)]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
DecimalAmount = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$", max_length=32),
]


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone name") from exc
    return value


IanaTimezone = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(_validate_timezone),
    WithJsonSchema(
        {
            "type": "string",
            "format": "iana-time-zone",
            "minLength": 1,
            "maxLength": 64,
            "examples": ["Asia/Shanghai"],
        }
    ),
]


class ArtifactType(StrEnum):
    TRIP_BRIEF = "TripBrief"
    EVIDENCE_BUNDLE = "EvidenceBundle"
    CANDIDATE_SET = "CandidateSet"
    ITINERARY_PLAN = "ItineraryPlan"
    CONSTRAINT_REPORT = "ConstraintReport"
    SEMANTIC_RISK_REPORT = "SemanticRiskReport"
    VALIDATION_REPORT = "ValidationReport"
    TRIP_SNAPSHOT = "TripSnapshot"
    SHARE_SNAPSHOT = "ShareSnapshot"


class SourceKind(StrEnum):
    USER = "user"
    RAG = "rag"
    PROVIDER = "provider"
    AGENT = "agent"
    POLICY = "policy"
    SYSTEM = "system"


class CoordinateSystem(StrEnum):
    WGS84 = "WGS84"
    GCJ02 = "GCJ-02"
    BD09 = "BD-09"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActorRef(ContractModel):
    actor_type: Literal["user", "agent", "service", "migration"]
    actor_id: Identifier


class VersionedComponent(ContractModel):
    name: ShortText
    version: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class SourceRef(ContractModel):
    """A safe, versioned provenance pointer; never contains provider raw payloads."""

    source_id: Identifier
    kind: SourceKind
    name: ShortText
    version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    uri: AnyHttpUrl | None = None
    retrieved_at: AwareDatetime
    publisher: ShortText | None = None
    license: ShortText | None = None


class ArtifactRef(ContractModel):
    artifact_type: ArtifactType
    artifact_id: Identifier
    schema_version: Literal[1]
    version: Annotated[int, Field(ge=1)]


class GeoPoint(ContractModel):
    latitude: Annotated[Decimal, Field(ge=Decimal("-90"), le=Decimal("90"))]
    longitude: Annotated[Decimal, Field(ge=Decimal("-180"), le=Decimal("180"))]
    coordinate_system: CoordinateSystem
    accuracy_meters: Annotated[Decimal, Field(gt=0)] | None = None


class ProviderPlaceId(ContractModel):
    provider: ShortText
    place_id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    version: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class PlaceRef(ContractModel):
    place_id: Identifier
    display_name: ShortText
    address: ShortText | None = None
    country_code: CountryCode
    timezone: IanaTimezone
    location: GeoPoint
    provider_ids: list[ProviderPlaceId] = Field(default_factory=list, max_length=16)
    source: SourceRef


class MoneyRange(ContractModel):
    min_amount: DecimalAmount
    max_amount: DecimalAmount
    currency: CurrencyCode
    basis: Literal["per_person", "per_group", "per_room", "per_item", "total"]
    observed_at: AwareDatetime
    source: SourceRef

    @model_validator(mode="after")
    def validate_range(self) -> MoneyRange:
        try:
            minimum = Decimal(self.min_amount)
            maximum = Decimal(self.max_amount)
        except InvalidOperation as exc:  # pragma: no cover - guarded by the field pattern
            raise ValueError("money amounts must be decimal strings") from exc
        if minimum > maximum:
            raise ValueError("min_amount cannot exceed max_amount")
        return self


class TripDateRange(ContractModel):
    start_date: date
    end_date: date
    timezone: IanaTimezone
    flexibility_days: Annotated[int, Field(ge=0, le=31)] = 0

    @model_validator(mode="after")
    def validate_dates(self) -> TripDateRange:
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ZonedTimeRange(ContractModel):
    local_date: date
    start_local_time: time
    end_local_time: time
    end_day_offset: Literal[0, 1] = 0
    timezone: IanaTimezone

    @model_validator(mode="after")
    def validate_times(self) -> ZonedTimeRange:
        if self.end_day_offset == 0 and self.end_local_time <= self.start_local_time:
            raise ValueError("end_local_time must be later than start_local_time")
        return self


class Freshness(ContractModel):
    observed_at: AwareDatetime
    valid_until: AwareDatetime | None = None
    status: FreshnessStatus
    source: SourceRef

    @model_validator(mode="after")
    def validate_window(self) -> Freshness:
        if self.valid_until is not None and self.valid_until < self.observed_at:
            raise ValueError("valid_until cannot be before observed_at")
        return self


class Citation(ContractModel):
    citation_id: Identifier
    evidence_id: Identifier
    title: ShortText
    locator: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    source: SourceRef


class TransitLeg(ContractModel):
    mode: Literal["walk", "bike", "transit", "taxi", "drive", "rail", "flight", "ferry"]
    duration_min_minutes: Annotated[int, Field(ge=0, le=10_080)]
    duration_max_minutes: Annotated[int, Field(ge=0, le=10_080)]
    distance_meters: Annotated[int, Field(ge=0)]
    provider_snapshot_ref: SourceRef

    @model_validator(mode="after")
    def validate_duration(self) -> TransitLeg:
        if self.duration_min_minutes > self.duration_max_minutes:
            raise ValueError("minimum duration cannot exceed maximum duration")
        return self


class ArtifactBase(ContractModel):
    """Metadata shared by every immutable artifact version."""

    artifact_id: Identifier
    schema_version: Literal[1]
    version: Annotated[int, Field(ge=1)]
    created_at: AwareDatetime
    created_by: ActorRef
    reason: NonEmptyText
