"""V1 Product Run, replay, tenancy, and cancellation contract tests."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request

from backend.moyuan_web.v1.models import Principal, RunLifecycle
from backend.moyuan_web.v1.routes import router
from backend.moyuan_web.v1.runtime import ExecutionResult, RunCoordinator, V1Runtime
from backend.moyuan_web.v1.store import InMemoryPlatformStore
from routepilot_contracts import validate_run_event


class FakeWholeRunExecutor:
    """Deterministic whole-run executor with an optional cancellation gate."""

    def __init__(self, gate: asyncio.Event | None = None, *, publishable: bool = True):
        self.gate = gate
        self.publishable = publishable
        self.calls = 0

    async def execute(self, run, principal, progress):
        self.calls += 1
        await progress("planning", "正在生成测试行程", 50)
        if self.gate is not None:
            await self.gate.wait()
        return ExecutionResult(
            artifact_type="TripSnapshot",
            schema_version=1,
            content={
                "schema_version": 1,
                "schema_origin": "test",
                "source_run_id": run.run_id,
                "answer": f"{principal.user_id}:{run.command.message}",
                "artifact": {},
            },
            publishable=self.publishable,
        )


def build_test_app(executor: FakeWholeRunExecutor, *, authenticated: bool = True) -> FastAPI:
    store = InMemoryPlatformStore()
    runtime = V1Runtime(store=store, coordinator=RunCoordinator(store, executor))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.routepilot_v1_runtime = runtime

    if authenticated:
        async def authenticate(request: Request) -> Principal:
            return Principal(
                tenant_id=request.headers.get("X-Test-Tenant", "tenant-a"),
                user_id=request.headers.get("X-Test-User", "user-a"),
                roles=frozenset({"owner"}),
                authorization_epoch=int(request.headers.get("X-Test-Epoch", "0")),
            )

        app.state.routepilot_v1_authenticator = authenticate
    return app


async def wait_for_terminal(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    for _ in range(100):
        response = await client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["lifecycle_state"] in {"completed", "failed", "canceled"}:
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError("run did not reach a terminal state")


@pytest.mark.asyncio
async def test_v1_denies_anonymous_requests_by_default():
    app = build_test_app(FakeWholeRunExecutor(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/trips")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.asyncio
async def test_v1_trip_scope_hides_cross_tenant_resources():
    app = build_test_app(FakeWholeRunExecutor())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post("/api/v1/trips", json={"title": "北京两日"})
        assert created.status_code == 201
        trip_id = created.json()["trip_id"]

        hidden = await client.get(
            f"/api/v1/trips/{trip_id}",
            headers={"X-Test-Tenant": "tenant-b", "X-Test-User": "user-b"},
        )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_v1_trip_membership_enforces_viewer_editor_and_owner_boundaries():
    app = build_test_app(FakeWholeRunExecutor())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        created = await client.post("/api/v1/trips", json={"title": "成员边界"})
        trip_id = created.json()["trip_id"]
        editor = await client.put(
            f"/api/v1/trips/{trip_id}/members/user-b",
            json={"role": "editor"},
        )
        viewer = await client.put(
            f"/api/v1/trips/{trip_id}/members/user-c",
            json={"role": "viewer"},
        )
        assert editor.status_code == 200
        assert viewer.status_code == 200

        edited = await client.patch(
            f"/api/v1/trips/{trip_id}",
            json={"title": "编辑者可修改"},
            headers={"X-Test-User": "user-b"},
        )
        viewed = await client.get(
            f"/api/v1/trips/{trip_id}",
            headers={"X-Test-User": "user-c"},
        )
        denied_write = await client.patch(
            f"/api/v1/trips/{trip_id}",
            json={"title": "查看者不可修改"},
            headers={"X-Test-User": "user-c"},
        )
        denied_admin = await client.put(
            f"/api/v1/trips/{trip_id}/members/user-d",
            json={"role": "viewer"},
            headers={"X-Test-User": "user-b"},
        )
        outsider = await client.get(
            f"/api/v1/trips/{trip_id}",
            headers={"X-Test-User": "user-z"},
        )

        assert edited.status_code == 200
        assert viewed.status_code == 200
        assert denied_write.status_code == 403
        assert denied_admin.status_code == 403
        assert outsider.status_code == 403

        revoked = await client.delete(f"/api/v1/trips/{trip_id}/members/user-c")
        after_revoke = await client.get(
            f"/api/v1/trips/{trip_id}",
            headers={"X-Test-User": "user-c"},
        )
        assert revoked.status_code == 204
        assert after_revoke.status_code == 403


@pytest.mark.asyncio
async def test_v1_run_is_idempotent_and_events_are_replayable():
    executor = FakeWholeRunExecutor()
    app = build_test_app(executor)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "北京两日"})).json()
        request = {
            "command": {
                "type": "trip.plan",
                "message": "带父母少走路",
            }
        }
        headers = {"Idempotency-Key": "idem-run-0001"}
        first = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json=request,
            headers=headers,
        )
        second = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json=request,
            headers=headers,
        )
        assert first.status_code == 202
        assert second.status_code == 202
        assert second.json()["run_id"] == first.json()["run_id"]

        terminal = await wait_for_terminal(client, first.json()["run_id"])
        assert terminal["lifecycle_state"] == "completed"
        assert executor.calls == 1

        async with client.stream(
            "GET",
            f"/api/v1/runs/{terminal['run_id']}/events",
        ) as response:
            body = (await response.aread()).decode()
        events = [
            json.loads(line.removeprefix("data: "))
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
        assert events[0]["type"] == "run.accepted"
        assert events[-1]["type"] == "run.completed"
        assert all("reasoning" not in json.dumps(event) for event in events)
        for event in events:
            validate_run_event(event)

        after_first = await client.get(
            f"/api/v1/runs/{terminal['run_id']}/events",
            headers={"Last-Event-ID": "1"},
        )
        assert "id: 1\n" not in after_first.text


@pytest.mark.asyncio
async def test_v1_idempotency_key_reuse_with_different_request_is_rejected():
    app = build_test_app(FakeWholeRunExecutor())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "北京"})).json()
        headers = {"Idempotency-Key": "idem-run-0002"}
        first = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json={"command": {"type": "trip.plan", "message": "计划 A"}},
            headers=headers,
        )
        conflict = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json={"command": {"type": "trip.plan", "message": "计划 B"}},
            headers=headers,
        )
        assert first.status_code == 202
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.asyncio
async def test_v1_cancel_uses_control_version_and_reaches_terminal_state():
    gate = asyncio.Event()
    app = build_test_app(FakeWholeRunExecutor(gate))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "北京"})).json()
        created = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json={"command": {"type": "trip.plan", "message": "慢计划"}},
            headers={"Idempotency-Key": "idem-run-cancel"},
        )
        run_id = created.json()["run_id"]

        current: dict[str, Any] = created.json()
        for _ in range(100):
            current = (await client.get(f"/api/v1/runs/{run_id}")).json()
            if current["phase"] == "planning":
                break
            await asyncio.sleep(0.01)

        canceled = await client.post(
            f"/api/v1/runs/{run_id}/cancel",
            json={"expected_control_version": current["control_version"]},
            headers={"Idempotency-Key": "idem-cancel-0001"},
        )
        assert canceled.status_code == 200
        assert canceled.json()["lifecycle_state"] == RunLifecycle.CANCEL_REQUESTED.value

        terminal = await wait_for_terminal(client, run_id)
        assert terminal["lifecycle_state"] == RunLifecycle.CANCELED.value


@pytest.mark.asyncio
async def test_validation_block_exposes_a_candidate_reference_without_publishing() -> None:
    app = build_test_app(FakeWholeRunExecutor(publishable=False))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        trip = (await client.post("/api/v1/trips", json={"title": "校验阻断"})).json()
        created = await client.post(
            f"/api/v1/trips/{trip['trip_id']}/runs",
            json={"command": {"type": "trip.plan", "message": "生成候选"}},
            headers={"Idempotency-Key": "validation-block-candidate"},
        )
        terminal = await wait_for_terminal(client, created.json()["run_id"])
        events = (
            await client.get(f"/api/v1/runs/{terminal['run_id']}/events")
        ).text
        refreshed_trip = (await client.get(f"/api/v1/trips/{trip['trip_id']}" )).json()
        artifacts = (
            await client.get(f"/api/v1/trips/{trip['trip_id']}/artifacts")
        ).json()["items"]

    assert terminal["lifecycle_state"] == "failed"
    assert terminal["public_error_code"] == "VALIDATION_BLOCKED"
    assert "event: artifact.candidate_updated" in events
    assert artifacts[0]["status"] == "candidate"
    assert refreshed_trip["current_artifact_id"] is None
