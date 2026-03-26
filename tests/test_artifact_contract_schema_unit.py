"""Unit tests for artifact contract normalization helpers."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.api.schemas import (  # noqa: E402
    ArtifactHistoryResponse,
    normalize_artifact_patch,
    normalize_trip_plan_artifact,
)


def test_normalize_trip_plan_artifact_converts_snake_case_to_public_camel_case():
    artifact = normalize_trip_plan_artifact(
        {
            "intent": {"name": "itinerary", "confidence": 0.9, "entities": {}, "detail": {}},
            "research": {
                "summary": "Collected signals.",
                "evidence": [{"tool": "search_cities", "status": "collected", "query": "Shanghai"}],
                "destinations": ["Shanghai"],
                "source_tools": ["search_cities"],
            },
            "itinerary": {
                "plan_id": "plan-123",
                "explanation": "3-day trip",
                "steps": [{"title": "Day 1"}],
                "validation_status": "warn",
                "validation_errors": [{"code": "TOOL_NOT_REGISTERED"}],
            },
            "budget": {
                "summary": {"currency": "CNY"},
                "execution_budget": {"daily": 500},
                "stale_result_count": 1,
                "fallback_steps": 2,
            },
            "verification": {
                "passed": True,
                "should_retry": False,
                "issues": [],
                "refresh_targets": ["weather"],
                "summary": "verification_passed",
            },
            "answer": "done",
            "reasoning": "thinking",
            "tools_used": ["search_cities"],
            "metadata": {"session_id": "session-1"},
        }
    )

    assert artifact["research"]["sourceTools"] == ["search_cities"]
    assert artifact["itinerary"]["planId"] == "plan-123"
    assert artifact["itinerary"]["validationStatus"] == "warn"
    assert artifact["budget"]["executionBudget"] == {"daily": 500}
    assert artifact["budget"]["staleResultCount"] == 1
    assert artifact["verification"]["shouldRetry"] is False
    assert artifact["verification"]["refreshTargets"] == ["weather"]
    assert artifact["toolsUsed"] == ["search_cities"]


def test_normalize_artifact_patch_converts_patch_aliases():
    patch = normalize_artifact_patch(
        {
            "itinerary": {"plan_id": "plan-123", "validation_status": "pass"},
            "budget": {"fallback_steps": 1},
            "verification": {"refresh_targets": ["weather"]},
            "tools_used": ["search_cities"],
        }
    )

    assert patch["itinerary"]["planId"] == "plan-123"
    assert patch["itinerary"]["validationStatus"] == "pass"
    assert patch["budget"]["fallbackSteps"] == 1
    assert patch["verification"]["refreshTargets"] == ["weather"]
    assert patch["toolsUsed"] == ["search_cities"]


def test_normalize_trip_plan_artifact_preserves_empty_payload_as_empty_dict():
    assert normalize_trip_plan_artifact({}) == {}
    assert normalize_trip_plan_artifact(None) == {}


def test_artifact_history_response_normalizes_nested_artifacts():
    response = ArtifactHistoryResponse.model_validate(
        {
            "success": True,
            "session_id": "session-1",
            "count": 1,
            "entries": [
                {
                    "artifact": {
                        "itinerary": {"plan_id": "plan-123"},
                        "budget": {"fallback_steps": 2},
                    },
                    "run_id": "run-1",
                    "message_timestamp": "2026-03-27T12:00:00",
                    "message_index": 3,
                }
            ],
        }
    ).model_dump(by_alias=True)

    assert response["entries"][0]["artifact"]["itinerary"]["planId"] == "plan-123"
    assert response["entries"][0]["artifact"]["budget"]["fallbackSteps"] == 2
