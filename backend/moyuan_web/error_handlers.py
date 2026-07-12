"""Fail-closed public exception projection for the RoutePilot V1 API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _problem(detail: Any, request: Request) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "code": "HTTP_ERROR",
        "message": "The request could not be completed.",
        "retryable": False,
    }
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        retryable = detail.get("retryable")
        if isinstance(code, str) and isinstance(message, str) and isinstance(retryable, bool):
            projected.update(
                code=code[:96],
                message=message[:2_000],
                retryable=retryable,
            )
            for field in ("current_version", "current_status"):
                value = detail.get(field)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    projected[field] = value
    trace_id = getattr(request.state, "trace_id", None)
    if isinstance(trace_id, str):
        projected["trace_id"] = trace_id
    return projected


def register_exception_handlers(app: FastAPI) -> None:
    """Attach V1-only handlers that never reflect raw input or exception text."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        fields = [
            ".".join(str(part) for part in entry.get("loc", ()) if part != "__root__")
            for entry in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "INVALID_REQUEST",
                    "message": "One or more request fields are invalid.",
                    "retryable": False,
                    "fields": [field for field in fields if field][:50],
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _problem(exc.detail, request)},
            headers={**(exc.headers or {}), "Cache-Control": "no-store"},
        )

    @app.exception_handler(Exception)
    async def internal_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled API exception type=%s trace_id=%s",
            type(exc).__name__,
            getattr(request.state, "trace_id", "unknown"),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "The service could not complete the request.",
                    "retryable": True,
                    "trace_id": getattr(request.state, "trace_id", ""),
                }
            },
            headers={"Cache-Control": "no-store"},
        )


__all__ = ["register_exception_handlers"]
