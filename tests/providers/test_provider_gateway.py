"""Resilience, tenancy and safe-error tests for the live Provider Gateway."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Awaitable, Callable

import httpx
import pytest

from agent.travel_agent.providers import (
    AMapProvider,
    CacheScope,
    Coordinate,
    FreshnessStatus,
    GatewayPolicy,
    OpeningHoursRequest,
    Place,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderCancelledError,
    ProviderCapability,
    ProviderCallContext,
    ProviderCircuitOpenError,
    ProviderDescriptor,
    ProviderGateway,
    ProviderIdempotencyConflictError,
    ProviderProvenance,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderUnavailableError,
    UnavailableProvider,
    WeatherRequest,
    utc_now,
)


class FakePlaceProvider:
    """Small deterministic adapter used to exercise gateway policy."""

    def __init__(
        self,
        provider_id: str,
        behavior: Callable[
            [PlaceSearchRequest, ProviderCallContext], Awaitable[PlaceSearchResult]
        ],
    ) -> None:
        self.descriptor = ProviderDescriptor(
            provider_id=provider_id,
            display_name=f"Fake {provider_id}",
            api_family="test",
            api_version="test-v1",
            capabilities=frozenset({ProviderCapability.PLACE_SEARCH}),
            configured=True,
        )
        self.behavior = behavior
        self.calls = 0
        self.closed = False

    async def search_places(
        self,
        request: PlaceSearchRequest,
        context: ProviderCallContext,
    ) -> PlaceSearchResult:
        self.calls += 1
        return await self.behavior(request, context)

    async def close(self) -> None:
        self.closed = True


def _place_result(provider_id: str, query: str = "故宫") -> PlaceSearchResult:
    observed_at = utc_now()
    return PlaceSearchResult(
        places=(
            Place(
                provider_place_id=f"{provider_id}-1",
                name=query,
                coordinate=Coordinate(
                    longitude=116.397,
                    latitude=39.918,
                    coordinate_system="GCJ-02",
                ),
            ),
        ),
        provenance=ProviderProvenance(
            provider_id=provider_id,
            provider_version="test-v1",
            capability=ProviderCapability.PLACE_SEARCH,
            observed_at=observed_at,
            valid_until=observed_at + timedelta(minutes=10),
            freshness_status=FreshnessStatus.FRESH,
        ),
    )


def _context(
    tenant_id: str = "tenant-a",
    *,
    operation_id: str = "op-1",
    cache_scope: CacheScope = CacheScope.DISABLED,
    timeout_seconds: float = 1,
    idempotency_key: str | None = None,
    cancellation_event: asyncio.Event | None = None,
) -> ProviderCallContext:
    return ProviderCallContext.with_timeout(
        tenant_id=tenant_id,
        actor_id="user-1",
        operation_id=operation_id,
        timeout_seconds=timeout_seconds,
        cache_scope=cache_scope,
        idempotency_key=idempotency_key,
        cancellation_event=cancellation_event,
    )


@pytest.mark.asyncio
async def test_gateway_falls_back_to_next_allowlisted_provider() -> None:
    async def fail(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        raise ProviderUnavailableError(provider_id="primary")

    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("secondary", request.query)

    primary = FakePlaceProvider("primary", fail)
    secondary = FakePlaceProvider("secondary", succeed)
    gateway = ProviderGateway(
        [primary, secondary],
        allowlist=frozenset({"primary", "secondary"}),
        policy=GatewayPolicy(max_retries=0),
    )

    result = await gateway.search_places(PlaceSearchRequest(query="故宫"), _context())

    assert result.provenance.provider_id == "secondary"
    assert primary.calls == 1
    assert secondary.calls == 1


@pytest.mark.asyncio
async def test_allowlist_prevents_disallowed_adapter_execution() -> None:
    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result(context.operation_id, request.query)

    denied = FakePlaceProvider("denied", succeed)

    async def allowed_success(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("allowed", request.query)

    allowed = FakePlaceProvider("allowed", allowed_success)
    gateway = ProviderGateway(
        [denied, allowed],
        allowlist=frozenset({"allowed"}),
        policy=GatewayPolicy(max_retries=0),
    )

    result = await gateway.search_places(PlaceSearchRequest(query="safe"), _context())

    assert result.provenance.provider_id == "allowed"
    assert denied.calls == 0


@pytest.mark.asyncio
async def test_retry_is_bounded_and_jittered() -> None:
    async def fail(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        raise ProviderUnavailableError(provider_id="retry")

    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    provider = FakePlaceProvider("retry", fail)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"retry"}),
        policy=GatewayPolicy(max_retries=1, backoff_seconds=0.01, jitter_seconds=0.01),
        sleep=record_delay,
        random_source=random.Random(7),
    )

    with pytest.raises(ProviderUnavailableError):
        await gateway.search_places(PlaceSearchRequest(query="retry"), _context())

    assert provider.calls == 2
    assert len(delays) == 1
    assert 0.01 <= delays[0] <= 0.02


@pytest.mark.asyncio
async def test_gateway_enforces_absolute_timeout_without_raw_error() -> None:
    async def slow(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        await asyncio.sleep(1)
        return _place_result("slow")

    provider = FakePlaceProvider("slow", slow)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"slow"}),
        policy=GatewayPolicy(max_retries=0),
    )

    with pytest.raises(Exception) as captured:
        await gateway.search_places(
            PlaceSearchRequest(query="timeout"),
            _context(timeout_seconds=0.03),
        )

    assert captured.value.as_public_detail()["code"] == "PROVIDER_TIMEOUT"
    assert "timeout" not in str(captured.value).lower()


@pytest.mark.asyncio
async def test_gateway_opens_circuit_after_bounded_failures() -> None:
    async def fail(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        raise ProviderUnavailableError(provider_id="broken")

    provider = FakePlaceProvider("broken", fail)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"broken"}),
        policy=GatewayPolicy(max_retries=0, circuit_failure_threshold=1),
    )

    with pytest.raises(ProviderUnavailableError):
        await gateway.search_places(PlaceSearchRequest(query="one"), _context())
    with pytest.raises(ProviderCircuitOpenError):
        await gateway.search_places(
            PlaceSearchRequest(query="two"),
            _context(operation_id="op-2"),
        )

    assert provider.calls == 1
    assert gateway.health()[0].circuit_state == "open"


@pytest.mark.asyncio
async def test_gateway_rate_limit_is_per_tenant_and_provider() -> None:
    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("limited", request.query)

    provider = FakePlaceProvider("limited", succeed)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"limited"}),
        policy=GatewayPolicy(max_retries=0, rate_limit_requests=1),
    )

    await gateway.search_places(PlaceSearchRequest(query="one"), _context())
    with pytest.raises(ProviderRateLimitedError):
        await gateway.search_places(
            PlaceSearchRequest(query="two"),
            _context(operation_id="op-2"),
        )
    # A different authenticated tenant has an independent quota window.
    result = await gateway.search_places(
        PlaceSearchRequest(query="three"),
        _context("tenant-b", operation_id="op-3"),
    )
    assert result.places[0].name == "three"


@pytest.mark.asyncio
async def test_private_cache_never_crosses_tenant_boundary() -> None:
    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("cached", request.query)

    provider = FakePlaceProvider("cached", succeed)
    gateway = ProviderGateway([provider], allowlist=frozenset({"cached"}))
    request = PlaceSearchRequest(query="private preference")

    first = await gateway.search_places(
        request,
        _context(cache_scope=CacheScope.TENANT),
    )
    second = await gateway.search_places(
        request,
        _context(operation_id="op-2", cache_scope=CacheScope.TENANT),
    )
    other_tenant = await gateway.search_places(
        request,
        _context("tenant-b", operation_id="op-3", cache_scope=CacheScope.TENANT),
    )

    assert first == second
    assert other_tenant.places == first.places
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_stale_if_error_is_marked_and_remains_tenant_scoped() -> None:
    now = [100.0]

    async def success_then_fail(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        if provider.calls == 1:
            return _place_result("stale", request.query)
        raise ProviderUnavailableError(provider_id="stale")

    provider = FakePlaceProvider("stale", success_then_fail)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"stale"}),
        policy=GatewayPolicy(max_retries=0),
        cache_ttls={ProviderCapability.PLACE_SEARCH: 0.1},
        stale_if_error={ProviderCapability.PLACE_SEARCH: 10},
        monotonic=lambda: now[0],
    )
    request = PlaceSearchRequest(query="tenant-private")
    first = await gateway.search_places(
        request,
        _context(cache_scope=CacheScope.TENANT),
    )
    now[0] += 1

    stale = await gateway.search_places(
        request,
        _context(operation_id="op-2", cache_scope=CacheScope.TENANT),
    )

    assert first.provenance.freshness_status is FreshnessStatus.FRESH
    assert stale.provenance.freshness_status is FreshnessStatus.STALE
    with pytest.raises(ProviderUnavailableError):
        await gateway.search_places(
            request,
            _context(
                "tenant-b",
                operation_id="op-3",
                cache_scope=CacheScope.TENANT,
            ),
        )


@pytest.mark.asyncio
async def test_idempotency_rejects_key_reuse_with_different_request() -> None:
    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("idempotent", request.query)

    provider = FakePlaceProvider("idempotent", succeed)
    gateway = ProviderGateway([provider], allowlist=frozenset({"idempotent"}))
    context = _context(idempotency_key="idem-key-123")

    await gateway.search_places(PlaceSearchRequest(query="one"), context)
    with pytest.raises(ProviderIdempotencyConflictError):
        await gateway.search_places(PlaceSearchRequest(query="two"), context)

    assert provider.calls == 1


@pytest.mark.asyncio
async def test_cancellation_event_prevents_provider_call() -> None:
    async def succeed(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return _place_result("cancelled")

    provider = FakePlaceProvider("cancelled", succeed)
    gateway = ProviderGateway([provider], allowlist=frozenset({"cancelled"}))
    cancellation_event = asyncio.Event()
    cancellation_event.set()

    with pytest.raises(ProviderCancelledError):
        await gateway.search_places(
            PlaceSearchRequest(query="cancel"),
            _context(cancellation_event=cancellation_event),
        )
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_active_provider_call_receives_cancellation() -> None:
    started = asyncio.Event()
    provider_cancelled = asyncio.Event()

    async def slow(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            provider_cancelled.set()
            raise
        return _place_result("slow-cancel")

    provider = FakePlaceProvider("slow-cancel", slow)
    gateway = ProviderGateway([provider], allowlist=frozenset({"slow-cancel"}))
    cancellation_event = asyncio.Event()
    task = asyncio.create_task(
        gateway.search_places(
            PlaceSearchRequest(query="cancel"),
            _context(timeout_seconds=2, cancellation_event=cancellation_event),
        )
    )
    await started.wait()
    cancellation_event.set()

    with pytest.raises(ProviderCancelledError):
        await task
    assert provider_cancelled.is_set()


@pytest.mark.asyncio
async def test_bulkhead_bounds_concurrent_provider_calls() -> None:
    active = 0
    max_active = 0

    async def measured(
        request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return _place_result("bulkhead", request.query)

    provider = FakePlaceProvider("bulkhead", measured)
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({"bulkhead"}),
        policy=GatewayPolicy(max_concurrency_per_provider=1),
    )

    await asyncio.gather(
        gateway.search_places(PlaceSearchRequest(query="one"), _context()),
        gateway.search_places(
            PlaceSearchRequest(query="two"),
            _context("tenant-b", operation_id="op-2"),
        ),
    )

    assert max_active == 1


@pytest.mark.asyncio
async def test_missing_weather_and_opening_providers_fail_explicitly() -> None:
    missing = UnavailableProvider(
        provider_id="missing-live",
        display_name="Missing live providers",
        capabilities=frozenset(
            {ProviderCapability.WEATHER, ProviderCapability.OPENING_HOURS}
        ),
    )
    gateway = ProviderGateway([missing], allowlist=frozenset({"missing-live"}))

    with pytest.raises(ProviderUnavailableError):
        await gateway.weather(
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
    with pytest.raises(ProviderUnavailableError):
        await gateway.opening_hours(
            OpeningHoursRequest(provider_place_ids=("B0001",)),
            _context(operation_id="op-2"),
        )


@pytest.mark.asyncio
async def test_amap_key_and_raw_error_are_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "super-secret-amap-key"
    seen_urls: list[httpx.URL] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(request.url)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "status": "0",
                "info": f"upstream rejected {secret}",
                "infocode": "99999",
            },
        )

    client = httpx.AsyncClient(
        base_url="https://restapi.amap.com",
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    adapter = AMapProvider(api_key=secret, client=client)

    with caplog.at_level(logging.INFO, logger="httpx"):
        with pytest.raises(ProviderResponseError) as captured:
            await adapter.search_places(PlaceSearchRequest(query="故宫"), _context())

    assert seen_urls[0].scheme == "https"
    assert seen_urls[0].host == "restapi.amap.com"
    serialized = str(captured.value.as_public_detail()) + str(captured.value) + repr(captured.value)
    assert secret not in serialized
    assert "upstream rejected" not in serialized
    assert secret not in caplog.text
    assert "REDACTED" in caplog.text
    await client.aclose()
