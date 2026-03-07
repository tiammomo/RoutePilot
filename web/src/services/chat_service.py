from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..repositories.session_repository import SessionRepository
from ..bootstrap import ensure_project_paths
from ..config.runtime import get_llm_config_path

ensure_project_paths()

from agent.src.llm.langchain_adapter import create_from_yaml_config
from agent.src.tools.travel_tools import get_travel_tools
from agent.src.graph import TRAVEL_AGENT_SYSTEM_PROMPT
from agent.src.graph.builder import (
    TOOL_RESULT_PREVIEW_LIMIT,
    generate_plan_preview_with_memory,
    run_travel_agent_streaming_with_memory,
)
from agent.src.graph.memory_integration import get_agent_memory_manager

logger = logging.getLogger(__name__)


class ChatService:
    """Application service for end-to-end chat orchestration."""

    VALID_MODES = {"direct", "react", "plan"}

    def __init__(self, repository: SessionRepository):
        self._repository = repository
        self._init_lock = asyncio.Lock()
        self._initialized = False

        self._llm_adapter = None
        self._llm = None
        self._tools = None
        self._memory_manager = None

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            config_path = get_llm_config_path()
            self._llm_adapter = create_from_yaml_config(config_path)
            self._llm = self._llm_adapter.chat_model
            self._tools = get_travel_tools()
            self._memory_manager = get_agent_memory_manager(
                max_history=10,
                summary_threshold=20,
            )
            self._initialized = True
            logger.info("Chat runtime initialized with model=%s tools=%d", self._llm_adapter.config.get("name"), len(self._tools))

    async def health_status(self) -> dict[str, Any]:
        return {
            "initialized": self._initialized,
            "llm_adapter": self._llm_adapter is not None,
            "tools_count": len(self._tools) if self._tools else 0,
            "memory_enabled": self._memory_manager is not None,
        }

    async def stream_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        mode: str = "react",
    ) -> AsyncGenerator[str, None]:
        await self.initialize()

        mode = self._normalize_mode(mode)
        sid = await self._ensure_session(session_id)

        yield self._sse({"type": "session_id", "session_id": sid})
        await self.save_message(sid, "user", message)

        answer_content = ""
        reasoning_content = ""
        tools_used: list[str] = []
        plan_id: Optional[str] = None
        execution_stats: dict[str, Any] = {}
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
                        yield self._sse(
                            {
                                "type": "plan_preview",
                                "plan_id": preview_plan_id,
                                "intent": preview_intent,
                                "explanation": preview_explanation,
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

                async for event in self._stream_agent_events(sid, message):
                    event_type = event.get("type")

                    if event_type == "reasoning":
                        content = event.get("content", "")
                        reasoning_content += content
                        yield self._sse({"type": "reasoning_chunk", "content": content})
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
                        execution_stats = event.get("execution_stats") or execution_stats
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

            yield self._sse({
                "type": "metadata",
                "total_steps": len(tools_used),
                "tools_used": tools_used,
                "has_reasoning": bool(reasoning_content),
                "reasoning_length": len(reasoning_content),
                "answer_length": len(answer_content),
                "plan_id": plan_id,
                "execution_stats": execution_stats,
            })
            yield self._sse({"type": "done"})

        except Exception as exc:
            logger.exception("Chat stream failed: %s", exc)
            interrupted_answer = answer_content or "[INTERRUPTED]"
            try:
                await self.save_message(sid, "assistant", interrupted_answer, reasoning_content or "stream interrupted")
            except Exception:
                pass
            await self._write_memory_assistant(sid, f"[INTERRUPTED]{answer_content}")
            yield self._sse({"type": "error", "content": str(exc)})
            yield self._sse({"type": "done"})

    async def _stream_direct_response(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
        history = self._build_memory_context_messages(session_id)
        if not history:
            history = await self._build_history_messages(session_id, exclude_last_user_message=message)
        payload = [SystemMessage(content=TRAVEL_AGENT_SYSTEM_PROMPT)]
        payload.extend(history)
        payload.append(HumanMessage(content=message))

        async for chunk in self._llm.astream(payload):
            token = getattr(chunk, "content", "")
            if token:
                yield token

    async def _stream_agent_events(self, session_id: str, message: str) -> AsyncGenerator[dict[str, Any], None]:
        async for event in run_travel_agent_streaming_with_memory(
            user_message=message,
            llm=self._llm,
            tools=self._tools,
            session_id=session_id,
            memory_manager=self._memory_manager,
            system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
            persist_memory=False,
        ):
            if event.get("type") == "tool_end":
                event["result"] = str(event.get("result", ""))[:TOOL_RESULT_PREVIEW_LIMIT]
            yield event

    def _generate_plan_preview(self, session_id: str, message: str) -> dict[str, Any]:
        return generate_plan_preview_with_memory(
            user_message=message,
            llm=self._llm,
            tools=self._tools,
            session_id=session_id,
            memory_manager=self._memory_manager,
            system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        )

    def _build_memory_context_messages(self, session_id: str) -> list[Any]:
        if self._memory_manager is None:
            return []
        try:
            return self._memory_manager.build_context_messages(session_id)
        except Exception as exc:
            logger.warning("Failed to build memory context messages: %s", exc)
            return []

    async def _build_history_messages(
        self,
        session_id: str,
        limit: int = 12,
        exclude_last_user_message: Optional[str] = None,
    ) -> list[Any]:
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
        if session_id:
            session = await self._repository.get(session_id)
            if session:
                return session_id

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
        if not mode:
            return "react"
        mode = mode.strip().lower()
        return mode if mode in ChatService.VALID_MODES else "react"

    @staticmethod
    def _sse(payload: dict[str, Any]) -> str:
        import json

        return f"data: {json.dumps(payload, ensure_ascii=False)}\\n\\n"

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        reasoning: Optional[str] = None,
    ) -> dict[str, Any]:
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
        session = await self._repository.get(session_id)
        if not session:
            return {"success": False, "error": "会话不存在", "messages": []}

        return {"success": True, "messages": session.get("messages", [])}

    async def cleanup_expired_sessions(self, max_age_seconds: int = 86400) -> int:
        return await self._repository.cleanup_expired(max_age_seconds)

    @staticmethod
    def _get_timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def _write_memory_user(self, session_id: str, message: str) -> bool:
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "user", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write user memory: %s", exc)
            return False

    async def _write_memory_assistant(self, session_id: str, message: str) -> bool:
        if self._memory_manager is None:
            return False
        try:
            await self._memory_manager.add_message(session_id, "assistant", message)
            return True
        except Exception as exc:
            logger.warning("Failed to write assistant memory: %s", exc)
            return False
