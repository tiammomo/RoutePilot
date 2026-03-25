"""Observability helpers for request context, structured logs, and Prometheus metrics."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar, Token
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

logger = logging.getLogger(__name__)

_request_id_var: ContextVar[str] = ContextVar("moyuan_request_id", default="")
_trace_id_var: ContextVar[str] = ContextVar("moyuan_trace_id", default="")


def _structured_logging_enabled() -> bool:
    """Read structured-logging flag lazily to avoid bootstrap import cycles."""
    try:
        from config import server_config

        return bool(server_config.structured_logging)
    except Exception:
        return True

HTTP_REQUESTS_TOTAL = Counter(
    "moyuan_http_requests_total",
    "HTTP requests handled by the web API.",
    ["method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "moyuan_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)
HTTP_IN_FLIGHT_REQUESTS = Gauge(
    "moyuan_http_in_flight_requests",
    "Current number of in-flight HTTP requests.",
)
CHAT_STREAM_REQUESTS_TOTAL = Counter(
    "moyuan_chat_stream_requests_total",
    "Chat stream requests grouped by mode and outcome.",
    ["mode", "outcome"],
)
RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "moyuan_rate_limit_rejections_total",
    "Rate-limited HTTP requests grouped by route path.",
    ["path"],
)
HTTP_TIMEOUTS_TOTAL = Counter(
    "moyuan_http_timeouts_total",
    "HTTP requests terminated by timeout middleware grouped by route path.",
    ["path"],
)
SSE_EVENTS_TOTAL = Counter(
    "moyuan_sse_events_total",
    "SSE events emitted by chat streaming.",
    ["event_type"],
)
READINESS_STATE = Gauge(
    "moyuan_readiness_state",
    "Readiness state gauge. 1 means ready, 0 means not ready.",
)


def new_request_id(prefix: str = "req") -> str:
    """Generate a short request identifier safe for logs and response headers."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def bind_request_context(request_id: str, trace_id: str | None = None) -> tuple[Token[str], Token[str]]:
    """Bind request-scoped identifiers to context vars for downstream logs and SSE."""
    effective_trace_id = trace_id or request_id
    return _request_id_var.set(request_id), _trace_id_var.set(effective_trace_id)


def reset_request_context(tokens: tuple[Token[str], Token[str]]) -> None:
    """Reset request-scoped context vars after request handling completes."""
    request_token, trace_token = tokens
    _request_id_var.reset(request_token)
    _trace_id_var.reset(trace_token)


def get_request_context() -> dict[str, str]:
    """Return current request and trace identifiers for logs, metrics, and SSE payloads."""
    request_id = _request_id_var.get("")
    trace_id = _trace_id_var.get("")
    return {
        "request_id": request_id,
        "trace_id": trace_id or request_id,
    }


def emit_structured_log(
    target_logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one JSON log line with request context merged into event fields."""
    if not _structured_logging_enabled():
        target_logger.log(level, "%s %s", event, fields)
        return
    payload: dict[str, Any] = {
        "event": event,
        **get_request_context(),
        **fields,
    }
    target_logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))


def record_http_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    """Record Prometheus metrics for one handled HTTP request."""
    status = str(status_code)
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def record_chat_stream(mode: str, outcome: str) -> None:
    """Increment chat-stream outcome counters for monitoring and alerting."""
    CHAT_STREAM_REQUESTS_TOTAL.labels(mode=mode, outcome=outcome).inc()


def record_rate_limit_rejection(path: str) -> None:
    """Increment rate-limit rejection counters for one request path."""
    RATE_LIMIT_REJECTIONS_TOTAL.labels(path=path or "unknown").inc()


def record_http_timeout(path: str) -> None:
    """Increment timeout counters for one request path."""
    HTTP_TIMEOUTS_TOTAL.labels(path=path or "unknown").inc()


def record_sse_event(event_type: str) -> None:
    """Increment SSE event emission counters."""
    SSE_EVENTS_TOTAL.labels(event_type=event_type or "unknown").inc()


def set_readiness_state(is_ready: bool) -> None:
    """Update readiness gauge exposed through Prometheus."""
    READINESS_STATE.set(1 if is_ready else 0)


def metrics_response_payload() -> tuple[bytes, str]:
    """Return Prometheus exposition bytes and the required response content-type."""
    return generate_latest(), CONTENT_TYPE_LATEST


class RequestMetricsTimer:
    """Lightweight helper to track in-flight requests and elapsed duration."""

    def __init__(self) -> None:
        """Start request timer and increment in-flight gauge immediately."""
        self._started_at = time.perf_counter()
        HTTP_IN_FLIGHT_REQUESTS.inc()

    def stop(self) -> float:
        """Stop the timer, decrement in-flight gauge, and return elapsed seconds."""
        elapsed = time.perf_counter() - self._started_at
        HTTP_IN_FLIGHT_REQUESTS.dec()
        return elapsed
