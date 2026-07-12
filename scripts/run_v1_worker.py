"""Run the independent RoutePilot V1 Product Run worker."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import signal

from redis.asyncio import Redis

from moyuan_web.v1.runtime import build_default_v1_runtime
from moyuan_web.v1.worker import RedisRunWorker


def configure_logging() -> None:
    """Enable safe operational telemetry for the standalone worker."""

    level_name = os.getenv("ROUTEPILOT_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def run() -> None:
    redis_url = os.getenv("ROUTEPILOT_REDIS_URL", "").strip()
    if not redis_url or not os.getenv("ROUTEPILOT_V1_DATABASE_URL", "").strip():
        raise RuntimeError("ROUTEPILOT_REDIS_URL and ROUTEPILOT_V1_DATABASE_URL are required")
    redis = Redis.from_url(redis_url, decode_responses=True)
    worker = RedisRunWorker(
        redis,
        build_default_v1_runtime(),
        consumer=f"run-worker-{secrets.token_hex(8)}",
        lease_seconds=float(os.getenv("ROUTEPILOT_V1_RUN_LEASE_SECONDS", "60")),
        reclaim_idle_milliseconds=int(
            os.getenv("ROUTEPILOT_V1_RUN_RECLAIM_IDLE_MILLISECONDS", "60000")
        ),
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    try:
        while not stop.is_set():
            await worker.run_once()
    finally:
        await worker.close()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run())
