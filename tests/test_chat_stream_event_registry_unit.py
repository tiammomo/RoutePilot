"""Unit tests for public chat-stream SSE event registry."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.api.events import CHAT_STREAM_EVENT_TYPES, validate_chat_stream_payload  # noqa: E402


def test_validate_chat_stream_payload_injects_request_context_ids():
    payload = validate_chat_stream_payload(
        {
            "type": "metadata",
            "run_id": "run-123",
            "total_steps": 1,
            "tools_used": ["search_cities"],
            "has_reasoning": True,
            "reasoning_length": 12,
            "answer_length": 20,
            "execution_stats": {},
            "verification_passed": True,
            "stale_result_count": 0,
            "fallback_steps": 0,
            "failure_clusters": {},
            "artifact": {},
        },
        request_id="req-123",
        trace_id="trace-123",
    )

    assert payload["type"] == "metadata"
    assert payload["request_id"] == "req-123"
    assert payload["trace_id"] == "trace-123"


def test_validate_chat_stream_payload_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        validate_chat_stream_payload({"type": "reasoning_metadata", "has_reasoning": True})


def test_registered_chat_stream_event_types_cover_public_runtime_events():
    assert "plan_preview" in CHAT_STREAM_EVENT_TYPES
    assert "artifact_patch" in CHAT_STREAM_EVENT_TYPES
    assert "done" in CHAT_STREAM_EVENT_TYPES


def test_validate_chat_stream_payload_normalizes_artifact_aliases():
    payload = validate_chat_stream_payload(
        {
            "type": "artifact_patch",
            "subagent": "planning",
            "artifact_patch": {
                "itinerary": {
                    "plan_id": "plan-123",
                    "validation_status": "warn",
                },
                "budget": {
                    "fallback_steps": 1,
                },
            },
        }
    )

    assert payload["artifact_patch"]["itinerary"]["planId"] == "plan-123"
    assert payload["artifact_patch"]["itinerary"]["validationStatus"] == "warn"
    assert payload["artifact_patch"]["budget"]["fallbackSteps"] == 1
