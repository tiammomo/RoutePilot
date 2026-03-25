"""Unit tests for the refactored session service facade."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.services.session_service import SessionService  # noqa: E402


class _FakeRepository:
    def __init__(self) -> None:
        self.store = {
            "s1": {
                "session_id": "s1",
                "name": "existing",
                "model_id": "demo-model",
                "messages": [{"role": "user", "content": "hello"}],
                "message_count": 1,
            }
        }

    async def create(self, session_data):
        session_id = session_data.get("session_id", "s-new")
        self.store[session_id] = {"session_id": session_id, **session_data}
        return session_id

    async def list_all(self, include_empty=False):
        _ = include_empty
        return list(self.store.values())

    async def get(self, session_id):
        return self.store.get(session_id)

    async def update(self, session_id, session_data):
        if session_id in self.store:
            self.store[session_id].update(session_data)

    async def delete(self, session_id):
        return self.store.pop(session_id, None) is not None


class _FakeMemoryManager:
    async def delete_session(self, session_id):
        _ = session_id
        return True

    async def clear_session_messages(self, session_id):
        _ = session_id
        return True


@pytest.mark.asyncio
async def test_session_service_create_session_uses_default_name_and_model(monkeypatch):
    monkeypatch.setattr(SessionService, "_resolve_default_model_id", classmethod(lambda cls: "resolved-model"))
    service = SessionService(repository=_FakeRepository(), memory_manager=_FakeMemoryManager())

    result = await service.create_session()

    assert result["success"] is True
    assert result["session_id"] == "s-new"
    assert result["name"] == service.DEFAULT_SESSION_NAME
    assert service._repository.store["s-new"]["model_id"] == "resolved-model"


@pytest.mark.asyncio
async def test_session_service_lists_sessions_with_total():
    service = SessionService(repository=_FakeRepository(), memory_manager=_FakeMemoryManager())

    result = await service.list_sessions(include_empty=True)

    assert result["success"] is True
    assert result["total"] == 1
    assert result["sessions"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_session_service_returns_not_found_payload_for_missing_session():
    service = SessionService(repository=_FakeRepository(), memory_manager=_FakeMemoryManager())

    result = await service.get_session_model("missing")

    assert result == {"success": False, "error": "会话不存在"}


@pytest.mark.asyncio
async def test_session_service_builds_default_memory_manager_lazily(monkeypatch):
    calls = {"count": 0}

    class _LazyMemoryManager:
        async def delete_session(self, session_id):
            _ = session_id
            return True

        async def clear_session_messages(self, session_id):
            _ = session_id
            return True

    monkeypatch.setattr(
        "moyuan_web.services.session_service.build_default_memory_manager",
        lambda: calls.__setitem__("count", calls["count"] + 1) or _LazyMemoryManager(),
    )
    service = SessionService(repository=_FakeRepository(), memory_manager=None)

    assert service._memory_manager is None
    create_result = await service.create_session()
    assert create_result["success"] is True
    assert calls["count"] == 0

    clear_result = await service.clear_chat("s1")
    assert clear_result["success"] is True
    assert calls["count"] == 1
