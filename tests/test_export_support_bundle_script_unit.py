"""Unit tests for support bundle export utility."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.export_support_bundle import export_support_bundle


def test_export_support_bundle_writes_expected_files(tmp_path):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data" / "sessions").mkdir(parents=True)
    (project_root / "docs" / "reference").mkdir(parents=True)
    (project_root / "docs" / "benchmarks").mkdir(parents=True)
    (project_root / "artifacts" / "release").mkdir(parents=True)

    (project_root / "config" / "llm_config.yaml").write_text(
        """
default_model: demo
models:
  demo:
    provider: openai-compatible
    model: demo
    api_base: http://localhost:1234/v1
    api_key: ""
""".strip(),
        encoding="utf-8",
    )
    (project_root / "config" / "server_config.yaml").write_text(
        """
web:
  port: 38083
observability:
  metrics_enabled: true
  metrics_path: "/api/metrics"
""".strip(),
        encoding="utf-8",
    )
    (project_root / "data" / "sessions" / "sessions.json").write_text("{}", encoding="utf-8")
    (project_root / "docs" / "reference" / "openapi.snapshot.json").write_text(
        '{"openapi": "3.1.0", "paths": {}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "reference" / "sse-contract.snapshot.json").write_text(
        '{"schema_version": 1, "modes": {"react": {"event_types": ["done"]}}}',
        encoding="utf-8",
    )
    (project_root / "artifacts" / "release" / "release-manifest.json").write_text(
        json.dumps(
            {
                "created_at": "2026-03-29T00:00:00+00:00",
                "source": {"git_sha": "abc1234", "git_ref": "refs/tags/v3.3.0"},
                "applications": {"backend": {"version": "3.3.0", "name": "backend", "image": "ghcr.io/demo/backend"}},
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_root / "docs" / "benchmarks" / "release_harness_scorecard_latest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-29T00:00:00+00:00",
                "status": "pass",
                "summary": {"error_count": 0, "warning_count": 0},
                "benchmark": {},
                "subagents": {},
                "delivery": {},
                "skills": {},
                "findings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle_path = export_support_bundle(
        project_root=project_root,
        output_dir=project_root / "artifacts" / "support",
        release_manifest_path=project_root / "artifacts" / "release" / "release-manifest.json",
        release_scorecard_path=project_root / "docs" / "benchmarks" / "release_harness_scorecard_latest.json",
    )

    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "doctor-report.json" in names
        assert "doctor-report.txt" in names
        assert "checkpoint-runtime.json" in names
        assert "runtime-files.json" in names
        assert "release-manifest.json" in names
        assert "release-harness-scorecard.json" in names
        assert "contracts/openapi.snapshot.json" in names
        assert "contracts/sse-contract.snapshot.json" in names

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["runtime_health"]["doctor_status"] == "ok"
        assert manifest["runtime_health"]["runtime_files_count"] >= 1
        assert manifest["runtime_health"]["checkpoint_backend"] == "sqlite"
        assert manifest["runtime_health"]["checkpoint_restore_strategy"] == "metadata_only"
        assert manifest["runtime_health"]["checkpoint_requires_external_snapshot"] is False
        assert manifest["release_evidence"]["release_manifest_exists"] is True
        assert manifest["release_evidence"]["release_manifest_git_sha"] == "abc1234"
        assert manifest["release_evidence"]["release_scorecard_exists"] is True
        assert manifest["release_evidence"]["release_scorecard_status"] == "pass"
        assert manifest["release_evidence"]["quality_artifact_count"] == 6
        assert manifest["delivery_evidence"]["contract_snapshots"] == [
            "openapi.snapshot.json",
            "sse-contract.snapshot.json",
        ]

        checkpoint_runtime = json.loads(archive.read("checkpoint-runtime.json").decode("utf-8"))
        assert checkpoint_runtime["backend"] == "sqlite"
        assert checkpoint_runtime["restore_strategy"] == "metadata_only"
        assert checkpoint_runtime["requires_external_snapshot"] is False
