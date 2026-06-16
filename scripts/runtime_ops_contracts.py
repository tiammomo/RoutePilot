"""Shared contracts for runtime diagnostics, support bundles, and ops snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _coerce_text(value: Any, default: str = "") -> str:
    """Return one normalized text value."""

    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _copy_dict(value: Any) -> dict[str, Any]:
    """Return one shallow builtin dict copy."""

    return dict(value) if isinstance(value, dict) else {}


def _copy_str_list(value: Any) -> list[str]:
    """Return one normalized list of strings."""

    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _copy_list(value: Any) -> list[Any]:
    """Return one shallow builtin list copy."""

    return list(value) if isinstance(value, list) else []


@dataclass(slots=True)
class RuntimeDoctorCheck:
    """Describe one normalized runtime-doctor check."""

    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDoctorCheck":
        """Build one check contract from a loose dictionary payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            name=_coerce_text(item.get("name")),
            status=_coerce_text(item.get("status")),
            message=_coerce_text(item.get("message")),
            details=_copy_dict(item.get("details")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable check payload."""

        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": _copy_dict(self.details),
        }


@dataclass(slots=True)
class RuntimeDoctorSummary:
    """Describe aggregate runtime-doctor status counters."""

    checks_total: int = 0
    checks_ok: int = 0
    checks_degraded: int = 0
    checks_not_ready: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDoctorSummary":
        """Build one summary contract from a loose dictionary payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            checks_total=int(item.get("checks_total", 0) or 0),
            checks_ok=int(item.get("checks_ok", 0) or 0),
            checks_degraded=int(item.get("checks_degraded", 0) or 0),
            checks_not_ready=int(item.get("checks_not_ready", 0) or 0),
        )

    def to_dict(self) -> dict[str, int]:
        """Return one JSON-serializable summary payload."""

        return {
            "checks_total": self.checks_total,
            "checks_ok": self.checks_ok,
            "checks_degraded": self.checks_degraded,
            "checks_not_ready": self.checks_not_ready,
        }


@dataclass(slots=True)
class CheckpointRuntimeView:
    """Describe one normalized checkpoint-runtime view."""

    backend: str = ""
    target: str = ""
    restore_strategy: str = ""
    archive_contains_checkpoint_data: bool = False
    archived_files: list[str] = field(default_factory=list)
    requires_external_snapshot: bool = False
    restore_instructions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CheckpointRuntimeView":
        """Build one checkpoint-runtime view from a loose dictionary payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            backend=_coerce_text(item.get("backend")),
            target=_coerce_text(item.get("target")),
            restore_strategy=_coerce_text(item.get("restore_strategy")),
            archive_contains_checkpoint_data=bool(item.get("archive_contains_checkpoint_data")),
            archived_files=_copy_str_list(item.get("archived_files")),
            requires_external_snapshot=bool(item.get("requires_external_snapshot")),
            restore_instructions=_copy_str_list(item.get("restore_instructions")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable checkpoint-runtime payload."""

        return {
            "backend": self.backend,
            "target": self.target,
            "restore_strategy": self.restore_strategy,
            "archive_contains_checkpoint_data": self.archive_contains_checkpoint_data,
            "archived_files": list(self.archived_files),
            "requires_external_snapshot": self.requires_external_snapshot,
            "restore_instructions": list(self.restore_instructions),
        }


@dataclass(slots=True)
class RuntimeDoctorReport:
    """Describe the full runtime-doctor report contract."""

    status: str
    checked_at: str
    project_root: str
    summary: RuntimeDoctorSummary
    checks: dict[str, RuntimeDoctorCheck] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeDoctorReport":
        """Build one report contract from a loose runtime-doctor payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        raw_checks = item.get("checks")
        checks = (
            {
                str(name): RuntimeDoctorCheck.from_dict(check_payload)
                for name, check_payload in dict(raw_checks).items()
            }
            if isinstance(raw_checks, dict)
            else {}
        )
        return cls(
            status=_coerce_text(item.get("status")),
            checked_at=_coerce_text(item.get("checked_at")),
            project_root=_coerce_text(item.get("project_root")),
            summary=RuntimeDoctorSummary.from_dict(_copy_dict(item.get("summary"))),
            checks=checks,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable runtime-doctor report payload."""

        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "project_root": self.project_root,
            "summary": self.summary.to_dict(),
            "checks": {
                name: check.to_dict() for name, check in self.checks.items()
            },
        }


