"""History and persistence helpers for chat orchestration."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ChatHistoryMixin:
    """Persistence-oriented methods for chat sessions and message history."""

    def _build_memory_context_messages(self, session_id: str) -> list[Any]:
        """Build baseline memory context messages for graph invocation."""
        if self._memory_manager is None:
            return []
        try:
            return self._memory_manager.build_context_messages(session_id)
        except Exception as exc:
            logger.warning("Failed to build memory context messages: %s", exc)
            return []

    def _build_relevant_memory_context_messages(self, session_id: str, user_message: str) -> list[Any]:
        """Build query-relevant memory context messages to reduce token footprint."""
        if self._memory_manager is None:
            return []
        try:
            return self._memory_manager.build_context_messages_for_query(session_id, user_message, max_messages=8)
        except Exception as exc:
            logger.warning("Failed to build relevant memory context messages: %s", exc)
            return []

    async def _build_history_messages(
        self,
        session_id: str,
        limit: int = 12,
        exclude_last_user_message: Optional[str] = None,
    ) -> list[Any]:
        """Convert persisted session chat history into model message objects."""
        from langchain_core.messages import AIMessage, HumanMessage

        session = await self._repository.get(session_id)
        if not session:
            return []

        history = session.get("messages", [])
        if exclude_last_user_message and history:
            last = history[-1]
            if last.get("role") == "user" and last.get("content") == exclude_last_user_message:
                history = history[:-1]
        history = history[-limit:]
        result: list[Any] = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "assistant":
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        return result

    async def _ensure_session(self, session_id: Optional[str]) -> str:
        """Resolve or create a session identifier before writing chat data."""
        normalized_session_id = session_id.strip() if session_id else None

        if normalized_session_id:
            session = await self._repository.get(normalized_session_id)
            if session:
                return normalized_session_id
            sid = normalized_session_id
        else:
            sid = str(uuid.uuid4())

        await self._repository.create(
            {
                "session_id": sid,
                "name": "新会话",
                "model_id": self._llm_adapter.config.get("model", "mimo-v2.5-pro") if self._llm_adapter else "mimo-v2.5-pro",
                "messages": [],
                "user_preferences": {},
            }
        )
        return sid

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        reasoning: Optional[str] = None,
        diagnostics: Optional[dict[str, Any]] = None,
        model_content: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist one chat message into repository and optionally sync memory profile."""
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "SESSION_NOT_FOUND"}

        messages = session.get("messages", [])
        entry: dict[str, Any] = {
            "role": role,
            "content": content,
            "reasoning": reasoning,
            "timestamp": self._get_timestamp(),
        }
        if diagnostics:
            entry["diagnostics"] = diagnostics
        if model_content:
            entry["model_content"] = model_content
        messages.append(entry)

        await self._repository.update(
            session_id,
            {
                "messages": messages,
                "message_count": len(messages),
            },
        )
        return {"success": True}

    async def _save_user_message(
        self,
        session_id: str,
        content: str,
        *,
        model_content: Optional[str] = None,
    ) -> dict[str, Any]:
        """Save a user message while remaining compatible with older test doubles."""
        try:
            return await self.save_message(
                session_id,
                "user",
                content,
                model_content=model_content,
            )
        except TypeError as exc:
            if "unexpected keyword argument 'model_content'" not in str(exc):
                raise
            return await self.save_message(session_id, "user", content)

    async def get_messages(self, session_id: str) -> dict[str, Any]:
        """Return persisted public messages for a session, excluding model-only prompt fields."""
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "SESSION_NOT_FOUND", "messages": []}

        public_messages: list[dict[str, Any]] = []
        for message in session.get("messages", []):
            if not isinstance(message, dict):
                continue
            public_messages.append(
                {
                    key: value
                    for key, value in message.items()
                    if key in {"role", "content", "reasoning", "timestamp", "diagnostics"}
                }
            )

        return {"success": True, "messages": public_messages}

    async def cleanup_expired_sessions(self, max_age_seconds: int = 86400) -> int:
        """Run repository cleanup for expired sessions and stale data."""
        return await self._repository.cleanup_expired(max_age_seconds)

    @staticmethod
    def _get_timestamp() -> str:
        """Return current timestamp string used by persisted message records."""
        return datetime.now().strftime("%H:%M:%S")

    async def _write_memory_user(self, session_id: str, message: str) -> bool:
        """Write user message into memory manager and swallow non-fatal memory errors."""
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "user", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write user memory: %s", exc)
            return False

    async def _write_memory_assistant(self, session_id: str, message: str) -> bool:
        """Write assistant answer into memory manager and swallow non-fatal memory errors."""
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "assistant", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write assistant memory: %s", exc)
            return False
