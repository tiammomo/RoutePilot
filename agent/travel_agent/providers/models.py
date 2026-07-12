"""Strict contracts for live travel-data providers.

Provider data is deliberately separate from RAG evidence.  These models carry
an observation/validity window on every successful live result so callers
cannot accidentally present cached facts as timeless knowledge.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Reject unknown fields at every provider boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class ProviderCapability(StrEnum):
    """Typed deterministic capabilities exposed to agents."""

    PLACE_SEARCH = "place_search"
    GEOCODE = "geocode"
    ROUTE_MATRIX = "route_matrix"
    OPENING_HOURS = "opening_hours"
    WEATHER = "weather"


class FreshnessStatus(StrEnum):
    """Freshness of one live-provider observation."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ProviderProvenance(StrictModel):
    """Safe source and freshness metadata attached to every result."""

    source_kind: Literal["live_provider"] = "live_provider"
    provider_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    provider_version: str = Field(min_length=1, max_length=80)
    capability: ProviderCapability
    observed_at: datetime
    valid_until: datetime
    freshness_status: FreshnessStatus

    @model_validator(mode="after")
    def validate_window(self) -> "ProviderProvenance":
        """Require aware, forward-moving validity timestamps."""

        if self.observed_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("provider timestamps must be timezone-aware")
        if self.valid_until < self.observed_at:
            raise ValueError("valid_until must not precede observed_at")
        if (
            self.freshness_status is FreshnessStatus.FRESH
            and self.valid_until == self.observed_at
        ):
            raise ValueError("fresh observations require a non-empty validity window")
        return self


class Coordinate(StrictModel):
    """Longitude/latitude pair with an explicit coordinate datum.

    AMap Web Service consumes GCJ-02 coordinates in mainland China.  The port
    retains the neutral field names and records the actual coordinate system on
    every input and result to prevent silent datum mixing.
    """

    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["GCJ-02", "WGS-84"]

    def as_amap_parameter(self) -> str:
        """Serialize within AMap's documented six-decimal limit."""

        return f"{self.longitude:.6f},{self.latitude:.6f}"


class PlaceSearchRequest(StrictModel):
    """Keyword or nearby POI search."""

    query: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=80)
    center: Coordinate | None = None
    radius_meters: int = Field(default=3_000, ge=1, le=50_000)
    category_codes: tuple[str, ...] = Field(default=(), max_length=20)
    limit: int = Field(default=20, ge=1, le=25)
    page: int = Field(default=1, ge=1, le=100)

    @field_validator("category_codes")
    @classmethod
    def validate_category_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Keep provider type filters bounded and delimiter-safe."""

        for item in value:
            if not item or len(item) > 16 or not item.replace("_", "").isalnum():
                raise ValueError("invalid category code")
        return value


class Place(StrictModel):
    """Normalized POI without provider-specific raw fields."""

    provider_place_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    coordinate: Coordinate
    address: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=300)
    category_code: str | None = Field(default=None, max_length=40)
    administrative_code: str | None = Field(default=None, max_length=20)


class PlaceSearchResult(StrictModel):
    """Normalized POI search result."""

    places: tuple[Place, ...] = Field(max_length=25)
    provenance: ProviderProvenance


class GeocodeRequest(StrictModel):
    """Forward geocoding request."""

    address: str = Field(min_length=2, max_length=500)
    city: str | None = Field(default=None, max_length=80)


class GeocodeCandidate(StrictModel):
    """One normalized forward-geocoding candidate."""

    formatted_address: str = Field(min_length=1, max_length=500)
    coordinate: Coordinate
    country: str | None = Field(default=None, max_length=80)
    province: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=80)
    district: str | None = Field(default=None, max_length=80)
    administrative_code: str | None = Field(default=None, max_length=20)


class GeocodeResult(StrictModel):
    """Normalized geocoding result."""

    candidates: tuple[GeocodeCandidate, ...] = Field(max_length=10)
    provenance: ProviderProvenance


class RouteMode(StrEnum):
    """Modes supported by the V1 matrix contract."""

    DRIVING = "driving"
    WALKING = "walking"


class RouteMatrixRequest(StrictModel):
    """Bounded many-to-many distance/duration request."""

    origins: tuple[Coordinate, ...] = Field(min_length=1, max_length=25)
    destinations: tuple[Coordinate, ...] = Field(min_length=1, max_length=10)
    mode: RouteMode = RouteMode.DRIVING


class RouteMatrixCell(StrictModel):
    """One origin/destination travel estimate."""

    origin_index: int = Field(ge=0)
    destination_index: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)


class RouteMatrixResult(StrictModel):
    """Normalized matrix with provider observation metadata."""

    cells: tuple[RouteMatrixCell, ...] = Field(max_length=250)
    coordinate_system: Literal["GCJ-02", "WGS-84"]
    provenance: ProviderProvenance


class OpeningHoursRequest(StrictModel):
    """Request live/opening-policy facts for provider place IDs."""

    provider_place_ids: tuple[str, ...] = Field(min_length=1, max_length=50)
    local_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("local_date")
    @classmethod
    def validate_local_date(cls, value: str | None) -> str | None:
        """Reject syntactically shaped but impossible calendar dates."""

        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("provider_place_ids")
    @classmethod
    def validate_provider_place_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject delimiter injection and duplicate IDs before AMap batching."""

        if len(value) != len(set(value)):
            raise ValueError("provider place IDs must be unique")
        for item in value:
            if (
                not item.isascii()
                or len(item) > 128
                or any(character not in "._:-" and not character.isalnum() for character in item)
            ):
                raise ValueError("provider place ID must be delimiter-safe ASCII alphanumeric")
        return value


