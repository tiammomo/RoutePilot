"""SQL-backed session repository used by the optional postgres backend."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, Connection, delete, insert, select, update

from ..persistence import build_sync_engine, ensure_schema, session_messages_table, sessions_table
from .session_repository import SessionRepository


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _parse_iso_to_timestamp(value: Any) -> float:
    """Parse ISO datetime string into Unix timestamp with UTC fallback."""

    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


class PostgresSessionRepository(SessionRepository):
    """Persist session records in the SQL compatibility baseline tables."""

    def __init__(
        self,
        database_url: str,
        *,
        pool_min: int = 1,
        pool_max: int = 5,
        ensure_schema_ready: bool = True,
        engine: Engine | None = None,
    ) -> None:
        """Create SQL repository and optionally bootstrap baseline tables."""

        self._engine = engine or build_sync_engine(database_url, pool_min=pool_min, pool_max=pool_max)
        if ensure_schema_ready:
            ensure_schema(self._engine)

    async def create(self, session_data: dict[str, Any]) -> str:
        """Create or replace one session record."""

        return await asyncio.to_thread(self._create_sync, session_data)

    def _create_sync(self, session_data: dict[str, Any]) -> str:
        session_id = str(session_data.get("session_id") or uuid.uuid4())
        now = _utc_now_iso()
        messages = self._normalize_messages(session_data.get("messages", []))
        payload = {
            "session_id": session_id,
            "created_at": str(session_data.get("created_at") or now),
            "last_active": str(session_data.get("last_active") or now),
            "message_count": int(session_data.get("message_count", len(messages))),
            "name": str(session_data.get("name") or ""),
            "model_id": str(session_data.get("model_id") or "mimo-v2.5-pro"),
            "messages": self._build_messages_shadow(messages),
            "user_preferences": dict(session_data.get("user_preferences", {})),
        }
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(sessions_table.c.session_id).where(sessions_table.c.session_id == session_id)
            ).first()
            if existing is None:
                connection.execute(insert(sessions_table).values(**payload))
            else:
                connection.execute(
                    update(sessions_table)
                    .where(sessions_table.c.session_id == session_id)
                    .values(**payload)
                )
            self._replace_messages_sync(connection, session_id, messages)
        return session_id

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Fetch one session by ID."""

        return await asyncio.to_thread(self._get_sync, session_id)

    def _get_sync(self, session_id: str) -> dict[str, Any] | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(sessions_table).where(sessions_table.c.session_id == session_id)
            ).mappings().first()
            if row is None:
                return None
            return self._row_to_session(
                row,
                messages=self._load_messages_sync(connection, session_id, fallback=row["messages"]),
            )

    async def update(self, session_id: str, session_data: dict[str, Any]) -> None:
        """Update one existing session record by merging fields."""

        await asyncio.to_thread(self._update_sync, session_id, session_data)

    def _update_sync(self, session_id: str, session_data: dict[str, Any]) -> None:
        existing = self._get_sync(session_id)
        if existing is None:
            return
        merged = dict(existing)
        merged.update(session_data)
        merged["session_id"] = session_id
        merged["created_at"] = existing.get("created_at")
        merged["last_active"] = _utc_now_iso()
        merged["message_count"] = int(merged.get("message_count", len(merged.get("messages", []))))
        self._create_sync(merged)

    async def delete(self, session_id: str) -> bool:
        """Delete one session by ID."""

        return await asyncio.to_thread(self._delete_sync, session_id)

    def _delete_sync(self, session_id: str) -> bool:
        with self._engine.begin() as connection:
            connection.execute(
                delete(session_messages_table).where(session_messages_table.c.session_id == session_id)
            )
            result = connection.execute(
                delete(sessions_table).where(sessions_table.c.session_id == session_id)
            )
        return bool(result.rowcount)

    async def list_all(self, include_empty: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        """List sessions ordered by last activity descending."""

        return await asyncio.to_thread(self._list_all_sync, include_empty, limit)

    def _list_all_sync(self, include_empty: bool, limit: int) -> list[dict[str, Any]]:
        with self._engine.begin() as connection:
            rows = connection.execute(select(sessions_table)).mappings().all()
            message_map = self._load_all_messages_sync(connection)
            sessions = [
                self._row_to_session(
                    row,
                    messages=message_map.get(str(row["session_id"]), self._normalize_messages(row["messages"])),
                )
                for row in rows
            ]
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
        """Delete expired sessions based on last-active timestamp."""

        return await asyncio.to_thread(self._cleanup_expired_sync, max_age_seconds)

    def _cleanup_expired_sync(self, max_age_seconds: int) -> int:
        threshold = datetime.now(timezone.utc).timestamp() - max_age_seconds
        with self._engine.begin() as connection:
            rows = connection.execute(select(sessions_table.c.session_id, sessions_table.c.last_active)).mappings().all()
            expired_ids = [
                str(row["session_id"])
                for row in rows
                if _parse_iso_to_timestamp(row["last_active"]) <= threshold
            ]
            if not expired_ids:
                return 0
            connection.execute(
                delete(session_messages_table).where(session_messages_table.c.session_id.in_(expired_ids))
            )
            result = connection.execute(
                delete(sessions_table).where(sessions_table.c.session_id.in_(expired_ids))
            )
        return int(result.rowcount or 0)

    @staticmethod
    def _row_to_session(row: Any, *, messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "session_id": str(row["session_id"]),
            "created_at": str(row["created_at"] or ""),
            "last_active": str(row["last_active"] or ""),
            "message_count": int(row["message_count"] or 0),
            "name": str(row["name"] or ""),
            "model_id": str(row["model_id"] or ""),
            "messages": list(messages if messages is not None else (row["messages"] or [])),
            "user_preferences": dict(row["user_preferences"] or {}),
        }

    @staticmethod
    def _normalize_messages(raw_messages: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_messages, list):
            return []
        messages: list[dict[str, Any]] = []
        for item in raw_messages:
            if isinstance(item, dict):
                messages.append(dict(item))
        return messages

    @staticmethod
    def _build_messages_shadow(_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Persist an empty compatibility shadow; normalized rows are the source of truth."""

        return []

    @staticmethod
    def _build_message_rows(session_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sequence, item in enumerate(messages):
            rows.append(
                {
                    "session_id": session_id,
                    "sequence": sequence,
                    "role": str(item.get("role") or "user"),
                    "content": str(item.get("content") or ""),
                    "reasoning": str(item.get("reasoning")) if item.get("reasoning") is not None else None,
                    "model_content": (
                        str(item.get("model_content")) if item.get("model_content") is not None else None
                    ),
                    "diagnostics": item.get("diagnostics"),
                    "timestamp": str(item.get("timestamp") or ""),
                }
            )
        return rows

    def _replace_messages_sync(
        self,
        connection: Connection,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        connection.execute(delete(session_messages_table).where(session_messages_table.c.session_id == session_id))
        rows = self._build_message_rows(session_id, messages)
        if rows:
            connection.execute(insert(session_messages_table), rows)

    def _load_messages_sync(
        self,
        connection: Connection,
        session_id: str,
        *,
        fallback: Any,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            select(session_messages_table)
            .where(session_messages_table.c.session_id == session_id)
            .order_by(session_messages_table.c.sequence.asc())
        ).mappings().all()
        if not rows:
            return self._normalize_messages(fallback)
        return [self._row_to_message(row) for row in rows]

    def _load_all_messages_sync(self, connection: Connection) -> dict[str, list[dict[str, Any]]]:
        rows = connection.execute(
            select(session_messages_table)
            .order_by(session_messages_table.c.session_id.asc(), session_messages_table.c.sequence.asc())
        ).mappings().all()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            session_id = str(row["session_id"])
            grouped.setdefault(session_id, []).append(self._row_to_message(row))
        return grouped

    @staticmethod
    def _row_to_message(row: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": str(row["role"] or "user"),
            "content": str(row["content"] or ""),
            "timestamp": str(row["timestamp"] or ""),
        }
        if row["reasoning"] is not None:
            payload["reasoning"] = str(row["reasoning"])
        if row["model_content"] is not None:
            payload["model_content"] = str(row["model_content"])
        if row["diagnostics"] is not None:
            payload["diagnostics"] = row["diagnostics"]
        return payload
