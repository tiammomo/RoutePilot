"""Finalization helpers for successful and failed chat stream runs."""

from __future__ import annotations

import logging
from typing import Any

from .stream_diagnostics import ChatStreamDiagnostics


class ChatStreamFinalizer:
    """Persist diagnostics and build terminal payloads for chat streams."""

    def __init__(
        self,
        *,
        service: Any,
        logger: logging.Logger,
        diagnostics: ChatStreamDiagnostics,
    ) -> None:
        """Store service hooks, logger, and diagnostics builder for finalization."""
        self._service = service
        self._logger = logger
        self._diagnostics = diagnostics

    async def finalize_success(
        self,
        state: Any,
        *,
        message: str,
        mode: str,
    ) -> list[dict[str, Any]]:
        """Persist the successful run and build terminal metadata payloads."""
        self._finalize_stream_state(state, mode)
        assistant_diagnostics = self._diagnostics.build_success_diagnostics(state)
        await self._persist_successful_stream(state, message=message, diagnostics=assistant_diagnostics)
        self._emit_success_stream_telemetry(state, mode=mode)
        return self._build_success_terminal_payloads(state)

    async def finalize_failure(
        self,
        state: Any,
        *,
        mode: str,
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Persist failure state and build terminal error payloads."""
        self._logger.exception("Chat stream failed: %s", error)

        self._service._record_run_metrics(
            intent=state.detected_intent or ("direct" if mode == "direct" else "unknown"),
            execution_stats=state.execution_stats,
            hard_error=True,
        )
        await self._persist_failed_stream(state)
        self._emit_failed_stream_telemetry(state, mode=mode, error=error)
        return self._build_failure_terminal_payloads(state, error=error)

    def _finalize_stream_state(self, state: Any, mode: str) -> None:
        """Complete derived fields before terminal metadata emission."""
        state.tools_used = list(dict.fromkeys(state.tools_used))
        stats_steps = list((state.execution_stats or {}).get("steps", []) or [])
        if state.fallback_steps <= 0:
            state.fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))
        if state.stale_result_count <= 0:
            state.stale_result_count = sum(1 for item in stats_steps if bool(item.get("is_stale", False)))
        if state.verification_passed is None:
            state.verification_passed = True if mode == "direct" else state.stale_result_count == 0

    async def _persist_successful_stream(
        self,
        state: Any,
        *,
        message: str,
        diagnostics: dict[str, Any],
    ) -> None:
        """Persist assistant output and memory side effects for successful runs."""
        resolved_sid = state.resolved_session_id()
        await self._service.save_message(
            resolved_sid,
            "assistant",
            state.answer_content,
            state.reasoning_content or None,
            diagnostics=diagnostics,
        )
        if not await self._service._write_memory_assistant(resolved_sid, state.answer_content):
            self._logger.warning("Failed to write assistant memory for session=%s", resolved_sid)
        if not state.memory_user_written:
            await self._service._write_memory_user(resolved_sid, message)

    def _emit_success_stream_telemetry(self, state: Any, *, mode: str) -> None:
        """Emit success metrics and structured logs after persistence succeeds."""
        from ...observability import emit_structured_log, record_chat_stream

        resolved_sid = state.resolved_session_id()
        self._service._record_run_metrics(
            intent=state.detected_intent or ("direct" if mode == "direct" else "unknown"),
            execution_stats=state.execution_stats,
            hard_error=False,
        )
        self._service._emit_failure_telemetry(
            session_id=resolved_sid,
            run_id=state.run_id,
            mode=mode,
            execution_stats=state.execution_stats,
            answer=state.answer_content,
        )
        record_chat_stream(mode, "success")
        emit_structured_log(
            self._logger,
            "chat_stream_completed",
            session_id=resolved_sid,
            mode=mode,
            run_id=state.run_id,
            tools_used=state.tools_used,
            verification_passed=state.verification_passed,
            stale_result_count=state.stale_result_count,
            fallback_steps=state.fallback_steps,
        )

    def _build_success_terminal_payloads(self, state: Any) -> list[dict[str, Any]]:
        """Build terminal metadata and done events for a successful stream run."""
        return [
            {
                "type": "metadata",
                "run_id": state.run_id,
                "total_steps": len(state.tools_used),
                "tools_used": state.tools_used,
                "has_reasoning": bool(state.reasoning_content),
                "reasoning_length": len(state.reasoning_content),
                "answer_length": len(state.answer_content),
                "plan_id": state.plan_id,
                "execution_stats": state.execution_stats,
                "verification_passed": state.verification_passed,
                "stale_result_count": state.stale_result_count,
                "fallback_steps": state.fallback_steps,
                "failure_clusters": self._service._extract_failure_clusters(state.execution_stats),
                "artifact": state.final_artifact,
            },
            {
                "type": "done",
                "run_id": state.run_id,
                "artifact": state.final_artifact,
            },
        ]

    async def _persist_failed_stream(self, state: Any) -> None:
        """Persist interrupted output and write failure memory breadcrumbs."""
        resolved_sid = state.resolved_session_id()
        interrupted_answer = state.answer_content or "[INTERRUPTED]"

        try:
            await self._service.save_message(
                resolved_sid,
                "assistant",
                interrupted_answer,
                state.reasoning_content or "stream interrupted",
                diagnostics=self._diagnostics.build_failure_diagnostics(state),
            )
        except Exception:
            pass

        await self._service._write_memory_assistant(resolved_sid, f"[INTERRUPTED]{state.answer_content}")

    def _emit_failed_stream_telemetry(
        self,
        state: Any,
        *,
        mode: str,
        error: Exception,
    ) -> None:
        """Emit error metrics and structured logs for interrupted stream runs."""
        from ...observability import emit_structured_log, record_chat_stream

        resolved_sid = state.resolved_session_id()
        self._service._emit_failure_telemetry(
            session_id=resolved_sid,
            run_id=state.run_id,
            mode=mode,
            execution_stats=state.execution_stats,
            answer=state.answer_content,
            hard_error=str(error),
        )
        record_chat_stream(mode, "error")
        emit_structured_log(
            self._logger,
            "chat_stream_failed",
            level=logging.ERROR,
            session_id=resolved_sid,
            mode=mode,
            run_id=state.run_id,
            error=str(error),
        )

    @staticmethod
    def _build_failure_terminal_payloads(
        state: Any,
        *,
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Build terminal error and done events for interrupted runs."""
        return [
            {"type": "error", "content": str(error), "run_id": state.run_id},
            {"type": "done", "run_id": state.run_id},
        ]
