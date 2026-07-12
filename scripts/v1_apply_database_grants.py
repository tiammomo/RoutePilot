"""Apply the reviewed V1 runtime grants after an Alembic migration."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GRANTS_SQL = REPOSITORY_ROOT / "deploy" / "security" / "postgres-v1-grants.sql"


def apply_grants(database_url: str, *, sql_path: Path = GRANTS_SQL) -> None:
    """Execute the static least-privilege grants file without logging credentials."""

    if not database_url.strip():
        raise RuntimeError("MOYUAN_POSTGRES_DSN is required")
    sql = sql_path.read_text(encoding="utf-8")
    if "routepilot_runtime_grants" not in sql or "FORCE ROW LEVEL SECURITY" not in sql:
        raise RuntimeError("refusing to execute an unrecognized grants file")
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)


def main() -> int:
    """CLI entrypoint used only by the one-shot migration container."""

    apply_grants(os.environ.get("MOYUAN_POSTGRES_DSN", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
