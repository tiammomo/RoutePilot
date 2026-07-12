"""AMap normalization and fixed-endpoint adapter tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic import ValidationError

from agent.travel_agent.providers import (
    AMapProvider,
    Coordinate,
    GeocodeRequest,
    OpeningHoursRequest,
    PlaceSearchRequest,
    ProviderCallContext,
    ProviderCancelledError,
    ProviderInputError,
    ProviderResponseError,
    RouteMatrixRequest,
    WeatherRequest,
)


def _context() -> ProviderCallContext:
    return ProviderCallContext.with_timeout(
        tenant_id="tenant-a",
        actor_id="user-a",
        operation_id="amap-test",
        timeout_seconds=1,
    )


@pytest.mark.asyncio
async def test_amap_normalizes_place_geocode_and_route_matrix() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v3/place/text":
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "pois": [
                    {
                        "id": "B000A",
                        "name": "故宫博物院",
                        "location": "116.397026,39.918058",
                        "address": "景山前街4号",
                        "type": "风景名胜;风景名胜相关;旅游景点",
                        "typecode": "110000",
                        "adcode": "110101",
                        "unconsumed_new_field": "ignored",
                    }
                ],
            }
        elif request.url.path == "/v3/geocode/geo":
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "geocodes": [
                    {
                        "formatted_address": "北京市东城区景山前街4号",
                        "country": "中国",
                        "province": "北京市",
                        "city": "北京市",
                        "district": "东城区",
                        "adcode": "110101",
                        "location": "116.397026,39.918058",
                    }
                ],
            }
        elif request.url.path == "/v3/distance":
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "results": [
                    {
                        "origin_id": "1",
                        "dest_id": "1",
                        "distance": "1200",
                        "duration": "600",
                    },
                    {
                        "origin_id": "2",
                        "dest_id": "1",
                        "distance": "2400",
                        "duration": "900",
                    },
                ],
            }
        else:  # pragma: no cover - catches accidental endpoint expansion
            raise AssertionError(f"unexpected fixed path: {request.url.path}")
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            json=payload,
        )

    client = httpx.AsyncClient(
        base_url="https://restapi.amap.com",
        transport=httpx.MockTransport(handler),
    )
    provider = AMapProvider(api_key="server-only", client=client)

    places = await provider.search_places(PlaceSearchRequest(query="故宫"), _context())
    geocode = await provider.geocode(GeocodeRequest(address="景山前街4号"), _context())
    matrix = await provider.route_matrix(
        RouteMatrixRequest(
            origins=(
                Coordinate(
                    longitude=116.397,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
                Coordinate(
                    longitude=116.407,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
            ),
            destinations=(
                Coordinate(
                    longitude=116.417,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
            ),
        ),
        _context(),
    )

    assert places.places[0].provider_place_id == "B000A"
    assert places.places[0].coordinate.coordinate_system == "GCJ-02"
    assert geocode.candidates[0].administrative_code == "110101"
    assert [cell.distance_meters for cell in matrix.cells] == [1200, 2400]
    assert {request.url.scheme for request in requests} == {"https"}
    assert {request.url.host for request in requests} == {"restapi.amap.com"}
    assert all(request.url.params["key"] == "server-only" for request in requests)

    with pytest.raises(ProviderInputError):
        await provider.route_matrix(
            RouteMatrixRequest(
                origins=(
                    Coordinate(
                        longitude=116.397,
                        latitude=39.918,
                        coordinate_system="WGS-84",
                    ),
                ),
                destinations=(
                    Coordinate(
                        longitude=116.417,
                        latitude=39.918,
                        coordinate_system="GCJ-02",
                    ),
                ),
            ),
            _context(),
        )
    assert len(requests) == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_amap_rejects_injected_non_provider_origin() -> None:
    client = httpx.AsyncClient(base_url="https://example.invalid")
    with pytest.raises(ValueError, match="fixed HTTPS provider origin"):
        AMapProvider(api_key="server-only", client=client)
    await client.aclose()


@pytest.mark.asyncio
async def test_amap_normalizes_weather_and_batched_opening_hours() -> None:
    requests: list[httpx.Request] = []
    timezone = ZoneInfo("Asia/Shanghai")
    now = datetime.now(timezone)

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v3/geocode/regeo":
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "regeocode": {"addressComponent": {"adcode": "110101"}},
            }
        elif request.url.path == "/v3/weather/weatherInfo":
            assert request.url.params["city"] == "110101"
            assert request.url.params["extensions"] == "all"
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "count": "1",
                "forecasts": [
                    {
                        "adcode": "110101",
                        "reporttime": (now - timedelta(minutes=1)).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        "casts": [
                            {
                                "date": (now.date() + timedelta(days=offset)).isoformat(),
                                "dayweather": "晴",
                                "nightweather": "多云",
                                "daytemp": "26",
                                "nighttemp": "16",
                            }
                            for offset in range(4)
                        ],
                    }
                ],
            }
        elif request.url.path == "/v5/place/detail":
            assert request.url.params["show_fields"] == "business"
            ids = request.url.params["id"].split("|")
            assert 1 <= len(ids) <= 10
            payload = {
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "pois": [
                    {
                        "id": item,
                        "business": {
                            "opentime_today": (
                                "暂停营业" if item == "B0002" else "08:30-17:30 19:00-22:00"
                            ),
                            "opentime_week": "周一至周日:08:30-22:00",
                        },
                    }
                    for item in ids
                ],
            }
        else:  # pragma: no cover - fixed endpoint allowlist assertion
            raise AssertionError(request.url.path)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json=payload,
        )

    client = httpx.AsyncClient(
        base_url="https://restapi.amap.com",
        transport=httpx.MockTransport(handler),
    )
    provider = AMapProvider(api_key="server-only", client=client)
    weather = await provider.weather(
        WeatherRequest(
            coordinate=Coordinate(
                longitude=116.397,
                latitude=39.918,
                coordinate_system="GCJ-02",
            ),
            timezone="Asia/Shanghai",
            forecast_hours=48,
        ),
        _context(),
    )
    ids = tuple(f"B{index:04d}" for index in range(1, 12))
    opening = await provider.opening_hours(
        OpeningHoursRequest(provider_place_ids=ids),
        _context(),
    )

    assert weather.periods
    assert all(item.starts_at.tzinfo is not None for item in weather.periods)
    assert weather.provenance.capability.value == "weather"
    assert [item.provider_place_id for item in opening.entries] == list(ids)
    assert opening.entries[0].intervals == ("08:30-17:30", "19:00-22:00")
    assert opening.entries[1].status == "closed"
    assert opening.provenance.capability.value == "opening_hours"
    assert (
        opening.provenance.valid_until - opening.provenance.observed_at
    ).total_seconds() == 300
    assert (
        weather.provenance.valid_until - weather.provenance.observed_at
    ).total_seconds() == 21_600
    assert [item.url.path for item in requests].count("/v5/place/detail") == 2
    assert all(item.url.params["key"] == "server-only" for item in requests)
    await client.aclose()


@pytest.mark.asyncio
async def test_amap_live_capabilities_reject_invalid_ids_schema_and_cancellation() -> None:
    with pytest.raises(ValidationError, match="delimiter-safe"):
        OpeningHoursRequest(provider_place_ids=("B0001|B0002",))
    with pytest.raises(ValidationError, match="IANA timezone"):
        WeatherRequest(
            coordinate=Coordinate(
                longitude=116.397,
                latitude=39.918,
                coordinate_system="GCJ-02",
            ),
            timezone="Not/A-Timezone",
        )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "status": "1",
                "info": "OK",
                "infocode": "10000",
                "pois": [{"id": "UNREQUESTED", "business": {}}],
            },
        )

    client = httpx.AsyncClient(
        base_url="https://restapi.amap.com",
        transport=httpx.MockTransport(handler),
    )
    provider = AMapProvider(api_key="server-only", client=client)
    with pytest.raises(ProviderResponseError):
        await provider.opening_hours(
            OpeningHoursRequest(provider_place_ids=("B0001",)),
            _context(),
        )

    canceled = asyncio.Event()
    canceled.set()
    with pytest.raises(ProviderCancelledError):
        await provider.weather(
            WeatherRequest(
                coordinate=Coordinate(
                    longitude=116.397,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
                timezone="Asia/Shanghai",
            ),
            ProviderCallContext.with_timeout(
                tenant_id="tenant-a",
                actor_id="user-a",
                operation_id="cancelled-weather",
                timeout_seconds=1,
                cancellation_event=canceled,
            ),
        )
    await client.aclose()

    async def oversized_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-length": str(2 * 1024 * 1024 + 1),
            },
            json={"status": "1"},
        )

    oversized_client = httpx.AsyncClient(
        base_url="https://restapi.amap.com",
        transport=httpx.MockTransport(oversized_handler),
    )
    oversized_provider = AMapProvider(api_key="server-only", client=oversized_client)
    with pytest.raises(ProviderResponseError):
        await oversized_provider.weather(
            WeatherRequest(
                coordinate=Coordinate(
                    longitude=116.397,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
                timezone="Asia/Shanghai",
            ),
            _context(),
        )
    await oversized_client.aclose()
