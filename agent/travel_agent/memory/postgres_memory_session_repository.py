"""SQL-backed repository for full agent-memory session snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, delete, insert, select

from moyuan_web.persistence import build_sync_engine, ensure_schema, memory_sessions_table

from .memory_session_repository import MemorySessionRepository


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


class PostgresMemorySessionRepository(MemorySessionRepository):
    """Persist agent-memory session snapshots in the SQL baseline."""

    def __init__(
        self,
        database_url: str,
        *,
        pool_min: int = 1,
        pool_max: int = 5,
        ensure_schema_ready: bool = True,
        engine: Engine | None = None,
    ) -> None:
        """Create the SQL repository and optionally bootstrap the baseline tables."""

        self._engine = engine or build_sync_engine(database_url, pool_min=pool_min, pool_max=pool_max)
        if ensure_schema_ready:
            ensure_schema(self._engine)

    @property
    def enabled(self) -> bool:
        """Return whether the repository is active."""

        return True

    @property
    def backup_path(self) -> str | None:
        """SQL persistence has no separate filesystem hot-backup path."""

        return None

    def load_snapshot(self) -> tuple[dict[str, Any] | None, bool]:
        """Load the current full memory snapshot from SQL storage."""

        with self._engine.begin() as connection:
            rows = connection.execute(
                select(memory_sessions_table).order_by(memory_sessions_table.c.session_id.asc())
            ).mappings().all()
        payload = {
            str(row["session_id"]): {
                "summary": str(row["summary"] or ""),
                "profile": dict(row["profile"] or {}),
                "messages": list(row["messages"] or []),
            }
            for row in rows
        }
        return payload, False

    def write_snapshot(self, payload: dict[str, Any]) -> None:
        """Replace the current SQL snapshot with the provided payload."""

        rows = self._normalize_rows(payload)
        with self._engine.begin() as connection:
            connection.execute(delete(memory_sessions_table))
            if rows:
                connection.execute(insert(memory_sessions_table), rows)

    def restore_primary(self, payload: dict[str, Any]) -> None:
        """Restore the primary SQL snapshot by rewriting the current rows."""

        self.write_snapshot(payload)

    @staticmethod
    def _normalize_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert one memory snapshot payload into SQL insert rows."""

        rows: list[dict[str, Any]] = []
        for session_id, session in payload.items():
            if not isinstance(session, dict):
                continue
            profile = session.get("profile")
            messages = session.get("messages")
            rows.append(
                {
                    "session_id": str(session_id),
                    "summary": str(session.get("summary") or ""),
                    "profile": dict(profile) if isinstance(profile, dict) else {},
                    "messages": list(messages) if isinstance(messages, list) else [],
                    "updated_at": PostgresMemorySessionRepository._resolve_updated_at(session),
                }
            )
        return rows

    @staticmethod
    def _resolve_updated_at(session: dict[str, Any]) -> str:
        """Choose a stable updated-at timestamp from profile or latest message data."""

        profile = session.get("profile")
        if isinstance(profile, dict) and profile.get("updated_at"):
            return str(profile["updated_at"])
        messages = session.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict) and last.get("timestamp"):
                return str(last["timestamp"])
        return _utc_now_iso()