@dataclass(slots=True)
class ReleaseManifestSource:
    """Describe source-control metadata embedded in the release manifest."""

    git_sha: str
    git_ref: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseManifestSource":
        """Build one source metadata contract from a loose dictionary payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            git_sha=_coerce_text(item.get("git_sha")),
            git_ref=_coerce_text(item.get("git_ref")),
        )

    def to_dict(self) -> dict[str, str]:
        """Return one JSON-serializable source metadata payload."""

        return {
            "git_sha": self.git_sha,
            "git_ref": self.git_ref,
        }


@dataclass(slots=True)
class ReleaseApplicationEntry:
    """Describe one deployable application entry inside the release manifest."""

    name: str
    version: str
    image: str
    image_tag: str = ""
    image_ref: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseApplicationEntry":
        """Build one application entry from a loose manifest payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            name=_coerce_text(item.get("name")),
            version=_coerce_text(item.get("version")),
            image=_coerce_text(item.get("image")),
            image_tag=_coerce_text(item.get("image_tag")),
            image_ref=_coerce_text(item.get("image_ref")),
        )

    def to_dict(self) -> dict[str, str]:
        """Return one JSON-serializable application manifest entry."""

        payload = {
            "name": self.name,
            "version": self.version,
            "image": self.image,
        }
        if self.image_tag:
            payload["image_tag"] = self.image_tag
        if self.image_ref:
            payload["image_ref"] = self.image_ref
        return payload


@dataclass(slots=True)
class ReleaseQualityArtifacts:
    """Describe quality evidence references embedded in the release manifest."""

    benchmark_report: str = ""
    golden_eval_report: str = ""
    subagent_scorecard_report: str = ""
    release_harness_scorecard_report: str = ""
    delivery_snapshot: str = ""
    skills_catalog: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseQualityArtifacts":
        """Build one artifact-reference contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            benchmark_report=_coerce_text(item.get("benchmark_report")),
            golden_eval_report=_coerce_text(item.get("golden_eval_report")),
            subagent_scorecard_report=_coerce_text(item.get("subagent_scorecard_report")),
            release_harness_scorecard_report=_coerce_text(item.get("release_harness_scorecard_report")),
            delivery_snapshot=_coerce_text(item.get("delivery_snapshot")),
            skills_catalog=_coerce_text(item.get("skills_catalog")),
        )

    def to_dict(self) -> dict[str, str]:
        """Return one JSON-serializable artifact-reference payload."""

        return {
            "benchmark_report": self.benchmark_report,
            "golden_eval_report": self.golden_eval_report,
            "subagent_scorecard_report": self.subagent_scorecard_report,
            "release_harness_scorecard_report": self.release_harness_scorecard_report,
            "delivery_snapshot": self.delivery_snapshot,
            "skills_catalog": self.skills_catalog,
        }

    def count(self) -> int:
        """Return the number of populated quality artifact references."""

        return sum(1 for value in self.to_dict().values() if str(value).strip())


@dataclass(slots=True)
class ReleaseManifestQuality:
    """Describe release-quality evidence embedded in the release manifest."""

    release_check_command: str
    artifacts: ReleaseQualityArtifacts

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseManifestQuality":
        """Build one release-quality contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            release_check_command=_coerce_text(item.get("release_check_command")),
            artifacts=ReleaseQualityArtifacts.from_dict(_copy_dict(item.get("artifacts"))),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable release-quality payload."""

        return {
            "release_check_command": self.release_check_command,
            "artifacts": self.artifacts.to_dict(),
        }


@dataclass(slots=True)
class ReleaseManifest:
    """Describe the release-manifest contract used by release evidence tooling."""

    created_at: str
    source: ReleaseManifestSource
    applications: dict[str, ReleaseApplicationEntry] = field(default_factory=dict)
    quality: ReleaseManifestQuality = field(
        default_factory=lambda: ReleaseManifestQuality(
            release_check_command="",
            artifacts=ReleaseQualityArtifacts(),
        )
    )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseManifest":
        """Build one release-manifest contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        raw_applications = item.get("applications")
        applications = (
            {
                str(name): ReleaseApplicationEntry.from_dict(application_payload)
                for name, application_payload in dict(raw_applications).items()
            }
            if isinstance(raw_applications, dict)
            else {}
        )
        return cls(
            created_at=_coerce_text(item.get("created_at")),
            source=ReleaseManifestSource.from_dict(_copy_dict(item.get("source"))),
            applications=applications,
            quality=ReleaseManifestQuality.from_dict(_copy_dict(item.get("quality"))),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable release-manifest payload."""

        return {
            "created_at": self.created_at,
            "source": self.source.to_dict(),
            "applications": {
                name: entry.to_dict() for name, entry in self.applications.items()
            },
            "quality": self.quality.to_dict(),
        }


@dataclass(slots=True)
class ReleaseHarnessFinding:
    """Describe one release-harness finding."""

    severity: str
    category: str
    message: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessFinding":
        """Build one finding contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            severity=_coerce_text(item.get("severity")),
            category=_coerce_text(item.get("category")),
            message=_coerce_text(item.get("message")),
        )

    def to_dict(self) -> dict[str, str]:
        """Return one JSON-serializable finding payload."""

        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
        }


