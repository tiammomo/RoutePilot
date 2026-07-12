"""Transactional outbox dispatcher behavior tests."""

from __future__ import annotations

import pytest

from backend.moyuan_web.v1.outbox import OutboxDispatcher, OutboxRecord


def record(identifier: str) -> OutboxRecord:
    return OutboxRecord(
        outbox_id=identifier,
        tenant_id="tenant-a",
        aggregate_type="run",
        aggregate_id="run-a",
        event_type="run.dispatch.requested",
        payload={"run_id": "run-a"},
        publish_attempts=1,
    )


class FakeRepository:
    def __init__(self, records: list[OutboxRecord]):
        self.records = records
        self.published: list[str] = []
        self.failed: list[tuple[str, str]] = []

    async def claim_batch(self, *, limit: int = 100):
        return self.records[:limit]

    async def mark_published(self, item: OutboxRecord):
        self.published.append(item.outbox_id)

    async def mark_failed(self, item: OutboxRecord, *, error_code: str):
        self.failed.append((item.outbox_id, error_code))


class FakePublisher:
    def __init__(self, fail_id: str | None = None):
        self.fail_id = fail_id
        self.items: list[str] = []

    async def publish(self, item: OutboxRecord):
        if item.outbox_id == self.fail_id:
            raise RuntimeError("provider detail that must not be persisted")
        self.items.append(item.outbox_id)


@pytest.mark.asyncio
async def test_dispatcher_marks_each_success_after_publication() -> None:
    repository = FakeRepository([record("outbox-a"), record("outbox-b")])
    publisher = FakePublisher()

    processed = await OutboxDispatcher(repository, publisher).dispatch_once()

    assert processed == 2
    assert publisher.items == ["outbox-a", "outbox-b"]
    assert repository.published == ["outbox-a", "outbox-b"]
    assert repository.failed == []


@pytest.mark.asyncio
async def test_dispatcher_persists_only_safe_error_code_and_continues_batch() -> None:
    repository = FakeRepository([record("outbox-a"), record("outbox-b")])
    publisher = FakePublisher(fail_id="outbox-a")

    processed = await OutboxDispatcher(repository, publisher).dispatch_once()

    assert processed == 2
    assert repository.failed == [("outbox-a", "RuntimeError")]
    assert repository.published == ["outbox-b"]
    assert "provider detail" not in str(repository.failed)
