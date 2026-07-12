"""Version-one RoutePilot artifact contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from .common import (
    ArtifactBase,
    ArtifactRef,
    Citation,
    ContractModel,
    CountryCode,
    Freshness,
    IanaTimezone,
    Identifier,
    MoneyRange,
    NonEmptyText,
    PlaceRef,
    Severity,
    ShortText,
    SourceRef,
    TransitLeg,
    TripDateRange,
    VersionedComponent,
    ZonedTimeRange,
)


class TravelerGroup(ContractModel):
    adults: Annotated[int, Field(ge=0, le=99)]
    children_ages: list[Annotated[int, Field(ge=0, le=17)]] = Field(
        default_factory=list, max_length=30
    )
    seniors: Annotated[int, Field(ge=0, le=99)] = 0
    rooms: Annotated[int, Field(ge=0, le=50)] = 0
    accessibility_needs: list[ShortText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_traveler(self) -> TravelerGroup:
        if self.adults + len(self.children_ages) + self.seniors < 1:
            raise ValueError("at least one traveler is required")
        return self


class TravelPreference(ContractModel):
    preference_id: Identifier
    category: Literal[
        "pace", "food", "culture", "nature", "shopping", "lodging", "mobility", "other"
    ]
    value: ShortText
    priority: Annotated[int, Field(ge=1, le=5)]


class ConstraintSpec(ContractModel):
    constraint_id: Identifier
    constraint_type: Literal[
        "date", "budget", "mobility", "dietary", "lodging", "visit", "avoid", "other"
    ]
    hard: bool
    priority: Annotated[int, Field(ge=1, le=5)]
    description: NonEmptyText
    source: SourceRef


class ClarificationItem(ContractModel):
    question_id: Identifier
    prompt: NonEmptyText
    required: bool
    status: Literal["open", "answered", "dismissed"]
    answer: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_answer(self) -> ClarificationItem:
        if self.status == "answered" and self.answer is None:
            raise ValueError("answered clarification requires an answer")
        if self.status != "answered" and self.answer is not None:
            raise ValueError("only answered clarification can carry an answer")
        return self


class TripBrief(ArtifactBase):
    artifact_type: Literal["TripBrief"]
    destination: PlaceRef
    date_window: TripDateRange
    travelers: TravelerGroup
    budget: MoneyRange
    preferences: list[TravelPreference] = Field(default_factory=list, max_length=50)
    constraints: list[ConstraintSpec] = Field(default_factory=list, max_length=100)
    clarification_items: list[ClarificationItem] = Field(default_factory=list, max_length=30)
    source: SourceRef

    @model_validator(mode="after")
    def validate_context(self) -> TripBrief:
        if self.destination.timezone != self.date_window.timezone:
            raise ValueError("destination and trip date window timezones must match")
        if self.budget.currency.strip() != self.budget.currency:
            raise ValueError("currency must not contain whitespace")
        return self


class EvidenceClaim(ContractModel):
    claim_id: Identifier
    statement: NonEmptyText
    confidence: Annotated[Decimal, Field(ge=0, le=1)]


class EvidenceItem(ContractModel):
    evidence_id: Identifier
    kind: Literal[
        "poi", "area", "lodging_area", "opening_hours", "weather", "route", "price", "policy"
    ]
    title: ShortText
    summary: NonEmptyText
    place_ref: PlaceRef | None = None
    claims: list[EvidenceClaim] = Field(min_length=1, max_length=100)
    source: SourceRef
    freshness: Freshness
    retrieved_at: AwareDatetime

    @model_validator(mode="after")
    def validate_provenance(self) -> EvidenceItem:
        if self.freshness.source.source_id != self.source.source_id:
            raise ValueError("freshness source must match evidence source")
        return self


class EvidenceConflict(ContractModel):
    conflict_id: Identifier
    topic: ShortText
    evidence_refs: list[Identifier] = Field(min_length=2, max_length=20)
    detail: NonEmptyText
    resolution_status: Literal["unresolved", "resolved", "accepted_risk"]


class EvidenceBundle(ArtifactBase):
    artifact_type: Literal["EvidenceBundle"]
    trip_brief_ref: ArtifactRef
    timezone: IanaTimezone
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=1_000)
    citations: list[Citation] = Field(default_factory=list, max_length=1_000)
    conflicts: list[EvidenceConflict] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_references(self) -> EvidenceBundle:
        if self.trip_brief_ref.artifact_type.value != "TripBrief":
            raise ValueError("trip_brief_ref must reference TripBrief")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        known = set(evidence_ids)
        for citation in self.citations:
            if citation.evidence_id not in known:
                raise ValueError("citation references unknown evidence")
        for conflict in self.conflicts:
            if not set(conflict.evidence_refs).issubset(known):
                raise ValueError("conflict references unknown evidence")
        return self


class TravelQuestion(ArtifactBase):
    """Bounded user-authored question passed to the Answering Agent."""

    artifact_type: Literal["TravelQuestion"]
    question: NonEmptyText
    locale: Annotated[str, Field(min_length=2, max_length=32)] = "zh-CN"
    destination_hint: ShortText | None = None
    asked_at: AwareDatetime
    source: SourceRef

    @model_validator(mode="after")
    def validate_source(self) -> TravelQuestion:
        if self.source.kind.value != "user":
            raise ValueError("travel question source must be user-authored")
        return self


class AnswerEvidence(ContractModel):
    """A browser-safe evidence excerpt used by one grounded answer."""

    evidence_id: Identifier
    title: ShortText
    statement: NonEmptyText
    source: SourceRef
    freshness: Freshness

    @model_validator(mode="after")
    def validate_provenance(self) -> AnswerEvidence:
        if self.freshness.source.source_id != self.source.source_id:
            raise ValueError("answer evidence freshness source must match its source")
        return self


class AnswerSection(ContractModel):
    heading: ShortText
    body: NonEmptyText
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=20)


class TravelAnswer(ArtifactBase):
    """A concise, grounded answer that can later be converted into a trip plan."""

    artifact_type: Literal["TravelAnswer"]
    question_ref: ArtifactRef
    question: NonEmptyText
    answer_status: Literal["answered", "needs_clarification", "insufficient_evidence"]
    summary: NonEmptyText
    sections: list[AnswerSection] = Field(default_factory=list, max_length=8)
    evidence: list[AnswerEvidence] = Field(default_factory=list, max_length=30)
    citations: list[Citation] = Field(default_factory=list, max_length=100)
    assumptions: list[ShortText] = Field(default_factory=list, max_length=20)
    limitations: list[NonEmptyText] = Field(default_factory=list, max_length=20)
    suggested_questions: list[ShortText] = Field(default_factory=list, max_length=6)
    generated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_grounding(self) -> TravelAnswer:
        if self.question_ref.artifact_type.value != "TravelQuestion":
            raise ValueError("question_ref must reference TravelQuestion")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("answer evidence identifiers must be unique")
        known = set(evidence_ids)
        citation_ids = [item.citation_id for item in self.citations]
        if len(citation_ids) != len(set(citation_ids)):
            raise ValueError("answer citation identifiers must be unique")
        if any(item.evidence_id not in known for item in self.citations):
            raise ValueError("answer citation references unknown evidence")
        if any(not set(section.evidence_refs).issubset(known) for section in self.sections):
            raise ValueError("answer section references unknown evidence")
        if self.answer_status == "answered":
            if not self.evidence or not self.sections:
                raise ValueError("an answered response requires evidence and sections")
            if any(not section.evidence_refs for section in self.sections):
                raise ValueError("every answered section requires evidence")
        return self


class Candidate(ContractModel):
    candidate_id: Identifier
    category: Literal["area", "poi", "lodging_area", "activity"]
    place_ref: PlaceRef
    rationale: NonEmptyText
    evidence_refs: list[Identifier] = Field(min_length=1, max_length=100)
    score: Annotated[Decimal, Field(ge=0, le=1)]
    estimated_cost: MoneyRange | None = None
    recommended_duration_minutes: Annotated[int, Field(gt=0, le=10_080)] | None = None
    tags: list[ShortText] = Field(default_factory=list, max_length=30)


class CandidateSet(ArtifactBase):
    artifact_type: Literal["CandidateSet"]
    trip_brief_ref: ArtifactRef
    evidence_bundle_ref: ArtifactRef
    timezone: IanaTimezone
    candidates: list[Candidate] = Field(min_length=1, max_length=500)
    selection_notes: list[NonEmptyText] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_candidates(self) -> CandidateSet:
        if self.trip_brief_ref.artifact_type.value != "TripBrief":
            raise ValueError("trip_brief_ref must reference TripBrief")
        if self.evidence_bundle_ref.artifact_type.value != "EvidenceBundle":
            raise ValueError("evidence_bundle_ref must reference EvidenceBundle")
        identifiers = [candidate.candidate_id for candidate in self.candidates]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("candidate_id values must be unique")
        if any(candidate.place_ref.timezone != self.timezone for candidate in self.candidates):
            raise ValueError("candidate place timezones must match candidate set timezone")
        return self


class PlanAssumption(ContractModel):
    assumption_id: Identifier
    text: NonEmptyText
    source: SourceRef
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=50)


class PlaceAlternative(ContractModel):
    place_ref: PlaceRef
    rationale: NonEmptyText
    evidence_refs: list[Identifier] = Field(min_length=1, max_length=50)


class PlanTimeBlock(ContractModel):
    block_id: Identifier
    title: ShortText
    category: Literal["visit", "meal", "lodging", "transit", "free_time", "check_in", "check_out"]
    place_ref: PlaceRef
    time_range: ZonedTimeRange
    duration_minutes: Annotated[int, Field(gt=0, le=1_440)]
    transit_from_previous: TransitLeg | None = None
    cost_range: MoneyRange | None = None
    evidence_refs: list[Identifier] = Field(min_length=1, max_length=100)
    alternatives: list[PlaceAlternative] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_timezone(self) -> PlanTimeBlock:
        if self.place_ref.timezone != self.time_range.timezone:
            raise ValueError("place and time range timezones must match")
        return self


class PlanDay(ContractModel):
    date: date
    timezone: IanaTimezone
    time_blocks: list[PlanTimeBlock] = Field(min_length=1, max_length=50)
    day_summary: NonEmptyText
    daily_cost: MoneyRange

    @model_validator(mode="after")
    def validate_day(self) -> PlanDay:
        block_ids = [block.block_id for block in self.time_blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block_id values must be unique within a day")
        for block in self.time_blocks:
            if block.time_range.local_date != self.date:
                raise ValueError("time block local_date must match plan day")
            if block.time_range.timezone != self.timezone:
                raise ValueError("time block timezone must match plan day")
        starts = [block.time_range.start_local_time for block in self.time_blocks]
        if starts != sorted(starts):
            raise ValueError("time blocks must be ordered by local start time")
        return self


class BudgetCategoryTotal(ContractModel):
    category: Literal["lodging", "food", "transport", "tickets", "shopping", "other"]
    cost: MoneyRange


class BudgetSummary(ContractModel):
    estimated_total: MoneyRange
    category_totals: list[BudgetCategoryTotal] = Field(default_factory=list, max_length=20)
    contingency_percent: Annotated[Decimal, Field(ge=0, le=100)]

    @model_validator(mode="after")
    def validate_currency(self) -> BudgetSummary:
        currency = self.estimated_total.currency
        if any(item.cost.currency != currency for item in self.category_totals):
            raise ValueError("all budget category totals must use the summary currency")
        return self


class RouteSummary(ContractModel):
    total_distance_meters: Annotated[int, Field(ge=0)]
    total_transit_duration_minutes: Annotated[int, Field(ge=0)]
    legs_count: Annotated[int, Field(ge=0)]
    source: SourceRef


class RiskSummary(ContractModel):
    risk_id: Identifier
    severity: Severity
    message: NonEmptyText
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    resolution: NonEmptyText | None = None


class ItineraryPlan(ArtifactBase):
    artifact_type: Literal["ItineraryPlan"]
    plan_id: Identifier
    status: Literal[
        "generated", "candidate", "selected", "validated", "published", "superseded", "rejected", "revoked"
    ]
    trip_brief_ref: ArtifactRef
    candidate_set_ref: ArtifactRef
    evidence_bundle_ref: ArtifactRef
    timezone: IanaTimezone
    assumptions: list[PlanAssumption] = Field(default_factory=list, max_length=100)
    days: list[PlanDay] = Field(min_length=1, max_length=60)
    budget_summary: BudgetSummary
    route_summary: RouteSummary
    citations: list[Citation] = Field(min_length=1, max_length=1_000)
    unresolved_risks: list[RiskSummary] = Field(default_factory=list, max_length=200)
    validation_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def validate_plan(self) -> ItineraryPlan:
        expected = (
            (self.trip_brief_ref, "TripBrief"),
            (self.candidate_set_ref, "CandidateSet"),
            (self.evidence_bundle_ref, "EvidenceBundle"),
        )
        for reference, artifact_type in expected:
            if reference.artifact_type.value != artifact_type:
                raise ValueError(f"reference must target {artifact_type}")
        if self.validation_ref is not None and self.validation_ref.artifact_type.value != "ValidationReport":
            raise ValueError("validation_ref must target ValidationReport")
        dates = [day.date for day in self.days]
        if len(dates) != len(set(dates)):
            raise ValueError("plan day dates must be unique")
        if dates != sorted(dates):
            raise ValueError("plan days must be ordered by date")
        if any(day.timezone != self.timezone for day in self.days):
            raise ValueError("plan day timezones must match plan timezone")
        currency = self.budget_summary.estimated_total.currency
        if any(day.daily_cost.currency != currency for day in self.days):
            raise ValueError("daily costs must use the plan budget currency")
        return self


class MetricObservation(ContractModel):
    metric: ShortText
    value: Annotated[str, Field(min_length=1, max_length=128)]
    unit: Annotated[str, Field(min_length=1, max_length=64)]


class ConstraintCheck(ContractModel):
    check_id: Identifier
    constraint_ref: Identifier | None = None
    category: Literal["time", "route", "budget", "opening_hours", "hard_constraint"]
    outcome: Literal["pass", "warning", "fail"]
    message: NonEmptyText
    source: SourceRef
    related_block_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    observations: list[MetricObservation] = Field(default_factory=list, max_length=30)


class CheckSummary(ContractModel):
    passed: Annotated[int, Field(ge=0)]
    warnings: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]


class ConstraintReport(ArtifactBase):
    artifact_type: Literal["ConstraintReport"]
    plan_ref: ArtifactRef
    timezone: IanaTimezone
    checked_at: AwareDatetime
    engine: VersionedComponent
    outcome: Literal["pass", "warning", "fail"]
    checks: list[ConstraintCheck] = Field(min_length=1, max_length=2_000)
    summary: CheckSummary

    @model_validator(mode="after")
    def validate_checks(self) -> ConstraintReport:
        if self.plan_ref.artifact_type.value != "ItineraryPlan":
            raise ValueError("plan_ref must reference ItineraryPlan")
        actual = {
            "passed": sum(check.outcome == "pass" for check in self.checks),
            "warnings": sum(check.outcome == "warning" for check in self.checks),
            "failed": sum(check.outcome == "fail" for check in self.checks),
        }
        if self.summary.model_dump() != actual:
            raise ValueError("constraint summary counts do not match checks")
        expected_outcome = "fail" if actual["failed"] else "warning" if actual["warnings"] else "pass"
        if self.outcome != expected_outcome:
            raise ValueError("constraint report outcome does not match checks")
        return self


class EvidenceCoverage(ContractModel):
    claims_total: Annotated[int, Field(ge=0)]
    claims_supported: Annotated[int, Field(ge=0)]
    claims_missing: Annotated[int, Field(ge=0)]
    coverage_ratio: Annotated[Decimal, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def validate_counts(self) -> EvidenceCoverage:
        if self.claims_supported + self.claims_missing != self.claims_total:
            raise ValueError("supported and missing claims must equal total")
        expected = Decimal(1) if self.claims_total == 0 else Decimal(self.claims_supported) / Decimal(self.claims_total)
        if abs(self.coverage_ratio - expected) > Decimal("0.0001"):
            raise ValueError("coverage_ratio does not match claim counts")
        return self


class SemanticRisk(ContractModel):
    risk_id: Identifier
    category: Literal["evidence_gap", "assumption", "source_conflict", "soft_constraint", "ambiguity"]
    severity: Severity
    message: NonEmptyText
    affected_block_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    evidence_refs: list[Identifier] = Field(default_factory=list, max_length=100)
    suggested_resolution: NonEmptyText | None = None


class SemanticRiskReport(ArtifactBase):
    artifact_type: Literal["SemanticRiskReport"]
    plan_ref: ArtifactRef
    evidence_bundle_ref: ArtifactRef
    timezone: IanaTimezone
    assessed_at: AwareDatetime
    reviewer: VersionedComponent
    assessment_source: SourceRef
    outcome: Literal["pass", "warning", "fail"]
    evidence_coverage: EvidenceCoverage
    risks: list[SemanticRisk] = Field(default_factory=list, max_length=1_000)
    source_conflicts: list[EvidenceConflict] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_report(self) -> SemanticRiskReport:
        if self.plan_ref.artifact_type.value != "ItineraryPlan":
            raise ValueError("plan_ref must reference ItineraryPlan")
        if self.evidence_bundle_ref.artifact_type.value != "EvidenceBundle":
            raise ValueError("evidence_bundle_ref must reference EvidenceBundle")
        severities = {risk.severity.value for risk in self.risks}
        expected = "fail" if {"critical", "high"} & severities else "warning" if self.risks else "pass"
        if self.outcome != expected:
            raise ValueError("semantic outcome does not match risk severity")
        return self


class ValidationIssue(ContractModel):
    issue_id: Identifier
    origin: Literal["constraint", "semantic", "policy"]
    severity: Severity
    message: NonEmptyText
    source_report_ref: ArtifactRef


class ValidationReport(ArtifactBase):
    artifact_type: Literal["ValidationReport"]
    plan_ref: ArtifactRef
    constraint_report_ref: ArtifactRef
    semantic_risk_report_ref: ArtifactRef
    timezone: IanaTimezone
    generated_at: AwareDatetime
    policy_version: Annotated[str, Field(min_length=1, max_length=128)]
    verdict: Literal["pass", "warning", "fail"]
    publishable: bool
    blockers: list[ValidationIssue] = Field(default_factory=list, max_length=500)
    warnings: list[ValidationIssue] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_verdict(self) -> ValidationReport:
        expected = (
            (self.plan_ref, "ItineraryPlan"),
            (self.constraint_report_ref, "ConstraintReport"),
            (self.semantic_risk_report_ref, "SemanticRiskReport"),
        )
        for reference, artifact_type in expected:
            if reference.artifact_type.value != artifact_type:
                raise ValueError(f"reference must target {artifact_type}")
        if self.blockers and self.publishable:
            raise ValueError("a report with blockers cannot be publishable")
        if self.verdict == "fail" and self.publishable:
            raise ValueError("failed validation cannot be publishable")
        if self.verdict == "pass" and (self.blockers or self.warnings):
            raise ValueError("passing validation cannot contain issues")
        return self


class TripSnapshot(ArtifactBase):
    artifact_type: Literal["TripSnapshot"]
    trip_id: Identifier
    title: ShortText
    status: Literal["draft", "planning", "ready", "archived"]
    timezone: IanaTimezone
    brief: TripBrief
    itinerary: ItineraryPlan
    validation: ValidationReport
    generated_at: AwareDatetime
    source_artifact_versions: list[ArtifactRef] = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def validate_snapshot(self) -> TripSnapshot:
        if self.brief.destination.timezone != self.timezone:
            raise ValueError("snapshot and brief timezones must match")
        if self.itinerary.timezone != self.timezone or self.validation.timezone != self.timezone:
            raise ValueError("snapshot artifact timezones must match")
        if self.itinerary.trip_brief_ref.artifact_id != self.brief.artifact_id:
            raise ValueError("itinerary must reference embedded brief")
        if self.validation.plan_ref.artifact_id != self.itinerary.artifact_id:
            raise ValueError("validation must reference embedded itinerary")
        refs = {(ref.artifact_type.value, ref.artifact_id, ref.version) for ref in self.source_artifact_versions}
        required = {
            ("TripBrief", self.brief.artifact_id, self.brief.version),
            ("ItineraryPlan", self.itinerary.artifact_id, self.itinerary.version),
            ("ValidationReport", self.validation.artifact_id, self.validation.version),
        }
        if not required.issubset(refs):
            raise ValueError("source_artifact_versions must include embedded artifact versions")
        return self


class PublicGeoPoint(ContractModel):
    """A deliberately coarse coordinate approved for a public share."""

    latitude: Annotated[Decimal, Field(ge=Decimal("-90"), le=Decimal("90"))]
    longitude: Annotated[Decimal, Field(ge=Decimal("-180"), le=Decimal("180"))]
    coordinate_system: Literal["WGS84", "GCJ-02", "BD-09"]
    accuracy_meters: Annotated[int, Field(ge=100)]


class PublicPlace(ContractModel):
    display_name: ShortText
    locality: ShortText
    country_code: CountryCode
    approximate_location: PublicGeoPoint | None = None


class ShareTransitSummary(ContractModel):
    mode: Literal["walk", "bike", "transit", "taxi", "drive", "rail", "flight", "ferry"]
    duration_minutes: Annotated[int, Field(ge=0, le=10_080)]


class ShareTimeBlock(ContractModel):
    block_id: Identifier
    title: ShortText
    category: Literal["visit", "meal", "lodging", "transit", "free_time", "check_in", "check_out"]
    time_range: ZonedTimeRange
    place: PublicPlace
    transit_from_previous: ShareTransitSummary | None = None
    citation_refs: list[Identifier] = Field(default_factory=list, max_length=100)


class ShareDay(ContractModel):
    date: date
    timezone: IanaTimezone
    summary: NonEmptyText
    time_blocks: list[ShareTimeBlock] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_blocks(self) -> ShareDay:
        for block in self.time_blocks:
            if block.time_range.local_date != self.date or block.time_range.timezone != self.timezone:
                raise ValueError("shared time block must match shared day date and timezone")
        return self


class ShareSnapshot(ArtifactBase):
    """Explicit public projection; intentionally excludes users, conversation and exact budget."""

    artifact_type: Literal["ShareSnapshot"]
    public_id: Identifier
    trip_snapshot_ref: ArtifactRef
    title: ShortText
    destination: PublicPlace
    date_window: TripDateRange
    days: list[ShareDay] = Field(min_length=1, max_length=60)
    citations: list[Citation] = Field(default_factory=list, max_length=1_000)
    published_at: AwareDatetime

    @model_validator(mode="after")
    def validate_projection(self) -> ShareSnapshot:
        if self.trip_snapshot_ref.artifact_type.value != "TripSnapshot":
            raise ValueError("trip_snapshot_ref must reference TripSnapshot")
        if any(day.timezone != self.date_window.timezone for day in self.days):
            raise ValueError("shared day timezones must match date window")
        dates = [day.date for day in self.days]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise ValueError("shared days must be unique and ordered")
        return self


ARTIFACT_MODELS = (
    TravelQuestion,
    TravelAnswer,
    TripBrief,
    EvidenceBundle,
    CandidateSet,
    ItineraryPlan,
    ConstraintReport,
    SemanticRiskReport,
    ValidationReport,
    TripSnapshot,
    ShareSnapshot,
)
