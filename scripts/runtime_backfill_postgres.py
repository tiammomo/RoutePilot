#!/usr/bin/env python3
"""Backfill file-backed runtime snapshots into the SQL compatibility baseline."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if __package__:
    _bootstrap_paths = importlib.import_module(f"{__package__}.bootstrap_paths")
else:
    _bootstrap_paths_path = Path(__file__).with_name("bootstrap_paths.py")
    _bootstrap_paths_spec = importlib.util.spec_from_file_location("bootstrap_paths", _bootstrap_paths_path)
    if _bootstrap_paths_spec is None or _bootstrap_paths_spec.loader is None:
        raise ImportError(f"Unable to load bootstrap_paths from {_bootstrap_paths_path}")
    _bootstrap_paths = importlib.util.module_from_spec(_bootstrap_paths_spec)
    _bootstrap_paths_spec.loader.exec_module(_bootstrap_paths)

PROJECT_ROOT = _bootstrap_paths.PROJECT_ROOT
ensure_project_paths = _bootstrap_paths.ensure_project_paths
ensure_project_paths()

if TYPE_CHECKING:
    from agent.travel_agent.memory.postgres_memory_session_repository import PostgresMemorySessionRepository
    from moyuan_web.repositories.postgres_share_link_repository import PostgresShareLinkRepository
    from moyuan_web.repositories.session_repository_postgres import PostgresSessionRepository


DEFAULT_SESSIONS_FILE = PROJECT_ROOT / "data" / "sessions" / "sessions.json"
DEFAULT_SHARE_LINKS_FILE = PROJECT_ROOT / "data" / "share_links.json"
DEFAULT_AGENT_MEMORY_FILE = PROJECT_ROOT / "data" / "agent_memory.json"


def _load_sql_runtime_dependencies():
    """Load SQL runtime dependencies lazily so `--help` works before deps are installed."""

    from agent.travel_agent.memory.postgres_memory_session_repository import PostgresMemorySessionRepository
    from moyuan_web.persistence import build_sync_engine, ensure_schema
    from moyuan_web.repositories.postgres_share_link_repository import PostgresShareLinkRepository
    from moyuan_web.repositories.session_repository_postgres import PostgresSessionRepository

    return (
        build_sync_engine,
        ensure_schema,
        PostgresSessionRepository,
        PostgresShareLinkRepository,
        PostgresMemorySessionRepository,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the backfill entrypoint."""

    parser = argparse.ArgumentParser(
        description="Backfill sessions.json, share_links.json, and agent_memory.json into the SQL compatibility baseline.",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("MOYUAN_POSTGRES_DSN", "").strip(),
        help="Target database URL. Defaults to MOYUAN_POSTGRES_DSN.",
    )
    parser.add_argument(
        "--sessions-file",
        type=Path,
        default=DEFAULT_SESSIONS_FILE,
        help="Path to the file-backed sessions snapshot.",
    )
    parser.add_argument(
        "--share-links-file",
        type=Path,
        default=DEFAULT_SHARE_LINKS_FILE,
        help="Path to the file-backed share-links snapshot.",
    )
    parser.add_argument(
        "--agent-memory-file",
        type=Path,
        default=DEFAULT_AGENT_MEMORY_FILE,
        help="Path to the file-backed agent memory snapshot.",
    )
    parser.add_argument(
        "--skip-sessions",
        action="store_true",
        help="Skip importing session records.",
    )
    parser.add_argument(
        "--skip-share-links",
        action="store_true",
        help="Skip importing share-link records.",
    )
    parser.add_argument(
        "--skip-agent-memory",
        action="store_true",
        help="Skip importing agent-memory session snapshots.",
    )
    parser.add_argument(
        "--pool-min",
        type=int,
        default=1,
        help="SQLAlchemy pool size lower bound for postgres URLs.",
    )
    parser.add_argument(
        "--pool-max",
        type=int,
        default=5,
        help="SQLAlchemy pool size upper bound for postgres URLs.",
    )
    parser.add_argument(
        "--skip-ensure-schema",
        action="store_true",
        help="Skip calling metadata.create_all before import.",
    )
    return parser.parse_args()


