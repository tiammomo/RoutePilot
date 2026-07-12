"""Production AMap Web Service adapter.

Only fixed HTTPS paths on ``restapi.amap.com`` are reachable.  Upstream
payloads are validated and normalized at this boundary; keys, full request
URLs and provider error strings never escape it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from .errors import (
    ProviderAuthenticationError,
    ProviderCancelledError,
    ProviderInputError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .models import (
    Coordinate,
    FreshnessStatus,
    GeocodeCandidate,
    GeocodeRequest,
    GeocodeResult,
    OpeningHoursEntry,
    OpeningHoursRequest,
    OpeningHoursResult,
    Place,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderCapability,
    ProviderDescriptor,
    ProviderProvenance,
    RouteMatrixCell,
    RouteMatrixRequest,
    RouteMatrixResult,
    RouteMode,
    WeatherPeriod,
    WeatherRequest,
    WeatherResult,
    utc_now,
)
from .ports import ProviderCallContext

AMAP_BASE_URL = "https://restapi.amap.com"
AMAP_PROVIDER_ID = "amap"
AMAP_API_VERSION = "web-service-v3-v5"
MAX_AMAP_RESPONSE_BYTES = 2 * 1024 * 1024


class _RedactHttpxQuerySecrets(logging.Filter):
    """Redact query credentials from httpx's built-in request log record."""

    _sensitive_names = frozenset({"key", "sig", "token", "access_token", "api_key"})

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if record.name != "httpx" or not isinstance(args, tuple) or len(args) < 2:
            return True
        url = args[1]
        if not isinstance(url, httpx.URL):
            return True
        redacted = url
        for name in self._sensitive_names:
            if name in redacted.params:
                redacted = redacted.copy_set_param(name, "[REDACTED]")
        if redacted != url:
            safe_args = list(args)
            safe_args[1] = redacted
            record.args = tuple(safe_args)
        return True


_HTTPX_REDACTION_FILTER = _RedactHttpxQuerySecrets()


def _install_httpx_redaction_filter() -> None:
    """Install the process-wide outbound URL filter exactly once."""

    logger = logging.getLogger("httpx")
    if _HTTPX_REDACTION_FILTER not in logger.filters:
        logger.addFilter(_HTTPX_REDACTION_FILTER)


class _AMapModel(BaseModel):
    """Validate used fields while tolerating documented response expansion."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)


class _AMapStatusResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None


class _AMapPoi(_AMapModel):
    id: str
    name: str
    location: str
    address: str | list[Any] | None = None
    type: str | list[Any] | None = None
    typecode: str | list[Any] | None = None
    adcode: str | list[Any] | None = None


class _AMapPlaceResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    count: str | int = 0
    pois: list[_AMapPoi] = Field(default_factory=list)


class _AMapGeocode(_AMapModel):
    formatted_address: str
    country: str | list[Any] | None = None
    province: str | list[Any] | None = None
    city: str | list[Any] | None = None
    district: str | list[Any] | None = None
    adcode: str | list[Any] | None = None
    location: str


class _AMapGeocodeResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    count: str | int = 0
    geocodes: list[_AMapGeocode] = Field(default_factory=list)


class _AMapDistance(_AMapModel):
    origin_id: str | int
    dest_id: str | int
    distance: str | int
    duration: str | int
    info: str | None = None


class _AMapDistanceResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    results: list[_AMapDistance] = Field(default_factory=list)


class _AMapRegeoAddressComponent(_AMapModel):
    adcode: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class _AMapRegeocode(_AMapModel):
    address_component: _AMapRegeoAddressComponent = Field(alias="addressComponent")


class _AMapRegeoResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    regeocode: _AMapRegeocode


class _AMapWeatherCast(_AMapModel):
    date: str = Field(min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    dayweather: str = Field(min_length=1, max_length=100)
    nightweather: str = Field(min_length=1, max_length=100)
    daytemp: str | int | float
    nighttemp: str | int | float

    @field_validator("daytemp", "nighttemp", mode="before")
    @classmethod
    def bounded_temperature(cls, value: Any) -> Any:
        if isinstance(value, bool) or (isinstance(value, str) and len(value) > 16):
            raise ValueError("invalid temperature scalar")
        return value


class _AMapForecast(_AMapModel):
    adcode: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    reporttime: str = Field(min_length=19, max_length=19)
    casts: list[_AMapWeatherCast] = Field(min_length=1, max_length=8)


class _AMapWeatherResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    count: str | int = 0
    forecasts: list[_AMapForecast] = Field(min_length=1, max_length=2)


class _AMapBusiness(_AMapModel):
    opentime_today: str | None = Field(default=None, max_length=500)
    opentime_week: str | None = Field(default=None, max_length=500)

    @field_validator("opentime_today", "opentime_week", mode="before")
    @classmethod
    def empty_scalar_sentinel(cls, value: Any) -> Any:
        if value == []:
            return None
        return value


class _AMapDetailPoi(_AMapModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    business: _AMapBusiness | None = None

    @field_validator("business", mode="before")
    @classmethod
    def empty_business_sentinel(cls, value: Any) -> Any:
        if value == []:
            return None
        return value


class _AMapPlaceDetailResponse(_AMapModel):
    status: str
    info: str | None = None
    infocode: str | None = None
    pois: list[_AMapDetailPoi] = Field(default_factory=list, max_length=10)


_OPEN_INTERVAL_RE = re.compile(
    r"(?<!\d)((?:[01]\d|2[0-3]):[0-5]\d)-"
    r"((?:[01]\d|2[0-3]):[0-5]\d|24:00)(?!\d)"
)


def _safe_text(value: str | list[Any] | None) -> str | None:
    """Discard AMap's occasional empty-list sentinel for scalar fields."""

    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _coordinate(value: str) -> Coordinate:
    """Parse and validate a provider coordinate."""

    parts = value.split(",")
    if len(parts) != 2:
        raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
    try:
        return Coordinate(
            longitude=float(parts[0]),
            latitude=float(parts[1]),
            coordinate_system="GCJ-02",
        )
    except (TypeError, ValueError, ValidationError):
        raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None


