"""Memory integration for LangGraph travel agent.

This module provides:
- Session-scoped memory manager with async APIs
- Lightweight conversation summarizer
- AgentStateWithMemory helper for building initial graph state with memory context
"""

from __future__ import annotations

import json
import os
import asyncio
import re
import threading
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ..memory import MemoryConflictResolutionHelper, MemoryPersistenceStore


@dataclass
class MemoryMessage:
    """Minimal chat message shape used in history trimming and summarization."""

    role: str
    content: str
    timestamp: str


class ConversationSummarizer:
    """Compact summarizer for long dialogue context.

    The implementation is deterministic and does not rely on an LLM call,
    so it is safe in sync/async paths and resilient in offline runs.
    """

    def __init__(self, llm: Any = None, summary_threshold: int = 20):
        """Initialize deterministic summarization settings for long session histories.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            llm: Primary chat model runnable used for reasoning and answer generation.
            summary_threshold: Maximum message count before older dialogue turns are summarized.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self.llm = llm
        self.summary_threshold = max(2, summary_threshold)

    def summarize(self, messages: List[MemoryMessage]) -> str:
        """Compress older turns into short bullets used as compact system context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            messages: Chronological message list used as model/tool context.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        if not messages:
            return ""

        if len(messages) <= self.summary_threshold:
            return ""

        cutoff = max(2, len(messages) - self.summary_threshold)
        head = messages[:cutoff]

        user_points: List[str] = []
        assistant_points: List[str] = []

        for msg in head:
            text = (msg.content or "").strip().replace("\n", " ")
            if not text:
                continue
            short = text[:80] + ("..." if len(text) > 80 else "")
            if msg.role == "user":
                user_points.append(short)
            elif msg.role == "assistant":
                assistant_points.append(short)

        bullets: List[str] = []
        if user_points:
            bullets.append("用户关键信息: " + " | ".join(user_points[-4:]))
        if assistant_points:
            bullets.append("助手已给建议: " + " | ".join(assistant_points[-4:]))

        return "\n".join(bullets).strip()


