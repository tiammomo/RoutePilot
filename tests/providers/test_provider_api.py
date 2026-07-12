"""Metadata-only HTTP contract for provider capabilities and health."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from agent.travel_agent.providers import build_default_provider_gateway
from backend.moyuan_web.v1.auth import require_principal
from backend.moyuan_web.v1.models import Principal
from backend.moyuan_web.v1.provider_routes import router


@pytest.mark.asyncio
async def test_provider_metadata_endpoints_are_authenticated_and_secret_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "server-secret-never-in-metadata"
    monkeypatch.setenv("ROUTEPILOT_AMAP_WEB_KEY", secret)
    monkeypatch.setenv("ROUTEPILOT_PROVIDER_ALLOWLIST", "amap")
    gateway = build_default_provider_gateway()
    app = FastAPI()
    app.state.routepilot_provider_gateway = gateway
    app.include_router(router, prefix="/api/v1")

    async def authenticated_principal() -> Principal:
        return Principal(tenant_id="tenant-a", user_id="user-a")

    app.dependency_overrides[require_principal] = authenticated_principal
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        capabilities = await client.get("/api/v1/providers/capabilities")
        health = await client.get("/api/v1/providers/health")

    assert capabilities.status_code == 200
    assert health.status_code == 200
    serialized = capabilities.text + health.text
    assert secret not in serialized
    assert "ROUTEPILOT_AMAP_WEB_KEY" not in serialized
    assert "restapi.amap.com" not in serialized

    amap_capability = next(
        item for item in capabilities.json()["providers"] if item["provider_id"] == "amap"
    )
    assert set(amap_capability) == {
        "provider_id",
        "display_name",
        "api_family",
        "api_version",
        "capabilities",
        "configured",
    }
    assert set(amap_capability["capabilities"]) == {
        "place_search",
        "geocode",
        "route_matrix",
        "opening_hours",
        "weather",
    }
    assert len(capabilities.json()["providers"]) == 1
    amap_health = next(
        item for item in health.json()["providers"] if item["provider_id"] == "amap"
    )
    assert set(amap_health) == {
        "provider_id",
        "configured",
        "allowed",
        "circuit_state",
        "capabilities",
    }
    await gateway.close()