class AMapProvider:
    """AMap POI/geocode/distance adapter with one reusable HTTP client."""

    descriptor = ProviderDescriptor(
        provider_id=AMAP_PROVIDER_ID,
        display_name="AMap Web Service",
        api_family="AMap Web Service",
        api_version=AMAP_API_VERSION,
        capabilities=frozenset(
            {
                ProviderCapability.PLACE_SEARCH,
                ProviderCapability.GEOCODE,
                ProviderCapability.ROUTE_MATRIX,
                ProviderCapability.OPENING_HOURS,
                ProviderCapability.WEATHER,
            }
        ),
        configured=True,
    )

    def __init__(
        self,
        *,
        api_key: str | SecretStr,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        raw_key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not raw_key.strip():
            raise ValueError("AMap Web Service key is required")
        if not 0.1 <= timeout_seconds <= 15:
            raise ValueError("timeout_seconds must be between 0.1 and 15")
        self._api_key = SecretStr(raw_key.strip())
        self._owns_client = client is None
        if client is not None and (
            client.base_url.scheme != "https"
            or client.base_url.host != "restapi.amap.com"
            or client.base_url.port not in {None, 443}
            or bool(client.base_url.userinfo)
        ):
            raise ValueError("AMap client must use the fixed HTTPS provider origin")
        _install_httpx_redaction_filter()
        self._client = client or httpx.AsyncClient(
            base_url=AMAP_BASE_URL,
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "RoutePilot/1 provider-gateway"},
        )

    async def close(self) -> None:
        """Close the internally-owned reusable HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self,
        path: Literal[
            "/v3/place/text",
            "/v3/place/around",
            "/v3/geocode/geo",
            "/v3/geocode/regeo",
            "/v3/distance",
            "/v3/weather/weatherInfo",
            "/v5/place/detail",
        ],
        params: dict[str, str],
    ) -> Any:
        """Call a compile-time fixed endpoint and return decoded JSON."""

        safe_params = {
            **params,
            "key": self._api_key.get_secret_value(),
            "output": "JSON",
        }
        try:
            async with self._client.stream(
                "GET",
                path,
                params=safe_params,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                if response.status_code == 429:
                    raise ProviderRateLimitedError(provider_id=AMAP_PROVIDER_ID)
                if response.status_code in {401, 403}:
                    raise ProviderAuthenticationError(provider_id=AMAP_PROVIDER_ID)
                if response.status_code >= 500:
                    raise ProviderUnavailableError(provider_id=AMAP_PROVIDER_ID)
                if response.status_code != 200:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                content_type = response.headers.get("content-type", "").lower()
                if "json" not in content_type:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > MAX_AMAP_RESPONSE_BYTES:
                            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                    except ValueError:
                        raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_AMAP_RESPONSE_BYTES:
                        raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                    chunks.append(chunk)
                content = b"".join(chunks)
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException:
            raise ProviderTimeoutError(provider_id=AMAP_PROVIDER_ID) from None
        except httpx.HTTPError:
            raise ProviderUnavailableError(provider_id=AMAP_PROVIDER_ID) from None

        try:
            return json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None

    @staticmethod
    def _validate_status(status: str, infocode: str | None) -> None:
        """Map upstream status codes to the small safe taxonomy."""

        if status == "1" and infocode in {None, "", "10000"}:
            return
        # Official AMap categories are mapped without exposing ``info`` or keys.
        if infocode in {
            "10001",
            "10002",
            "10005",
            "10006",
            "10007",
            "10008",
            "10009",
            "10011",
            "10012",
            "10013",
            "10026",
            "10041",
            "40000",
            "40002",
            "40003",
        }:
            raise ProviderAuthenticationError(provider_id=AMAP_PROVIDER_ID)
        if infocode in {
            "10003",
            "10004",
            "10010",
            "10014",
            "10015",
            "10019",
            "10020",
            "10021",
            "10029",
            "10044",
            "10045",
        }:
            raise ProviderRateLimitedError(provider_id=AMAP_PROVIDER_ID)
        if infocode in {
            "20000",
            "20001",
            "20002",
            "20011",
            "20012",
            "20800",
            "20801",
            "20802",
            "20803",
        }:
            raise ProviderInputError(provider_id=AMAP_PROVIDER_ID)
        if infocode in {"10016", "10017", "20003"} or (
            infocode is not None and infocode.startswith("3")
        ):
            raise ProviderUnavailableError(provider_id=AMAP_PROVIDER_ID)
        raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)

    @classmethod
    def _validate_payload_status(cls, payload: Any) -> None:
        try:
            status = _AMapStatusResponse.model_validate(payload)
        except ValidationError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        cls._validate_status(status.status, status.infocode)

    @staticmethod
    def _provenance(
        capability: ProviderCapability,
        ttl_seconds: int,
        *,
        observed_at: datetime | None = None,
    ) -> ProviderProvenance:
        observed_at = observed_at or utc_now()
        valid_until = observed_at + timedelta(seconds=ttl_seconds)
        return ProviderProvenance(
            provider_id=AMAP_PROVIDER_ID,
            provider_version=AMAP_API_VERSION,
            capability=capability,
            observed_at=observed_at,
            valid_until=valid_until,
            freshness_status=(
                FreshnessStatus.FRESH if valid_until > utc_now() else FreshnessStatus.STALE
            ),
        )

    @staticmethod
    def _check_cancelled(context: ProviderCallContext) -> None:
        if context.cancellation_event is not None and context.cancellation_event.is_set():
            raise ProviderCancelledError(provider_id=AMAP_PROVIDER_ID)

    @staticmethod
    def _amap_parameter(coordinate: Coordinate) -> str:
        """Reject silent coordinate-datum conversion at the adapter boundary."""

        if coordinate.coordinate_system != "GCJ-02":
            raise ProviderInputError(provider_id=AMAP_PROVIDER_ID)
        return coordinate.as_amap_parameter()

    async def search_places(
        self,
        request: PlaceSearchRequest,
        context: ProviderCallContext,
    ) -> PlaceSearchResult:
        """Search AMap POIs using keyword or fixed-radius nearby search."""

        self._check_cancelled(context)
        params = {
            "keywords": request.query,
            "offset": str(request.limit),
            "page": str(request.page),
            "extensions": "base",
        }
        if request.city:
            params.update({"city": request.city, "citylimit": "true"})
        if request.category_codes:
            params["types"] = "|".join(request.category_codes)
        if request.center is None:
            path: Literal["/v3/place/text", "/v3/place/around"] = "/v3/place/text"
        else:
            path = "/v3/place/around"
            params.update(
                {
                    "location": self._amap_parameter(request.center),
                    "radius": str(request.radius_meters),
                }
            )
        payload = await self._get(path, params)
        try:
            envelope = _AMapPlaceResponse.model_validate(payload)
        except ValidationError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        self._validate_status(envelope.status, envelope.infocode)

        places: list[Place] = []
        for poi in envelope.pois[: request.limit]:
            places.append(
                Place(
                    provider_place_id=poi.id,
                    name=poi.name,
                    coordinate=_coordinate(poi.location),
                    address=_safe_text(poi.address),
                    category=_safe_text(poi.type),
                    category_code=_safe_text(poi.typecode),
                    administrative_code=_safe_text(poi.adcode),
                )
            )
        return PlaceSearchResult(
            places=tuple(places),
            provenance=self._provenance(ProviderCapability.PLACE_SEARCH, 21_600),
        )

    async def geocode(
        self,
        request: GeocodeRequest,
        context: ProviderCallContext,
    ) -> GeocodeResult:
        """Forward-geocode a structured address using AMap v3."""

        self._check_cancelled(context)
        params = {"address": request.address}
        if request.city:
            params["city"] = request.city
        payload = await self._get("/v3/geocode/geo", params)
        try:
            envelope = _AMapGeocodeResponse.model_validate(payload)
        except ValidationError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        self._validate_status(envelope.status, envelope.infocode)
        candidates = tuple(
            GeocodeCandidate(
                formatted_address=item.formatted_address,
                coordinate=_coordinate(item.location),
                country=_safe_text(item.country),
                province=_safe_text(item.province),
                city=_safe_text(item.city),
                district=_safe_text(item.district),
                administrative_code=_safe_text(item.adcode),
            )
            for item in envelope.geocodes[:10]
        )
        return GeocodeResult(
            candidates=candidates,
            provenance=self._provenance(ProviderCapability.GEOCODE, 86_400),
        )

    async def route_matrix(
        self,
        request: RouteMatrixRequest,
        context: ProviderCallContext,
    ) -> RouteMatrixResult:
        """Build a bounded matrix using AMap v3 distance measurements."""

        self._check_cancelled(context)
        route_type = "1" if request.mode is RouteMode.DRIVING else "3"
        origins = "|".join(self._amap_parameter(item) for item in request.origins)
        cells: list[RouteMatrixCell] = []
        # The official distance API accepts many origins but one destination.
        # Keep destination requests sequential so adapter-level concurrency never
        # bypasses the gateway bulkhead/quota controls.
        for destination_index, destination in enumerate(request.destinations):
            self._check_cancelled(context)
            payload = await self._get(
                "/v3/distance",
                {
                    "origins": origins,
                    "destination": self._amap_parameter(destination),
                    "type": route_type,
                },
            )
            self._validate_payload_status(payload)
            try:
                envelope = _AMapDistanceResponse.model_validate(payload)
            except ValidationError:
                raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
            self._validate_status(envelope.status, envelope.infocode)
            if len(envelope.results) != len(request.origins):
                raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
            for expected_origin, item in enumerate(envelope.results):
                if item.info not in {None, "", "OK"}:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                try:
                    origin_index = int(item.origin_id) - 1
                    destination_id = int(item.dest_id)
                    distance = int(item.distance)
                    duration = int(item.duration)
                except (TypeError, ValueError):
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
                if (
                    origin_index != expected_origin
                    or destination_id != 1
                    or distance < 0
                    or duration < 0
                ):
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                cells.append(
                    RouteMatrixCell(
                        origin_index=origin_index,
                        destination_index=destination_index,
                        distance_meters=distance,
                        duration_seconds=duration,
                    )
                )
        return RouteMatrixResult(
            cells=tuple(cells),
            coordinate_system="GCJ-02",
            provenance=self._provenance(ProviderCapability.ROUTE_MATRIX, 300),
        )

    async def opening_hours(
        self,
        request: OpeningHoursRequest,
        context: ProviderCallContext,
    ) -> OpeningHoursResult:
        """Fetch bounded AMap v5 business schedules in ten-ID batches."""

        self._check_cancelled(context)
        entries_by_id: dict[str, OpeningHoursEntry] = {}
        for start in range(0, len(request.provider_place_ids), 10):
            self._check_cancelled(context)
            batch = request.provider_place_ids[start : start + 10]
            payload = await self._get(
                "/v5/place/detail",
                {
                    "id": "|".join(batch),
                    "show_fields": "business",
                },
            )
            self._validate_payload_status(payload)
            try:
                envelope = _AMapPlaceDetailResponse.model_validate(payload)
            except ValidationError:
                raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
            self._validate_status(envelope.status, envelope.infocode)
            batch_ids = set(batch)
            for poi in envelope.pois:
                if poi.id not in batch_ids or poi.id in entries_by_id:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                today = poi.business.opentime_today if poi.business else None
                weekly = poi.business.opentime_week if poi.business else None
                intervals = (
                    tuple(dict.fromkeys(match.group(0) for match in _OPEN_INTERVAL_RE.finditer(today)))
                    if today and request.local_date is None
                    else ()
                )
                if len(intervals) > 14:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
                closed_today = bool(
                    today
                    and any(
                        marker in today
                        for marker in ("暂停营业", "停止营业", "休息", "关闭")
                    )
                )
                note = weekly
                if request.local_date is not None and not note:
                    note = "Provider did not return a schedule for the requested date."
                elif not note and not intervals:
                    note = "Provider did not return opening-hour details."
                entries_by_id[poi.id] = OpeningHoursEntry(
                    provider_place_id=poi.id,
                    status=(
                        "closed"
                        if closed_today and request.local_date is None
                        else "unknown"
                    ),
                    intervals=intervals,
                    note=note,
                )

            for place_id in batch:
                entries_by_id.setdefault(
                    place_id,
                    OpeningHoursEntry(
                        provider_place_id=place_id,
                        status="unknown",
                        note="Provider did not return opening-hour details.",
                    ),
                )
        return OpeningHoursResult(
            entries=tuple(entries_by_id[item] for item in request.provider_place_ids),
            provenance=self._provenance(ProviderCapability.OPENING_HOURS, 300),
        )

    async def weather(
        self,
        request: WeatherRequest,
        context: ProviderCallContext,
    ) -> WeatherResult:
        """Resolve an adcode and normalize AMap daily forecasts into local periods."""

        self._check_cancelled(context)
        location = self._amap_parameter(request.coordinate)
        regeo_payload = await self._get(
            "/v3/geocode/regeo",
            {"location": location, "extensions": "base", "radius": "0"},
        )
        self._validate_payload_status(regeo_payload)
        try:
            regeo = _AMapRegeoResponse.model_validate(regeo_payload)
        except ValidationError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        self._validate_status(regeo.status, regeo.infocode)
        adcode = regeo.regeocode.address_component.adcode

        self._check_cancelled(context)
        weather_payload = await self._get(
            "/v3/weather/weatherInfo",
            {"city": adcode, "extensions": "all"},
        )
        self._validate_payload_status(weather_payload)
        try:
            response = _AMapWeatherResponse.model_validate(weather_payload)
        except ValidationError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        self._validate_status(response.status, response.infocode)
        if len(response.forecasts) != 1 or response.forecasts[0].adcode != adcode:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
        forecast = response.forecasts[0]
        timezone = ZoneInfo(request.timezone)
        try:
            reported_local = datetime.strptime(
                forecast.reporttime,
                "%Y-%m-%d %H:%M:%S",
            ).replace(tzinfo=timezone)
        except ValueError:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        observed_at = reported_local.astimezone(UTC)
        if observed_at > utc_now() + timedelta(minutes=10):
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)

        now_local = utc_now().astimezone(timezone)
        horizon = now_local + timedelta(hours=request.forecast_hours)
        periods: list[WeatherPeriod] = []
        seen_dates: set[date] = set()
        for cast in forecast.casts:
            try:
                forecast_date = date.fromisoformat(cast.date)
                day_temperature = float(cast.daytemp)
                night_temperature = float(cast.nighttemp)
            except (TypeError, ValueError):
                raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
            if forecast_date in seen_dates:
                raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
            seen_dates.add(forecast_date)
            day_start = datetime.combine(forecast_date, time(8), timezone)
            day_end = datetime.combine(forecast_date, time(20), timezone)
            candidates = (
                (day_start, day_end, cast.dayweather, day_temperature),
                (
                    day_end,
                    datetime.combine(forecast_date + timedelta(days=1), time(8), timezone),
                    cast.nightweather,
                    night_temperature,
                ),
            )
            for starts_at, ends_at, condition, temperature in candidates:
                if ends_at <= now_local or starts_at >= horizon:
                    continue
                try:
                    periods.append(
                        WeatherPeriod(
                            starts_at=starts_at,
                            ends_at=ends_at,
                            condition=condition,
                            temperature_celsius=temperature,
                        )
                    )
                except ValidationError:
                    raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID) from None
        periods.sort(key=lambda item: item.starts_at)
        if not periods:
            raise ProviderResponseError(provider_id=AMAP_PROVIDER_ID)
        return WeatherResult(
            periods=tuple(periods),
            provenance=self._provenance(
                ProviderCapability.WEATHER,
                21_600,
                observed_at=observed_at,
            ),
        )


__all__ = ["AMAP_API_VERSION", "AMAP_BASE_URL", "AMAP_PROVIDER_ID", "AMapProvider"]
