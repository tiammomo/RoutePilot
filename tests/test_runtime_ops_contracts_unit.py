"""Unit tests for runtime ops contracts and manifest sections."""

from __future__ import annotations

from scripts.runtime_ops_contracts import (
    ReleaseHarnessScorecard,
    ReleaseManifest,
    RuntimeDoctorReport,
    SupportBundleManifest,
    SupportBundleRuntimeHealthSection,
)


def test_runtime_doctor_report_round_trip_preserves_check_inventory() -> None:
    """Round-trip a loose runtime-doctor payload through the typed report contract."""

    payload = {
        "status": "ok",
        "checked_at": "2026-03-28T00:00:00+00:00",
        "project_root": "D:/demo",
        "summary": {
            "checks_total": 2,
            "checks_ok": 2,
            "checks_degraded": 0,
            "checks_not_ready": 0,
        },
        "checks": {
            "llm_config": {
                "name": "llm_config",
                "status": "ok",
                "message": "LLM config parsed successfully.",
                "details": {"default_model": "demo"},
            },
            "runtime_files": {
                "name": "runtime_files",
                "status": "ok",
                "message": "Discovered 1 runtime file(s).",
                "details": {"files": [{"key": "sessions"}]},
            },
        },
    }

    report = RuntimeDoctorReport.from_dict(payload)

    assert report.status == "ok"
    assert report.summary.checks_total == 2
    assert report.checks["llm_config"].details["default_model"] == "demo"
    assert report.to_dict() == payload


def test_support_bundle_manifest_round_trip_preserves_nested_sections() -> None:
    """Round-trip a support-bundle manifest through the typed nested-section contract."""

    payload = {
        "created_at": "2026-03-28T00:00:00+00:00",
        "project_root": "D:/demo",
        "base_url": "http://localhost:38083",
        "runtime_health": {
            "doctor_status": "ok",
            "runtime_files_count": 3,
            "checks_total": 7,
            "checks_degraded": 0,
            "checks_not_ready": 0,
            "checkpoint_backend": "postgres",
            "checkpoint_restore_strategy": "external_snapshot",
            "checkpoint_requires_external_snapshot": True,
        },
        "release_evidence": {
            "release_manifest_exists": True,
            "release_manifest_path": "artifacts/release/release-manifest.json",
            "release_manifest_git_sha": "abc1234",
            "release_manifest_git_ref": "refs/tags/v3.3.0",
            "release_scorecard_exists": True,
            "release_scorecard_path": "docs/benchmarks/release_harness_scorecard_latest.json",
            "release_scorecard_status": "pass",
            "quality_artifact_count": 6,
        },
        "delivery_evidence": {
            "contract_snapshots": ["openapi.snapshot.json", "sse-contract.snapshot.json"],
            "includes_http_snapshot": False,
        },
    }

    manifest = SupportBundleManifest.from_dict(payload)

    assert manifest.runtime_health.runtime_files_count == 3
    assert manifest.runtime_health.checkpoint_backend == "postgres"
    assert manifest.release_evidence.release_manifest_exists is True
    assert manifest.release_evidence.release_scorecard_status == "pass"
    assert manifest.delivery_evidence.contract_snapshots == [
        "openapi.snapshot.json",
        "sse-contract.snapshot.json",
    ]
    assert manifest.to_dict() == payload


def test_runtime_health_section_uses_runtime_files_from_doctor_report() -> None:
    """Derive runtime-health manifest counters from the typed doctor report."""

    report = RuntimeDoctorReport.from_dict(
        {
            "status": "degraded",
            "checked_at": "2026-03-28T00:00:00+00:00",
            "project_root": "D:/demo",
            "summary": {
                "checks_total": 4,
                "checks_ok": 2,
                "checks_degraded": 1,
                "checks_not_ready": 1,
            },
            "checks": {
                "runtime_files": {
                    "name": "runtime_files",
                    "status": "ok",
                    "message": "Discovered 2 runtime file(s).",
                    "details": {
                        "files": [
                            {"key": "sessions"},
                            {"key": "share_links"},
                        ]
                    },
                },
                "checkpoint_runtime": {
                    "name": "checkpoint_runtime",
                    "status": "ok",
                    "message": "Checkpoint runtime uses postgres with external snapshot recovery.",
                    "details": {
                        "backend": "postgres",
                        "target": "postgresql://demo:***@db.example.com:5432/moyuan",
                        "restore_strategy": "external_snapshot",
                        "archive_contains_checkpoint_data": False,
                        "archived_files": [],
                        "requires_external_snapshot": True,
                        "restore_instructions": [
                            "Checkpoint backend is postgres; restore checkpoint tables from an external database snapshot before switching runtime back to postgres."
                        ],
                    },
                },
            },
        }
    )

    section = SupportBundleRuntimeHealthSection.from_doctor_report(report)

    assert section.doctor_status == "degraded"
    assert section.runtime_files_count == 2
    assert section.checks_degraded == 1
    assert section.checks_not_ready == 1
    assert section.checkpoint_backend == "postgres"
    assert section.checkpoint_restore_strategy == "external_snapshot"
    assert section.checkpoint_requires_external_snapshot is True


