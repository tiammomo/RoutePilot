"""Bridge legacy graph-builder entrypoints into the application-facing runtime."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional, Protocol

from langchain_core.runnables import Runnable
from langchain_core.tools import Tool

TOOL_RESULT_PREVIEW_LIMIT = 200


class LegacyRuntimeBridge(Protocol):
    """Describe the compatibility surface that still delegates to the legacy graph."""

    async def stream_with_memory(
        self,
        *,
        user_message: str,
        llm: Runnable,
        tools: list[Tool],
        session_id: str,
        memory_manager: Any,
        system_prompt: Optional[str],
        persist_memory: bool,
        run_id: Optional[str],
        chat_mode: Optional[str],
        routing_llm: Optional[Runnable],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield normalized runtime events backed by the legacy graph implementation."""

    def generate_plan_preview_with_memory(
        self,
        *,
        user_message: str,
        llm: Runnable,
        tools: list[Tool],
        session_id: str,
        memory_manager: Any,
        system_prompt: Optional[str],
        chat_mode: Optional[str],
        routing_llm: Optional[Runnable],
    ) -> dict[str, Any]:
        """Return one memory-aware plan preview from the legacy graph path."""

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return legacy graph tool-health diagnostics."""


class DefaultLegacyRuntimeBridge:
    """Lazy compatibility adapter around the existing graph.builder entrypoints."""

    async def stream_with_memory(
        self,
        *,
        user_message: str,
        llm: Runnable,
        tools: list[Tool],
        session_id: str,
        memory_manager: Any,
        system_prompt: Optional[str],
        persist_memory: bool,
        run_id: Optional[str],
        chat_mode: Optional[str],
        routing_llm: Optional[Runnable],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield runtime events from the legacy memory-aware streaming entrypoint."""
        from ..graph.builder import run_travel_agent_streaming_with_memory

        async for event in run_travel_agent_streaming_with_memory(
            user_message=user_message,
            llm=llm,
            tools=tools,
            session_id=session_id,
            memory_manager=memory_manager,
            system_prompt=system_prompt,
            persist_memory=persist_memory,
            run_id=run_id,
            chat_mode=chat_mode,
            routing_llm=routing_llm,
        ):
            yield event

    def generate_plan_preview_with_memory(
        self,
        *,
        user_message: str,
        llm: Runnable,
        tools: list[Tool],
        session_id: str,
        memory_manager: Any,
        system_prompt: Optional[str],
        chat_mode: Optional[str],
        routing_llm: Optional[Runnable],
    ) -> dict[str, Any]:
        """Return legacy graph plan preview data without exposing builder imports upstream."""
        from ..graph.builder import generate_plan_preview_with_memory

        return generate_plan_preview_with_memory(
            user_message=user_message,
            llm=llm,
            tools=tools,
            session_id=session_id,
            memory_manager=memory_manager,
            system_prompt=system_prompt,
            chat_mode=chat_mode,
            routing_llm=routing_llm,
        )

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return tool-health diagnostics from the legacy graph compatibility path."""
        from ..graph.builder import get_tool_health_diagnostics

        return get_tool_health_diagnostics()