def load_snapshot(path: Path) -> dict[str, dict[str, Any]]:
    """Load one file-backed JSON snapshot or return an empty mapping when missing."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Snapshot must be a JSON object: {path}")
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            normalized[str(key)] = dict(value)
    return normalized


async def _import_sessions(
    repository: PostgresSessionRepository,
    snapshot: dict[str, dict[str, Any]],
) -> int:
    """Import file-backed session records into the PostgreSQL repository."""

    imported = 0
    for session_id, session_data in snapshot.items():
        record = dict(session_data)
        record.setdefault("session_id", session_id)
        await repository.create(record)
        imported += 1
    return imported


async def _import_share_links(
    repository: PostgresShareLinkRepository,
    snapshot: dict[str, dict[str, Any]],
) -> int:
    """Import file-backed share-link records into the PostgreSQL repository."""

    imported = 0
    for share_id, record in snapshot.items():
        payload = dict(record)
        payload.setdefault("share_id", share_id)
        await repository.save(payload)
        imported += 1
    return imported


def _import_agent_memory(
    repository: PostgresMemorySessionRepository,
    snapshot: dict[str, dict[str, Any]],
) -> int:
    """Import file-backed agent-memory snapshots into the PostgreSQL repository."""

    normalized = {
        str(session_id): dict(session)
        for session_id, session in snapshot.items()
        if isinstance(session, dict)
    }
    if not normalized:
        return 0
    repository.write_snapshot(normalized)
    return len(normalized)


async def backfill_runtime_snapshots(
    *,
    database_url: str,
    sessions_file: Path = DEFAULT_SESSIONS_FILE,
    share_links_file: Path = DEFAULT_SHARE_LINKS_FILE,
    agent_memory_file: Path = DEFAULT_AGENT_MEMORY_FILE,
    include_sessions: bool = True,
    include_share_links: bool = True,
    include_agent_memory: bool = True,
    pool_min: int = 1,
    pool_max: int = 5,
    ensure_schema_ready: bool = True,
) -> dict[str, int]:
    """Import file-backed snapshots into the SQL baseline using idempotent upserts."""

    normalized_database_url = str(database_url or "").strip()
    if not normalized_database_url:
        raise ValueError("database_url is required")

    (
        build_sync_engine,
        ensure_schema,
        session_repository_cls,
        share_repository_cls,
        memory_repository_cls,
    ) = _load_sql_runtime_dependencies()
    engine = build_sync_engine(normalized_database_url, pool_min=pool_min, pool_max=pool_max)
    try:
        if ensure_schema_ready:
            ensure_schema(engine)

        result = {
            "sessions_imported": 0,
            "share_links_imported": 0,
            "memory_sessions_imported": 0,
        }

        if include_sessions:
            session_repository = session_repository_cls(
                normalized_database_url,
                pool_min=pool_min,
                pool_max=pool_max,
                ensure_schema_ready=False,
                engine=engine,
            )
            result["sessions_imported"] = await _import_sessions(
                session_repository,
                load_snapshot(sessions_file),
            )

        if include_share_links:
            share_repository = share_repository_cls(
                normalized_database_url,
                pool_min=pool_min,
                pool_max=pool_max,
                ensure_schema_ready=False,
                engine=engine,
            )
            result["share_links_imported"] = await _import_share_links(
                share_repository,
                load_snapshot(share_links_file),
            )

        if include_agent_memory:
            memory_repository = memory_repository_cls(
                normalized_database_url,
                pool_min=pool_min,
                pool_max=pool_max,
                ensure_schema_ready=False,
                engine=engine,
            )
            result["memory_sessions_imported"] = _import_agent_memory(
                memory_repository,
                load_snapshot(agent_memory_file),
            )

        return result
    finally:
        engine.dispose()


async def _main_async() -> int:
    """Run the CLI backfill flow and print a JSON summary."""

    args = parse_args()
    result = await backfill_runtime_snapshots(
        database_url=args.database_url,
        sessions_file=args.sessions_file,
        share_links_file=args.share_links_file,
        agent_memory_file=args.agent_memory_file,
        include_sessions=not args.skip_sessions,
        include_share_links=not args.skip_share_links,
        include_agent_memory=not args.skip_agent_memory,
        pool_min=args.pool_min,
        pool_max=args.pool_max,
        ensure_schema_ready=not args.skip_ensure_schema,
    )
    print(f"sessions_imported={result['sessions_imported']}")
    print(f"share_links_imported={result['share_links_imported']}")
    print(f"memory_sessions_imported={result['memory_sessions_imported']}")
    return 0


def main() -> int:
    """Run the CLI entrypoint."""

    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
