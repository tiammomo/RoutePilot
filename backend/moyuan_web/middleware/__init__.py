"""Small V1 HTTP safety middleware with no business-layer dependencies."""

from __future__ import annotations

import asyncio
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{2,95}$")


class RequestBoundaryMiddleware(BaseHTTPMiddleware):
    """Attach safe trace IDs, security headers, timeout, and basic abuse limits."""

    def __init__(
        self,
        app,
        *,
        timeout_seconds: float = 30.0,
        rate_limit: int = 300,
        rate_window_seconds: float = 60.0,
    ) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        self.rate_limit = rate_limit
        self.rate_window_seconds = rate_window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @staticmethod
    def _streaming_path(request: Request) -> bool:
        return request.method == "GET" and (
            request.url.path.endswith("/events") or "/a2a/" in request.url.path
        )

    async def _allowed(self, request: Request) -> bool:
        if request.url.path in {"/api/live", "/api/ready", "/api/health"}:
            return True
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.rate_window_seconds
        async with self._lock:
            window = self._requests[key]
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= self.rate_limit:
                return False
            window.append(now)
            return True

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID.fullmatch(supplied) else f"req_{secrets.token_hex(16)}"
        request.state.request_id = request_id
        request.state.trace_id = request_id
        if not await self._allowed(request):
            response: Response = JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests.",
                        "retryable": True,
                        "trace_id": request_id,
                    }
                },
            )
        elif self._streaming_path(request):
            response = await call_next(request)
        else:
            try:
                response = await asyncio.wait_for(
                    call_next(request),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError:
                response = JSONResponse(
                    status_code=504,
                    content={
                        "detail": {
                            "code": "REQUEST_TIMEOUT",
                            "message": "The request exceeded its deadline.",
                            "retryable": True,
                            "trace_id": request_id,
                        }
                    },
                )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def setup_middleware(app: FastAPI) -> None:
    """Install the sole reviewed request boundary."""

    app.add_middleware(RequestBoundaryMiddleware)


__all__ = ["RequestBoundaryMiddleware", "setup_middleware"]
