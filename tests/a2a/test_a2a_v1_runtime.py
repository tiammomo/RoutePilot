"""A2A 1.0 Agent Card, JSON-RPC, Task and security contract tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from fastapi import FastAPI, Request

from agent.travel_agent.a2a.constants import (
    INPUT_RESPONSE_SCHEMA_URI,
    TRAVEL_ARTIFACT_EXTENSION_URI,
    invocation_schema_uri,
)
from agent.travel_agent.a2a.handler import RoutePilotA2ARequestHandler
from agent.travel_agent.a2a.models import (
    A2AActor,
    ArtifactOutput,
    CompletedExecution,
    InputField,
    InputRequiredExecution,
    TypedInputRequest,
)
from agent.travel_agent.a2a.registry import build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import InMemoryAgentTaskStore
from backend.moyuan_web.v1.a2a_routes import (
    A2ARuntime,
    PrincipalContextBuilder,
    router,
)
from backend.moyuan_web.v1.models import Principal


class GateResearchExecutor:
    """Hold one valid result until tests inspect working/cancellation state."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def execute(self, context, invocation, input_response):
        del context, invocation, input_response
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return CompletedExecution(
            artifacts=[
                ArtifactOutput(
                    contract="EvidenceBundle@1",
                    payload={"artifact_type": "EvidenceBundle", "safe": True},
                    name="Evidence bundle",
                )
            ]
        )


class ClarifyingResearchExecutor:
    """Interrupt once for typed input, then complete after the matching response."""

    async def execute(self, context, invocation, input_response):
        del context, invocation
        if input_response is None:
            return InputRequiredExecution(
                request=TypedInputRequest(
                    request_id="clarify_dates",
                    prompt="请选择出发日期。",
                    fields=[
                        InputField(
                            field_id="start_date",
                            label="出发日期",
                            input_type="date",
                        )
                    ],
                )
            )
        return CompletedExecution(
            artifacts=[
                ArtifactOutput(
                    contract="EvidenceBundle@1",
                    payload={"artifact_type": "EvidenceBundle", "safe": True},
                    name="Evidence bundle",
                )
            ]
        )


