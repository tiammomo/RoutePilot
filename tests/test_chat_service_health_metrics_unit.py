from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.services.chat_service import ChatService


class _DummyRepository:
    async def create(self, session_data):
        _ = session_data
        return "dummy-session"

    async def get(self, session_id):
        _ = session_id
        return None

    async def update(self, session_id, session_data):
        _ = (session_id, session_data)
        return None

    async def delete(self, session_id):
        _ = session_id
        return False

    async def list_all(self, include_empty=False, limit=100):
        _ = (include_empty, limit)
        return []

    async def cleanup_expired(self, max_age_seconds):
        _ = max_age_seconds
        return 0


@pytest.mark.asyncio
async def test_tools_health_status_contains_slo_and_intent_aggregate():
    service = ChatService(_DummyRepository())

    service._record_run_metrics(
        intent="recommend",
        execution_stats={"steps": [{"status": "success", "error_code": None, "fallback_used": False}]},
        hard_error=False,
    )
    service._record_run_metrics(
        intent="budget",
        execution_stats={"steps": [{"status": "failed", "error_code": "TOOL_TIMEOUT", "fallback_used": True}]},
        hard_error=False,
    )
    service._record_run_metrics(intent="itinerary", execution_stats={"steps": []}, hard_error=True)

    status = await service.tools_health_status()
    slo = status.get("slo", {})
    intent_aggregate = status.get("intent_aggregate", {})

    assert status.get("window_minutes") == 60
    assert slo.get("status") == "degraded"
    assert slo.get("total_requests") == 3
    assert slo.get("timeout_rate") == 0.3333
    assert slo.get("failure_rate") == 0.6667
    assert slo.get("fallback_rate") == 0.3333
    assert isinstance(slo.get("thresholds"), dict)

    assert set(intent_aggregate.keys()) == {"recommend", "budget", "itinerary"}
    assert intent_aggregate["recommend"]["total"] == 1
    assert intent_aggregate["recommend"]["failure_rate"] == 0.0
    assert intent_aggregate["budget"]["timeout_rate"] == 1.0
    assert intent_aggregate["budget"]["fallback_rate"] == 1.0
    assert intent_aggregate["itinerary"]["failure_rate"] == 1.0
