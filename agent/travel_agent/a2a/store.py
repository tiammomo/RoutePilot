"""A2A Task persistence port and concurrency-safe in-memory reference adapter."""

from __future__ import annotations

import asyncio
import builtins
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, TypeVar

from a2a.server.events.event_queue import Event
from a2a.types import Task
from google.protobuf.message import Message as ProtoMessage

from .models import AgentInvocation, InputResponse

ProtoT = TypeVar("ProtoT", bound=ProtoMessage)


def clone_proto(value: ProtoT) -> ProtoT:
    """Clone a mutable protobuf value before it crosses a store boundary."""

    cloned = type(value)()
    cloned.CopyFrom(value)
    return cloned


@dataclass(frozen=True, slots=True)
class VersionedEvent:
    """One monotonic Task event retained for streaming subscribers."""

    version: int
    event: Event


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Durable state required to recover and reconcile one A2A Task."""

    tenant_id: str
    actor_id: str
    agent_interface_id: str
    run_id: str
    dispatch_id: str
    request_fingerprint: str
    task: Task
    invocation: AgentInvocation
    deadline: datetime
    reference_task_ids: tuple[str, ...] = ()
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pending_input_request_id: str | None = None
    execution_input: InputResponse | None = None
    message_fingerprints: dict[str, str] = field(default_factory=dict)
    events: tuple[VersionedEvent, ...] = ()


def clone_record(record: TaskRecord) -> TaskRecord:
    """Return a deeply detached record suitable for caller mutation."""

    return replace(
        record,
        task=clone_proto(record.task),
        invocation=record.invocation.model_copy(deep=True),
        execution_input=(
            record.execution_input.model_copy(deep=True)
            if record.execution_input is not None
            else None
        ),
        message_fingerprints=dict(record.message_fingerprints),
        events=tuple(
            VersionedEvent(item.version, clone_proto(item.event)) for item in record.events
        ),
    )


class TaskStoreError(RuntimeError):
    """Base persistence error exposed to TaskService."""


class TaskMissing(TaskStoreError):
    """The scoped Task does not exist."""


class TaskVersionConflict(TaskStoreError):
    """Optimistic Task version changed before replacement."""


class TaskExecutionLeaseLost(TaskStoreError):
    """The caller no longer owns the durable Task execution fence."""


class DispatchConflict(TaskStoreError):
    """A dispatch ID was reused with a different request."""


@dataclass(frozen=True, slots=True)
class TaskExecutionLease:
    """Opaque fencing token for one submitted/working Task execution attempt."""

    tenant_id: str
    agent_interface_id: str
    task_id: str
    owner: str
    attempt: int
    lease_until: datetime


class AgentTaskPersistence(Protocol):
    """Persistence port; production adapters must make create/dedupe atomic."""

    async def create_or_get(self, record: TaskRecord) -> tuple[TaskRecord, bool]: ...

    async def get(self, tenant_id: str, agent_interface_id: str, task_id: str) -> TaskRecord: ...

    async def get_by_dispatch(
        self,
        tenant_id: str,
        agent_interface_id: str,
        dispatch_id: str,
    ) -> TaskRecord: ...

    async def replace(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
        execution_lease: TaskExecutionLease | None = None,
    ) -> TaskRecord: ...

    async def claim_execution(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> TaskExecutionLease | None: ...

    async def renew_execution(
        self,
        lease: TaskExecutionLease,
        *,
        lease_seconds: float,
    ) -> TaskExecutionLease | None: ...

    async def release_execution(self, lease: TaskExecutionLease) -> None: ...

    async def list(
        self,
        tenant_id: str,
        agent_interface_id: str,
        *,
        context_id: str | None = None,
        state: int | None = None,
    ) -> list[TaskRecord]: ...

    async def list_for_run(self, tenant_id: str, run_id: str) -> builtins.list[TaskRecord]: ...

    async def wait_for_change(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        after_version: int,
        timeout_seconds: float,
    ) -> TaskRecord | None: ...

    async def close(self) -> None: ...


class InMemoryAgentTaskStore:
    """Reference adapter with inbox dedupe, CAS and subscriber notification.

    Production must replace this with a durable database implementation whose
    inbox insert, Task creation and execution-outbox insert share one transaction.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], TaskRecord] = {}
        self._dispatch_index: dict[tuple[str, str, str], tuple[str, str, str]] = {}
        self._execution_leases: dict[tuple[str, str, str], TaskExecutionLease] = {}
        self._execution_attempts: dict[tuple[str, str, str], int] = {}
        self._condition = asyncio.Condition()

    async def create_or_get(self, record: TaskRecord) -> tuple[TaskRecord, bool]:
        key = (record.tenant_id, record.agent_interface_id, record.task.id)
        dispatch_key = (record.tenant_id, record.agent_interface_id, record.dispatch_id)
        async with self._condition:
            existing_key = self._dispatch_index.get(dispatch_key)
            if existing_key is not None:
                existing = self._records[existing_key]
                if existing.request_fingerprint != record.request_fingerprint:
                    raise DispatchConflict("dispatch identifier already has another request")
                return clone_record(existing), False
            if key in self._records:
                raise DispatchConflict("task identifier already exists")
            stored = clone_record(record)
            self._records[key] = stored
            self._dispatch_index[dispatch_key] = key
            self._condition.notify_all()
            return clone_record(stored), True

    async def get(self, tenant_id: str, agent_interface_id: str, task_id: str) -> TaskRecord:
        async with self._condition:
            record = self._records.get((tenant_id, agent_interface_id, task_id))
            if record is None:
                raise TaskMissing("task not found")
            return clone_record(record)

    async def get_by_dispatch(
        self,
        tenant_id: str,
        agent_interface_id: str,
        dispatch_id: str,
    ) -> TaskRecord:
        async with self._condition:
            key = self._dispatch_index.get((tenant_id, agent_interface_id, dispatch_id))
            record = self._records.get(key) if key is not None else None
            if record is None:
                raise TaskMissing("task not found")
            return clone_record(record)

    async def replace(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
        execution_lease: TaskExecutionLease | None = None,
    ) -> TaskRecord:
        key = (record.tenant_id, record.agent_interface_id, record.task.id)
        async with self._condition:
            current = self._records.get(key)
            if current is None:
                raise TaskMissing("task not found")
            if execution_lease is not None:
                active = self._execution_leases.get(key)
                if (
                    active is None
                    or active.owner != execution_lease.owner
                    or active.attempt != execution_lease.attempt
                    or active.lease_until <= datetime.now(UTC)
                ):
                    raise TaskExecutionLeaseLost("task execution lease was lost")
            if current.version != expected_version or record.version != expected_version + 1:
                raise TaskVersionConflict("task state changed")
            stored = clone_record(record)
            self._records[key] = stored
            if int(stored.task.status.state) not in {1, 2}:
                self._execution_leases.pop(key, None)
            self._condition.notify_all()
            return clone_record(stored)

    async def claim_execution(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> TaskExecutionLease | None:
        key = (tenant_id, agent_interface_id, task_id)
        async with self._condition:
            record = self._records.get(key)
            if record is None:
                raise TaskMissing("task not found")
            if int(record.task.status.state) not in {1, 2}:
                return None
            now = datetime.now(UTC)
            active = self._execution_leases.get(key)
            if active is not None and active.lease_until > now:
                return None
            attempt = self._execution_attempts.get(key, 0) + 1
            lease = TaskExecutionLease(
                tenant_id=tenant_id,
                agent_interface_id=agent_interface_id,
                task_id=task_id,
                owner=owner,
                attempt=attempt,
                lease_until=now + timedelta(seconds=max(0.05, lease_seconds)),
            )
            self._execution_attempts[key] = attempt
            self._execution_leases[key] = lease
            return lease

    async def renew_execution(
        self,
        lease: TaskExecutionLease,
        *,
        lease_seconds: float,
    ) -> TaskExecutionLease | None:
        key = (lease.tenant_id, lease.agent_interface_id, lease.task_id)
        async with self._condition:
            record = self._records.get(key)
            active = self._execution_leases.get(key)
            now = datetime.now(UTC)
            if (
                record is None
                or int(record.task.status.state) not in {1, 2}
                or active is None
                or active.owner != lease.owner
                or active.attempt != lease.attempt
                or active.lease_until <= now
            ):
                return None
            renewed = replace(
                active,
                lease_until=now + timedelta(seconds=max(0.05, lease_seconds)),
            )
            self._execution_leases[key] = renewed
            return renewed

    async def release_execution(self, lease: TaskExecutionLease) -> None:
        key = (lease.tenant_id, lease.agent_interface_id, lease.task_id)
        async with self._condition:
            active = self._execution_leases.get(key)
            if (
                active is not None
                and active.owner == lease.owner
                and active.attempt == lease.attempt
            ):
                self._execution_leases.pop(key, None)

    async def list(
        self,
        tenant_id: str,
        agent_interface_id: str,
        *,
        context_id: str | None = None,
        state: int | None = None,
    ) -> list[TaskRecord]:
        async with self._condition:
            records = [
                record
                for (tenant, interface, _), record in self._records.items()
                if tenant == tenant_id
                and interface == agent_interface_id
                and (context_id is None or record.task.context_id == context_id)
                and (state is None or record.task.status.state == state)
            ]
            records.sort(key=lambda item: (item.created_at or item.deadline, item.task.id))
            return [clone_record(record) for record in records]

    async def list_for_run(self, tenant_id: str, run_id: str) -> builtins.list[TaskRecord]:
        async with self._condition:
            records = [
                record
                for (tenant, _, _), record in self._records.items()
                if tenant == tenant_id and record.run_id == run_id
            ]
            records.sort(key=lambda item: (item.created_at or item.deadline, item.task.id))
            return [clone_record(record) for record in records]

    async def wait_for_change(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        after_version: int,
        timeout_seconds: float,
    ) -> TaskRecord | None:
        key = (tenant_id, agent_interface_id, task_id)
        async with self._condition:
            try:
                await asyncio.wait_for(
                    self._condition.wait_for(
                        lambda: (
                            key not in self._records or self._records[key].version > after_version
                        )
                    ),
                    timeout=max(0.001, timeout_seconds),
                )
            except TimeoutError:
                return None
            record = self._records.get(key)
            if record is None:
                raise TaskMissing("task not found")
            return clone_record(record)

    async def close(self) -> None:
        """Match the durable adapter lifecycle contract."""

        return None


__all__ = [
    "AgentTaskPersistence",
    "DispatchConflict",
    "InMemoryAgentTaskStore",
    "TaskMissing",
    "TaskRecord",
    "TaskExecutionLease",
    "TaskExecutionLeaseLost",
    "TaskStoreError",
    "TaskVersionConflict",
    "VersionedEvent",
    "clone_proto",
    "clone_record",
]
