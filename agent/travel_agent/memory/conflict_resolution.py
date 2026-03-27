"""Conflict-detection and clarification helpers for session memory profiles."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


class MemoryConflictResolutionHelper:
    """Encapsulate preference conflict detection, prompting, and resolution traces."""

    def __init__(self, manager: Any):
        """Bind the helper to the owning memory manager instance."""

        self._manager = manager

    def build_clarification_turn_fingerprint(self, user_message: str, query_tokens: set[str]) -> str:
        """Build a stable per-turn fingerprint for clarification retry deduplication."""

        normalized = " ".join(sorted(token for token in query_tokens if token))
        if normalized:
            return f"query_tokens:{normalized[:128]}"
        short = (user_message or "").strip().lower().replace("\n", " ")
        return f"query_text:{short[:128]}"

    def consume_conflict_clarification_hint(
        self,
        session_id: str,
        query_tokens: set[str],
        turn_fingerprint: str,
    ) -> str:
        """Consume eligible pending clarifications for one user turn and update retry state."""

        manager = self._manager
        with manager._sync_lock:
            session = manager._sessions.get(session_id)
            if not session:
                return ""
            profile = manager._normalize_profile(session.get("profile", {}))
            session["profile"] = profile
            pending = profile.get("pending_clarifications", [])
            if not isinstance(pending, list) or not pending:
                return ""

            scored: List[tuple[float, Dict[str, Any], str]] = []
            total = max(1, len(pending))
            for idx, item in enumerate(pending):
                if not isinstance(item, dict):
                    continue
                if str(item.get("state", "pending")).lower() != "pending":
                    continue
                retry_count = manager._safe_int(item.get("retry_count", 0) or 0)
                last_fingerprint = str(item.get("last_asked_fingerprint", "")).strip()
                if retry_count >= manager.CLARIFICATION_MAX_ASK_PER_ITEM and last_fingerprint != turn_fingerprint:
                    continue
                prompt = str(item.get("prompt", "")).strip()
                if not prompt:
                    continue
                severity = str(item.get("severity", "medium")).lower()
                severity_weight = manager.CLARIFICATION_SEVERITY_PRIORITY.get(severity, 2)
                focus_text = " ".join(
                    [
                        str(item.get("key", "")),
                        str(item.get("old_value", "")),
                        str(item.get("new_value", "")),
                        prompt,
                    ]
                )
                overlap = len(query_tokens & manager._tokenize(focus_text)) if query_tokens else 0
                recency = float(idx + 1) / float(total)
                score = float(severity_weight * 1.5) + float(overlap * 2) + recency
                scored.append((score, item, prompt))

            if not scored:
                return ""

            scored.sort(key=lambda item: (item[0], item[2]), reverse=True)
            now = datetime.now().isoformat()
            prompts: List[str] = []
            seen: set[str] = set()
            for _, item, prompt in scored:
                if prompt in seen:
                    continue
                last_fingerprint = str(item.get("last_asked_fingerprint", "")).strip()
                if last_fingerprint != turn_fingerprint:
                    # Retry is counted per user turn, so repeated helper calls in one turn do not burn quota.
                    item["retry_count"] = manager._safe_int(item.get("retry_count", 0) or 0) + 1
                    item["asked_at"] = now
                    item["last_asked_fingerprint"] = turn_fingerprint
                    manager._increment_profile_stat(profile, "clarification_asked", 1)
                prompts.append(prompt)
                seen.add(prompt)
                if len(prompts) >= manager.CLARIFICATION_TOP_K:
                    break

            return self.compose_conflict_clarification_hint(prompts)

    def build_conflict_clarification_hint(self, profile: Dict[str, Any], query_tokens: set[str]) -> str:
        """Rank pending preference conflicts and compose a deterministic clarification hint."""

        manager = self._manager
        if not isinstance(profile, dict):
            return ""

        pending = profile.get("pending_clarifications", [])
        if not isinstance(pending, list) or not pending:
            return ""

        scored: List[tuple[float, str]] = []
        total = max(1, len(pending))
        for idx, item in enumerate(pending):
            if not isinstance(item, dict):
                continue
            if str(item.get("state", "pending")).lower() != "pending":
                continue
            retry_count = manager._safe_int(item.get("retry_count", 0) or 0)
            if retry_count >= manager.CLARIFICATION_MAX_ASK_PER_ITEM:
                continue
            prompt = str(item.get("prompt", "")).strip()
            if not prompt:
                continue
            severity = str(item.get("severity", "medium")).lower()
            severity_weight = manager.CLARIFICATION_SEVERITY_PRIORITY.get(severity, 2)
            focus_text = " ".join(
                [
                    str(item.get("key", "")),
                    str(item.get("old_value", "")),
                    str(item.get("new_value", "")),
                    prompt,
                ]
            )
            overlap = len(query_tokens & manager._tokenize(focus_text)) if query_tokens else 0
            recency = float(idx + 1) / float(total)
            score = float(severity_weight * 1.5) + float(overlap * 2) + recency
            scored.append((score, prompt))

        if not scored:
            return ""

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        prompts: List[str] = []
        seen: set[str] = set()
        for _, prompt in scored:
            if prompt in seen:
                continue
            prompts.append(prompt)
            seen.add(prompt)
            if len(prompts) >= manager.CLARIFICATION_TOP_K:
                break

        if not prompts:
            return ""
        return self.compose_conflict_clarification_hint(prompts)

    @staticmethod
    def compose_conflict_clarification_hint(prompts: List[str]) -> str:
        """Compose final clarification helper text shown to the agent runtime."""

        if not prompts:
            return ""
        return (
            "偏好冲突自动澄清:\n- "
            + "\n- ".join(prompts)
            + "\n请先用 1 句确认冲突偏好，再继续提供可执行建议；若用户本轮已明确选择，则直接按最新选择执行。"
        )

    def extract_conflict_resolution_intent(self, text: str) -> Dict[str, Any]:
        """Detect explicit user language that resolves a previously pending preference conflict."""

        markers = ["为准", "按这次", "以这次", "按最新", "以最新", "就按", "本次按", "这次按"]
        force_all_markers = ["按最新", "以最新", "按这次", "以这次", "本次按", "这次按"]
        has_resolution_marker = any(marker in text for marker in markers)
        if not has_resolution_marker:
            return {"force_all": False, "keys": set()}

        keys: set[str] = set()
        if any(word in text for word in ["预算", "花费", "开销", "元", "人民币", "rmb", "cny"]):
            keys.add("budget_hint")
        if re.search(r"\d{1,2}\s*(天|日)", text) or any(word in text for word in ["天数", "行程天数", "日程"]):
            keys.add("days_hint")
        if re.search(r"\d{1,2}\s*(人|位)", text) or any(word in text for word in ["人数", "同行", "大人", "小孩"]):
            keys.add("people_hint")
        if any(word in text for word in ["季节", "月份", "春", "夏", "秋", "冬", "暑假", "寒假"]):
            keys.add("season_hint")

        return {"force_all": any(marker in text for marker in force_all_markers), "keys": keys}

    @staticmethod
    def should_force_replace_for_key(key: str, resolution_intent: Dict[str, Any]) -> bool:
        """Decide whether one profile key should accept the latest explicit value immediately."""

        force_all = bool(resolution_intent.get("force_all"))
        keyed = resolution_intent.get("keys", set())
        if not isinstance(keyed, set):
            keyed = set()
        return force_all or key in keyed

    def resolve_pending_clarifications(
        self,
        profile: Dict[str, Any],
        key: str,
        now: str,
        resolution_source: str,
        new_value: Any,
        default_old_value: Any = None,
    ) -> None:
        """Resolve pending clarification entries and persist matching resolution traces."""

        manager = self._manager
        pending = profile.get("pending_clarifications", [])
        if not isinstance(pending, list) or not pending:
            return

        remaining: List[Any] = []
        resolved_entries: List[Dict[str, Any]] = []
        for item in pending:
            if not isinstance(item, dict):
                remaining.append(item)
                continue
            if item.get("key") != key:
                remaining.append(item)
                continue
            state = str(item.get("state", "pending")).lower()
            if state == "resolved":
                continue
            item["state"] = "resolved"
            item["resolved_at"] = now
            item["resolution_source"] = resolution_source
            resolved_entries.append(dict(item))
        profile["pending_clarifications"] = remaining

        if not resolved_entries:
            return

        self.mark_conflict_log_resolved(
            profile=profile,
            key=key,
            now=now,
            resolution_source=resolution_source,
            resolved_value=new_value,
        )
        for item in resolved_entries:
            self.append_conflict_resolution_log(
                profile=profile,
                key=key,
                old_value=item.get("old_value", default_old_value),
                new_value=new_value,
                now=now,
                resolution_source=resolution_source,
                retry_count=manager._safe_int(item.get("retry_count", 0) or 0),
                asked_at=item.get("asked_at"),
            )
        manager._increment_profile_stat(profile, "conflict_resolved", len(resolved_entries))

    def mark_conflict_log_resolved(
        self,
        profile: Dict[str, Any],
        key: str,
        now: str,
        resolution_source: str,
        resolved_value: Any,
    ) -> None:
        """Mark the latest unresolved conflict-log entry for one key as resolved."""

        conflict_log = profile.get("conflict_log", [])
        if not isinstance(conflict_log, list) or not conflict_log:
            return
        for entry in reversed(conflict_log):
            if not isinstance(entry, dict):
                continue
            if entry.get("key") != key:
                continue
            if str(entry.get("state", "pending")).lower() == "resolved":
                continue
            if str(entry.get("type")) == "conflict_resolved":
                continue
            entry["state"] = "resolved"
            entry["resolved_at"] = now
            entry["resolution_source"] = resolution_source
            entry["resolved_value"] = resolved_value
            return

    def append_conflict_resolution_log(
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

        manager = self._manager
        conflict_log = profile.setdefault("conflict_log", [])
        if not isinstance(conflict_log, list):
            profile["conflict_log"] = []
            conflict_log = profile["conflict_log"]
        conflict_log.append(
            {
                "key": key,
                "type": "conflict_resolved",
                "old_value": old_value,
                "new_value": new_value,
                "severity": "info",
                "prompt": None,
                "created_at": now,
                "state": "resolved",
                "asked_at": asked_at,
                "retry_count": max(0, manager._safe_int(retry_count)),
                "resolved_at": now,
                "resolution_source": resolution_source,
            }
        )
        if len(conflict_log) > 50:
            del conflict_log[:-50]

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Parse integer-like values with a safe fallback for schema normalization."""

        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def normalize_conflict_entry(cls, item: Any) -> Optional[Dict[str, Any]]:
        """Normalize one conflict-log entry into the canonical persisted schema."""

        if not isinstance(item, dict):
            return None
        retry_count = cls._safe_int(item.get("retry_count", 0) or 0)
        state = str(item.get("state", "pending")).lower()
        if state not in {"pending", "resolved"}:
            state = "pending"
        return {
            "key": item.get("key"),
            "type": item.get("type"),
            "old_value": item.get("old_value"),
            "new_value": item.get("new_value"),
            "severity": item.get("severity", "medium"),
            "prompt": item.get("prompt"),
            "created_at": item.get("created_at", datetime.now().isoformat()),
            "state": state,
            "asked_at": item.get("asked_at"),
            "retry_count": max(0, retry_count),
            "resolved_at": item.get("resolved_at"),
            "resolution_source": item.get("resolution_source"),
            "resolved_value": item.get("resolved_value"),
        }

    @classmethod
    def normalize_pending_clarification(cls, item: Any) -> Optional[Dict[str, Any]]:
        """Normalize one pending clarification entry while preserving retry-fingerprint state."""

        normalized = cls.normalize_conflict_entry(item)
        if normalized is None:
            return None
        normalized["last_asked_fingerprint"] = (
            item.get("last_asked_fingerprint") if isinstance(item, dict) else None
        )
        if str(normalized.get("state", "pending")).lower() == "resolved":
            return None
        return normalized

    def detect_preference_conflict(
        self,
        key: str,
        existing: Dict[str, Any],
        new_value: Any,
        new_source: str,
    ) -> Optional[Dict[str, Any]]:
        """Detect contradictory preference updates and emit clarification metadata."""

        manager = self._manager
        old_value = existing.get("value")
        if old_value is None:
            return None
        if key == "budget_hint":
            old_num = manager._to_number(old_value)
            new_num = manager._to_number(new_value)
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
            old_num = manager._to_number(old_value)
            new_num = manager._to_number(new_value)
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
            old_num = manager._to_number(old_value)
            new_num = manager._to_number(new_value)
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

    def record_conflict(self, profile: Dict[str, Any], key: str, conflict: Dict[str, Any], now: str) -> None:
        """Record one preference conflict into both audit log and pending clarification queue."""

        entry = {
            "key": key,
            "type": conflict.get("type"),
            "old_value": conflict.get("old_value"),
            "new_value": conflict.get("new_value"),
            "severity": conflict.get("severity", "medium"),
            "prompt": conflict.get("prompt"),
            "created_at": now,
            "state": "pending",
            "asked_at": None,
            "retry_count": 0,
            "resolved_at": None,
            "resolution_source": None,
            "last_asked_fingerprint": None,
        }
        conflict_log = profile.setdefault("conflict_log", [])
        conflict_log.append(entry)
        if len(conflict_log) > 50:
            del conflict_log[:-50]

        pending = profile.setdefault("pending_clarifications", [])
        same_key_pending = next(
            (
                item
                for item in pending
                if isinstance(item, dict)
                and item.get("key") == key
                and str(item.get("state", "pending")).lower() == "pending"
            ),
            None,
        )
        if same_key_pending is None:
            pending.append(dict(entry))
        else:
            same_key_pending["type"] = entry["type"]
            same_key_pending["old_value"] = entry["old_value"]
            same_key_pending["new_value"] = entry["new_value"]
            same_key_pending["severity"] = entry["severity"]
            same_key_pending["prompt"] = entry["prompt"]
            same_key_pending["created_at"] = entry["created_at"]
            same_key_pending["state"] = "pending"
        if len(pending) > 10:
            del pending[:-10]
