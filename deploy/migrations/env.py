"""Alembic environment wiring for the clean RoutePilot V1 SQL baseline."""
# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from agent.travel_agent.a2a.sql_tables import metadata as a2a_metadata
from agent.travel_agent.rag.sql_tables import metadata as rag_metadata
from moyuan_web.v1.sql_tables import metadata as v1_metadata


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = str(
    os.getenv("MOYUAN_POSTGRES_DSN") or config.get_main_option("sqlalchemy.url") or ""
).strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = [v1_metadata, rag_metadata, a2a_metadata]


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    """Keep the optional pgvector side table under its manual capability migration."""

    _ = (object_, reflected, compare_to)
    return not (type_ == "table" and name == "v1_knowledge_chunk_vectors")


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    if not database_url:
        raise RuntimeError("Set MOYUAN_POSTGRES_DSN or sqlalchemy.url before running alembic migrations.")

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    if not database_url:
        raise RuntimeError("Set MOYUAN_POSTGRES_DSN or sqlalchemy.url before running alembic migrations.")

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
