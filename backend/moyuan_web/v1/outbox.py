"""Transactional outbox claiming and Redis Streams publication.

The dispatcher is intentionally a separate process. Its database credential
must belong to a dedicated role allowed to read the cross-tenant outbox; the
public API credential remains constrained by RLS and can only append rows for
the current transaction-local tenant.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from redis.asyncio import Redis
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .models import utc_now
from .postgres_store import normalize_async_database_url
from .sql_tables import outbox_events_table


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: str
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    publish_attempts: int


class OutboxRepository(Protocol):
    async def claim_batch(self, *, limit: int = 100) -> list[OutboxRecord]: ...

    async def mark_published(self, record: OutboxRecord) -> None: ...

    async def mark_failed(self, record: OutboxRecord, *, error_code: str) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, record: OutboxRecord) -> None: ...


class PostgresOutboxRepository:
    """Claim records with SKIP LOCKED and recover abandoned leases."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        worker_id: str,
        dedicated_worker_role: bool,
        lease_seconds: int = 60,
    ) -> None:
        if not dedicated_worker_role:
            raise ValueError("outbox dispatch requires a dedicated cross-tenant database role")
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be between 1 and 128 characters")
        self.engine = engine
        self.worker_id = worker_id
        self.lease_seconds = max(10, lease_seconds)

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        worker_id: str,
        dedicated_worker_role: bool,
    ) -> "PostgresOutboxRepository":
        engine = create_async_engine(
            normalize_async_database_url(database_url),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        return cls(
            engine,
            worker_id=worker_id,
            dedicated_worker_role=dedicated_worker_role,
        )

    async def claim_batch(self, *, limit: int = 100) -> list[OutboxRecord]:
        now = utc_now()
        stale_before = now - timedelta(seconds=self.lease_seconds)
        async with self.engine.begin() as connection:
            rows = (
                await connection.execute(
                    select(outbox_events_table)
                    .where(
                        outbox_events_table.c.published_at.is_(None),
                        outbox_events_table.c.available_at <= now,
                        or_(
                            outbox_events_table.c.locked_at.is_(None),
                            outbox_events_table.c.locked_at < stale_before,
                        ),
                    )
                    .order_by(outbox_events_table.c.created_at)
                    .limit(max(1, min(limit, 500)))
                    .with_for_update(skip_locked=True)
                )
            ).mappings().all()
            if not rows:
                return []
            ids = [str(row["outbox_id"]) for row in rows]
            await connection.execute(
                update(outbox_events_table)
                .where(outbox_events_table.c.outbox_id.in_(ids))
                .values(
                    locked_at=now,
                    locked_by=self.worker_id,
                    publish_attempts=outbox_events_table.c.publish_attempts + 1,
                )
            )
        return [
            OutboxRecord(
                outbox_id=str(row["outbox_id"]),
                tenant_id=str(row["tenant_id"]),
                aggregate_type=str(row["aggregate_type"]),
                aggregate_id=str(row["aggregate_id"]),
                event_type=str(row["event_type"]),
                payload=dict(row["payload"]) if isinstance(row["payload"], dict) else {},
                publish_attempts=int(row["publish_attempts"]) + 1,
            )
            for row in rows
        ]

    async def mark_published(self, record: OutboxRecord) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                update(outbox_events_table)
                .where(
                    outbox_events_table.c.outbox_id == record.outbox_id,
                    outbox_events_table.c.locked_by == self.worker_id,
                    outbox_events_table.c.published_at.is_(None),
                )
                .values(
                    published_at=utc_now(),
                    locked_at=None,
                    locked_by=None,
                    last_error=None,
                )
            )

    async def mark_failed(self, record: OutboxRecord, *, error_code: str) -> None:
        safe_code = re.sub(r"[^A-Z0-9_]", "_", error_code.upper())[:96] or "PUBLISH_FAILED"
        delay_seconds = min(300, 2 ** min(record.publish_attempts, 8))
        async with self.engine.begin() as connection:
            await connection.execute(
                update(outbox_events_table)
                .where(
                    outbox_events_table.c.outbox_id == record.outbox_id,
                    outbox_events_table.c.locked_by == self.worker_id,
                    outbox_events_table.c.published_at.is_(None),
                )
                .values(
                    available_at=utc_now() + timedelta(seconds=delay_seconds),
                    locked_at=None,
                    locked_by=None,
                    last_error=safe_code,
                )
            )

    async def close(self) -> None:
        await self.engine.dispose()


class RedisStreamPublisher:
    """Publish outbox envelopes to one bounded at-least-once Redis Stream."""

    def __init__(
        self,
        redis: Redis,
        *,
        stream: str = "routepilot:v1:outbox",
        max_length: int = 100_000,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.max_length = max(1_000, max_length)

    @classmethod
    def from_url(cls, redis_url: str, *, stream: str = "routepilot:v1:outbox") -> "RedisStreamPublisher":
        return cls(Redis.from_url(redis_url, decode_responses=True), stream=stream)

    async def publish(self, record: OutboxRecord) -> None:
        await self.redis.xadd(
            self.stream,
            {
                "outbox_id": record.outbox_id,
                "tenant_id": record.tenant_id,
                "aggregate_type": record.aggregate_type,
                "aggregate_id": record.aggregate_id,
                "event_type": record.event_type,
                "payload": json.dumps(
                    record.payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
            maxlen=self.max_length,
            approximate=True,
        )

    async def close(self) -> None:
        await self.redis.aclose()


class OutboxDispatcher:
    """At-least-once dispatcher with bounded retries and lease recovery."""

    def __init__(self, repository: OutboxRepository, publisher: EventPublisher):
        self.repository = repository
        self.publisher = publisher

    async def dispatch_once(self, *, limit: int = 100) -> int:
        records = await self.repository.claim_batch(limit=limit)
        for record in records:
            try:
                await self.publisher.publish(record)
            except Exception as exc:
                await self.repository.mark_failed(record, error_code=type(exc).__name__)
            else:
                await self.repository.mark_published(record)
        return len(records)

    async def run_forever(
        self,
        stop_event: asyncio.Event,
        *,
        idle_seconds: float = 0.5,
    ) -> None:
        while not stop_event.is_set():
            processed = await self.dispatch_once()
            if processed:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=max(0.05, idle_seconds))
            except TimeoutError:
                pass
