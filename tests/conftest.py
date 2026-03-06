"""
Pytest 配置文件和共享 fixtures
"""

import pytest
import httpx
import asyncio
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def api_url() -> str:
    """API 基础 URL"""
    return "http://localhost:38000/api/chat/stream"


@pytest.fixture
def web_url() -> str:
    """Web API URL (v3.x - Agent 集成到 Web API)"""
    return "http://localhost:38000"


@pytest.fixture
def sample_queries():
    """测试查询列表"""
    return [
        "北京旅游推荐",
        "上海美食攻略",
        "杭州西湖一日游",
        "成都火锅",
        "三亚海滨度假"
    ]


@pytest_asyncio.fixture
async def async_client():
    """异步 HTTP 客户端"""
    async with httpx.AsyncClient(timeout=180.0) as client:
        yield client
