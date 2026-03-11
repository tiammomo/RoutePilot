"""Chat orchestration service for SSE streaming, memory sync, and health metrics."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..repositories.session_repository import SessionRepository
from ..bootstrap import ensure_project_paths
from ..config.runtime import get_llm_config_path

ensure_project_paths()

from agent.travel_agent.llm.langchain_adapter import create_from_yaml_config
from agent.travel_agent.tools.travel_tools import get_travel_tools
from agent.travel_agent.graph import TRAVEL_AGENT_SYSTEM_PROMPT
from agent.travel_agent.graph.builder import (
    TOOL_RESULT_PREVIEW_LIMIT,
    generate_plan_preview_with_memory,
    get_tool_health_diagnostics,
    run_travel_agent_streaming_with_memory,
)
from agent.travel_agent.graph.memory_integration import get_agent_memory_manager

logger = logging.getLogger(__name__)


class ChatService:
    """Application service for end-to-end chat orchestration."""

    VALID_MODES = {"direct", "react", "plan"}
    DEFAULT_HEALTH_WINDOW_MINUTES = 60
    DEFAULT_SLO_THRESHOLDS = {
        "timeout_rate": 0.1,
        "failure_rate": 0.2,
        "fallback_rate": 0.5,
    }

    def __init__(self, repository: SessionRepository):
        """Initialize chat orchestration dependencies, runtime thresholds, and health-metric buffers.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            repository: Session repository abstraction used for persistence operations.
        
        Returns:
            Any: Result value produced by this method.
        """
        self._repository = repository
        self._init_lock = asyncio.Lock()
        self._initialized = False

        self._llm_adapter = None
        self._llm = None
        self._router_llm = None
        self._tools = None
        self._memory_manager = None
        self._health_window_minutes = self._parse_int_env(
            "AGENT_HEALTH_WINDOW_MINUTES",
            self.DEFAULT_HEALTH_WINDOW_MINUTES,
            minimum=5,
        )
        self._slo_thresholds = {
            "timeout_rate": self._parse_float_env(
                "AGENT_SLO_TIMEOUT_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["timeout_rate"],
            ),
            "failure_rate": self._parse_float_env(
                "AGENT_SLO_FAILURE_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["failure_rate"],
            ),
            "fallback_rate": self._parse_float_env(
                "AGENT_SLO_FALLBACK_RATE_THRESHOLD",
                self.DEFAULT_SLO_THRESHOLDS["fallback_rate"],
            ),
        }
        self._health_metrics_lock = Lock()
        self._health_metrics: deque[dict[str, Any]] = deque()

    async def initialize(self) -> None:
        """Lazily initialize LLM adapter, router model, tool registry, and memory manager.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            None: Result value produced by this method.
        """
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            config_path = get_llm_config_path()
            self._llm_adapter = create_from_yaml_config(config_path)
            self._llm = self._llm_adapter.chat_model
            router_cfg = os.getenv("AGENT_ROUTER_LLM_CONFIG", "").strip()
            if router_cfg:
                try:
                    router_adapter = create_from_yaml_config(router_cfg)
                    self._router_llm = router_adapter.chat_model
                except Exception as exc:
                    logger.warning("Failed to initialize router llm from %s: %s", router_cfg, exc)
                    self._router_llm = self._llm
            else:
                self._router_llm = self._llm
            self._tools = get_travel_tools()
            self._memory_manager = get_agent_memory_manager(
                max_history=10,
                summary_threshold=20,
            )
            self._initialized = True
            logger.info("Chat runtime initialized with model=%s tools=%d", self._llm_adapter.config.get("name"), len(self._tools))

    async def health_status(self) -> dict[str, Any]:
        """Return lightweight runtime readiness status used by health endpoints.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        return {
            "initialized": self._initialized,
            "llm_adapter": self._llm_adapter is not None,
            "tools_count": len(self._tools) if self._tools else 0,
            "memory_enabled": self._memory_manager is not None,
        }

    async def tools_health_status(self) -> dict[str, Any]:
        """Return detailed tool-health diagnostics with SLO counters and circuit states.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        status = await self.health_status()
        diagnostics = get_tool_health_diagnostics()
        health_metrics = self._build_health_metrics_snapshot()
        return {
            "status": "ok" if status.get("initialized") else "not initialized",
            "initialized": status.get("initialized", False),
            "configured_tools_count": status.get("tools_count", 0),
            "circuit_open_count": diagnostics.get("open_circuit_count", 0),
            "slo": health_metrics.get("slo", {}),
            "intent_aggregate": health_metrics.get("intent_aggregate", {}),
            "window_minutes": self._health_window_minutes,
            "diagnostics": diagnostics,
        }

    async def tools_intents_health_status(self) -> dict[str, Any]:
        """Return intent-level aggregate health metrics for monitoring dashboards.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        status = await self.health_status()
        health_metrics = self._build_health_metrics_snapshot()
        slo = health_metrics.get("slo", {})
        return {
            "status": "ok" if status.get("initialized") else "not initialized",
            "window_minutes": self._health_window_minutes,
            "total_requests": int(slo.get("total_requests", 0) or 0),
            "intent_aggregate": health_metrics.get("intent_aggregate", {}),
        }

    async def stream_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode: str = "react",
    ) -> AsyncGenerator[str, None]:
        """Run one chat request and stream normalized SSE events (reasoning/chunk/stage/metadata).
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            message: User message text for this chat run.
            session_id: Session identifier used to isolate chat and memory state.
            mode: Requested chat mode (direct/react/plan).
        
        Returns:
            AsyncGenerator[str, None]: Streamed SSE/event payload sequence.
        """
        await self.initialize()

        mode = self._normalize_mode(mode)
        sid = await self._ensure_session(session_id)
        run_id = str(uuid.uuid4())

        yield self._sse({"type": "session_id", "session_id": sid, "run_id": run_id})
        await self.save_message(sid, "user", message)

        answer_content = ""
        reasoning_content = ""
        tools_used: list[str] = []
        plan_id: Optional[str] = None
        detected_intent: Optional[str] = None
        execution_stats: dict[str, Any] = {}
        verification_passed: Optional[bool] = None
        stale_result_count = 0
        fallback_steps = 0
        answer_started = False
        reasoning_ended = False
        memory_user_written = False

        try:
            memory_user_written = await self._write_memory_user(sid, message)
            if mode == "direct":
                yield self._sse({"type": "reasoning_start"})
                yield self._sse({"type": "reasoning_end"})
                reasoning_ended = True
                yield self._sse({"type": "answer_start"})
                answer_started = True

                async for token in self._stream_direct_response(sid, message):
                    answer_content += token
                    yield self._sse({"type": "chunk", "content": token})
            else:
                yield self._sse({"type": "reasoning_start"})
                if mode == "plan":
                    reasoning_content += "开始制定旅行计划..."
                    yield self._sse({"type": "reasoning_chunk", "content": "开始制定旅行计划..."})
                    try:
                        plan_preview = await asyncio.to_thread(self._generate_plan_preview, sid, message)
                        preview_steps = plan_preview.get("plan", [])
                        preview_intent = plan_preview.get("intent")
                        preview_plan_id = plan_preview.get("plan_id")
                        preview_explanation = plan_preview.get("plan_explanation")
                        preview_validation_status = plan_preview.get("validation_status", "pass")
                        preview_validation_errors = plan_preview.get("validation_errors", [])
                        yield self._sse(
                            {
                                "type": "plan_preview",
                                "plan_id": preview_plan_id,
                                "intent": preview_intent,
                                "explanation": preview_explanation,
                                "validation_status": preview_validation_status,
                                "validation_errors": preview_validation_errors,
                                "steps": preview_steps,
                            }
                        )
                        if preview_steps:
                            reasoning_content += f" 识别意图：{preview_intent}，共 {len(preview_steps)} 步。"
                            yield self._sse(
                                {
                                    "type": "reasoning_chunk",
                                    "content": f"识别意图：{preview_intent}，将执行 {len(preview_steps)} 步。",
                                }
                            )
                    except Exception as exc:
                        logger.warning("Plan preview failed, continue react flow: %s", exc)

                async for event in self._stream_agent_events(sid, message, mode=mode, run_id=run_id):
                    event_type = event.get("type")

                    if event_type == "reasoning":
                        content = event.get("content", "")
                        reasoning_content += content
                        yield self._sse({"type": "reasoning_chunk", "content": content})
                        continue

                    if event_type == "stage":
                        yield self._sse(
                            {
                                "type": "stage",
                                "stage": event.get("stage"),
                                "label": event.get("label"),
                                "progress": event.get("progress"),
                            }
                        )
                        continue

                    if event_type == "tool_start":
                        tool_name = event.get("tool", "")
                        if tool_name:
                            tools_used.append(tool_name)
                        yield self._sse({"type": "tool_start", "tool": tool_name})
                        continue

                    if event_type == "tool_end":
                        yield self._sse({
                            "type": "tool_end",
                            "tool": event.get("tool", ""),
                            "result": event.get("result", ""),
                        })
                        continue

                    if event_type == "chunk":
                        if not reasoning_ended:
                            yield self._sse({"type": "reasoning_end"})
                            reasoning_ended = True
                        if not answer_started:
                            yield self._sse({"type": "answer_start"})
                            answer_started = True

                        content = event.get("content", "")
                        if content:
                            answer_content += content
                            yield self._sse({"type": "chunk", "content": content})
                        continue

                    if event_type == "done":
                        answer_content = event.get("answer", answer_content)
                        plan_id = event.get("plan_id") or plan_id
                        detected_intent = event.get("intent") or detected_intent
                        execution_stats = event.get("execution_stats") or execution_stats
                        if event.get("verification_passed") is not None:
                            verification_passed = bool(event.get("verification_passed"))
                        if event.get("stale_result_count") is not None:
                            try:
                                stale_result_count = int(event.get("stale_result_count") or 0)
                            except Exception:
                                stale_result_count = 0
                        if event.get("fallback_steps") is not None:
                            try:
                                fallback_steps = int(event.get("fallback_steps") or 0)
                            except Exception:
                                fallback_steps = 0
                        stream_tools = event.get("tools_used", [])
                        if stream_tools:
                            tools_used.extend([tool for tool in stream_tools if tool])
                        continue

                if not reasoning_ended:
                    yield self._sse({"type": "reasoning_end"})
                if not answer_started:
                    yield self._sse({"type": "answer_start"})

            await self.save_message(sid, "assistant", answer_content, reasoning_content or None)
            if not await self._write_memory_assistant(sid, answer_content):
                logger.warning("Failed to write assistant memory for session=%s", sid)
            if not memory_user_written:
                await self._write_memory_user(sid, message)

            tools_used = list(dict.fromkeys(tools_used))
            stats_steps = list((execution_stats or {}).get("steps", []) or [])
            if fallback_steps <= 0:
                fallback_steps = sum(1 for item in stats_steps if bool(item.get("fallback_used", False)))
            if stale_result_count <= 0:
                stale_result_count = sum(1 for item in stats_steps if bool(item.get("is_stale", False)))
            if verification_passed is None:
                verification_passed = True if mode == "direct" else stale_result_count == 0
            self._record_run_metrics(
                intent=detected_intent or ("direct" if mode == "direct" else "unknown"),
                execution_stats=execution_stats,
                hard_error=False,
            )

            yield self._sse({
                "type": "metadata",
                "run_id": run_id,
                "total_steps": len(tools_used),
                "tools_used": tools_used,
                "has_reasoning": bool(reasoning_content),
                "reasoning_length": len(reasoning_content),
                "answer_length": len(answer_content),
                "plan_id": plan_id,
                "execution_stats": execution_stats,
                "verification_passed": verification_passed,
                "stale_result_count": stale_result_count,
                "fallback_steps": fallback_steps,
                "failure_clusters": self._extract_failure_clusters(execution_stats),
            })
            yield self._sse({"type": "done", "run_id": run_id})
            self._emit_failure_telemetry(
                session_id=sid,
                run_id=run_id,
                mode=mode,
                execution_stats=execution_stats,
                answer=answer_content,
            )

        except Exception as exc:
            logger.exception("Chat stream failed: %s", exc)
            self._record_run_metrics(
                intent=detected_intent or ("direct" if mode == "direct" else "unknown"),
                execution_stats=execution_stats,
                hard_error=True,
            )
            interrupted_answer = answer_content or "[INTERRUPTED]"
            try:
                await self.save_message(sid, "assistant", interrupted_answer, reasoning_content or "stream interrupted")
            except Exception:
                pass
            await self._write_memory_assistant(sid, f"[INTERRUPTED]{answer_content}")
            self._emit_failure_telemetry(
                session_id=sid,
                run_id=run_id,
                mode=mode,
                execution_stats=execution_stats,
                answer=answer_content,
                hard_error=str(exc),
            )
            yield self._sse({"type": "error", "content": str(exc), "run_id": run_id})
            yield self._sse({"type": "done", "run_id": run_id})

    async def _stream_direct_response(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
        """Stream direct LLM output tokens when mode bypasses tool orchestration.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            message: User message text for this chat run.
        
        Returns:
            AsyncGenerator[str, None]: Result value produced by this method.
        """
        history = self._build_relevant_memory_context_messages(session_id, message)
        if not history:
            history = await self._build_history_messages(session_id, exclude_last_user_message=message)
        payload = [SystemMessage(content=TRAVEL_AGENT_SYSTEM_PROMPT)]
        payload.extend(history)
        payload.append(HumanMessage(content=message))

        async for chunk in self._llm.astream(payload):
            token = self._extract_stream_text(chunk)
            if token:
                yield token

    @staticmethod
    def _extract_stream_text(chunk: Any) -> str:
        """Extract text token from heterogeneous streaming chunk payloads.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            chunk: Input `chunk` consumed by this method.
        
        Returns:
            str: Result value produced by this method.
        """
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
        """Bridge graph streaming events into service-level normalized event dictionaries.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            message: User message text for this chat run.
            mode: Requested chat mode (direct/react/plan).
            run_id: Input `run_id` consumed by this method.
        
        Returns:
            AsyncGenerator[str, None]: Streamed SSE/event payload sequence.
        """
        async for event in run_travel_agent_streaming_with_memory(
            user_message=message,
            llm=self._llm,
            tools=self._tools,
            session_id=session_id,
            memory_manager=self._memory_manager,
            system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
            persist_memory=False,
            run_id=run_id,
            chat_mode=mode,
            routing_llm=self._router_llm,
        ):
            if event.get("type") == "tool_end":
                event["result"] = str(event.get("result", ""))[:TOOL_RESULT_PREVIEW_LIMIT]
            yield event

    def _generate_plan_preview(self, session_id: str, message: str) -> dict[str, Any]:
        """Generate plan preview payload shown before full execution in plan mode.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            message: User message text for this chat run.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        return generate_plan_preview_with_memory(
            user_message=message,
            llm=self._llm,
            tools=self._tools,
            session_id=session_id,
            memory_manager=self._memory_manager,
            system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
            chat_mode="plan",
            routing_llm=self._router_llm,
        )

    def _build_memory_context_messages(self, session_id: str) -> list[Any]:
        """Build baseline memory context messages for graph invocation.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            list[Any]: Result value produced by this method.
        """
        if self._memory_manager is None:
            return []
        try:
            return self._memory_manager.build_context_messages(session_id)
        except Exception as exc:
            logger.warning("Failed to build memory context messages: %s", exc)
            return []

    def _build_relevant_memory_context_messages(self, session_id: str, user_message: str) -> list[Any]:
        """Build query-relevant memory context messages to reduce token footprint.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            user_message: Input `user_message` consumed by this method.
        
        Returns:
            list[Any]: Result value produced by this method.
        """
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
        """Convert persisted session chat history into model message objects.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            limit: Input `limit` consumed by this method.
            exclude_last_user_message: Input `exclude_last_user_message` consumed by this method.
        
        Returns:
            list[Any]: Result value produced by this method.
        """
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
        """Resolve or create a session identifier before writing chat data.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            str: Result value produced by this method.
        """
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
                "model_id": self._llm_adapter.config.get("model", "MiniMax-M2.5") if self._llm_adapter else "MiniMax-M2.5",
                "messages": [],
                "user_preferences": {},
            }
        )
        return sid

    @staticmethod
    def _normalize_mode(mode: Optional[str]) -> str:
        """Normalize requested mode and fall back to safe default when invalid.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            mode: Requested chat mode (direct/react/plan).
        
        Returns:
            str: Result value produced by this method.
        """
        if not mode:
            return "react"
        mode = mode.strip().lower()
        return mode if mode in ChatService.VALID_MODES else "react"

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        """Serialize one SSE envelope line from a structured payload object.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            payload: Structured payload serialized into SSE format.
        
        Returns:
            str: Result value produced by this method.
        """
        import json

        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        reasoning: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist one chat message into repository and optionally sync memory profile.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            role: Input `role` consumed by this method.
            content: Text content being streamed, persisted, or analyzed.
            reasoning: Input `reasoning` consumed by this method.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在"}

        messages = session.get("messages", [])
        messages.append(
            {
                "role": role,
                "content": content,
                "reasoning": reasoning,
                "timestamp": self._get_timestamp(),
            }
        )

        await self._repository.update(
            session_id,
            {
                "messages": messages,
                "message_count": len(messages),
            },
        )
        return {"success": True}

    async def get_messages(self, session_id: str) -> dict[str, Any]:
        """Return persisted messages for a session, ordered by repository contract.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在", "messages": []}

        return {"success": True, "messages": session.get("messages", [])}

    async def cleanup_expired_sessions(self, max_age_seconds: int = 86400) -> int:
        """Run repository cleanup for expired sessions and stale data.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            max_age_seconds: Input `max_age_seconds` consumed by this method.
        
        Returns:
            int: Result value produced by this method.
        """
        return await self._repository.cleanup_expired(max_age_seconds)

    @staticmethod
    def _get_timestamp() -> str:
        """Return current timestamp string used by persisted message records.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            str: Result value produced by this method.
        """
        return datetime.now().strftime("%H:%M:%S")

    async def _write_memory_user(self, session_id: str, message: str) -> bool:
        """Write user message into memory manager and swallow non-fatal memory errors.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            message: User message text for this chat run.
        
        Returns:
            bool: Result value produced by this method.
        """
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "user", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write user memory: %s", exc)
            return False

    async def _write_memory_assistant(self, session_id: str, message: str) -> bool:
        """Write assistant answer into memory manager and swallow non-fatal memory errors.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            message: User message text for this chat run.
        
        Returns:
            bool: Result value produced by this method.
        """
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "assistant", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write assistant memory: %s", exc)
            return False

    @staticmethod
    def _extract_failure_clusters(execution_stats: dict[str, Any]) -> dict[str, int]:
        """Extract clustered failure patterns from execution metadata for telemetry.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            execution_stats: Input `execution_stats` consumed by this method.
        
        Returns:
            dict[str, int]: Result value produced by this method.
        """
        steps = list((execution_stats or {}).get("steps", []) or [])
        clusters = {"timeout": 0, "param_error": 0, "irrelevant_answer": 0, "tool_error": 0}
        for step in steps:
            code = str(step.get("error_code") or "")
            if code == "TOOL_TIMEOUT":
                clusters["timeout"] += 1
            elif code == "PARAM_VALIDATION_ERROR":
                clusters["param_error"] += 1
            elif code:
                clusters["tool_error"] += 1
        return clusters

    def _emit_failure_telemetry(
        self,
        session_id: str,
        run_id: str,
        mode: str,
        execution_stats: dict[str, Any],
        answer: str,
        hard_error: Optional[str] = None,
    ) -> None:
        """Emit summarized failure telemetry into service health metric buffers.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            session_id: Session identifier used to isolate chat and memory state.
            run_id: Input `run_id` consumed by this method.
            mode: Requested chat mode (direct/react/plan).
            execution_stats: Input `execution_stats` consumed by this method.
            answer: Input `answer` consumed by this method.
            hard_error: Input `hard_error` consumed by this method.
        
        Returns:
            None: Result value produced by this method.
        """
        clusters = self._extract_failure_clusters(execution_stats)
        if not answer.strip():
            clusters["irrelevant_answer"] += 1
        payload = {
            "ts": datetime.now().isoformat(),
            "session_id": session_id,
            "run_id": run_id,
            "mode": mode,
            "clusters": clusters,
            "hard_error": hard_error,
        }
        if not any(value > 0 for value in clusters.values()) and not hard_error:
            return

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        target = os.path.join(root, "data", "runtime_failure_clusters.jsonl")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            with open(target, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to write failure telemetry: %s", exc)

    @staticmethod
    def _parse_int_env(name: str, default: int, minimum: int) -> int:
        """Parse integer environment variable with fallback and lower-bound protection.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            name: Session display name provided by API caller.
            default: Fallback value used when environment variable is missing or invalid.
            minimum: Lower bound enforced for parsed integer environment values.
        
        Returns:
            int: Result value produced by this method.
        """
        raw = str(os.getenv(name, str(default))).strip()
        try:
            value = int(raw)
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")
            return value
        except Exception:
            return default

    @staticmethod
    def _parse_float_env(name: str, default: float) -> float:
        """Parse float environment variable with fallback protection.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            name: Session display name provided by API caller.
            default: Fallback value used when environment variable is missing or invalid.
        
        Returns:
            float: Result value produced by this method.
        """
        raw = str(os.getenv(name, str(default))).strip()
        try:
            value = float(raw)
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            return value
        except Exception:
            return default

    def _record_run_metrics(self, intent: str, execution_stats: dict[str, Any], hard_error: bool) -> None:
        """Record per-run metrics into bounded in-memory buffers for SLO snapshots.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Args:
            intent: Input `intent` consumed by this method.
            execution_stats: Input `execution_stats` consumed by this method.
            hard_error: Input `hard_error` consumed by this method.
        
        Returns:
            None: Result value produced by this method.
        """
        steps = list((execution_stats or {}).get("steps", []) or [])
        has_timeout = any(str(step.get("error_code") or "") == "TOOL_TIMEOUT" for step in steps)
        has_failure = hard_error or any(str(step.get("status") or "") in {"failed", "blocked"} for step in steps)
        has_fallback = any(bool(step.get("fallback_used")) for step in steps)
        record = {
            "timestamp": datetime.now(),
            "intent": str(intent or "unknown"),
            "has_timeout": has_timeout,
            "has_failure": has_failure,
            "has_fallback": has_fallback,
        }
        with self._health_metrics_lock:
            self._health_metrics.append(record)
            self._prune_old_metrics_locked()

    def _prune_old_metrics_locked(self) -> None:
        """Prune old metrics outside configured health window under lock.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            None: Result value produced by this method.
        """
        if not self._health_metrics:
            return
        cutoff = datetime.now() - timedelta(minutes=self._health_window_minutes)
        while self._health_metrics and self._health_metrics[0]["timestamp"] < cutoff:
            self._health_metrics.popleft()

    def _build_health_metrics_snapshot(self) -> dict[str, Any]:
        """Build current health snapshot including SLO rates and intent aggregates.
        
        Purpose:
            Document service-level contracts, side effects, and response semantics for easier API/backend maintenance.
        
        Returns:
            dict[str, Any]: Result value produced by this method.
        """
        with self._health_metrics_lock:
            self._prune_old_metrics_locked()
            records = list(self._health_metrics)

        total = len(records)
        timeout_count = sum(1 for item in records if bool(item.get("has_timeout")))
        failure_count = sum(1 for item in records if bool(item.get("has_failure")))
        fallback_count = sum(1 for item in records if bool(item.get("has_fallback")))
        timeout_rate = round(timeout_count / total, 4) if total else 0.0
        failure_rate = round(failure_count / total, 4) if total else 0.0
        fallback_rate = round(fallback_count / total, 4) if total else 0.0

        status = "ok"
        if (
            timeout_rate > float(self._slo_thresholds["timeout_rate"])
            or failure_rate > float(self._slo_thresholds["failure_rate"])
            or fallback_rate > float(self._slo_thresholds["fallback_rate"])
        ):
            status = "degraded"

        intent_aggregate: dict[str, dict[str, Any]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in records:
            intent = str(item.get("intent") or "unknown")
            grouped.setdefault(intent, []).append(item)
        for intent, items in grouped.items():
            bucket_total = len(items)
            intent_aggregate[intent] = {
                "total": bucket_total,
                "timeout_rate": round(sum(1 for it in items if bool(it.get("has_timeout"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
                "failure_rate": round(sum(1 for it in items if bool(it.get("has_failure"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
                "fallback_rate": round(sum(1 for it in items if bool(it.get("has_fallback"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
            }

        return {
            "slo": {
                "status": status,
                "timeout_rate": timeout_rate,
                "failure_rate": failure_rate,
                "fallback_rate": fallback_rate,
                "thresholds": dict(self._slo_thresholds),
                "total_requests": total,
            },
            "intent_aggregate": intent_aggregate,
        }
