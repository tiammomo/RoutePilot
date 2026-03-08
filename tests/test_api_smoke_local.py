"""Local ASGI smoke tests for key web APIs."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

# Ensure `src.*` imports resolve exactly like runtime.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.main import create_app


@pytest.mark.asyncio
async def test_models_session_clear_smoke():
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        models_resp = await client.get("/api/models")
        assert models_resp.status_code == 200
        models_data = models_resp.json()
        assert models_data.get("success") is True
        assert isinstance(models_data.get("models"), list)

        create_resp = await client.post("/api/session/new")
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data.get("success") is True
        session_id = create_data.get("session_id")
        assert isinstance(session_id, str) and session_id

        clear_resp = await client.post("/api/clear", params={"session_id": session_id})
        assert clear_resp.status_code == 200
        clear_data = clear_resp.json()
        assert clear_data.get("success") is True


@pytest.mark.asyncio
async def test_health_routes_smoke():
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health_resp = await client.get("/api/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data.get("status") == "healthy"
        assert isinstance(health_data.get("services"), dict)
        assert "llm" in health_data["services"]

        llm_resp = await client.get("/api/health/llm")
        assert llm_resp.status_code == 200
        llm_data = llm_resp.json()
        assert llm_data.get("status") in {"ok", "not initialized"}
        assert isinstance(llm_data.get("tools_count"), int)

        tools_resp = await client.get("/api/health/tools")
        assert tools_resp.status_code == 200
        tools_data = tools_resp.json()
        assert tools_data.get("status") in {"ok", "not initialized"}
        assert isinstance(tools_data.get("configured_tools_count"), int)
        assert isinstance(tools_data.get("circuit_open_count"), int)
        assert isinstance(tools_data.get("window_minutes"), int)
        assert isinstance(tools_data.get("diagnostics"), dict)
        assert isinstance(tools_data.get("slo"), dict)
        assert tools_data["slo"].get("status") in {"ok", "degraded"}
        assert isinstance(tools_data["slo"].get("timeout_rate"), float)
        assert isinstance(tools_data["slo"].get("failure_rate"), float)
        assert isinstance(tools_data["slo"].get("fallback_rate"), float)
        assert isinstance(tools_data["slo"].get("thresholds"), dict)
        assert isinstance(tools_data.get("intent_aggregate"), dict)

        intent_resp = await client.get("/api/health/tools/intents")
        assert intent_resp.status_code == 200
        intent_data = intent_resp.json()
        assert intent_data.get("status") in {"ok", "not initialized"}
        assert isinstance(intent_data.get("window_minutes"), int)
        assert isinstance(intent_data.get("total_requests"), int)
        assert isinstance(intent_data.get("intent_aggregate"), dict)

        ready_resp = await client.get("/api/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json().get("status") == "ready"

        live_resp = await client.get("/api/live")
        assert live_resp.status_code == 200
        assert live_resp.json().get("status") == "alive"


@pytest.mark.asyncio
async def test_city_routes_smoke():
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        cities_resp = await client.get("/api/cities")
        assert cities_resp.status_code == 200
        cities_data = cities_resp.json()
        cities = cities_data.get("cities")
        assert isinstance(cities, list)
        assert len(cities) > 0

        region_resp = await client.get("/api/cities", params={"region": "华东"})
        assert region_resp.status_code == 200
        region_cities = region_resp.json().get("cities")
        assert isinstance(region_cities, list)
        assert len(region_cities) > 0
        assert all(item.get("region") == "华东" for item in region_cities)

        tags_resp = await client.get("/api/cities", params={"tags": "美食, 休闲, ,美食"})
        assert tags_resp.status_code == 200
        tag_cities = tags_resp.json().get("cities")
        assert isinstance(tag_cities, list)
        assert len(tag_cities) > 0
        assert any("美食" in item.get("tags", []) for item in tag_cities)
        assert any("休闲" in item.get("tags", []) for item in tag_cities)

        first_city_id = cities[0]["id"]
        city_resp = await client.get(f"/api/cities/{first_city_id}")
        assert city_resp.status_code == 200
        city_data = city_resp.json()
        assert city_data.get("id") == first_city_id
        assert isinstance(city_data.get("attractions"), list)

        attractions_resp = await client.get(f"/api/cities/{first_city_id}/attractions")
        assert attractions_resp.status_code == 200
        attractions_data = attractions_resp.json()
        assert isinstance(attractions_data.get("attractions"), list)

        regions_resp = await client.get("/api/regions")
        assert regions_resp.status_code == 200
        regions = regions_resp.json().get("regions")
        assert isinstance(regions, list)
        assert regions == sorted(regions)

        all_tags_resp = await client.get("/api/tags")
        assert all_tags_resp.status_code == 200
        all_tags = all_tags_resp.json().get("tags")
        assert isinstance(all_tags, list)
        assert all_tags == sorted(all_tags)

        missing_city_resp = await client.get("/api/cities/not-exists")
        assert missing_city_resp.status_code == 404
        missing_city_data = missing_city_resp.json()
        assert missing_city_data.get("detail", {}).get("success") is False
        assert missing_city_data.get("detail", {}).get("error") == "City not found"
        assert missing_city_data.get("detail", {}).get("code") == "CITY_NOT_FOUND"