def _permissive_contract_validator(contract: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert contract.endswith("@1")
    assert isinstance(payload, dict)
    return payload


def build_app(executor: Any, *, authenticated: bool = True) -> tuple[FastAPI, A2ARuntime]:
    registry = build_default_registry(
        base_url="http://testserver/api/v1/a2a",
        executors={"research": executor},
    )
    store = InMemoryAgentTaskStore()
    service = TaskService(
        registry,
        store,
        contract_validator=_permissive_contract_validator,
    )
    context_builder = PrincipalContextBuilder()
    dispatchers = {
        profile.interface_id: JsonRpcDispatcher(
            RoutePilotA2ARequestHandler(profile.interface_id, registry, service),
            context_builder=context_builder,
        )
        for profile in registry.list_profiles()
    }
    runtime = A2ARuntime(registry, store, service, dispatchers)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.routepilot_v1_a2a_runtime = runtime
    if authenticated:

        async def authenticate(request: Request) -> Principal:
            return Principal(
                tenant_id=request.headers.get("X-Test-Tenant", "tenant-a"),
                user_id=request.headers.get("X-Test-User", "orchestrator-a"),
                roles=frozenset({"owner"}),
            )

        app.state.routepilot_v1_authenticator = authenticate
    return app, runtime


def rpc_headers(**extra: str) -> dict[str, str]:
    return {
        "A2A-Version": "1.0",
        "A2A-Extensions": TRAVEL_ARTIFACT_EXTENSION_URI,
        **extra,
    }


def initial_message(
    *,
    dispatch_id: str,
    run_id: str = "run_test_001",
    return_immediately: bool = True,
) -> dict[str, Any]:
    return {
        "tenant": "tenant-a",
        "message": {
            "messageId": dispatch_id,
            "role": "ROLE_USER",
            "parts": [
                {
                    "data": {
                        "goal": "为北京两日游检索可靠证据",
                        "artifacts": [
                            {
                                "contract": "TripBrief@1",
                                "payload": {"artifact_type": "TripBrief"},
                            }
                        ],
                    },
                    "metadata": {
                        "schema_uri": invocation_schema_uri("research"),
                        "schema_version": 1,
                    },
                }
            ],
            "metadata": {
                TRAVEL_ARTIFACT_EXTENSION_URI: {
                    "dispatch_id": dispatch_id,
                    "run_id": run_id,
                }
            },
            "extensions": [TRAVEL_ARTIFACT_EXTENSION_URI],
        },
        "configuration": {"returnImmediately": return_immediately},
    }


async def rpc(
    client: httpx.AsyncClient,
    method: str,
    params: dict[str, Any],
    *,
    request_id: str = "rpc-1",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/a2a/agents/research/rpc",
        json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        headers=headers or rpc_headers(),
    )


async def get_task(
    client: httpx.AsyncClient,
    task_id: str,
    *,
    tenant: str = "tenant-a",
) -> dict[str, Any]:
    response = await rpc(
        client,
        "GetTask",
        {"tenant": tenant, "id": task_id},
        request_id=f"get-{uuid4()}",
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_curated_agent_cards_use_a2a_1_jsonrpc_and_etag():
    app, runtime = build_app(GateResearchExecutor())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        listed = await client.get("/api/v1/a2a/agents")
        card = await client.get(
            "/api/v1/a2a/agents/research/.well-known/agent-card.json"
        )
        cached = await client.get(
            "/api/v1/a2a/agents/research/.well-known/agent-card.json",
            headers={"If-None-Match": card.headers["ETag"]},
        )

    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 5
    assert {profile.interface_id for profile in runtime.registry.list_profiles()} == {
        "answering",
        "research",
        "planner",
        "validation",
        "semantic-verifier",
    }
    payload = card.json()
    assert payload["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
    assert payload["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert payload["capabilities"]["streaming"] is True
    assert cached.status_code == 304


@pytest.mark.asyncio
async def test_send_message_is_deduped_scoped_and_maps_to_product_run():
    executor = GateResearchExecutor()
    app, runtime = build_app(executor)
    dispatch_id = str(uuid4())
    params = initial_message(dispatch_id=dispatch_id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await rpc(client, "SendMessage", params)
        duplicate = await rpc(client, "SendMessage", params, request_id="rpc-duplicate")
        assert first.status_code == duplicate.status_code == 200
        task_id = first.json()["result"]["task"]["id"]
        assert duplicate.json()["result"]["task"]["id"] == task_id
        await asyncio.wait_for(executor.started.wait(), timeout=1)

        cross_tenant = await get_task(client, task_id, tenant="tenant-b")
        assert cross_tenant["error"]["code"] == -32001

        refs = await runtime.task_service.list_run_task_refs(
            A2AActor(tenant_id="tenant-a", actor_id="orchestrator-a"),
            "run_test_001",
        )
        assert [(item.agent_interface_id, item.task_id) for item in refs] == [
            ("research", task_id)
        ]

        executor.release.set()
        for _ in range(100):
            current = await get_task(client, task_id)
            if current["result"]["status"]["state"] == "TASK_STATE_COMPLETED":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("Task did not complete")

    assert executor.calls == 1
    serialized = json.dumps(current, ensure_ascii=False)
    assert "reasoning" not in serialized.lower()
    assert "tool_call" not in serialized.lower()
    assert current["result"]["artifacts"][0]["parts"][0]["data"]["safe"] is True


@pytest.mark.asyncio
async def test_input_required_uses_same_task_and_typed_supplement():
    app, _runtime = build_app(ClarifyingResearchExecutor())
    dispatch_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        interrupted = await rpc(
            client,
            "SendMessage",
            initial_message(dispatch_id=dispatch_id, return_immediately=False),
        )
        task = interrupted.json()["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        request_part = task["status"]["message"]["parts"][0]
        assert request_part["metadata"]["schema_uri"].endswith("input-request:v1")

        supplement_id = str(uuid4())
        resumed = await rpc(
            client,
            "SendMessage",
            {
                "tenant": "tenant-a",
                "message": {
                    "messageId": supplement_id,
                    "taskId": task["id"],
                    "contextId": task["contextId"],
                    "role": "ROLE_USER",
                    "parts": [
                        {
                            "data": {
                                "request_id": "clarify_dates",
                                "values": {"start_date": "2026-10-01"},
                            },
                            "metadata": {
                                "schema_uri": INPUT_RESPONSE_SCHEMA_URI,
                                "schema_version": 1,
                            },
                        }
                    ],
                    "metadata": {
                        TRAVEL_ARTIFACT_EXTENSION_URI: {
                            "dispatch_id": dispatch_id,
                            "run_id": "run_test_001",
                        }
                    },
                    "extensions": [TRAVEL_ARTIFACT_EXTENSION_URI],
                },
            },
            request_id="rpc-resume",
        )
    resumed_task = resumed.json()["result"]["task"]
    assert resumed_task["id"] == task["id"]
    assert resumed_task["status"]["state"] == "TASK_STATE_COMPLETED"


@pytest.mark.asyncio
async def test_cancel_fences_late_executor_result():
    executor = GateResearchExecutor()
    app, _runtime = build_app(executor)
    dispatch_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        sent = await rpc(client, "SendMessage", initial_message(dispatch_id=dispatch_id))
        task_id = sent.json()["result"]["task"]["id"]
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        canceled = await rpc(
            client,
            "CancelTask",
            {"tenant": "tenant-a", "id": task_id},
            request_id="rpc-cancel",
        )
        executor.release.set()
        await asyncio.sleep(0)
        current = await get_task(client, task_id)
    assert canceled.json()["result"]["status"]["state"] == "TASK_STATE_CANCELED"
    assert current["result"]["status"]["state"] == "TASK_STATE_CANCELED"
    assert "artifacts" not in current["result"]


@pytest.mark.asyncio
async def test_task_deadline_fails_with_safe_public_error():
    executor = GateResearchExecutor()
    app, _runtime = build_app(executor)
    dispatch_id = str(uuid4())
    params = initial_message(dispatch_id=dispatch_id)
    params["message"]["metadata"][TRAVEL_ARTIFACT_EXTENSION_URI]["deadline"] = (
        datetime.now(UTC) + timedelta(milliseconds=50)
    ).isoformat()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        sent = await rpc(client, "SendMessage", params)
        task_id = sent.json()["result"]["task"]["id"]
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        for _ in range(100):
            current = await get_task(client, task_id)
            if current["result"]["status"]["state"] == "TASK_STATE_FAILED":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("Task did not fail at its deadline")
    error = current["result"]["status"]["message"]["parts"][0]["data"]
    assert error["code"] == "AGENT_DEADLINE_EXCEEDED"
    assert "exception" not in json.dumps(error).lower()


@pytest.mark.asyncio
async def test_streaming_schema_and_security_fail_closed():
    executor = GateResearchExecutor()
    app, _runtime = build_app(executor)
    dispatch_id = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        async def release_executor() -> None:
            await executor.started.wait()
            executor.release.set()

        releaser = asyncio.create_task(release_executor())
        streamed = await rpc(
            client,
            "SendStreamingMessage",
            initial_message(dispatch_id=dispatch_id),
            request_id="rpc-stream",
        )
        await releaser
        assert streamed.headers["content-type"].startswith("text/event-stream")
        assert "statusUpdate" in streamed.text
        assert "artifactUpdate" in streamed.text
        assert "reasoning" not in streamed.text.lower()

        raw_id = str(uuid4())
        invalid = initial_message(dispatch_id=raw_id)
        invalid["message"]["parts"] = [
            {
                "raw": "c2VjcmV0",
                "mediaType": "application/octet-stream",
                "metadata": {
                    "schema_uri": invocation_schema_uri("research"),
                    "schema_version": 1,
                },
            }
        ]
        rejected = await rpc(client, "SendMessage", invalid, request_id="rpc-raw")
        assert rejected.json()["error"]["code"] == -32005

        no_version = await rpc(
            client,
            "GetTask",
            {"tenant": "tenant-a", "id": "missing"},
            headers={"A2A-Extensions": TRAVEL_ARTIFACT_EXTENSION_URI},
        )
        assert no_version.json()["error"]["code"] == -32009


@pytest.mark.asyncio
async def test_a2a_denies_anonymous_requests_and_oversize_payloads():
    app, _runtime = build_app(GateResearchExecutor(), authenticated=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        anonymous = await client.get("/api/v1/a2a/agents")
    assert anonymous.status_code == 401

    authenticated_app, _runtime = build_app(GateResearchExecutor())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=authenticated_app), base_url="http://testserver"
    ) as client:
        oversized = await client.post(
            "/api/v1/a2a/agents/research/rpc",
            content=b"{" + b"x" * (256 * 1024) + b"}",
            headers={"Content-Type": "application/json", **rpc_headers()},
        )
    assert oversized.status_code == 200
    assert oversized.json()["error"]["code"] == -32600
