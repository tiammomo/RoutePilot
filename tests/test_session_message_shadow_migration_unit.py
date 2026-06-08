"""Unit tests for retiring the legacy `sessions.messages` shadow payload."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import insert, select

from moyuan_web.persistence import build_sync_engine, session_messages_table, sessions_table


ROOT = Path(__file__).resolve().parents[1]


def _build_alembic_config(database_url: str) -> Config:
    migrations_root = ROOT / "deploy" / "migrations"
    config = Config(str(migrations_root / "alembic.ini"))
    config.set_main_option("script_location", str(migrations_root))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_session_message_shadow_migration_backfills_and_clears_shadow(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'shadow-migration.db'}"
    config = _build_alembic_config(database_url)

    command.upgrade(config, "20260404_0002")

    engine = build_sync_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            insert(sessions_table).values(
                session_id="session-shadow",
                created_at="2026-04-04T00:00:00+00:00",
                last_active="2026-04-04T00:00:00+00:00",
                message_count=1,
                name="Shadow",
                model_id="demo-model",
                messages=[
                    {
                        "role": "user",
                        "content": "legacy shadow message",
                        "timestamp": "2026-04-04T00:00:00+00:00",
                    }
                ],
                user_preferences={},
            )
        )
    engine.dispose()

    command.upgrade(config, "20260404_0003")

    engine = build_sync_engine(database_url)
    with engine.begin() as connection:
        session_row = connection.execute(
            select(sessions_table.c.messages).where(sessions_table.c.session_id == "session-shadow")
        ).mappings().one()
        message_rows = connection.execute(
            select(
                session_messages_table.c.role,
                session_messages_table.c.content,
                session_messages_table.c.timestamp,
            ).where(session_messages_table.c.session_id == "session-shadow")
        ).mappings().all()
    engine.dispose()

    assert session_row["messages"] == []
    assert message_rows == [
        {
            "role": "user",
            "content": "legacy shadow message",
            "timestamp": "2026-04-04T00:00:00+00:00",
        }
    ]
