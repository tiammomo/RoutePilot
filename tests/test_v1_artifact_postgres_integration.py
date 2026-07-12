"""Opt-in real PostgreSQL parity test for the V1 Artifact workflow."""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactCommandRequest,
    ArtifactPatchRequest,
    ArtifactStatus,
    Principal,
    TripCreateRequest,
)
from backend.moyuan_web.v1.postgres_store import PostgresPlatformStore
from backend.moyuan_web.v1.store import (
    IdempotencyConflict,
    VersionConflict,
    canonical_request_hash,
)
from tests.contract.samples import build_valid_contracts


def snapshot_content(artifact_id: str, version: int, *, reason: str) -> dict[str, Any]:
    payload = deepcopy(build_valid_contracts()["TripSnapshot@1"])
    payload.update(
        artifact_id=artifact_id,
        version=version,
        reason=reason,
    )
    return payload


@pytest.mark.asyncio
async def test_postgres_artifact_version_command_and_pointer_parity() -> None:
    dsn = os.getenv("ROUTEPILOT_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("set ROUTEPILOT_TEST_POSTGRES_DSN to run PostgreSQL parity")

    store = PostgresPlatformStore.from_database_url(dsn)
    principal = Principal(tenant_id="tenant-artifact-pg", user_id="owner-artifact-pg")
    try:
        trip = await store.create_trip(principal, TripCreateRequest(title="PG Artifact"))
        first_artifact_id = "pg_snapshot_first_001"
        first = await store.create_artifact(
            principal,
            trip_id=trip.trip_id,
            artifact_id=first_artifact_id,
            artifact_type="TripSnapshot",
            schema_version=1,
            content=snapshot_content(
                first_artifact_id,
                1,
                reason="PostgreSQL first snapshot.",
            ),
            status=ArtifactStatus.VALIDATED,
        )
        second_artifact_id = "pg_snapshot_second_001"
        second = await store.create_artifact(
            principal,
            trip_id=trip.trip_id,
            artifact_id=second_artifact_id,
            artifact_type="TripSnapshot",
            schema_version=1,
            content=snapshot_content(
                second_artifact_id,
                1,
                reason="PostgreSQL second snapshot.",
            ),
            status=ArtifactStatus.VALIDATED,
        )

        first_command = ArtifactCommandRequest(
            type="artifact.publish",
            base_version=1,
        )
        await store.command_artifact(
            principal,
            first.artifact_id,
            first_command,
            idempotency_key="pg-publish-first-0001",
            request_hash=canonical_request_hash(
                {
                    "artifact_id": first.artifact_id,
                    "command": first_command.model_dump(mode="json"),
                }
            ),
        )
        second_command = ArtifactCommandRequest(
            type="artifact.publish",
            base_version=1,
        )
        second_hash = canonical_request_hash(
            {
                "artifact_id": second.artifact_id,
                "command": second_command.model_dump(mode="json"),
            }
        )
        published = await store.command_artifact(
            principal,
            second.artifact_id,
            second_command,
            idempotency_key="test-only-idempotency-pg-publish-second-0001",
            request_hash=second_hash,
        )
        assert published.artifact.status == ArtifactStatus.PUBLISHED
        assert (
            await store.get_artifact(principal, first.artifact_id, version=1)
        ).status == ArtifactStatus.SUPERSEDED
        pointed = await store.get_trip(principal, trip.trip_id)
        assert pointed.current_artifact_id == second.artifact_id

        revoke = ArtifactCommandRequest(type="artifact.revoke", base_version=1)
        await store.command_artifact(
            principal,
            second.artifact_id,
            revoke,
            idempotency_key="test-only-idempotency-pg-revoke-second-0001",
            request_hash=canonical_request_hash(
                {
                    "artifact_id": second.artifact_id,
                    "command": revoke.model_dump(mode="json"),
                }
            ),
        )
        replay = await store.command_artifact(
            principal,
            second.artifact_id,
            second_command,
            idempotency_key="test-only-idempotency-pg-publish-second-0001",
            request_hash=second_hash,
        )
        assert replay.replayed is True
        assert replay.artifact.status == ArtifactStatus.PUBLISHED
        assert (await store.get_artifact(principal, second.artifact_id)).status == ArtifactStatus.REVOKED
        assert (await store.get_trip(principal, trip.trip_id)).current_artifact_id is None

        with pytest.raises(IdempotencyConflict):
            await store.command_artifact(
                principal,
                second.artifact_id,
                revoke,
                idempotency_key="test-only-idempotency-pg-publish-second-0001",
                request_hash=canonical_request_hash(
                    {
                        "artifact_id": second.artifact_id,
                        "command": revoke.model_dump(mode="json"),
                    }
                ),
            )

        patched = await store.patch_artifact(
            principal,
            second.artifact_id,
            ArtifactPatchRequest(
                base_version=1,
                content=snapshot_content(
                    second_artifact_id,
                    2,
                    reason="PostgreSQL versioned snapshot edit.",
                ),
            ),
        )
        assert patched.version == 2
        assert patched.parent_version == 1
        assert patched.status == ArtifactStatus.CANDIDATE
        assert (
            await store.get_artifact(principal, second.artifact_id, version=1)
        ).content["reason"] == "PostgreSQL second snapshot."
        with pytest.raises(VersionConflict) as conflict:
            await store.patch_artifact(
                principal,
                second.artifact_id,
                ArtifactPatchRequest(
                    base_version=1,
                    content=snapshot_content(
                        second_artifact_id,
                        2,
                        reason="Stale PostgreSQL snapshot edit.",
                    ),
                ),
            )
        assert conflict.value.current_version == 2
    finally:
        await store.close()
