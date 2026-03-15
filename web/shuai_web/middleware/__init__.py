"""HTTP middleware for request logging, rate limiting, and timeout control."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ..observability import (
    RequestMetricsTimer,
    bind_request_context,
    emit_structured_log,
    new_request_id,
    record_http_request,
    record_http_timeout,
    record_rate_limit_rejection,
    reset_request_context,
)

logger = logging.getLogger(__name__)


def _default_exclude_paths(metrics_path: str = "/api/metrics") -> list[str]:
    """Return request paths that should not be rate-limited."""
    paths = [
        "/",
        "/docs",
        "/redoc",
        "/rapidoc",
        "/openapi.json",
        "/api/health",
        "/api/health/llm",
        "/api/health/tools",
        "/api/health/tools/intents",
        "/api/ready",
        "/api/live",
        "/api/metrics",
    ]
    if metrics_path and metrics_path not in paths:
        paths.append(metrics_path)
    return paths


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach request IDs, emit structured request logs, and record base metrics."""

    def __init__(self, app: ASGIApp, logger_name: str = "web.request") -> None:
        """Initialize middleware with the logger namespace used for request events."""
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Wrap one request with IDs, logs, latency metrics, and response headers."""
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        trace_id = request.headers.get("X-Trace-ID") or request_id
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        context_tokens = bind_request_context(request_id, trace_id)
        timer = RequestMetricsTimer()

        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        query_params = dict(request.query_params)

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            emit_structured_log(
                self.logger,
                "http_request_failed",
                level=logging.ERROR,
                method=method,
                path=path,
                client_ip=client_ip,
                query_params=query_params,
            )
            reset_request_context(context_tokens)
            raise
        finally:
            duration_seconds = timer.stop()
            record_http_request(method, getattr(request.scope.get("route"), "path", path), status_code, duration_seconds)

        emit_structured_log(
            self.logger,
            "http_request",
            method=method,
            path=path,
            route=getattr(request.scope.get("route"), "path", path),
            status=status_code,
            duration_ms=round(duration_seconds * 1000, 2),
            client_ip=client_ip,
            query_params=query_params,
        )

        response.headers["X-Process-Time"] = f"{duration_seconds * 1000:.2f}ms"
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        reset_request_context(context_tokens)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a simple in-memory sliding-window rate limit to incoming requests."""

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 100,
        window: int = 60,
        key_func: Callable[[Request], str] | None = None,
        exclude_paths: list[str] | None = None,
    ) -> None:
        """Initialize sliding-window rate limiting and its request key strategy."""
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self.key_func = key_func or self._default_key_func
        self.exclude_paths = exclude_paths or _default_exclude_paths()
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def _default_key_func(self, request: Request) -> str:
        """Build the default rate-limit key from the client IP address."""
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, key: str, current_time: float) -> None:
        """Drop request timestamps that no longer belong to the active window."""
        requests = self._requests[key]
        window_start = current_time - self.window
        while requests and requests[0] < window_start:
            requests.popleft()
        if not requests:
            del self._requests[key]

    def _check_rate_limit(self, key: str) -> tuple[bool, int]:
        """Evaluate whether one request is allowed and return remaining quota."""
        current_time = time.time()
        self._clean_old_requests(key, current_time)

        requests = self._requests[key]
        current_count = len(requests)
        remaining = self.max_requests - current_count
        if current_count >= self.max_requests:
            return False, 0
        requests.append(current_time)
        return True, remaining

    def _is_excluded(self, path: str) -> bool:
        """Return whether a request path is exempt from rate limiting."""
        for exclude in self.exclude_paths:
            if exclude == "/":
                if path == "/":
                    return True
                continue
            if path.startswith(exclude):
                return True
        return False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Apply rate limiting, attach rate headers, and emit rejection telemetry."""
        if self._is_excluded(request.url.path):
            return await call_next(request)

        key = self.key_func(request)
        allowed, remaining = self._check_rate_limit(key)

        if not allowed:
            route_path = getattr(request.scope.get("route"), "path", request.url.path)
            record_rate_limit_rejection(route_path)
            emit_structured_log(
                logger,
                "http_request_rate_limited",
                level=logging.WARNING,
                method=request.method,
                path=request.url.path,
                route=route_path,
                key=key,
                max_requests=self.max_requests,
                window_seconds=self.window,
            )
            rate_limit_response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window} seconds.",
                        "details": {
                            "max_requests": self.max_requests,
                            "window_seconds": self.window,
                        },
                    }
                },
            )
            rate_limit_response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            rate_limit_response.headers["X-RateLimit-Remaining"] = "0"
            rate_limit_response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.window))
            if hasattr(request.state, "request_id"):
                rate_limit_response.headers["X-Request-ID"] = request.state.request_id
            if hasattr(request.state, "trace_id"):
                rate_limit_response.headers["X-Trace-ID"] = request.state.trace_id
            return rate_limit_response

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.window))
        return response


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Abort slow requests with a 504 response and track timeout telemetry."""

    def __init__(self, app: ASGIApp, timeout: float = 30.0) -> None:
        """Initialize timeout middleware with the maximum request duration."""
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Abort slow requests with a gateway-timeout response and telemetry."""
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            route_path = getattr(request.scope.get("route"), "path", request.url.path)
            record_http_timeout(route_path)
            emit_structured_log(
                logger,
                "http_request_timeout",
                level=logging.WARNING,
                method=request.method,
                path=request.url.path,
                route=route_path,
                timeout_seconds=self.timeout,
            )
            response = JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": f"Request processing timeout after {self.timeout} seconds",
                    }
                },
            )
            if hasattr(request.state, "request_id"):
                response.headers["X-Request-ID"] = request.state.request_id
            if hasattr(request.state, "trace_id"):
                response.headers["X-Trace-ID"] = request.state.trace_id
            return response


def setup_middleware(app: FastAPI) -> None:
    """Configure middleware using current server configuration when available."""
    try:
        from shuai_web.config.runtime import get_server_config

        server_config = get_server_config()
        max_requests = server_config.rate_limit_max_requests
        window = server_config.rate_limit_window_seconds
        timeout = server_config.request_timeout_seconds
        metrics_path = str(server_config.metrics_path or "/api/metrics")
    except Exception:
        max_requests = 100
        window = 60
        timeout = 30.0
        metrics_path = "/api/metrics"

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        max_requests=max_requests,
        window=window,
        exclude_paths=_default_exclude_paths(metrics_path),
    )
    app.add_middleware(TimeoutMiddleware, timeout=timeout)


__all__ = [
    "RequestLoggingMiddleware",
    "RateLimitMiddleware",
    "TimeoutMiddleware",
    "setup_middleware",
]
