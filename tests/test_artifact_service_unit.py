"""Unit tests for persisted artifact retrieval service."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.services.artifact_service import ArtifactService  # noqa: E402


class _RepositoryStub:
    def __init__(self, session: dict | None):
        self._session = session

    async def get(self, session_id: str):
        _ = session_id
        return self._session


@pytest.mark.asyncio
async def test_artifact_service_returns_latest_assistant_artifact():
    service = ArtifactService(
        _RepositoryStub(
            {
                "messages": [
                    {"role": "assistant", "content": "older"},
                    {
                        "role": "assistant",
                        "timestamp": "12:00:01",
                        "diagnostics": {
                            "runId": "run-123",
                            "artifact": {
                                "itinerary": {"plan_id": "plan-123"},
                                "budget": {"fallback_steps": 1},
                            },
                        },
                    },
                    {"role": "user", "content": "follow up"},
                ]
            }
        )
    )

    result = await service.get_latest_artifact("session-1")

    assert result["success"] is True
    assert result["artifact_found"] is True
    assert result["run_id"] == "run-123"
    assert result["message_timestamp"] == "12:00:01"
    assert result["artifact"]["itinerary"]["planId"] == "plan-123"
    assert result["artifact"]["budget"]["fallbackSteps"] == 1


@pytest.mark.asyncio
async def test_artifact_service_returns_empty_payload_when_session_has_no_artifact():
    service = ArtifactService(_RepositoryStub({"messages": [{"role": "assistant", "content": "plain text only"}]}))

    result = await service.get_latest_artifact("session-1")

    assert result["success"] is True
    assert result["artifact_found"] is False
    assert result["artifact"] is None


@pytest.mark.asyncio
async def test_artifact_service_returns_history_in_newest_first_order_with_limit():
    service = ArtifactService(
        _RepositoryStub(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "timestamp": "12:00:00",
                        "diagnostics": {
                            "runId": "run-1",
                            "artifact": {"itinerary": {"plan_id": "plan-1"}},
                        },
                    },
                    {"role": "user", "content": "continue"},
                    {
                        "role": "assistant",
                        "timestamp": "12:10:00",
                        "diagnostics": {
                            "runId": "run-2",
                            "artifact": {"itinerary": {"plan_id": "plan-2"}, "budget": {"fallback_steps": 1}},
                        },
                    },
                    {
                        "role": "assistant",
                        "timestamp": "12:20:00",
                        "diagnostics": {
                            "runId": "run-3",
                            "artifact": {"itinerary": {"plan_id": "plan-3"}},
                        },
                    },
                ]
            }
        )
    )

    result = await service.get_artifact_history("session-1", limit=2)

    assert result["success"] is True
    assert result["count"] == 2
    assert [entry["run_id"] for entry in result["entries"]] == ["run-3", "run-2"]
    assert result["entries"][0]["artifact"]["itinerary"]["planId"] == "plan-3"
    assert result["entries"][1]["artifact"]["budget"]["fallbackSteps"] == 1
