from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.src.graph.builder import (
    TravelAgentGraph,
    _extract_text_from_chunk,
    _resolve_stream_events_version,
)
from agent.src.graph.nodes import AgentNodes, _resolve_parallelism_default


def test_extract_text_from_chunk_supports_content_blocks():
    chunk = SimpleNamespace(content=[{"type": "text", "text": "北"}, {"type": "text", "text": "京"}])
    assert _extract_text_from_chunk(chunk) == "北京"


def test_extract_text_from_chunk_handles_plain_string():
    chunk = SimpleNamespace(content="旅行规划")
    assert _extract_text_from_chunk(chunk) == "旅行规划"


def test_resolve_stream_events_version_fallback_to_v1(monkeypatch):
    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "v3")
    assert _resolve_stream_events_version() == "v1"


def test_intent_structured_output_fallback_chain(monkeypatch):
    class DummyLLM:
        def __init__(self):
            self.methods: list[str] = []

        def bind_tools(self, tools):
            return self

        def with_structured_output(self, schema, method="json_schema"):
            self.methods.append(method)
            if method == "json_schema":
                raise ValueError("json_schema unsupported")
            if method == "function_calling":
                return self
            raise ValueError(f"unsupported method={method}")

    monkeypatch.setenv("AGENT_INTENT_STRUCTURED_METHOD", "json_schema")
    llm = DummyLLM()
    nodes = AgentNodes(llm=llm, tools=[])

    assert nodes.llm_with_intent is llm
    assert llm.methods[:2] == ["json_schema", "function_calling"]


def test_parallelism_default_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "5")
    assert _resolve_parallelism_default() == 5


def test_parallelism_default_invalid_env_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "0")
    assert _resolve_parallelism_default() == 2


def test_travel_agent_astream_events_uses_v2(monkeypatch):
    class DummyCompiledGraph:
        def __init__(self):
            self.version = None

        async def astream_events(self, state, version, config=None):
            self.version = version
            yield {"event": "dummy"}

    dummy_graph = DummyCompiledGraph()
    graph = TravelAgentGraph.__new__(TravelAgentGraph)
    graph._graph = dummy_graph
    graph._build_thread_config = lambda state: {}

    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "v2")

    async def _collect():
        return [event async for event in TravelAgentGraph.astream_events(graph, {"session_id": "s1"})]

    events = asyncio.run(_collect())
    assert dummy_graph.version == "v2"
    assert events == [{"event": "dummy"}]


def test_travel_agent_invoke_falls_back_to_async_invoke():
    class DummyCompiledGraph:
        def __init__(self):
            self.sync_calls = 0
            self.async_calls = 0

        def invoke(self, state, config=None):  # noqa: ARG002
            self.sync_calls += 1
            raise TypeError('No synchronous function provided to "execute".')

        async def ainvoke(self, state, config=None):  # noqa: ARG002
            self.async_calls += 1
            return {"answer": "ok"}

    dummy_graph = DummyCompiledGraph()
    graph = TravelAgentGraph.__new__(TravelAgentGraph)
    graph._graph = dummy_graph
    graph._build_thread_config = lambda state: {}

    result = TravelAgentGraph.invoke(graph, {"session_id": "s1"})
    assert result == {"answer": "ok"}
    assert dummy_graph.sync_calls == 1
    assert dummy_graph.async_calls == 1
