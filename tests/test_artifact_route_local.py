"""Local ASGI smoke tests for artifact retrieval route."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.dependencies.container import get_container  # noqa: E402
from moyuan_web.main import create_app  # noqa: E402


@pytest.mark.asyncio
async def test_latest_artifact_route_returns_normalized_artifact():
    app = create_app()
    repository = get_container().resolve("SessionRepository")
    session_id = f"artifact-route-{uuid.uuid4()}"
    await repository.create(
        {
            "session_id": session_id,
            "name": "artifact route",
            "model_id": "MiniMax-M2.5",
            "messages": [
                {
                    "role": "assistant",
                    "content": "trip ready",
                    "timestamp": "13:00:00",
                    "diagnostics": {
                        "runId": "run-artifact",
                        "artifact": {
                            "itinerary": {"plan_id": "plan-route"},
                            "verification": {"should_retry": False},
                        },
                    },
                }
            ],
        }
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/artifacts/{session_id}/latest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_found"] is True
    assert payload["run_id"] == "run-artifact"
    assert payload["artifact"]["itinerary"]["planId"] == "plan-route"
    assert payload["artifact"]["verification"]["shouldRetry"] is False


@pytest.mark.asyncio
async def test_latest_artifact_route_returns_not_found_for_missing_session():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/artifacts/missing-session/latest")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_artifact_history_route_returns_newest_first_entries_with_limit():
    app = create_app()
    repository = get_container().resolve("SessionRepository")
    session_id = f"artifact-history-{uuid.uuid4()}"
    await repository.create(
        {
            "session_id": session_id,
            "name": "artifact history",
            "model_id": "MiniMax-M2.5",
            "messages": [
                {
                    "role": "assistant",
                    "content": "v1",
                    "timestamp": "13:00:00",
                    "diagnostics": {
                        "runId": "run-1",
                        "artifact": {"itinerary": {"plan_id": "plan-1"}},
                    },
                },
                {
                    "role": "assistant",
                    "content": "v2",
                    "timestamp": "13:05:00",
                    "diagnostics": {
                        "runId": "run-2",
                        "artifact": {"itinerary": {"plan_id": "plan-2"}},
                    },
                },
                {
                    "role": "assistant",
                    "content": "v3",
                    "timestamp": "13:10:00",
                    "diagnostics": {
                        "runId": "run-3",
                        "artifact": {"itinerary": {"plan_id": "plan-3"}, "budget": {"fallback_steps": 2}},
                    },
                },
            ],
        }
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(f"/api/artifacts/{session_id}/history", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [entry["run_id"] for entry in payload["entries"]] == ["run-3", "run-2"]
    assert payload["entries"][0]["artifact"]["itinerary"]["planId"] == "plan-3"
    assert payload["entries"][0]["artifact"]["budget"]["fallbackSteps"] == 2
