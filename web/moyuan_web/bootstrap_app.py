"""Application bootstrap helpers for assembling the FastAPI web service."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from moyuan_web.app_meta import APP_NAME, APP_VERSION, build_metadata
from moyuan_web.bootstrap import ensure_project_paths
from moyuan_web.bootstrap_container import initialize_dependency_container
from moyuan_web.config.runtime import get_model_config_manager, get_server_config
from moyuan_web.middleware import setup_middleware
from moyuan_web.routes import (
    api_docs_router,
    chat_router,
    city_router,
    health_router,
    map_router,
    metrics_endpoint,
    model_router,
    session_router,
    share_router,
)
from moyuan_web.startup_checks import maybe_fail_fast_on_startup

logger = logging.getLogger(__name__)

ensure_project_paths()

DEFAULT_CORS_ORIGINS = (
    "http://localhost:33001",
    "http://localhost:38000",
)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Run startup validation and cache readiness state for health endpoints."""
    app.state.readiness_snapshot = {
        "status": "starting",
        "validated_at": None,
        "checks": {},
    }
    await maybe_fail_fast_on_startup(app)
    yield


def load_server_config_or_none() -> Any:
    """Return server config when available, otherwise log and fall back to defaults."""
    try:
        return get_server_config()
    except Exception as exc:
        logger.warning("Failed to read server config; using middleware defaults: %s", exc)
        return None


def resolve_allowed_origins(
    server_config: Any,
    *,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Resolve CORS origins with explicit runtime override precedence."""
    env_values = env or os.environ
    env_cors = [item.strip() for item in env_values.get("CORS_ORIGINS", "").split(",") if item.strip()]

    try:
        config_cors = list(server_config.cors_origins) if server_config else []
    except Exception as exc:
        logger.warning("Failed to read CORS config; using fallback origins: %s", exc)
        config_cors = []

    return env_cors or config_cors or list(DEFAULT_CORS_ORIGINS)


def configure_cors(app: FastAPI, *, server_config: Any) -> None:
    """Attach CORS middleware using resolved runtime origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_allowed_origins(server_config),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


def warm_application_dependencies() -> None:
    """Preload lightweight runtime dependencies while keeping failures non-fatal."""
    try:
        get_model_config_manager()
        logger.info("Model config manager initialized")
    except Exception as exc:
        logger.warning("Could not initialize model config manager: %s", exc)

    try:
        initialize_dependency_container()
        logger.info("Dependency container initialized")
    except Exception as exc:
        logger.warning("Could not initialize dependency container: %s", exc)


def should_register_metrics_alias(server_config: Any) -> bool:
    """Return whether a custom metrics alias route should be exposed."""
    return bool(
        server_config
        and getattr(server_config, "metrics_enabled", False)
        and getattr(server_config, "metrics_path", None)
        and getattr(server_config, "metrics_path") != "/api/metrics"
    )


def register_api_routes(app: FastAPI, *, server_config: Any) -> None:
    """Register API routers and optional metrics alias endpoints."""
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(session_router, prefix="/api", tags=["session"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(model_router, prefix="/api", tags=["model"])
    app.include_router(city_router, prefix="/api", tags=["city"])
    app.include_router(map_router, prefix="/api", tags=["map"])
    app.include_router(share_router, prefix="/api", tags=["share"])
    app.include_router(api_docs_router)

    if should_register_metrics_alias(server_config):
        app.add_api_route(
            server_config.metrics_path,
            metrics_endpoint,
            methods=["GET"],
            include_in_schema=False,
        )


def build_root_payload() -> dict[str, Any]:
    """Return root endpoint metadata and docs links."""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "build": build_metadata(),
        "docs": "/docs",
        "rapidoc": "/rapidoc",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


def build_openapi_response(app: FastAPI, request: Request) -> JSONResponse:
    """Return the OpenAPI document with a request-aware server URL."""
    openapi_schema = app.openapi()
    base_url = str(request.base_url).rstrip("/")
    openapi_schema["servers"] = [{"url": base_url, "description": "Current server"}]
    return JSONResponse(content=openapi_schema)


def register_metadata_routes(app: FastAPI) -> None:
    """Register root and OpenAPI helper routes on the application."""

    @app.get("/")
    async def root() -> dict[str, Any]:
        return build_root_payload()

    @app.get("/openapi.json", include_in_schema=False)
    async def get_openapi_spec(request: Request) -> JSONResponse:
        return build_openapi_response(app, request)


def create_web_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    server_config = load_server_config_or_none()
    app = FastAPI(
        title=APP_NAME,
        description="AI Travel Assistant API with SSE streaming support.",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=app_lifespan,
    )

    configure_cors(app, server_config=server_config)
    setup_middleware(app)
    warm_application_dependencies()
    register_api_routes(app, server_config=server_config)
    register_metadata_routes(app)
    return app


__all__ = [
    "DEFAULT_CORS_ORIGINS",
    "app_lifespan",
    "build_openapi_response",
    "build_root_payload",
    "configure_cors",
    "create_web_application",
    "load_server_config_or_none",
    "register_api_routes",
    "register_metadata_routes",
    "resolve_allowed_origins",
    "should_register_metrics_alias",
    "warm_application_dependencies",
]
