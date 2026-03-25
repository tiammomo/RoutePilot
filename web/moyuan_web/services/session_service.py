"""Compatibility facade for session lifecycle orchestration."""

from __future__ import annotations

from ..repositories.session_repository import SessionRepository
from .session import (
    DEFAULT_MODEL_ID,
    DEFAULT_SESSION_NAME,
    SessionLifecycleService,
    build_default_memory_manager,
    resolve_default_model_id,
)


class SessionService:
    """Expose the existing session-service API while delegating to smaller collaborators."""

    DEFAULT_SESSION_NAME = DEFAULT_SESSION_NAME
    DEFAULT_MODEL_ID = DEFAULT_MODEL_ID

    def __init__(self, repository: SessionRepository, memory_manager: object | None = None):
        self._repository = repository
        self._default_model_id = self._resolve_default_model_id()
        self._memory_manager = memory_manager
        self._lifecycle = SessionLifecycleService(
            repository,
            memory_manager=self._memory_manager,
            memory_manager_factory=build_default_memory_manager if memory_manager is None else None,
            default_model_id=self._default_model_id,
            default_session_name=self.DEFAULT_SESSION_NAME,
        )

    @classmethod
    def _resolve_default_model_id(cls) -> str:
        """Resolve default model id from config manager with fallback constant."""
        return resolve_default_model_id(default_model_id=cls.DEFAULT_MODEL_ID)

    async def create_session(self, name: str | None = None) -> dict[str, object]:
        """Create a new session record with normalized display name and default model."""
        return await self._lifecycle.create_session(name=name)

    async def list_sessions(self, include_empty: bool = False) -> dict[str, object]:
        """List sessions and include total count for API response payload."""
        return await self._lifecycle.list_sessions(include_empty=include_empty)

    async def delete_session(self, session_id: str) -> dict[str, object]:
        """Delete session data and associated memory snapshot when session exists."""
        return await self._lifecycle.delete_session(session_id)

    async def update_session_name(self, session_id: str, name: str) -> dict[str, object]:
        """Update session display name after existence validation."""
        return await self._lifecycle.update_session_name(session_id, name)

    async def update_session_model(self, session_id: str, model_id: str) -> dict[str, object]:
        """Update model binding for one existing session."""
        return await self._lifecycle.update_session_model(session_id, model_id)

    async def get_session_model(self, session_id: str) -> dict[str, object]:
        """Return active model id configured for the target session."""
        return await self._lifecycle.get_session_model(session_id)

    async def clear_chat(self, session_id: str) -> dict[str, object]:
        """Clear persisted chat messages and in-memory conversation cache for the session."""
        return await self._lifecycle.clear_chat(session_id)

    async def get_session_info(self, session_id: str) -> dict[str, object]:
        """Return full session metadata payload by session id."""
        return await self._lifecycle.get_session_info(session_id)
