"""Planning subagent for itinerary synthesis and draft generation."""

from __future__ import annotations

from typing import Any, Optional

from ..artifacts import build_trip_plan_artifact_from_plan_preview
from .base import BaseSubagent


class PlanningSubagent(BaseSubagent):
    """Minimal planning subagent backed by the existing planner and artifact builders."""

    def artifact_patch_from_preview(self, preview: dict[str, Any]) -> dict[str, Any]:
        """Build a planning artifact patch from a plan preview payload."""
        artifact = build_trip_plan_artifact_from_plan_preview(
            preview,
            user_message="",
            session_id=str(preview.get("session_id") or "default"),
        )
        return {
            "itinerary": artifact.get("itinerary", {}),
            "metadata": {
                "planning_preview_available": True,
            },
        }

    def artifact_patch_from_done(
        self,
        done_event: dict[str, Any],
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> dict[str, Any]:
        """Build a planning artifact patch from the completed stream event."""
        _ = (session_id, chat_mode)
        plan_id = done_event.get("plan_id")
        return {
            "itinerary": {
                "plan_id": plan_id,
                "planId": plan_id,
                "explanation": user_message,
                "steps": [],
                "validation_status": "pass",
                "validationStatus": "pass",
                "validation_errors": [],
                "validationErrors": [],
            },
            "metadata": {
                "planning_subagent_completed": True,
            },
        }
