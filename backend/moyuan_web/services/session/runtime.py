"""Lazy runtime helpers and protocols for session services."""

from __future__ import annotations

from typing import Any, Callable, Protocol

DEFAULT_SESSION_NAME = "新会话"
DEFAULT_MODEL_ID = "mimo-v2.5-pro"


class SessionMemoryManager(Protocol):
    """Minimal memory-manager contract used by session services."""

    async def delete_session(self, session_id: str) -> Any:
        """Delete all memory artifacts associated with one session."""

    async def clear_session_messages(self, session_id: str) -> Any:
        """Clear turn-level conversation memory while keeping session profile state."""


MemoryManagerFactory = Callable[[], SessionMemoryManager]


def resolve_default_model_id(default_model_id: str = DEFAULT_MODEL_ID) -> str:
    """Resolve default model id from runtime config with a safe fallback."""
    try:
        from ...config.runtime import get_model_config_manager

        return get_model_config_manager().get_default_model_id()
    except Exception:
        return default_model_id


def build_default_memory_manager() -> SessionMemoryManager:
    """Construct the default memory manager lazily to avoid eager agent imports."""
    from agent.travel_agent.graph.memory_integration import get_agent_memory_manager

    return get_agent_memory_manager(max_history=10, summary_threshold=20)
