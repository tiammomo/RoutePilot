"""Unit tests for runtime diagnostics script."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
  port: 38000
frontend:
  port: 33001
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
    assert report["checks"]["backups"]["details"]["archive_count"] == 1


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
