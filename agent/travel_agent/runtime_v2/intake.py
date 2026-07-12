"""Typed TripBrief intake backed by an allowlisted geocoding provider."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from agent.travel_agent.providers import (
    CacheScope,
    Coordinate,
    FreshnessStatus as ProviderFreshnessStatus,
    GeocodeCandidate,
    GeocodeRequest,
    GeocodeResult,
    ProviderCancelledError,
    ProviderCapability,
    ProviderCallContext,
    ProviderError,
    ProviderProvenance,
)
from routepilot_contracts.artifacts import (
    ConstraintSpec,
    TravelPreference,
    TravelerGroup,
    TripBrief,
)
from routepilot_contracts.common import (
    ActorRef,
    GeoPoint,
    MoneyRange,
    PlaceRef,
    SourceKind,
    SourceRef,
    TripDateRange,
)

from .shared import new_id, utc_now


DecimalText = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,4})?$", max_length=32),
]


class TripIntakeError(RuntimeError):
    """Safe structured-intake failure with a stable public code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GeocodeService(Protocol):
    """Narrow Provider Gateway capability used during intake."""

    async def geocode(
        self,
        request: GeocodeRequest,
        context: ProviderCallContext,
    ) -> GeocodeResult: ...


class ApprovedDestinationCatalog:
    """Operator-owned fallback for stable city centroids, never POI facts."""

    _VERSION = "cn-city-centroids-2026-07-12"
    _CITIES: dict[str, tuple[str, float, float]] = {
        "北京": ("北京市", 116.4074, 39.9042),
        "北京市": ("北京市", 116.4074, 39.9042),
        "上海": ("上海市", 121.4737, 31.2304),
        "上海市": ("上海市", 121.4737, 31.2304),
        "广州": ("广州市", 113.2644, 23.1291),
        "广州市": ("广州市", 113.2644, 23.1291),
        "杭州": ("杭州市", 120.1551, 30.2741),
        "杭州市": ("杭州市", 120.1551, 30.2741),
        "成都": ("成都市", 104.0665, 30.5723),
        "成都市": ("成都市", 104.0665, 30.5723),
        "西安": ("西安市", 108.9398, 34.3416),
        "西安市": ("西安市", 108.9398, 34.3416),
    }

    async def geocode(
        self,
        request: GeocodeRequest,
        context: ProviderCallContext,
    ) -> GeocodeResult:
        del context
        entry = self._CITIES.get(request.address.strip())
        now = utc_now()
        candidates: tuple[GeocodeCandidate, ...] = ()
        if entry is not None:
            formatted_address, longitude, latitude = entry
            candidates = (
                GeocodeCandidate(
                    formatted_address=formatted_address,
                    coordinate=Coordinate(
                        longitude=longitude,
                        latitude=latitude,
                        coordinate_system="WGS-84",
                    ),
                    country="中国",
                    city=formatted_address,
                ),
            )
        return GeocodeResult(
            candidates=candidates,
            provenance=ProviderProvenance(
                provider_id="routepilot-destination-catalog",
                provider_version=self._VERSION,
                capability=ProviderCapability.GEOCODE,
                observed_at=now,
                valid_until=now + timedelta(days=365),
                freshness_status=ProviderFreshnessStatus.FRESH,
            ),
        )


