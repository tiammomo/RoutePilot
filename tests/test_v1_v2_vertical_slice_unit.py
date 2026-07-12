"""Product Run -> A2A mesh -> Artifact graph vertical-slice test."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agent.travel_agent.a2a.models import (
    A2AActor,
    ArtifactOutput,
    CompletedExecution,
)
from agent.travel_agent.a2a.registry import build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import InMemoryAgentTaskStore
from agent.travel_agent.providers import (
    Coordinate,
    FreshnessStatus,
    GatewayPolicy,
    GeocodeCandidate,
    GeocodeResult,
    Place,
    PlaceSearchResult,
    ProviderCallContext,
    ProviderCapability,
    ProviderDescriptor,
    ProviderGateway,
    ProviderProvenance,
    RouteMatrixCell,
    RouteMatrixRequest,
    RouteMatrixResult,
)
from agent.travel_agent.runtime_v2 import (
    LocalA2AAgentMesh,
    TripBriefFactory,
    TravelOrchestratorV2,
    build_core_a2a_executors,
)
from backend.moyuan_web.v1.models import (
    Principal,
    RunCommand,
    RunCreateRequest,
    RunLifecycle,
    TripCreateRequest,
)
from backend.moyuan_web.v1.runtime import OrchestratedWholeRunExecutor, RunCoordinator
from backend.moyuan_web.v1.store import InMemoryPlatformStore
from tests.runtime_v2.test_planning_validation import build_inputs


class FakeVerticalProvider:
    """Network-impossible provider port covering the complete planning data path."""

    descriptor = ProviderDescriptor(
        provider_id="fake-vertical",
        display_name="Fake vertical provider",
        api_family="test",
        api_version="fixture-v1",
        capabilities=frozenset(
            {
                ProviderCapability.GEOCODE,
                ProviderCapability.PLACE_SEARCH,
                ProviderCapability.ROUTE_MATRIX,
            }
        ),
        configured=True,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[ProviderCapability, object, ProviderCallContext]] = []
        self.closed = False

    @staticmethod
    def _provenance(capability: ProviderCapability) -> ProviderProvenance:
        observed_at = datetime.now(UTC)
        return ProviderProvenance(
            provider_id="fake-vertical",
            provider_version="fixture-v1",
            capability=capability,
            observed_at=observed_at,
            valid_until=observed_at + timedelta(hours=1),
            freshness_status=FreshnessStatus.FRESH,
        )

    async def geocode(self, request, context: ProviderCallContext) -> GeocodeResult:
        self.calls.append((ProviderCapability.GEOCODE, request, context))
        return GeocodeResult(
            candidates=(
                GeocodeCandidate(
                    formatted_address="北京市东城区",
                    coordinate=Coordinate(
                        longitude=116.4074,
                        latitude=39.9042,
                        coordinate_system="GCJ-02",
                    ),
                    country="中国",
                    city="北京市",
                    district="东城区",
                ),
            ),
            provenance=self._provenance(ProviderCapability.GEOCODE),
        )

    async def search_places(self, request, context: ProviderCallContext) -> PlaceSearchResult:
        self.calls.append((ProviderCapability.PLACE_SEARCH, request, context))
        return PlaceSearchResult(
            places=(
                Place(
                    provider_place_id="poi-palace-museum",
                    name="故宫博物院",
                    coordinate=Coordinate(
                        longitude=116.397,
                        latitude=39.918,
                        coordinate_system="GCJ-02",
                    ),
                    address="北京市东城区景山前街4号",
                    category="风景名胜",
                ),
                Place(
                    provider_place_id="poi-temple-of-heaven",
                    name="天坛公园",
                    coordinate=Coordinate(
                        longitude=116.417,
                        latitude=39.882,
                        coordinate_system="GCJ-02",
                    ),
                    address="北京市东城区天坛东里甲1号",
                    category="风景名胜",
                ),
            ),
            provenance=self._provenance(ProviderCapability.PLACE_SEARCH),
        )

    async def route_matrix(
        self,
        request: RouteMatrixRequest,
        context: ProviderCallContext,
    ) -> RouteMatrixResult:
        self.calls.append((ProviderCapability.ROUTE_MATRIX, request, context))
        return RouteMatrixResult(
            cells=(
                RouteMatrixCell(
                    origin_index=0,
                    destination_index=0,
                    distance_meters=5_200,
                    duration_seconds=1_200,
                ),
            ),
            coordinate_system=request.origins[0].coordinate_system,
            provenance=self._provenance(ProviderCapability.ROUTE_MATRIX),
        )

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_v2_product_run_persists_complete_validated_artifact_graph() -> None:
    brief, evidence, candidates = build_inputs()

    class FixtureResearchExecutor:
        async def execute(self, context, invocation, input_response):
            del context, invocation, input_response
            return CompletedExecution(
                artifacts=[
                    ArtifactOutput(
                        contract="EvidenceBundle@1",
                        payload=evidence.model_dump(mode="json"),
                        artifact_id=evidence.artifact_id,
                        name="Evidence",
                    ),
                    ArtifactOutput(
                        contract="CandidateSet@1",
                        payload=candidates.model_dump(mode="json"),
                        artifact_id=candidates.artifact_id,
                        name="Candidates",
                    ),
                ]
            )

    executors = build_core_a2a_executors()
    executors["research"] = FixtureResearchExecutor()
    registry = build_default_registry(executors=executors)
    task_service = TaskService(registry, InMemoryAgentTaskStore())
    executor = OrchestratedWholeRunExecutor(
        TravelOrchestratorV2(LocalA2AAgentMesh(task_service))
    )
    store = InMemoryPlatformStore()
    coordinator = RunCoordinator(store, executor)
    principal = Principal(
        tenant_id="tenant-a",
        user_id="user-a",
        roles=frozenset({"owner"}),
    )
    trip = await store.create_trip(principal, TripCreateRequest(title="北京两日"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(
            command=RunCommand(
                type="trip.plan",
                message="带父母少走路",
                payload={
                    "title": "北京两日",
                    "trip_brief": brief.model_dump(mode="json"),
                },
            )
        ),
        idempotency_key="v2-vertical-slice",
        trace_id="trace-v2-vertical",
    )

    terminal = submitted.run
    for _ in range(100):
        terminal = await store.get_run(principal, submitted.run.run_id)
        if terminal.lifecycle_state in {
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELED,
        }:
            break
        await asyncio.sleep(0.01)

    assert terminal.lifecycle_state == RunLifecycle.COMPLETED
    artifacts = await store.list_artifacts(principal, trip.trip_id)
    assert {artifact.artifact_type for artifact in artifacts} == {
        "TripBrief",
        "EvidenceBundle",
        "CandidateSet",
        "ItineraryPlan",
        "ConstraintReport",
        "SemanticRiskReport",
        "ValidationReport",
        "TripSnapshot",
    }
    snapshot = next(item for item in artifacts if item.artifact_type == "TripSnapshot")
    assert snapshot.status.value == "published"
    assert snapshot.content["status"] == "ready"
    assert (await store.get_trip(principal, trip.trip_id)).current_artifact_id == snapshot.artifact_id

    refs = await task_service.list_run_task_refs(
        A2AActor(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            roles=principal.roles,
        ),
        submitted.run.run_id,
    )
    assert {item.agent_interface_id for item in refs} == {
        "research",
        "planner",
        "validation",
        "semantic-verifier",
    }
    assert all(item.status == "TASK_STATE_COMPLETED" for item in refs)
    await coordinator.close()
    await task_service.shutdown()


@pytest.mark.asyncio
async def test_trip_request_provider_only_vertical_slice_publishes_snapshot() -> None:
    """No RAG fixture: one fake Gateway grounds intake, research, and routing."""

    provider = FakeVerticalProvider()
    gateway = ProviderGateway(
        [provider],
        allowlist=frozenset({provider.descriptor.provider_id}),
        policy=GatewayPolicy(max_retries=0),
    )
    registry = build_default_registry(
        executors=build_core_a2a_executors(providers=gateway)
    )
    task_service = TaskService(registry, InMemoryAgentTaskStore())
    executor = OrchestratedWholeRunExecutor(
        TravelOrchestratorV2(LocalA2AAgentMesh(task_service)),
        brief_factory=TripBriefFactory(gateway),
    )
    store = InMemoryPlatformStore()
    coordinator = RunCoordinator(store, executor)
    principal = Principal(
        tenant_id="tenant-provider-only",
        user_id="user-provider-only",
        roles=frozenset({"owner"}),
    )

    try:
        trip = await store.create_trip(
            principal,
            TripCreateRequest(title="北京 Provider 行程"),
        )
        submitted = await coordinator.submit(
            principal,
            trip.trip_id,
            RunCreateRequest(
                command=RunCommand(
                    type="trip.plan",
                    message="为长辈安排节奏舒缓的北京历史文化行程",
                    payload={
                        "title": "北京 Provider 行程",
                        "trip_request": {
                            "destination": "北京",
                            "start_date": "2026-10-01",
                            "end_date": "2026-10-02",
                            "adults": 2,
                            "seniors": 1,
                            "children_ages": [],
                            "accessibility_needs": ["少走路"],
                            "budget_min": "3000",
                            "budget_max": "6000",
                            "currency": "CNY",
                            "preferences": ["历史文化", "安静节奏"],
                        },
                    },
                )
            ),
            idempotency_key="provider-only-vertical-slice",
            trace_id="trace-provider-only-vertical",
        )

        terminal = submitted.run
        for _ in range(100):
            terminal = await store.get_run(principal, submitted.run.run_id)
            if terminal.lifecycle_state in {
                RunLifecycle.COMPLETED,
                RunLifecycle.FAILED,
                RunLifecycle.CANCELED,
            }:
                break
            await asyncio.sleep(0.01)

        assert terminal.lifecycle_state is RunLifecycle.COMPLETED
        artifacts = await store.list_artifacts(principal, trip.trip_id)
        by_type = {artifact.artifact_type: artifact for artifact in artifacts}
        assert set(by_type) == {
            "TripBrief",
            "EvidenceBundle",
            "CandidateSet",
            "ItineraryPlan",
            "ConstraintReport",
            "SemanticRiskReport",
            "ValidationReport",
            "TripSnapshot",
        }

        assert by_type["TripBrief"].content["destination"]["source"]["kind"] == "provider"
        assert all(
            item["source"]["kind"] == "provider"
            for item in by_type["EvidenceBundle"].content["evidence"]
        )
        transit_legs = [
            block["transit_from_previous"]
            for day in by_type["ItineraryPlan"].content["days"]
            for block in day["time_blocks"]
            if block["transit_from_previous"] is not None
        ]
        assert transit_legs
        assert all(
            leg["provider_snapshot_ref"]["kind"] == "provider" for leg in transit_legs
        )
        assert by_type["ConstraintReport"].content["summary"]["failed"] == 0
        assert by_type["ValidationReport"].content["publishable"] is True

        snapshot = by_type["TripSnapshot"]
        assert snapshot.status.value == "published"
        assert snapshot.content["status"] == "ready"
        persisted_trip = await store.get_trip(principal, trip.trip_id)
        assert persisted_trip.current_artifact_id == snapshot.artifact_id

        capabilities = [capability for capability, _, _ in provider.calls]
        assert capabilities.count(ProviderCapability.GEOCODE) == 1
        assert capabilities.count(ProviderCapability.PLACE_SEARCH) == 1
        assert ProviderCapability.ROUTE_MATRIX in capabilities
        assert all(
            context.tenant_id == principal.tenant_id
            and context.actor_id == principal.user_id
            for _, _, context in provider.calls
        )

        refs = await task_service.list_run_task_refs(
            A2AActor(
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                roles=principal.roles,
            ),
            submitted.run.run_id,
        )
        assert {item.agent_interface_id for item in refs} == {
            "research",
            "planner",
            "validation",
            "semantic-verifier",
        }
        assert all(item.status == "TASK_STATE_COMPLETED" for item in refs)
    finally:
        await coordinator.close()
        await task_service.shutdown()
        await gateway.close()

    assert provider.closed is True
