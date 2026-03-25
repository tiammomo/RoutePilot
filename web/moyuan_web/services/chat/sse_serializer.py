"""SSE serialization helpers for chat stream payloads."""

from __future__ import annotations

import json
from typing import Any, Iterable


class ChatStreamSSESerializer:
    """Serialize normalized chat payloads into public SSE envelopes."""

    @classmethod
    def serialize_payload(cls, payload: dict[str, Any]) -> str:
        """Serialize one normalized payload into an SSE envelope."""
        return cls.sse(payload)

    @classmethod
    def serialize_payloads(cls, payloads: Iterable[dict[str, Any]]) -> list[str]:
        """Serialize a batch of normalized payloads into SSE envelopes."""
        return [cls.serialize_payload(payload) for payload in payloads]

    @staticmethod
    def sse(payload: dict[str, Any]) -> str:
        """Serialize one SSE envelope line from a structured payload object."""
        from ...api.events import validate_chat_stream_payload
        from ...observability import get_request_context, record_sse_event

        context = get_request_context()
        normalized_payload = validate_chat_stream_payload(
            payload,
            request_id=context.get("request_id"),
            trace_id=context.get("trace_id"),
        )
        record_sse_event(str(normalized_payload.get("type", "unknown")))
        return f"data: {json.dumps(normalized_payload, ensure_ascii=False)}\n\n"