class ResilientGeocodeService:
    """Prefer live geocoding and fall back to the reviewed city catalog."""

    def __init__(
        self,
        primary: GeocodeService,
        fallback: GeocodeService | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or ApprovedDestinationCatalog()

    async def geocode(
        self,
        request: GeocodeRequest,
        context: ProviderCallContext,
    ) -> GeocodeResult:
        try:
            result = await self.primary.geocode(request, context)
            if result.candidates:
                return result
        except ProviderCancelledError:
            raise
        except ProviderError:
            pass
        return await self.fallback.geocode(request, context)


class StructuredTripRequest(BaseModel):
    """Explicit travel constraints submitted by the workbench or API client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str = Field(min_length=1, max_length=100)
    country_code: str = Field(default="CN", pattern=r"^[A-Z]{2}$")
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    start_date: date
    end_date: date
    adults: int = Field(default=1, ge=0, le=99)
    seniors: int = Field(default=0, ge=0, le=99)
    children_ages: list[int] = Field(default_factory=list, max_length=30)
    accessibility_needs: list[str] = Field(default_factory=list, max_length=20)
    budget_min: DecimalText
    budget_max: DecimalText
    currency: str = Field(default="CNY", pattern=r"^[A-Z]{3}$")
    preferences: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("children_ages")
    @classmethod
    def validate_child_ages(cls, value: list[int]) -> list[int]:
        if any(age < 0 or age > 17 for age in value):
            raise ValueError("children ages must be between 0 and 17")
        return value

    @field_validator("accessibility_needs", "preferences")
    @classmethod
    def bound_text_list(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 256 for item in cleaned):
            raise ValueError("list values must contain between 1 and 256 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_request(self) -> "StructuredTripRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if (self.end_date - self.start_date).days > 30:
            raise ValueError("a V1 planning window cannot exceed 31 days")
        if self.adults + self.seniors + len(self.children_ages) < 1:
            raise ValueError("at least one traveler is required")
        try:
            minimum = Decimal(self.budget_min)
            maximum = Decimal(self.budget_max)
        except InvalidOperation as exc:  # pragma: no cover - regex guards this path
            raise ValueError("budget must contain finite decimal values") from exc
        if minimum > maximum:
            raise ValueError("budget_min cannot exceed budget_max")
        return self


def _stable_identifier(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


class TripBriefFactory:
    """Resolve a destination and turn explicit user constraints into TripBrief@1."""

    def __init__(self, geocoder: GeocodeService, *, timeout_seconds: float = 5.0):
        self.geocoder = geocoder
        self.timeout_seconds = max(0.5, min(float(timeout_seconds), 15.0))

    async def build(
        self,
        request: StructuredTripRequest,
        *,
        tenant_id: str,
        actor_id: str,
        run_id: str,
    ) -> TripBrief:
        context = ProviderCallContext.with_timeout(
            tenant_id=tenant_id,
            actor_id=actor_id,
            operation_id=f"{run_id}:trip-intake-geocode",
            timeout_seconds=self.timeout_seconds,
            cache_scope=CacheScope.TENANT,
        )
        result = await self.geocoder.geocode(
            GeocodeRequest(address=request.destination, city=request.destination),
            context,
        )
        if not result.candidates:
            raise TripIntakeError(
                "DESTINATION_NOT_FOUND",
                "The destination could not be resolved by an approved provider.",
            )
        candidate = result.candidates[0]
        now = utc_now()
        provider_source = SourceRef(
            source_id=_stable_identifier(
                "source",
                f"{result.provenance.provider_id}:{request.destination}:{result.provenance.observed_at.isoformat()}",
            ),
            kind=SourceKind.PROVIDER,
            name=f"{result.provenance.provider_id} geocode",
            version=result.provenance.provider_version,
            retrieved_at=result.provenance.observed_at,
            publisher=result.provenance.provider_id,
        )
        user_source = SourceRef(
            source_id=new_id("source"),
            kind=SourceKind.USER,
            name="Trip workbench constraints",
            version="1",
            retrieved_at=now,
            publisher="RoutePilot user",
        )
        place = PlaceRef(
            place_id=_stable_identifier(
                "place",
                f"{result.provenance.provider_id}:{candidate.formatted_address}",
            ),
            display_name=request.destination,
            address=candidate.formatted_address,
            country_code=request.country_code,
            timezone=request.timezone,
            location=GeoPoint(
                latitude=str(candidate.coordinate.latitude),
                longitude=str(candidate.coordinate.longitude),
                coordinate_system=(
                    "WGS84"
                    if candidate.coordinate.coordinate_system == "WGS-84"
                    else candidate.coordinate.coordinate_system
                ),
            ),
            source=provider_source,
        )
        budget = MoneyRange(
            min_amount=request.budget_min,
            max_amount=request.budget_max,
            currency=request.currency,
            basis="total",
            observed_at=now,
            source=user_source,
        )
        date_window = TripDateRange(
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=request.timezone,
        )
        return TripBrief(
            artifact_id=new_id("artifact"),
            artifact_type="TripBrief",
            schema_version=1,
            version=1,
            created_at=now,
            created_by=ActorRef(
                actor_type="user",
                actor_id=_stable_identifier("user", actor_id),
            ),
            reason="将用户显式约束和经批准 Provider 解析的目的地固化为规划输入。",
            destination=place,
            date_window=date_window,
            travelers=TravelerGroup(
                adults=request.adults,
                seniors=request.seniors,
                children_ages=request.children_ages,
                accessibility_needs=request.accessibility_needs,
            ),
            budget=budget,
            preferences=[
                TravelPreference(
                    preference_id=f"preference_{index}_{new_id('pref')}",
                    category="other",
                    value=value,
                    priority=3,
                )
                for index, value in enumerate(request.preferences)
            ],
            constraints=[
                ConstraintSpec(
                    constraint_id=new_id("constraint"),
                    constraint_type="date",
                    hard=True,
                    priority=5,
                    description=(
                        f"旅行日期为 {request.start_date.isoformat()} 至 "
                        f"{request.end_date.isoformat()}。"
                    ),
                    source=user_source,
                ),
                ConstraintSpec(
                    constraint_id=new_id("constraint"),
                    constraint_type="budget",
                    hard=True,
                    priority=5,
                    description=(
                        f"总预算为 {request.budget_min}–{request.budget_max} "
                        f"{request.currency}。"
                    ),
                    source=user_source,
                ),
            ],
            source=user_source,
        )


__all__ = [
    "ApprovedDestinationCatalog",
    "GeocodeService",
    "ResilientGeocodeService",
    "StructuredTripRequest",
    "TripBriefFactory",
    "TripIntakeError",
]
