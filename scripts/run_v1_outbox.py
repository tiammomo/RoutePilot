"""Run the RoutePilot V1 transactional outbox dispatcher."""

from __future__ import annotations

import asyncio
import os
import secrets
import signal

from moyuan_web.v1.outbox import (
    OutboxDispatcher,
    PostgresOutboxRepository,
    RedisStreamPublisher,
)


async def run() -> None:
    database_url = os.getenv("ROUTEPILOT_OUTBOX_DATABASE_URL", "").strip()
    api_database_url = os.getenv("ROUTEPILOT_V1_DATABASE_URL", "").strip()
    redis_url = os.getenv("ROUTEPILOT_REDIS_URL", "").strip()
    dedicated = os.getenv("ROUTEPILOT_OUTBOX_DEDICATED_ROLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not database_url or not redis_url:
        raise RuntimeError("ROUTEPILOT_OUTBOX_DATABASE_URL and ROUTEPILOT_REDIS_URL are required")
    if database_url == api_database_url:
        raise RuntimeError("outbox and public API must not share one database credential")

    worker_id = f"outbox-{secrets.token_hex(8)}"
    repository = PostgresOutboxRepository.from_database_url(
        database_url,
        worker_id=worker_id,
        dedicated_worker_role=dedicated,
    )
    publisher = RedisStreamPublisher.from_url(redis_url)
    dispatcher = OutboxDispatcher(repository, publisher)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    try:
        await dispatcher.run_forever(stop)
    finally:
        await publisher.close()
        await repository.close()


if __name__ == "__main__":
    asyncio.run(run())
