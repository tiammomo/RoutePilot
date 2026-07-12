"""Tests for the clean V1-only FastAPI composition root."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from moyuan_web.bootstrap_app import allowed_origins, create_web_application


def test_local_cors_defaults_and_explicit_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.delenv("ROUTEPILOT_DEPLOYMENT_ENV", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert allowed_origins() == ["http://127.0.0.1:33003", "http://localhost:33003"]

    monkeypatch.setenv("CORS_ORIGINS", "https://travel.example,https://ops.example/")
    assert allowed_origins() == ["https://travel.example", "https://ops.example"]


def test_secure_deployment_requires_explicit_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTEPILOT_DEPLOYMENT_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="explicit CORS_ORIGINS"):
        allowed_origins()
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="explicit CORS_ORIGINS"):
        allowed_origins()


def test_application_exposes_only_v1_business_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://testserver")
    app = create_web_application()
    paths = {route.path for route in app.routes}

    assert "/api/v1/trips" in paths
    assert "/api/live" in paths
    assert "/api/ready" in paths
    assert "/api/health" in paths
    assert "/api/chat/stream" not in paths
    assert "/api/session/new" not in paths
    assert "/api/sessions" not in paths
    assert "/api/models" not in paths

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Request-ID": "unsafe value"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
    assert response.headers["x-request-id"].startswith("req_")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
