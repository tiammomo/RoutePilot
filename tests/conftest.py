"""Shared pytest fixtures, CI guards, and import bootstrap."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from backend.moyuan_web.bootstrap import ensure_project_paths

ensure_project_paths()

EXTERNAL_API_TEST_FILES = {
    "test_api_integration.py",
    "test_sse_streaming.py",
    "test_e2e_streaming.py",
}
LOCAL_SMOKE_TEST_FILES = {
    "test_api_smoke_local.py",
    "test_chat_stream_local.py",
}
QUALITY_TEST_FILES = {
    "test_agent_benchmark_script_unit.py",
    "test_agent_benchmark_trend_script_unit.py",
    "test_agent_golden_eval_script_unit.py",
    "test_agent_quality_gate_script_unit.py",
    "test_agent_replay_script_unit.py",
}


@lru_cache(maxsize=1)
def _is_external_api_available(base_url: str = "http://localhost:38083") -> bool:
    """Best-effort probe for externally hosted API tests."""
    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{base_url}/api/health")
            return resp.status_code < 500
    except Exception:
        return False


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop once for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def api_url() -> str:
    """Default chat streaming endpoint."""
    return "http://localhost:38083/api/chat/stream"


@pytest.fixture
def web_url() -> str:
    """Default web API root URL."""
    return "http://localhost:38083"


@pytest.fixture
def sample_queries():
    """A small set of smoke queries."""
    return [
        "北京旅游推荐",
        "上海美食攻略",
        "杭州西湖一日游",
        "成都火锅",
        "三亚海滨度假",
    ]


@pytest_asyncio.fixture
async def async_client():
    """Shared async client fixture."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        yield client


@pytest.fixture(autouse=True)
def skip_external_api_tests_when_server_unavailable(request):
    """Skip tests that require a separately running localhost API in CI.

    These suites are true integration checks and require the API service
    to be launched out-of-process at localhost:38083.
    """
    file_name = Path(str(request.node.fspath)).name
    if file_name not in EXTERNAL_API_TEST_FILES:
        return
    if _is_external_api_available():
        return
    pytest.skip(
        "External API integration tests require http://localhost:38083; "
        "server is unavailable in current environment."
    )


def pytest_collection_modifyitems(config, items):
    """Apply stable markers from filename conventions so CI can slice test layers."""
    _ = config
    for item in items:
        file_name = Path(str(item.fspath)).name
        if file_name in EXTERNAL_API_TEST_FILES:
            item.add_marker(pytest.mark.external_api)
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.local)
            continue
        if file_name in LOCAL_SMOKE_TEST_FILES:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.local)
            continue
        if file_name in QUALITY_TEST_FILES:
            item.add_marker(pytest.mark.quality)
            item.add_marker(pytest.mark.unit)
            continue
        if "integration" in file_name or "e2e" in file_name:
            item.add_marker(pytest.mark.integration)
            continue
        item.add_marker(pytest.mark.unit)
