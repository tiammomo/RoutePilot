"""Session lifecycle orchestration helpers."""

from __future__ import annotations

from typing import Any

from ...repositories.session_repository import SessionRepository
from .runtime import DEFAULT_SESSION_NAME, MemoryManagerFactory, SessionMemoryManager


class SessionLifecycleService:
    """Coordinate session CRUD operations and memory side effects."""

    def __init__(
        self,
        repository: SessionRepository,
        *,
        memory_manager: SessionMemoryManager | None,
        memory_manager_factory: MemoryManagerFactory | None,
        default_model_id: str,
        default_session_name: str = DEFAULT_SESSION_NAME,
    ) -> None:
        self._repository = repository
        self._memory_manager = memory_manager
        self._memory_manager_factory = memory_manager_factory
        self._default_model_id = default_model_id
        self._default_session_name = default_session_name

    async def create_session(self, name: str | None = None) -> dict[str, Any]:
        """Create a new session record with normalized display name and default model."""
        session_name = (name or self._default_session_name).strip() or self._default_session_name
        session_id = await self._repository.create(
            {
                "name": session_name,
                "model_id": self._default_model_id,
            }
        )
        return {"success": True, "session_id": session_id, "name": session_name}

    async def list_sessions(self, include_empty: bool = False) -> dict[str, Any]:
        """List sessions and include total count for API response payload."""
        sessions = await self._repository.list_all(include_empty=include_empty)
        return {"success": True, "sessions": sessions, "total": len(sessions)}

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        """Delete session data and associated memory snapshot when session exists."""
        deleted = await self._repository.delete(session_id)
        if deleted:
            try:
                await self._get_memory_manager().delete_session(session_id)
            except Exception:
                pass
            return {"success": True}
        return self._not_found()

    async def update_session_name(self, session_id: str, name: str) -> dict[str, Any]:
        """Update session display name after existence validation."""
        session = await self._repository.get(session_id)
        if not session:
            return self._not_found()

        await self._repository.update(session_id, {"name": name})
        return {"success": True, "name": name}

    async def update_session_model(self, session_id: str, model_id: str) -> dict[str, Any]:
        """Update model binding for one existing session."""
        session = await self._repository.get(session_id)
        if not session:
            return self._not_found()

        await self._repository.update(session_id, {"model_id": model_id})
        return {"success": True, "model_id": model_id}

    async def get_session_model(self, session_id: str) -> dict[str, Any]:
        """Return the active model id configured for the target session."""
        session = await self._repository.get(session_id)
        if not session:
            return self._not_found()

        return {"success": True, "model_id": session.get("model_id", self._default_model_id)}

    async def clear_chat(self, session_id: str) -> dict[str, Any]:
        """Clear persisted chat messages and in-memory conversation cache for the session."""
        session = await self._repository.get(session_id)
        if not session:
            return self._not_found()

        await self._repository.update(session_id, {"messages": [], "message_count": 0})
        try:
            await self._get_memory_manager().clear_session_messages(session_id)
        except Exception:
            pass
        return {"success": True}

    async def get_session_info(self, session_id: str) -> dict[str, Any]:
        """Return full session metadata payload by session id."""
        session = await self._repository.get(session_id)
        if not session:
            return self._not_found()

        return {"success": True, "session": session}

    @staticmethod
    def _not_found() -> dict[str, Any]:
        """Build the canonical not-found payload shared by session operations."""
        return {"success": False, "error": "会话不存在"}

    def _get_memory_manager(self) -> SessionMemoryManager:
        """Resolve the memory manager lazily so light operations avoid agent imports."""
        if self._memory_manager is None:
            if self._memory_manager_factory is None:
                raise RuntimeError("Session memory manager is not configured")
            self._memory_manager = self._memory_manager_factory()
        return self._memory_manager
