"""Authenticated FastAPI adapter for the RoutePilot A2A 1.0 agent mesh."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated

from a2a.extensions.common import HTTP_EXTENSION_HEADER, get_requested_extensions
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers.response_helpers import agent_card_to_dict, build_error_response
from a2a.server.routes.common import ServerCallContextBuilder
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.utils.errors import InvalidRequestError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from agent.travel_agent.a2a.constants import MAX_A2A_HTTP_BODY_BYTES
from agent.travel_agent.a2a.handler import RoutePilotA2ARequestHandler
from agent.travel_agent.a2a.models import A2AActor
from agent.travel_agent.a2a.registry import AgentExecutor, AgentRegistry, build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import AgentTaskPersistence, InMemoryAgentTaskStore

from .auth import require_principal
from .models import Principal

router = APIRouter(prefix="/a2a")
PrincipalDep = Annotated[Principal, Depends(require_principal)]


class PrincipalContextBuilder(ServerCallContextBuilder):
    """Pass only server-derived V1 Principal claims into the A2A handler."""

    def build(self, request: Request) -> ServerCallContext:
        principal = getattr(request.state, "routepilot_a2a_principal", None)
        if not isinstance(principal, Principal):
            raise RuntimeError("authenticated Principal missing from A2A request")
        actor = A2AActor(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            roles=principal.roles,
            authorization_epoch=principal.authorization_epoch,
        )
        return ServerCallContext(
            state={
                "routepilot_actor": actor,
                "headers": dict(request.headers),
            },
            requested_extensions=get_requested_extensions(
                request.headers.getlist(HTTP_EXTENSION_HEADER)
            ),
        )


@dataclass(slots=True)
class A2ARuntime:
    """App-scoped registry, TaskService and official SDK dispatchers."""

    registry: AgentRegistry
    store: AgentTaskPersistence
    task_service: TaskService
    dispatchers: dict[str, JsonRpcDispatcher]

    async def close(self) -> None:
        """Stop local executions and dispose the configured Task store."""

        await self.task_service.shutdown()


def build_default_a2a_runtime(
    *,
    executors: dict[str, AgentExecutor] | None = None,
    store: AgentTaskPersistence | None = None,
    database_url: str | None = None,
    environment: str | None = None,
) -> A2ARuntime:
    """Select durable PostgreSQL in deployments and memory only for local/test."""

    registry = build_default_registry(executors=executors)
    selected_store = store
    selected_environment = (
        environment if environment is not None else os.getenv("ENVIRONMENT", "dev")
    ).strip().lower()
    selected_database_url = str(
        database_url
        if database_url is not None
        else (
            os.getenv("ROUTEPILOT_A2A_DATABASE_URL", "").strip()
            or os.getenv("ROUTEPILOT_V1_DATABASE_URL", "").strip()
        )
    ).strip()
    if selected_store is None and selected_database_url:
        from agent.travel_agent.a2a.postgres_store import PostgresAgentTaskStore

        selected_store = PostgresAgentTaskStore.from_database_url(selected_database_url)
    elif selected_store is None and selected_environment in {"production", "prod", "staging"}:
        raise RuntimeError(
            "ROUTEPILOT_A2A_DATABASE_URL or ROUTEPILOT_V1_DATABASE_URL is required "
            "outside local/test environments"
        )
    elif selected_store is None:
        selected_store = InMemoryAgentTaskStore()
    service = TaskService(registry, selected_store)
    context_builder = PrincipalContextBuilder()
    dispatchers = {
        profile.interface_id: JsonRpcDispatcher(
            request_handler=RoutePilotA2ARequestHandler(
                profile.interface_id,
                registry,
                service,
            ),
            context_builder=context_builder,
            enable_v0_3_compat=False,
        )
        for profile in registry.list_profiles()
    }
    return A2ARuntime(
        registry=registry,
        store=selected_store,
        task_service=service,
        dispatchers=dispatchers,
    )


async def get_a2a_runtime(request: Request) -> A2ARuntime:
    """Resolve the app-scoped A2A runtime."""

    runtime = getattr(request.app.state, "routepilot_v1_a2a_runtime", None)
    if runtime is None:
        product_runtime = getattr(request.app.state, "routepilot_v1_runtime", None)
        if product_runtime is None:
            from .routes import get_runtime

            product_runtime = get_runtime(request)
        runtime = product_runtime.a2a_runtime
    if runtime is None:
        from agent.travel_agent.runtime_v2 import build_core_a2a_executors

        knowledge = getattr(request.app.state, "routepilot_knowledge_service", None)
        if knowledge is None:
            try:
                from .rag_routes import get_knowledge_service

                knowledge = await get_knowledge_service(request)
            except HTTPException as exc:
                if exc.status_code != status.HTTP_503_SERVICE_UNAVAILABLE:
                    raise
                knowledge = None
        runtime = build_default_a2a_runtime(
            executors=build_core_a2a_executors(knowledge=knowledge)
        )
        request.app.state.routepilot_v1_a2a_runtime = runtime
    if not isinstance(runtime, A2ARuntime):
        raise RuntimeError("routepilot_v1_a2a_runtime must be an A2ARuntime")
    return runtime


RuntimeDep = Annotated[A2ARuntime, Depends(get_a2a_runtime)]


def _resolve_profile(runtime: A2ARuntime, agent_interface_id: str):
    try:
        return runtime.registry.get(agent_interface_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") from exc


def _authorize_agent(principal: Principal, agent_interface_id: str) -> None:
    required_scope = f"agent:{agent_interface_id}"
    if not principal.roles.intersection({"owner", "admin", required_scope}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "AGENT_SCOPE_REQUIRED",
                "message": "The caller is not authorized for this agent interface.",
                "retryable": False,
            },
        )


@router.get("/agents")
async def list_agent_cards(
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> dict[str, object]:
    """List authenticated, curated Agent Cards; no public auto-discovery occurs."""

    visible = []
    for profile in runtime.registry.list_profiles():
        if principal.roles.intersection(
            {"owner", "admin", f"agent:{profile.interface_id}"}
        ):
            visible.append(agent_card_to_dict(profile.card))
    return {"items": visible}


@router.get("/agents/{agent_interface_id}/.well-known/agent-card.json")
async def get_agent_card(
    agent_interface_id: str,
    request: Request,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> Response:
    """Serve an authenticated A2A 1.0 Agent Card with ETag revalidation."""

    _authorize_agent(principal, agent_interface_id)
    profile = _resolve_profile(runtime, agent_interface_id)
    if request.headers.get("If-None-Match") == profile.etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": profile.etag})
    return JSONResponse(
        agent_card_to_dict(profile.card),
        headers={"ETag": profile.etag, "Cache-Control": "private, max-age=60"},
    )


@router.post("/agents/{agent_interface_id}/rpc")
async def a2a_jsonrpc(
    agent_interface_id: str,
    request: Request,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> Response:
    """Dispatch official A2A 1.0 JSON-RPC methods, including SDK-managed SSE."""

    _authorize_agent(principal, agent_interface_id)
    _resolve_profile(runtime, agent_interface_id)
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return JSONResponse(
            build_error_response(None, InvalidRequestError(message="Content-Type must be application/json")),
            status_code=status.HTTP_200_OK,
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_A2A_HTTP_BODY_BYTES:
                return JSONResponse(
                    build_error_response(None, InvalidRequestError(message="Payload too large")),
                    status_code=status.HTTP_200_OK,
                )
        except ValueError:
            return JSONResponse(
                build_error_response(None, InvalidRequestError(message="Invalid Content-Length")),
                status_code=status.HTTP_200_OK,
            )
    body = await request.body()
    if len(body) > MAX_A2A_HTTP_BODY_BYTES:
        return JSONResponse(
            build_error_response(None, InvalidRequestError(message="Payload too large")),
            status_code=status.HTTP_200_OK,
        )
    # Starlette caches the body, so the official dispatcher parses these exact bounded bytes.
    request.state.routepilot_a2a_principal = principal
    dispatcher = runtime.dispatchers[agent_interface_id]
    response = await dispatcher.handle_requests(request)
    response.headers.setdefault("Cache-Control", "no-store, no-transform")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


__all__ = ["A2ARuntime", "build_default_a2a_runtime", "router"]
