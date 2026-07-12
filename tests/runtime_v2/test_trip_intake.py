"""Typed workbench request to TripBrief provider-grounding tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from agent.travel_agent.providers import (
    Coordinate,
    FreshnessStatus,
    GeocodeCandidate,
    GeocodeResult,
    OpeningHoursEntry,
    OpeningHoursResult,
    Place,
    PlaceSearchResult,
    ProviderCapability,
    ProviderCancelledError,
    ProviderProvenance,
    WeatherPeriod,
    WeatherResult,
)
from agent.travel_agent.a2a.models import AgentExecutionContext, AgentInvocation, ArtifactInput
from agent.travel_agent.runtime_v2 import (
    ResilientGeocodeService,
    StructuredTripRequest,
    TripBriefFactory,
    TripIntakeError,
)
from agent.travel_agent.runtime_v2.a2a_executors import ResearchA2AExecutor
from routepilot_contracts import validate_contract


class FakeGeocoder:
    def __init__(self, *, empty: bool = False):
        self.empty = empty
        self.requests = []
        self.contexts = []

    async def geocode(self, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        now = datetime.now(UTC)
        return GeocodeResult(
            candidates=()
            if self.empty
            else (
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
            provenance=ProviderProvenance(
                provider_id="amap",
                provider_version="web-service-v3",
                capability=ProviderCapability.GEOCODE,
                observed_at=now,
                valid_until=now + timedelta(days=1),
                freshness_status=FreshnessStatus.FRESH,
            ),
        )

    async def search_places(self, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        now = datetime.now(UTC)
        return PlaceSearchResult(
            places=(
                Place(
                    provider_place_id="amap-palace-museum",
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
                    provider_place_id="amap-temple-of-heaven",
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
            provenance=ProviderProvenance(
                provider_id="amap",
                provider_version="web-service-v3",
                capability=ProviderCapability.PLACE_SEARCH,
                observed_at=now,
                valid_until=now + timedelta(minutes=15),
                freshness_status=FreshnessStatus.FRESH,
            ),
        )


class FakeLiveResearchProvider(FakeGeocoder):
    async def weather(self, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        return WeatherResult(
            periods=(
                WeatherPeriod(
                    starts_at=now,
                    ends_at=now + timedelta(hours=12),
                    condition="晴",
                    temperature_celsius=25,
                ),
            ),
            provenance=self._provenance(ProviderCapability.WEATHER),
        )

    async def opening_hours(self, request, context):
        self.requests.append(request)
        self.contexts.append(context)
        return OpeningHoursResult(
            entries=tuple(
                OpeningHoursEntry(
                    provider_place_id=item,
                    status="unknown",
                    note="周一至周日:08:30-17:30",
                )
                for item in request.provider_place_ids
            ),
            provenance=self._provenance(ProviderCapability.OPENING_HOURS),
        )

    @staticmethod
    def _provenance(capability):
        now = datetime.now(UTC)
        return ProviderProvenance(
            provider_id="amap",
            provider_version="web-service-v3-v5",
            capability=capability,
            observed_at=now,
            valid_until=now + timedelta(minutes=15),
            freshness_status=FreshnessStatus.FRESH,
        )


class FakeCanceledResearchProvider(FakeGeocoder):
    async def weather(self, request, context):
        del request, context
        raise ProviderCancelledError(provider_id="amap")


class FakeUnavailableGeocoder(FakeGeocoder):
    async def geocode(self, request, context):
        del request, context
        from agent.travel_agent.providers import ProviderAuthenticationError

        raise ProviderAuthenticationError(provider_id="amap")


class FakeUnavailableResearchProvider(FakeUnavailableGeocoder):
    async def search_places(self, request, context):
        del request, context
        from agent.travel_agent.providers import ProviderAuthenticationError

        raise ProviderAuthenticationError(provider_id="amap")


def request() -> StructuredTripRequest:
    return StructuredTripRequest(
        destination="北京",
        start_date="2026-10-01",
        end_date="2026-10-03",
        adults=2,
        seniors=1,
        accessibility_needs=["少走路"],
        budget_min="3000",
        budget_max="5000",
        preferences=["历史文化", "安静节奏"],
    )


def near_term_request() -> StructuredTripRequest:
    start = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    return StructuredTripRequest(
        destination="北京",
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=2)).isoformat(),
        adults=2,
        budget_min="3000",
        budget_max="5000",
        preferences=["历史文化"],
    )


@pytest.mark.asyncio
async def test_trip_intake_builds_a_contract_valid_provider_grounded_brief() -> None:
    geocoder = FakeGeocoder()
    brief = await TripBriefFactory(geocoder).build(
        request(),
        tenant_id="tenant-a",
        actor_id="OIDC.User@example.com",
        run_id="run-intake-1",
    )

    parsed = validate_contract("TripBrief@1", brief.model_dump(mode="json"))
    assert parsed.destination.display_name == "北京"
    assert parsed.destination.location.coordinate_system.value == "GCJ-02"
    assert parsed.destination.source.kind.value == "provider"
    assert parsed.travelers.seniors == 1
    assert parsed.budget.max_amount == "5000"
    assert geocoder.requests[0].address == "北京"
    assert geocoder.contexts[0].tenant_id == "tenant-a"
    assert geocoder.contexts[0].cache_scope.value == "tenant"


@pytest.mark.asyncio
async def test_trip_intake_fails_closed_when_provider_cannot_resolve_destination() -> None:
    with pytest.raises(TripIntakeError, match="approved provider") as raised:
        await TripBriefFactory(FakeGeocoder(empty=True)).build(
            request(),
            tenant_id="tenant-a",
            actor_id="user-a",
            run_id="run-intake-2",
        )
    assert raised.value.code == "DESTINATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_trip_intake_uses_approved_city_catalog_when_live_geocoder_is_down() -> None:
    brief = await TripBriefFactory(
        ResilientGeocodeService(FakeUnavailableGeocoder())
    ).build(
        request(),
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-intake-fallback-1",
    )

    assert brief.destination.display_name == "北京"
    assert brief.destination.address == "北京市"
    assert brief.destination.source.publisher == "routepilot-destination-catalog"
    assert brief.destination.location.coordinate_system.value == "WGS84"


@pytest.mark.asyncio
async def test_research_uses_distinct_reviewed_places_when_live_provider_is_down() -> None:
    provider = FakeUnavailableResearchProvider()
    brief = await TripBriefFactory(ResilientGeocodeService(provider)).build(
        StructuredTripRequest(
            destination="北京",
            start_date="2026-07-20",
            end_date="2026-07-20",
            adults=1,
            budget_min="800",
            budget_max="2000",
            preferences=["历史文化", "少排队"],
        ),
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-catalog-research-1",
    )
    result = await ResearchA2AExecutor(providers=provider).execute(
        AgentExecutionContext(
            tenant_id="tenant-a",
            actor_id="user-a",
            agent_interface_id="research",
            task_id="task-catalog-research-1",
            context_id="context-catalog-research-1",
            run_id="run-catalog-research-1",
            dispatch_id="dispatch-catalog-research-1",
            deadline=datetime.now(UTC) + timedelta(seconds=30),
        ),
        AgentInvocation(
            goal="规划北京一日历史文化轻旅行",
            artifacts=[
                ArtifactInput(
                    contract="TripBrief@1",
                    payload=brief.model_dump(mode="json"),
                )
            ],
        ),
        None,
    )

    evidence = validate_contract("EvidenceBundle@1", result.artifacts[0].payload)
    candidates = validate_contract("CandidateSet@1", result.artifacts[1].payload)
    names = [item.place_ref.display_name for item in candidates.candidates]
    assert len(names) >= 4
    assert len(names) == len(set(names))
    assert "北京" not in names
    assert "故宫博物院" not in names  # Monday closure is known and filtered.
    assert all(item.place_ref.source.kind.value == "rag" for item in candidates.candidates)
    assert any("官方来源地点目录" in note for note in candidates.selection_notes)
    assert any(item.source.uri is not None for item in evidence.evidence)


def test_trip_intake_rejects_inconsistent_or_unbounded_constraints() -> None:
    with pytest.raises(ValidationError):
        StructuredTripRequest(
            destination="北京",
            start_date="2026-10-03",
            end_date="2026-10-01",
            adults=0,
            budget_min="5000",
            budget_max="3000",
        )


@pytest.mark.asyncio
async def test_research_agent_can_ground_candidates_from_live_provider_without_rag() -> None:
    provider = FakeGeocoder()
    brief = await TripBriefFactory(provider).build(
        request(),
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-provider-1",
    )
    result = await ResearchA2AExecutor(providers=provider).execute(
        AgentExecutionContext(
            tenant_id="tenant-a",
            actor_id="user-a",
            agent_interface_id="research",
            task_id="task-provider-1",
            context_id="context-provider-1",
            run_id="run-provider-1",
            dispatch_id="dispatch-provider-1",
            deadline=datetime.now(UTC) + timedelta(seconds=30),
        ),
        AgentInvocation(
            goal="为北京三日行程查找历史文化景点",
            artifacts=[
                ArtifactInput(
                    contract="TripBrief@1",
                    payload=brief.model_dump(mode="json"),
                )
            ],
        ),
        None,
    )

    assert len(result.artifacts) == 2
    evidence = validate_contract("EvidenceBundle@1", result.artifacts[0].payload)
    candidates = validate_contract("CandidateSet@1", result.artifacts[1].payload)
    assert {item.title for item in evidence.evidence} == {"故宫博物院", "天坛公园"}
    assert all(item.source.kind.value == "provider" for item in evidence.evidence)
    assert {item.place_ref.display_name for item in candidates.candidates} == {
        "故宫博物院",
        "天坛公园",
    }
    assert any("透明降级" in note for note in candidates.selection_notes)
    assert any("超出实时天气预报窗口" in note for note in candidates.selection_notes)


@pytest.mark.asyncio
async def test_research_adds_live_weather_and_opening_evidence_with_deadlines() -> None:
    provider = FakeLiveResearchProvider()
    brief = await TripBriefFactory(provider).build(
        near_term_request(),
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-provider-live-1",
    )
    result = await ResearchA2AExecutor(providers=provider).execute(
        AgentExecutionContext(
            tenant_id="tenant-a",
            actor_id="user-a",
            agent_interface_id="research",
            task_id="task-provider-live-1",
            context_id="context-provider-live-1",
            run_id="run-provider-live-1",
            dispatch_id="dispatch-provider-live-1",
            deadline=datetime.now(UTC) + timedelta(seconds=30),
        ),
        AgentInvocation(
            goal="为北京三日行程查找历史文化景点并核验天气与营业时间",
            artifacts=[
                ArtifactInput(
                    contract="TripBrief@1",
                    payload=brief.model_dump(mode="json"),
                )
            ],
        ),
        None,
    )

    evidence = validate_contract("EvidenceBundle@1", result.artifacts[0].payload)
    candidates = validate_contract("CandidateSet@1", result.artifacts[1].payload)
    kinds = [item.kind for item in evidence.evidence]
    assert kinds.count("weather") == 1
    assert kinds.count("opening_hours") == 2
    assert all(item.source.kind.value == "provider" for item in evidence.evidence)
    assert any("天气已按目的地时区" in note for note in candidates.selection_notes)
    assert any("营业信息已从实时 Provider 获取" in note for note in candidates.selection_notes)
    provider_contexts = provider.contexts[1:]
    assert {item.operation_id.rsplit(":", 1)[-1] for item in provider_contexts} >= {
        "place-search",
        "weather",
        "opening-hours",
    }
    assert all(item.deadline_monotonic is not None for item in provider_contexts)


@pytest.mark.asyncio
async def test_research_never_turns_provider_cancellation_into_degraded_success() -> None:
    provider = FakeCanceledResearchProvider()
    brief = await TripBriefFactory(provider).build(
        near_term_request(),
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-provider-cancel-1",
    )
    with pytest.raises(ProviderCancelledError):
        await ResearchA2AExecutor(providers=provider).execute(
            AgentExecutionContext(
                tenant_id="tenant-a",
                actor_id="user-a",
                agent_interface_id="research",
                task_id="task-provider-cancel-1",
                context_id="context-provider-cancel-1",
                run_id="run-provider-cancel-1",
                dispatch_id="dispatch-provider-cancel-1",
                deadline=datetime.now(UTC) + timedelta(seconds=30),
            ),
            AgentInvocation(
                goal="测试取消传播",
                artifacts=[
                    ArtifactInput(
                        contract="TripBrief@1",
                        payload=brief.model_dump(mode="json"),
                    )
                ],
            ),
            None,
        )
