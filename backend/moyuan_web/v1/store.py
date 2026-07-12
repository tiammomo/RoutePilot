"""Persistence ports and a concurrency-safe V1 in-memory reference store."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, TypeVar, cast

from routepilot_contracts import validate_contract
from routepilot_contracts.validation import CONTRACT_MODELS

from .models import (
    ArtifactCommandRequest,
    ArtifactPatchRequest,
    ArtifactStatus,
    ArtifactView,
    PUBLIC_EVENT_TYPES,
    Principal,
    RunCommand,
    RunEvent,
    RunPendingInput,
    RunLifecycle,
    RunView,
    TERMINAL_RUN_STATES,
    TripCreateRequest,
    TripMemberRole,
    TripMemberUpsertRequest,
    TripMemberView,
    TripPatchRequest,
    TripStatus,
    TripView,
    new_public_id,
    utc_now,
    validate_run_input_values,
)

ModelT = TypeVar("ModelT", TripView, RunView, RunEvent, ArtifactView)


class StoreError(Exception):
    """Base persistence error mapped by the V1 API layer."""


class ResourceNotFound(StoreError):
    """Requested scoped resource does not exist."""


class ResourceForbidden(StoreError):
    """Authenticated actor cannot access a scoped resource."""


class VersionConflict(StoreError):
    """Optimistic concurrency control rejected a stale command."""

    def __init__(self, current_version: int):
        super().__init__(f"expected version is stale; current version is {current_version}")
        self.current_version = current_version


class IdempotencyConflict(StoreError):
    """The same idempotency key was reused for a different request."""


class ArtifactTransitionConflict(StoreError):
    """An Artifact command is not legal from its current lifecycle state."""

    def __init__(self, *, current_version: int, current_status: ArtifactStatus, command: str):
        super().__init__(f"{command} is not allowed from {current_status.value}")
        self.current_version = current_version
        self.current_status = current_status
        self.command = command


class ArtifactReadOnly(StoreError):
    """The stored Artifact belongs to a migration-only or unsupported type."""

    def __init__(self, *, artifact_type: str, current_version: int):
        super().__init__("artifact type is read-only")
        self.artifact_type = artifact_type
        self.current_version = current_version


class ArtifactContentInvalid(StoreError):
    """Artifact content failed its registered public contract."""

    def __init__(self, *, current_version: int):
        super().__init__("artifact content is invalid")
        self.current_version = current_version


class RunExecutionBusy(StoreError):
    """A non-expired worker lease already owns this Product Run."""


class RunExecutionLeaseLost(StoreError):
    """A stale worker attempted a fenced Product Run side effect."""


class RunInputExpired(StoreError):
    """The persisted human-input interruption is no longer resumable."""


class RunInputInvalid(StoreError):
    """A resume request did not satisfy the persisted input schema."""


@dataclass(frozen=True, slots=True)
class RunExecutionLease:
    """Opaque worker fencing token; ``attempt`` never decreases for a Run."""

    run_id: str
    owner: str
    attempt: int
    lease_until: datetime


@dataclass(frozen=True, slots=True)
class IdempotentRunResult:
    """Result of atomically creating or replaying a Run."""

    run: RunView
    event: RunEvent | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class IdempotentArtifactResult:
    """Result of applying or replaying an Artifact lifecycle command."""

    artifact: ArtifactView
    replayed: bool


class PlatformStore(Protocol):
    """Persistence boundary required by the V1 application layer."""

    async def create_trip(self, principal: Principal, request: TripCreateRequest) -> TripView: ...

    async def list_trips(self, principal: Principal) -> list[TripView]: ...

    async def get_trip(self, principal: Principal, trip_id: str) -> TripView: ...

    async def patch_trip(
        self,
        principal: Principal,
        trip_id: str,
        request: TripPatchRequest,
    ) -> TripView: ...

    async def set_trip_status(
        self,
        principal: Principal,
        trip_id: str,
        status: TripStatus,
    ) -> TripView: ...

    async def list_trip_members(
        self,
        principal: Principal,
        trip_id: str,
    ) -> list[TripMemberView]: ...

    async def upsert_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
        request: TripMemberUpsertRequest,
    ) -> TripMemberView: ...

    async def remove_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
    ) -> None: ...

    async def create_run(
        self,
        principal: Principal,
        *,
        trip_id: str,
        command: RunCommand,
        base_artifact_id: str | None,
        base_artifact_version: int | None,
        idempotency_key: str,
        request_hash: str,
        trace_id: str,
    ) -> IdempotentRunResult: ...

    async def get_run(self, principal: Principal, run_id: str) -> RunView: ...

    async def claim_run_execution(
        self,
        principal: Principal,
        run_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> RunExecutionLease | None: ...

    async def renew_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
        *,
        lease_seconds: float,
    ) -> RunExecutionLease | None: ...

    async def release_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
    ) -> bool: ...

    async def mutate_run(
        self,
        principal: Principal,
        run_id: str,
        *,
        expected_control_version: int,
        lifecycle_state: RunLifecycle | None = None,
        phase: str | None = None,
        pending_input: RunPendingInput | None = None,
        result_artifact: ArtifactView | None = None,
        public_error_code: str | None = None,
        execution_lease: RunExecutionLease | None = None,
        event_type: PUBLIC_EVENT_TYPES,
        event_data: dict[str, Any],
    ) -> tuple[RunView, RunEvent]: ...

    async def resume_run(
        self,
        principal: Principal,
        run_id: str,
        *,
        expected_control_version: int,
        request_id: str,
        values: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotentRunResult: ...

    async def list_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
    ) -> list[RunEvent]: ...

    async def wait_for_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
        timeout_seconds: float,
    ) -> bool: ...

    async def create_artifact(
        self,
        principal: Principal,
        *,
        trip_id: str,
        artifact_id: str | None = None,
        artifact_type: str,
        schema_version: int,
        content: dict[str, Any],
        status: ArtifactStatus,
        parent_version: int | None = None,
        execution_lease: RunExecutionLease | None = None,
    ) -> ArtifactView: ...

    async def list_artifacts(self, principal: Principal, trip_id: str) -> list[ArtifactView]: ...

    async def get_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        *,
        version: int | None = None,
    ) -> ArtifactView: ...

    async def patch_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactPatchRequest,
    ) -> ArtifactView: ...

    async def command_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactCommandRequest,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotentArtifactResult: ...


def canonical_request_hash(payload: dict[str, Any]) -> str:
    """Hash a canonical request for idempotency conflict detection."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_execution_lease_request(owner: str, lease_seconds: float) -> None:
    """Reject ambiguous owners and unsafe lease durations at the store edge."""

    if not owner or len(owner) > 128:
        raise ValueError("execution lease owner must be between 1 and 128 characters")
    if not 0.05 <= lease_seconds <= 3_600:
        raise ValueError("execution lease duration must be between 0.05 and 3600 seconds")


