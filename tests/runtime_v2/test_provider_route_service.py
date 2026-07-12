"""Live Provider Gateway integration at the deterministic Planner boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agent.travel_agent.a2a.models import AgentExecutionContext
from agent.travel_agent.providers import (
    CacheScope,
    FreshnessStatus as ProviderFreshnessStatus,
    GatewayPolicy,
    ProviderCallContext,
    ProviderCapability,
    ProviderDescriptor,
    ProviderGateway,
    ProviderProvenance,
    ProviderUnavailableError,
    RouteMatrixCell,
    RouteMatrixRequest,
    RouteMatrixResult,
    RouteMode,
)
from agent.travel_agent.runtime_v2 import ProviderRouteService
from agent.travel_agent.runtime_v2.a2a_executors import (
    PlannerA2AExecutor,
    ResearchA2AExecutor,
    build_core_a2a_executors,
)
from routepilot_contracts.artifacts import Candidate
from routepilot_contracts.common import (
    CoordinateSystem,
    GeoPoint,
    PlaceRef,
    SourceKind,
    SourceRef,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _source() -> SourceRef:
    return SourceRef(
        source_id="source:test_route",
        kind=SourceKind.RAG,
        name="Route fixture",
        version="1",
        retrieved_at=_now(),
    )


def _candidate(
    candidate_id: str,
    *,
    latitude: str,
    longitude: str,
    coordinate_system: CoordinateSystem = CoordinateSystem.WGS84,
) -> Candidate:
    return Candidate(
        candidate_id=candidate_id,
        category="poi",
        place_ref=PlaceRef(
            place_id=f"place:{candidate_id}",
            display_name=candidate_id,
            country_code="CN",
            timezone="Asia/Shanghai",
            location=GeoPoint(
                latitude=Decimal(latitude),
                longitude=Decimal(longitude),
                coordinate_system=coordinate_system,
            ),
            source=_source(),
        ),
        rationale="Provider route integration fixture.",
        evidence_refs=[f"evidence:{candidate_id}"],
        score=Decimal("0.9"),
    )


def _agent_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        tenant_id="tenant-route-a",
        actor_id="user-route-a",
        agent_interface_id="planner",
        task_id="task-route-a",
        context_id="context-route-a",
        run_id="run-route-a",
        dispatch_id="00000000-0000-4000-8000-000000000031",
        deadline=_now() + timedelta(minutes=5),
    )


class FakeRouteProvider:
    """Deterministic port; no network call is possible from this fake."""

    def __init__(self, *, fail: bool = False, empty: bool = False) -> None:
        self.descriptor = ProviderDescriptor(
            provider_id="fake-route",
            display_name="Fake route provider",
            api_family="test",
            api_version="route-v1",
            capabilities=frozenset({ProviderCapability.ROUTE_MATRIX}),
            configured=True,
        )
        self.fail = fail
        self.empty = empty
        self.requests: list[RouteMatrixRequest] = []
        self.contexts: list[ProviderCallContext] = []

    async def route_matrix(
        self,
        request: RouteMatrixRequest,
        context: ProviderCallContext,
    ) -> RouteMatrixResult:
        self.requests.append(request)
        self.contexts.append(context)
        if self.fail:
            raise ProviderUnavailableError(provider_id=self.descriptor.provider_id)
        observed_at = _now()
        cells: tuple[RouteMatrixCell, ...] = ()
        if not self.empty:
            cells = (
                RouteMatrixCell(
                    origin_index=0,
                    destination_index=0,
                    distance_meters=(700 if request.mode is RouteMode.WALKING else 8_000),
                    duration_seconds=(61 if request.mode is RouteMode.WALKING else 121),
                ),
            )
        return RouteMatrixResult(
            cells=cells,
            coordinate_system=request.origins[0].coordinate_system,
            provenance=ProviderProvenance(
                provider_id=self.descriptor.provider_id,
                provider_version=self.descriptor.api_version,
                capability=ProviderCapability.ROUTE_MATRIX,
                observed_at=observed_at,
                valid_until=observed_at + timedelta(minutes=5),
                freshness_status=ProviderFreshnessStatus.FRESH,
            ),
        )

    async def close(self) -> None:
        return None


def _gateway(provider: FakeRouteProvider) -> ProviderGateway:
    return ProviderGateway(
        [provider],
        allowlist=frozenset({provider.descriptor.provider_id}),
        policy=GatewayPolicy(max_retries=0),
    )


@pytest.mark.asyncio
async def test_provider_route_uses_mode_context_units_and_provenance() -> None:
    provider = FakeRouteProvider()
    gateway = _gateway(provider)
    service = ProviderRouteService(gateway, _agent_context())
    origin = _candidate("candidate:origin", latitude="39.900", longitude="116.390")
    short = _candidate("candidate:short", latitude="39.901", longitude="116.390")
    long = _candidate("candidate:long", latitude="40.100", longitude="116.390")

    walking = await service.route(origin, short)
    driving = await service.route(origin, long)

    assert [request.mode for request in provider.requests] == [
        RouteMode.WALKING,
        RouteMode.DRIVING,
    ]
    assert all(
        request.origins[0].coordinate_system == "WGS-84" for request in provider.requests
    )
    assert walking.mode == "walk"
    assert walking.duration_min_minutes == walking.duration_max_minutes == 2
    assert walking.distance_meters == 700
    assert driving.mode == "drive"
    assert driving.duration_min_minutes == driving.duration_max_minutes == 3
    assert driving.distance_meters == 8_000
    assert walking.provider_snapshot_ref.kind is SourceKind.PROVIDER
    assert walking.provider_snapshot_ref.publisher == "fake-route"
    assert walking.provider_snapshot_ref.version == "route-v1"
    assert all(context.tenant_id == "tenant-route-a" for context in provider.contexts)
    assert all(context.actor_id == "user-route-a" for context in provider.contexts)
    assert all(
        context.operation_id.startswith("task-route-a:route-matrix:")
        for context in provider.contexts
    )
    assert all(context.cache_scope is CacheScope.TENANT for context in provider.contexts)
    assert all(context.deadline_monotonic is not None for context in provider.contexts)


@pytest.mark.asyncio
async def test_provider_error_has_explicit_haversine_fallback() -> None:
    provider = FakeRouteProvider(fail=True)
    service = ProviderRouteService(_gateway(provider), _agent_context())
    origin = _candidate(
        "candidate:origin",
        latitude="39.900",
        longitude="116.390",
        coordinate_system=CoordinateSystem.GCJ02,
    )
    destination = _candidate(
        "candidate:destination",
        latitude="40.100",
        longitude="116.390",
        coordinate_system=CoordinateSystem.GCJ02,
    )

    leg = await service.route(origin, destination)

    assert len(provider.requests) == 1
    assert leg.mode == "transit"
    assert leg.provider_snapshot_ref.kind is SourceKind.SYSTEM
    assert leg.provider_snapshot_ref.name == "route-estimate"
    assert leg.provider_snapshot_ref.version == "haversine-fallback-1"


@pytest.mark.asyncio
async def test_schema_valid_but_logically_invalid_matrix_is_not_swallowed() -> None:
    provider = FakeRouteProvider(empty=True)
    service = ProviderRouteService(_gateway(provider), _agent_context())
    origin = _candidate("candidate:origin", latitude="39.900", longitude="116.390")
    destination = _candidate(
        "candidate:destination", latitude="39.901", longitude="116.390"
    )

    with pytest.raises(ValueError, match="exactly one matrix cell"):
        await service.route(origin, destination)


def test_core_executor_builder_shares_gateway_with_research_and_planner() -> None:
    gateway = _gateway(FakeRouteProvider())

    executors = build_core_a2a_executors(providers=gateway)

    planner = executors["planner"]
    research = executors["research"]
    assert isinstance(planner, PlannerA2AExecutor)
    assert planner.providers is gateway
    assert isinstance(research, ResearchA2AExecutor)
    assert research.providers is gateway
