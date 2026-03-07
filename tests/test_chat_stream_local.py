"""Local ASGI smoke test for chat streaming route."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from src.dependencies.container import get_container
from src.main import create_app


@pytest.mark.asyncio
async def test_chat_stream_sse_smoke(monkeypatch):
    app = create_app()
    container = get_container()
    service = container.resolve("ChatService")

    async def mock_initialize(self):
        self._initialized = True

    async def mock_stream_agent_events(self, session_id: str, message: str):
        yield {"type": "reasoning", "content": "analyzing"}
        yield {"type": "tool_start", "tool": "search_cities"}
        yield {"type": "tool_end", "tool": "search_cities", "result": "ok"}
        yield {"type": "chunk", "content": "Hello"}
        yield {"type": "chunk", "content": " world"}
        yield {"type": "done", "answer": "Hello world", "tools_used": ["search_cities"]}

    monkeypatch.setattr(type(service), "initialize", mock_initialize, raising=True)
    monkeypatch.setattr(type(service), "_stream_agent_events", mock_stream_agent_events, raising=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "推荐旅行地", "mode": "react"},
        ) as response:
            assert response.status_code == 200

            events = []
            async for line in response.aiter_lines():
                if "data:" in line:
                    for part in line.split("data:"):
                        data = part.strip()
                        if not data or data == "[DONE]":
                            continue

                        decoder = json.JSONDecoder()
                        idx = 0
                        while idx < len(data):
                            while idx < len(data) and data[idx].isspace():
                                idx += 1
                            if idx >= len(data):
                                break
                            try:
                                payload, end = decoder.raw_decode(data, idx)
                            except json.JSONDecodeError:
                                break
                            events.append(payload)
                            idx = end

            event_types = [item.get("type") for item in events]
            assert "session_id" in event_types
            assert "reasoning_start" in event_types
            assert "reasoning_chunk" in event_types
            assert "answer_start" in event_types
            assert "chunk" in event_types
            assert "metadata" in event_types
            assert "done" in event_types

            chunks = [item.get("content", "") for item in events if item.get("type") == "chunk"]
            assert "".join(chunks) == "Hello world"


@pytest.mark.asyncio
async def test_chat_stream_plan_mode_emits_plan_preview(monkeypatch):
    app = create_app()
    container = get_container()
    service = container.resolve("ChatService")

    async def mock_initialize(self):
        self._initialized = True

    async def mock_stream_agent_events(self, session_id: str, message: str):
        yield {"type": "reasoning", "content": "planning"}
        yield {"type": "chunk", "content": "final"}
        yield {"type": "done", "answer": "final", "tools_used": ["search_cities"]}

    def mock_generate_plan_preview(self, session_id: str, message: str):
        return {
            "plan_id": "plan-abc123",
            "intent": "itinerary",
            "plan_explanation": "intent=itinerary, plan_steps=2",
            "plan": [
                {"step": 1, "tool": "query_attractions", "params": {"city": "北京"}},
                {"step": 2, "tool": "plan_itinerary", "params": {"destination": "北京", "days": 3}},
            ],
        }

    monkeypatch.setattr(type(service), "initialize", mock_initialize, raising=True)
    monkeypatch.setattr(type(service), "_stream_agent_events", mock_stream_agent_events, raising=True)
    monkeypatch.setattr(type(service), "_generate_plan_preview", mock_generate_plan_preview, raising=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "做一个北京行程", "mode": "plan"},
        ) as response:
            assert response.status_code == 200

            events = []
            async for line in response.aiter_lines():
                if "data:" not in line:
                    continue
                for part in line.split("data:"):
                    data = part.strip()
                    if not data or data == "[DONE]":
                        continue

                    decoder = json.JSONDecoder()
                    idx = 0
                    while idx < len(data):
                        while idx < len(data) and data[idx].isspace():
                            idx += 1
                        if idx >= len(data):
                            break
                        try:
                            payload, end = decoder.raw_decode(data, idx)
                        except json.JSONDecodeError:
                            break
                        events.append(payload)
                        if payload.get("type") == "done":
                            break
                        idx = end

    event_types = [item.get("type") for item in events]
    assert "plan_preview" in event_types
    plan_event = next(item for item in events if item.get("type") == "plan_preview")
    assert plan_event.get("plan_id") == "plan-abc123"
    assert "plan_steps=2" in plan_event.get("explanation", "")
    assert plan_event.get("intent") == "itinerary"
    assert len(plan_event.get("steps", [])) == 2
