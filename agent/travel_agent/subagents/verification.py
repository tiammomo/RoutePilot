"""Verification subagent for quality and consistency checks."""

from __future__ import annotations

from typing import Any, Optional

from .base import BaseSubagent


class VerificationSubagent(BaseSubagent):
    """Minimal verification subagent backed by existing verify/self-check output."""

    def artifact_patch_from_done(
        self,
        done_event: dict[str, Any],
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> dict[str, object]:
        """Build a verification artifact patch from the completed stream event."""
        _ = (user_message, session_id, chat_mode)
        passed = done_event.get("verification_passed")
        stale = int(done_event.get("stale_result_count", 0) or 0)
        fallback_steps = int(done_event.get("fallback_steps", 0) or 0)
        summary = "Verification completed."
        if passed is False:
            summary = "Verification found issues and may require follow-up."
        elif stale > 0:
            summary = "Verification completed with stale results noted."
        return {
            "verification": {
                "passed": passed,
                "should_retry": False,
                "shouldRetry": False,
                "issues": [],
                "refresh_targets": [],
                "refreshTargets": [],
                "summary": summary,
            },
            "budget": {
                "fallback_steps": fallback_steps,
                "fallbackSteps": fallback_steps,
                "stale_result_count": stale,
                "staleResultCount": stale,
            },
            "metadata": {
                "verification_subagent_completed": True,
            },
        }
