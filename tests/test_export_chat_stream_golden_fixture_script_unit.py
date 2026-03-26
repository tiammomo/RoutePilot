"""Unit tests for chat-stream golden fixture export utility."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_sse_contract_snapshot import export_chat_stream_golden_fixture  # noqa: E402


def test_export_chat_stream_golden_fixture_writes_expected_modes(tmp_path):
    output_path = tmp_path / "chat_stream_golden_fixture.json"

    target = export_chat_stream_golden_fixture(output_path)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert target == output_path
    assert payload["schema_version"] == 2
    assert payload["source_snapshot_schema_version"] == 2
    assert payload["endpoint"] == "POST /api/chat/stream"
    assert set(payload["modes"].keys()) == {"direct", "react", "plan"}
    assert payload["modes"]["direct"]["request"]["mode"] == "direct"
    assert payload["modes"]["react"]["response"]["status_code"] == 200
    assert "plan_preview" in payload["modes"]["plan"]["event_sequence"]
    assert "artifact_patch" in payload["modes"]["plan"]["event_sequence"]
    assert "metadata" in payload["modes"]["react"]["key_events"]
    assert "done" in payload["modes"]["react"]["key_events"]
    assert len(payload["modes"]["direct"]["key_events"]["answer_chunks"]) >= 2
    assert len(payload["modes"]["react"]["key_events"]["reasoning_chunks"]) >= 1
    assert len(payload["modes"]["plan"]["key_events"]["stages"]) >= 1
    assert len(payload["modes"]["plan"]["key_events"]["artifact_patches"]) >= 2
    assert len(payload["modes"]["react"]["key_events"]["subagent_starts"]) >= 1


def test_checked_in_chat_stream_golden_fixture_matches_current_export(tmp_path):
    output_path = tmp_path / "chat_stream_golden_fixture.json"
    target = export_chat_stream_golden_fixture(output_path)
    checked_in_path = PROJECT_ROOT / "tests" / "golden" / "chat_stream_golden_fixture.json"

    current = json.loads(target.read_text(encoding="utf-8"))
    checked_in = json.loads(checked_in_path.read_text(encoding="utf-8"))

    assert current == checked_in