class OpeningHoursEntry(StrictModel):
    """One provider-supplied opening status."""

    provider_place_id: str = Field(min_length=1, max_length=128)
    status: Literal["open", "closed", "unknown"]
    intervals: tuple[str, ...] = Field(default=(), max_length=14)
    note: str | None = Field(default=None, max_length=500)


class OpeningHoursResult(StrictModel):
    """Live opening-hours result."""

    entries: tuple[OpeningHoursEntry, ...] = Field(max_length=50)
    provenance: ProviderProvenance


class WeatherRequest(StrictModel):
    """Current/forecast weather request."""

    coordinate: Coordinate
    timezone: str = Field(min_length=1, max_length=64)
    forecast_hours: int = Field(default=48, ge=1, le=168)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a real IANA timezone; never infer one from a coordinate."""

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value


class WeatherPeriod(StrictModel):
    """One normalized forecast interval."""

    starts_at: datetime
    ends_at: datetime
    condition: str = Field(min_length=1, max_length=100)
    temperature_celsius: float = Field(ge=-100, le=80)
    precipitation_probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_period(self) -> "WeatherPeriod":
        """Require a timezone-aware, forward-moving forecast interval."""

        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("weather period timestamps must be timezone-aware")
        if self.ends_at <= self.starts_at:
            raise ValueError("weather period must have positive duration")
        return self


class WeatherResult(StrictModel):
    """Live weather result."""

    periods: tuple[WeatherPeriod, ...] = Field(max_length=168)
    provenance: ProviderProvenance


class ProviderDescriptor(StrictModel):
    """Non-secret provider capability metadata."""

    provider_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=120)
    api_family: str = Field(min_length=1, max_length=120)
    api_version: str = Field(min_length=1, max_length=80)
    capabilities: frozenset[ProviderCapability] = Field(min_length=1)
    configured: bool


class ProviderHealth(StrictModel):
    """Safe runtime health metadata; never contains URLs, keys or raw errors."""

    provider_id: str
    configured: bool
    allowed: bool
    circuit_state: Literal["closed", "open", "half_open"]
    capabilities: frozenset[ProviderCapability]


__all__ = [
    "Coordinate",
    "FreshnessStatus",
    "GeocodeCandidate",
    "GeocodeRequest",
    "GeocodeResult",
    "OpeningHoursEntry",
    "OpeningHoursRequest",
    "OpeningHoursResult",
    "Place",
    "PlaceSearchRequest",
    "PlaceSearchResult",
    "ProviderCapability",
    "ProviderDescriptor",
    "ProviderHealth",
    "ProviderProvenance",
    "RouteMatrixCell",
    "RouteMatrixRequest",
    "RouteMatrixResult",
    "RouteMode",
    "WeatherPeriod",
    "WeatherRequest",
    "WeatherResult",
    "utc_now",
]
