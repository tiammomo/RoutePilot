"""Session application service."""

from __future__ import annotations

from typing import Any, Dict

from ..config.runtime import get_model_config_manager
from ..repositories.session_repository import SessionRepository
from agent.travel_agent.graph.memory_integration import AgentMemoryManager, get_agent_memory_manager


class SessionService:
    """Business service for session lifecycle management."""

    DEFAULT_SESSION_NAME = "新会话"
    DEFAULT_MODEL_ID = "gpt-4o-mini"

    def __init__(self, repository: SessionRepository, memory_manager: AgentMemoryManager | None = None):
        """Initialize session lifecycle service with repository and memory manager dependencies.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            repository: Session repository abstraction used for persistence operations.
            memory_manager: Memory manager used to keep cross-turn profile and summary data in sync.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self._repository = repository
        self._default_model_id = self._resolve_default_model_id()
        self._memory_manager = memory_manager or get_agent_memory_manager(max_history=10, summary_threshold=20)

    @classmethod
    def _resolve_default_model_id(cls) -> str:
        """Resolve default model ID from config manager with fallback constant.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        try:
            return get_model_config_manager().get_default_model_id()
        except Exception:
            return cls.DEFAULT_MODEL_ID

    async def create_session(self, name: str | None = None) -> Dict[str, Any]:
        """Create a new session record with normalized display name and default model.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            name: Session display name provided by API caller.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session_name = (name or self.DEFAULT_SESSION_NAME).strip() or self.DEFAULT_SESSION_NAME
        session_id = await self._repository.create(
            {
                "name": session_name,
                "model_id": self._default_model_id,
            }
        )
        return {"success": True, "session_id": session_id, "name": session_name}

    async def list_sessions(self, include_empty: bool = False) -> Dict[str, Any]:
        """List sessions and include total count for API response payload.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            include_empty: Whether empty sessions should be included in listing results.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        sessions = await self._repository.list_all(include_empty=include_empty)
        return {"success": True, "sessions": sessions, "total": len(sessions)}

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete session data and associated memory snapshot when session exists.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        deleted = await self._repository.delete(session_id)
        if deleted:
            try:
                await self._memory_manager.delete_session(session_id)
            except Exception:
                pass
            return {"success": True}
        return {"success": False, "error": "会话不存在"}

    async def update_session_name(self, session_id: str, name: str) -> Dict[str, Any]:
        """Update session display name after existence validation.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            name: Session display name provided by API caller.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"name": name})
        return {"success": True, "name": name}

    async def update_session_model(self, session_id: str, model_id: str) -> Dict[str, Any]:
        """Update model binding for one existing session.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            model_id: Model identifier to bind with target session.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"model_id": model_id})
        return {"success": True, "model_id": model_id}

    async def get_session_model(self, session_id: str) -> Dict[str, Any]:
        """Return active model ID configured for the target session.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        return {"success": True, "model_id": session.get("model_id", self._default_model_id)}

    async def clear_chat(self, session_id: str) -> Dict[str, Any]:
        """Clear persisted chat messages and in-memory conversation cache for the session.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        await self._repository.update(session_id, {"messages": [], "message_count": 0})
        try:
            await self._memory_manager.clear_session_messages(session_id)
        except Exception:
            pass
        return {"success": True}

    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Return full session metadata payload by session ID.
        
        Purpose:
            Describe chat-service behavior, emitted events, and persistence side effects for maintainers.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        return {"success": True, "session": session}
