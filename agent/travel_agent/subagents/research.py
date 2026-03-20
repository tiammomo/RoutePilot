"""Research subagent for collecting destination evidence."""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseSubagent


class ResearchSubagent(BaseSubagent):
    """Minimal research subagent backed by current travel tools and skills."""

    def artifact_patch_from_done(
        self,
        done_event: dict[str, Any],
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> dict[str, Any]:
        """Build a research artifact patch from the completed stream event."""
        _ = (session_id, chat_mode)
        tool_names = [name for name in done_event.get("tools_used", []) if name in self.tool_names()]
        if not tool_names:
            return {}
        intent = str(done_event.get("intent") or "general")
        return {
            "research": {
                "summary": f"Collected {len(tool_names)} research signal(s) for intent={intent}.",
                "source_tools": tool_names,
                "sourceTools": tool_names,
                "destinations": [],
                "evidence": [
                    {
                        "tool": tool_name,
                        "status": "collected",
                        "query": user_message,
                    }
                    for tool_name in tool_names
                ],
            },
            "metadata": {
                "research_subagent_completed": True,
            },
        }
