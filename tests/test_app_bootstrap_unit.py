"""Tests for the clean V1-only FastAPI composition root."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from moyuan_web.bootstrap_app import allowed_origins, create_web_application
from moyuan_web.v1.operations import DependencyReadiness


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
    # FastAPI may retain included routers as internal markers instead of
    # flattening every child route into app.routes. OpenAPI is the stable public
    # business surface this test is intended to constrain.
    paths = set(app.openapi()["paths"])

    assert "/api/v1/trips" in paths
    assert "/api/chat/stream" not in paths
    assert "/api/session/new" not in paths
    assert "/api/sessions" not in paths
    assert "/api/models" not in paths

    with TestClient(app) as client:
        assert client.get("/api/live").status_code == 200
        readiness = client.get("/api/ready")
        assert readiness.status_code == 503
        assert readiness.json() == {
            "status": "not_ready",
            "components": {
                "postgresql": "not_configured",
                "redis": "not_configured",
            },
        }
        for removed_path in (
            "/api/chat/stream",
            "/api/session/new",
            "/api/sessions",
            "/api/models",
        ):
            assert client.get(removed_path).status_code == 404
        response = client.get(
            "/api/health", headers={"X-Request-ID": "unsafe value"}
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}
    assert response.headers["x-request-id"].startswith("req_")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_readiness_probes_dependencies_and_metrics_require_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def healthy() -> bool:
        return True

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://testserver")
    metrics_token = "metrics-test-token-32-characters-long"
    monkeypatch.setenv("ROUTEPILOT_METRICS_TOKEN", metrics_token)
    app = create_web_application()
    app.state.routepilot_readiness_checker = DependencyReadiness(
        database_url="postgresql://probe-only",
        redis_url="redis://probe-only",
        postgresql_probe=healthy,
        redis_probe=healthy,
    )

    with TestClient(app) as client:
        readiness = client.get("/api/ready")
        unauthorized = client.get("/api/metrics")
        metrics = client.get(
            "/api/metrics",
            headers={"Authorization": f"Bearer {metrics_token}"},
        )

    assert readiness.status_code == 200
    assert readiness.json()["components"] == {
        "postgresql": "available",
        "redis": "available",
    }
    assert unauthorized.status_code == 401
    assert metrics.status_code == 200
    assert 'routepilot_dependency_ready{dependency="postgresql"} 1' in metrics.text
    assert 'route="/api/ready"' in metrics.text
