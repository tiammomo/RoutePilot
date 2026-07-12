"""PostgreSQL implementation of the V1 persistence boundary.

Every Run transition, browser-safe event, Artifact publication, Trip pointer,
and outbox record is committed in one transaction. The event cursor is the
same monotonic value as ``Run.control_version``.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from time import monotonic
from typing import Any, cast

from sqlalchemy import and_, exists, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

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
from .sql_tables import (
    artifact_versions_table,
    artifacts_table,
    idempotency_keys_table,
    outbox_events_table,
    run_public_events_table,
    runs_table,
    trips_table,
    trip_members_table,
)
from .store import (
    ArtifactTransitionConflict,
    IdempotencyConflict,
    IdempotentArtifactResult,
    IdempotentRunResult,
    ResourceForbidden,
    ResourceNotFound,
    RunInputExpired,
    RunInputInvalid,
    RunExecutionLease,
    RunExecutionLeaseLost,
    VersionConflict,
    ensure_artifact_mutable,
    validate_artifact_patch_content,
    validate_execution_lease_request,
)


def normalize_async_database_url(database_url: str) -> str:
    """Normalize a PostgreSQL DSN for SQLAlchemy's asyncio extension."""

    normalized = str(database_url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    if normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    if not normalized.startswith("postgresql+psycopg://"):
        raise ValueError("RoutePilot V1 durable storage requires a PostgreSQL psycopg DSN")
    return normalized


class PostgresPlatformStore:
    """Tenant-scoped, CAS-protected PostgreSQL store."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresPlatformStore":
        engine = create_async_engine(
            normalize_async_database_url(database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        return cls(engine)

    @staticmethod
    def _is_tenant_admin(principal: Principal) -> bool:
        return bool(principal.roles.intersection({"admin", "tenant_admin"}))

    @staticmethod
    def _trip_from_row(row: Any) -> TripView:
        return TripView.model_validate(dict(row))

    @staticmethod
    def _run_from_row(row: Any) -> RunView:
        payload = dict(row)
        return RunView.model_validate(
            {name: payload[name] for name in RunView.model_fields if name in payload}
        )

    @staticmethod
    def _event_from_row(row: Any) -> RunEvent:
        payload = dict(row)
        payload.pop("tenant_id", None)
        return RunEvent.model_validate(payload)

    @staticmethod
    def _artifact_from_row(row: Any) -> ArtifactView:
        return ArtifactView.model_validate(dict(row))

    @staticmethod
    def _artifact_projection() -> tuple[Any, ...]:
        return (
            artifacts_table.c.artifact_id,
            artifact_versions_table.c.version,
            artifacts_table.c.trip_id,
            artifacts_table.c.tenant_id,
            artifacts_table.c.artifact_type,
            artifact_versions_table.c.schema_version,
            artifact_versions_table.c.status,
            artifact_versions_table.c.content,
            artifacts_table.c.created_by,
            artifact_versions_table.c.created_at,
            artifact_versions_table.c.parent_version,
        )

    async def _get_trip_tx(
        self,
        connection: AsyncConnection,
        principal: Principal,
        trip_id: str,
        *,
        write: bool = False,
        lock: bool = False,
    ) -> TripView:
        statement = select(trips_table).where(
            trips_table.c.trip_id == trip_id,
            trips_table.c.tenant_id == principal.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None:
            raise ResourceNotFound("trip not found")
        trip = self._trip_from_row(row)
        if trip.owner_id != principal.user_id and not self._is_tenant_admin(principal):
            member_role = (
                await connection.execute(
                    select(trip_members_table.c.role).where(
                        trip_members_table.c.tenant_id == principal.tenant_id,
                        trip_members_table.c.trip_id == trip_id,
                        trip_members_table.c.user_id == principal.user_id,
                    )
                )
            ).scalar_one_or_none()
            if member_role is None or (write and member_role != TripMemberRole.EDITOR.value):
                raise ResourceForbidden("trip access denied")
        return trip

    async def _get_run_tx(
        self,
        connection: AsyncConnection,
        principal: Principal,
        run_id: str,
        *,
        lock: bool = False,
    ) -> RunView:
        statement = select(runs_table).where(
            runs_table.c.run_id == run_id,
            runs_table.c.tenant_id == principal.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None:
            raise ResourceNotFound("run not found")
        run = self._run_from_row(row)
        await self._get_trip_tx(connection, principal, run.trip_id)
        return run

    async def _assert_execution_lease_tx(
        self,
        connection: AsyncConnection,
        run: RunView,
        lease: RunExecutionLease,
        *,
        trip_id: str | None = None,
    ) -> None:
        """Validate a lease against the locked Run row using database time."""

        if lease.run_id != run.run_id or (trip_id is not None and run.trip_id != trip_id):
            raise RunExecutionLeaseLost("run execution lease targets another aggregate")
        row = (
            await connection.execute(
                select(
                    runs_table.c.execution_lease_owner,
                    runs_table.c.execution_lease_until,
                    runs_table.c.execution_attempt,
                    runs_table.c.lifecycle_state,
                ).where(
                    runs_table.c.run_id == run.run_id,
                    runs_table.c.tenant_id == run.tenant_id,
                )
            )
        ).mappings().one_or_none()
        database_now = (await connection.execute(select(func.now()))).scalar_one()
        if (
            row is None
            or row["execution_lease_owner"] != lease.owner
            or int(row["execution_attempt"]) != lease.attempt
            or row["execution_lease_until"] is None
            or row["execution_lease_until"] <= database_now
            or row["lifecycle_state"]
            not in {RunLifecycle.QUEUED.value, RunLifecycle.RUNNING.value}
        ):
            raise RunExecutionLeaseLost("run execution lease is no longer valid")

    async def _get_artifact_tx(
        self,
        connection: AsyncConnection,
        principal: Principal,
        artifact_id: str,
        *,
        version: int | None = None,
        write: bool = False,
        lock: bool = False,
    ) -> ArtifactView:
        metadata = (
            await connection.execute(
                select(artifacts_table).where(
                    artifacts_table.c.artifact_id == artifact_id,
                    artifacts_table.c.tenant_id == principal.tenant_id,
                )
            )
        ).mappings().one_or_none()
        if metadata is None:
            raise ResourceNotFound("artifact not found")

        # All Artifact writers lock Trip before Artifact rows. Publication uses
        # the same order, preventing cross-artifact pointer/supersede deadlocks.
        await self._get_trip_tx(
            connection,
            principal,
            cast(str, metadata["trip_id"]),
            write=write,
            lock=lock and write,
        )
        if lock:
            locked = (
                await connection.execute(
                    select(artifacts_table.c.artifact_id)
                    .where(
                        artifacts_table.c.artifact_id == artifact_id,
                        artifacts_table.c.tenant_id == principal.tenant_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if locked is None:
                raise ResourceNotFound("artifact not found")

        statement = (
            select(*self._artifact_projection())
            .select_from(
                artifacts_table.join(
                    artifact_versions_table,
                    artifacts_table.c.artifact_id == artifact_versions_table.c.artifact_id,
                )
            )
            .where(
                artifacts_table.c.artifact_id == artifact_id,
                artifacts_table.c.tenant_id == principal.tenant_id,
            )
        )
        if version is None:
            statement = statement.order_by(artifact_versions_table.c.version.desc()).limit(1)
        else:
            statement = statement.where(artifact_versions_table.c.version == version)
        if lock:
            statement = statement.with_for_update()
        row = (await connection.execute(statement)).mappings().one_or_none()
        if row is None:
            raise ResourceNotFound("artifact version not found")
        return self._artifact_from_row(row)

    @staticmethod
    def _artifact_idempotency_fingerprint(
        principal: Principal,
        artifact_id: str,
        idempotency_key: str,
    ) -> str:
        value = "\x1f".join(
            (principal.tenant_id, principal.user_id, artifact_id, idempotency_key)
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _advisory_lock_id(fingerprint: str) -> int:
        value = int(fingerprint[:16], 16)
        return value if value < 2**63 else value - 2**64

    @staticmethod
    async def _insert_outbox(
        connection: AsyncConnection,
        *,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        await connection.execute(
            insert(outbox_events_table).values(
                outbox_id=new_public_id("outbox"),
                tenant_id=tenant_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload=payload,
                created_at=utc_now(),
                available_at=utc_now(),
                publish_attempts=0,
            )
        )

    @staticmethod
    async def _scope_tenant(connection: AsyncConnection, principal: Principal) -> None:
        """Set a transaction-local PostgreSQL RLS tenant without pool leakage."""

        await connection.execute(
            select(func.set_config("routepilot.tenant_id", principal.tenant_id, True))
        )

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
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            await connection.execute(insert(trips_table).values(**trip.model_dump(mode="python")))
            await connection.execute(
                insert(trip_members_table).values(
                    tenant_id=trip.tenant_id,
                    trip_id=trip.trip_id,
                    user_id=principal.user_id,
                    role=TripMemberRole.OWNER.value,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=trip.tenant_id,
                aggregate_type="trip",
                aggregate_id=trip.trip_id,
                event_type="trip.created",
                payload={"trip_id": trip.trip_id, "version": trip.version},
            )
        return trip

    async def list_trips(self, principal: Principal) -> list[TripView]:
        access_filter = trips_table.c.tenant_id == principal.tenant_id
        if not self._is_tenant_admin(principal):
            membership = exists(
                select(trip_members_table.c.trip_id).where(
                    trip_members_table.c.tenant_id == principal.tenant_id,
                    trip_members_table.c.trip_id == trips_table.c.trip_id,
                    trip_members_table.c.user_id == principal.user_id,
                )
            )
            access_filter = and_(access_filter, membership)
        statement = select(trips_table).where(access_filter).order_by(
            trips_table.c.updated_at.desc(),
            trips_table.c.trip_id.desc(),
        )
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            rows = (await connection.execute(statement)).mappings().all()
        return [self._trip_from_row(row) for row in rows]

    async def get_trip(self, principal: Principal, trip_id: str) -> TripView:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            return await self._get_trip_tx(connection, principal, trip_id)

    async def patch_trip(
        self,
        principal: Principal,
        trip_id: str,
        request: TripPatchRequest,
    ) -> TripView:
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            current = await self._get_trip_tx(connection, principal, trip_id, write=True, lock=True)
            values = {
                **request.model_dump(exclude_unset=True),
                "version": current.version + 1,
                "updated_at": utc_now(),
            }
            row = (
                await connection.execute(
                    update(trips_table)
                    .where(
                        trips_table.c.trip_id == trip_id,
                        trips_table.c.tenant_id == principal.tenant_id,
                        trips_table.c.version == current.version,
                    )
                    .values(**values)
                    .returning(trips_table)
                )
            ).mappings().one_or_none()
            if row is None:
                raise VersionConflict(current.version)
            updated_trip = self._trip_from_row(row)
            await self._insert_outbox(
                connection,
                tenant_id=principal.tenant_id,
                aggregate_type="trip",
                aggregate_id=trip_id,
                event_type="trip.updated",
                payload={"trip_id": trip_id, "version": updated_trip.version},
            )
            return updated_trip

    async def set_trip_status(
        self,
        principal: Principal,
        trip_id: str,
        status: TripStatus,
    ) -> TripView:
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            current = await self._get_trip_tx(connection, principal, trip_id, write=True, lock=True)
            row = (
                await connection.execute(
                    update(trips_table)
                    .where(
                        trips_table.c.trip_id == trip_id,
                        trips_table.c.tenant_id == principal.tenant_id,
                        trips_table.c.version == current.version,
                    )
                    .values(status=status.value, version=current.version + 1, updated_at=utc_now())
                    .returning(trips_table)
                )
            ).mappings().one_or_none()
            if row is None:
                raise VersionConflict(current.version)
            updated_trip = self._trip_from_row(row)
            await self._insert_outbox(
                connection,
                tenant_id=principal.tenant_id,
                aggregate_type="trip",
                aggregate_id=trip_id,
                event_type=f"trip.{status.value}",
                payload={"trip_id": trip_id, "version": updated_trip.version},
            )
            return updated_trip

    async def list_trip_members(
        self,
        principal: Principal,
        trip_id: str,
    ) -> list[TripMemberView]:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            await self._get_trip_tx(connection, principal, trip_id)
            rows = (
                await connection.execute(
                    select(trip_members_table)
                    .where(
                        trip_members_table.c.tenant_id == principal.tenant_id,
                        trip_members_table.c.trip_id == trip_id,
                    )
                    .order_by(
                        (trip_members_table.c.role != TripMemberRole.OWNER.value),
                        trip_members_table.c.user_id,
                    )
                )
            ).mappings().all()
        return [TripMemberView.model_validate(dict(row)) for row in rows]

    async def upsert_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
        request: TripMemberUpsertRequest,
    ) -> TripMemberView:
        if not user_id or len(user_id) > 128:
            raise ResourceNotFound("user not found")
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            trip = await self._get_trip_tx(connection, principal, trip_id, write=True, lock=True)
            if trip.owner_id != principal.user_id and not self._is_tenant_admin(principal):
                raise ResourceForbidden("only the owner can manage members")
            if user_id == trip.owner_id:
                raise VersionConflict(trip.version)
            current = (
                await connection.execute(
                    select(trip_members_table)
                    .where(
                        trip_members_table.c.tenant_id == principal.tenant_id,
                        trip_members_table.c.trip_id == trip_id,
                        trip_members_table.c.user_id == user_id,
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            now = utc_now()
            row: Any
            if current is None:
                values = {
                    "tenant_id": principal.tenant_id,
                    "trip_id": trip_id,
                    "user_id": user_id,
                    "role": request.role,
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                row = (
                    await connection.execute(
                        insert(trip_members_table).values(**values).returning(trip_members_table)
                    )
                ).mappings().one()
            else:
                row = (
                    await connection.execute(
                        update(trip_members_table)
                        .where(
                            trip_members_table.c.tenant_id == principal.tenant_id,
                            trip_members_table.c.trip_id == trip_id,
                            trip_members_table.c.user_id == user_id,
                            trip_members_table.c.version == int(current["version"]),
                        )
                        .values(
                            role=request.role,
                            version=int(current["version"]) + 1,
                            updated_at=now,
                        )
                        .returning(trip_members_table)
                    )
                ).mappings().one_or_none()
                if row is None:
                    raise VersionConflict(int(current["version"]))
            member = TripMemberView.model_validate(dict(row))
            await self._insert_outbox(
                connection,
                tenant_id=principal.tenant_id,
                aggregate_type="trip",
                aggregate_id=trip_id,
                event_type="trip.member_upserted",
                payload={
                    "trip_id": trip_id,
                    "user_id": user_id,
                    "role": member.role.value,
                    "version": member.version,
                },
            )
            return member

    async def remove_trip_member(
        self,
        principal: Principal,
        trip_id: str,
        user_id: str,
    ) -> None:
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            trip = await self._get_trip_tx(connection, principal, trip_id, write=True, lock=True)
            if trip.owner_id != principal.user_id and not self._is_tenant_admin(principal):
                raise ResourceForbidden("only the owner can manage members")
            if user_id == trip.owner_id:
                raise VersionConflict(trip.version)
            deleted = await connection.execute(
                trip_members_table.delete().where(
                    trip_members_table.c.tenant_id == principal.tenant_id,
                    trip_members_table.c.trip_id == trip_id,
                    trip_members_table.c.user_id == user_id,
                )
            )
            if not deleted.rowcount:
                raise ResourceNotFound("member not found")
            await self._insert_outbox(
                connection,
                tenant_id=principal.tenant_id,
                aggregate_type="trip",
                aggregate_id=trip_id,
                event_type="trip.member_removed",
                payload={"trip_id": trip_id, "user_id": user_id},
            )

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
        now = utc_now()
        run_id = new_public_id("run")
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            trip = await self._get_trip_tx(connection, principal, trip_id, write=True, lock=True)
            if trip.status != TripStatus.ACTIVE:
                raise VersionConflict(trip.version)

            reservation = (
                await connection.execute(
                    pg_insert(idempotency_keys_table)
                    .values(
                        tenant_id=principal.tenant_id,
                        actor_id=principal.user_id,
                        operation="run.create",
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_run_id=run_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "tenant_id",
                            "actor_id",
                            "operation",
                            "idempotency_key",
                        ]
                    )
                    .returning(idempotency_keys_table.c.response_run_id)
                )
            ).scalar_one_or_none()
            if reservation is None:
                existing = (
                    await connection.execute(
                        select(idempotency_keys_table).where(
                            idempotency_keys_table.c.tenant_id == principal.tenant_id,
                            idempotency_keys_table.c.actor_id == principal.user_id,
                            idempotency_keys_table.c.operation == "run.create",
                            idempotency_keys_table.c.idempotency_key == idempotency_key,
                        )
                    )
                ).mappings().one()
                if existing["request_hash"] != request_hash:
                    raise IdempotencyConflict("idempotency key reused with different request")
                replayed = await self._get_run_tx(
                    connection,
                    principal,
                    cast(str, existing["response_run_id"]),
                )
                return IdempotentRunResult(run=replayed, event=None, replayed=True)

            current_snapshot: ArtifactView | None = None
            if trip.current_artifact_id is not None:
                current_snapshot = await self._get_artifact_tx(
                    connection,
                    principal,
                    trip.current_artifact_id,
                    version=trip.current_artifact_version,
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

            run = RunView(
                run_id=run_id,
                trip_id=trip_id,
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
            await connection.execute(insert(runs_table).values(**run.model_dump(mode="python")))
            event = RunEvent(
                event_id=new_public_id("evt"),
                seq=1,
                type="run.accepted",
                occurred_at=now,
                trip_id=run.trip_id,
                run_id=run.run_id,
                trace_id=run.trace_id,
                data={
                    "lifecycle_state": run.lifecycle_state.value,
                    "phase": run.phase,
                    "control_version": run.control_version,
                },
            )
            event_payload = event.model_dump(mode="json")
            await connection.execute(
                insert(run_public_events_table).values(
                    tenant_id=run.tenant_id,
                    **event.model_dump(mode="python"),
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=run.tenant_id,
                aggregate_type="run",
                aggregate_id=run.run_id,
                event_type=event.type,
                payload=event_payload,
            )
            await self._insert_outbox(
                connection,
                tenant_id=run.tenant_id,
                aggregate_type="run",
                aggregate_id=run.run_id,
                event_type="run.dispatch.requested",
                payload={
                    "tenant_id": run.tenant_id,
                    "actor_id": run.actor_id,
                    "trip_id": run.trip_id,
                    "run_id": run.run_id,
                    "trace_id": run.trace_id,
                    "control_version": run.control_version,
                },
            )
            return IdempotentRunResult(run=run, event=event, replayed=False)

    async def get_run(self, principal: Principal, run_id: str) -> RunView:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            return await self._get_run_tx(connection, principal, run_id)

    async def claim_run_execution(
        self,
        principal: Principal,
        run_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> RunExecutionLease | None:
        validate_execution_lease_request(owner, lease_seconds)
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            run = await self._get_run_tx(connection, principal, run_id, lock=True)
            if run.lifecycle_state not in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}:
                return None
            row = (
                await connection.execute(
                    select(
                        runs_table.c.execution_lease_owner,
                        runs_table.c.execution_lease_until,
                        runs_table.c.execution_attempt,
                    ).where(
                        runs_table.c.run_id == run_id,
                        runs_table.c.tenant_id == principal.tenant_id,
                    )
                )
            ).mappings().one()
            database_now = (await connection.execute(select(func.now()))).scalar_one()
            if (
                row["execution_lease_owner"] is not None
                and row["execution_lease_until"] is not None
                and row["execution_lease_until"] > database_now
            ):
                return None
            current_attempt = int(row["execution_attempt"])
            next_attempt = current_attempt + 1
            lease_until = database_now + timedelta(seconds=lease_seconds)
            claimed_until = (
                await connection.execute(
                    update(runs_table)
                    .where(
                        runs_table.c.run_id == run_id,
                        runs_table.c.tenant_id == principal.tenant_id,
                        runs_table.c.execution_attempt == current_attempt,
                        runs_table.c.lifecycle_state.in_(
                            [RunLifecycle.QUEUED.value, RunLifecycle.RUNNING.value]
                        ),
                    )
                    .values(
                        execution_lease_owner=owner,
                        execution_lease_until=lease_until,
                        execution_attempt=next_attempt,
                    )
                    .returning(runs_table.c.execution_lease_until)
                )
            ).scalar_one_or_none()
            if claimed_until is None:
                return None
            return RunExecutionLease(
                run_id=run_id,
                owner=owner,
                attempt=next_attempt,
                lease_until=claimed_until,
            )

    async def renew_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
        *,
        lease_seconds: float,
    ) -> RunExecutionLease | None:
        validate_execution_lease_request(lease.owner, lease_seconds)
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            await self._get_run_tx(connection, principal, lease.run_id)
            database_now = (await connection.execute(select(func.now()))).scalar_one()
            renewed_until = (
                await connection.execute(
                    update(runs_table)
                    .where(
                        runs_table.c.run_id == lease.run_id,
                        runs_table.c.tenant_id == principal.tenant_id,
                        runs_table.c.execution_lease_owner == lease.owner,
                        runs_table.c.execution_attempt == lease.attempt,
                        runs_table.c.execution_lease_until > database_now,
                        runs_table.c.lifecycle_state.in_(
                            [RunLifecycle.QUEUED.value, RunLifecycle.RUNNING.value]
                        ),
                    )
                    .values(
                        execution_lease_until=database_now
                        + timedelta(seconds=lease_seconds)
                    )
                    .returning(runs_table.c.execution_lease_until)
                )
            ).scalar_one_or_none()
            if renewed_until is None:
                return None
            return RunExecutionLease(
                run_id=lease.run_id,
                owner=lease.owner,
                attempt=lease.attempt,
                lease_until=renewed_until,
            )

    async def release_run_execution(
        self,
        principal: Principal,
        lease: RunExecutionLease,
    ) -> bool:
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            await self._get_run_tx(connection, principal, lease.run_id)
            released = await connection.execute(
                update(runs_table)
                .where(
                    runs_table.c.run_id == lease.run_id,
                    runs_table.c.tenant_id == principal.tenant_id,
                    runs_table.c.execution_lease_owner == lease.owner,
                    runs_table.c.execution_attempt == lease.attempt,
                )
                .values(
                    execution_lease_owner=None,
                    execution_lease_until=None,
                )
            )
            return bool(released.rowcount)

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
        now = utc_now()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            current = await self._get_run_tx(connection, principal, run_id, lock=True)
            if execution_lease is not None:
                await self._assert_execution_lease_tx(
                    connection,
                    current,
                    execution_lease,
                )
            if current.control_version != expected_control_version:
                raise VersionConflict(current.control_version)
            new_version = current.control_version + 1
            values: dict[str, Any] = {
                "control_version": new_version,
                "updated_at": now,
            }
            if lifecycle_state is not None:
                values["lifecycle_state"] = lifecycle_state.value
            if phase is not None:
                values["phase"] = phase
            if pending_input is not None:
                values["pending_input"] = pending_input.model_dump(mode="json")
            if public_error_code is not None:
                values["public_error_code"] = public_error_code
            if lifecycle_state in TERMINAL_RUN_STATES | {
                RunLifecycle.CANCEL_REQUESTED,
                RunLifecycle.WAITING_INPUT,
            }:
                values["execution_lease_owner"] = None
                values["execution_lease_until"] = None

            if result_artifact is not None:
                trip = await self._get_trip_tx(
                    connection,
                    principal,
                    current.trip_id,
                    write=True,
                    lock=True,
                )
                artifact_row = (
                    await connection.execute(
                        select(
                            artifacts_table.c.artifact_id,
                            artifacts_table.c.trip_id,
                            artifacts_table.c.tenant_id,
                            artifact_versions_table.c.version,
                        )
                        .select_from(
                            artifacts_table.join(
                                artifact_versions_table,
                                artifacts_table.c.artifact_id == artifact_versions_table.c.artifact_id,
                            )
                        )
                        .where(
                            artifacts_table.c.artifact_id == result_artifact.artifact_id,
                            artifacts_table.c.trip_id == current.trip_id,
                            artifacts_table.c.tenant_id == principal.tenant_id,
                            artifact_versions_table.c.version == result_artifact.version,
                        )
                        .with_for_update()
                    )
                ).mappings().one_or_none()
                if artifact_row is None:
                    raise ResourceNotFound("artifact not found")
                await connection.execute(
                    update(artifact_versions_table)
                    .where(
                        artifact_versions_table.c.artifact_id == result_artifact.artifact_id,
                        artifact_versions_table.c.version == result_artifact.version,
                    )
                    .values(status=ArtifactStatus.PUBLISHED.value)
                )
                if trip.current_artifact_id and not (
                    trip.current_artifact_id == result_artifact.artifact_id
                    and trip.current_artifact_version == result_artifact.version
                ):
                    await connection.execute(
                        update(artifact_versions_table)
                        .where(
                            artifact_versions_table.c.artifact_id == trip.current_artifact_id,
                            artifact_versions_table.c.version == trip.current_artifact_version,
                            artifact_versions_table.c.status == ArtifactStatus.PUBLISHED.value,
                        )
                        .values(status=ArtifactStatus.SUPERSEDED.value)
                    )
                await connection.execute(
                    update(trips_table)
                    .where(
                        trips_table.c.trip_id == trip.trip_id,
                        trips_table.c.tenant_id == principal.tenant_id,
                        trips_table.c.version == trip.version,
                    )
                    .values(
                        current_artifact_id=result_artifact.artifact_id,
                        current_artifact_version=result_artifact.version,
                        version=trip.version + 1,
                        updated_at=now,
                    )
                )
                values["result_artifact_id"] = result_artifact.artifact_id
                values["result_artifact_version"] = result_artifact.version

            row = (
                await connection.execute(
                    update(runs_table)
                    .where(
                        runs_table.c.run_id == run_id,
                        runs_table.c.tenant_id == principal.tenant_id,
                        runs_table.c.control_version == expected_control_version,
                    )
                    .values(**values)
                    .returning(runs_table)
                )
            ).mappings().one_or_none()
            if row is None:
                raise VersionConflict(current.control_version)
            updated_run = self._run_from_row(row)
            event = RunEvent(
                event_id=new_public_id("evt"),
                seq=new_version,
                type=event_type,
                occurred_at=now,
                trip_id=updated_run.trip_id,
                run_id=updated_run.run_id,
                trace_id=updated_run.trace_id,
                data={**event_data, "control_version": new_version},
            )
            event_payload = event.model_dump(mode="json")
            await connection.execute(
                insert(run_public_events_table).values(
                    tenant_id=updated_run.tenant_id,
                    **event.model_dump(mode="python"),
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=updated_run.tenant_id,
                aggregate_type="run",
                aggregate_id=updated_run.run_id,
                event_type=event.type,
                payload=event_payload,
            )
            return updated_run, event

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
        now = utc_now()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            current = await self._get_run_tx(connection, principal, run_id, lock=True)
            await self._get_trip_tx(
                connection,
                principal,
                current.trip_id,
                write=True,
            )
            reservation = (
                await connection.execute(
                    pg_insert(idempotency_keys_table)
                    .values(
                        tenant_id=principal.tenant_id,
                        actor_id=principal.user_id,
                        operation="run.resume",
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_run_id=run_id,
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "tenant_id",
                            "actor_id",
                            "operation",
                            "idempotency_key",
                        ]
                    )
                    .returning(idempotency_keys_table.c.response_run_id)
                )
            ).scalar_one_or_none()
            if reservation is None:
                existing = (
                    await connection.execute(
                        select(idempotency_keys_table).where(
                            idempotency_keys_table.c.tenant_id == principal.tenant_id,
                            idempotency_keys_table.c.actor_id == principal.user_id,
                            idempotency_keys_table.c.operation == "run.resume",
                            idempotency_keys_table.c.idempotency_key == idempotency_key,
                        )
                    )
                ).mappings().one()
                if (
                    existing["request_hash"] != request_hash
                    or existing["response_run_id"] != run_id
                ):
                    raise IdempotencyConflict("idempotency key reused with different request")
                replayed = await self._get_run_tx(connection, principal, run_id)
                return IdempotentRunResult(run=replayed, event=None, replayed=True)

            if current.control_version != expected_control_version:
                raise VersionConflict(current.control_version)
            if current.lifecycle_state != RunLifecycle.WAITING_INPUT or current.pending_input is None:
                raise RunInputInvalid("run is not waiting for input")
            pending = current.pending_input
            if pending.request_id != request_id:
                raise RunInputInvalid("input request does not match the pending request")
            database_now = (await connection.execute(select(func.now()))).scalar_one()
            if pending.expires_at <= database_now:
                raise RunInputExpired("pending input has expired")
            try:
                normalized = validate_run_input_values(pending, values)
            except ValueError:
                raise RunInputInvalid("resume input does not satisfy the pending schema") from None
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
            next_version = current.control_version + 1
            row = (
                await connection.execute(
                    update(runs_table)
                    .where(
                        runs_table.c.run_id == run_id,
                        runs_table.c.tenant_id == principal.tenant_id,
                        runs_table.c.control_version == expected_control_version,
                        runs_table.c.lifecycle_state == RunLifecycle.WAITING_INPUT.value,
                    )
                    .values(
                        lifecycle_state=RunLifecycle.QUEUED.value,
                        phase="accepted",
                        control_version=next_version,
                        command=command.model_dump(mode="json"),
                        pending_input=None,
                        updated_at=now,
                    )
                    .returning(runs_table)
                )
            ).mappings().one_or_none()
            if row is None:
                raise VersionConflict(current.control_version)
            updated = self._run_from_row(row)
            event = RunEvent(
                event_id=new_public_id("evt"),
                seq=next_version,
                type="run.lifecycle_changed",
                occurred_at=now,
                trip_id=updated.trip_id,
                run_id=updated.run_id,
                trace_id=updated.trace_id,
                data={
                    "previous_state": RunLifecycle.WAITING_INPUT.value,
                    "lifecycle_state": RunLifecycle.QUEUED.value,
                    "reason_code": "INPUT_SUPPLIED",
                    "control_version": next_version,
                },
            )
            event_payload = event.model_dump(mode="json")
            await connection.execute(
                insert(run_public_events_table).values(
                    tenant_id=updated.tenant_id,
                    **event.model_dump(mode="python"),
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=updated.tenant_id,
                aggregate_type="run",
                aggregate_id=updated.run_id,
                event_type=event.type,
                payload=event_payload,
            )
            await self._insert_outbox(
                connection,
                tenant_id=updated.tenant_id,
                aggregate_type="run",
                aggregate_id=updated.run_id,
                event_type="run.dispatch.requested",
                payload={
                    "tenant_id": updated.tenant_id,
                    "actor_id": updated.actor_id,
                    "trip_id": updated.trip_id,
                    "run_id": updated.run_id,
                    "trace_id": updated.trace_id,
                    "control_version": updated.control_version,
                },
            )
            return IdempotentRunResult(run=updated, event=event, replayed=False)

    async def list_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
    ) -> list[RunEvent]:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            await self._get_run_tx(connection, principal, run_id)
            rows = (
                await connection.execute(
                    select(run_public_events_table)
                    .where(
                        run_public_events_table.c.tenant_id == principal.tenant_id,
                        run_public_events_table.c.run_id == run_id,
                        run_public_events_table.c.seq > max(0, after_seq),
                    )
                    .order_by(run_public_events_table.c.seq)
                )
            ).mappings().all()
        return [self._event_from_row(row) for row in rows]

    async def wait_for_events(
        self,
        principal: Principal,
        run_id: str,
        *,
        after_seq: int,
        timeout_seconds: float,
    ) -> bool:
        deadline = monotonic() + max(0.0, timeout_seconds)
        while True:
            run = await self.get_run(principal, run_id)
            async with self.engine.connect() as connection:
                await self._scope_tenant(connection, principal)
                available = (
                    await connection.execute(
                        select(run_public_events_table.c.event_id)
                        .where(
                            run_public_events_table.c.tenant_id == principal.tenant_id,
                            run_public_events_table.c.run_id == run_id,
                            run_public_events_table.c.seq > after_seq,
                        )
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if available is not None or run.lifecycle_state in TERMINAL_RUN_STATES:
                return True
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.25, remaining))

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
        now = utc_now()
        artifact = ArtifactView(
            artifact_id=artifact_id or new_public_id("artifact"),
            version=1,
            trip_id=trip_id,
            tenant_id=principal.tenant_id,
            artifact_type=artifact_type,
            schema_version=schema_version,
            status=status,
            content=content,
            created_by=principal.user_id,
            created_at=now,
            parent_version=parent_version,
        )
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            if execution_lease is not None:
                run = await self._get_run_tx(
                    connection,
                    principal,
                    execution_lease.run_id,
                    lock=True,
                )
                await self._assert_execution_lease_tx(
                    connection,
                    run,
                    execution_lease,
                    trip_id=trip_id,
                )
            await self._get_trip_tx(connection, principal, trip_id, write=True)
            await connection.execute(
                insert(artifacts_table).values(
                    artifact_id=artifact.artifact_id,
                    trip_id=artifact.trip_id,
                    tenant_id=artifact.tenant_id,
                    artifact_type=artifact.artifact_type,
                    created_by=artifact.created_by,
                    created_at=artifact.created_at,
                )
            )
            await connection.execute(
                insert(artifact_versions_table).values(
                    artifact_id=artifact.artifact_id,
                    tenant_id=artifact.tenant_id,
                    version=artifact.version,
                    schema_version=artifact.schema_version,
                    status=artifact.status.value,
                    content=artifact.content,
                    parent_version=artifact.parent_version,
                    created_at=artifact.created_at,
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=artifact.tenant_id,
                aggregate_type="artifact",
                aggregate_id=artifact.artifact_id,
                event_type="artifact.created",
                payload={
                    "artifact_id": artifact.artifact_id,
                    "version": artifact.version,
                    "trip_id": trip_id,
                    "status": artifact.status.value,
                },
            )
        return artifact

    async def list_artifacts(self, principal: Principal, trip_id: str) -> list[ArtifactView]:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            await self._get_trip_tx(connection, principal, trip_id)
            rows = (
                await connection.execute(
                    select(
                        artifacts_table.c.artifact_id,
                        artifact_versions_table.c.version,
                        artifacts_table.c.trip_id,
                        artifacts_table.c.tenant_id,
                        artifacts_table.c.artifact_type,
                        artifact_versions_table.c.schema_version,
                        artifact_versions_table.c.status,
                        artifact_versions_table.c.content,
                        artifacts_table.c.created_by,
                        artifact_versions_table.c.created_at,
                        artifact_versions_table.c.parent_version,
                    )
                    .select_from(
                        artifacts_table.join(
                            artifact_versions_table,
                            artifacts_table.c.artifact_id == artifact_versions_table.c.artifact_id,
                        )
                    )
                    .where(
                        artifacts_table.c.tenant_id == principal.tenant_id,
                        artifacts_table.c.trip_id == trip_id,
                    )
                    .order_by(
                        artifact_versions_table.c.created_at.desc(),
                        artifacts_table.c.artifact_id.desc(),
                    )
                )
            ).mappings().all()
        return [self._artifact_from_row(row) for row in rows]

    async def get_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        *,
        version: int | None = None,
    ) -> ArtifactView:
        async with self.engine.connect() as connection:
            await self._scope_tenant(connection, principal)
            return await self._get_artifact_tx(
                connection,
                principal,
                artifact_id,
                version=version,
            )

    async def patch_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactPatchRequest,
    ) -> ArtifactView:
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)
            current = await self._get_artifact_tx(
                connection,
                principal,
                artifact_id,
                write=True,
                lock=True,
            )
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
            await connection.execute(
                insert(artifact_versions_table).values(
                    artifact_id=updated.artifact_id,
                    tenant_id=updated.tenant_id,
                    version=updated.version,
                    schema_version=updated.schema_version,
                    status=updated.status.value,
                    content=updated.content,
                    parent_version=updated.parent_version,
                    created_at=updated.created_at,
                )
            )
            await self._insert_outbox(
                connection,
                tenant_id=updated.tenant_id,
                aggregate_type="artifact",
                aggregate_id=updated.artifact_id,
                event_type="artifact.version_created",
                payload={
                    "artifact_id": updated.artifact_id,
                    "version": updated.version,
                    "parent_version": updated.parent_version,
                    "trip_id": updated.trip_id,
                    "status": updated.status.value,
                },
            )
            return updated

    async def command_artifact(
        self,
        principal: Principal,
        artifact_id: str,
        request: ArtifactCommandRequest,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotentArtifactResult:
        fingerprint = self._artifact_idempotency_fingerprint(
            principal,
            artifact_id,
            idempotency_key,
        )
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, principal)

            # Authorize every replay against current membership. The transaction
            # advisory lock makes same-key requests deterministic across workers;
            # the outbox record is the durable replay journal without misusing
            # the Run-only idempotency table's non-null response_run_id FK.
            authorized = await self._get_artifact_tx(
                connection,
                principal,
                artifact_id,
                write=True,
            )
            ensure_artifact_mutable(authorized)
            await connection.execute(
                select(func.pg_advisory_xact_lock(self._advisory_lock_id(fingerprint)))
            )
            replay_payload = (
                await connection.execute(
                    select(outbox_events_table.c.payload)
                    .where(
                        outbox_events_table.c.tenant_id == principal.tenant_id,
                        outbox_events_table.c.aggregate_type == "artifact",
                        outbox_events_table.c.aggregate_id == artifact_id,
                        outbox_events_table.c.payload[
                            "idempotency_fingerprint"
                        ].as_string()
                        == fingerprint,
                    )
                    .order_by(outbox_events_table.c.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if replay_payload is not None:
                if replay_payload.get("request_hash") != request_hash:
                    raise IdempotencyConflict("idempotency key reused with different request")
                replayed = await self._get_artifact_tx(
                    connection,
                    principal,
                    artifact_id,
                    version=int(replay_payload["response_version"]),
                    write=True,
                )
                response = replayed.model_copy(
                    update={"status": ArtifactStatus(replay_payload["response_status"])}
                )
                return IdempotentArtifactResult(artifact=response, replayed=True)

            current = await self._get_artifact_tx(
                connection,
                principal,
                artifact_id,
                write=True,
                lock=True,
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

            trip = await self._get_trip_tx(
                connection,
                principal,
                current.trip_id,
                write=True,
                lock=True,
            )
            now = utc_now()
            if target == ArtifactStatus.PUBLISHED:
                trip_artifacts = select(artifacts_table.c.artifact_id).where(
                    artifacts_table.c.tenant_id == principal.tenant_id,
                    artifacts_table.c.trip_id == current.trip_id,
                )
                await connection.execute(
                    update(artifact_versions_table)
                    .where(
                        artifact_versions_table.c.artifact_id.in_(trip_artifacts),
                        artifact_versions_table.c.status == ArtifactStatus.PUBLISHED.value,
                        ~and_(
                            artifact_versions_table.c.artifact_id == current.artifact_id,
                            artifact_versions_table.c.version == current.version,
                        ),
                    )
                    .values(status=ArtifactStatus.SUPERSEDED.value)
                )

            changed = await connection.execute(
                update(artifact_versions_table)
                .where(
                    artifact_versions_table.c.artifact_id == current.artifact_id,
                    artifact_versions_table.c.version == current.version,
                    artifact_versions_table.c.status == required.value,
                )
                .values(status=target.value)
            )
            if not changed.rowcount:
                raise VersionConflict(current.version)

            if target == ArtifactStatus.PUBLISHED:
                updated_trip = await connection.execute(
                    update(trips_table)
                    .where(
                        trips_table.c.trip_id == trip.trip_id,
                        trips_table.c.tenant_id == principal.tenant_id,
                        trips_table.c.version == trip.version,
                    )
                    .values(
                        current_artifact_id=current.artifact_id,
                        current_artifact_version=current.version,
                        version=trip.version + 1,
                        updated_at=now,
                    )
                )
                if not updated_trip.rowcount:
                    raise VersionConflict(trip.version)
            elif target == ArtifactStatus.REVOKED and (
                trip.current_artifact_id == current.artifact_id
                and trip.current_artifact_version == current.version
            ):
                updated_trip = await connection.execute(
                    update(trips_table)
                    .where(
                        trips_table.c.trip_id == trip.trip_id,
                        trips_table.c.tenant_id == principal.tenant_id,
                        trips_table.c.version == trip.version,
                    )
                    .values(
                        current_artifact_id=None,
                        current_artifact_version=None,
                        version=trip.version + 1,
                        updated_at=now,
                    )
                )
                if not updated_trip.rowcount:
                    raise VersionConflict(trip.version)

            response = current.model_copy(update={"status": target})
            event_type = {
                ArtifactStatus.SELECTED: "artifact.selected",
                ArtifactStatus.PUBLISHED: "artifact.published",
                ArtifactStatus.REVOKED: "artifact.revoked",
            }[target]
            await self._insert_outbox(
                connection,
                tenant_id=current.tenant_id,
                aggregate_type="artifact",
                aggregate_id=current.artifact_id,
                event_type=event_type,
                payload={
                    "artifact_id": current.artifact_id,
                    "version": current.version,
                    "trip_id": current.trip_id,
                    "previous_status": current.status.value,
                    "status": target.value,
                    "command": request.type,
                    "idempotency_fingerprint": fingerprint,
                    "request_hash": request_hash,
                    "response_version": response.version,
                    "response_status": response.status.value,
                },
            )
            return IdempotentArtifactResult(artifact=response, replayed=False)

    async def close(self) -> None:
        """Dispose pooled connections during application shutdown."""

        await self.engine.dispose()
