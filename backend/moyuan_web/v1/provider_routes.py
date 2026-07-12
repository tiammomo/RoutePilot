"""Authenticated metadata-only endpoints for the live Provider Gateway."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict

from agent.travel_agent.providers import (
    ProviderDescriptor,
    ProviderGateway,
    ProviderHealth,
    build_default_provider_gateway,
)

from .auth import require_principal
from .models import Principal

@asynccontextmanager
async def provider_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Close the app-scoped reusable HTTP client during graceful shutdown."""

    yield
    gateway = getattr(app.state, "routepilot_provider_gateway", None)
    product_runtime = getattr(app.state, "routepilot_v1_runtime", None)
    runtime_gateway = (
        getattr(product_runtime, "provider_gateway", None)
        if product_runtime is not None
        else None
    )
    if gateway is not None and gateway is not runtime_gateway:
        await gateway.close()


router = APIRouter(
    prefix="/providers",
    tags=["v1-providers"],
    lifespan=provider_lifespan,
)
PrincipalDep = Annotated[Principal, Depends(require_principal)]


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderCapabilitiesResponse(_StrictResponse):
    providers: tuple[ProviderDescriptor, ...]


class ProviderHealthResponse(_StrictResponse):
    providers: tuple[ProviderHealth, ...]


def get_provider_gateway(request: Request) -> ProviderGateway:
    """Resolve one app-scoped gateway so HTTP clients and resilience state are reused."""

    gateway = getattr(request.app.state, "routepilot_provider_gateway", None)
    if gateway is None:
        product_runtime = getattr(request.app.state, "routepilot_v1_runtime", None)
        if product_runtime is not None:
            gateway = product_runtime.provider_gateway
    if gateway is None:
        gateway = build_default_provider_gateway()
        request.app.state.routepilot_provider_gateway = gateway
    return gateway


GatewayDep = Annotated[ProviderGateway, Depends(get_provider_gateway)]


@router.get("/capabilities", response_model=ProviderCapabilitiesResponse)
async def list_provider_capabilities(
    principal: PrincipalDep,
    gateway: GatewayDep,
) -> ProviderCapabilitiesResponse:
    """List non-secret provider versions and typed capabilities."""

    del principal
    return ProviderCapabilitiesResponse(providers=gateway.descriptors())


@router.get("/health", response_model=ProviderHealthResponse)
async def provider_health(
    principal: PrincipalDep,
    gateway: GatewayDep,
) -> ProviderHealthResponse:
    """Expose configured/allowlisted/circuit metadata without probing upstream."""

    del principal
    return ProviderHealthResponse(providers=gateway.health())


__all__ = [
    "ProviderCapabilitiesResponse",
    "ProviderHealthResponse",
    "get_provider_gateway",
    "provider_lifespan",
    "router",
]
