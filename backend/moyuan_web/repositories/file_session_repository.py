"""File-backed session repository with atomic writes and backup recovery."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

from .session_repository import SessionRepository


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _parse_iso_as_utc(value: Any) -> datetime | None:
    """Parse one ISO timestamp into an aware UTC datetime when possible."""

    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_to_timestamp(value: Any) -> float:
    """Parse one ISO timestamp into Unix seconds for ordering and expiry checks."""

    parsed = _parse_iso_as_utc(value)
    return parsed.timestamp() if parsed is not None else 0.0


class FileSessionRepository(SessionRepository):
    """Persist session records to one JSON snapshot plus `.bak` recovery copy."""

    BACKUP_SUFFIX = ".bak"

    def __init__(self, file_path: str = "data/sessions/sessions.json") -> None:
        """Initialize file-backed repository and load the current snapshot."""

        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        self._file_path = file_path
        self._lock = asyncio.Lock()
        self._sessions: dict[str, dict[str, Any]] = self._load_from_file()

    @classmethod
    def backup_path(cls, path: str) -> str:
        """Return the backup snapshot path for one primary JSON file."""

        return f"{path}{cls.BACKUP_SUFFIX}"

    @staticmethod
    def _load_json_file(path: str) -> dict[str, dict[str, Any]] | None:
        """Load one JSON snapshot when it exists and is well formed."""

        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _fsync_directory(path: str) -> None:
        """Best-effort directory fsync so renamed snapshots survive crashes."""

        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)

    def _atomic_write_json(self, path: str, payload: dict[str, dict[str, Any]]) -> None:
        """Persist JSON payload atomically using temp-file plus replace."""

        target_dir = os.path.dirname(path) or "."
        os.makedirs(target_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=target_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(target_dir)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _load_from_file(self) -> dict[str, dict[str, Any]]:
        """Load sessions and recover the primary snapshot from backup when needed."""

        primary_payload = self._load_json_file(self._file_path)
        if primary_payload is not None:
            return primary_payload

        backup_payload = self._load_json_file(self.backup_path(self._file_path))
        if backup_payload is None:
            return {}

        try:
            self._atomic_write_json(self._file_path, backup_payload)
        except OSError:
            pass
        return backup_payload

    def _save_to_file(self) -> None:
        """Persist current in-memory sessions to primary and backup snapshots."""

        self._atomic_write_json(self._file_path, self._sessions)
        self._atomic_write_json(self.backup_path(self._file_path), self._sessions)

    async def create(self, session_data: dict[str, Any]) -> str:
        """Create one new session record and persist it to the file snapshot."""

        async with self._lock:
            session_id = str(session_data.get("session_id") or uuid.uuid4())
            now = _utc_now_iso()
            messages = list(session_data.get("messages", [])) if isinstance(session_data.get("messages"), list) else []
            self._sessions[session_id] = {
                "session_id": session_id,
                "created_at": str(session_data.get("created_at") or now),
                "last_active": str(session_data.get("last_active") or now),
                "message_count": int(session_data.get("message_count", len(messages))),
                "name": str(session_data.get("name") or ""),
                "model_id": str(session_data.get("model_id") or "mimo-v2.5-pro"),
                "messages": messages,
                "user_preferences": dict(session_data.get("user_preferences", {})),
            }
            await asyncio.to_thread(self._save_to_file)
            return session_id

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Return one session record by ID."""

        async with self._lock:
            session = self._sessions.get(session_id)
            return dict(session) if isinstance(session, dict) else None

    async def update(self, session_id: str, session_data: dict[str, Any]) -> None:
        """Update one existing session record in-place and persist the snapshot."""

        async with self._lock:
            existing = self._sessions.get(session_id)
            if not isinstance(existing, dict):
                return
            merged = dict(existing)
            merged.update(session_data)
            merged["session_id"] = session_id
            merged["created_at"] = existing.get("created_at")
            merged["last_active"] = _utc_now_iso()
            merged["message_count"] = int(merged.get("message_count", len(merged.get("messages", []))))
            self._sessions[session_id] = merged
            await asyncio.to_thread(self._save_to_file)

    async def delete(self, session_id: str) -> bool:
        """Delete one session record when present."""

        async with self._lock:
            if session_id not in self._sessions:
                return False
            del self._sessions[session_id]
            await asyncio.to_thread(self._save_to_file)
            return True

    async def list_all(self, include_empty: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        """List sessions ordered by last activity descending."""

        async with self._lock:
            sessions = [dict(item) for item in self._sessions.values()]

        one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
        result: list[dict[str, Any]] = []
        for session_data in sessions:
            last_active = _parse_iso_to_timestamp(session_data.get("last_active"))
            if include_empty:
                result.append(session_data)
            elif session_data.get("message_count", 0) > 0 or last_active > one_hour_ago:
                result.append(session_data)

        result.sort(key=lambda item: _parse_iso_to_timestamp(item.get("last_active")), reverse=True)
        return result[:limit]

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """Delete sessions whose last-active timestamp is older than the threshold."""

        async with self._lock:
            current_time = datetime.now(timezone.utc)
            expired_ids = [
                session_id
                for session_id, data in self._sessions.items()
                if (
                    (last_active := _parse_iso_as_utc(data.get("last_active"))) is not None
                    and (current_time - last_active).total_seconds() > max_age_seconds
                )
            ]
            for session_id in expired_ids:
                del self._sessions[session_id]
            if expired_ids:
                await asyncio.to_thread(self._save_to_file)
            return len(expired_ids)
