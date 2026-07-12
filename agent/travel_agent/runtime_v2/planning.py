"""Deterministic planning primitives used by the V2 Planner Agent.

The planner deliberately produces a conservative candidate. It never invents
places or evidence: every time block originates in ``CandidateSet`` and every
citation originates in ``EvidenceBundle``.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Protocol

from agent.travel_agent.a2a.models import AgentExecutionContext
from agent.travel_agent.providers import (
    CacheScope,
    Coordinate as ProviderCoordinate,
    ProviderCallContext,
    ProviderError,
    ProviderGateway,
    ProviderTimeoutError,
    RouteMatrixRequest,
    RouteMode,
)
from routepilot_contracts.artifacts import (
    BudgetCategoryTotal,
    BudgetSummary,
    Candidate,
    CandidateSet,
    Citation,
    EvidenceBundle,
    ItineraryPlan,
    PlanDay,
    PlanTimeBlock,
    RouteSummary,
    TripBrief,
)
from routepilot_contracts.common import (
    ArtifactType,
    MoneyRange,
    SourceKind,
    SourceRef,
    TransitLeg,
    ZonedTimeRange,
)

from .shared import artifact_ref, new_id, system_actor, system_source, utc_now


class RouteService(Protocol):
    async def route(self, origin: Candidate, destination: Candidate) -> TransitLeg: ...


@dataclass(frozen=True, slots=True)
class PlanningPolicy:
    """Deterministic scheduling limits, versioned with the generated plan."""

    version: str = "planner-policy-1"
    day_start_hour: int = 9
    day_end_hour: int = 20
    max_blocks_per_day: int = 4
    default_duration_minutes: int = 120
    minimum_buffer_minutes: int = 15


class HaversineRouteService:
    """Offline route estimate for fallback/testing, clearly marked non-provider."""

    version = "haversine-fallback-1"

    async def route(self, origin: Candidate, destination: Candidate) -> TransitLeg:
        distance = _haversine_distance_meters(origin, destination)
        if distance <= 1_500:
            mode, speed_m_per_minute = "walk", 70
        else:
            mode, speed_m_per_minute = "transit", 300
        minimum = max(0, math.ceil(distance / speed_m_per_minute))
        maximum = max(minimum, math.ceil(minimum * 1.35) + 5)
        return TransitLeg(
            mode=mode,
            duration_min_minutes=minimum,
            duration_max_minutes=maximum,
            distance_meters=distance,
            provider_snapshot_ref=system_source("route-estimate", self.version),
        )


def _haversine_distance_meters(origin: Candidate, destination: Candidate) -> int:
    left = origin.place_ref.location
    right = destination.place_ref.location
    if left.coordinate_system != right.coordinate_system:
        raise ValueError("routing requires origin and destination in one coordinate system")
    lat1, lon1 = math.radians(float(left.latitude)), math.radians(float(left.longitude))
    lat2, lon2 = math.radians(float(right.latitude)), math.radians(float(right.longitude))
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return int(6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))


def _provider_coordinate(candidate: Candidate) -> ProviderCoordinate:
    point = candidate.place_ref.location
    coordinate_system: Literal["GCJ-02", "WGS-84"]
    if point.coordinate_system.value == "WGS84":
        coordinate_system = "WGS-84"
    elif point.coordinate_system.value == "GCJ-02":
        coordinate_system = "GCJ-02"
    else:
        raise ValueError(
            f"provider routing does not support {point.coordinate_system.value} coordinates"
        )
    return ProviderCoordinate(
        longitude=float(point.longitude),
        latitude=float(point.latitude),
        coordinate_system=coordinate_system,
    )


class ProviderRouteService:
    """Context-bound live routing with a provenance-visible offline fallback."""

    def __init__(
        self,
        gateway: ProviderGateway,
        context: AgentExecutionContext,
        *,
        fallback: RouteService | None = None,
        walking_threshold_meters: int = 1_500,
        timeout_seconds: float = 10.0,
    ) -> None:
        if walking_threshold_meters < 0:
            raise ValueError("walking_threshold_meters cannot be negative")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.gateway = gateway
        self.context = context
        self.fallback = fallback or HaversineRouteService()
        self.walking_threshold_meters = walking_threshold_meters
        self.timeout_seconds = timeout_seconds

    async def route(self, origin: Candidate, destination: Candidate) -> TransitLeg:
        straight_line_distance = _haversine_distance_meters(origin, destination)
        provider_origin = _provider_coordinate(origin)
        provider_destination = _provider_coordinate(destination)
        if provider_origin.coordinate_system != provider_destination.coordinate_system:
            raise ValueError("provider routing cannot mix coordinate systems")
        route_mode = (
            RouteMode.WALKING
            if straight_line_distance <= self.walking_threshold_meters
            else RouteMode.DRIVING
        )
        operation_digest = hashlib.sha256(
            (
                f"{self.context.task_id}:{origin.candidate_id}:"
                f"{destination.candidate_id}:{route_mode.value}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        operation_suffix = f":route-matrix:{operation_digest}"
        operation_id = f"{self.context.task_id[: 200 - len(operation_suffix)]}{operation_suffix}"
        remaining_seconds = (self.context.deadline - utc_now()).total_seconds()

        try:
            if remaining_seconds <= 0:
                raise ProviderTimeoutError()
            result = await self.gateway.route_matrix(
                RouteMatrixRequest(
                    origins=(provider_origin,),
                    destinations=(provider_destination,),
                    mode=route_mode,
                ),
                ProviderCallContext.with_timeout(
                    tenant_id=self.context.tenant_id,
                    actor_id=self.context.actor_id,
                    operation_id=operation_id,
                    idempotency_key=f"route:{operation_digest}",
                    timeout_seconds=min(self.timeout_seconds, remaining_seconds),
                    cache_scope=CacheScope.TENANT,
                ),
            )
        except ProviderError:
            return await self.fallback.route(origin, destination)

        if result.coordinate_system != provider_origin.coordinate_system:
            raise ValueError("route provider changed the coordinate system")
        if len(result.cells) != 1:
            raise ValueError("route provider must return exactly one matrix cell")
        cell = result.cells[0]
        if cell.origin_index != 0 or cell.destination_index != 0:
            raise ValueError("route provider returned invalid matrix indexes")

        provenance = result.provenance
        source_digest = hashlib.sha256(
            (
                f"{provenance.provider_id}:{provenance.provider_version}:"
                f"{provenance.observed_at.isoformat()}:{operation_digest}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        duration_minutes = math.ceil(cell.duration_seconds / 60)
        return TransitLeg(
            mode="walk" if route_mode is RouteMode.WALKING else "drive",
            duration_min_minutes=duration_minutes,
            duration_max_minutes=duration_minutes,
            distance_meters=cell.distance_meters,
            provider_snapshot_ref=SourceRef(
                source_id=f"source:route_{source_digest}",
                kind=SourceKind.PROVIDER,
                name=f"{provenance.provider_id} route matrix",
                version=provenance.provider_version,
                retrieved_at=provenance.observed_at,
                publisher=provenance.provider_id,
            ),
        )


def _decimal_text(value: Decimal) -> str:
    normalized = format(max(Decimal(0), value), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _money(
    minimum: Decimal,
    maximum: Decimal,
    *,
    currency: str,
    source: SourceRef,
) -> MoneyRange:
    return MoneyRange(
        min_amount=_decimal_text(minimum),
        max_amount=_decimal_text(maximum),
        currency=currency,
        basis="total",
        observed_at=utc_now(),
        source=source,
    )


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=index) for index in range((end - start).days + 1)]


class DeterministicPlanner:
    """Build a schema-valid candidate plan from approved candidates and evidence."""

    def __init__(
        self,
        route_service: RouteService | None = None,
        policy: PlanningPolicy | None = None,
    ) -> None:
        self.route_service = route_service or HaversineRouteService()
        self.policy = policy or PlanningPolicy()

    @staticmethod
    def _citations(evidence: EvidenceBundle) -> list[Citation]:
        if evidence.citations:
            return list(evidence.citations)
        first = evidence.evidence[0]
        return [
            Citation(
                citation_id=new_id("citation"),
                evidence_id=first.evidence_id,
                title=first.title,
                locator=f"evidence:{first.evidence_id}",
                source=first.source,
            )
        ]

    async def build_candidate(
        self,
        brief: TripBrief,
        candidates: CandidateSet,
        evidence: EvidenceBundle,
    ) -> ItineraryPlan:
        if candidates.trip_brief_ref.artifact_id != brief.artifact_id:
            raise ValueError("candidate set does not belong to the supplied trip brief")
        if candidates.evidence_bundle_ref.artifact_id != evidence.artifact_id:
            raise ValueError("candidate set does not belong to the supplied evidence bundle")
        if brief.destination.timezone != candidates.timezone or evidence.timezone != candidates.timezone:
            raise ValueError("planner inputs must share one timezone")

        avoid_terms = [
            item.description.casefold()
            for item in brief.constraints
            if item.hard and item.constraint_type == "avoid"
        ]
        visit_terms = [
            item.description.casefold()
            for item in brief.constraints
            if item.hard and item.constraint_type == "visit"
        ]
        eligible = [
            item
            for item in candidates.candidates
            if not any(term in item.place_ref.display_name.casefold() for term in avoid_terms)
        ]
        if not eligible:
            raise ValueError("hard avoid constraints removed every grounded candidate")
        retained = [
            item
            for term in visit_terms
            for item in eligible
            if term in item.place_ref.display_name.casefold()
        ]
        retained_ids = {item.candidate_id for item in retained}
        planning_candidates = [*retained, *(item for item in eligible if item.candidate_id not in retained_ids)]

        dates = _dates(brief.date_window.start_date, brief.date_window.end_date)
        source = system_source("deterministic-planner", self.policy.version)
        currency = brief.budget.currency
        days: list[PlanDay] = []
        total_min = Decimal(0)
        total_max = Decimal(0)
        route_distance = 0
        route_duration = 0
        route_legs = 0
        cursor = 0

        for day_index, local_date in enumerate(dates):
            blocks: list[PlanTimeBlock] = []
            day_min = Decimal(0)
            day_max = Decimal(0)
            current_time = datetime.combine(local_date, time(self.policy.day_start_hour), tzinfo=None)
            previous: Candidate | None = None

            # Never manufacture apparent variety by cycling the same small
            # candidate set. A shorter honest plan is better than duplicates.
            for block_index in range(
                min(self.policy.max_blocks_per_day, len(planning_candidates))
            ):
                candidate = planning_candidates[cursor % len(planning_candidates)]
                cursor += 1
                transit: TransitLeg | None = None
                if previous is not None:
                    transit = await self.route_service.route(previous, candidate)
                    current_time += timedelta(
                        minutes=transit.duration_max_minutes + self.policy.minimum_buffer_minutes
                    )
                    route_distance += transit.distance_meters
                    route_duration += transit.duration_max_minutes
                    route_legs += 1

                duration = min(
                    240,
                    candidate.recommended_duration_minutes or self.policy.default_duration_minutes,
                )
                end_time = current_time + timedelta(minutes=duration)
                if blocks and end_time.hour >= self.policy.day_end_hour:
                    break
                cost = candidate.estimated_cost or _money(
                    Decimal(0), Decimal(0), currency=currency, source=source
                )
                if cost.currency != currency:
                    raise ValueError("candidate costs must use the trip budget currency")
                day_min += Decimal(cost.min_amount)
                day_max += Decimal(cost.max_amount)
                blocks.append(
                    PlanTimeBlock(
                        block_id=f"block_{day_index}_{block_index}_{new_id('item')}",
                        title=candidate.place_ref.display_name,
                        category="visit",
                        place_ref=candidate.place_ref,
                        time_range=ZonedTimeRange(
                            local_date=local_date,
                            start_local_time=current_time.time(),
                            end_local_time=end_time.time(),
                            timezone=candidates.timezone,
                        ),
                        duration_minutes=duration,
                        transit_from_previous=transit,
                        cost_range=cost,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                current_time = end_time
                previous = candidate

            if not blocks:
                raise ValueError("planning policy could not place at least one candidate per day")
            daily_cost = _money(day_min, day_max, currency=currency, source=source)
            total_min += day_min
            total_max += day_max
            days.append(
                PlanDay(
                    date=local_date,
                    timezone=candidates.timezone,
                    time_blocks=blocks,
                    day_summary=f"{local_date.isoformat()} 的候选行程，包含 {len(blocks)} 个地点。",
                    daily_cost=daily_cost,
                )
            )

        estimated_total = _money(total_min, total_max, currency=currency, source=source)
        return ItineraryPlan(
            artifact_id=new_id("artifact"),
            artifact_type="ItineraryPlan",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=system_actor("planner"),
            reason="根据已批准的候选地点和证据生成可校验的候选行程。",
            plan_id=new_id("plan"),
            status="candidate",
            trip_brief_ref=artifact_ref(brief, ArtifactType.TRIP_BRIEF),
            candidate_set_ref=artifact_ref(candidates, ArtifactType.CANDIDATE_SET),
            evidence_bundle_ref=artifact_ref(evidence, ArtifactType.EVIDENCE_BUNDLE),
            timezone=candidates.timezone,
            days=days,
            budget_summary=BudgetSummary(
                estimated_total=estimated_total,
                category_totals=[BudgetCategoryTotal(category="other", cost=estimated_total)],
                contingency_percent=Decimal("10"),
            ),
            route_summary=RouteSummary(
                total_distance_meters=route_distance,
                total_transit_duration_minutes=route_duration,
                legs_count=route_legs,
                source=system_source("route-summary", "1"),
            ),
            citations=self._citations(evidence),
        )
