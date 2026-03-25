"""Streaming orchestration helpers for chat service."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Iterable, Optional

from ...bootstrap import ensure_project_paths
from .plan_preview_coordinator import ChatPlanPreviewCoordinator
from .shared import merge_artifact_payload

ensure_project_paths()

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _StreamRunState:
    """Mutable state accumulated during one streamed chat run."""

    requested_session_id: Optional[str]
    session_id: Optional[str] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    answer_content: str = ""
    reasoning_content: str = ""
    tools_used: list[str] = field(default_factory=list)
    plan_id: Optional[str] = None
    detected_intent: Optional[str] = None
    execution_stats: dict[str, Any] = field(default_factory=dict)
    verification_passed: Optional[bool] = None
    stale_result_count: int = 0
    fallback_steps: int = 0
    final_artifact: dict[str, Any] = field(default_factory=dict)
    subagent_events: list[dict[str, Any]] = field(default_factory=list)
    answer_started: bool = False
    reasoning_ended: bool = False
    memory_user_written: bool = False

    def resolved_session_id(self) -> str:
        """Return the best available session identifier for persistence and logging."""
        return self.session_id or self.requested_session_id or "unknown"


class ChatStreamMixin:
    """Streaming and SSE serialization methods for chat orchestration."""

    async def stream_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode: str = "react",
        display_message: Optional[str] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Run one chat request and stream normalized SSE events."""
        from ...observability import bind_request_context, emit_structured_log, reset_request_context

        context_tokens = bind_request_context(request_id or str(uuid.uuid4()), trace_id)
        mode = self._normalize_mode(mode)
        state = _StreamRunState(requested_session_id=session_id)

        try:
            await self.initialize()
            state.session_id = await self._ensure_session(session_id)
            emit_structured_log(
                logger,
                "chat_stream_started",
                session_id=state.session_id,
                mode=mode,
                run_id=state.run_id,
            )

            yield self._serialize_sse_payload(
                {"type": "session_id", "session_id": state.session_id, "run_id": state.run_id}
            )
            await self._save_user_message(
                state.session_id,
                display_message or message,
                model_content=message,
            )
            state.memory_user_written = await self._write_memory_user(state.session_id, message)

            async for envelope in self._stream_normalized_sse_events(state, message=message, mode=mode):
                yield envelope

            for envelope in self._serialize_sse_payloads(
                await self._finalize_stream_run(state, message=message, mode=mode)
            ):
                yield envelope

        except Exception as exc:
            for envelope in self._serialize_sse_payloads(
                await self._finalize_stream_failure(state, mode=mode, error=exc)
            ):
                yield envelope
        finally:
            reset_request_context(context_tokens)

    async def _stream_normalized_sse_events(
        self,
        state: _StreamRunState,
        *,
        message: str,
        mode: str,
    ) -> AsyncGenerator[str, None]:
        """Serialize normalized runtime payloads into SSE envelopes."""
        async for payload in self._normalize_stream_events(state, message=message, mode=mode):
            yield self._serialize_sse_payload(payload)

    async def _normalize_stream_events(
        self,
        state: _StreamRunState,
        *,
        message: str,
        mode: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Normalize internal runtime output into public stream payloads."""
        if mode == "direct":
            async for payload in self._normalize_direct_stream_events(state, message=message):
                yield payload
            return

        yield {"type": "reasoning_start"}

        if mode == "plan":
            for payload in await self._normalize_plan_preview_events(state, message=message):
                yield payload

        async for event in self._stream_agent_events(
            state.resolved_session_id(),
            message,
            mode=mode,
            run_id=state.run_id,
        ):
            for payload in self._normalize_runtime_event(state, event):
                yield payload

        for payload in self._ensure_answer_section_started(state):
            yield payload

    async def _normalize_direct_stream_events(
        self,
        state: _StreamRunState,
        *,
        message: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Normalize the direct LLM streaming branch into standard payloads."""
        yield {"type": "reasoning_start"}
        yield {"type": "reasoning_end"}
        state.reasoning_ended = True
        yield {"type": "answer_start"}
        state.answer_started = True

        async for token in self._stream_direct_response(state.resolved_session_id(), message):
            state.answer_content += token
            yield {"type": "chunk", "content": token}

    async def _normalize_plan_preview_events(
        self,
        state: _StreamRunState,
        *,
        message: str,
    ) -> list[dict[str, Any]]:
        """Normalize optional plan-preview output for plan mode."""
        return await self._build_plan_preview_coordinator().normalize(
            state,
            session_id=state.resolved_session_id(),
            message=message,
        )

    def _build_plan_preview_coordinator(self) -> ChatPlanPreviewCoordinator:
        """Build the plan preview collaborator used by streamed plan mode."""
        return ChatPlanPreviewCoordinator(
            generate_plan_preview=self._generate_plan_preview,
            get_timestamp=self._get_timestamp,
            logger=logger,
        )

    def _normalize_runtime_event(
        self,
        state: _StreamRunState,
        event: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Normalize one runtime event and update accumulated stream state."""
        for handler in (
            self._normalize_reasoning_runtime_event,
            self._normalize_subagent_runtime_event,
            self._normalize_tool_runtime_event,
            self._normalize_answer_runtime_event,
        ):
            payloads = handler(state, event)
            if payloads is not None:
                return payloads

        return []

    def _normalize_reasoning_runtime_event(
        self,
        state: _StreamRunState,
        event: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        """Normalize reasoning and stage events produced during runtime execution."""
        event_type = event.get("type")
        if event_type == "reasoning":
            content = event.get("content", "")
            state.reasoning_content += content
            return [{"type": "reasoning_chunk", "content": content}]
        if event_type == "stage":
            return [
                {
                    "type": "stage",
                    "stage": event.get("stage"),
                    "label": event.get("label"),
                    "progress": event.get("progress"),
                    "subagent": event.get("subagent"),
                }
            ]
        return None

    def _normalize_subagent_runtime_event(
        self,
        state: _StreamRunState,
        event: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        """Normalize subagent lifecycle and artifact patch events."""
        event_type = event.get("type")
        if event_type == "subagent_start":
            state.subagent_events.append(
                {
                    "subagent": event.get("subagent"),
                    "description": event.get("description"),
                    "skills": event.get("skills", []),
                    "toolNames": event.get("tool_names", []),
                    "sequence": event.get("sequence"),
                    "trigger": event.get("trigger"),
                    "timestamp": self._get_timestamp(),
                }
            )
            return [
                {
                    "type": "subagent_start",
                    "subagent": event.get("subagent"),
                    "description": event.get("description"),
                    "skills": event.get("skills", []),
                    "tool_names": event.get("tool_names", []),
                    "sequence": event.get("sequence"),
                    "trigger": event.get("trigger"),
                }
            ]
        if event_type == "subagent_end":
            state.subagent_events.append(
                {
                    "subagent": event.get("subagent"),
                    "sequence": event.get("sequence"),
                    "status": event.get("status"),
                    "summary": event.get("summary"),
                    "timestamp": self._get_timestamp(),
                }
            )
            return [
                {
                    "type": "subagent_end",
                    "subagent": event.get("subagent"),
                    "sequence": event.get("sequence"),
                    "status": event.get("status"),
                    "summary": event.get("summary"),
                }
            ]
        if event_type == "artifact_patch":
            state.final_artifact = merge_artifact_payload(
                state.final_artifact,
                event.get("artifact_patch") if isinstance(event.get("artifact_patch"), dict) else {},
            )
            return [
                {
                    "type": "artifact_patch",
                    "subagent": event.get("subagent"),
                    "artifact_patch": event.get("artifact_patch", {}),
                }
            ]
        return None

    def _normalize_tool_runtime_event(
        self,
        state: _StreamRunState,
        event: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        """Normalize tool lifecycle events and update used-tool tracking."""
        event_type = event.get("type")
        if event_type == "tool_start":
            tool_name = event.get("tool", "")
            if tool_name:
                state.tools_used.append(tool_name)
            return [
                {
                    "type": "tool_start",
                    "tool": tool_name,
                    "subagent": event.get("subagent"),
                }
            ]
        if event_type == "tool_end":
            return [
                {
                    "type": "tool_end",
                    "tool": event.get("tool", ""),
                    "result": event.get("result", ""),
                    "subagent": event.get("subagent"),
                }
            ]
        return None

    def _normalize_answer_runtime_event(
        self,
        state: _StreamRunState,
        event: dict[str, Any],
    ) -> Optional[list[dict[str, Any]]]:
        """Normalize answer token flow and terminal runtime updates."""
        event_type = event.get("type")
        if event_type == "chunk":
            payloads = self._ensure_answer_section_started(state)
            content = event.get("content", "")
            if content:
                state.answer_content += content
                payloads.append({"type": "chunk", "content": content})
            return payloads
        if event_type == "done":
            self._apply_done_event(state, event)
            return []
        return None

    def _apply_done_event(self, state: _StreamRunState, event: dict[str, Any]) -> None:
        """Merge terminal runtime event data into the accumulated stream state."""
        state.answer_content = event.get("answer", state.answer_content)
        state.plan_id = event.get("plan_id") or state.plan_id
        state.detected_intent = event.get("intent") or state.detected_intent
        state.execution_stats = event.get("execution_stats") or state.execution_stats

        if event.get("verification_passed") is not None:
            state.verification_passed = bool(event.get("verification_passed"))

        if event.get("stale_result_count") is not None:
            try:
                state.stale_result_count = int(event.get("stale_result_count") or 0)
            except Exception:
                state.stale_result_count = 0

        if event.get("fallback_steps") is not None:
            try:
                state.fallback_steps = int(event.get("fallback_steps") or 0)
            except Exception:
                state.fallback_steps = 0

        if isinstance(event.get("artifact"), dict):
            state.final_artifact = merge_artifact_payload(state.final_artifact, event.get("artifact"))

        stream_tools = event.get("tools_used", [])
        if stream_tools:
            state.tools_used.extend([tool for tool in stream_tools if tool])

    def _ensure_answer_section_started(self, state: _StreamRunState) -> list[dict[str, Any]]:
        """Emit missing reasoning/answer boundary events before answer tokens flow."""
        payloads: list[dict[str, Any]] = []
        if not state.reasoning_ended:
            payloads.append({"type": "reasoning_end"})
            state.reasoning_ended = True
        if not state.answer_started:
            payloads.append({"type": "answer_start"})
            state.answer_started = True
        return payloads

    async def _finalize_stream_run(
        self,
        state: _StreamRunState,
        *,
        message: str,
        mode: str,
    ) -> list[dict[str, Any]]:
        """Persist the successful run and build terminal metadata payloads."""
        self._finalize_stream_state(state, mode)
        assistant_diagnostics = self._build_success_diagnostics(state)
        await self._persist_successful_stream(state, message=message, diagnostics=assistant_diagnostics)
        self._emit_success_stream_telemetry(state, mode=mode)
        return self._build_success_terminal_payloads(state)

    async def _finalize_stream_failure(
        self,
        state: _StreamRunState,
        *,
        mode: str,
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Persist failure state and build terminal error payloads."""
        logger.exception("Chat stream failed: %s", error)

        self._record_run_metrics(
            intent=state.detected_intent or ("direct" if mode == "direct" else "unknown"),
            execution_stats=state.execution_stats,
            hard_error=True,
        )
        await self._persist_failed_stream(state)
        self._emit_failed_stream_telemetry(state, mode=mode, error=error)
        return self._build_failure_terminal_payloads(state, error=error)

    def _finalize_stream_state(self, state: _StreamRunState, mode: str) -> None:
        """Complete derived fields before terminal metadata emission."""
        state.tools_used = list(dict.fromkeys(state.tools_used))
        stats_steps = list((state.execution_stats or {}).get("steps", []) or [])
        if state.fallback_steps <= 0:
            state.fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))
        if state.stale_result_count <= 0:
            state.stale_result_count = sum(1 for item in stats_steps if bool(item.get("is_stale", False)))
        if state.verification_passed is None:
            state.verification_passed = True if mode == "direct" else state.stale_result_count == 0

    def _serialize_sse_payload(self, payload: dict[str, Any]) -> str:
        """Serialize one normalized payload into an SSE envelope."""
        return self._sse(payload)

    def _serialize_sse_payloads(self, payloads: Iterable[dict[str, Any]]) -> list[str]:
        """Serialize a batch of normalized payloads into SSE envelopes."""
        return [self._serialize_sse_payload(payload) for payload in payloads]

    def _build_success_diagnostics(self, state: _StreamRunState) -> dict[str, Any]:
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
            "artifact": state.final_artifact or None,
            "subagentEvents": state.subagent_events,
            "runId": state.run_id,
            "requestId": request_context.get("request_id"),
            "traceId": request_context.get("trace_id"),
        }

    async def _persist_successful_stream(
        self,
        state: _StreamRunState,
        *,
        message: str,
        diagnostics: dict[str, Any],
    ) -> None:
        """Persist assistant output and memory side effects for successful runs."""
        resolved_sid = state.resolved_session_id()
        await self.save_message(
            resolved_sid,
            "assistant",
            state.answer_content,
            state.reasoning_content or None,
            diagnostics=diagnostics,
        )
        if not await self._write_memory_assistant(resolved_sid, state.answer_content):
            logger.warning("Failed to write assistant memory for session=%s", resolved_sid)
        if not state.memory_user_written:
            await self._write_memory_user(resolved_sid, message)

    def _emit_success_stream_telemetry(self, state: _StreamRunState, *, mode: str) -> None:
        """Emit success metrics and structured logs after persistence succeeds."""
        from ...observability import emit_structured_log, record_chat_stream

        resolved_sid = state.resolved_session_id()
        self._record_run_metrics(
            intent=state.detected_intent or ("direct" if mode == "direct" else "unknown"),
            execution_stats=state.execution_stats,
            hard_error=False,
        )
        self._emit_failure_telemetry(
            session_id=resolved_sid,
            run_id=state.run_id,
            mode=mode,
            execution_stats=state.execution_stats,
            answer=state.answer_content,
        )
        record_chat_stream(mode, "success")
        emit_structured_log(
            logger,
            "chat_stream_completed",
            session_id=resolved_sid,
            mode=mode,
            run_id=state.run_id,
            tools_used=state.tools_used,
            verification_passed=state.verification_passed,
            stale_result_count=state.stale_result_count,
            fallback_steps=state.fallback_steps,
        )

    def _build_success_terminal_payloads(self, state: _StreamRunState) -> list[dict[str, Any]]:
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
                "failure_clusters": self._extract_failure_clusters(state.execution_stats),
                "artifact": state.final_artifact,
            },
            {
                "type": "done",
                "run_id": state.run_id,
                "artifact": state.final_artifact,
            },
        ]

    def _build_failure_diagnostics(self, state: _StreamRunState) -> dict[str, Any]:
        """Build assistant diagnostics persisted for interrupted stream runs."""
        from ...observability import get_request_context

        request_context = get_request_context()
        return {
            "artifact": state.final_artifact or None,
            "subagentEvents": state.subagent_events,
            "runId": state.run_id,
            "requestId": request_context.get("request_id"),
            "traceId": request_context.get("trace_id"),
        }

    async def _persist_failed_stream(self, state: _StreamRunState) -> None:
        """Persist interrupted output and write failure memory breadcrumbs."""
        resolved_sid = state.resolved_session_id()
        interrupted_answer = state.answer_content or "[INTERRUPTED]"

        try:
            await self.save_message(
                resolved_sid,
                "assistant",
                interrupted_answer,
                state.reasoning_content or "stream interrupted",
                diagnostics=self._build_failure_diagnostics(state),
            )
        except Exception:
            pass

        await self._write_memory_assistant(resolved_sid, f"[INTERRUPTED]{state.answer_content}")

    def _emit_failed_stream_telemetry(
        self,
        state: _StreamRunState,
        *,
        mode: str,
        error: Exception,
    ) -> None:
        """Emit error metrics and structured logs for interrupted stream runs."""
        from ...observability import emit_structured_log, record_chat_stream

        resolved_sid = state.resolved_session_id()
        self._emit_failure_telemetry(
            session_id=resolved_sid,
            run_id=state.run_id,
            mode=mode,
            execution_stats=state.execution_stats,
            answer=state.answer_content,
            hard_error=str(error),
        )
        record_chat_stream(mode, "error")
        emit_structured_log(
            logger,
            "chat_stream_failed",
            level=logging.ERROR,
            session_id=resolved_sid,
            mode=mode,
            run_id=state.run_id,
            error=str(error),
        )

    def _build_failure_terminal_payloads(
        self,
        state: _StreamRunState,
        *,
        error: Exception,
    ) -> list[dict[str, Any]]:
        """Build terminal error and done events for interrupted runs."""
        return [
            {"type": "error", "content": str(error), "run_id": state.run_id},
            {"type": "done", "run_id": state.run_id},
        ]

    async def _stream_direct_response(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
        """Stream direct LLM output tokens when mode bypasses tool orchestration."""
        from langchain_core.messages import HumanMessage, SystemMessage
        from agent.travel_agent.graph import TRAVEL_AGENT_SYSTEM_PROMPT

        history = self._build_relevant_memory_context_messages(session_id, message)
        if not history:
            history = await self._build_history_messages(session_id, exclude_last_user_message=message)
        payload: list[Any] = [SystemMessage(content=TRAVEL_AGENT_SYSTEM_PROMPT)]
        payload.extend(history)
        payload.append(HumanMessage(content=message))

        async for chunk in self._llm.astream(payload):
            token = self._extract_stream_text(chunk)
            if token:
                yield token

    @staticmethod
    def _extract_stream_text(chunk: Any) -> str:
        """Extract text token from heterogeneous streaming chunk payloads."""
        content = getattr(chunk, "content", chunk)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                return text
        return str(content)

    async def _stream_agent_events(
        self,
        session_id: str,
        message: str,
        mode: str = "react",
        run_id: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Bridge graph streaming events into service-level normalized event dictionaries."""
        from agent.travel_agent.runtime import TOOL_RESULT_PREVIEW_LIMIT

        if self._agent_runtime is None:
            raise RuntimeError("Agent runtime is not initialized")

        async for event in self._agent_runtime.stream_with_memory(
            user_message=message,
            session_id=session_id,
            persist_memory=False,
            run_id=run_id,
            chat_mode=mode,
        ):
            if event.get("type") == "tool_end":
                event["result"] = str(event.get("result", ""))[:TOOL_RESULT_PREVIEW_LIMIT]
            yield event

    def _generate_plan_preview(self, session_id: str, message: str) -> dict[str, Any]:
        """Generate plan preview payload shown before full execution in plan mode."""
        if self._agent_runtime is None:
            raise RuntimeError("Agent runtime is not initialized")

        return self._agent_runtime.generate_plan_preview_with_memory(
            user_message=message,
            session_id=session_id,
            chat_mode="plan",
        )

    @staticmethod
    def _normalize_mode(mode: Optional[str]) -> str:
        """Normalize requested mode and fall back to safe default when invalid."""
        if not mode:
            return "react"
        mode = mode.strip().lower()
        valid_modes = {"direct", "react", "plan"}
        return mode if mode in valid_modes else "react"

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        """Serialize one SSE envelope line from a structured payload object."""
        from ...observability import get_request_context, record_sse_event

        context = get_request_context()
        if context.get("request_id") and "request_id" not in payload:
            payload["request_id"] = context["request_id"]
        if context.get("trace_id") and "trace_id" not in payload:
            payload["trace_id"] = context["trace_id"]
        record_sse_event(str(payload.get("type", "unknown")))
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