def test_release_manifest_round_trip_preserves_quality_artifacts() -> None:
    """Round-trip one release manifest through the typed release-evidence contract."""

    payload = {
        "created_at": "2026-03-29T00:00:00+00:00",
        "source": {
            "git_sha": "abc1234",
            "git_ref": "refs/tags/v3.3.0",
        },
        "applications": {
            "backend": {
                "name": "moyuan-backend",
                "version": "3.3.0",
                "image": "ghcr.io/demo/moyuan-backend",
            },
            "frontend": {
                "name": "moyuan-frontend",
                "version": "3.3.0",
                "image": "ghcr.io/demo/moyuan-frontend",
            },
        },
        "quality": {
            "release_check_command": "python scripts/release_harness_scorecard.py --strict",
            "artifacts": {
                "benchmark_report": "docs/benchmarks/agent_benchmark_latest.json",
                "golden_eval_report": "docs/benchmarks/agent_golden_eval_latest.json",
                "subagent_scorecard_report": "docs/benchmarks/agent_subagent_scorecard_latest.json",
                "release_harness_scorecard_report": "docs/benchmarks/release_harness_scorecard_latest.json",
                "delivery_snapshot": "frontend/tests/features/trip-plan/__snapshots__/travelPlanDeliverySnapshot.test.ts.snap",
                "skills_catalog": "docs/reference/skills-market-catalog.md",
            },
        },
    }

    manifest = ReleaseManifest.from_dict(payload)

    assert manifest.source.git_sha == "abc1234"
    assert manifest.applications["backend"].version == "3.3.0"
    assert manifest.quality.artifacts.count() == 6
    assert manifest.to_dict() == payload


def test_release_harness_scorecard_round_trip_preserves_release_sections() -> None:
    """Round-trip one release scorecard through the typed release-evidence contract."""

    payload = {
        "generated_at": "2026-03-29T00:00:00+00:00",
        "status": "warn",
        "summary": {
            "error_count": 0,
            "warning_count": 2,
        },
        "benchmark": {
            "golden_report": "docs/benchmarks/agent_golden_eval_latest.json",
            "benchmark_report": "docs/benchmarks/agent_benchmark_latest.json",
            "golden_pass_rate": 0.98,
            "golden_hallucination_rate": 0.0,
            "benchmark_success_rate": 0.75,
            "benchmark_hallucination_rate": 0.0,
            "fallback_steps_total": 3,
        },
        "subagents": {
            "scorecard_report": "docs/benchmarks/agent_subagent_scorecard_latest.json",
            "expected_subagents": ["research", "planning"],
            "observed_subagents": ["research"],
            "healthy_subagents": 1,
            "partial_subagents": 0,
            "missing_subagents": 1,
            "mismatch_subagents": 0,
        },
        "delivery": {
            "snapshot_path": "frontend/tests/features/trip-plan/__snapshots__/travelPlanDeliverySnapshot.test.ts.snap",
            "modes_covered": ["plan"],
            "expected_modes": ["direct", "plan", "react"],
            "branding_present": True,
        },
        "skills": {
            "skills_catalog": "docs/reference/skills-market-catalog.md",
            "total_skills": 4,
            "docs_covered": 4,
            "eval_covered": 3,
            "selection_policy_covered": 4,
            "allowed_subagents_covered": 4,
            "skill_names": ["PlanSynthesisSkill"],
        },
        "findings": [
            {
                "severity": "warning",
                "category": "delivery",
                "message": "delivery snapshot is missing replay modes: direct, react",
            }
        ],
    }

    scorecard = ReleaseHarnessScorecard.from_dict(payload)

    assert scorecard.status == "warn"
    assert scorecard.summary.warning_count == 2
    assert scorecard.delivery.modes_covered == ["plan"]
    assert scorecard.findings[0].category == "delivery"
    assert scorecard.to_dict() == payload
