"""FastAPI entrypoint for ShuaiTravelAgent web API."""

from __future__ import annotations

import argparse
import os
import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shuai_web.app_meta import APP_NAME, APP_VERSION
from shuai_web.bootstrap import ensure_project_paths
from shuai_web.config.runtime import get_model_config_manager, get_server_config
from shuai_web.middleware import RequestLoggingMiddleware, RateLimitMiddleware, TimeoutMiddleware
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

logger = logging.getLogger(__name__)

ensure_project_paths()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=APP_NAME,
        description="AI Travel Assistant API with SSE streaming support.",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Load CORS configuration.
    try:
        config_cors = get_server_config().cors_origins
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

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=100, window=60)
    app.add_middleware(TimeoutMiddleware, timeout=30.0)

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

    @app.get("/")
    async def root() -> dict:
        """Execute root in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            dict: Result value produced by this method.
        """
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "docs": "/docs",
            "rapidoc": "/rapidoc",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        }

    @app.get("/openapi.json", include_in_schema=False)
    async def get_openapi_spec(request: Request):
        """Get openapi spec from current backend context.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            request: Input `request` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
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
