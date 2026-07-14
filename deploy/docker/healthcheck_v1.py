"""Dependency-aware health probe for RoutePilot V1 Python containers."""

from __future__ import annotations

import argparse
import os
from urllib.request import urlopen

import psycopg
from redis import Redis


def check_http(url: str) -> None:
    """Require an HTTP 2xx response without printing response content."""

    with urlopen(url, timeout=3) as response:  # noqa: S310 - fixed local URL from image command
        if not 200 <= response.status < 300:
            raise RuntimeError("HTTP probe failed")


def check_database(variable: str) -> None:
    """Verify the configured role can open a database transaction."""

    database_url = os.environ.get(variable, "").strip()
    if not database_url:
        raise RuntimeError(f"{variable} is required")
    with psycopg.connect(database_url, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                raise RuntimeError("database probe failed")


def check_redis() -> None:
    """Verify Redis authentication and availability."""

    redis_url = os.environ.get("ROUTEPILOT_REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("ROUTEPILOT_REDIS_URL is required")
    client = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        if not client.ping():
            raise RuntimeError("Redis probe failed")
    finally:
        client.close()


def main() -> int:
    """Run the probe selected by the container healthcheck."""

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("api", "worker", "outbox"))
    args = parser.parse_args()
    if args.mode == "api":
        check_http("http://127.0.0.1:38083/api/ready")
    elif args.mode == "worker":
        check_database("ROUTEPILOT_V1_DATABASE_URL")
        check_redis()
    else:
        check_database("ROUTEPILOT_OUTBOX_DATABASE_URL")
        check_redis()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
