"""Unit tests for runtime diagnostics script."""

from __future__ import annotations

import scripts.runtime_doctor as runtime_doctor
from scripts.runtime_ops_contracts import RuntimeDoctorReport
from scripts.runtime_doctor import run_runtime_doctor


def test_runtime_doctor_reports_ok_for_healthy_offline_layout(tmp_path):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data").mkdir()
    (project_root / "docs" / "reference").mkdir(parents=True)
    (project_root / "artifacts" / "runtime_backups").mkdir(parents=True)

    (project_root / "config" / "server_config.yaml").write_text(
        """
web:
  host: "0.0.0.0"
  port: 38083
frontend:
  port: 33003
observability:
  metrics_enabled: true
  metrics_path: "/api/metrics"
""".strip(),
        encoding="utf-8",
    )
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
    (project_root / "docs" / "reference" / "openapi.snapshot.json").write_text(
        '{"openapi": "3.1.0", "paths": {}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "reference" / "sse-contract.snapshot.json").write_text(
        '{"schema_version": 1, "modes": {"react": {"event_types": ["session_id", "done"]}}}',
        encoding="utf-8",
    )
    (project_root / "data" / "share_links.json").write_text("{}", encoding="utf-8")
    (project_root / "artifacts" / "runtime_backups" / "runtime_backup_20260315T000000Z.zip").write_bytes(b"zip")

    report = run_runtime_doctor(
        project_root=project_root,
        backup_dir=project_root / "artifacts" / "runtime_backups",
        openapi_snapshot=project_root / "docs" / "reference" / "openapi.snapshot.json",
        sse_snapshot=project_root / "docs" / "reference" / "sse-contract.snapshot.json",
    )

    assert report["status"] == "ok"
    assert report["checks"]["llm_config"]["status"] == "ok"
    assert report["checks"]["contract_snapshots"]["status"] == "ok"
    assert report["checks"]["checkpoint_runtime"]["status"] == "ok"
    assert report["checks"]["checkpoint_runtime"]["details"]["backend"] == "sqlite"
    assert report["checks"]["checkpoint_runtime"]["details"]["restore_strategy"] == "metadata_only"
    assert report["checks"]["checkpoint_runtime"]["details"]["requires_external_snapshot"] is False
    assert report["checks"]["backups"]["details"]["archive_count"] == 1
    normalized = RuntimeDoctorReport.from_dict(report)
    assert normalized.summary.checks_total >= 6
    assert normalized.checks["server_config"].details["web_port"] == 38083


def test_runtime_doctor_reports_postgres_checkpoint_runtime_dependency(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data").mkdir()
    (project_root / "docs" / "reference").mkdir(parents=True)

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
    (project_root / "docs" / "reference" / "openapi.snapshot.json").write_text(
        '{"openapi": "3.1.0", "paths": {}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "reference" / "sse-contract.snapshot.json").write_text(
        '{"schema_version": 1, "modes": {}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        runtime_doctor,
        "resolve_checkpoint_runtime",
        lambda _project_root: {
            "backend": "postgres",
            "target": "postgresql://demo:***@db.example.com:5432/moyuan",
            "restore_strategy": "external_snapshot",
            "archive_contains_checkpoint_data": False,
            "archived_files": [],
        },
    )
    monkeypatch.setattr(
        runtime_doctor,
        "build_restore_instructions",
        lambda _checkpoint_runtime: [
            "Checkpoint backend is postgres; restore checkpoint tables from an external database snapshot before switching runtime back to postgres."
        ],
    )

    report = run_runtime_doctor(
        project_root=project_root,
        backup_dir=project_root / "artifacts" / "runtime_backups",
        openapi_snapshot=project_root / "docs" / "reference" / "openapi.snapshot.json",
        sse_snapshot=project_root / "docs" / "reference" / "sse-contract.snapshot.json",
    )

    checkpoint_details = report["checks"]["checkpoint_runtime"]["details"]
    assert checkpoint_details["backend"] == "postgres"
    assert checkpoint_details["restore_strategy"] == "external_snapshot"
    assert checkpoint_details["requires_external_snapshot"] is True
    assert "external database snapshot" in checkpoint_details["restore_instructions"][0]


def test_runtime_doctor_reports_not_ready_when_llm_config_missing(tmp_path):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data").mkdir()
    (project_root / "docs" / "reference").mkdir(parents=True)

    (project_root / "docs" / "reference" / "openapi.snapshot.json").write_text(
        '{"openapi": "3.1.0", "paths": {}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "reference" / "sse-contract.snapshot.json").write_text(
        '{"schema_version": 1, "modes": {}}',
        encoding="utf-8",
    )

    report = run_runtime_doctor(
        project_root=project_root,
        backup_dir=project_root / "artifacts" / "runtime_backups",
        openapi_snapshot=project_root / "docs" / "reference" / "openapi.snapshot.json",
        sse_snapshot=project_root / "docs" / "reference" / "sse-contract.snapshot.json",
    )

    assert report["status"] == "not_ready"
    assert report["checks"]["llm_config"]["status"] == "not_ready"


def test_runtime_doctor_degrades_when_runtime_file_inventory_is_locked(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data").mkdir()
    (project_root / "docs" / "reference").mkdir(parents=True)

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
    (project_root / "docs" / "reference" / "openapi.snapshot.json").write_text(
        '{"openapi": "3.1.0", "paths": {}}',
        encoding="utf-8",
    )
    (project_root / "docs" / "reference" / "sse-contract.snapshot.json").write_text(
        '{"schema_version": 1, "modes": {}}',
        encoding="utf-8",
    )

    def _raise_permission_error(_project_root):
        raise PermissionError("sessions.json is locked")

    monkeypatch.setattr(runtime_doctor, "discover_runtime_files", _raise_permission_error)

    report = run_runtime_doctor(
        project_root=project_root,
        backup_dir=project_root / "artifacts" / "runtime_backups",
        openapi_snapshot=project_root / "docs" / "reference" / "openapi.snapshot.json",
        sse_snapshot=project_root / "docs" / "reference" / "sse-contract.snapshot.json",
    )

    assert report["status"] == "degraded"
    assert report["checks"]["runtime_files"]["status"] == "degraded"
    assert report["checks"]["runtime_files"]["details"]["error_type"] == "PermissionError"
