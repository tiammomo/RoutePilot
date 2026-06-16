"""FastAPI entrypoint for moyuan-travel-agent web API."""

from __future__ import annotations

import argparse
import logging

import uvicorn

from moyuan_web.bootstrap_app import create_web_application
from moyuan_web.config.runtime import get_server_config

logger = logging.getLogger(__name__)

def create_app():
    """Create the FastAPI application via the shared bootstrap helper."""
    return create_web_application()


app = create_app()


def main(host: str = "0.0.0.0", port: int = 38083, debug: bool = False) -> None:
    """Run uvicorn server with config defaults and CLI overrides."""
    try:
        server_config = get_server_config()

        if host == "0.0.0.0":
            host = server_config.web_host
        if port == 38083:
            port = server_config.web_port
    except Exception as exc:
        logger.warning("Failed to load server config; falling back to defaults: %s", exc)

    uvicorn.run(
        "moyuan_web.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info",
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="moyuan-travel-agent Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=38083, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    main(args.host, args.port, args.debug)
