"""Shared pytest fixtures and CI guards."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


EXTERNAL_API_TEST_FILES = {
    "test_api_integration.py",
    "test_sse_streaming.py",
    "test_e2e_streaming.py",
}


@lru_cache(maxsize=1)
def _is_external_api_available(base_url: str = "http://localhost:38000") -> bool:
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
    return "http://localhost:38000/api/chat/stream"


@pytest.fixture
def web_url() -> str:
    """Default web API root URL."""
    return "http://localhost:38000"


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
    to be launched out-of-process at localhost:38000.
    """
    file_name = Path(str(request.node.fspath)).name
    if file_name not in EXTERNAL_API_TEST_FILES:
        return
    if _is_external_api_available():
        return
    pytest.skip(
        "External API integration tests require http://localhost:38000; "
        "server is unavailable in current environment."
    )
