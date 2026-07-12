"""Artifact-first Planner, deterministic validation, and publication gate tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from agent.travel_agent.runtime_v2 import (
    DeterministicConstraintValidator,
    DeterministicPlanner,
    DeterministicSemanticVerifier,
    ValidationPolicyService,
)
from agent.travel_agent.runtime_v2.a2a_executors import (
    PlannerA2AExecutor,
    SemanticVerifierA2AExecutor,
    ValidationA2AExecutor,
    build_core_a2a_executors,
)
from agent.travel_agent.a2a.models import (
    AgentExecutionContext,
    AgentInvocation,
    ArtifactInput,
    ArtifactOutput,
    CompletedExecution,
)
from agent.travel_agent.a2a.registry import build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import InMemoryAgentTaskStore
from agent.travel_agent.runtime_v2.orchestrator import LocalA2AAgentMesh, TravelOrchestratorV2
from routepilot_contracts.artifacts import (
    Candidate,
    CandidateSet,
    EvidenceBundle,
    EvidenceClaim,
    EvidenceConflict,
    EvidenceItem,
    TravelerGroup,
    TripBrief,
)
from routepilot_contracts.common import (
    ActorRef,
    ArtifactRef,
    ArtifactType,
    Citation,
    CoordinateSystem,
    Freshness,
    FreshnessStatus,
    GeoPoint,
    MoneyRange,
    PlaceRef,
    SourceKind,
    SourceRef,
    TripDateRange,
)


NOW = datetime(2026, 7, 12, 8, tzinfo=UTC)


def source(source_id: str = "source:test") -> SourceRef:
    return SourceRef(
        source_id=source_id,
        kind=SourceKind.RAG,
        name="Test corpus",
        version="revision-1",
        retrieved_at=NOW,
        publisher="RoutePilot tests",
        license="CC-BY-4.0",
    )


def money(minimum: str, maximum: str) -> MoneyRange:
    return MoneyRange(
        min_amount=minimum,
        max_amount=maximum,
        currency="CNY",
        basis="total",
        observed_at=NOW,
        source=source(),
    )


def place(index: int) -> PlaceRef:
    return PlaceRef(
        place_id=f"place_{index}",
        display_name=f"测试地点 {index}",
        address="北京市",
        country_code="CN",
        timezone="Asia/Shanghai",
        location=GeoPoint(
            latitude=Decimal("39.90") + Decimal(index) / 100,
            longitude=Decimal("116.39") + Decimal(index) / 100,
            coordinate_system=CoordinateSystem.GCJ02,
            accuracy_meters=Decimal("10"),
        ),
        source=source(),
    )


def base_artifact() -> dict[str, object]:
    return {
        "schema_version": 1,
        "version": 1,
        "created_at": NOW,
        "created_by": ActorRef(actor_type="service", actor_id="service:test"),
        "reason": "测试固定输入。",
    }


def build_inputs(
    *,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    conflict: bool = False,
) -> tuple[TripBrief, EvidenceBundle, CandidateSet]:
    destination = place(0)
    brief = TripBrief(
        **base_artifact(),
        artifact_id="artifact_brief",
        artifact_type="TripBrief",
        destination=destination,
        date_window=TripDateRange(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 2),
            timezone="Asia/Shanghai",
        ),
        travelers=TravelerGroup(adults=2),
        budget=money("0", "3000"),
        source=source("source:user"),
    )

    evidence_items: list[EvidenceItem] = []
    citations: list[Citation] = []
    for index in range(1, 5):
        evidence_id = f"evidence_{index}"
        item_source = source(f"source:item_{index}")
        evidence_items.append(
            EvidenceItem(
                evidence_id=evidence_id,
                kind="poi",
                title=f"地点 {index} 资料",
                summary="可用于规划的测试资料。",
                place_ref=place(index),
                claims=[
                    EvidenceClaim(
                        claim_id=f"claim_{index}",
                        statement="地点在测试日期可访问。",
                        confidence=Decimal("0.9"),
                    )
                ],
                source=item_source,
                freshness=Freshness(
                    observed_at=NOW,
                    valid_until=NOW + timedelta(days=30),
                    status=freshness,
                    source=item_source,
                ),
                retrieved_at=NOW,
            )
        )
        citations.append(
            Citation(
                citation_id=f"citation_{index}",
                evidence_id=evidence_id,
                title=f"地点 {index} 资料",
                locator=f"chunk:{index}",
                source=item_source,
            )
        )
    conflicts = (
        [
            EvidenceConflict(
                conflict_id="conflict_1",
                topic="营业时间",
                evidence_refs=["evidence_1", "evidence_2"],
                detail="两个来源给出的营业时间不同。",
                resolution_status="unresolved",
            )
        ]
        if conflict
        else []
    )
    evidence = EvidenceBundle(
        **base_artifact(),
        artifact_id="artifact_evidence",
        artifact_type="EvidenceBundle",
        trip_brief_ref=ArtifactRef(
            artifact_type=ArtifactType.TRIP_BRIEF,
            artifact_id=brief.artifact_id,
            schema_version=1,
            version=1,
        ),
        timezone="Asia/Shanghai",
        evidence=evidence_items,
        citations=citations,
        conflicts=conflicts,
    )
    candidates = CandidateSet(
        **base_artifact(),
        artifact_id="artifact_candidates",
        artifact_type="CandidateSet",
        trip_brief_ref=evidence.trip_brief_ref,
        evidence_bundle_ref=ArtifactRef(
            artifact_type=ArtifactType.EVIDENCE_BUNDLE,
            artifact_id=evidence.artifact_id,
            schema_version=1,
            version=1,
        ),
        timezone="Asia/Shanghai",
        candidates=[
            Candidate(
                candidate_id=f"candidate_{index}",
                category="poi",
                place_ref=place(index),
                rationale="来源充分且符合基础路线。",
                evidence_refs=[f"evidence_{index}"],
                score=Decimal("0.8"),
                estimated_cost=money("100", "200"),
                recommended_duration_minutes=90,
            )
            for index in range(1, 5)
        ],
    )
    return brief, evidence, candidates


@pytest.mark.asyncio
async def test_candidate_plan_passes_independent_publication_gate() -> None:
    brief, evidence, candidates = build_inputs()
    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)

    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)
    semantics = DeterministicSemanticVerifier().verify(plan, evidence)
    report = ValidationPolicyService().combine(plan, constraints, semantics)

    assert plan.status == "candidate"
    assert len(plan.days) == 2
    assert constraints.outcome == "pass"
    assert semantics.outcome == "pass"
    assert semantics.evidence_coverage.coverage_ratio == Decimal(1)
    assert report.verdict == "pass"
    assert report.publishable is True


@pytest.mark.asyncio
async def test_planner_never_repeats_a_single_candidate_to_fill_a_day() -> None:
    brief, evidence, candidates = build_inputs()
    candidates = candidates.model_copy(update={"candidates": candidates.candidates[:1]})

    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)
    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)

    assert all(len(day.time_blocks) == 1 for day in plan.days)
    assert all(
        len({block.place_ref.place_id for block in day.time_blocks})
        == len(day.time_blocks)
        for day in plan.days
    )
    assert not any(
        item.outcome == "fail" and "重复地点" in item.message
        for item in constraints.checks
    )


@pytest.mark.asyncio
async def test_city_placeholder_only_plan_is_blocked_as_low_value() -> None:
    brief, evidence, candidates = build_inputs()
    placeholder = candidates.candidates[0].model_copy(
        update={"place_ref": brief.destination}
    )
    candidates = candidates.model_copy(update={"candidates": [placeholder]})

    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)
    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)
    semantic = DeterministicSemanticVerifier().verify(plan, evidence)
    report = ValidationPolicyService().combine(plan, constraints, semantic)

    assert any(
        item.outcome == "fail" and "城市占位符" in item.message
        for item in constraints.checks
    )
    assert report.publishable is False


@pytest.mark.asyncio
async def test_budget_failure_is_a_publication_blocker() -> None:
    brief, evidence, candidates = build_inputs()
    brief = brief.model_copy(update={"budget": money("0", "100")})
    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)

    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)
    semantics = DeterministicSemanticVerifier().verify(plan, evidence)
    report = ValidationPolicyService().combine(plan, constraints, semantics)

    assert constraints.outcome == "fail"
    assert any(item.category == "budget" and item.outcome == "fail" for item in constraints.checks)
    assert report.verdict == "fail"
    assert report.publishable is False


@pytest.mark.asyncio
async def test_stale_evidence_is_visible_but_not_fabricated_as_current() -> None:
    brief, evidence, candidates = build_inputs(freshness=FreshnessStatus.STALE)
    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)

    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)
    semantics = DeterministicSemanticVerifier().verify(plan, evidence)
    report = ValidationPolicyService().combine(plan, constraints, semantics)

    assert constraints.outcome == "warning"
    assert semantics.outcome == "warning"
    assert report.verdict == "warning"
    assert report.publishable is True
    assert report.warnings


@pytest.mark.asyncio
async def test_unresolved_source_conflict_blocks_publication() -> None:
    brief, evidence, candidates = build_inputs(conflict=True)
    plan = await DeterministicPlanner().build_candidate(brief, candidates, evidence)

    constraints = DeterministicConstraintValidator().validate(brief, plan, evidence)
    semantics = DeterministicSemanticVerifier().verify(plan, evidence)
    report = ValidationPolicyService().combine(plan, constraints, semantics)

    assert semantics.outcome == "fail"
    assert any(item.category == "source_conflict" for item in semantics.risks)
    assert report.publishable is False


@pytest.mark.asyncio
async def test_professional_agents_exchange_only_versioned_a2a_artifacts() -> None:
    brief, evidence, candidates = build_inputs()
    context = AgentExecutionContext(
        tenant_id="tenant-a",
        actor_id="user-a",
        agent_interface_id="planner",
        task_id="task-a",
        context_id="context-a",
        run_id="run-a",
        dispatch_id="00000000-0000-4000-8000-000000000001",
        deadline=NOW + timedelta(minutes=5),
    )
    planner_invocation = AgentInvocation(
        goal="生成候选方案",
        artifacts=[
            ArtifactInput(contract="TripBrief@1", payload=brief.model_dump(mode="json")),
            ArtifactInput(
                contract="EvidenceBundle@1",
                payload=evidence.model_dump(mode="json"),
            ),
            ArtifactInput(
                contract="CandidateSet@1",
                payload=candidates.model_dump(mode="json"),
            ),
        ],
    )
    planned = await PlannerA2AExecutor().execute(context, planner_invocation, None)
    assert planned.kind == "completed"
    plan_payload = planned.artifacts[0].payload

    validation_invocation = AgentInvocation(
        goal="执行确定性校验",
        artifacts=[
            ArtifactInput(contract="TripBrief@1", payload=brief.model_dump(mode="json")),
            ArtifactInput(contract="ItineraryPlan@1", payload=plan_payload),
            ArtifactInput(
                contract="EvidenceBundle@1",
                payload=evidence.model_dump(mode="json"),
            ),
        ],
    )
    validated = await ValidationA2AExecutor().execute(
        context.model_copy(update={"agent_interface_id": "validation"}),
        validation_invocation,
        None,
    )
    assert validated.kind == "completed"

    semantic_invocation = AgentInvocation(
        goal="独立审查证据风险",
        artifacts=[
            ArtifactInput(contract="TripBrief@1", payload=brief.model_dump(mode="json")),
            ArtifactInput(contract="ItineraryPlan@1", payload=plan_payload),
            ArtifactInput(
                contract="EvidenceBundle@1",
                payload=evidence.model_dump(mode="json"),
            ),
            ArtifactInput(
                contract="ConstraintReport@1",
                payload=validated.artifacts[0].payload,
            ),
        ],
    )
    verified = await SemanticVerifierA2AExecutor().execute(
        context.model_copy(update={"agent_interface_id": "semantic-verifier"}),
        semantic_invocation,
        None,
    )

    assert verified.kind == "completed"
    assert verified.artifacts[0].contract == "SemanticRiskReport@1"
    serialized = str(verified.model_dump(mode="json"))
    assert "reasoning" not in serialized
    assert "tool_result" not in serialized


@pytest.mark.asyncio
async def test_orchestrator_uses_four_distinct_a2a_tasks_and_builds_snapshot() -> None:
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
    orchestrator = TravelOrchestratorV2(LocalA2AAgentMesh(task_service))
    progress_events: list[tuple[str, int]] = []

    async def progress(phase: str, label: str, percentage: int) -> None:
        assert label
        progress_events.append((phase, percentage))

    result = await orchestrator.execute(
        tenant_id="tenant-a",
        actor_id="user-a",
        run_id="run-test-001",
        trip_id="trip-test-001",
        title="北京两日",
        brief=brief,
        goal="带父母少走路",
        progress=progress,
    )

    assert [item.interface_id for item in result.task_refs] == [
        "research",
        "planner",
        "validation",
        "semantic-verifier",
    ]
    assert len({item.task_id for item in result.task_refs}) == 4
    assert result.validation.publishable is True
    assert result.snapshot.status == "ready"
    assert result.snapshot.itinerary.status == "validated"
    assert progress_events == [
        ("research", 20),
        ("planning", 45),
        ("validation", 65),
        ("validation", 80),
        ("publishing", 95),
    ]
