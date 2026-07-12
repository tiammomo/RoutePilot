"""Concrete professional-Agent executors behind the A2A Task boundary."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from agent.travel_agent.a2a.models import (
    AgentExecutionContext,
    AgentInvocation,
    ArtifactOutput,
    CompletedExecution,
    ContractName,
    FailedExecution,
    InputResponse,
)
from agent.travel_agent.a2a.registry import AgentExecutor
from agent.travel_agent.providers import (
    CacheScope,
    Coordinate as ProviderCoordinate,
    OpeningHoursRequest,
    OpeningHoursResult,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderCancelledError,
    ProviderCallContext,
    ProviderError,
    ProviderGateway,
    WeatherRequest,
    WeatherResult,
)
from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    KnowledgeError,
    KnowledgeService,
    ResearchQuery,
    RetrievalResult as RetrievalEvidenceBundle,
)
from routepilot_contracts.artifacts import (
    Candidate,
    CandidateSet,
    ConstraintReport,
    EvidenceBundle,
    EvidenceClaim,
    EvidenceConflict,
    EvidenceItem,
    ItineraryPlan,
    TripBrief,
)
from routepilot_contracts.common import (
    ActorRef,
    ArtifactRef,
    ArtifactType,
    Citation,
    Freshness,
    FreshnessStatus,
    GeoPoint,
    ProviderPlaceId,
    PlaceRef,
    SourceKind,
    SourceRef,
)
from routepilot_contracts.validation import validate_contract

from .model_gateway import ModelGatewayError, ResearchDirectiveGenerator
from .place_catalog import ApprovedPlaceCatalog, CatalogPlace
from .planning import DeterministicPlanner, ProviderRouteService
from .shared import new_id, utc_now
from .validation import DeterministicConstraintValidator, DeterministicSemanticVerifier

logger = logging.getLogger(__name__)


def _input(invocation: AgentInvocation, contract: str) -> Any:
    for artifact in invocation.artifacts:
        if artifact.contract == contract:
            return validate_contract(contract, artifact.payload)
    raise ValueError(f"missing required input {contract}")


def _completed(contract: ContractName, artifact: Any, *, name: str) -> CompletedExecution:
    return CompletedExecution(
        artifacts=[
            ArtifactOutput(
                contract=contract,
                payload=artifact.model_dump(mode="json"),
                artifact_id=artifact.artifact_id,
                name=name,
            )
        ]
    )


class PlannerA2AExecutor:
    """Generate one grounded candidate ItineraryPlan."""

    def __init__(
        self,
        planner: DeterministicPlanner | None = None,
        *,
        providers: ProviderGateway | None = None,
    ):
        if planner is not None and providers is not None:
            raise ValueError("planner and providers cannot both define the route service")
        self.planner = planner or (None if providers is not None else DeterministicPlanner())
        self.providers = providers

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ):
        del input_response
        brief = _input(invocation, "TripBrief@1")
        evidence = _input(invocation, "EvidenceBundle@1")
        candidates = _input(invocation, "CandidateSet@1")
        if not isinstance(brief, TripBrief) or not isinstance(evidence, EvidenceBundle):
            raise ValueError("planner received incompatible artifacts")
        if not isinstance(candidates, CandidateSet):
            raise ValueError("planner received incompatible candidates")
        planner = self.planner
        if planner is None:
            if self.providers is None:  # pragma: no cover - constructor invariant
                raise RuntimeError("provider-backed planner is not configured")
            planner = DeterministicPlanner(
                route_service=ProviderRouteService(self.providers, context)
            )
        plan = await planner.build_candidate(brief, candidates, evidence)
        return _completed("ItineraryPlan@1", plan, name="Candidate itinerary")


class ValidationA2AExecutor:
    """Run deterministic constraints independently from the Planner."""

    def __init__(self, validator: DeterministicConstraintValidator | None = None):
        self.validator = validator or DeterministicConstraintValidator()

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ):
        del context, input_response
        brief = _input(invocation, "TripBrief@1")
        plan = _input(invocation, "ItineraryPlan@1")
        evidence = _input(invocation, "EvidenceBundle@1")
        if not isinstance(brief, TripBrief) or not isinstance(plan, ItineraryPlan):
            raise ValueError("validation received incompatible artifacts")
        if not isinstance(evidence, EvidenceBundle):
            raise ValueError("validation requires evidence")
        report = self.validator.validate(brief, plan, evidence)
        return _completed("ConstraintReport@1", report, name="Constraint report")


class SemanticVerifierA2AExecutor:
    """Review evidence and risks without changing the candidate plan."""

    def __init__(self, verifier: DeterministicSemanticVerifier | None = None):
        self.verifier = verifier or DeterministicSemanticVerifier()

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ):
        del context, input_response
        plan = _input(invocation, "ItineraryPlan@1")
        evidence = _input(invocation, "EvidenceBundle@1")
        constraints = _input(invocation, "ConstraintReport@1")
        if not isinstance(plan, ItineraryPlan) or not isinstance(evidence, EvidenceBundle):
            raise ValueError("semantic verifier received incompatible artifacts")
        if not isinstance(constraints, ConstraintReport):
            raise ValueError("semantic verifier requires a constraint report")
        if constraints.plan_ref.artifact_id != plan.artifact_id:
            raise ValueError("constraint report belongs to another plan")
        report = self.verifier.verify(plan, evidence)
        return _completed("SemanticRiskReport@1", report, name="Semantic risk report")


def _source(item: Any) -> SourceRef:
    return SourceRef(
        source_id=f"source:{item.document_id.lower()[:96]}",
        kind=SourceKind.RAG,
        name=item.source_title,
        version=item.source_version,
        uri=item.source_uri,
        retrieved_at=utc_now(),
        publisher=item.source_type,
        license=item.license_id,
    )


def _freshness(item: Any, source: SourceRef) -> Freshness:
    mapping = {
        "fresh": FreshnessStatus.FRESH,
        "stale": FreshnessStatus.STALE,
        "not_yet_valid": FreshnessStatus.UNKNOWN,
        "unknown": FreshnessStatus.UNKNOWN,
    }
    return Freshness(
        observed_at=item.observed_at,
        valid_until=item.valid_until,
        status=mapping[item.freshness_status.value],
        source=source,
    )


def _provider_source(provenance: Any, label: str) -> SourceRef:
    source_hash = hashlib.sha256(
        (
            f"{provenance.provider_id}:{provenance.provider_version}:"
            f"{provenance.capability.value}:{provenance.observed_at.isoformat()}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return SourceRef(
        source_id=f"source:{source_hash}",
        kind=SourceKind.PROVIDER,
        name=f"{provenance.provider_id} {label}",
        version=provenance.provider_version,
        retrieved_at=provenance.observed_at,
        publisher=provenance.provider_id,
    )


def _provider_freshness(provenance: Any, source: SourceRef) -> Freshness:
    return Freshness(
        observed_at=provenance.observed_at,
        valid_until=provenance.valid_until,
        status=FreshnessStatus(provenance.freshness_status.value),
        source=source,
    )


def _evidence_kind(source_type: str) -> str:
    normalized = source_type.casefold()
    for allowed in ("poi", "area", "lodging_area", "opening_hours", "weather", "route", "price", "policy"):
        if allowed in normalized:
            return allowed
    return "poi"


class ResearchA2AExecutor:
    """Retrieve tenant-bound RAG evidence and create a conservative candidate set."""

    def __init__(
        self,
        knowledge: KnowledgeService | None = None,
        *,
        providers: ProviderGateway | None = None,
        directive_generator: ResearchDirectiveGenerator | None = None,
        place_catalog: ApprovedPlaceCatalog | None = None,
        corpus_revision: str | None = None,
    ):
        if knowledge is None and providers is None:
            raise ValueError("research requires knowledge retrieval or a Provider Gateway")
        self.knowledge = knowledge
        self.providers = providers
        self.directive_generator = directive_generator
        self.place_catalog = place_catalog or ApprovedPlaceCatalog()
        self.corpus_revision = corpus_revision or os.getenv(
            "ROUTEPILOT_RAG_CORPUS_REVISION",
            "beijing-v1",
        )

    @staticmethod
    def _provider_context(
        context: AgentExecutionContext,
        suffix: str,
        *,
        maximum_seconds: float = 10.0,
    ) -> ProviderCallContext | None:
        remaining = (context.deadline - utc_now()).total_seconds()
        if remaining <= 0.05:
            return None
        return ProviderCallContext.with_timeout(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            operation_id=f"{context.task_id}:{suffix}",
            timeout_seconds=min(maximum_seconds, remaining),
            cache_scope=CacheScope.TENANT,
        )

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ):
        del input_response
        brief = _input(invocation, "TripBrief@1")
        if not isinstance(brief, TripBrief):
            raise ValueError("research received an incompatible trip brief")
        raw_top_k = invocation.options.get("top_k")
        top_k = (
            int(raw_top_k)
            if isinstance(raw_top_k, (str, int, float)) and not isinstance(raw_top_k, bool)
            else 10
        )
        query = ResearchQuery(
            query=f"{brief.destination.display_name} {invocation.goal}",
            claim_scope="travel.destination",
            corpus_revision=str(
                invocation.options.get("corpus_revision") or self.corpus_revision
            )[:128],
            top_k=min(20, max(3, top_k)),
        )
        place_query = str(invocation.options.get("place_query") or "景点")[:100]
        if self.directive_generator is not None:
            try:
                directive = await self.directive_generator.generate(brief, invocation.goal)
                place_query = directive.place_query
            except ModelGatewayError:
                # Model assistance cannot make the grounded deterministic flow unavailable.
                logger.warning(
                    "research directive unavailable; deterministic fallback selected"
                )
                place_query = "景点"
        catalog_places = self.place_catalog.search(
            brief.destination.display_name,
            local_date=brief.date_window.start_date,
            query=" ".join(
                [place_query, invocation.goal, *(item.value for item in brief.preferences)]
            ),
            limit=min(8, max(4, top_k)),
        )
        retrieved: RetrievalEvidenceBundle | None = None
        if self.knowledge is not None:
            try:
                retrieved = await self.knowledge.retrieve(
                    AuthorizedKnowledgeContext(
                        tenant_id=context.tenant_id,
                        actor_id=context.actor_id,
                    ),
                    query,
                )
            except KnowledgeError:
                if self.providers is None:
                    raise

        live_places: PlaceSearchResult | None = None
        live_weather: WeatherResult | None = None
        live_opening: OpeningHoursResult | None = None
        provider_failures: set[str] = set()
        if self.providers is not None:
            location = brief.destination.location
            coordinate_system = location.coordinate_system.value
            place_context = self._provider_context(context, "place-search")
            try:
                if place_context is None:
                    raise ProviderError()
                live_places = await self.providers.search_places(
                    PlaceSearchRequest(
                        query=place_query,
                        city=brief.destination.display_name,
                        center=ProviderCoordinate(
                            longitude=float(location.longitude),
                            latitude=float(location.latitude),
                            coordinate_system=(
                                "WGS-84" if coordinate_system == "WGS84" else coordinate_system
                            ),
                        ),
                        limit=min(20, max(3, top_k)),
                    ),
                    place_context,
                )
            except ProviderCancelledError:
                raise
            except ProviderError:
                provider_failures.add("place_search")
                if (retrieved is None or not retrieved.items) and not catalog_places:
                    raise

            weather_method = getattr(self.providers, "weather", None)
            weather_context = self._provider_context(context, "weather", maximum_seconds=8)
            destination_today = datetime.now(
                ZoneInfo(brief.destination.timezone)
            ).date()
            weather_relevant = (
                brief.date_window.end_date >= destination_today
                and brief.date_window.start_date
                <= destination_today + timedelta(days=3)
            )
            if (
                weather_relevant
                and callable(weather_method)
                and weather_context is not None
            ):
                try:
                    live_weather = await weather_method(
                        WeatherRequest(
                            coordinate=ProviderCoordinate(
                                longitude=float(location.longitude),
                                latitude=float(location.latitude),
                                coordinate_system=(
                                    "WGS-84"
                                    if coordinate_system == "WGS84"
                                    else coordinate_system
                                ),
                            ),
                            timezone=brief.destination.timezone,
                            forecast_hours=min(
                                168,
                                max(
                                    24,
                                    (
                                        brief.date_window.end_date
                                        - brief.date_window.start_date
                                    ).days
                                    * 24
                                    + 24,
                                ),
                            ),
                        ),
                        weather_context,
                    )
                    if not live_weather.periods:
                        live_weather = None
                        provider_failures.add("weather")
                except ProviderCancelledError:
                    raise
                except ProviderError:
                    provider_failures.add("weather")
            else:
                provider_failures.add(
                    "weather" if weather_relevant else "weather_out_of_window"
                )

            opening_method = getattr(self.providers, "opening_hours", None)
            opening_context = self._provider_context(
                context,
                "opening-hours",
                maximum_seconds=8,
            )
            if (
                live_places is not None
                and live_places.places
                and callable(opening_method)
                and opening_context is not None
            ):
                try:
                    live_opening = await opening_method(
                        OpeningHoursRequest(
                            provider_place_ids=tuple(
                                item.provider_place_id for item in live_places.places
                            ),
                            local_date=str(brief.date_window.start_date),
                        ),
                        opening_context,
                    )
                    if not live_opening.entries:
                        live_opening = None
                        provider_failures.add("opening_hours")
                except ProviderCancelledError:
                    raise
                except ProviderError:
                    provider_failures.add("opening_hours")
            else:
                provider_failures.add("opening_hours")
        return self._convert(
            brief,
            retrieved,
            live_places,
            live_weather,
            live_opening,
            catalog_places,
            provider_failures=frozenset(provider_failures),
            provider_enabled=self.providers is not None,
        )

    @staticmethod
    def _convert(
        brief: TripBrief,
        retrieved: RetrievalEvidenceBundle | None,
        live_places: PlaceSearchResult | None,
        live_weather: WeatherResult | None,
        live_opening: OpeningHoursResult | None,
        catalog_places: tuple[CatalogPlace, ...],
        *,
        provider_failures: frozenset[str],
        provider_enabled: bool,
    ):
        if (
            not (retrieved and retrieved.items)
            and not (live_places and live_places.places)
            and not catalog_places
        ):
            return FailedExecution(
                code="NO_GROUNDED_EVIDENCE",
                message="No eligible evidence was found for this research request.",
            )
        evidence_items: list[EvidenceItem] = []
        citations: list[Citation] = []
        rag_evidence_ids: list[str] = []
        for index, item in enumerate(retrieved.items if retrieved else ()):
            source = _source(item)
            evidence_id = f"evidence_{index}_{new_id('ev')}"
            rag_evidence_ids.append(evidence_id)
            evidence_items.append(
                EvidenceItem(
                    evidence_id=evidence_id,
                    kind=_evidence_kind(item.source_type),
                    title=item.source_title,
                    summary=item.snippet,
                    claims=[
                        EvidenceClaim(
                            claim_id=f"claim_{index}_{new_id('claim')}",
                            statement=item.snippet,
                            confidence=Decimal(str(round(item.scores.fused, 4))),
                        )
                    ],
                    source=source,
                    freshness=_freshness(item, source),
                    retrieved_at=utc_now(),
                )
            )
            citations.append(
                Citation(
                    citation_id=f"citation_{index}_{new_id('citation')}",
                    evidence_id=evidence_id,
                    title=item.source_title,
                    locator=f"chunk:{item.chunk_id}",
                    source=source,
                )
            )
        provider_candidates: list[Candidate] = []
        catalog_candidates: list[Candidate] = []
        provider_place_refs: dict[str, PlaceRef] = {}
        if live_places is not None:
            provenance = live_places.provenance
            provider_source = _provider_source(provenance, "place search")
            for index, place in enumerate(live_places.places):
                evidence_id = f"evidence_provider_{index}_{new_id('ev')}"
                place_id = (
                    "place:"
                    + hashlib.sha256(
                        f"{provenance.provider_id}:{place.provider_place_id}".encode("utf-8")
                    ).hexdigest()[:32]
                )
                coordinate_system = place.coordinate.coordinate_system
                place_ref = PlaceRef(
                    place_id=place_id,
                    display_name=place.name[:256],
                    address=place.address[:256] if place.address else None,
                    country_code=brief.destination.country_code,
                    timezone=brief.destination.timezone,
                    location=GeoPoint(
                        latitude=str(place.coordinate.latitude),
                        longitude=str(place.coordinate.longitude),
                        coordinate_system=(
                            "WGS84" if coordinate_system == "WGS-84" else coordinate_system
                        ),
                    ),
                    provider_ids=[
                        ProviderPlaceId(
                            provider=provenance.provider_id,
                            place_id=place.provider_place_id,
                            version=provenance.provider_version,
                        )
                    ],
                    source=provider_source,
                )
                provider_place_refs[place.provider_place_id] = place_ref
                summary = "；".join(
                    value
                    for value in (
                        place.address,
                        f"类别：{place.category}" if place.category else None,
                    )
                    if value
                ) or f"{place.name} 的实时地点结果。"
                evidence_items.append(
                    EvidenceItem(
                        evidence_id=evidence_id,
                        kind="poi",
                        title=place.name[:256],
                        summary=summary[:2_000],
                        place_ref=place_ref,
                        claims=[
                            EvidenceClaim(
                                claim_id=f"claim_provider_{index}_{new_id('claim')}",
                                statement=f"批准的地点 Provider 返回了 {place.name}。"[:2_000],
                                confidence=Decimal("0.9"),
                            )
                        ],
                        source=provider_source,
                        freshness=_provider_freshness(provenance, provider_source),
                        retrieved_at=utc_now(),
                    )
                )
                citations.append(
                    Citation(
                        citation_id=f"citation_provider_{index}_{new_id('citation')}",
                        evidence_id=evidence_id,
                        title=place.name[:256],
                        locator=f"provider-place:{place.provider_place_id}"[:512],
                        source=provider_source,
                    )
                )
                provider_candidates.append(
                    Candidate(
                        candidate_id=new_id("candidate"),
                        category="poi",
                        place_ref=place_ref,
                        rationale="批准的实时地点 Provider 返回该候选，并保留了观测时间。",
                        evidence_refs=[evidence_id],
                        score=Decimal(str(max(0.5, 0.9 - index * 0.02))),
                    )
                )

        if not provider_candidates:
            for index, catalog_place in enumerate(catalog_places):
                source = catalog_place.source()
                place_ref = catalog_place.place_ref(source)
                evidence_id = f"evidence_catalog_{index}_{new_id('ev')}"
                evidence_items.append(
                    EvidenceItem(
                        evidence_id=evidence_id,
                        kind="poi",
                        title=catalog_place.name,
                        summary=catalog_place.summary,
                        place_ref=place_ref,
                        claims=[
                            EvidenceClaim(
                                claim_id=f"claim_catalog_{index}_{new_id('claim')}",
                                statement=(
                                    f"受审官方来源确认 {catalog_place.name} 位于"
                                    f"{catalog_place.address}；"
                                    "营业、预约和票价属于待实时复核信息。"
                                ),
                                confidence=Decimal("0.85"),
                            )
                        ],
                        source=source,
                        freshness=catalog_place.freshness(source),
                        retrieved_at=utc_now(),
                    )
                )
                citations.append(
                    Citation(
                        citation_id=f"citation_catalog_{index}_{new_id('citation')}",
                        evidence_id=evidence_id,
                        title=catalog_place.source_name,
                        locator=f"official-place:{catalog_place.slug}",
                        source=source,
                    )
                )
                catalog_candidates.append(
                    Candidate(
                        candidate_id=new_id("candidate"),
                        category="poi",
                        place_ref=place_ref,
                        rationale=(
                            "地点身份、地址与主题来自受审官方页面；动态开放信息已明确标记为待核验。"
                        ),
                        evidence_refs=[evidence_id],
                        score=Decimal(str(max(0.65, 0.88 - index * 0.03))),
                        estimated_cost=catalog_place.estimated_cost(source),
                        recommended_duration_minutes=catalog_place.duration_minutes,
                        tags=list(catalog_place.tags),
                    )
                )

        if live_weather is not None:
            provenance = live_weather.provenance
            weather_source = _provider_source(provenance, "weather forecast")
            weather_id = f"evidence_weather_{new_id('ev')}"
            periods = live_weather.periods[:14]
            summary = "；".join(
                f"{item.starts_at.isoformat()} {item.condition} {item.temperature_celsius:g}°C"
                for item in periods
            )[:2_000]
            evidence_items.append(
                EvidenceItem(
                    evidence_id=weather_id,
                    kind="weather",
                    title=f"{brief.destination.display_name}天气预报"[:256],
                    summary=summary,
                    place_ref=brief.destination,
                    claims=[
                        EvidenceClaim(
                            claim_id=f"claim_weather_{index}_{new_id('claim')}",
                            statement=(
                                f"{item.starts_at.isoformat()} 至 {item.ends_at.isoformat()}"
                                f"预计为{item.condition}，气温{item.temperature_celsius:g}°C。"
                            )[:2_000],
                            confidence=Decimal("0.85"),
                        )
                        for index, item in enumerate(periods)
                    ],
                    source=weather_source,
                    freshness=_provider_freshness(provenance, weather_source),
                    retrieved_at=utc_now(),
                )
            )
            citations.append(
                Citation(
                    citation_id=f"citation_weather_{new_id('citation')}",
                    evidence_id=weather_id,
                    title=f"{brief.destination.display_name}天气预报"[:256],
                    locator="provider-weather:forecast",
                    source=weather_source,
                )
            )

        if live_opening is not None:
            provenance = live_opening.provenance
            opening_source = _provider_source(provenance, "opening hours")
            for index, entry in enumerate(live_opening.entries):
                place_ref = provider_place_refs.get(entry.provider_place_id)
                if place_ref is None:
                    continue
                evidence_id = f"evidence_opening_{index}_{new_id('ev')}"
                interval_text = "、".join(entry.intervals)
                summary = "；".join(
                    item
                    for item in (
                        f"状态：{entry.status}",
                        f"时段：{interval_text}" if interval_text else None,
                        entry.note,
                    )
                    if item
                )[:2_000]
                evidence_items.append(
                    EvidenceItem(
                        evidence_id=evidence_id,
                        kind="opening_hours",
                        title=f"{place_ref.display_name}营业信息"[:256],
                        summary=summary,
                        place_ref=place_ref,
                        claims=[
                            EvidenceClaim(
                                claim_id=f"claim_opening_{index}_{new_id('claim')}",
                                statement=(
                                    f"实时 Provider 对 {place_ref.display_name} 返回营业状态"
                                    f" {entry.status}"
                                    + (f"，时段为 {interval_text}" if interval_text else "")
                                    + "。"
                                )[:2_000],
                                confidence=(
                                    Decimal("0.8")
                                    if entry.intervals or entry.status != "unknown"
                                    else Decimal("0.5")
                                ),
                            )
                        ],
                        source=opening_source,
                        freshness=_provider_freshness(provenance, opening_source),
                        retrieved_at=utc_now(),
                    )
                )
                citations.append(
                    Citation(
                        citation_id=f"citation_opening_{index}_{new_id('citation')}",
                        evidence_id=evidence_id,
                        title=f"{place_ref.display_name}营业信息"[:256],
                        locator=f"provider-place:{entry.provider_place_id}:business"[:512],
                        source=opening_source,
                    )
                )
        conflicts = [
            EvidenceConflict.model_validate(item)
            for item in (retrieved.conflicts if retrieved else ())
            if isinstance(item, dict)
        ]
        bundle = EvidenceBundle(
            artifact_id=new_id("artifact"),
            artifact_type="EvidenceBundle",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=ActorRef(actor_type="agent", actor_id="agent:research"),
            reason="合并授权知识库与实时 Provider 结果，形成带来源和时效的旅行证据。",
            trip_brief_ref=ArtifactRef(
                artifact_type=ArtifactType.TRIP_BRIEF,
                artifact_id=brief.artifact_id,
                schema_version=1,
                version=brief.version,
            ),
            timezone=brief.destination.timezone,
            evidence=evidence_items,
            citations=citations,
            conflicts=conflicts,
        )
        if provider_candidates:
            candidates = provider_candidates
            selection_notes = ["POI 来自批准的实时 Provider，并保留来源与观测时间。"]
        elif catalog_candidates:
            candidates = catalog_candidates
            selection_notes = [
                "实时 POI Provider 不可用，本轮使用受审官方来源地点目录；",
                "已按行程日期排除已知固定闭馆日，营业、预约与临时闭馆仍需出发前复核。",
            ]
        else:
            assert retrieved is not None and retrieved.items
            candidates = [
                Candidate(
                    candidate_id=new_id("candidate"),
                    category="area",
                    place_ref=brief.destination,
                    rationale="用户明确指定的目的地，已有知识库证据支持。",
                    evidence_refs=rag_evidence_ids,
                    score=Decimal(
                        str(round(max(item.scores.fused for item in retrieved.items), 4))
                    ),
                )
            ]
            selection_notes = ["缺少实时 POI Provider，因此不虚构具体地点。"]
        if provider_enabled:
            if live_weather is not None:
                selection_notes.append(
                    f"天气已按目的地时区 {brief.destination.timezone} 从实时 Provider 获取；"
                    "仅覆盖 Provider 返回的近期窗口。"
                )
            elif "weather" in provider_failures:
                selection_notes.append(
                    "实时天气能力本轮不可用，已透明降级；出发前仍需独立核验天气。"
                )
            elif "weather_out_of_window" in provider_failures:
                selection_notes.append(
                    "行程日期超出实时天气预报窗口，未用当前天气替代；临近出发时需重新获取。"
                )
            if live_opening is not None:
                selection_notes.append(
                    "营业信息已从实时 Provider 获取；unknown 表示 Provider 未给出可确认状态。"
                )
            elif "opening_hours" in provider_failures:
                selection_notes.append(
                    "实时营业信息本轮不可用，已透明降级；到访前仍需独立核验。"
                )
            if "place_search" in provider_failures:
                selection_notes.append("实时 POI 检索失败，本轮候选仅使用已有授权证据。")
        candidate = CandidateSet(
            artifact_id=new_id("artifact"),
            artifact_type="CandidateSet",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=ActorRef(actor_type="agent", actor_id="agent:research"),
            reason="从具有显式来源的证据中生成候选，未使用模型臆测地点。",
            trip_brief_ref=bundle.trip_brief_ref,
            evidence_bundle_ref=ArtifactRef(
                artifact_type=ArtifactType.EVIDENCE_BUNDLE,
                artifact_id=bundle.artifact_id,
                schema_version=1,
                version=bundle.version,
            ),
            timezone=bundle.timezone,
            candidates=candidates,
            selection_notes=selection_notes,
        )
        return CompletedExecution(
            artifacts=[
                ArtifactOutput(
                    contract="EvidenceBundle@1",
                    payload=bundle.model_dump(mode="json"),
                    artifact_id=bundle.artifact_id,
                    name="Grounded evidence",
                ),
                ArtifactOutput(
                    contract="CandidateSet@1",
                    payload=candidate.model_dump(mode="json"),
                    artifact_id=candidate.artifact_id,
                    name="Destination candidates",
                ),
            ]
        )


def build_core_a2a_executors(
    *,
    knowledge: KnowledgeService | None = None,
    providers: ProviderGateway | None = None,
    directive_generator: ResearchDirectiveGenerator | None = None,
) -> dict[str, AgentExecutor]:
    """Build local Agent executors; Research needs RAG, live providers, or both."""

    executors: dict[str, AgentExecutor] = {
        "planner": PlannerA2AExecutor(providers=providers),
        "validation": ValidationA2AExecutor(),
        "semantic-verifier": SemanticVerifierA2AExecutor(),
    }
    if knowledge is not None or providers is not None:
        executors["research"] = ResearchA2AExecutor(
            knowledge,
            providers=providers,
            directive_generator=directive_generator,
        )
    return executors


__all__ = [
    "PlannerA2AExecutor",
    "ResearchA2AExecutor",
    "SemanticVerifierA2AExecutor",
    "ValidationA2AExecutor",
    "build_core_a2a_executors",
]
