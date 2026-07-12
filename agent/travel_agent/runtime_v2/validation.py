"""Deterministic constraint checks, semantic review, and publication policy."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from routepilot_contracts.artifacts import (
    CheckSummary,
    ConstraintCheck,
    ConstraintReport,
    EvidenceBundle,
    EvidenceCoverage,
    ItineraryPlan,
    MetricObservation,
    SemanticRisk,
    SemanticRiskReport,
    TripBrief,
    ValidationIssue,
    ValidationReport,
)
from routepilot_contracts.common import ArtifactType, FreshnessStatus, Severity, VersionedComponent

from .shared import artifact_ref, new_id, system_actor, system_source, utc_now


def _check(
    category: str,
    outcome: str,
    message: str,
    *,
    block_ids: list[str] | None = None,
    observations: list[MetricObservation] | None = None,
    constraint_ref: str | None = None,
) -> ConstraintCheck:
    return ConstraintCheck(
        check_id=new_id("check"),
        constraint_ref=constraint_ref,
        category=category,
        outcome=outcome,
        message=message,
        source=system_source("constraint-validator", "1"),
        related_block_ids=block_ids or [],
        observations=observations or [],
    )


def _local_interval(local_date, time_range) -> tuple[datetime, datetime]:
    start = datetime.combine(local_date, time_range.start_local_time)
    end = datetime.combine(local_date, time_range.end_local_time) + timedelta(
        days=time_range.end_day_offset
    )
    return start, end


class DeterministicConstraintValidator:
    """Validate exact time, route, budget, reference, and hard constraints."""

    version = "constraint-validator-1"

    def validate(
        self,
        brief: TripBrief,
        plan: ItineraryPlan,
        evidence: EvidenceBundle,
    ) -> ConstraintReport:
        checks: list[ConstraintCheck] = []
        evidence_ids = {item.evidence_id for item in evidence.evidence}

        dates = [day.date for day in plan.days]
        dates_valid = bool(dates) and min(dates) >= brief.date_window.start_date and max(
            dates
        ) <= brief.date_window.end_date
        checks.append(
            _check(
                "hard_constraint",
                "pass" if dates_valid else "fail",
                "行程日期位于用户日期窗口内。" if dates_valid else "行程日期超出用户日期窗口。",
            )
        )

        planned_places = [
            block.place_ref.place_id
            for day in plan.days
            for block in day.time_blocks
        ]
        has_concrete_place = any(
            place_id != brief.destination.place_id for place_id in planned_places
        )
        checks.append(
            _check(
                "hard_constraint",
                "pass" if has_concrete_place else "fail",
                "方案包含经过证据支持的具体地点。"
                if has_concrete_place
                else "方案只有目的地城市占位符，没有具体地点，属于低价值结果，禁止发布。",
                block_ids=[
                    block.block_id
                    for day in plan.days
                    for block in day.time_blocks
                ],
            )
        )

        for day in plan.days:
            place_ids = [block.place_ref.place_id for block in day.time_blocks]
            unique_places = len(place_ids) == len(set(place_ids))
            checks.append(
                _check(
                    "hard_constraint",
                    "pass" if unique_places else "fail",
                    "单日行程没有重复地点。"
                    if unique_places
                    else "单日行程包含重复地点，属于无信息量方案，禁止发布。",
                    block_ids=[block.block_id for block in day.time_blocks],
                )
            )
            previous_end: datetime | None = None
            for block in day.time_blocks:
                start, end = _local_interval(day.date, block.time_range)
                actual_duration = int((end - start).total_seconds() // 60)
                duration_ok = actual_duration == block.duration_minutes
                checks.append(
                    _check(
                        "time",
                        "pass" if duration_ok else "fail",
                        "停留时长与时间区间一致。" if duration_ok else "停留时长与时间区间不一致。",
                        block_ids=[block.block_id],
                        observations=[
                            MetricObservation(
                                metric="duration",
                                value=str(actual_duration),
                                unit="minutes",
                            )
                        ],
                    )
                )
                if previous_end is not None:
                    gap = int((start - previous_end).total_seconds() // 60)
                    required = (
                        block.transit_from_previous.duration_max_minutes
                        if block.transit_from_previous
                        else 0
                    )
                    feasible = gap >= required
                    checks.append(
                        _check(
                            "route",
                            "pass" if feasible else "fail",
                            "地点间预留时间可覆盖路线耗时。"
                            if feasible
                            else "地点间预留时间不足以覆盖路线耗时。",
                            block_ids=[block.block_id],
                            observations=[
                                MetricObservation(metric="available", value=str(gap), unit="minutes"),
                                MetricObservation(metric="required", value=str(required), unit="minutes"),
                            ],
                        )
                    )
                previous_end = end

                references_valid = set(block.evidence_refs).issubset(evidence_ids)
                checks.append(
                    _check(
                        "hard_constraint",
                        "pass" if references_valid else "fail",
                        "时间块证据引用均可解析。"
                        if references_valid
                        else "时间块包含无法解析的证据引用。",
                        block_ids=[block.block_id],
                    )
                )

        plan_max = Decimal(plan.budget_summary.estimated_total.max_amount)
        budget_max = Decimal(brief.budget.max_amount)
        same_currency = plan.budget_summary.estimated_total.currency == brief.budget.currency
        budget_ok = same_currency and plan_max <= budget_max
        checks.append(
            _check(
                "budget",
                "pass" if budget_ok else "fail",
                "候选行程预算未超过用户上限。" if budget_ok else "候选行程预算超过用户上限或币种不一致。",
                observations=[
                    MetricObservation(metric="plan_max", value=str(plan_max), unit=brief.budget.currency),
                    MetricObservation(metric="budget_max", value=str(budget_max), unit=brief.budget.currency),
                ],
            )
        )

        titles = " ".join(
            block.title.casefold() for day in plan.days for block in day.time_blocks
        )
        for constraint in brief.constraints:
            if not constraint.hard or constraint.constraint_type not in {"visit", "avoid"}:
                continue
            mentioned = constraint.description.casefold() in titles
            satisfied = mentioned if constraint.constraint_type == "visit" else not mentioned
            checks.append(
                _check(
                    "hard_constraint",
                    "pass" if satisfied else "fail",
                    "可机器核验的必去/避开约束已满足。"
                    if satisfied
                    else "可机器核验的必去/避开约束未满足。",
                    constraint_ref=constraint.constraint_id,
                )
            )

        freshness_by_id = {item.evidence_id: item.freshness.status for item in evidence.evidence}
        for day in plan.days:
            for block in day.time_blocks:
                statuses = {freshness_by_id[item] for item in block.evidence_refs if item in freshness_by_id}
                current = statuses and not statuses.intersection(
                    {FreshnessStatus.STALE, FreshnessStatus.EXPIRED, FreshnessStatus.UNKNOWN}
                )
                checks.append(
                    _check(
                        "opening_hours",
                        "pass" if current else "warning",
                        "地点证据当前有效。" if current else "地点证据可能过期，营业状态需实时 Provider 复核。",
                        block_ids=[block.block_id],
                    )
                )

        passed = sum(item.outcome == "pass" for item in checks)
        warnings = sum(item.outcome == "warning" for item in checks)
        failed = sum(item.outcome == "fail" for item in checks)
        outcome = "fail" if failed else "warning" if warnings else "pass"
        return ConstraintReport(
            artifact_id=new_id("artifact"),
            artifact_type="ConstraintReport",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=system_actor("constraint-validator"),
            reason="对候选方案执行确定性的时间、路线、预算与硬约束校验。",
            plan_ref=artifact_ref(plan, ArtifactType.ITINERARY_PLAN),
            timezone=plan.timezone,
            checked_at=utc_now(),
            engine=VersionedComponent(name="RoutePilot Constraint Validator", version=self.version),
            outcome=outcome,
            checks=checks,
            summary=CheckSummary(passed=passed, warnings=warnings, failed=failed),
        )


class DeterministicSemanticVerifier:
    """Reference semantic verifier for evidence coverage, conflicts, and freshness."""

    version = "semantic-verifier-1"

    def verify(self, plan: ItineraryPlan, evidence: EvidenceBundle) -> SemanticRiskReport:
        known = {item.evidence_id for item in evidence.evidence}
        used = [
            set(block.evidence_refs)
            for day in plan.days
            for block in day.time_blocks
        ] + [set(item.evidence_refs) for item in plan.assumptions]
        supported = sum(bool(refs) and refs.issubset(known) for refs in used)
        total = len(used)
        missing = total - supported
        ratio = Decimal(1) if total == 0 else Decimal(supported) / Decimal(total)
        risks: list[SemanticRisk] = []

        for day in plan.days:
            for block in day.time_blocks:
                unknown = set(block.evidence_refs) - known
                if unknown:
                    risks.append(
                        SemanticRisk(
                            risk_id=new_id("risk"),
                            category="evidence_gap",
                            severity=Severity.HIGH,
                            message="计划时间块包含未知证据引用。",
                            affected_block_ids=[block.block_id],
                            evidence_refs=sorted(unknown),
                            suggested_resolution="重新检索并只引用 EvidenceBundle 中的证据。",
                        )
                    )

        evidence_by_id = {item.evidence_id: item for item in evidence.evidence}
        used_refs = set().union(*used) if used else set()
        for evidence_id in sorted(used_refs & known):
            item = evidence_by_id[evidence_id]
            if item.freshness.status in {
                FreshnessStatus.STALE,
                FreshnessStatus.EXPIRED,
                FreshnessStatus.UNKNOWN,
            }:
                risks.append(
                    SemanticRisk(
                        risk_id=new_id("risk"),
                        category="evidence_gap",
                        severity=Severity.MEDIUM,
                        message=f"证据“{item.title}”不是 fresh 状态。",
                        evidence_refs=[evidence_id],
                        suggested_resolution="在发布前通过实时 Provider 刷新该事实。",
                    )
                )

        for assumption in plan.assumptions:
            if not assumption.evidence_refs:
                risks.append(
                    SemanticRisk(
                        risk_id=new_id("risk"),
                        category="assumption",
                        severity=Severity.MEDIUM,
                        message="计划包含未被证据支持的假设。",
                        evidence_refs=[],
                        suggested_resolution="补充证据或在用户界面明确展示该假设。",
                    )
                )

        unresolved = [
            item for item in evidence.conflicts if item.resolution_status == "unresolved"
        ]
        for conflict in unresolved:
            risks.append(
                SemanticRisk(
                    risk_id=new_id("risk"),
                    category="source_conflict",
                    severity=Severity.HIGH,
                    message=f"来源冲突尚未解决：{conflict.topic}",
                    evidence_refs=conflict.evidence_refs,
                    suggested_resolution="选择权威或更新更近的来源后重新验证。",
                )
            )

        severity_values = {risk.severity for risk in risks}
        outcome = (
            "fail"
            if severity_values.intersection({Severity.HIGH, Severity.CRITICAL})
            else "warning"
            if risks
            else "pass"
        )
        return SemanticRiskReport(
            artifact_id=new_id("artifact"),
            artifact_type="SemanticRiskReport",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=system_actor("semantic-verifier"),
            reason="独立审查证据覆盖、假设、来源冲突和软风险。",
            plan_ref=artifact_ref(plan, ArtifactType.ITINERARY_PLAN),
            evidence_bundle_ref=artifact_ref(evidence, ArtifactType.EVIDENCE_BUNDLE),
            timezone=plan.timezone,
            assessed_at=utc_now(),
            reviewer=VersionedComponent(name="RoutePilot Semantic Verifier", version=self.version),
            assessment_source=system_source("semantic-verifier", self.version),
            outcome=outcome,
            evidence_coverage=EvidenceCoverage(
                claims_total=total,
                claims_supported=supported,
                claims_missing=missing,
                coverage_ratio=ratio,
            ),
            risks=risks,
            source_conflicts=unresolved,
        )


class ValidationPolicyService:
    """Combine independent reports into one versioned publication decision."""

    version = "publication-policy-1"

    def combine(
        self,
        plan: ItineraryPlan,
        constraints: ConstraintReport,
        semantic: SemanticRiskReport,
    ) -> ValidationReport:
        if constraints.plan_ref.artifact_id != plan.artifact_id:
            raise ValueError("constraint report belongs to another plan")
        if semantic.plan_ref.artifact_id != plan.artifact_id:
            raise ValueError("semantic report belongs to another plan")
        blockers: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        constraint_ref = artifact_ref(constraints, ArtifactType.CONSTRAINT_REPORT)
        semantic_ref = artifact_ref(semantic, ArtifactType.SEMANTIC_RISK_REPORT)
        for item in constraints.checks:
            if item.outcome == "pass":
                continue
            issue = ValidationIssue(
                issue_id=new_id("issue"),
                origin="constraint",
                severity=Severity.HIGH if item.outcome == "fail" else Severity.MEDIUM,
                message=item.message,
                source_report_ref=constraint_ref,
            )
            (blockers if item.outcome == "fail" else warnings).append(issue)

        for risk in semantic.risks:
            issue = ValidationIssue(
                issue_id=new_id("issue"),
                origin="semantic",
                severity=risk.severity,
                message=risk.message,
                source_report_ref=semantic_ref,
            )
            if risk.severity in {Severity.HIGH, Severity.CRITICAL}:
                blockers.append(issue)
            else:
                warnings.append(issue)

        if semantic.evidence_coverage.coverage_ratio < Decimal("0.9"):
            blockers.append(
                ValidationIssue(
                    issue_id=new_id("issue"),
                    origin="policy",
                    severity=Severity.HIGH,
                    message="证据覆盖率低于 90% 发布门槛。",
                    source_report_ref=semantic_ref,
                )
            )

        verdict = "fail" if blockers else "warning" if warnings else "pass"
        return ValidationReport(
            artifact_id=new_id("artifact"),
            artifact_type="ValidationReport",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=system_actor("validation-policy"),
            reason="合并确定性约束与独立语义审查，形成发布门禁。",
            plan_ref=artifact_ref(plan, ArtifactType.ITINERARY_PLAN),
            constraint_report_ref=constraint_ref,
            semantic_risk_report_ref=semantic_ref,
            timezone=plan.timezone,
            generated_at=utc_now(),
            policy_version=self.version,
            verdict=verdict,
            publishable=not blockers,
            blockers=blockers,
            warnings=warnings,
        )
