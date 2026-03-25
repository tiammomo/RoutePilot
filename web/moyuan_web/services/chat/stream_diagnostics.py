"""Diagnostics helpers for streamed chat runs."""

from __future__ import annotations

from typing import Any


class ChatStreamDiagnostics:
    """Build normalized diagnostics payloads persisted after streamed chat runs."""

    @staticmethod
    def public_artifact_contract(payload: Any) -> dict[str, Any] | None:
        """Normalize stored artifact payloads into the public contract shape."""
        from ...api.schemas import normalize_trip_plan_artifact

        normalized = normalize_trip_plan_artifact(payload)
        return normalized or None

    def build_success_diagnostics(self, state: Any) -> dict[str, Any]:
        """Build assistant diagnostics persisted for a successful stream run."""
        from ...observability import get_request_context

        request_context = get_request_context()
        return {
            "toolsUsed": state.tools_used,
            "verificationPassed": state.verification_passed,
            "staleResultCount": state.stale_result_count,
            "fallbackSteps": state.fallback_steps,
            "planId": state.plan_id,
            "executionStats": state.execution_stats,
            "artifact": self.public_artifact_contract(state.final_artifact),
            "subagentEvents": state.subagent_events,
            "runId": state.run_id,
            "requestId": request_context.get("request_id"),
            "traceId": request_context.get("trace_id"),
        }

    def build_failure_diagnostics(self, state: Any) -> dict[str, Any]:
        """Build assistant diagnostics persisted for interrupted stream runs."""
        from ...observability import get_request_context

        request_context = get_request_context()
        return {
            "artifact": self.public_artifact_contract(state.final_artifact),
            "subagentEvents": state.subagent_events,
            "runId": state.run_id,
            "requestId": request_context.get("request_id"),
            "traceId": request_context.get("trace_id"),
        }
