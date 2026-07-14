"""RoutePilot V1 ASGI entrypoint."""

from __future__ import annotations

import argparse
import os

import uvicorn
from fastapi import FastAPI

from .bootstrap_app import create_web_application


def create_app() -> FastAPI:
    return create_web_application()


app = create_app()


def main(host: str | None = None, port: int | None = None, debug: bool = False) -> None:
    uvicorn.run(
        "moyuan_web.main:app",
        host=host or os.getenv("MOYUAN_WEB_HOST") or "0.0.0.0",
        port=port or int(os.getenv("MOYUAN_WEB_PORT", "38083")),
        reload=debug,
        log_level="info",
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoutePilot V1 API")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    main(args.host, args.port, args.debug)