class AgentMemoryManager:
    """Session memory manager used by LangGraph integration."""

    def __init__(
        self,
        llm: Any = None,
        max_history: int = 10,
        summary_threshold: int = 20,
        persist_path: Optional[str] = None,
        session_ttl_seconds: int = 7 * 24 * 3600,
        max_sessions: int = 5000,
    ):
        """Initialize session memory store, locks, retention policy, and optional disk persistence.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            llm: Primary chat model runnable used for reasoning and answer generation.
            max_history: Numeric control parameter `max_history` used for bounds or pagination.
            summary_threshold: Maximum message count before older dialogue turns are summarized.
            persist_path: Filesystem/resource path for `persist_path` resolution.
            session_ttl_seconds: Time-related setting `session_ttl_seconds` used by scheduling/retry windows.
            max_sessions: Numeric control parameter `max_sessions` used for bounds or pagination.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self.max_history = max(2, max_history)
        self.summarizer = ConversationSummarizer(llm=llm, summary_threshold=summary_threshold)

        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()
        self._session_ttl_seconds = max(60, session_ttl_seconds)
        self._max_sessions = max(1, max_sessions)

        self._persist_path = persist_path
        self._persistence_store = MemoryPersistenceStore(
            persist_path=self._persist_path,
            backup_suffix=self.PERSIST_BACKUP_SUFFIX,
        )
        self._conflict_resolution = MemoryConflictResolutionHelper(self)
        if self._persistence_store.enabled:
            self._load_from_disk()

    PROFILE_SCHEMA_VERSION = 2
    SOURCE_PRIORITY = {"inferred": 1, "recent_inferred": 2, "explicit": 3}
    CLARIFICATION_SEVERITY_PRIORITY = {"low": 1, "medium": 2, "high": 3}
    DECAY_HALF_LIFE_HOURS = 72.0
    MIN_DECAY_CONFIDENCE = 0.25
    PROFILE_SLOT_TOP_K = 6
    PROFILE_TAG_TOP_K = 4
    CLARIFICATION_TOP_K = 2
    CLARIFICATION_MAX_ASK_PER_ITEM = 1
    PERSIST_BACKUP_SUFFIX = ".bak"
    MEMORY_PROMPT_TOKEN_BUDGET = 900
    MEMORY_SUMMARY_TOKEN_BUDGET = 180
    MEMORY_PROFILE_TOKEN_BUDGET = 260
    MEMORY_CLARIFICATION_TOKEN_BUDGET = 150
    MEMORY_CROSS_SESSION_TOKEN_BUDGET = 130
    MEMORY_MESSAGE_TOKEN_BUDGET = 520
    MEMORY_PER_MESSAGE_TOKEN_BUDGET = 140
    MEMORY_MIN_CONTEXT_MESSAGES = 2
    PROFILE_INTEREST_MAX_ITEMS = 16
    PROFILE_AVOID_MAX_ITEMS = 16
    ATTRIBUTE_GC_MIN_DECAY_CONFIDENCE = 0.08
    ATTRIBUTE_GC_MIN_AGE_HOURS = 24 * 45
    PENDING_CLARIFICATION_EXPIRE_HOURS = 24 * 14
    CROSS_SESSION_MIN_DECAY_CONFIDENCE = 0.55
    CROSS_SESSION_MIN_SOURCE_PRIORITY = 2
    CROSS_SESSION_LOOKBACK_HOURS = 24 * 180
    CROSS_SESSION_ATTR_TOP_K = 3
    CROSS_SESSION_TERM_TOP_K = 3
    CROSS_SESSION_INJECT_MIN_CORE_SLOTS = 3
    CROSS_SESSION_INJECT_MIN_INTERESTS = 2
    CROSS_SESSION_INJECT_MIN_AVOIDS = 1
    TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]+")
    CJK_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    ALNUM_PATTERN = re.compile(r"[a-zA-Z0-9_]+")
    INTEREST_SYNONYM_MAP: Dict[str, tuple[str, ...]] = {
        "美食": ("美食", "小吃", "探店", "吃喝", "餐厅", "打卡店"),
        "亲子": ("亲子", "遛娃", "带娃", "儿童友好"),
        "博物馆": ("博物馆", "展览", "美术馆", "科技馆"),
        "摄影": ("摄影", "拍照", "机位", "出片"),
        "徒步": ("徒步", "步行", "walk", "hiking"),
        "自然": ("自然", "户外", "公园", "山海"),
        "历史": ("历史", "人文", "古迹", "文化"),
        "海边": ("海边", "海岛", "看海", "滨海"),
        "滑雪": ("滑雪", "雪场", "冰雪"),
        "购物": ("购物", "逛街", "买买买", "商圈"),
        "夜景": ("夜景", "夜游", "夜拍", "灯光秀"),
    }
    AVOID_SYNONYM_MAP: Dict[str, tuple[str, ...]] = {
        "人多": ("人多", "人挤人", "拥挤", "人山人海"),
        "排队": ("排队", "等位", "久等", "长队"),
        "贵": ("贵", "太贵", "高消费", "花钱多"),
        "早起": ("早起", "起太早", "起早"),
        "爬山": ("爬山", "登山", "爬坡", "上坡"),
        "舟车劳顿": ("舟车劳顿", "奔波", "折腾", "路途太远"),
    }

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """Persist one chat turn, refresh summary/profile, and enforce retention and capacity rules.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            role: Message role label (user/assistant/system).
            content: Raw text content being normalized or analyzed.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        async with self._lock:
            with self._sync_lock:
                self._cleanup_expired_locked()
                session = self._sessions.setdefault(
                    session_id,
                    {"messages": [], "summary": "", "profile": self._empty_profile()},
                )
                session["messages"].append(
                    MemoryMessage(
                        role=role,
                        content=content,
                        timestamp=datetime.now().isoformat(),
                    )
                )
                self._update_profile(session, role=role, content=content)
                session["summary"] = self.summarizer.summarize(session["messages"])
                self._trim_messages(session)
                self._enforce_capacity_locked()

            if self._persist_path:
                await asyncio.to_thread(self._save_to_disk_locked)

    async def get_recent_messages(self, session_id: str, limit: Optional[int] = None) -> List[MemoryMessage]:
        """Return recent session messages for async call-sites.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            limit: Numeric control parameter `limit` used for bounds or pagination.
        
        Returns:
            List[MemoryMessage]: Computed value returned to the caller.
        """
        async with self._lock:
            with self._sync_lock:
                self._cleanup_expired_locked()
                session = self._sessions.get(session_id)
                if not session:
                    return []
                cap = limit or self.max_history
                return list(session["messages"][-cap:])

    async def get_summary(self, session_id: str) -> str:
        """Return the cached session summary for async call-sites.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        async with self._lock:
            with self._sync_lock:
                self._cleanup_expired_locked()
                session = self._sessions.get(session_id)
                if not session:
                    return ""
                return session.get("summary", "")

    def get_recent_messages_sync(self, session_id: str, limit: Optional[int] = None) -> List[MemoryMessage]:
        """Get recent messages sync from current runtime context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            limit: Numeric control parameter `limit` used for bounds or pagination.
        
        Returns:
            List[MemoryMessage]: Computed value returned to the caller.
        """
        with self._sync_lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            cap = limit or self.max_history
            return list(session["messages"][-cap:])

    def get_summary_sync(self, session_id: str) -> str:
        """Get summary sync from current runtime context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        with self._sync_lock:
            session = self._sessions.get(session_id)
            if not session:
                return ""
            return session.get("summary", "")

    def build_context_messages(self, session_id: str) -> List[BaseMessage]:
        """Build baseline memory context injected into the next agent invocation.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            List[BaseMessage]: Computed value returned to the caller.
        """
        summary = self.get_summary_sync(session_id)
        recent = self.get_recent_messages_sync(session_id, self.max_history)
        profile = self.get_profile_sync(session_id)
        query_tokens: set[str] = set()
        clarification_hint = self._build_conflict_clarification_hint(profile, query_tokens=query_tokens)
        return self._build_budgeted_context_messages(
            session_id=session_id,
            summary=summary,
            profile=profile,
            clarification_hint=clarification_hint,
            selected_messages=recent,
            query_tokens=query_tokens,
        )

    def _build_clarification_turn_fingerprint(self, user_message: str, query_tokens: set[str]) -> str:
        """Build a stable per-turn fingerprint for clarification retry deduplication."""

        return self._conflict_resolution.build_clarification_turn_fingerprint(user_message, query_tokens)

    def _consume_conflict_clarification_hint(
        self,
        session_id: str,
        query_tokens: set[str],
        turn_fingerprint: str,
    ) -> str:
        """Consume eligible pending clarifications for one user turn and update retry state."""

        return self._conflict_resolution.consume_conflict_clarification_hint(
            session_id=session_id,
            query_tokens=query_tokens,
            turn_fingerprint=turn_fingerprint,
        )

    def _build_budgeted_context_messages(
        self,
        session_id: str,
        summary: str,
        profile: Dict[str, Any],
        clarification_hint: str,
        selected_messages: List[MemoryMessage],
        query_tokens: set[str],
    ) -> List[BaseMessage]:
        """Build memory context under token budget guardrails.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            summary: Session summary string used as compact historical context.
            profile: User preference profile snapshot stored in memory manager.
            clarification_hint: Clarification hint text built from pending preference conflicts.
            selected_messages: Ranked message candidates used for context injection.
            query_tokens: Tokenized query terms used for relevance scoring.
        
        Returns:
            List[BaseMessage]: Computed value returned to the caller.
        """
        context: List[BaseMessage] = []
        used_tokens = 0

        if summary:
            trimmed_summary = self._truncate_text_to_token_budget(summary, self.MEMORY_SUMMARY_TOKEN_BUDGET)
            summary_content = f"会话摘要:\n{trimmed_summary}"
            summary_tokens = self._estimate_token_cost(summary_content)
            if used_tokens + summary_tokens <= self.MEMORY_PROMPT_TOKEN_BUDGET:
                context.append(SystemMessage(content=summary_content))
                used_tokens += summary_tokens

        compact_profile = self._fit_compact_profile_to_budget(
            profile=profile,
            query_tokens=query_tokens,
            budget_tokens=self.MEMORY_PROFILE_TOKEN_BUDGET,
        )
        if compact_profile:
            profile_content = "用户长期偏好(Top-K 槽位):\n" + json.dumps(compact_profile, ensure_ascii=False, indent=2)
            profile_tokens = self._estimate_token_cost(profile_content)
            if used_tokens + profile_tokens <= self.MEMORY_PROMPT_TOKEN_BUDGET:
                context.append(SystemMessage(content=profile_content))
                used_tokens += profile_tokens

        if clarification_hint:
            trimmed_hint = self._truncate_text_to_token_budget(
                clarification_hint,
                self.MEMORY_CLARIFICATION_TOKEN_BUDGET,
            )
            hint_tokens = self._estimate_token_cost(trimmed_hint)
            if used_tokens + hint_tokens <= self.MEMORY_PROMPT_TOKEN_BUDGET:
                context.append(SystemMessage(content=trimmed_hint))
                used_tokens += hint_tokens

        cross_session_hints = self._build_cross_session_preference_hints(
            session_id=session_id,
            current_profile=profile,
            query_tokens=query_tokens,
        )
        cross_session_hints = self._fit_cross_session_hints_to_budget(
            hints=cross_session_hints,
            budget_tokens=self.MEMORY_CROSS_SESSION_TOKEN_BUDGET,
        )
        if cross_session_hints:
            cross_content = (
                "跨会话稳定偏好候选(仅在本会话缺失时参考):\n"
                + json.dumps(cross_session_hints, ensure_ascii=False, indent=2)
            )
            cross_tokens = self._estimate_token_cost(cross_content)
            if used_tokens + cross_tokens <= self.MEMORY_PROMPT_TOKEN_BUDGET:
                context.append(SystemMessage(content=cross_content))
                used_tokens += cross_tokens
                # Cross-session hints are advisory only; still tracked for observability and tuning feedback loops.
                self._increment_session_stat(session_id=session_id, key="cross_session_hint_injected", delta=1)

        remaining_tokens = max(0, self.MEMORY_PROMPT_TOKEN_BUDGET - used_tokens)
        context.extend(
            self._build_budgeted_chat_messages(
                selected_messages=selected_messages,
                message_budget_tokens=min(remaining_tokens, self.MEMORY_MESSAGE_TOKEN_BUDGET),
            )
        )
        return context

    def build_context_messages_for_query(
        self,
        session_id: str,
        user_message: str,
        max_messages: int = 8,
    ) -> List[BaseMessage]:
        """Select memory messages relevant to the current query and build compact context messages.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            user_message: Raw user request text for this run.
            max_messages: Numeric control parameter `max_messages` used for bounds or pagination.
        
        Returns:
            List[BaseMessage]: Computed value returned to the caller.
        """
        summary = self.get_summary_sync(session_id)
        profile = self.get_profile_sync(session_id)
        candidates = self.get_recent_messages_sync(session_id, max(self.max_history * 2, max_messages))
        query_tokens = self._tokenize(user_message)

        ranked: List[tuple[float, int, MemoryMessage]] = []
        for idx, msg in enumerate(candidates):
            msg_tokens = self._tokenize(msg.content)
            overlap = len(query_tokens & msg_tokens) if query_tokens else 0
            recency_boost = idx  # preserve latest messages under tie
            decay = self._time_decay_factor(msg.timestamp)
            score = float(overlap * 2) + float(recency_boost * 0.05) + decay
            ranked.append((score, recency_boost, msg))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = [item[2] for item in ranked[: max(2, max_messages)]]
        selected.sort(key=lambda item: item.timestamp)
        turn_fingerprint = self._build_clarification_turn_fingerprint(user_message, query_tokens)
        clarification_hint = self._consume_conflict_clarification_hint(
            session_id=session_id,
            query_tokens=query_tokens,
            turn_fingerprint=turn_fingerprint,
        )
        return self._build_budgeted_context_messages(
            session_id=session_id,
            summary=summary,
            profile=profile,
            clarification_hint=clarification_hint,
            selected_messages=selected,
            query_tokens=query_tokens,
        )

    async def clear_session_messages(self, session_id: str) -> bool:
        """Clear session message history while keeping profile/context data.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        async with self._lock:
            with self._sync_lock:
                session = self._sessions.get(session_id)
                if not session:
                    return False
                session["messages"] = []
                session["summary"] = ""
                session["profile"] = self._empty_profile()
            if self._persist_path:
                await asyncio.to_thread(self._save_to_disk_locked)
            return True

    async def delete_session(self, session_id: str) -> bool:
        """Delete one session and all associated memory payloads.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        async with self._lock:
            with self._sync_lock:
                existed = self._sessions.pop(session_id, None) is not None
            if existed and self._persist_path:
                await asyncio.to_thread(self._save_to_disk_locked)
            return existed

    def get_profile_sync(self, session_id: str) -> Dict[str, Any]:
        """Get profile sync from current runtime context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        with self._sync_lock:
            session = self._sessions.get(session_id)
            if not session:
                return {}
            profile = self._normalize_profile(session.get("profile"))
            flattened = {
                "schema_version": profile.get("schema_version", self.PROFILE_SCHEMA_VERSION),
                "updated_at": profile.get("updated_at"),
            }
            for key, item in profile.get("attributes", {}).items():
                decayed_conf = self._decayed_confidence(item if isinstance(item, dict) else {})
                if decayed_conf >= self.MIN_DECAY_CONFIDENCE and isinstance(item, dict):
                    flattened[key] = item.get("value")
            flattened["interests"] = sorted(profile.get("interests", []))
            flattened["avoid_preferences"] = sorted(profile.get("avoid_preferences", []))
            flattened["pending_clarifications"] = profile.get("pending_clarifications", [])
            flattened["_meta"] = self._attributes_with_decay(profile.get("attributes", {}))
            return flattened

    async def get_profile(self, session_id: str) -> Dict[str, Any]:
        """Get profile from current runtime context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        async with self._lock:
            return self.get_profile_sync(session_id)

    def get_memory_diagnostics_sync(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Return memory diagnostics for one session or for the whole manager.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        with self._sync_lock:
            self._cleanup_expired_locked()
            self._enforce_capacity_locked()

            if session_id:
                session = self._sessions.get(session_id)
                if not session:
                    return {"session_id": session_id, "exists": False}
                profile = self._normalize_profile(session.get("profile", {}))
                session["profile"] = profile
                messages = session.get("messages", [])
                last_message_ts = messages[-1].timestamp if messages else None
                return {
                    "session_id": session_id,
                    "exists": True,
                    "message_count": len(messages),
                    "attribute_count": len(profile.get("attributes", {})),
                    "interest_count": len(profile.get("interests", [])),
                    "avoid_count": len(profile.get("avoid_preferences", [])),
                    "pending_clarification_count": len(profile.get("pending_clarifications", [])),
                    "last_message_timestamp": last_message_ts,
                    "stats": dict(profile.get("stats", {})),
                }

            session_count = len(self._sessions)
            sessions_with_messages = 0
            total_messages = 0
            total_attributes = 0
            total_pending = 0
            total_clarification_asked = 0
            total_conflict_resolved = 0
            total_attr_pruned = 0
            total_pending_pruned = 0
            total_cross_session_hint = 0

            for sid, session in self._sessions.items():
                if not isinstance(session, dict):
                    continue
                profile = self._normalize_profile(session.get("profile", {}))
                session["profile"] = profile
                messages = session.get("messages", [])
                if messages:
                    sessions_with_messages += 1
                total_messages += len(messages)
                total_attributes += len(profile.get("attributes", {}))
                total_pending += len(profile.get("pending_clarifications", []))
                stats = self._ensure_profile_stats(profile)
                total_clarification_asked += self._safe_int(stats.get("clarification_asked", 0))
                total_conflict_resolved += self._safe_int(stats.get("conflict_resolved", 0))
                total_attr_pruned += self._safe_int(stats.get("attr_pruned", 0))
                total_pending_pruned += self._safe_int(stats.get("pending_pruned", 0))
                total_cross_session_hint += self._safe_int(stats.get("cross_session_hint_injected", 0))

            avg_attributes = float(total_attributes) / float(session_count) if session_count else 0.0
            avg_messages = float(total_messages) / float(session_count) if session_count else 0.0
            return {
                "session_count": session_count,
                "sessions_with_messages": sessions_with_messages,
                "total_messages": total_messages,
                "average_messages_per_session": round(avg_messages, 2),
                "total_attributes": total_attributes,
                "average_attributes_per_session": round(avg_attributes, 2),
                "pending_clarification_total": total_pending,
                "clarification_asked_total": total_clarification_asked,
                "conflict_resolved_total": total_conflict_resolved,
                "attr_pruned_total": total_attr_pruned,
                "pending_pruned_total": total_pending_pruned,
                "cross_session_hint_injected_total": total_cross_session_hint,
            }

    async def get_memory_diagnostics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Async wrapper for memory diagnostics API.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        async with self._lock:
            return self.get_memory_diagnostics_sync(session_id=session_id)

    @staticmethod
    def _ordered_unique_terms(raw_terms: Any) -> List[str]:
        """Deduplicate list-like terms while preserving their original order.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            raw_terms: Input field `raw_terms` used for normalization or matching rules.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        if not isinstance(raw_terms, list):
            return []
        seen: set[str] = set()
        terms: List[str] = []
        for item in raw_terms:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            terms.append(text)
        return terms

    @staticmethod
    def _estimate_token_cost(text: str) -> int:
        """Estimate token cost for heuristic prompt budgeting.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            text: Text input `text` used for parsing, prompt assembly, or display.
        
        Returns:
            int: Integer outcome used for bounds checking and budget control.
        """
        if not text:
            return 0
        cjk_chars = len(AgentMemoryManager.CJK_CHAR_PATTERN.findall(text))
        latin_words = len(AgentMemoryManager.ALNUM_PATTERN.findall(text))
        # Fallback component captures punctuation/whitespace-heavy text.
        fallback = max(0, len(text) - cjk_chars) // 4
        return max(1, cjk_chars + latin_words + fallback)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Parse integer-like values with a safe fallback.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            value: Candidate scalar value to normalize/validate.
            default: Fallback integer used when parsing fails.
        
        Returns:
            int: Integer outcome used for bounds checking and budget control.
        """
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _empty_profile_stats() -> Dict[str, int]:
        """Return default per-session memory stats scaffold.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            Dict[str, int]: Computed value returned to the caller.
        """
        return {
            "clarification_asked": 0,
            "conflict_resolved": 0,
            "attr_pruned": 0,
            "pending_pruned": 0,
            "cross_session_hint_injected": 0,
        }

    def _ensure_profile_stats(self, profile: Dict[str, Any]) -> Dict[str, int]:
        """Ensure profile has canonical stats dictionary and return it.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
        
        Returns:
            Dict[str, int]: Computed value returned to the caller.
        """
        stats = profile.get("stats", {})
        if not isinstance(stats, dict):
            stats = {}
        defaults = self._empty_profile_stats()
        normalized = {
            key: max(0, self._safe_int(stats.get(key, defaults[key])))
            for key in defaults.keys()
        }
        profile["stats"] = normalized
        return normalized

    def _increment_profile_stat(self, profile: Dict[str, Any], key: str, delta: int = 1) -> None:
        """Increment one profile-level memory stat counter.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
            key: Input field `key` used for normalization or matching rules.
            delta: Numeric control parameter `delta` used for bounds or pagination.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if delta == 0:
            return
        stats = self._ensure_profile_stats(profile)
        if key not in stats:
            stats[key] = 0
        stats[key] = max(0, self._safe_int(stats.get(key, 0)) + self._safe_int(delta, 0))

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Parse float-like values with a safe fallback.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            value: Candidate scalar value to normalize/validate.
            default: Fallback float used when parsing fails.
        
        Returns:
            float: Parsed float value after validation and fallback handling.
        """
        try:
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _parse_iso_datetime(timestamp: Any) -> Optional[datetime]:
        """Parse ISO timestamp and return timezone-aware UTC datetime.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            timestamp: Timestamp associated with a memory message for recency weighting.
        
        Returns:
            Optional[datetime]: Computed value returned to the caller.
        """
        if not timestamp:
            return None
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _match_terms_by_synonyms(cls, text: str, synonym_map: Dict[str, tuple[str, ...]]) -> List[str]:
        """Match canonical preference terms by checking canonical labels and aliases in text.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            text: Text input `text` used for parsing, prompt assembly, or display.
            synonym_map: Synonym dictionary mapping canonical labels to alias tuples.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        if not text:
            return []
        lowered = text.lower()
        matched: List[str] = []
        for canonical, aliases in synonym_map.items():
            alias_pool = [canonical, *aliases]
            if any(alias and alias.lower() in lowered for alias in alias_pool):
                matched.append(canonical)
        return matched

    def _merge_preference_terms(self, existing: Any, incoming: List[str], limit: int) -> List[str]:
        """Merge preference term lists with dedupe and bounded retention.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            existing: Existing list-like preference terms stored in profile.
            incoming: Newly extracted canonical terms from current user message.
            limit: Numeric control parameter `limit` used for bounds or pagination.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        base = self._ordered_unique_terms(existing if isinstance(existing, list) else [])
        merged = self._ordered_unique_terms(base + [term for term in incoming if term])
        cap = max(1, int(limit))
        if len(merged) > cap:
            # Keep most recent terms to preserve latest user intent under bounded profile size.
            merged = merged[-cap:]
        return merged

    def _normalize_profile_attr_value(self, key: str, value: Any) -> Any:
        """Normalize profile attribute values to canonical forms for merge stability.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            value: Candidate scalar value to normalize/validate.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        if value is None:
            return None
        if key == "budget_hint":
            num = self._to_number(value)
            if num is not None:
                return f"{int(round(num))}元"
            text = str(value).strip().replace("人民币", "元").replace("RMB", "元").replace("CNY", "元")
            return text.replace(" ", "")
        if key in {"days_hint", "people_hint"}:
            num = self._to_number(value)
            if num is not None:
                return int(round(num))
            return value
        if key == "season_hint":
            text = str(value).strip()
            season_alias = {
                "春季": "春",
                "春天": "春",
                "夏季": "夏",
                "夏天": "夏",
                "秋季": "秋",
                "秋天": "秋",
                "冬季": "冬",
                "冬天": "冬",
            }
            return season_alias.get(text, text)
        return value

    def _cleanup_stale_profile_entries(self, profile: Dict[str, Any]) -> None:
        """Prune low-signal stale profile entries to keep memory compact and relevant.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        attributes = profile.get("attributes", {})
        if isinstance(attributes, dict):
            now = datetime.now(timezone.utc)
            to_delete: List[str] = []
            for key, item in attributes.items():
                if not isinstance(item, dict):
                    to_delete.append(key)
                    continue
                decayed_conf = self._decayed_confidence(item)
                ts = self._parse_iso_datetime(item.get("updated_at"))
                age_hours = ((now - ts).total_seconds() / 3600.0) if ts is not None else float("inf")
                if (
                    decayed_conf < self.ATTRIBUTE_GC_MIN_DECAY_CONFIDENCE
                    and age_hours >= self.ATTRIBUTE_GC_MIN_AGE_HOURS
                ):
                    to_delete.append(key)
            for key in to_delete:
                attributes.pop(key, None)
            if to_delete:
                self._increment_profile_stat(profile, "attr_pruned", len(to_delete))

        profile["interests"] = self._merge_preference_terms(
            profile.get("interests", []),
            incoming=[],
            limit=self.PROFILE_INTEREST_MAX_ITEMS,
        )
        profile["avoid_preferences"] = self._merge_preference_terms(
            profile.get("avoid_preferences", []),
            incoming=[],
            limit=self.PROFILE_AVOID_MAX_ITEMS,
        )

        pending = profile.get("pending_clarifications", [])
        if isinstance(pending, list) and pending:
            now = datetime.now(timezone.utc)
            fresh_pending: List[Any] = []
            for item in pending:
                if not isinstance(item, dict):
                    continue
                state = str(item.get("state", "pending")).lower()
                if state != "pending":
                    continue
                created_at = self._parse_iso_datetime(item.get("created_at"))
                if created_at is None:
                    fresh_pending.append(item)
                    continue
                age_hours = (now - created_at).total_seconds() / 3600.0
                retry_count = self._safe_int(item.get("retry_count", 0) or 0)
                if (
                    retry_count >= self.CLARIFICATION_MAX_ASK_PER_ITEM
                    and age_hours > self.PENDING_CLARIFICATION_EXPIRE_HOURS
                ):
                    # Long-stale unresolved clarifications are dropped to avoid repetitive old noise.
                    continue
                fresh_pending.append(item)
            pruned_count = max(0, len(pending) - len(fresh_pending))
            if pruned_count > 0:
                self._increment_profile_stat(profile, "pending_pruned", pruned_count)
            if len(fresh_pending) > 10:
                fresh_pending = fresh_pending[-10:]
            profile["pending_clarifications"] = fresh_pending

    def _truncate_text_to_token_budget(self, text: str, max_tokens: int) -> str:
        """Truncate text to keep estimated token cost below target budget.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            text: Text input `text` used for parsing, prompt assembly, or display.
            max_tokens: Numeric control parameter `max_tokens` used for bounds or pagination.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        if not text:
            return ""
        max_tokens = max(1, int(max_tokens))
        estimated = self._estimate_token_cost(text)
        if estimated <= max_tokens:
            return text
        keep_ratio = max(0.05, float(max_tokens) / float(max(1, estimated)))
        keep_chars = max(24, int(len(text) * keep_ratio))
        trimmed = text[:keep_chars].rstrip()
        return (trimmed + " ...") if trimmed else text[:24]

    def _build_budgeted_chat_messages(
        self,
        selected_messages: List[MemoryMessage],
        message_budget_tokens: int,
    ) -> List[BaseMessage]:
        """Convert message candidates into model messages under budget constraints.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            selected_messages: Ranked message candidates used for context injection.
            message_budget_tokens: Numeric control parameter `message_budget_tokens` used for bounds or pagination.
        
        Returns:
            List[BaseMessage]: Computed value returned to the caller.
        """
        if not selected_messages:
            return []
        budget = max(0, int(message_budget_tokens))
        min_keep = min(self.MEMORY_MIN_CONTEXT_MESSAGES, len(selected_messages))

        picked: List[tuple[str, str]] = []
        used_tokens = 0
        for msg in reversed(selected_messages):
            truncated = self._truncate_text_to_token_budget(msg.content, self.MEMORY_PER_MESSAGE_TOKEN_BUDGET)
            if not truncated:
                continue
            token_cost = self._estimate_token_cost(truncated) + 4
            if used_tokens + token_cost <= budget or len(picked) < min_keep:
                # Keep latest turns first to preserve near-term conversational continuity.
                picked.append((msg.role, truncated))
                used_tokens += token_cost

        picked.reverse()
        result: List[BaseMessage] = []
        for role, content in picked:
            if role == "assistant":
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        return result

    def _select_top_terms_for_query(self, terms: Any, query_tokens: set[str], top_k: int) -> List[str]:
        """Select top tags/lists with a simple overlap+recency score.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            terms: Input field `terms` used for normalization or matching rules.
            query_tokens: Tokenized query terms used for relevance scoring.
            top_k: Numeric control parameter `top_k` used for bounds or pagination.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        cleaned = self._ordered_unique_terms(terms)
        if not cleaned:
            return []

        scored: List[tuple[float, str]] = []
        total = max(1, len(cleaned))
        for idx, term in enumerate(cleaned):
            # Query overlap keeps currently relevant tags; recency bias keeps newer tags when overlap ties.
            overlap = len(query_tokens & self._tokenize(term)) if query_tokens else 0
            recency_bias = float(total - idx) / float(total)
            score = float(overlap * 2) + recency_bias
            scored.append((score, term))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [term for _, term in scored[: max(1, top_k)]]

    def _build_compact_profile_for_prompt(
        self,
        profile: Dict[str, Any],
        query_tokens: set[str],
        slot_top_k: Optional[int] = None,
        tag_top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Build compact profile payload (Top-K slots) for prompt injection.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
            query_tokens: Tokenized query terms used for relevance scoring.
            slot_top_k: Numeric control parameter `slot_top_k` used for bounds or pagination.
            tag_top_k: Numeric control parameter `tag_top_k` used for bounds or pagination.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        if not isinstance(profile, dict) or not profile:
            return {}
        slot_top_k = max(1, int(slot_top_k or self.PROFILE_SLOT_TOP_K))
        tag_top_k = max(1, int(tag_top_k or self.PROFILE_TAG_TOP_K))

        excluded = {
            "schema_version",
            "updated_at",
            "interests",
            "avoid_preferences",
            "pending_clarifications",
            "_meta",
            "conflict_log",
            "stats",
        }

        meta = profile.get("_meta", {})
        if not isinstance(meta, dict):
            meta = {}

        scored_slots: List[tuple[float, str, Any]] = []
        for key, value in profile.items():
            if key in excluded or value is None:
                continue
            value_text = str(value).strip()
            if not value_text:
                continue
            attr_meta = meta.get(key, {})
            if not isinstance(attr_meta, dict):
                attr_meta = {}
            decayed_conf = float(attr_meta.get("decayed_confidence", 0.5) or 0.5)
            source = str(attr_meta.get("source", "inferred"))
            source_priority = self.SOURCE_PRIORITY.get(source, 1)
            # Slot score balances relevance, freshness confidence and explicitness of source.
            overlap = len(query_tokens & self._tokenize(f"{key} {value_text}")) if query_tokens else 0
            score = float(overlap * 3) + decayed_conf + float(source_priority * 0.15)
            scored_slots.append((score, key, value))

        scored_slots.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected_slots = scored_slots[: slot_top_k]
        compact_slots = {key: value for _, key, value in selected_slots}

        interests = self._select_top_terms_for_query(
            profile.get("interests", []),
            query_tokens=query_tokens,
            top_k=tag_top_k,
        )
        avoid_preferences = self._select_top_terms_for_query(
            profile.get("avoid_preferences", []),
            query_tokens=query_tokens,
            top_k=tag_top_k,
        )

        compact: Dict[str, Any] = {}
        if compact_slots:
            compact["core_slots"] = compact_slots
        if interests:
            compact["interests"] = interests
        if avoid_preferences:
            compact["avoid_preferences"] = avoid_preferences
        return compact

    def _fit_compact_profile_to_budget(
        self,
        profile: Dict[str, Any],
        query_tokens: set[str],
        budget_tokens: int,
    ) -> Dict[str, Any]:
        """Fit compact profile payload to token budget by shrinking slot/tag Top-K values.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
            query_tokens: Tokenized query terms used for relevance scoring.
            budget_tokens: Numeric control parameter `budget_tokens` used for bounds or pagination.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        if not isinstance(profile, dict) or not profile:
            return {}

        slot_k = self.PROFILE_SLOT_TOP_K
        tag_k = self.PROFILE_TAG_TOP_K
        budget = max(1, int(budget_tokens))

        best_payload: Dict[str, Any] = {}
        while slot_k >= 1 and tag_k >= 1:
            payload = self._build_compact_profile_for_prompt(
                profile=profile,
                query_tokens=query_tokens,
                slot_top_k=slot_k,
                tag_top_k=tag_k,
            )
            if not payload:
                return {}
            content = "用户长期偏好(Top-K 槽位):\n" + json.dumps(payload, ensure_ascii=False, indent=2)
            if self._estimate_token_cost(content) <= budget:
                return payload
            best_payload = payload
            if slot_k > 1:
                slot_k -= 1
                continue
            if tag_k > 1:
                tag_k -= 1
                continue
            break

        # Last-resort fallback keeps a minimal shape and removes low-priority tag arrays.
        core_slots = best_payload.get("core_slots", {})
        if isinstance(core_slots, dict) and core_slots:
            first_key = next(iter(core_slots.keys()))
            return {"core_slots": {first_key: core_slots[first_key]}}
        return {}

    def _build_cross_session_preference_hints(
        self,
        session_id: str,
        current_profile: Dict[str, Any],
        query_tokens: set[str],
    ) -> Dict[str, Any]:
        """Build cross-session preference candidates for sparse current-session profiles.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            current_profile: User preference profile snapshot stored in memory manager.
            query_tokens: Tokenized query terms used for relevance scoring.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        if not query_tokens:
            return {}
        if not self._should_inject_cross_session_hints(current_profile):
            return {}

        current_slots = {
            key
            for key, value in (current_profile or {}).items()
            if key not in {"schema_version", "updated_at", "interests", "avoid_preferences", "pending_clarifications", "_meta"}
            and value not in (None, "", [])
        }
        current_interests = set(self._ordered_unique_terms(current_profile.get("interests", [])))
        current_avoids = set(self._ordered_unique_terms(current_profile.get("avoid_preferences", [])))

        attr_best: Dict[str, tuple[float, Any]] = {}
        interest_scores: Dict[str, float] = {}
        avoid_scores: Dict[str, float] = {}

        now = datetime.now(timezone.utc)
        with self._sync_lock:
            for other_session_id, session in self._sessions.items():
                if other_session_id == session_id:
                    continue
                if not isinstance(session, dict):
                    continue
                profile = self._normalize_profile(session.get("profile", {}))
                recency_bonus = self._cross_session_recency_bonus(session, now)

                attrs = profile.get("attributes", {})
                if isinstance(attrs, dict):
                    for key, item in attrs.items():
                        if key in current_slots:
                            continue
                        if not isinstance(item, dict):
                            continue
                        source = str(item.get("source", "inferred"))
                        source_priority = self.SOURCE_PRIORITY.get(source, 1)
                        if source_priority < self.CROSS_SESSION_MIN_SOURCE_PRIORITY:
                            continue
                        decayed_conf = self._decayed_confidence(item)
                        if decayed_conf < self.CROSS_SESSION_MIN_DECAY_CONFIDENCE:
                            continue
                        updated_at = self._parse_iso_datetime(item.get("updated_at"))
                        if updated_at is not None:
                            age_hours = (now - updated_at).total_seconds() / 3600.0
                            if age_hours > self.CROSS_SESSION_LOOKBACK_HOURS:
                                continue
                        value = self._normalize_profile_attr_value(key, item.get("value"))
                        overlap = len(query_tokens & self._tokenize(f"{key} {value}")) if query_tokens else 0
                        score = float(overlap * 2) + decayed_conf + float(source_priority * 0.15) + recency_bonus
                        existing = attr_best.get(key)
                        if existing is None or score > existing[0]:
                            attr_best[key] = (score, value)

                interests = self._ordered_unique_terms(profile.get("interests", []))
                for term in interests:
                    if term in current_interests:
                        continue
                    overlap = len(query_tokens & self._tokenize(term)) if query_tokens else 0
                    score = float(overlap * 2) + recency_bonus
                    interest_scores[term] = max(score, interest_scores.get(term, float("-inf")))

                avoids = self._ordered_unique_terms(profile.get("avoid_preferences", []))
                for term in avoids:
                    if term in current_avoids:
                        continue
                    overlap = len(query_tokens & self._tokenize(term)) if query_tokens else 0
                    score = float(overlap * 2) + recency_bonus
                    avoid_scores[term] = max(score, avoid_scores.get(term, float("-inf")))

        if not attr_best and not interest_scores and not avoid_scores:
            return {}

        attr_ranked = sorted(
            ((score, key, value) for key, (score, value) in attr_best.items()),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )[: self.CROSS_SESSION_ATTR_TOP_K]
        interests_ranked = sorted(
            ((score, term) for term, score in interest_scores.items()),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )[: self.CROSS_SESSION_TERM_TOP_K]
        avoids_ranked = sorted(
            ((score, term) for term, score in avoid_scores.items()),
            key=lambda item: (item[0], item[1]),
            reverse=True,
        )[: self.CROSS_SESSION_TERM_TOP_K]

        hints: Dict[str, Any] = {}
        if attr_ranked:
            hints["core_slots"] = {key: value for _, key, value in attr_ranked}
        if interests_ranked:
            hints["interests"] = [term for _, term in interests_ranked]
        if avoids_ranked:
            hints["avoid_preferences"] = [term for _, term in avoids_ranked]
        return hints

    def _should_inject_cross_session_hints(self, current_profile: Dict[str, Any]) -> bool:
        """Decide whether current session profile is sparse enough to use cross-session hints.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            current_profile: User preference profile snapshot stored in memory manager.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        if not isinstance(current_profile, dict):
            return False
        current_slots = [
            key
            for key, value in current_profile.items()
            if key
            not in {
                "schema_version",
                "updated_at",
                "interests",
                "avoid_preferences",
                "pending_clarifications",
                "_meta",
                "stats",
            }
            and value not in (None, "", [])
        ]
        interests = self._ordered_unique_terms(current_profile.get("interests", []))
        avoids = self._ordered_unique_terms(current_profile.get("avoid_preferences", []))
        is_rich_profile = (
            len(current_slots) >= self.CROSS_SESSION_INJECT_MIN_CORE_SLOTS
            and len(interests) >= self.CROSS_SESSION_INJECT_MIN_INTERESTS
            and len(avoids) >= self.CROSS_SESSION_INJECT_MIN_AVOIDS
        )
        return not is_rich_profile

    def _cross_session_recency_bonus(self, session: Dict[str, Any], now: datetime) -> float:
        """Compute recency bonus for one peer session during cross-session preference ranking.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session: Session snapshot containing messages and profile fields.
            now: Current UTC timestamp used for decay and freshness calculations.
        
        Returns:
            float: Parsed float value after validation and fallback handling.
        """
        latest: Optional[datetime] = None
        messages = session.get("messages", [])
        if isinstance(messages, list) and messages:
            last = messages[-1]
            timestamp = last.timestamp if isinstance(last, MemoryMessage) else None
            latest = self._parse_iso_datetime(timestamp)

        if latest is None:
            profile = session.get("profile", {})
            if isinstance(profile, dict):
                latest = self._parse_iso_datetime(profile.get("updated_at"))

        if latest is None:
            return 0.0

        age_hours = max(0.0, (now - latest).total_seconds() / 3600.0)
        # Slow half-life keeps recently active sessions slightly favored without dominating relevance score.
        return math.pow(0.5, age_hours / 240.0)

    def _fit_cross_session_hints_to_budget(
        self,
        hints: Dict[str, Any],
        budget_tokens: int,
    ) -> Dict[str, Any]:
        """Shrink cross-session hints payload until it fits the configured token budget.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            hints: Cross-session hint payload before budget fitting.
            budget_tokens: Numeric control parameter `budget_tokens` used for bounds or pagination.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        if not isinstance(hints, dict) or not hints:
            return {}
        budget = max(1, int(budget_tokens))

        attr_items = list((hints.get("core_slots") or {}).items())
        interest_items = list(hints.get("interests") or [])
        avoid_items = list(hints.get("avoid_preferences") or [])
        attr_k, interest_k, avoid_k = len(attr_items), len(interest_items), len(avoid_items)

        while attr_k >= 0 and interest_k >= 0 and avoid_k >= 0:
            candidate: Dict[str, Any] = {}
            if attr_k > 0:
                candidate["core_slots"] = {key: value for key, value in attr_items[:attr_k]}
            if interest_k > 0:
                candidate["interests"] = interest_items[:interest_k]
            if avoid_k > 0:
                candidate["avoid_preferences"] = avoid_items[:avoid_k]
            if not candidate:
                return {}

            content = "跨会话稳定偏好候选(仅在本会话缺失时参考):\n" + json.dumps(candidate, ensure_ascii=False, indent=2)
            if self._estimate_token_cost(content) <= budget:
                return candidate

            # Reduce the currently largest section first to preserve overall coverage under tight budget.
            if attr_k >= interest_k and attr_k >= avoid_k and attr_k > 0:
                attr_k -= 1
            elif interest_k >= avoid_k and interest_k > 0:
                interest_k -= 1
            elif avoid_k > 0:
                avoid_k -= 1
            else:
                break
        return {}

    def _increment_session_stat(self, session_id: str, key: str, delta: int = 1) -> None:
        """Increment one stat counter for the given session profile.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session_id: Session identifier used to isolate memory/checkpoint scope.
            key: Input field `key` used for normalization or matching rules.
            delta: Numeric control parameter `delta` used for bounds or pagination.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not session_id or delta == 0:
            return
        with self._sync_lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            profile = self._normalize_profile(session.get("profile", {}))
            session["profile"] = profile
            self._increment_profile_stat(profile, key, delta)

    def _build_conflict_clarification_hint(self, profile: Dict[str, Any], query_tokens: set[str]) -> str:
        """Build a deterministic clarification hint from pending memory conflicts."""

        return self._conflict_resolution.build_conflict_clarification_hint(profile, query_tokens)

    @staticmethod
    def _compose_conflict_clarification_hint(prompts: List[str]) -> str:
        """Compose final clarification hint text from selected prompt lines."""

        return MemoryConflictResolutionHelper.compose_conflict_clarification_hint(prompts)

    def _trim_messages(self, session: Dict[str, Any]) -> None:
        """Trim per-session message history while preserving the configured recency window.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session: Mutable session record containing messages/summary/profile fields.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        keep = max(self.max_history * 3, self.max_history + 6)
        if len(session["messages"]) > keep:
            session["messages"] = session["messages"][-keep:]

    def _update_profile(self, session: Dict[str, Any], role: str, content: str) -> None:
        """Extract and merge long-term preference signals from incoming conversation text.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            session: Mutable session record containing messages/summary/profile fields.
            role: Message role label (user/assistant/system).
            content: Raw text content being normalized or analyzed.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if role != "user":
            return

        text = (content or "").strip()
        if not text:
            return

        profile = session.setdefault("profile", {})
        if not isinstance(profile, dict):
            profile = self._empty_profile()
        profile = self._normalize_profile(profile)
        session["profile"] = profile

        resolution_intent = self._extract_conflict_resolution_intent(text)

        budget_match = re.search(r"(\d{3,6})\s*(元|人民币|rmb|cny)", text, flags=re.IGNORECASE)
        if budget_match:
            self._merge_profile_attr(
                profile,
                key="budget_hint",
                value=f"{budget_match.group(1)}{budget_match.group(2)}",
                source="explicit",
                confidence=0.92,
                force_replace_conflict=self._should_force_replace_for_key("budget_hint", resolution_intent),
            )

        day_match = re.search(r"(\d{1,2})\s*(天|日)", text)
        if day_match:
            try:
                self._merge_profile_attr(
                    profile,
                    key="days_hint",
                    value=int(day_match.group(1)),
                    source="explicit",
                    confidence=0.9,
                    force_replace_conflict=self._should_force_replace_for_key("days_hint", resolution_intent),
                )
            except ValueError:
                pass

        people_match = re.search(r"(\d{1,2})\s*(人|位)", text)
        if people_match:
            try:
                self._merge_profile_attr(
                    profile,
                    key="people_hint",
                    value=int(people_match.group(1)),
                    source="explicit",
                    confidence=0.9,
                    force_replace_conflict=self._should_force_replace_for_key("people_hint", resolution_intent),
                )
            except ValueError:
                pass
        else:
            cn_people_map = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
            for cn_num, numeric in cn_people_map.items():
                if f"{cn_num}个人" in text or f"{cn_num}人" in text:
                    self._merge_profile_attr(
                        profile,
                        key="people_hint",
                        value=numeric,
                        source="explicit",
                        confidence=0.85,
                        force_replace_conflict=self._should_force_replace_for_key("people_hint", resolution_intent),
                    )
                    break

        interest_terms = self._match_terms_by_synonyms(text, self.INTEREST_SYNONYM_MAP)
        if interest_terms:
            profile["interests"] = self._merge_preference_terms(
                profile.get("interests", []),
                incoming=interest_terms,
                limit=self.PROFILE_INTEREST_MAX_ITEMS,
            )

        season_keywords = ["春", "夏", "秋", "冬", "暑假", "寒假"]
        for word in season_keywords:
            if word in text:
                self._merge_profile_attr(
                    profile,
                    key="season_hint",
                    value=word,
                    source="recent_inferred",
                    confidence=0.8,
                    force_replace_conflict=self._should_force_replace_for_key("season_hint", resolution_intent),
                )
                break

        if any(flag in text for flag in ["不要", "不想", "避免", "别", "不喜欢", "怕"]):
            avoid_terms = self._match_terms_by_synonyms(text, self.AVOID_SYNONYM_MAP)
            if avoid_terms:
                profile["avoid_preferences"] = self._merge_preference_terms(
                    profile.get("avoid_preferences", []),
                    incoming=avoid_terms,
                    limit=self.PROFILE_AVOID_MAX_ITEMS,
                )

        profile["schema_version"] = self.PROFILE_SCHEMA_VERSION
        profile["updated_at"] = datetime.now().isoformat()
        self._cleanup_stale_profile_entries(profile)

    def _extract_conflict_resolution_intent(self, text: str) -> Dict[str, Any]:
        """Detect whether the user explicitly resolved a pending preference conflict."""

        return self._conflict_resolution.extract_conflict_resolution_intent(text)

    @staticmethod
    def _should_force_replace_for_key(key: str, resolution_intent: Dict[str, Any]) -> bool:
        """Decide whether one key should accept the latest explicit value immediately."""

        return MemoryConflictResolutionHelper.should_force_replace_for_key(key, resolution_intent)

    def _enforce_capacity_locked(self) -> None:
        """Evict oldest sessions when global in-memory capacity exceeds configured limits.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if len(self._sessions) <= self._max_sessions:
            return

        def _latest_ts(session_data: Dict[str, Any]) -> str:
            """Extract latest message timestamp from one session snapshot.
            
            Purpose:
                Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
            
            Args:
                session_data: Session snapshot containing messages and profile fields.
            
            Returns:
                str: Normalized text string used by downstream logic.
            """
            messages = session_data.get("messages", [])
            if messages:
                return messages[-1].timestamp
            return ""

        overflow = len(self._sessions) - self._max_sessions
        ordered = sorted(self._sessions.items(), key=lambda item: _latest_ts(item[1]))
        for session_id, _ in ordered[:overflow]:
            self._sessions.pop(session_id, None)

    def _cleanup_expired_locked(self) -> None:
        """Cleanup expired sessions and enforce max-session capacity under lock.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        now = datetime.now(timezone.utc)
        ttl = timedelta(seconds=self._session_ttl_seconds)
        expired: List[str] = []
        for session_id, session in self._sessions.items():
            messages = session.get("messages", [])
            if not messages:
                continue
            last_ts = messages[-1].timestamp
            try:
                last_dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                else:
                    last_dt = last_dt.astimezone(timezone.utc)
            except Exception:
                continue
            if now - last_dt > ttl:
                expired.append(session_id)

        for session_id in expired:
            self._sessions.pop(session_id, None)

    def _load_from_disk(self) -> None:
        """Load persisted memory snapshot and normalize schema before serving requests.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not self._persistence_store.enabled:
            return

        raw, recovered_from_backup = self._persistence_store.load_snapshot()
        if raw is None:
            return

        with self._sync_lock:
            self._sessions.clear()
            self._sessions.update(self._deserialize_persisted_sessions(raw))
            self._cleanup_expired_locked()
            self._enforce_capacity_locked()

        if recovered_from_backup:
            try:
                # Write recovered snapshot back to primary to restore canonical file.
                self._persistence_store.restore_primary(raw)
            except Exception:
                # Recovery write-back is best-effort and should not block startup.
                pass

    def _save_to_disk_locked(self) -> None:
        """Persist in-memory sessions to disk under lock protection for crash recovery.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not self._persistence_store.enabled:
            return

        with self._sync_lock:
            serializable = self._serialize_sessions_for_persistence()

        try:
            self._persistence_store.write_snapshot(serializable)
        except Exception:
            # Memory persistence is best-effort only.
            pass

    def _deserialize_persisted_sessions(self, raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Restore persisted sessions into the in-memory runtime shape."""
        restored: Dict[str, Dict[str, Any]] = {}
        for session_id, session in raw.items():
            normalized = self._deserialize_persisted_session(session)
            if normalized is not None:
                restored[session_id] = normalized
        return restored

    def _deserialize_persisted_session(self, session: Any) -> Optional[Dict[str, Any]]:
        """Restore one persisted session payload into the runtime session structure."""
        if not isinstance(session, dict):
            return None
        messages = [
            MemoryMessage(
                role=item.get("role", "user"),
                content=item.get("content", ""),
                timestamp=item.get("timestamp", datetime.now().isoformat()),
            )
            for item in session.get("messages", [])
            if isinstance(item, dict)
        ]
        return {
            "messages": messages,
            "summary": session.get("summary", ""),
            "profile": self._normalize_profile(session.get("profile", {})),
        }

    def _serialize_sessions_for_persistence(self) -> Dict[str, Any]:
        """Serialize all in-memory sessions into the persisted snapshot shape."""
        return {
            session_id: self._serialize_persisted_session(session)
            for session_id, session in self._sessions.items()
        }

    def _serialize_persisted_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize one runtime session into the persisted snapshot structure."""
        return {
            "summary": session.get("summary", ""),
            "profile": self._normalize_profile(session.get("profile", {})),
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                    "timestamp": message.timestamp,
                }
                for message in session.get("messages", [])
            ],
        }

    def _merge_profile_attr(
        self,
        profile: Dict[str, Any],
        key: str,
        value: Any,
        source: str,
        confidence: float,
        force_replace_conflict: bool = False,
    ) -> None:
        """Merge profile attributes using source-priority and confidence rules.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
            key: Input field `key` used for normalization or matching rules.
            value: Candidate scalar value to normalize/validate.
            source: Input field `source` used for normalization or matching rules.
            confidence: Confidence score used when writing inferred profile attributes.
            force_replace_conflict: Whether to force accept explicit resolution over conflict hold.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        source = source if source in self.SOURCE_PRIORITY else "inferred"
        confidence = max(0.0, min(1.0, float(confidence)))
        value = self._normalize_profile_attr_value(key, value)
        now = datetime.now().isoformat()

        attributes = profile.setdefault("attributes", {})
        existing = attributes.get(key)
        if isinstance(existing, dict):
            existing["value"] = self._normalize_profile_attr_value(key, existing.get("value"))
        if not existing:
            attributes[key] = {
                "value": value,
                "source": source,
                "confidence": confidence,
                "updated_at": now,
            }
            return

        conflict = self._detect_preference_conflict(
            key=key,
            existing=existing if isinstance(existing, dict) else {},
            new_value=value,
            new_source=source,
        )
        if conflict is not None:
            if force_replace_conflict:
                # User explicitly selected a side (for example "按这次预算为准"), so close the conflict loop.
                attributes[key] = {
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "updated_at": now,
                }
                self._resolve_pending_clarifications(
                    profile=profile,
                    key=key,
                    now=now,
                    resolution_source="explicit_override",
                    new_value=value,
                    default_old_value=existing.get("value"),
                )
                return
            self._record_conflict(profile, key=key, conflict=conflict, now=now)
            return

        existing_priority = self.SOURCE_PRIORITY.get(existing.get("source", "inferred"), 1)
        new_priority = self.SOURCE_PRIORITY.get(source, 1)
        existing_conf = float(existing.get("confidence", 0))
        should_replace = False
        if new_priority > existing_priority:
            should_replace = True
        elif new_priority == existing_priority and confidence >= existing_conf:
            should_replace = True

        if should_replace:
            old_value = existing.get("value")
            attributes[key] = {
                "value": value,
                "source": source,
                "confidence": confidence,
                "updated_at": now,
            }
            if source == "explicit":
                # Explicit updates should resolve stale pending clarifications on the same key.
                self._resolve_pending_clarifications(
                    profile=profile,
                    key=key,
                    now=now,
                    resolution_source="explicit_update",
                    new_value=value,
                    default_old_value=old_value,
                )

    def _resolve_pending_clarifications(
        self,
        profile: Dict[str, Any],
        key: str,
        now: str,
        resolution_source: str,
        new_value: Any,
        default_old_value: Any = None,
    ) -> None:
        """Resolve pending clarification entries and persist matching resolution traces."""

        self._conflict_resolution.resolve_pending_clarifications(
            profile=profile,
            key=key,
            now=now,
            resolution_source=resolution_source,
            new_value=new_value,
            default_old_value=default_old_value,
        )

    def _mark_conflict_log_resolved(
        self,
        profile: Dict[str, Any],
        key: str,
        now: str,
        resolution_source: str,
        resolved_value: Any,
    ) -> None:
        """Mark the latest unresolved conflict log entry for one key as resolved."""

        self._conflict_resolution.mark_conflict_log_resolved(
            profile=profile,
            key=key,
            now=now,
            resolution_source=resolution_source,
            resolved_value=resolved_value,
        )

    def _append_conflict_resolution_log(
        self,
        profile: Dict[str, Any],
        key: str,
        old_value: Any,
        new_value: Any,
        now: str,
        resolution_source: str,
        retry_count: int = 0,
        asked_at: Optional[str] = None,
    ) -> None:
        """Append an explicit conflict-resolution record for auditability."""

        self._conflict_resolution.append_conflict_resolution_log(
            profile=profile,
            key=key,
            old_value=old_value,
            new_value=new_value,
            now=now,
            resolution_source=resolution_source,
            retry_count=retry_count,
            asked_at=asked_at,
        )

    @staticmethod
    def _normalize_conflict_entry(item: Any) -> Optional[Dict[str, Any]]:
        """Normalize one conflict-log entry into the canonical persisted schema."""

        return MemoryConflictResolutionHelper.normalize_conflict_entry(item)

    @staticmethod
    def _normalize_pending_clarification(item: Any) -> Optional[Dict[str, Any]]:
        """Normalize one pending clarification entry for retry-state management."""

        return MemoryConflictResolutionHelper.normalize_pending_clarification(item)

    def _empty_profile(self) -> Dict[str, Any]:
        """Build an empty profile scaffold for new sessions.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return {
            "schema_version": self.PROFILE_SCHEMA_VERSION,
            "updated_at": datetime.now().isoformat(),
            "attributes": {},
            "interests": [],
            "avoid_preferences": [],
            "conflict_log": [],
            "pending_clarifications": [],
            "stats": self._empty_profile_stats(),
        }

    def _normalize_profile(self, profile: Any) -> Dict[str, Any]:
        """Normalize profile into canonical format.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        if not isinstance(profile, dict):
            return self._empty_profile()

        schema_version = int(profile.get("schema_version", 1))
        if schema_version >= self.PROFILE_SCHEMA_VERSION and "attributes" in profile:
            normalized_conflict_log = [
                entry
                for entry in (
                    self._normalize_conflict_entry(item) for item in profile.get("conflict_log", [])
                )
                if entry is not None
            ]
            normalized_pending = [
                entry
                for entry in (
                    self._normalize_pending_clarification(item)
                    for item in profile.get("pending_clarifications", [])
                )
                if entry is not None
            ]
            normalized = {
                "schema_version": self.PROFILE_SCHEMA_VERSION,
                "updated_at": profile.get("updated_at", datetime.now().isoformat()),
                "attributes": dict(profile.get("attributes", {})),
                "interests": list(profile.get("interests", [])),
                "avoid_preferences": list(profile.get("avoid_preferences", [])),
                "conflict_log": normalized_conflict_log,
                "pending_clarifications": normalized_pending,
                "stats": dict(profile.get("stats", {})),
            }
            self._ensure_profile_stats(normalized)
            self._cleanup_stale_profile_entries(normalized)
            return normalized

        # v1 -> v2 migration: flatten keys into attributes.
        migrated = self._empty_profile()
        for key in ["budget_hint", "days_hint", "people_hint", "season_hint"]:
            if key in profile:
                self._merge_profile_attr(
                    migrated,
                    key=key,
                    value=profile.get(key),
                    source="inferred",
                    confidence=0.6,
                )
        migrated["interests"] = list(profile.get("interests", []))
        migrated["avoid_preferences"] = list(profile.get("avoid_preferences", []))
        migrated["updated_at"] = profile.get("updated_at", datetime.now().isoformat())
        migrated["conflict_log"] = [
            entry
            for entry in (
                self._normalize_conflict_entry(item) for item in profile.get("conflict_log", [])
            )
            if entry is not None
        ]
        migrated["pending_clarifications"] = [
            entry
            for entry in (
                self._normalize_pending_clarification(item)
                for item in profile.get("pending_clarifications", [])
            )
            if entry is not None
        ]
        migrated["stats"] = self._empty_profile_stats()
        self._ensure_profile_stats(migrated)
        self._cleanup_stale_profile_entries(migrated)
        return migrated

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        """Convert arbitrary values to numeric form when possible.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            value: Candidate scalar value to normalize/validate.
        
        Returns:
            Optional[float]: Computed value returned to the caller.
        """
        if value is None:
            return None
        try:
            text = str(value).strip().lower().replace(",", "")
            text = text.replace("cny", "").replace("rmb", "").replace("元", "")
            return float(text)
        except Exception:
            return None

    def _detect_preference_conflict(
        self,
        key: str,
        existing: Dict[str, Any],
        new_value: Any,
        new_source: str,
    ) -> Optional[Dict[str, Any]]:
        """Detect contradictory preference updates and emit clarification metadata."""

        return self._conflict_resolution.detect_preference_conflict(key, existing, new_value, new_source)

    def _record_conflict(self, profile: Dict[str, Any], key: str, conflict: Dict[str, Any], now: str) -> None:
        """Record a preference conflict into audit log and pending clarification queue."""

        self._conflict_resolution.record_conflict(profile, key, conflict, now)

    @staticmethod
    def _time_decay_factor(timestamp: str) -> float:
        """Compute confidence decay factor from attribute freshness.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            timestamp: Timestamp associated with a memory message for recency weighting.
        
        Returns:
            float: Parsed float value after validation and fallback handling.
        """
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            age_hours = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0)
            return math.pow(0.5, age_hours / AgentMemoryManager.DECAY_HALF_LIFE_HOURS)
        except Exception:
            return 0.5

    def _decayed_confidence(self, attr: Dict[str, Any]) -> float:
        """Apply time decay and return effective confidence score.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            attr: Input field `attr` used for normalization or matching rules.
        
        Returns:
            float: Parsed float value after validation and fallback handling.
        """
        base = float(attr.get("confidence", 0.0) or 0.0)
        updated_at = str(attr.get("updated_at") or "")
        decay = self._time_decay_factor(updated_at) if updated_at else 0.6
        return max(0.0, min(1.0, base * decay))

    def _attributes_with_decay(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        """Return profile attributes annotated with decayed confidence.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            attrs: Input field `attrs` used for normalization or matching rules.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        output: Dict[str, Any] = {}
        for key, item in attrs.items():
            if not isinstance(item, dict):
                continue
            output[key] = {
                **item,
                "decayed_confidence": round(self._decayed_confidence(item), 4),
            }
        return output

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into lowercase keyword set for matching.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            text: Text input `text` used for parsing, prompt assembly, or display.
        
        Returns:
            set[str]: Computed value returned to the caller.
        """
        tokens = AgentMemoryManager.TOKEN_PATTERN.findall(text or "")
        return {token.lower() for token in tokens if token}


class AgentStateWithMemory:
    """Factory helper to build initial agent state with conversation memory."""

    @staticmethod
    def create(
        user_message: str,
        session_id: str,
        memory_manager: AgentMemoryManager,
        system_prompt: str,
        chat_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create initial agent state enriched with memory context.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            user_message: Raw user request text for this run.
            session_id: Session identifier used to isolate memory/checkpoint scope.
            memory_manager: Session memory manager used to build context and persist message memory.
            system_prompt: System prompt text injected at the beginning of model context.
            chat_mode: Requested orchestration mode such as direct/react/plan.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]

        if memory_manager is not None:
            messages.extend(memory_manager.build_context_messages_for_query(session_id, user_message, max_messages=8))

        messages.append(HumanMessage(content=user_message))

        return {
            "messages": messages,
            "chat_mode": chat_mode,
            "intent": None,
            "intent_detail": None,
            "strategy": None,
            "strategy_detail": None,
            "routing": None,
            "plan_id": None,
            "plan_explanation": None,
            "plan": None,
            "current_step": 0,
            "execution_round": 0,
            "parallelism": None,
            "max_parallelism": None,
            "execution_state": None,
            "execution_stats": None,
            "execution_summary": None,
            "execution_trace": [],
            "execution_budget": None,
            "fused_tool_results": None,
            "early_stop_reason": None,
            "verify_retry_count": 0,
            "verify_result": None,
            "self_check_result": None,
            "tools_used": [],
            "tool_results": {},
            "answer": None,
            "reasoning": None,
            "session_id": session_id,
            "error": None,
        }


_DEFAULT_MANAGER: Optional[AgentMemoryManager] = None
_DEFAULT_LOCK = threading.Lock()
_DEFAULT_MANAGER_KEY: Optional[tuple[int, int, int]] = None


def get_agent_memory_manager(
    llm: Any = None,
    max_history: int = 10,
    summary_threshold: int = 20,
    session_ttl_seconds: int = 7 * 24 * 3600,
) -> AgentMemoryManager:
    """Return process-wide shared memory manager for agent sessions."""

    global _DEFAULT_MANAGER, _DEFAULT_MANAGER_KEY
    config_key = (max_history, summary_threshold, session_ttl_seconds)
    if _DEFAULT_MANAGER is not None and _DEFAULT_MANAGER_KEY == config_key:
        return _DEFAULT_MANAGER

    with _DEFAULT_LOCK:
        if _DEFAULT_MANAGER is not None and _DEFAULT_MANAGER_KEY == config_key:
            return _DEFAULT_MANAGER

        persist_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "..",
            "data",
            "agent_memory.json",
        )
        persist_path = os.path.abspath(persist_path)

        _DEFAULT_MANAGER = AgentMemoryManager(
            llm=llm,
            max_history=max_history,
            summary_threshold=summary_threshold,
            persist_path=persist_path,
            session_ttl_seconds=session_ttl_seconds,
        )
        _DEFAULT_MANAGER_KEY = config_key

    return _DEFAULT_MANAGER