@dataclass(slots=True)
class ReleaseHarnessSummary:
    """Describe aggregate release-harness finding counters."""

    error_count: int = 0
    warning_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessSummary":
        """Build one summary contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            error_count=int(item.get("error_count", 0) or 0),
            warning_count=int(item.get("warning_count", 0) or 0),
        )

    def to_dict(self) -> dict[str, int]:
        """Return one JSON-serializable summary payload."""

        return {
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


@dataclass(slots=True)
class ReleaseHarnessBenchmarkSection:
    """Describe benchmark evidence embedded in the release scorecard."""

    golden_report: str = ""
    benchmark_report: str = ""
    golden_pass_rate: float = 0.0
    golden_hallucination_rate: float = 0.0
    benchmark_success_rate: float = 0.0
    benchmark_hallucination_rate: float = 0.0
    fallback_steps_total: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessBenchmarkSection":
        """Build one benchmark section from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            golden_report=_coerce_text(item.get("golden_report")),
            benchmark_report=_coerce_text(item.get("benchmark_report")),
            golden_pass_rate=float(item.get("golden_pass_rate", 0.0) or 0.0),
            golden_hallucination_rate=float(item.get("golden_hallucination_rate", 0.0) or 0.0),
            benchmark_success_rate=float(item.get("benchmark_success_rate", 0.0) or 0.0),
            benchmark_hallucination_rate=float(item.get("benchmark_hallucination_rate", 0.0) or 0.0),
            fallback_steps_total=int(item.get("fallback_steps_total", 0) or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable benchmark section."""

        return {
            "golden_report": self.golden_report,
            "benchmark_report": self.benchmark_report,
            "golden_pass_rate": self.golden_pass_rate,
            "golden_hallucination_rate": self.golden_hallucination_rate,
            "benchmark_success_rate": self.benchmark_success_rate,
            "benchmark_hallucination_rate": self.benchmark_hallucination_rate,
            "fallback_steps_total": self.fallback_steps_total,
        }


@dataclass(slots=True)
class ReleaseHarnessSubagentsSection:
    """Describe subagent evidence embedded in the release scorecard."""

    scorecard_report: str = ""
    expected_subagents: list[str] = field(default_factory=list)
    observed_subagents: list[str] = field(default_factory=list)
    healthy_subagents: int = 0
    partial_subagents: int = 0
    missing_subagents: int = 0
    mismatch_subagents: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessSubagentsSection":
        """Build one subagent section from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            scorecard_report=_coerce_text(item.get("scorecard_report")),
            expected_subagents=_copy_str_list(item.get("expected_subagents")),
            observed_subagents=_copy_str_list(item.get("observed_subagents")),
            healthy_subagents=int(item.get("healthy_subagents", 0) or 0),
            partial_subagents=int(item.get("partial_subagents", 0) or 0),
            missing_subagents=int(item.get("missing_subagents", 0) or 0),
            mismatch_subagents=int(item.get("mismatch_subagents", 0) or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable subagent section."""

        return {
            "scorecard_report": self.scorecard_report,
            "expected_subagents": list(self.expected_subagents),
            "observed_subagents": list(self.observed_subagents),
            "healthy_subagents": self.healthy_subagents,
            "partial_subagents": self.partial_subagents,
            "missing_subagents": self.missing_subagents,
            "mismatch_subagents": self.mismatch_subagents,
        }


@dataclass(slots=True)
class ReleaseHarnessDeliverySection:
    """Describe delivery evidence embedded in the release scorecard."""

    snapshot_path: str = ""
    modes_covered: list[str] = field(default_factory=list)
    expected_modes: list[str] = field(default_factory=list)
    branding_present: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessDeliverySection":
        """Build one delivery section from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            snapshot_path=_coerce_text(item.get("snapshot_path")),
            modes_covered=_copy_str_list(item.get("modes_covered")),
            expected_modes=_copy_str_list(item.get("expected_modes")),
            branding_present=bool(item.get("branding_present")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable delivery section."""

        return {
            "snapshot_path": self.snapshot_path,
            "modes_covered": list(self.modes_covered),
            "expected_modes": list(self.expected_modes),
            "branding_present": self.branding_present,
        }


@dataclass(slots=True)
class ReleaseHarnessSkillsSection:
    """Describe governed skills evidence embedded in the release scorecard."""

    skills_catalog: str = ""
    total_skills: int = 0
    docs_covered: int = 0
    eval_covered: int = 0
    selection_policy_covered: int = 0
    allowed_subagents_covered: int = 0
    skill_names: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessSkillsSection":
        """Build one skills section from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        return cls(
            skills_catalog=_coerce_text(item.get("skills_catalog")),
            total_skills=int(item.get("total_skills", 0) or 0),
            docs_covered=int(item.get("docs_covered", 0) or 0),
            eval_covered=int(item.get("eval_covered", 0) or 0),
            selection_policy_covered=int(item.get("selection_policy_covered", 0) or 0),
            allowed_subagents_covered=int(item.get("allowed_subagents_covered", 0) or 0),
            skill_names=_copy_str_list(item.get("skill_names")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable skills section."""

        return {
            "skills_catalog": self.skills_catalog,
            "total_skills": self.total_skills,
            "docs_covered": self.docs_covered,
            "eval_covered": self.eval_covered,
            "selection_policy_covered": self.selection_policy_covered,
            "allowed_subagents_covered": self.allowed_subagents_covered,
            "skill_names": list(self.skill_names),
        }


@dataclass(slots=True)
class ReleaseHarnessScorecard:
    """Describe the release-harness scorecard contract."""

    generated_at: str
    status: str
    summary: ReleaseHarnessSummary
    benchmark: ReleaseHarnessBenchmarkSection
    subagents: ReleaseHarnessSubagentsSection
    delivery: ReleaseHarnessDeliverySection
    skills: ReleaseHarnessSkillsSection
    findings: list[ReleaseHarnessFinding] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseHarnessScorecard":
        """Build one scorecard contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        raw_findings = item.get("findings")
        findings = [
            ReleaseHarnessFinding.from_dict(finding)
            for finding in _copy_list(raw_findings)
            if isinstance(finding, dict)
        ]
        return cls(
            generated_at=_coerce_text(item.get("generated_at")),
            status=_coerce_text(item.get("status")),
            summary=ReleaseHarnessSummary.from_dict(_copy_dict(item.get("summary"))),
            benchmark=ReleaseHarnessBenchmarkSection.from_dict(_copy_dict(item.get("benchmark"))),
            subagents=ReleaseHarnessSubagentsSection.from_dict(_copy_dict(item.get("subagents"))),
            delivery=ReleaseHarnessDeliverySection.from_dict(_copy_dict(item.get("delivery"))),
            skills=ReleaseHarnessSkillsSection.from_dict(_copy_dict(item.get("skills"))),
            findings=findings,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable scorecard payload."""

        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "summary": self.summary.to_dict(),
            "benchmark": self.benchmark.to_dict(),
            "subagents": self.subagents.to_dict(),
            "delivery": self.delivery.to_dict(),
            "skills": self.skills.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(slots=True)
class SupportBundleRuntimeHealthSection:
    """Describe runtime-health evidence embedded in the support-bundle manifest."""

    doctor_status: str
    runtime_files_count: int
    checks_total: int
    checks_degraded: int
    checks_not_ready: int
    checkpoint_backend: str = ""
    checkpoint_restore_strategy: str = ""
    checkpoint_requires_external_snapshot: bool = False

    @classmethod
    def from_doctor_report(cls, report: RuntimeDoctorReport) -> "SupportBundleRuntimeHealthSection":
        """Build runtime-health evidence from one runtime-doctor report."""

        runtime_files = report.checks.get("runtime_files")
        details = runtime_files.details if runtime_files else {}
        files = details.get("files")
        runtime_files_count = len(files) if isinstance(files, list) else 0
        checkpoint_runtime = report.checks.get("checkpoint_runtime")
        checkpoint_view = CheckpointRuntimeView.from_dict(
            checkpoint_runtime.details if checkpoint_runtime is not None else {}
        )
        return cls(
            doctor_status=report.status,
            runtime_files_count=runtime_files_count,
            checks_total=report.summary.checks_total,
            checks_degraded=report.summary.checks_degraded,
            checks_not_ready=report.summary.checks_not_ready,
            checkpoint_backend=checkpoint_view.backend,
            checkpoint_restore_strategy=checkpoint_view.restore_strategy,
            checkpoint_requires_external_snapshot=checkpoint_view.requires_external_snapshot,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable runtime-health manifest section."""

        payload = {
            "doctor_status": self.doctor_status,
            "runtime_files_count": self.runtime_files_count,
            "checks_total": self.checks_total,
            "checks_degraded": self.checks_degraded,
            "checks_not_ready": self.checks_not_ready,
        }
        if self.checkpoint_backend:
            payload["checkpoint_backend"] = self.checkpoint_backend
            payload["checkpoint_restore_strategy"] = self.checkpoint_restore_strategy
            payload["checkpoint_requires_external_snapshot"] = self.checkpoint_requires_external_snapshot
        return payload


@dataclass(slots=True)
class SupportBundleReleaseEvidenceSection:
    """Describe release-evidence entries embedded in the support-bundle manifest."""

    release_manifest_exists: bool
    release_manifest_path: str | None = None
    release_manifest_git_sha: str | None = None
    release_manifest_git_ref: str | None = None
    release_scorecard_exists: bool = False
    release_scorecard_path: str | None = None
    release_scorecard_status: str | None = None
    quality_artifact_count: int = 0

    @classmethod
    def from_release_artifacts(
        cls,
        *,
        manifest: ReleaseManifest | None,
        manifest_path: str | None,
        scorecard: ReleaseHarnessScorecard | None,
        scorecard_path: str | None,
    ) -> "SupportBundleReleaseEvidenceSection":
        """Build release-evidence metadata from typed release manifest and scorecard contracts."""

        return cls(
            release_manifest_exists=manifest is not None,
            release_manifest_path=manifest_path if manifest is not None else None,
            release_manifest_git_sha=manifest.source.git_sha if manifest is not None else None,
            release_manifest_git_ref=manifest.source.git_ref if manifest is not None else None,
            release_scorecard_exists=scorecard is not None,
            release_scorecard_path=scorecard_path if scorecard is not None else None,
            release_scorecard_status=scorecard.status if scorecard is not None else None,
            quality_artifact_count=manifest.quality.artifacts.count() if manifest is not None else 0,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable release-evidence manifest section."""

        return {
            "release_manifest_exists": self.release_manifest_exists,
            "release_manifest_path": self.release_manifest_path,
            "release_manifest_git_sha": self.release_manifest_git_sha,
            "release_manifest_git_ref": self.release_manifest_git_ref,
            "release_scorecard_exists": self.release_scorecard_exists,
            "release_scorecard_path": self.release_scorecard_path,
            "release_scorecard_status": self.release_scorecard_status,
            "quality_artifact_count": self.quality_artifact_count,
        }


@dataclass(slots=True)
class SupportBundleDeliveryEvidenceSection:
    """Describe delivery-evidence entries embedded in the support-bundle manifest."""

    contract_snapshots: list[str] = field(default_factory=list)
    includes_http_snapshot: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable delivery-evidence manifest section."""

        return {
            "contract_snapshots": list(self.contract_snapshots),
            "includes_http_snapshot": self.includes_http_snapshot,
        }


@dataclass(slots=True)
class SupportBundleManifest:
    """Describe the support-bundle manifest contract."""

    created_at: str
    project_root: str
    base_url: str | None
    runtime_health: SupportBundleRuntimeHealthSection
    release_evidence: SupportBundleReleaseEvidenceSection
    delivery_evidence: SupportBundleDeliveryEvidenceSection

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SupportBundleManifest":
        """Build one support-bundle manifest contract from a loose payload."""

        item = dict(payload) if isinstance(payload, dict) else {}
        runtime_health = _copy_dict(item.get("runtime_health"))
        release_evidence = _copy_dict(item.get("release_evidence"))
        delivery_evidence = _copy_dict(item.get("delivery_evidence"))
        return cls(
            created_at=_coerce_text(item.get("created_at")),
            project_root=_coerce_text(item.get("project_root")),
            base_url=_coerce_text(item.get("base_url")) or None,
            runtime_health=SupportBundleRuntimeHealthSection(
                doctor_status=_coerce_text(runtime_health.get("doctor_status")),
                runtime_files_count=int(runtime_health.get("runtime_files_count", 0) or 0),
                checks_total=int(runtime_health.get("checks_total", 0) or 0),
                checks_degraded=int(runtime_health.get("checks_degraded", 0) or 0),
                checks_not_ready=int(runtime_health.get("checks_not_ready", 0) or 0),
                checkpoint_backend=_coerce_text(runtime_health.get("checkpoint_backend")),
                checkpoint_restore_strategy=_coerce_text(runtime_health.get("checkpoint_restore_strategy")),
                checkpoint_requires_external_snapshot=bool(runtime_health.get("checkpoint_requires_external_snapshot")),
            ),
            release_evidence=SupportBundleReleaseEvidenceSection(
                release_manifest_exists=bool(release_evidence.get("release_manifest_exists")),
                release_manifest_path=_coerce_text(release_evidence.get("release_manifest_path")) or None,
                release_manifest_git_sha=_coerce_text(release_evidence.get("release_manifest_git_sha")) or None,
                release_manifest_git_ref=_coerce_text(release_evidence.get("release_manifest_git_ref")) or None,
                release_scorecard_exists=bool(release_evidence.get("release_scorecard_exists")),
                release_scorecard_path=_coerce_text(release_evidence.get("release_scorecard_path")) or None,
                release_scorecard_status=_coerce_text(release_evidence.get("release_scorecard_status")) or None,
                quality_artifact_count=int(release_evidence.get("quality_artifact_count", 0) or 0),
            ),
            delivery_evidence=SupportBundleDeliveryEvidenceSection(
                contract_snapshots=_copy_str_list(delivery_evidence.get("contract_snapshots")),
                includes_http_snapshot=bool(delivery_evidence.get("includes_http_snapshot")),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return one JSON-serializable support-bundle manifest payload."""

        return {
            "created_at": self.created_at,
            "project_root": self.project_root,
            "base_url": self.base_url,
            "runtime_health": self.runtime_health.to_dict(),
            "release_evidence": self.release_evidence.to_dict(),
            "delivery_evidence": self.delivery_evidence.to_dict(),
        }


def build_runtime_doctor_contract_snapshot() -> dict[str, Any]:
    """Return a stable snapshot payload that documents the runtime-doctor contract shape."""

    report = RuntimeDoctorReport(
        status="ok",
        checked_at="<iso8601-utc>",
        project_root="<project_root>",
        summary=RuntimeDoctorSummary(
            checks_total=8,
            checks_ok=8,
            checks_degraded=0,
            checks_not_ready=0,
        ),
        checks={
            "server_config": RuntimeDoctorCheck(
                name="server_config",
                status="ok",
                message="Server config parsed successfully.",
                details={
                    "path": "<project_root>/backend/config/server_config.yaml",
                    "exists": True,
                    "web_host": "0.0.0.0",
                    "web_port": 38083,
                    "frontend_port": 33003,
                    "metrics_enabled": True,
                    "metrics_path": "/api/metrics",
                },
            ),
            "llm_config": RuntimeDoctorCheck(
                name="llm_config",
                status="ok",
                message="LLM config parsed successfully.",
                details={
                    "path": "<project_root>/backend/config/llm_config.yaml",
                    "exists": True,
                    "default_model": "<default_model>",
                    "active_models": ["<default_model>"],
                    "models_count": 1,
                },
            ),
            "data_dir": RuntimeDoctorCheck(
                name="data_dir",
                status="ok",
                message="Runtime data directory is writable.",
                details={"path": "<project_root>/data"},
            ),
            "runtime_files": RuntimeDoctorCheck(
                name="runtime_files",
                status="ok",
                message="Discovered 2 runtime file(s).",
                details={
                    "files": [
                        {"key": "sessions", "relative_path": "data/sessions/sessions.json", "size_bytes": 1024},
                        {"key": "share_links", "relative_path": "data/share_links.json", "size_bytes": 256},
                    ]
                },
            ),
            "checkpoint_runtime": RuntimeDoctorCheck(
                name="checkpoint_runtime",
                status="ok",
                message="Checkpoint runtime is configured for sqlite with archive-file recovery.",
                details=CheckpointRuntimeView(
                    backend="sqlite",
                    target="data/langgraph_checkpoints.sqlite3",
                    restore_strategy="archive_file",
                    archive_contains_checkpoint_data=True,
                    archived_files=["data/langgraph_checkpoints.sqlite3"],
                    requires_external_snapshot=False,
                    restore_instructions=[
                        "Checkpoint backend is sqlite; the archive contains the checkpoint database file and restore will place it back into the recorded runtime path.",
                        "Recorded checkpoint target: data/langgraph_checkpoints.sqlite3",
                    ],
                ).to_dict(),
            ),
            "backups": RuntimeDoctorCheck(
                name="backups",
                status="ok",
                message="Runtime backup inventory loaded.",
                details={
                    "path": "<project_root>/artifacts/runtime_backups",
                    "archive_count": 1,
                    "latest_archive": "<project_root>/artifacts/runtime_backups/runtime_backup_example.zip",
                },
            ),
            "contract_snapshots": RuntimeDoctorCheck(
                name="contract_snapshots",
                status="ok",
                message="Contract snapshots validated.",
                details={
                    "snapshots": {
                        "openapi": {
                            "name": "openapi_snapshot",
                            "status": "ok",
                            "message": "Snapshot file loaded.",
                            "details": {
                                "exists": True,
                                "path": "<project_root>/docs/reference/openapi.snapshot.json",
                                "root_type": "dict",
                                "top_level_keys": ["components", "info", "openapi", "paths", "servers"],
                            },
                        },
                        "sse": {
                            "name": "sse_snapshot",
                            "status": "ok",
                            "message": "Snapshot file loaded.",
                            "details": {
                                "exists": True,
                                "path": "<project_root>/docs/reference/sse-contract.snapshot.json",
                                "root_type": "dict",
                                "top_level_keys": ["endpoint", "modes", "registered_event_types", "schema_version"],
                            },
                        },
                    }
                },
            ),
            "http_probe": RuntimeDoctorCheck(
                name="http_probe",
                status="ok",
                message="Live HTTP probes passed.",
                details={
                    "base_url": "http://localhost:38083",
                    "endpoints": {
                        "health": {
                            "name": "health",
                            "status": "ok",
                            "message": "HTTP 200",
                            "details": {
                                "url": "http://localhost:38083/api/health",
                                "status_code": 200,
                                "content_type": "application/json",
                            },
                        },
                        "ready": {
                            "name": "ready",
                            "status": "ok",
                            "message": "HTTP 200",
                            "details": {
                                "url": "http://localhost:38083/api/ready",
                                "status_code": 200,
                                "content_type": "application/json",
                            },
                        },
                        "metrics": {
                            "name": "metrics",
                            "status": "ok",
                            "message": "HTTP 200",
                            "details": {
                                "url": "http://localhost:38083/api/metrics",
                                "status_code": 200,
                                "content_type": "text/plain; version=0.0.4",
                            },
                        },
                    },
                },
            ),
        },
    )
    return report.to_dict()
