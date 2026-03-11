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
        if self._persist_path:
            self._load_from_disk()

    PROFILE_SCHEMA_VERSION = 2
    SOURCE_PRIORITY = {"inferred": 1, "recent_inferred": 2, "explicit": 3}
    DECAY_HALF_LIFE_HOURS = 72.0
    MIN_DECAY_CONFIDENCE = 0.25

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

        context: List[BaseMessage] = []
        if summary:
            context.append(SystemMessage(content=f"会话摘要:\n{summary}"))
        if profile:
            context.append(
                SystemMessage(
                    content="用户长期偏好:\n" + json.dumps(profile, ensure_ascii=False, indent=2),
                )
            )

        for msg in recent:
            if msg.role == "assistant":
                context.append(AIMessage(content=msg.content))
            else:
                context.append(HumanMessage(content=msg.content))

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

        context: List[BaseMessage] = []
        if summary:
            context.append(SystemMessage(content=f"会话摘要:\n{summary}"))
        if profile:
            context.append(
                SystemMessage(
                    content="用户长期偏好:\n" + json.dumps(profile, ensure_ascii=False, indent=2),
                )
            )
            pending = profile.get("pending_clarifications", [])
            if pending:
                prompts = [str(item.get("prompt", "")).strip() for item in pending[:2] if isinstance(item, dict)]
                prompts = [item for item in prompts if item]
                if prompts:
                    context.append(
                        SystemMessage(
                            content="偏好冲突待澄清:\n- " + "\n- ".join(prompts),
                        )
                    )

        for msg in selected:
            if msg.role == "assistant":
                context.append(AIMessage(content=msg.content))
            else:
                context.append(HumanMessage(content=msg.content))
        return context

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

        budget_match = re.search(r"(\d{3,6})\s*(元|人民币|rmb|cny)", text, flags=re.IGNORECASE)
        if budget_match:
            self._merge_profile_attr(
                profile,
                key="budget_hint",
                value=f"{budget_match.group(1)}{budget_match.group(2)}",
                source="explicit",
                confidence=0.92,
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
                    )
                    break

        interest_keywords = [
            "美食",
            "亲子",
            "博物馆",
            "摄影",
            "徒步",
            "自然",
            "历史",
            "海边",
            "滑雪",
            "购物",
            "夜景",
        ]
        interests = set(profile.get("interests", []))
        for word in interest_keywords:
            if word in text:
                interests.add(word)
        if interests:
            profile["interests"] = sorted(interests)

        season_keywords = ["春", "夏", "秋", "冬", "暑假", "寒假"]
        for word in season_keywords:
            if word in text:
                self._merge_profile_attr(
                    profile,
                    key="season_hint",
                    value=word,
                    source="recent_inferred",
                    confidence=0.8,
                )
                break

        if "不要" in text or "不想" in text or "避免" in text:
            avoids = set(profile.get("avoid_preferences", []))
            avoid_candidates = ["人多", "排队", "贵", "早起", "爬山", "舟车劳顿"]
            for word in avoid_candidates:
                if word in text:
                    avoids.add(word)
            if avoids:
                profile["avoid_preferences"] = sorted(avoids)

        profile["schema_version"] = self.PROFILE_SCHEMA_VERSION
        profile["updated_at"] = datetime.now().isoformat()

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
        if not self._persist_path or not os.path.exists(self._persist_path):
            return

        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return

        with self._sync_lock:
            for session_id, session in raw.items():
                msgs = [
                    MemoryMessage(
                        role=item.get("role", "user"),
                        content=item.get("content", ""),
                        timestamp=item.get("timestamp", datetime.now().isoformat()),
                    )
                    for item in session.get("messages", [])
                ]
                self._sessions[session_id] = {
                    "messages": msgs,
                    "summary": session.get("summary", ""),
                    "profile": self._normalize_profile(session.get("profile", {})),
                }
            self._cleanup_expired_locked()
            self._enforce_capacity_locked()

    def _save_to_disk_locked(self) -> None:
        """Persist in-memory sessions to disk under lock protection for crash recovery.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if not self._persist_path:
            return

        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)

        with self._sync_lock:
            serializable: Dict[str, Any] = {}
            for session_id, session in self._sessions.items():
                serializable[session_id] = {
                    "summary": session.get("summary", ""),
                    "profile": self._normalize_profile(session.get("profile", {})),
                    "messages": [
                        {
                            "role": m.role,
                            "content": m.content,
                            "timestamp": m.timestamp,
                        }
                        for m in session.get("messages", [])
                    ],
                }

        try:
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception:
            # Memory persistence is best-effort only.
            pass

    def _merge_profile_attr(
        self,
        profile: Dict[str, Any],
        key: str,
        value: Any,
        source: str,
        confidence: float,
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
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        source = source if source in self.SOURCE_PRIORITY else "inferred"
        confidence = max(0.0, min(1.0, float(confidence)))
        now = datetime.now().isoformat()

        attributes = profile.setdefault("attributes", {})
        existing = attributes.get(key)
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
            attributes[key] = {
                "value": value,
                "source": source,
                "confidence": confidence,
                "updated_at": now,
            }

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
            normalized = {
                "schema_version": self.PROFILE_SCHEMA_VERSION,
                "updated_at": profile.get("updated_at", datetime.now().isoformat()),
                "attributes": dict(profile.get("attributes", {})),
                "interests": list(profile.get("interests", [])),
                "avoid_preferences": list(profile.get("avoid_preferences", [])),
                "conflict_log": list(profile.get("conflict_log", [])),
                "pending_clarifications": list(profile.get("pending_clarifications", [])),
            }
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
        migrated["conflict_log"] = list(profile.get("conflict_log", []))
        migrated["pending_clarifications"] = list(profile.get("pending_clarifications", []))
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
        """Detect contradictory preference updates and emit conflict metadata for clarification.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            existing: Existing profile attribute value before merge/overwrite decisions.
            new_value: Input field `new_value` used for normalization or matching rules.
            new_source: Input field `new_source` used for normalization or matching rules.
        
        Returns:
            Optional[Dict[str, Any]]: Computed value returned to the caller.
        """
        old_value = existing.get("value")
        if old_value is None:
            return None
        if key == "budget_hint":
            old_num = self._to_number(old_value)
            new_num = self._to_number(new_value)
            if old_num and new_num:
                ratio = max(old_num, new_num) / max(1.0, min(old_num, new_num))
                if ratio >= 2.0 and abs(old_num - new_num) >= 3000:
                    return {
                        "type": "budget_conflict",
                        "old_value": old_value,
                        "new_value": new_value,
                        "severity": "high",
                        "prompt": f"你之前预算偏好是 {old_value}，这次是 {new_value}。本次按哪个预算执行？",
                        "new_source": new_source,
                    }
        if key == "days_hint":
            old_num = self._to_number(old_value)
            new_num = self._to_number(new_value)
            if old_num is not None and new_num is not None and abs(old_num - new_num) >= 3:
                return {
                    "type": "days_conflict",
                    "old_value": old_value,
                    "new_value": new_value,
                    "severity": "medium",
                    "prompt": f"你之前常用天数是 {int(old_num)} 天，这次是 {int(new_num)} 天。按哪一个规划？",
                    "new_source": new_source,
                }
        if key == "people_hint":
            old_num = self._to_number(old_value)
            new_num = self._to_number(new_value)
            if old_num is not None and new_num is not None and abs(old_num - new_num) >= 2:
                return {
                    "type": "people_conflict",
                    "old_value": old_value,
                    "new_value": new_value,
                    "severity": "medium",
                    "prompt": f"你之前出行人数偏好是 {int(old_num)} 人，这次是 {int(new_num)} 人。本次按哪个人数？",
                    "new_source": new_source,
                }
        if key == "season_hint" and str(old_value).strip() != str(new_value).strip():
            return {
                "type": "season_conflict",
                "old_value": old_value,
                "new_value": new_value,
                "severity": "low",
                "prompt": f"你之前季节偏好是 {old_value}，这次是 {new_value}。本次按哪个季节建议？",
                "new_source": new_source,
            }
        return None

    def _record_conflict(self, profile: Dict[str, Any], key: str, conflict: Dict[str, Any], now: str) -> None:
        """Record preference conflicts for later prompts and profile reconciliation.
        
        Purpose:
            Explain how this routine updates graph state, tool execution flow, and downstream decision logic.
        
        Args:
            profile: User preference profile snapshot stored in memory manager.
            key: Input field `key` used for normalization or matching rules.
            conflict: Conflict descriptor generated when incoming and stored values disagree.
            now: Current UTC timestamp used for decay and freshness calculations.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        entry = {
            "key": key,
            "type": conflict.get("type"),
            "old_value": conflict.get("old_value"),
            "new_value": conflict.get("new_value"),
            "severity": conflict.get("severity", "medium"),
            "prompt": conflict.get("prompt"),
            "created_at": now,
        }
        conflict_log = profile.setdefault("conflict_log", [])
        conflict_log.append(entry)
        if len(conflict_log) > 50:
            del conflict_log[:-50]

        pending = profile.setdefault("pending_clarifications", [])
        same_key_items = [item for item in pending if isinstance(item, dict) and item.get("key") == key]
        if not same_key_items:
            pending.append(entry)
        if len(pending) > 10:
            del pending[:-10]

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
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]+", text or "")
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
