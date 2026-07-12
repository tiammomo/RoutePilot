"""Focused V1 Artifact versioning, lifecycle, and authorization tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from pydantic import ValidationError

from backend.moyuan_web.v1.models import (
    ArtifactPatchRequest,
    ArtifactStatus,
    Principal,
    TripCreateRequest,
)
from backend.moyuan_web.v1.routes import router
from backend.moyuan_web.v1.runtime import RunCoordinator, V1Runtime
from backend.moyuan_web.v1.store import InMemoryPlatformStore, VersionConflict
from tests.contract.samples import build_valid_contracts


class UnusedExecutor:
    """Artifact-only tests never dispatch a Product Run."""

    async def execute(self, run: Any, principal: Principal, progress: Any) -> Any:
        raise AssertionError("the Artifact workflow must not dispatch a Product Run")


def build_artifact_app() -> tuple[FastAPI, InMemoryPlatformStore]:
    store = InMemoryPlatformStore()
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.routepilot_v1_runtime = V1Runtime(
        store=store,
        coordinator=RunCoordinator(store, UnusedExecutor()),
    )

    async def authenticate(request: Request) -> Principal:
        return Principal(
            tenant_id=request.headers.get("X-Test-Tenant", "tenant-a"),
            user_id=request.headers.get("X-Test-User", "owner-a"),
        )

    app.state.routepilot_v1_authenticator = authenticate
    return app, store


def owner_principal() -> Principal:
    return Principal(tenant_id="tenant-a", user_id="owner-a")


def contract_content(
    contract_name: str,
    artifact_id: str,
    version: int,
    *,
    reason: str,
) -> dict[str, Any]:
    payload = deepcopy(build_valid_contracts()[f"{contract_name}@1"])
    payload.update(
        artifact_id=artifact_id,
        artifact_type=contract_name,
        schema_version=1,
        version=version,
        reason=reason,
    )
    if contract_name == "ItineraryPlan":
        payload["status"] = "candidate"
    return payload


@pytest.mark.asyncio
async def test_patch_creates_immutable_version_and_enforces_payload_and_cas() -> None:
    app, store = build_artifact_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "版本化行程"})).json()
        artifact_id = "plan_edit_001"
        original_content = contract_content(
            "ItineraryPlan",
            artifact_id,
            1,
            reason="Original immutable plan version.",
        )
        artifact = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_id=artifact_id,
            artifact_type="ItineraryPlan",
            schema_version=1,
            content=original_content,
            status=ArtifactStatus.CANDIDATE,
        )
        next_content = contract_content(
            "ItineraryPlan",
            artifact_id,
            2,
            reason="Editor created the second immutable plan version.",
        )

        patched = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={
                "base_version": 1,
                "content": next_content,
            },
        )
        assert patched.status_code == 200
        assert patched.json()["version"] == 2
        assert patched.json()["parent_version"] == 1
        assert patched.json()["status"] == "candidate"

        original = await client.get(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            params={"version": 1},
        )
        latest = await client.get(f"/api/v1/artifacts/{artifact.artifact_id}")
        assert original.json()["content"]["version"] == 1
        assert original.json()["content"]["reason"] == "Original immutable plan version."
        assert latest.json()["version"] == 2
        assert latest.json()["content"]["artifact_id"] == artifact_id
        assert latest.json()["content"]["artifact_type"] == "ItineraryPlan"
        assert latest.json()["content"]["schema_version"] == 1
        assert latest.json()["content"]["version"] == 2

        stale = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={"base_version": 1, "content": {"days": []}},
        )
        unknown = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={"base_version": 2, "content": {}, "status": "published"},
        )
        oversized = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={"base_version": 2, "content": {"blob": "x" * 1_048_576}},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_version"] == 2
        assert unknown.status_code == 422
        assert oversized.status_code == 422

        with pytest.raises(ValidationError):
            ArtifactPatchRequest(base_version=2, content={"cost": float("nan")})


@pytest.mark.asyncio
async def test_viewer_reads_pinned_versions_but_cannot_edit_or_command() -> None:
    app, store = build_artifact_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "只读边界"})).json()
        await client.put(
            f"/api/v1/trips/{trip['trip_id']}/members/viewer-a",
            json={"role": "viewer"},
        )
        await client.put(
            f"/api/v1/trips/{trip['trip_id']}/members/editor-a",
            json={"role": "editor"},
        )
        artifact_id = "plan_auth_001"
        artifact = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_id=artifact_id,
            artifact_type="ItineraryPlan",
            schema_version=1,
            content=contract_content(
                "ItineraryPlan",
                artifact_id,
                1,
                reason="Authorization fixture version one.",
            ),
            status=ArtifactStatus.CANDIDATE,
        )
        viewer_headers = {"X-Test-User": "viewer-a"}

        read = await client.get(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            headers=viewer_headers,
        )
        edited = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={"base_version": 1, "content": {"days": [1]}},
            headers=viewer_headers,
        )
        commanded = await client.post(
            f"/api/v1/artifacts/{artifact.artifact_id}/commands",
            json={"type": "artifact.select", "base_version": 1},
            headers={**viewer_headers, "Idempotency-Key": "viewer-denied-1"},
        )
        assert read.status_code == 200
        assert edited.status_code == 403
        assert commanded.status_code == 403

        editor_patch = await client.patch(
            f"/api/v1/artifacts/{artifact.artifact_id}",
            json={
                "base_version": 1,
                "content": contract_content(
                    "ItineraryPlan",
                    artifact_id,
                    2,
                    reason="Authorized editor update.",
                ),
            },
            headers={"X-Test-User": "editor-a"},
        )
        assert editor_patch.status_code == 200
        assert editor_patch.json()["version"] == 2


@pytest.mark.asyncio
async def test_select_is_idempotent_and_illegal_transition_is_rejected() -> None:
    app, store = build_artifact_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "候选选择"})).json()
        artifact = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_type="ItineraryPlan",
            schema_version=1,
            content={"days": []},
            status=ArtifactStatus.CANDIDATE,
        )
        body = {"type": "select", "base_version": 1}
        headers = {"Idempotency-Key": "artifact-select-0001"}
        first = await client.post(
            f"/api/v1/artifacts/{artifact.artifact_id}/commands",
            json=body,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/artifacts/{artifact.artifact_id}/commands",
            json=body,
            headers=headers,
        )
        invalid = await client.post(
            f"/api/v1/artifacts/{artifact.artifact_id}/commands",
            json={"type": "artifact.publish", "base_version": 1},
            headers={"Idempotency-Key": "artifact-publish-bad"},
        )
        reused = await client.post(
            f"/api/v1/artifacts/{artifact.artifact_id}/commands",
            json={"type": "artifact.revoke", "base_version": 1},
            headers=headers,
        )
        assert first.status_code == 200
        assert replay.status_code == 200
        assert first.json() == replay.json()
        assert first.json()["status"] == "selected"
        assert invalid.status_code == 409
        assert invalid.json()["detail"] == {
            "code": "ARTIFACT_TRANSITION_CONFLICT",
            "message": "The Artifact command is not valid from its current status.",
            "retryable": False,
            "current_version": 1,
            "current_status": "selected",
        }
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_publish_atomically_supersedes_previous_pointer_and_revoke_clears_it() -> None:
    app, store = build_artifact_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "发布状态机"})).json()
        first = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"revision": "first"},
            status=ArtifactStatus.VALIDATED,
        )
        second = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"revision": "second"},
            status=ArtifactStatus.VALIDATED,
        )

        first_published = await client.post(
            f"/api/v1/artifacts/{first.artifact_id}/commands",
            json={"type": "artifact.publish", "base_version": 1},
            headers={"Idempotency-Key": "publish-first-0001"},
        )
        second_headers = {"Idempotency-Key": "publish-second-0001"}
        second_body = {"type": "artifact.publish", "base_version": 1}
        second_published = await client.post(
            f"/api/v1/artifacts/{second.artifact_id}/commands",
            json=second_body,
            headers=second_headers,
        )
        superseded = await client.get(
            f"/api/v1/artifacts/{first.artifact_id}",
            params={"version": 1},
        )
        pointed = await client.get(f"/api/v1/trips/{trip['trip_id']}")

        assert first_published.json()["status"] == "published"
        assert second_published.json()["status"] == "published"
        assert superseded.json()["status"] == "superseded"
        assert pointed.json()["current_artifact_id"] == second.artifact_id
        assert pointed.json()["current_artifact_version"] == 1

        revoked = await client.post(
            f"/api/v1/artifacts/{second.artifact_id}/commands",
            json={"type": "artifact.revoke", "base_version": 1},
            headers={"Idempotency-Key": "revoke-second-0001"},
        )
        cleared = await client.get(f"/api/v1/trips/{trip['trip_id']}")
        replayed_publish = await client.post(
            f"/api/v1/artifacts/{second.artifact_id}/commands",
            json=second_body,
            headers=second_headers,
        )
        current = await client.get(f"/api/v1/artifacts/{second.artifact_id}")
        assert revoked.json()["status"] == "revoked"
        assert cleared.json()["current_artifact_id"] is None
        assert cleared.json()["current_artifact_version"] is None
        assert replayed_publish.json()["status"] == "published"
        assert current.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_concurrent_edits_have_one_winner() -> None:
    store = InMemoryPlatformStore()
    principal = owner_principal()
    trip = await store.create_trip(principal, TripCreateRequest(title="并发编辑"))
    artifact_id = "plan_concurrent_001"
    artifact = await store.create_artifact(
        principal,
        trip_id=trip.trip_id,
        artifact_id=artifact_id,
        artifact_type="ItineraryPlan",
        schema_version=1,
        content=contract_content(
            "ItineraryPlan",
            artifact_id,
            1,
            reason="Concurrent edit base.",
        ),
        status=ArtifactStatus.CANDIDATE,
    )

    results = await asyncio.gather(
        store.patch_artifact(
            principal,
            artifact.artifact_id,
            ArtifactPatchRequest(
                base_version=1,
                content=contract_content(
                    "ItineraryPlan",
                    artifact_id,
                    2,
                    reason="Concurrent editor A.",
                ),
            ),
        ),
        store.patch_artifact(
            principal,
            artifact.artifact_id,
            ArtifactPatchRequest(
                base_version=1,
                content=contract_content(
                    "ItineraryPlan",
                    artifact_id,
                    2,
                    reason="Concurrent editor B.",
                ),
            ),
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, VersionConflict)]
    assert len(conflicts) == 1
    assert conflicts[0].current_version == 2


@pytest.mark.asyncio
async def test_patch_validates_every_registered_v1_artifact_contract() -> None:
    store = InMemoryPlatformStore()
    principal = owner_principal()
    trip = await store.create_trip(principal, TripCreateRequest(title="契约注册表"))

    for contract_id, fixture in build_valid_contracts().items():
        artifact_type, schema_version = contract_id.split("@", maxsplit=1)
        artifact_id = str(fixture["artifact_id"])
        await store.create_artifact(
            principal,
            trip_id=trip.trip_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            schema_version=int(schema_version),
            content=contract_content(
                artifact_type,
                artifact_id,
                1,
                reason=f"{artifact_type} registered contract base.",
            ),
            status=ArtifactStatus.CANDIDATE,
        )
        updated = await store.patch_artifact(
            principal,
            artifact_id,
            ArtifactPatchRequest(
                base_version=1,
                content=contract_content(
                    artifact_type,
                    artifact_id,
                    2,
                    reason=f"{artifact_type} registered contract update.",
                ),
            ),
        )
        assert updated.version == 2
        assert updated.content["artifact_id"] == artifact_id
        assert updated.content["artifact_type"] == artifact_type
        assert updated.content["schema_version"] == int(schema_version)
        assert updated.content["version"] == 2


@pytest.mark.asyncio
async def test_invalid_contract_is_generic_and_import_archive_and_unknown_types_fail_closed() -> None:
    app, store = build_artifact_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "契约边界"})).json()
        artifact_id = "plan_invalid_001"
        await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_id=artifact_id,
            artifact_type="ItineraryPlan",
            schema_version=1,
            content=contract_content(
                "ItineraryPlan",
                artifact_id,
                1,
                reason="Invalid contract test base.",
            ),
            status=ArtifactStatus.CANDIDATE,
        )
        invalid_content = contract_content(
            "ItineraryPlan",
            artifact_id,
            2,
            reason="PRIVATE_RAW_MARKER_MUST_NOT_LEAK",
        )
        invalid_content["days"] = []
        invalid = await client.patch(
            f"/api/v1/artifacts/{artifact_id}",
            json={"base_version": 1, "content": invalid_content},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == {
            "code": "ARTIFACT_CONTENT_INVALID",
            "message": "Artifact content does not satisfy its registered contract.",
            "retryable": False,
            "current_version": 1,
        }
        assert "PRIVATE_RAW_MARKER_MUST_NOT_LEAK" not in invalid.text
        assert "validation_error" not in invalid.text.lower()

        mismatched = contract_content(
            "ItineraryPlan",
            artifact_id,
            2,
            reason="Header mismatch must fail.",
        )
        mismatched["artifact_id"] = "plan_wrong_001"
        mismatch_response = await client.patch(
            f"/api/v1/artifacts/{artifact_id}",
            json={"base_version": 1, "content": mismatched},
        )
        assert mismatch_response.status_code == 422
        assert mismatch_response.json()["detail"]["code"] == "ARTIFACT_CONTENT_INVALID"

        imported_archive = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_id="imported_archive_001",
            artifact_type="ImportedTripArchive",
            schema_version=1,
            content={"answer": "migration-only"},
            status=ArtifactStatus.CANDIDATE,
        )
        archive_response = await client.patch(
            f"/api/v1/artifacts/{imported_archive.artifact_id}",
            json={
                "base_version": 1,
                "content": {"raw": "PRIVATE_ARCHIVE_MARKER_MUST_NOT_LEAK"},
            },
        )
        assert archive_response.status_code == 409
        assert archive_response.json()["detail"] == {
            "code": "ARTIFACT_READ_ONLY",
            "message": "This Artifact type does not support versioned editing.",
            "retryable": False,
            "current_version": 1,
        }
        assert "PRIVATE_ARCHIVE_MARKER_MUST_NOT_LEAK" not in archive_response.text
        archive_command = await client.post(
            f"/api/v1/artifacts/{imported_archive.artifact_id}/commands",
            json={"type": "select", "base_version": 1},
            headers={"Idempotency-Key": "archive-readonly-command"},
        )
        assert archive_command.status_code == 409
        assert archive_command.json()["detail"]["code"] == "ARTIFACT_READ_ONLY"

        unknown = await store.create_artifact(
            owner_principal(),
            trip_id=trip["trip_id"],
            artifact_id="future_artifact_001",
            artifact_type="FutureRoutePlan",
            schema_version=1,
            content={"version": 1},
            status=ArtifactStatus.CANDIDATE,
        )
        unknown_response = await client.patch(
            f"/api/v1/artifacts/{unknown.artifact_id}",
            json={
                "base_version": 1,
                "content": {
                    "artifact_id": unknown.artifact_id,
                    "artifact_type": "FutureRoutePlan",
                    "schema_version": 1,
                    "version": 2,
                    "raw": "PRIVATE_UNKNOWN_MARKER_MUST_NOT_LEAK",
                },
            },
        )
        assert unknown_response.status_code == 409
        assert unknown_response.json()["detail"]["code"] == "ARTIFACT_READ_ONLY"
        assert "PRIVATE_UNKNOWN_MARKER_MUST_NOT_LEAK" not in unknown_response.text