def validate_artifact_patch_content(
    current: ArtifactView,
    request: ArtifactPatchRequest,
) -> dict[str, Any]:
    """Validate and canonicalize a complete immutable Artifact envelope.

    Imported archives are intentionally not public edit contracts. Unknown
    names fail closed against the contract registry instead of being persisted
    as arbitrary dictionaries.
    """

    ensure_artifact_mutable(current)
    next_version = current.version + 1
    expected_header = {
        "artifact_id": current.artifact_id,
        "artifact_type": current.artifact_type,
        "schema_version": current.schema_version,
        "version": next_version,
    }
    if any(request.content.get(field) != value for field, value in expected_header.items()):
        raise ArtifactContentInvalid(current_version=current.version)
    try:
        validated = validate_contract(
            f"{current.artifact_type}@{current.schema_version}",
            request.content,
        )
    except (TypeError, ValueError):
        # Contract failures can embed raw input in Pydantic's exception tree;
        # never retain that tree in the public store error chain.
        raise ArtifactContentInvalid(current_version=current.version) from None
    return cast(dict[str, Any], validated.model_dump(mode="json"))


def ensure_artifact_mutable(current: ArtifactView) -> None:
    """Fail closed unless the Artifact has a registered editable contract."""

    contract_id = f"{current.artifact_type}@{current.schema_version}"
    if contract_id not in CONTRACT_MODELS:
        raise ArtifactReadOnly(
            artifact_type=current.artifact_type,
            current_version=current.version,
        )


