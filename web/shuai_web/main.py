"""FastAPI entrypoint for ShuaiTravelAgent web API."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shuai_web.app_meta import APP_NAME, APP_VERSION, build_metadata
from shuai_web.bootstrap import ensure_project_paths
from shuai_web.config.runtime import get_model_config_manager, get_server_config
from shuai_web.middleware import setup_middleware
from shuai_web.startup_checks import maybe_fail_fast_on_startup
from shuai_web.routes import (
    api_docs_router,
    city_router,
    health_router,
    map_router,
    model_router,
    session_router,
    share_router,
)
from shuai_web.routes.chat import router as chat_router
from shuai_web.routes.health import metrics_endpoint

logger = logging.getLogger(__name__)

ensure_project_paths()


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


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    try:
        server_config = get_server_config()
    except Exception as exc:
        logger.warning("Failed to read server config; using middleware defaults: %s", exc)
        server_config = None

    app = FastAPI(
        title=APP_NAME,
        description="AI Travel Assistant API with SSE streaming support.",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=app_lifespan,
    )

    # Load CORS configuration.
    try:
        config_cors = server_config.cors_origins if server_config else []
    except Exception as exc:
        logger.warning("Failed to read CORS config; using fallback origins: %s", exc)
        config_cors = []

    env_cors = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    default_cors = [
        "http://localhost:33001",
        "http://localhost:38000",
    ]
    allowed_origins = [c for c in env_cors if c] or config_cors or default_cors

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    setup_middleware(app)

    # Warm up model config manager.
    try:
        get_model_config_manager()
        logger.info("Model config manager initialized")
    except Exception as exc:
        logger.warning("Could not initialize model config manager: %s", exc)

    # Initialize dependency container.
    try:
        from shuai_web.dependencies.container import get_container

        get_container()
        logger.info("Dependency container initialized")
    except Exception as exc:
        logger.warning("Could not initialize dependency container: %s", exc)

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(session_router, prefix="/api", tags=["session"])
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(model_router, prefix="/api", tags=["model"])
    app.include_router(city_router, prefix="/api", tags=["city"])
    app.include_router(map_router, prefix="/api", tags=["map"])
    app.include_router(share_router, prefix="/api", tags=["share"])
    app.include_router(api_docs_router)

    if (
        server_config
        and server_config.metrics_enabled
        and server_config.metrics_path
        and server_config.metrics_path != "/api/metrics"
    ):
        app.add_api_route(
            server_config.metrics_path,
            metrics_endpoint,
            methods=["GET"],
            include_in_schema=False,
        )

    @app.get("/")
    async def root() -> dict:
        """Return root endpoint metadata and docs links.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            dict: Structured dictionary result for upstream callers.
        """
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "build": build_metadata(),
            "docs": "/docs",
            "rapidoc": "/rapidoc",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }

    @app.get("/openapi.json", include_in_schema=False)
    async def get_openapi_spec(request: Request):
        """Get openapi spec from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            request: Incoming FastAPI request object for context/path/header access.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        openapi_schema = app.openapi()
        base_url = str(request.base_url).rstrip("/")
        openapi_schema["servers"] = [{"url": base_url, "description": "Current server"}]
        return JSONResponse(content=openapi_schema)

    return app


app = create_app()


def main(host: str = "0.0.0.0", port: int = 38000, debug: bool = False) -> None:
    """Run uvicorn server with config defaults and CLI overrides."""
    try:
        server_config = get_server_config()

        if host == "0.0.0.0":
            host = server_config.web_host
        if port == 38000:
            port = server_config.web_port
    except Exception as exc:
        logger.warning("Failed to load server config; falling back to defaults: %s", exc)

    uvicorn.run(
        "shuai_web.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info",
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShuaiTravelAgent Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=38000, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    main(args.host, args.port, args.debug)
