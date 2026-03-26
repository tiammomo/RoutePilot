"""Unit tests for frontend chat-runtime golden fixture export utility."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_frontend_chat_runtime_golden_fixture import (  # noqa: E402
    build_frontend_chat_runtime_golden_fixture,
    export_frontend_chat_runtime_golden_fixture,
)


def test_build_frontend_chat_runtime_golden_fixture_preserves_plan_validation_payload():
    source_path = PROJECT_ROOT / "tests" / "golden" / "chat_stream_golden_fixture.json"
    source_fixture = json.loads(source_path.read_text(encoding="utf-8"))

    payload = build_frontend_chat_runtime_golden_fixture(source_fixture)

    assert payload["schema_version"] == 1
    assert payload["source_fixture_schema_version"] == 2
    assert payload["modes"]["direct"]["assistant_message"]["content"] == "<text><text>"
    assert payload["modes"]["react"]["assistant_message"]["diagnostics"]["planId"] == "plan-demo"
    assert payload["modes"]["plan"]["runtime_state"]["plan_preview"]["validationErrors"] == [
        {
            "code": "TOOL_NOT_REGISTERED",
            "message": "<text>",
            "step_id": "s2",
            "tool": "not_registered_tool",
        }
    ]


def test_checked_in_frontend_chat_runtime_golden_fixture_matches_current_export(tmp_path):
    source_path = PROJECT_ROOT / "tests" / "golden" / "chat_stream_golden_fixture.json"
    output_path = tmp_path / "frontend_chat_runtime_golden_fixture.json"
    target = export_frontend_chat_runtime_golden_fixture(source_path, output_path)
    checked_in_path = PROJECT_ROOT / "tests" / "golden" / "frontend_chat_runtime_golden_fixture.json"

    current = json.loads(target.read_text(encoding="utf-8"))
    checked_in = json.loads(checked_in_path.read_text(encoding="utf-8"))

    assert current == checked_in
