"""Clean RoutePilot V1 FastAPI composition root."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .error_handlers import register_exception_handlers
from .middleware import setup_middleware
from .v1 import v1_router
from .v1.auth import install_oidc_authenticator

APP_NAME = "RoutePilot API"
APP_VERSION = "1.0.0"


def _deployment() -> str:
    return (
        os.getenv("ROUTEPILOT_DEPLOYMENT_ENV", "")
        or os.getenv("ENVIRONMENT", "dev")
    ).strip().lower()


def allowed_origins() -> list[str]:
    """Resolve an explicit CORS allowlist and fail closed in secure deployments."""

    origins = [
        value.strip().rstrip("/")
        for value in os.getenv("CORS_ORIGINS", "").split(",")
        if value.strip()
    ]
    secure = _deployment() in {"staging", "preprod", "production", "prod"}
    if secure and (not origins or "*" in origins):
        raise RuntimeError("secure deployments require an explicit CORS_ORIGINS allowlist")
    if any(not item.startswith(("http://", "https://")) or item == "*" for item in origins):
        raise RuntimeError("CORS_ORIGINS contains an invalid origin")
    return origins or ["http://127.0.0.1:33003", "http://localhost:33003"]


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Release lazily-created V1 resources on shutdown."""

    yield
    runtime = getattr(app.state, "routepilot_v1_runtime", None)
    if runtime is not None:
        await runtime.close()


def create_web_application() -> FastAPI:
    """Build the only supported API surface: health, docs, and `/api/v1`."""

    app = FastAPI(
        title=APP_NAME,
        description="Artifact-first multi-agent travel planning API.",
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=app_lifespan,
    )
    install_oidc_authenticator(app)
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "If-Match",
            "X-Request-ID",
            "X-RoutePilot-Dev-BFF-Secret",
            "X-RoutePilot-Dev-Tenant",
            "X-RoutePilot-Dev-User",
            "X-RoutePilot-Dev-Roles",
        ],
        expose_headers=["X-Request-ID"],
    )
    setup_middleware(app)
    app.include_router(v1_router, prefix="/api", tags=["v1"])

    @app.get("/api/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/api/ready", include_in_schema=False)
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": APP_NAME, "version": APP_VERSION, "docs": "/docs"}

    return app


__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "allowed_origins",
    "app_lifespan",
    "create_web_application",
]
