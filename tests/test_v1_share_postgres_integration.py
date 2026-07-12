"""Opt-in PostgreSQL/RLS parity for capability-based public sharing."""

from __future__ import annotations

import os
from copy import deepcopy
from uuid import uuid4

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactCommandRequest,
    ArtifactStatus,
    Principal,
    TripCreateRequest,
)
from backend.moyuan_web.v1.postgres_store import PostgresPlatformStore
from backend.moyuan_web.v1.share_models import ShareCreateRequest, ShareStatus
from backend.moyuan_web.v1.share_service import ShareCapabilityInvalid, ShareService
from backend.moyuan_web.v1.store import canonical_request_hash
from tests.contract.samples import build_valid_contracts


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_share_projection_rotation_and_revocation_are_fenced() -> None:
    dsn = os.getenv("ROUTEPILOT_SHARE_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("set ROUTEPILOT_SHARE_TEST_DSN to run PostgreSQL share parity")
    store = PostgresPlatformStore.from_database_url(dsn)
    suffix = uuid4().hex[:12]
    principal = Principal(tenant_id=f"tenant-share-pg-{suffix}", user_id="owner-share-pg")
    service = ShareService(store)
    try:
        trip = await store.create_trip(principal, TripCreateRequest(title="PostgreSQL 安全分享"))
        content = deepcopy(build_valid_contracts()["TripSnapshot@1"])
        content["artifact_id"] = f"snapshot_share_pg_{suffix}"
        content["trip_id"] = trip.trip_id
        artifact = await store.create_artifact(
            principal,
            trip_id=trip.trip_id,
            artifact_id=content["artifact_id"],
            artifact_type="TripSnapshot",
            schema_version=1,
            content=content,
            status=ArtifactStatus.VALIDATED,
        )
        command = ArtifactCommandRequest(type="artifact.publish", base_version=1)
        await store.command_artifact(
            principal,
            artifact.artifact_id,
            command,
            idempotency_key=f"publish-share-pg-{suffix}",
            request_hash=canonical_request_hash(command.model_dump(mode="json")),
        )
        request = ShareCreateRequest(artifact_id=artifact.artifact_id, artifact_version=1)
        created = await service.create(principal, trip.trip_id, request, idempotency_key=f"create-share-pg-{suffix}")
        replayed = await service.create(principal, trip.trip_id, request, idempotency_key=f"create-share-pg-{suffix}")
        assert created.capability_secret == replayed.capability_secret
        assert replayed.replayed is True
        assert created.capability_secret

        old_session = await service.exchange(created.share.public_id, created.capability_secret)
        public = await service.public_snapshot(created.share.public_id, old_session.session_token)
        assert public.snapshot.artifact_type == "ShareSnapshot"
        assert "budget" not in public.model_dump_json().lower()

        rotated = await service.rotate(
            principal,
            created.share.share_id,
            expected_version=created.share.version,
            idempotency_key=f"rotate-share-pg-{suffix}",
        )
        with pytest.raises(ShareCapabilityInvalid):
            await service.public_snapshot(created.share.public_id, old_session.session_token)
        assert rotated.capability_secret
        new_session = await service.exchange(rotated.share.public_id, rotated.capability_secret)
        revoked = await service.revoke(
            principal,
            rotated.share.share_id,
            expected_version=rotated.share.version,
            idempotency_key=f"revoke-share-pg-{suffix}",
        )
        assert revoked.share.status == ShareStatus.REVOKED
        with pytest.raises(ShareCapabilityInvalid):
            await service.public_snapshot(rotated.share.public_id, new_session.session_token)
    finally:
        await store.close()
