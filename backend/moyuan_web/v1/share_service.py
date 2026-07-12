"""Capability-secured immutable Trip sharing for RoutePilot V1."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from routepilot_contracts.artifacts import (
    PublicGeoPoint,
    PublicPlace,
    ShareDay,
    ShareSnapshot,
    ShareTimeBlock,
    ShareTransitSummary,
    TripSnapshot,
)
from routepilot_contracts.common import ActorRef, ArtifactRef, ArtifactType
from routepilot_contracts.validation import validate_contract
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .models import ArtifactStatus, Principal, new_public_id, utc_now
from .share_models import (
    PublicShareSnapshotResponse,
    ShareCreateRequest,
    ShareExchangeResponse,
    ShareListResponse,
    ShareMutationResponse,
    ShareStatus,
    ShareView,
)
from .sql_tables import (
    artifact_versions_table,
    artifacts_table,
    share_idempotency_keys_table,
    share_public_lookup_table,
    share_sessions_table,
    share_snapshots_table,
    shares_table,
    trips_table,
)
from .store import PlatformStore, canonical_request_hash


class ShareError(Exception):
    """Base public-sharing failure."""


class ShareNotFound(ShareError):
    """Share or source snapshot is not visible to the caller."""


class ShareConflict(ShareError):
    """A stale or invalid share transition was rejected."""

    def __init__(self, message: str, *, current_version: int | None = None):
        super().__init__(message)
        self.current_version = current_version


class ShareCapabilityInvalid(ShareError):
    """Capability or short-lived share session is invalid."""


class ShareRateLimited(ShareError):
    """Capability exchange is temporarily blocked."""

    def __init__(self, retry_after_seconds: int):
        super().__init__("share exchange is temporarily blocked")
        self.retry_after_seconds = max(1, retry_after_seconds)


@dataclass(slots=True)
class _MemoryShare:
    view: ShareView
    secret_hash: str


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _public_place(place: Any) -> PublicPlace:
    point = place.location
    return PublicPlace(
        display_name=place.display_name,
        locality=(place.address or place.display_name)[:256],
        country_code=place.country_code,
        approximate_location=PublicGeoPoint(
            latitude=Decimal(str(round(float(point.latitude), 2))),
            longitude=Decimal(str(round(float(point.longitude), 2))),
            coordinate_system=point.coordinate_system.value,
            accuracy_meters=2_000,
        ),
    )


def project_share_snapshot(source: TripSnapshot, *, public_id: str) -> ShareSnapshot:
    """Create the only public projection; omit travelers, exact budget and private notes."""

    citations = list(source.itinerary.citations)
    citation_by_evidence = {item.evidence_id: item.citation_id for item in citations}
    days: list[ShareDay] = []
    for day in source.itinerary.days:
        blocks: list[ShareTimeBlock] = []
        for block in day.time_blocks:
            transit = block.transit_from_previous
            blocks.append(
                ShareTimeBlock(
                    block_id=block.block_id,
                    title=block.title,
                    category=block.category,
                    time_range=block.time_range,
                    place=_public_place(block.place_ref),
                    transit_from_previous=(
                        ShareTransitSummary(
                            mode=transit.mode,
                            duration_minutes=transit.duration_max_minutes,
                        )
                        if transit is not None
                        else None
                    ),
                    citation_refs=[
                        citation_by_evidence[evidence_id]
                        for evidence_id in block.evidence_refs
                        if evidence_id in citation_by_evidence
                    ],
                )
            )
        days.append(
            ShareDay(
                date=day.date,
                timezone=day.timezone,
                summary=day.day_summary,
                time_blocks=blocks,
            )
        )
    now = utc_now()
    return ShareSnapshot(
        artifact_id=new_public_id("share_snapshot"),
        artifact_type="ShareSnapshot",
        schema_version=1,
        version=1,
        created_at=now,
        created_by=ActorRef(actor_type="service", actor_id="service:share_projector"),
        reason="从已发布 TripSnapshot 生成显式、不可变且最小化的公共投影。",
        public_id=public_id,
        trip_snapshot_ref=ArtifactRef(
            artifact_type=ArtifactType.TRIP_SNAPSHOT,
            artifact_id=source.artifact_id,
            schema_version=1,
            version=source.version,
        ),
        title=source.title,
        destination=_public_place(source.brief.destination),
        date_window=source.brief.date_window,
        days=days,
        citations=citations,
        published_at=now,
    )


class ShareService:
    """One share service with in-memory parity and durable PostgreSQL execution."""

    def __init__(
        self,
        platform_store: PlatformStore,
        *,
        pepper: str | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        environment = os.getenv("ENVIRONMENT", "dev").strip().lower()
        configured = pepper if pepper is not None else os.getenv("ROUTEPILOT_SHARE_PEPPER", "")
        if not configured and environment in {"staging", "preprod", "production", "prod"}:
            raise RuntimeError("ROUTEPILOT_SHARE_PEPPER is required in secure deployments")
        self._pepper = (configured or _base64url(secrets.token_bytes(32))).encode("utf-8")
        if len(self._pepper) < 32:
            raise RuntimeError("ROUTEPILOT_SHARE_PEPPER must contain at least 32 bytes")
        self.platform_store = platform_store
        self.engine = engine or getattr(platform_store, "engine", None)
        self._lock = asyncio.Lock()
        self._shares: dict[str, _MemoryShare] = {}
        self._public_ids: dict[str, str] = {}
        self._snapshots: dict[str, ShareSnapshot] = {}
        self._sessions: dict[str, tuple[str, int, Any]] = {}
        self._idempotency: dict[tuple[str, str, str, str], tuple[str, str, int, int]] = {}
        self._failures: dict[str, tuple[int, Any, Any | None]] = {}

    def _derive_secret(
        self,
        operation: str,
        principal: Principal,
        idempotency_key: str,
        request_hash: str,
        share_id: str,
        epoch: int,
    ) -> str:
        message = (
            f"capability\x1f{operation}\x1f{principal.tenant_id}\x1f{principal.user_id}\x1f"
            f"{idempotency_key}\x1f{request_hash}\x1f{share_id}\x1f{epoch}"
        ).encode("utf-8")
        return _base64url(hmac.new(self._pepper, message, hashlib.sha256).digest())

    def _capability_hash(self, public_id: str, secret: str) -> str:
        return hmac.new(
            self._pepper,
            f"capability-hash\x1f{public_id}\x1f{secret}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _session_hash(self, token: str) -> str:
        return hmac.new(
            self._pepper,
            f"share-session\x1f{token}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _view(row: Any) -> ShareView:
        data = dict(row)
        return ShareView.model_validate(
            {name: data[name] for name in ShareView.model_fields if name in data}
        )

    async def _source(
        self,
        principal: Principal,
        trip_id: str,
        request: ShareCreateRequest,
    ) -> TripSnapshot:
        trip = await self.platform_store.get_trip(principal, trip_id)
        if (
            trip.current_artifact_id != request.artifact_id
            or trip.current_artifact_version != request.artifact_version
        ):
            raise ShareConflict("only the current published TripSnapshot can be shared")
        artifact = await self.platform_store.get_artifact(
            principal,
            request.artifact_id,
            version=request.artifact_version,
        )
        if (
            artifact.trip_id != trip_id
            or artifact.artifact_type != "TripSnapshot"
            or artifact.status != ArtifactStatus.PUBLISHED
        ):
            raise ShareConflict("only a published TripSnapshot can be shared")
        parsed = validate_contract("TripSnapshot@1", artifact.content)
        if not isinstance(parsed, TripSnapshot):
            raise ShareConflict("source Artifact is not a TripSnapshot")
        return parsed

    @staticmethod
    async def _scope(connection: AsyncConnection, tenant_id: str) -> None:
        await connection.execute(
            select(func.set_config("routepilot.tenant_id", tenant_id, True))
        )

    async def create(
        self,
        principal: Principal,
        trip_id: str,
        request: ShareCreateRequest,
        *,
        idempotency_key: str,
    ) -> ShareMutationResponse:
        source = await self._source(principal, trip_id, request)
        request_hash = canonical_request_hash(
            {"trip_id": trip_id, "request": request.model_dump(mode="json")}
        )
        if self.engine is None:
            return await self._create_memory(
                principal, trip_id, source, request_hash, idempotency_key
            )
        return await self._create_postgres(
            principal, trip_id, source, request_hash, idempotency_key
        )

    async def _create_memory(
        self,
        principal: Principal,
        trip_id: str,
        source: TripSnapshot,
        request_hash: str,
        idempotency_key: str,
    ) -> ShareMutationResponse:
        scope = (principal.tenant_id, principal.user_id, "share.create", idempotency_key)
        async with self._lock:
            existing = self._idempotency.get(scope)
            if existing is not None:
                old_hash, share_id, version, epoch = existing
                if old_hash != request_hash:
                    raise ShareConflict("idempotency key reused with another request")
                stored = self._shares[share_id]
                secret = self._derive_secret(
                    "share.create", principal, idempotency_key, request_hash, share_id, epoch
                )
                return ShareMutationResponse(
                    share=stored.view, capability_secret=secret, replayed=True
                )
            now = utc_now()
            share_id = new_public_id("share")
            public_id = new_public_id("public")
            secret = self._derive_secret(
                "share.create", principal, idempotency_key, request_hash, share_id, 1
            )
            view = ShareView(
                share_id=share_id,
                public_id=public_id,
                trip_id=trip_id,
                source_artifact_id=source.artifact_id,
                source_artifact_version=source.version,
                status=ShareStatus.ACTIVE,
                version=1,
                capability_epoch=1,
                created_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
            self._shares[share_id] = _MemoryShare(
                view=view,
                secret_hash=self._capability_hash(public_id, secret),
            )
            self._public_ids[public_id] = share_id
            self._snapshots[share_id] = project_share_snapshot(source, public_id=public_id)
            self._idempotency[scope] = (request_hash, share_id, 1, 1)
            return ShareMutationResponse(share=view, capability_secret=secret)

    async def _create_postgres(
        self,
        principal: Principal,
        trip_id: str,
        source: TripSnapshot,
        request_hash: str,
        idempotency_key: str,
    ) -> ShareMutationResponse:
        assert self.engine is not None
        share_id = new_public_id("share")
        public_id = new_public_id("public")
        secret = self._derive_secret(
            "share.create", principal, idempotency_key, request_hash, share_id, 1
        )
        now = utc_now()
        replayed = False
        async with self.engine.begin() as connection:
            await self._scope(connection, principal.tenant_id)
            reserved = (
                await connection.execute(
                    pg_insert(share_idempotency_keys_table)
                    .values(
                        tenant_id=principal.tenant_id,
                        actor_id=principal.user_id,
                        operation="share.create",
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_share_id=share_id,
                        response_version=1,
                        response_epoch=1,
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            "tenant_id", "actor_id", "operation", "idempotency_key"
                        ]
                    )
                    .returning(share_idempotency_keys_table.c.response_share_id)
                )
            ).scalar_one_or_none()
            if reserved is None:
                idem = (
                    await connection.execute(
                        select(share_idempotency_keys_table).where(
                            share_idempotency_keys_table.c.tenant_id == principal.tenant_id,
                            share_idempotency_keys_table.c.actor_id == principal.user_id,
                            share_idempotency_keys_table.c.operation == "share.create",
                            share_idempotency_keys_table.c.idempotency_key == idempotency_key,
                        )
                    )
                ).mappings().one()
                if idem["request_hash"] != request_hash:
                    raise ShareConflict("idempotency key reused with another request")
                share_id = str(idem["response_share_id"])
                row = (
                    await connection.execute(
                        select(shares_table).where(shares_table.c.share_id == share_id)
                    )
                ).mappings().one()
                view = self._view(row)
                secret = self._derive_secret(
                    "share.create",
                    principal,
                    idempotency_key,
                    request_hash,
                    share_id,
                    int(idem["response_epoch"]),
                )
                replayed = True
            else:
                current = (
                    await connection.execute(
                        select(
                            trips_table.c.current_artifact_id,
                            trips_table.c.current_artifact_version,
                            artifact_versions_table.c.status,
                        )
                        .select_from(
                            trips_table.join(
                                artifacts_table,
                                artifacts_table.c.trip_id == trips_table.c.trip_id,
                            ).join(
                                artifact_versions_table,
                                artifact_versions_table.c.artifact_id
                                == artifacts_table.c.artifact_id,
                            )
                        )
                        .where(
                            trips_table.c.trip_id == trip_id,
                            trips_table.c.tenant_id == principal.tenant_id,
                            artifacts_table.c.artifact_id == source.artifact_id,
                            artifact_versions_table.c.version == source.version,
                        )
                        .with_for_update()
                    )
                ).mappings().one_or_none()
                if (
                    current is None
                    or current["current_artifact_id"] != source.artifact_id
                    or current["current_artifact_version"] != source.version
                    or current["status"] != ArtifactStatus.PUBLISHED.value
                ):
                    raise ShareConflict("source snapshot changed before share creation")
                view = ShareView(
                    share_id=share_id,
                    public_id=public_id,
                    trip_id=trip_id,
                    source_artifact_id=source.artifact_id,
                    source_artifact_version=source.version,
                    status=ShareStatus.ACTIVE,
                    version=1,
                    capability_epoch=1,
                    created_by=principal.user_id,
                    created_at=now,
                    updated_at=now,
                )
                await connection.execute(
                    insert(shares_table).values(
                        tenant_id=principal.tenant_id,
                        capability_secret_hash=self._capability_hash(public_id, secret),
                        failed_attempts=0,
                        **view.model_dump(mode="python"),
                    )
                )
                await connection.execute(
                    insert(share_public_lookup_table).values(
                        public_id=public_id,
                        tenant_id=principal.tenant_id,
                        share_id=share_id,
                    )
                )
                snapshot = project_share_snapshot(source, public_id=public_id)
                await connection.execute(
                    insert(share_snapshots_table).values(
                        snapshot_id=snapshot.artifact_id,
                        tenant_id=principal.tenant_id,
                        share_id=share_id,
                        snapshot=snapshot.model_dump(mode="json"),
                        created_at=now,
                    )
                )
        return ShareMutationResponse(
            share=view,
            capability_secret=secret,
            replayed=replayed,
        )

    async def list(self, principal: Principal, trip_id: str) -> ShareListResponse:
        await self.platform_store.get_trip(principal, trip_id)
        if self.engine is None:
            async with self._lock:
                items = [
                    item.view
                    for item in self._shares.values()
                    if item.view.trip_id == trip_id
                ]
            return ShareListResponse(items=sorted(items, key=lambda item: item.created_at))
        assert self.engine is not None
        async with self.engine.connect() as connection:
            await self._scope(connection, principal.tenant_id)
            rows = (
                await connection.execute(
                    select(shares_table)
                    .where(
                        shares_table.c.tenant_id == principal.tenant_id,
                        shares_table.c.trip_id == trip_id,
                    )
                    .order_by(shares_table.c.created_at)
                )
            ).mappings().all()
        return ShareListResponse(items=[self._view(row) for row in rows])

    async def rotate(
        self,
        principal: Principal,
        share_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> ShareMutationResponse:
        request_hash = canonical_request_hash(
            {"share_id": share_id, "expected_version": expected_version, "operation": "rotate"}
        )
        if self.engine is None:
            return await self._rotate_memory(
                principal, share_id, expected_version, idempotency_key, request_hash
            )
        return await self._rotate_postgres(
            principal, share_id, expected_version, idempotency_key, request_hash
        )

    async def _rotate_memory(
        self,
        principal: Principal,
        share_id: str,
        expected_version: int,
        idempotency_key: str,
        request_hash: str,
    ) -> ShareMutationResponse:
        scope = (principal.tenant_id, principal.user_id, f"share.rotate:{share_id}", idempotency_key)
        async with self._lock:
            replay = self._idempotency.get(scope)
            if replay is not None:
                old_hash, replay_share_id, version, epoch = replay
                if old_hash != request_hash or replay_share_id != share_id:
                    raise ShareConflict("idempotency key reused with another request")
                stored = self._shares.get(share_id)
                if stored is None:
                    raise ShareNotFound("share not found")
                secret = (
                    self._derive_secret(
                        "share.rotate", principal, idempotency_key, request_hash, share_id, epoch
                    )
                    if stored.view.version == version and stored.view.capability_epoch == epoch
                    else None
                )
                return ShareMutationResponse(share=stored.view, capability_secret=secret, replayed=True)
            stored = self._shares.get(share_id)
            if stored is None or stored.view.created_by != principal.user_id:
                raise ShareNotFound("share not found")
            if stored.view.status != ShareStatus.ACTIVE or stored.view.version != expected_version:
                raise ShareConflict("share changed", current_version=stored.view.version)
            epoch = stored.view.capability_epoch + 1
            version = stored.view.version + 1
            secret = self._derive_secret(
                "share.rotate", principal, idempotency_key, request_hash, share_id, epoch
            )
            updated = stored.view.model_copy(
                update={"version": version, "capability_epoch": epoch, "updated_at": utc_now()}
            )
            self._shares[share_id] = _MemoryShare(
                view=updated,
                secret_hash=self._capability_hash(updated.public_id, secret),
            )
            self._sessions = {
                key: value for key, value in self._sessions.items() if value[0] != share_id
            }
            self._idempotency[scope] = (request_hash, share_id, version, epoch)
            return ShareMutationResponse(share=updated, capability_secret=secret)

    async def _rotate_postgres(
        self,
        principal: Principal,
        share_id: str,
        expected_version: int,
        idempotency_key: str,
        request_hash: str,
    ) -> ShareMutationResponse:
        assert self.engine is not None
        operation = f"share.rotate:{share_id}"
        now = utc_now()
        async with self.engine.begin() as connection:
            await self._scope(connection, principal.tenant_id)
            current = (
                await connection.execute(
                    select(shares_table)
                    .where(
                        shares_table.c.share_id == share_id,
                        shares_table.c.tenant_id == principal.tenant_id,
                        shares_table.c.created_by == principal.user_id,
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if current is None:
                raise ShareNotFound("share not found")
            pg_replay = (
                await connection.execute(
                    select(share_idempotency_keys_table).where(
                        share_idempotency_keys_table.c.tenant_id == principal.tenant_id,
                        share_idempotency_keys_table.c.actor_id == principal.user_id,
                        share_idempotency_keys_table.c.operation == operation,
                        share_idempotency_keys_table.c.idempotency_key == idempotency_key,
                    )
                )
            ).mappings().one_or_none()
            if pg_replay is not None:
                if pg_replay["request_hash"] != request_hash:
                    raise ShareConflict("idempotency key reused with another request")
                view = self._view(current)
                secret = (
                    self._derive_secret(
                        "share.rotate",
                        principal,
                        idempotency_key,
                        request_hash,
                        share_id,
                        int(pg_replay["response_epoch"]),
                    )
                    if view.version == pg_replay["response_version"]
                    and view.capability_epoch == pg_replay["response_epoch"]
                    else None
                )
                return ShareMutationResponse(share=view, capability_secret=secret, replayed=True)
            if current["status"] != ShareStatus.ACTIVE.value or current["version"] != expected_version:
                raise ShareConflict("share changed", current_version=int(current["version"]))
            epoch = int(current["capability_epoch"]) + 1
            version = int(current["version"]) + 1
            secret = self._derive_secret(
                "share.rotate", principal, idempotency_key, request_hash, share_id, epoch
            )
            row = (
                await connection.execute(
                    update(shares_table)
                    .where(
                        shares_table.c.share_id == share_id,
                        shares_table.c.version == expected_version,
                    )
                    .values(
                        version=version,
                        capability_epoch=epoch,
                        capability_secret_hash=self._capability_hash(current["public_id"], secret),
                        failed_attempts=0,
                        failure_window_started_at=None,
                        blocked_until=None,
                        updated_at=now,
                    )
                    .returning(shares_table)
                )
            ).mappings().one()
            await connection.execute(
                delete(share_sessions_table).where(share_sessions_table.c.share_id == share_id)
            )
            await connection.execute(
                insert(share_idempotency_keys_table).values(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.user_id,
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_share_id=share_id,
                    response_version=version,
                    response_epoch=epoch,
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            return ShareMutationResponse(share=self._view(row), capability_secret=secret)

    async def revoke(
        self,
        principal: Principal,
        share_id: str,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> ShareMutationResponse:
        request_hash = canonical_request_hash(
            {"share_id": share_id, "expected_version": expected_version, "operation": "revoke"}
        )
        operation = f"share.revoke:{share_id}"
        if self.engine is None:
            scope = (principal.tenant_id, principal.user_id, operation, idempotency_key)
            async with self._lock:
                replay = self._idempotency.get(scope)
                if replay is not None:
                    if replay[0] != request_hash:
                        raise ShareConflict("idempotency key reused with another request")
                    stored = self._shares.get(share_id)
                    if stored is None:
                        raise ShareNotFound("share not found")
                    return ShareMutationResponse(share=stored.view, replayed=True)
                stored = self._shares.get(share_id)
                if stored is None or stored.view.created_by != principal.user_id:
                    raise ShareNotFound("share not found")
                if stored.view.status != ShareStatus.ACTIVE or stored.view.version != expected_version:
                    raise ShareConflict("share changed", current_version=stored.view.version)
                now = utc_now()
                updated = stored.view.model_copy(
                    update={
                        "status": ShareStatus.REVOKED,
                        "version": stored.view.version + 1,
                        "capability_epoch": stored.view.capability_epoch + 1,
                        "updated_at": now,
                        "revoked_at": now,
                    }
                )
                self._shares[share_id] = _MemoryShare(updated, stored.secret_hash)
                self._sessions = {
                    key: value for key, value in self._sessions.items() if value[0] != share_id
                }
                self._idempotency[scope] = (
                    request_hash, share_id, updated.version, updated.capability_epoch
                )
                return ShareMutationResponse(share=updated)
        assert self.engine is not None
        now = utc_now()
        async with self.engine.begin() as connection:
            await self._scope(connection, principal.tenant_id)
            row = (
                await connection.execute(
                    select(shares_table)
                    .where(
                        shares_table.c.share_id == share_id,
                        shares_table.c.tenant_id == principal.tenant_id,
                        shares_table.c.created_by == principal.user_id,
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise ShareNotFound("share not found")
            pg_replay = (
                await connection.execute(
                    select(share_idempotency_keys_table).where(
                        share_idempotency_keys_table.c.tenant_id == principal.tenant_id,
                        share_idempotency_keys_table.c.actor_id == principal.user_id,
                        share_idempotency_keys_table.c.operation == operation,
                        share_idempotency_keys_table.c.idempotency_key == idempotency_key,
                    )
                )
            ).mappings().one_or_none()
            if pg_replay is not None:
                if pg_replay["request_hash"] != request_hash:
                    raise ShareConflict("idempotency key reused with another request")
                return ShareMutationResponse(share=self._view(row), replayed=True)
            if row["status"] != ShareStatus.ACTIVE.value or row["version"] != expected_version:
                raise ShareConflict("share changed", current_version=int(row["version"]))
            version = int(row["version"]) + 1
            epoch = int(row["capability_epoch"]) + 1
            updated_row = (
                await connection.execute(
                    update(shares_table)
                    .where(
                        shares_table.c.share_id == share_id,
                        shares_table.c.version == expected_version,
                    )
                    .values(
                        status=ShareStatus.REVOKED.value,
                        version=version,
                        capability_epoch=epoch,
                        updated_at=now,
                        revoked_at=now,
                    )
                    .returning(shares_table)
                )
            ).mappings().one()
            await connection.execute(
                delete(share_sessions_table).where(share_sessions_table.c.share_id == share_id)
            )
            await connection.execute(
                insert(share_idempotency_keys_table).values(
                    tenant_id=principal.tenant_id,
                    actor_id=principal.user_id,
                    operation=operation,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_share_id=share_id,
                    response_version=version,
                    response_epoch=epoch,
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            return ShareMutationResponse(share=self._view(updated_row))

    async def _resolve_public_tenant(self, public_id: str) -> str | None:
        assert self.engine is not None
        async with self.engine.connect() as connection:
            return (
                await connection.execute(
                    select(func.routepilot_resolve_share_tenant(public_id))
                )
            ).scalar_one_or_none()

    async def exchange(self, public_id: str, secret: str) -> ShareExchangeResponse:
        now = utc_now()
        if self.engine is None:
            async with self._lock:
                share_id = self._public_ids.get(public_id)
                stored = self._shares.get(share_id or "")
                if stored is None or stored.view.status != ShareStatus.ACTIVE:
                    raise ShareCapabilityInvalid("invalid share capability")
                assert share_id is not None
                attempts, window_start, blocked_until = self._failures.get(
                    share_id, (0, now, None)
                )
                if blocked_until is not None and blocked_until > now:
                    raise ShareRateLimited(int((blocked_until - now).total_seconds()) + 1)
                candidate = self._capability_hash(public_id, secret)
                if not hmac.compare_digest(candidate, stored.secret_hash):
                    if now - window_start > timedelta(minutes=10):
                        attempts, window_start = 0, now
                    attempts += 1
                    blocked_until = now + timedelta(minutes=15) if attempts >= 5 else None
                    self._failures[share_id] = (attempts, window_start, blocked_until)
                    if blocked_until is not None:
                        raise ShareRateLimited(15 * 60)
                    raise ShareCapabilityInvalid("invalid share capability")
                self._failures.pop(share_id, None)
                token = _base64url(secrets.token_bytes(32))
                expires_at = now + timedelta(minutes=15)
                self._sessions[self._session_hash(token)] = (
                    share_id,
                    stored.view.capability_epoch,
                    expires_at,
                )
                return ShareExchangeResponse(session_token=token, expires_at=expires_at)

        tenant_id = await self._resolve_public_tenant(public_id)
        if not tenant_id:
            raise ShareCapabilityInvalid("invalid share capability")
        assert self.engine is not None
        error: ShareError | None = None
        response: ShareExchangeResponse | None = None
        async with self.engine.begin() as connection:
            await self._scope(connection, tenant_id)
            row = (
                await connection.execute(
                    select(shares_table)
                    .where(
                        shares_table.c.tenant_id == tenant_id,
                        shares_table.c.public_id == public_id,
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None or row["status"] != ShareStatus.ACTIVE.value:
                error = ShareCapabilityInvalid("invalid share capability")
            elif row["blocked_until"] is not None and row["blocked_until"] > now:
                error = ShareRateLimited(
                    int((row["blocked_until"] - now).total_seconds()) + 1
                )
            else:
                candidate = self._capability_hash(public_id, secret)
                if not hmac.compare_digest(candidate, str(row["capability_secret_hash"])):
                    window_start = row["failure_window_started_at"]
                    attempts = int(row["failed_attempts"])
                    if window_start is None or now - window_start > timedelta(minutes=10):
                        attempts, window_start = 0, now
                    attempts += 1
                    blocked_until = now + timedelta(minutes=15) if attempts >= 5 else None
                    await connection.execute(
                        update(shares_table)
                        .where(shares_table.c.share_id == row["share_id"])
                        .values(
                            failed_attempts=attempts,
                            failure_window_started_at=window_start,
                            blocked_until=blocked_until,
                        )
                    )
                    error = (
                        ShareRateLimited(15 * 60)
                        if blocked_until is not None
                        else ShareCapabilityInvalid("invalid share capability")
                    )
                else:
                    token = _base64url(secrets.token_bytes(32))
                    expires_at = now + timedelta(minutes=15)
                    await connection.execute(
                        update(shares_table)
                        .where(shares_table.c.share_id == row["share_id"])
                        .values(
                            failed_attempts=0,
                            failure_window_started_at=None,
                            blocked_until=None,
                        )
                    )
                    await connection.execute(
                        insert(share_sessions_table).values(
                            session_hash=self._session_hash(token),
                            tenant_id=tenant_id,
                            share_id=row["share_id"],
                            capability_epoch=row["capability_epoch"],
                            created_at=now,
                            expires_at=expires_at,
                        )
                    )
                    response = ShareExchangeResponse(
                        session_token=token,
                        expires_at=expires_at,
                    )
        if error is not None:
            raise error
        if response is None:  # pragma: no cover - transaction invariant
            raise ShareCapabilityInvalid("invalid share capability")
        return response

    async def public_snapshot(
        self,
        public_id: str,
        session_token: str,
    ) -> PublicShareSnapshotResponse:
        session_hash = self._session_hash(session_token)
        now = utc_now()
        if self.engine is None:
            async with self._lock:
                session = self._sessions.get(session_hash)
                share_id = self._public_ids.get(public_id)
                stored = self._shares.get(share_id or "")
                if (
                    session is None
                    or stored is None
                    or session[0] != share_id
                    or session[1] != stored.view.capability_epoch
                    or session[2] <= now
                    or stored.view.status != ShareStatus.ACTIVE
                ):
                    raise ShareCapabilityInvalid("invalid share session")
                return PublicShareSnapshotResponse(
                    public_id=public_id,
                    snapshot=self._snapshots[share_id],
                )
        tenant_id = await self._resolve_public_tenant(public_id)
        if not tenant_id:
            raise ShareCapabilityInvalid("invalid share session")
        assert self.engine is not None
        async with self.engine.connect() as connection:
            await self._scope(connection, tenant_id)
            row = (
                await connection.execute(
                    select(
                        shares_table.c.status,
                        shares_table.c.capability_epoch,
                        share_sessions_table.c.expires_at,
                        share_sessions_table.c.capability_epoch.label("session_epoch"),
                        share_snapshots_table.c.snapshot,
                    )
                    .select_from(
                        shares_table.join(
                            share_sessions_table,
                            share_sessions_table.c.share_id == shares_table.c.share_id,
                        ).join(
                            share_snapshots_table,
                            share_snapshots_table.c.share_id == shares_table.c.share_id,
                        )
                    )
                    .where(
                        shares_table.c.tenant_id == tenant_id,
                        shares_table.c.public_id == public_id,
                        share_sessions_table.c.session_hash == session_hash,
                    )
                )
            ).mappings().one_or_none()
        if (
            row is None
            or row["status"] != ShareStatus.ACTIVE.value
            or row["expires_at"] <= now
            or row["session_epoch"] != row["capability_epoch"]
        ):
            raise ShareCapabilityInvalid("invalid share session")
        snapshot = validate_contract("ShareSnapshot@1", row["snapshot"])
        if not isinstance(snapshot, ShareSnapshot):  # pragma: no cover - contract invariant
            raise ShareCapabilityInvalid("invalid share snapshot")
        return PublicShareSnapshotResponse(public_id=public_id, snapshot=snapshot)


__all__ = [
    "ShareCapabilityInvalid",
    "ShareConflict",
    "ShareError",
    "ShareNotFound",
    "ShareRateLimited",
    "ShareService",
    "project_share_snapshot",
]
