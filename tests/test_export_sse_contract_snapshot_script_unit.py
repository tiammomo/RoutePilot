"""Unit tests for SSE contract snapshot export script."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_sse_contract_snapshot import export_sse_contract_snapshot  # noqa: E402


def test_export_sse_contract_snapshot_writes_expected_modes(tmp_path):
    output_path = tmp_path / "sse-contract.snapshot.json"

    target = export_sse_contract_snapshot(output_path)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert target == output_path
    assert payload["schema_version"] == 2
    assert "metadata" in payload["registered_event_types"]
    assert "done" in payload["registered_event_types"]
    assert set(payload["modes"].keys()) == {"direct", "react", "plan"}
    assert "done" in payload["modes"]["react"]["event_types"]
    assert "plan_preview" in payload["modes"]["plan"]["event_types"]
    assert "subagent_start" in payload["modes"]["react"]["event_types"]
    assert "artifact_patch" in payload["modes"]["plan"]["event_types"]
    assert payload["modes"]["direct"]["response"]["status_code"] == 200
    assert payload["modes"]["react"]["response"]["headers"]["x-request-id"] == "<id>"
