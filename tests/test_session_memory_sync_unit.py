import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.services.session_service import SessionService


class FakeRepository:
    def __init__(self):
        self.store = {
            "s1": {
                "session_id": "s1",
                "messages": [{"role": "user", "content": "hello"}],
                "message_count": 1,
            }
        }

    async def create(self, session_data):
        session_id = session_data.get("session_id", "s_new")
        self.store[session_id] = {"session_id": session_id, **session_data}
        return session_id

    async def list_all(self, include_empty=False):
        return list(self.store.values())

    async def get(self, session_id):
        return self.store.get(session_id)

    async def update(self, session_id, session_data):
        if session_id in self.store:
            self.store[session_id].update(session_data)

    async def delete(self, session_id):
        return self.store.pop(session_id, None) is not None

    async def cleanup_expired(self, max_age_seconds):
        return 0


class FakeMemoryManager:
    def __init__(self):
        self.deleted_sessions = []
        self.cleared_sessions = []

    async def delete_session(self, session_id):
        self.deleted_sessions.append(session_id)
        return True

    async def clear_session_messages(self, session_id):
        self.cleared_sessions.append(session_id)
        return True


@pytest.mark.asyncio
async def test_delete_session_syncs_memory():
    repo = FakeRepository()
    memory = FakeMemoryManager()
    service = SessionService(repository=repo, memory_manager=memory)

    result = await service.delete_session("s1")

    assert result["success"] is True
    assert "s1" in memory.deleted_sessions


@pytest.mark.asyncio
async def test_clear_chat_syncs_memory():
    repo = FakeRepository()
    memory = FakeMemoryManager()
    service = SessionService(repository=repo, memory_manager=memory)

    result = await service.clear_chat("s1")

    assert result["success"] is True
    assert "s1" in memory.cleared_sessions
    assert repo.store["s1"]["messages"] == []
    assert repo.store["s1"]["message_count"] == 0
