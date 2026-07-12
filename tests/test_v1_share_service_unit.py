"""Capability, projection, rotation, revocation, and rate-limit tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactCommandRequest,
    ArtifactStatus,
    Principal,
    TripCreateRequest,
)
from backend.moyuan_web.v1.share_models import ShareCreateRequest, ShareStatus
from backend.moyuan_web.v1.share_service import (
    ShareCapabilityInvalid,
    ShareRateLimited,
    ShareService,
)
from backend.moyuan_web.v1.store import InMemoryPlatformStore, canonical_request_hash
from tests.contract.samples import build_valid_contracts


async def published_snapshot():
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-share", user_id="owner-share")
    trip = await store.create_trip(principal, TripCreateRequest(title="可分享行程"))
    content = deepcopy(build_valid_contracts()["TripSnapshot@1"])
    artifact_id = "snapshot_share_001"
    content["artifact_id"] = artifact_id
    content["trip_id"] = trip.trip_id
    artifact = await store.create_artifact(
        principal,
        trip_id=trip.trip_id,
        artifact_id=artifact_id,
        artifact_type="TripSnapshot",
        schema_version=1,
        content=content,
        status=ArtifactStatus.VALIDATED,
    )
    await store.command_artifact(
        principal,
        artifact_id,
        ArtifactCommandRequest(type="artifact.publish", base_version=1),
        idempotency_key="publish-share-snapshot",
        request_hash=canonical_request_hash({"publish": artifact_id}),
    )
    return store, principal, trip, artifact


@pytest.mark.asyncio
async def test_share_secret_is_replayable_without_storage_and_projection_is_minimal() -> None:
    store, principal, trip, artifact = await published_snapshot()
    service = ShareService(store, pepper="p" * 32)
    request = ShareCreateRequest(
        artifact_id=artifact.artifact_id,
        artifact_version=artifact.version,
    )
    created = await service.create(
        principal,
        trip.trip_id,
        request,
        idempotency_key="create-share-001",
    )
    replayed = await service.create(
        principal,
        trip.trip_id,
        request,
        idempotency_key="create-share-001",
    )
    assert created.capability_secret == replayed.capability_secret
    assert replayed.replayed is True
    assert created.capability_secret and len(created.capability_secret) >= 43

    exchanged = await service.exchange(created.share.public_id, created.capability_secret)
    public = await service.public_snapshot(
        created.share.public_id,
        exchanged.session_token,
    )
    serialized = public.model_dump_json().lower()
    assert public.snapshot.artifact_type == "ShareSnapshot"
    assert "travelers" not in serialized
    assert "budget" not in serialized
    assert "owner-share" not in serialized


@pytest.mark.asyncio
async def test_rotation_and_revocation_immediately_fence_old_capabilities_and_sessions() -> None:
    store, principal, trip, artifact = await published_snapshot()
    service = ShareService(store, pepper="q" * 32)
    created = await service.create(
        principal,
        trip.trip_id,
        ShareCreateRequest(
            artifact_id=artifact.artifact_id,
            artifact_version=artifact.version,
        ),
        idempotency_key="create-share-rotate",
    )
    assert created.capability_secret
    old_session = await service.exchange(created.share.public_id, created.capability_secret)
    rotated = await service.rotate(
        principal,
        created.share.share_id,
        expected_version=created.share.version,
        idempotency_key="rotate-share-001",
    )
    assert rotated.capability_secret
    with pytest.raises(ShareCapabilityInvalid):
        await service.exchange(created.share.public_id, created.capability_secret)
    with pytest.raises(ShareCapabilityInvalid):
        await service.public_snapshot(created.share.public_id, old_session.session_token)

    new_session = await service.exchange(created.share.public_id, rotated.capability_secret)
    revoked = await service.revoke(
        principal,
        created.share.share_id,
        expected_version=rotated.share.version,
        idempotency_key="revoke-share-001",
    )
    assert revoked.share.status == ShareStatus.REVOKED
    with pytest.raises(ShareCapabilityInvalid):
        await service.public_snapshot(created.share.public_id, new_session.session_token)


@pytest.mark.asyncio
async def test_capability_failures_are_bounded_by_a_persisted_style_rate_limit() -> None:
    store, principal, trip, artifact = await published_snapshot()
    service = ShareService(store, pepper="r" * 32)
    created = await service.create(
        principal,
        trip.trip_id,
        ShareCreateRequest(
            artifact_id=artifact.artifact_id,
            artifact_version=artifact.version,
        ),
        idempotency_key="create-share-rate-limit",
    )
    for _ in range(4):
        with pytest.raises(ShareCapabilityInvalid):
            await service.exchange(created.share.public_id, "x" * 43)
    with pytest.raises(ShareRateLimited) as blocked:
        await service.exchange(created.share.public_id, "x" * 43)
    assert blocked.value.retry_after_seconds >= 899