class InMemoryPlatformStore:
    """Concurrency-safe reference implementation used for tests and local scaffolding."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._trips: dict[str, TripView] = {}
        self._runs: dict[str, RunView] = {}
        self._events: dict[str, list[RunEvent]] = {}
        self._artifacts: dict[str, list[ArtifactView]] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._run_control_idempotency: dict[
            tuple[str, str, str, str], tuple[str, str]
        ] = {}
        self._artifact_idempotency: dict[
            tuple[str, str, str, str], tuple[str, ArtifactView]
        ] = {}
        self._members: dict[tuple[str, str], TripMemberView] = {}
        self._execution_leases: dict[str, RunExecutionLease] = {}
        self._execution_attempts: dict[str, int] = {}

    @staticmethod
    def _copy(value: ModelT) -> ModelT:
        return cast(ModelT, value.model_copy(deep=True))

    @staticmethod
    def _assert_tenant(principal: Principal, tenant_id: str) -> None:
        if principal.tenant_id != tenant_id:
            raise ResourceNotFound("resource not found")

    def _trip_locked(self, principal: Principal, trip_id: str, *, write: bool = False) -> TripView:
        trip = self._trips.get(trip_id)
        if trip is None:
            raise ResourceNotFound("trip not found")
        self._assert_tenant(principal, trip.tenant_id)
        if trip.owner_id == principal.user_id or principal.roles.intersection(
            {"admin", "tenant_admin"}
        ):
            return trip
        member = self._members.get((trip_id, principal.user_id))
        if member is None or (write and member.role != TripMemberRole.EDITOR):
            raise ResourceForbidden("trip access denied")
        return trip

    def _run_locked(self, principal: Principal, run_id: str) -> RunView:
        run = self._runs.get(run_id)
        if run is None:
            raise ResourceNotFound("run not found")
        self._assert_tenant(principal, run.tenant_id)
        self._trip_locked(principal, run.trip_id)
        return run

    def _assert_execution_lease_locked(
        self,
        principal: Principal,
        lease: RunExecutionLease,
        *,
        trip_id: str | None = None,
    ) -> RunView:
        run = self._run_locked(principal, lease.run_id)
        current = self._execution_leases.get(lease.run_id)
        now = utc_now()
        if (
            current is None
            or current.owner != lease.owner
            or current.attempt != lease.attempt
            or current.lease_until <= now
            or run.lifecycle_state not in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}
            or (trip_id is not None and run.trip_id != trip_id)
        ):
            raise RunExecutionLeaseLost("run execution lease is no longer valid")
        return run

    def _artifact_locked(
        self,
        principal: Principal,
        artifact_id: str,
        *,
        version: int | None = None,
        write: bool = False,
    ) -> ArtifactView:
        versions = self._artifacts.get(artifact_id)
        if not versions:
            raise ResourceNotFound("artifact not found")
        latest = max(versions, key=lambda item: item.version)
        resolved = latest if version is None else next(
            (item for item in versions if item.version == version),
            None,
        )
        if resolved is None:
            raise ResourceNotFound("artifact version not found")
        self._assert_tenant(principal, resolved.tenant_id)
        self._trip_locked(principal, resolved.trip_id, write=write)
        return resolved

    def _append_event_locked(
        self,
        run: RunView,
        *,
        event_type: PUBLIC_EVENT_TYPES,
        event_data: dict[str, Any],
        trace_id: str,
        occurred_at: datetime | None = None,
    ) -> RunEvent:
        events = self._events.setdefault(run.run_id, [])
        event = RunEvent(
            event_id=new_public_id("evt"),
            seq=len(events) + 1,
            type=event_type,
            occurred_at=occurred_at or utc_now(),
            trip_id=run.trip_id,
            run_id=run.run_id,
            trace_id=trace_id,
            data=event_data,
        )
        events.append(event)
        return event

    async def create_trip(self, principal: Principal, request: TripCreateRequest) -> TripView:
        now = utc_now()
        trip = TripView(
            trip_id=new_public_id("trip"),
            tenant_id=principal.tenant_id,
            owner_id=principal.user_id,
            title=request.title,
            locale=request.locale,
            timezone=request.timezone,
            status=TripStatus.ACTIVE,
            version=1,
            created_at=now,
            updated_at=now,
        )
        async with self._condition:
            self._trips[trip.trip_id] = trip
            self._members[(trip.trip_id, principal.user_id)] = TripMemberView(
                trip_id=trip.trip_id,
                tenant_id=trip.tenant_id,
                user_id=principal.user_id,
                role=TripMemberRole.OWNER,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self._condition.notify_all()
        return self._copy(trip)

    async def list_trips(self, principal: Principal) -> list[TripView]:
        async with self._condition:
            items = [
                self._copy(trip)
                for trip in self._trips.values()
                if trip.tenant_id == principal.tenant_id
                and (
                    trip.owner_id == principal.user_id
                    or principal.roles.intersection({"admin", "tenant_admin"})
                    or (trip.trip_id, principal.user_id) in self._members
                )
            ]
        return sorted(items, key=lambda item: (item.updated_at, item.trip_id), reverse=True)

    async def get_trip(self, principal: Principal, trip_id: str) -> TripView:
        async with self._condition:
            return self._copy(self._trip_locked(principal, trip_id))

    async def patch_trip(
        self,
        principal: Principal,
        trip_id: str,
        request: TripPatchRequest,
    ) -> TripView:
        async with self._condition:
            current = self._trip_locked(principal, trip_id, write=True)
            changes = request.model_dump(exclude_unset=True)
            updated = current.model_copy(
                update={
                    **changes,
                    "version": current.version + 1,
                    "updated_at": utc_now(),
                }
            )
            self._trips[trip_id] = updated
            self._condition.notify_all()
            return self._copy(updated)

    async def set_trip_status(
        self,
        principal: Principal,
        trip_id: str,
        status: TripStatus,
    ) -> TripView:
        async with self._condition:
            current = self._trip_locked(principal, trip_id, write=True)
            updated = current.model_copy(
                update={
                    "status": status,
                    "version": current.version + 1,
                    "updated_at": utc_now(),
                }
            )
            self._trips[trip_id] = updated
            self._condition.notify_all()
            return self._copy(updated)

    async def list_trip_members(
        self,
        principal: Principal,
        trip_id: str,
    ) -> list[TripMemberView]:
        async with self._condition:
            self._trip_locked(principal, trip_id)
            items = [
                member.model_copy(deep=True)
                for (member_trip_id, _), member in self._members.items()
                if member_trip_id == trip_id and member.tenant_id == principal.tenant_id
            ]
        return sorted(items, key=lambda item: (item.role != TripMemberRole.OWNER, item.user_id))

    async def upsert_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
        request: TripMemberUpsertRequest,
    ) -> TripMemberView:
        if not user_id or len(user_id) > 128:
            raise ResourceNotFound("user not found")
        async with self._condition:
            trip = self._trip_locked(principal, trip_id, write=True)
            if trip.owner_id != principal.user_id and not principal.roles.intersection(
                {"admin", "tenant_admin"}
            ):
                raise ResourceForbidden("only the owner can manage members")
            if user_id == trip.owner_id:
                raise VersionConflict(trip.version)
            key = (trip_id, user_id)
            current = self._members.get(key)
            now = utc_now()
            member = TripMemberView(
                trip_id=trip_id,
                tenant_id=principal.tenant_id,
                user_id=user_id,
                role=TripMemberRole(request.role),
                version=(current.version + 1) if current else 1,
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            self._members[key] = member
            self._condition.notify_all()
            return member.model_copy(deep=True)

    async def remove_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
    ) -> None:
        async with self._condition:
            trip = self._trip_locked(principal, trip_id, write=True)
            if trip.owner_id != principal.user_id and not principal.roles.intersection(
                {"admin", "tenant_admin"}
            ):
                raise ResourceForbidden("only the owner can manage members")
            if user_id == trip.owner_id:
                raise VersionConflict(trip.version)
            if self._members.pop((trip_id, user_id), None) is None:
                raise ResourceNotFound("member not found")
            self._condition.notify_all()

    async def create_run(
        self,
        principal: Principal,
        *,
        trip_id: str,
        command: RunCommand,
        base_artifact_id: str | None,
        base_artifact_version: int | None,
        idempotency_key: str,
        request_hash: str,
        trace_id: str,
    ) -> IdempotentRunResult:
        async with self._condition:
            trip = self._trip_locked(principal, trip_id, write=True)
            if trip.status != TripStatus.ACTIVE:
                raise VersionConflict(trip.version)

            idempotency_scope = (principal.tenant_id, principal.user_id, idempotency_key)
            existing = self._idempotency.get(idempotency_scope)
            if existing is not None:
                existing_hash, existing_run_id = existing
                if existing_hash != request_hash:
                    raise IdempotencyConflict("idempotency key reused with different request")
                return IdempotentRunResult(
                    run=self._copy(self._runs[existing_run_id]),
                    event=None,
                    replayed=True,
                )

            current_snapshot: ArtifactView | None = None
            if trip.current_artifact_id is not None:
                versions = self._artifacts.get(trip.current_artifact_id, [])
                current_snapshot = next(
                    (
                        item
                        for item in versions
                        if item.version == trip.current_artifact_version
                    ),
                    None,
                )
            if command.type == "trip.plan":
                if (
                    current_snapshot is not None
                    and current_snapshot.artifact_type == "TripSnapshot"
                    and current_snapshot.status == ArtifactStatus.PUBLISHED
                ):
                    raise VersionConflict(current_snapshot.version)
            elif command.type == "trip.replan":
                current_version = trip.current_artifact_version or 1
                if (
                    current_snapshot is None
                    or current_snapshot.artifact_type != "TripSnapshot"
                    or current_snapshot.status != ArtifactStatus.PUBLISHED
                    or current_snapshot.artifact_id != base_artifact_id
                    or current_snapshot.version != base_artifact_version
                ):
                    raise VersionConflict(current_version)

            now = utc_now()
            run = RunView(
                run_id=new_public_id("run"),
                trip_id=trip.trip_id,
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                trace_id=trace_id,
                lifecycle_state=RunLifecycle.QUEUED,
                phase="accepted",
                control_version=1,
                command=command,
                base_artifact_id=base_artifact_id,
                base_artifact_version=base_artifact_version,
                created_at=now,
                updated_at=now,
            )
            self._runs[run.run_id] = run
            self._events[run.run_id] = []
            event = self._append_event_locked(
                run,
                event_type="run.accepted",
                event_data={
                    "lifecycle_state": run.lifecycle_state.value,
                    "phase": run.phase,
                    "control_version": run.control_version,
                },
                trace_id=trace_id,
                occurred_at=now,
            )
            self._idempotency[idempotency_scope] = (request_hash, run.run_id)
            self._condition.notify_all()
            return IdempotentRunResult(
                run=self._copy(run),
                event=self._copy(event),
                replayed=False,
            )

    async def get_run(self, principal: Principal, run_id: str) -> RunView:
        async with self._condition:
            return self._copy(self._run_locked(principal, run_id))

    async def claim_run_execution(
        self,
        principal: Principal,
        run_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> RunExecutionLease | None:
        validate_execution_lease_request(owner, lease_seconds)
        async with self._condition:
            run = self._run_locked(principal, run_id)
            if run.lifecycle_state not in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}:
                return None
            now = utc_now()
            current = self._execution_leases.get(run_id)
            if current is not None and current.lease_until > now:
                return None
            attempt = self._execution_attempts.get(run_id, 0) + 1
            lease = RunExecutionLease(
                run_id=run_id,
                owner=owner,
                attempt=attempt,
                lease_until=now + timedelta(seconds=lease_seconds),
            )
            self._execution_attempts[run_id] = attempt
            self._execution_leases[run_id] = lease
            self._condition.notify_all()
            return lease

    async def renew_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
        *,
        lease_seconds: float,
    ) -> RunExecutionLease | None:
        validate_execution_lease_request(lease.owner, lease_seconds)
        async with self._condition:
            try:
                self._assert_execution_lease_locked(principal, lease)
            except RunExecutionLeaseLost:
                return None
            renewed = RunExecutionLease(
                run_id=lease.run_id,
                owner=lease.owner,
                attempt=lease.attempt,
                lease_until=utc_now() + timedelta(seconds=lease_seconds),
            )
            self._execution_leases[lease.run_id] = renewed
            self._condition.notify_all()
            return renewed

    async def release_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
    ) -> bool:
        async with self._condition:
            self._run_locked(principal, lease.run_id)
            current = self._execution_leases.get(lease.run_id)
            if (
                current is None
                or current.owner != lease.owner
                or current.attempt != lease.attempt
            ):
                return False
            self._execution_leases.pop(lease.run_id, None)
            self._condition.notify_all()
            return True

    async def mutate_run(
        self,
        principal: Principal,
        run_id: str,
        *,
        expected_control_version: int,
        lifecycle_state: RunLifecycle | None = None,
        phase: str | None = None,
        pending_input: RunPendingInput | None = None,
        result_artifact: ArtifactView | None = None,
        public_error_code: str | None = None,
        execution_lease: RunExecutionLease | None = None,
        event_type: PUBLIC_EVENT_TYPES,
        event_data: dict[str, Any],
    ) -> tuple[RunView, RunEvent]:
        async with self._condition:
            current = self._run_locked(principal, run_id)
            if execution_lease is not None:
                if execution_lease.run_id != run_id:
                    raise RunExecutionLeaseLost("run execution lease targets another run")
                self._assert_execution_lease_locked(principal, execution_lease)
            if current.control_version != expected_control_version:
                raise VersionConflict(current.control_version)
            now = utc_now()
            updates: dict[str, Any] = {
                "control_version": current.control_version + 1,
                "updated_at": now,
            }
            if lifecycle_state is not None:
                updates["lifecycle_state"] = lifecycle_state
            if phase is not None:
                updates["phase"] = phase
            if pending_input is not None:
                updates["pending_input"] = pending_input
            if public_error_code is not None:
                updates["public_error_code"] = public_error_code
            if result_artifact is not None:
                updates["result_artifact_id"] = result_artifact.artifact_id
                updates["result_artifact_version"] = result_artifact.version
                versions = self._artifacts.get(result_artifact.artifact_id)
                if not versions:
                    raise ResourceNotFound("artifact not found")
                stored_artifact = next(
                    (item for item in versions if item.version == result_artifact.version),
                    None,
                )
                if stored_artifact is None or stored_artifact.trip_id != current.trip_id:
                    raise ResourceNotFound("artifact not found")
                published_artifact = stored_artifact.model_copy(
                    update={"status": ArtifactStatus.PUBLISHED}
                )
                versions[versions.index(stored_artifact)] = published_artifact
                if published_artifact.artifact_type == "TripSnapshot":
                    for candidate_versions in self._artifacts.values():
                        for index, candidate in enumerate(candidate_versions):
                            if (
                                candidate.trip_id == current.trip_id
                                and candidate.artifact_type == "TripSnapshot"
                                and candidate.status == ArtifactStatus.PUBLISHED
                                and not (
                                    candidate.artifact_id == stored_artifact.artifact_id
                                    and candidate.version == stored_artifact.version
                                )
                            ):
                                candidate_versions[index] = candidate.model_copy(
                                    update={"status": ArtifactStatus.SUPERSEDED}
                                )
                    trip = self._trip_locked(principal, current.trip_id, write=True)
                    self._trips[current.trip_id] = trip.model_copy(
                        update={
                            "current_artifact_id": published_artifact.artifact_id,
                            "current_artifact_version": published_artifact.version,
                            "version": trip.version + 1,
                            "updated_at": now,
                        }
                    )
            updated = current.model_copy(update=updates)
            self._runs[run_id] = updated
            if updated.lifecycle_state in TERMINAL_RUN_STATES | {
                RunLifecycle.CANCEL_REQUESTED,
                RunLifecycle.WAITING_INPUT,
            }:
                self._execution_leases.pop(run_id, None)
            event = self._append_event_locked(
                updated,
                event_type=event_type,
                event_data={**event_data, "control_version": updated.control_version},
                trace_id=updated.trace_id,
                occurred_at=now,
            )
            self._condition.notify_all()
            return self._copy(updated), self._copy(event)

    async def resume_run(
        self,
        principal: Principal,
        run_id: str,
        *,
        expected_control_version: int,
        request_id: str,
        values: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotentRunResult:
        async with self._condition:
            current = self._run_locked(principal, run_id)
            scope = (principal.tenant_id, principal.user_id, "run.resume", idempotency_key)
            existing = self._run_control_idempotency.get(scope)
            if existing is not None:
                existing_hash, existing_run_id = existing
                if existing_hash != request_hash or existing_run_id != run_id:
                    raise IdempotencyConflict("idempotency key reused with different request")
                return IdempotentRunResult(
                    run=self._copy(self._runs[run_id]),
                    event=None,
                    replayed=True,
                )
            if current.control_version != expected_control_version:
                raise VersionConflict(current.control_version)
            if current.lifecycle_state != RunLifecycle.WAITING_INPUT or current.pending_input is None:
                raise RunInputInvalid("run is not waiting for input")
            pending = current.pending_input
            if pending.request_id != request_id:
                raise RunInputInvalid("input request does not match the pending request")
            if pending.expires_at <= utc_now():
                raise RunInputExpired("pending input has expired")
            try:
                normalized = validate_run_input_values(pending, values)
            except ValueError:
                raise RunInputInvalid("resume input does not satisfy the pending schema") from None
            now = utc_now()
            command = current.command.model_copy(
                update={
                    "payload": {
                        **current.command.payload,
                        "resume_input": {
                            "request_id": request_id,
                            "values": normalized,
                        },
                    }
                }
            )
            updated = current.model_copy(
                update={
                    "lifecycle_state": RunLifecycle.QUEUED,
                    "phase": "accepted",
                    "control_version": current.control_version + 1,
                    "command": command,
                    "pending_input": None,
                    "updated_at": now,
                }
            )
            self._runs[run_id] = updated
            event = self._append_event_locked(
                updated,
                event_type="run.lifecycle_changed",
                event_data={
                    "previous_state": RunLifecycle.WAITING_INPUT.value,
                    "lifecycle_state": RunLifecycle.QUEUED.value,
                    "reason_code": "INPUT_SUPPLIED",
                    "control_version": updated.control_version,
                },
                trace_id=updated.trace_id,
                occurred_at=now,
            )
            self._run_control_idempotency[scope] = (request_hash, run_id)
            self._condition.notify_all()
            return IdempotentRunResult(
                run=self._copy(updated),
                event=self._copy(event),
                replayed=False,
            )

    async def list_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
    ) -> list[RunEvent]:
        async with self._condition:
            self._run_locked(principal, run_id)
            return [
                self._copy(event)
                for event in self._events.get(run_id, [])
                if event.seq > max(0, after_seq)
            ]

    async def wait_for_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
        timeout_seconds: float,
    ) -> bool:
        async with self._condition:
            self._run_locked(principal, run_id)

            def event_available() -> bool:
                current = self._run_locked(principal, run_id)
                has_new = any(event.seq > after_seq for event in self._events.get(run_id, []))
                return has_new or current.lifecycle_state in {
                    RunLifecycle.COMPLETED,
                    RunLifecycle.FAILED,
                    RunLifecycle.CANCELED,
                }

            try:
                await asyncio.wait_for(self._condition.wait_for(event_available), timeout=timeout_seconds)
            except TimeoutError:
                return False
            return True

    async def create_artifact(
        self,
        principal: Principal,
        *,
        trip_id: str,
        artifact_id: str | None = None,
        artifact_type: str,
        schema_version: int,
        content: dict[str, Any],
        status: ArtifactStatus,
        parent_version: int | None = None,
        execution_lease: RunExecutionLease | None = None,
    ) -> ArtifactView:
        async with self._condition:
            self._trip_locked(principal, trip_id, write=True)
            if execution_lease is not None:
                self._assert_execution_lease_locked(
                    principal,
                    execution_lease,
                    trip_id=trip_id,
                )
            resolved_artifact_id = artifact_id or new_public_id("artifact")
            if resolved_artifact_id in self._artifacts:
                raise VersionConflict(len(self._artifacts[resolved_artifact_id]))
            artifact = ArtifactView(
                artifact_id=resolved_artifact_id,
                version=1,
                trip_id=trip_id,
                tenant_id=principal.tenant_id,
                artifact_type=artifact_type,
                schema_version=schema_version,
                status=status,
                content=content,
                created_by=principal.user_id,
                created_at=utc_now(),
                parent_version=parent_version,
            )
            self._artifacts[resolved_artifact_id] = [artifact]
            self._condition.notify_all()
            return self._copy(artifact)

    async def list_artifacts(self, principal: Principal, trip_id: str) -> list[ArtifactView]:
        async with self._condition:
            self._trip_locked(principal, trip_id)
            items = [
                self._copy(version)
                for versions in self._artifacts.values()
                for version in versions
                if version.trip_id == trip_id and version.tenant_id == principal.tenant_id
            ]
        return sorted(items, key=lambda item: (item.created_at, item.artifact_id), reverse=True)

    async def get_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        *,
        version: int | None = None,
    ) -> ArtifactView:
        async with self._condition:
            return self._copy(
                self._artifact_locked(principal, artifact_id, version=version)
            )

    async def patch_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactPatchRequest,
    ) -> ArtifactView:
        async with self._condition:
            current = self._artifact_locked(principal, artifact_id, write=True)
            ensure_artifact_mutable(current)
            if current.version != request.base_version:
                raise VersionConflict(current.version)
            content = validate_artifact_patch_content(current, request)
            updated = ArtifactView(
                artifact_id=current.artifact_id,
                version=current.version + 1,
                trip_id=current.trip_id,
                tenant_id=current.tenant_id,
                artifact_type=current.artifact_type,
                schema_version=current.schema_version,
                status=ArtifactStatus.CANDIDATE,
                content=content,
                created_by=current.created_by,
                created_at=utc_now(),
                parent_version=current.version,
            )
            self._artifacts[artifact_id].append(updated)
            self._condition.notify_all()
            return self._copy(updated)

    async def command_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactCommandRequest,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotentArtifactResult:
        async with self._condition:
            current = self._artifact_locked(principal, artifact_id, write=True)
            ensure_artifact_mutable(current)
            idempotency_scope = (
                principal.tenant_id,
                principal.user_id,
                artifact_id,
                idempotency_key,
            )
            existing = self._artifact_idempotency.get(idempotency_scope)
            if existing is not None:
                existing_hash, response = existing
                if existing_hash != request_hash:
                    raise IdempotencyConflict("idempotency key reused with different request")
                return IdempotentArtifactResult(
                    artifact=self._copy(response),
                    replayed=True,
                )

            if current.version != request.base_version:
                raise VersionConflict(current.version)
            transitions = {
                "artifact.select": (ArtifactStatus.CANDIDATE, ArtifactStatus.SELECTED),
                "artifact.publish": (ArtifactStatus.VALIDATED, ArtifactStatus.PUBLISHED),
                "artifact.revoke": (ArtifactStatus.PUBLISHED, ArtifactStatus.REVOKED),
            }
            required, target = transitions[request.type]
            if current.status != required:
                raise ArtifactTransitionConflict(
                    current_version=current.version,
                    current_status=current.status,
                    command=request.type,
                )

            versions = self._artifacts[artifact_id]
            updated = current.model_copy(update={"status": target})
            versions[versions.index(current)] = updated
            now = utc_now()
            if target == ArtifactStatus.PUBLISHED:
                for candidate_versions in self._artifacts.values():
                    for index, candidate in enumerate(candidate_versions):
                        if (
                            candidate.trip_id == current.trip_id
                            and candidate.status == ArtifactStatus.PUBLISHED
                            and not (
                                candidate.artifact_id == current.artifact_id
                                and candidate.version == current.version
                            )
                        ):
                            candidate_versions[index] = candidate.model_copy(
                                update={"status": ArtifactStatus.SUPERSEDED}
                            )
                trip = self._trip_locked(principal, current.trip_id, write=True)
                self._trips[trip.trip_id] = trip.model_copy(
                    update={
                        "current_artifact_id": current.artifact_id,
                        "current_artifact_version": current.version,
                        "version": trip.version + 1,
                        "updated_at": now,
                    }
                )
            elif target == ArtifactStatus.REVOKED:
                trip = self._trip_locked(principal, current.trip_id, write=True)
                if (
                    trip.current_artifact_id == current.artifact_id
                    and trip.current_artifact_version == current.version
                ):
                    self._trips[trip.trip_id] = trip.model_copy(
                        update={
                            "current_artifact_id": None,
                            "current_artifact_version": None,
                            "version": trip.version + 1,
                            "updated_at": now,
                        }
                    )

            response = self._copy(updated)
            self._artifact_idempotency[idempotency_scope] = (request_hash, response)
            self._condition.notify_all()
            return IdempotentArtifactResult(artifact=response, replayed=False)
