"""Session application service."""

from __future__ import annotations

from typing import Any, Dict

from ..repositories.session_repository import SessionRepository


class SessionService:
    """Business service for session lifecycle management."""

    DEFAULT_SESSION_NAME = "新会话"
    DEFAULT_MODEL_ID = "gpt-4o-mini"

    def __init__(self, repository: SessionRepository):
        self._repository = repository

    async def create_session(self, name: str | None = None) -> Dict[str, Any]:
        session_name = (name or self.DEFAULT_SESSION_NAME).strip() or self.DEFAULT_SESSION_NAME
        session_id = await self._repository.create({"name": session_name})
        return {"success": True, "session_id": session_id, "name": session_name}

    async def list_sessions(self, include_empty: bool = False) -> Dict[str, Any]:
        sessions = await self._repository.list_all(include_empty=include_empty)
        return {"success": True, "sessions": sessions, "total": len(sessions)}

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        deleted = await self._repository.delete(session_id)
        if deleted:
            return {"success": True}
        return {"success": False, "error": "会话不存在"}

    async def update_session_name(self, session_id: str, name: str) -> Dict[str, Any]:
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"name": name})
        return {"success": True, "name": name}

    async def update_session_model(self, session_id: str, model_id: str) -> Dict[str, Any]:
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"model_id": model_id})
        return {"success": True, "model_id": model_id}

    async def get_session_model(self, session_id: str) -> Dict[str, Any]:
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        return {"success": True, "model_id": session.get("model_id", self.DEFAULT_MODEL_ID)}

    async def clear_chat(self, session_id: str) -> Dict[str, Any]:
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"messages": [], "message_count": 0})
        return {"success": True}

    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        return {"success": True, "session": session}
