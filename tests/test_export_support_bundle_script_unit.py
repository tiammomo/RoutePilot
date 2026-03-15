"""Unit tests for support bundle export utility."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_support_bundle import export_support_bundle


def test_export_support_bundle_writes_expected_files(tmp_path):
    project_root = tmp_path
    (project_root / "config").mkdir()
    (project_root / "data" / "sessions").mkdir(parents=True)
    (project_root / "docs" / "reference").mkdir(parents=True)
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
  port: 38000
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
        json.dumps({"applications": {"backend": {"version": "3.3.0"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    bundle_path = export_support_bundle(
        project_root=project_root,
        output_dir=project_root / "artifacts" / "support",
        release_manifest_path=project_root / "artifacts" / "release" / "release-manifest.json",
    )

    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "doctor-report.json" in names
        assert "doctor-report.txt" in names
        assert "runtime-files.json" in names
        assert "release-manifest.json" in names
        assert "contracts/openapi.snapshot.json" in names
        assert "contracts/sse-contract.snapshot.json" in names

        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["doctor_status"] == "ok"
        assert manifest["release_manifest_exists"] is True
