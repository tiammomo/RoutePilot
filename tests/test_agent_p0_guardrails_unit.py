from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from agent.src.graph.builder import build_travel_agent
from agent.src.graph.state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state


class _StructuredIntentLLM:
    def __init__(self, schema, intent: str):
        self._schema = schema
        self._intent = intent

    def invoke(self, _messages):
        return self._schema(
            intent=self._intent,
            confidence=1.0,
            entities={},
            requires_tools=True,
        )


class FakeLLM:
    def __init__(self, intent: str):
        self._intent = intent

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _StructuredIntentLLM(schema, self._intent)

    def invoke(self, _messages):
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_step_param_validation_blocks_invalid_invocation():
    calls = {"count": 0}

    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        calls["count"] += 1
        return f"attractions:{city}"

    def broken_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "query_attractions",
                "params": {},
                "description": "broken",
                "depends_on": [],
            }
        ]

    agent = build_travel_agent(
        llm=FakeLLM("attractions"),
        tools=[query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"attractions": broken_plan},
    )

    result = await agent.ainvoke(
        create_initial_state(
            user_message="帮我查景点",
            session_id="validation-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    assert calls["count"] == 0
    tool_result = next(iter(result.get("tool_results", {}).values()))
    assert tool_result["error_code"] == "PARAM_VALIDATION_ERROR"
    assert result["execution_summary"]["failed_steps"] == 1


@pytest.mark.asyncio
async def test_execution_summary_aggregates_step_results():
    @tool
    async def search_cities(query: str) -> str:
        """Search cities."""
        return f"cities:{query}"

    def recommend_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "search_cities",
                "params": {"query": "北京"},
                "description": "ok",
                "depends_on": [],
            },
            {
                "step": 2,
                "step_id": "s2",
                "tool": "not_exists",
                "params": {},
                "description": "fail",
                "depends_on": [],
            },
        ]

    agent = build_travel_agent(
        llm=FakeLLM("recommend"),
        tools=[search_cities],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"recommend": recommend_plan},
    )

    result = await agent.ainvoke(
        create_initial_state(
            user_message="推荐城市",
            session_id="summary-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    summary = result.get("execution_summary", {})
    assert summary.get("total_steps") == 2
    assert summary.get("success_steps") == 1
    assert summary.get("failed_steps") == 1
    assert summary.get("success_rate") == 0.5
    assert summary.get("fallback_rate") == 0.0
    assert summary.get("latency_percentiles_ms", {}).get("p95", 0) >= 0
    assert summary.get("retry_histogram", {}).get("1") == 2
    assert summary.get("error_code_distribution", {}).get("TOOL_NOT_FOUND") == 1
    assert summary["tool_metrics"]["search_cities"]["success"] == 1
    assert summary["tool_metrics"]["not_exists"]["failed"] == 1


@pytest.mark.asyncio
async def test_tool_result_contains_source_metadata_and_fallback():
    @tool
    async def search_cities(query: str) -> str:
        """Search cities."""
        return f"cities:{query}"

    def recommend_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "search_cities",
                "params": {"query": "上海"},
                "description": "ok",
                "depends_on": [],
            },
            {
                "step": 2,
                "step_id": "s2",
                "tool": "not_exists",
                "params": {},
                "description": "missing",
                "depends_on": [],
            },
        ]

    agent = build_travel_agent(
        llm=FakeLLM("recommend"),
        tools=[search_cities],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"recommend": recommend_plan},
    )

    result = await agent.ainvoke(
        create_initial_state(
            user_message="推荐城市",
            session_id="source-meta-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    success_result = result["tool_results"]["s1:search_cities"]
    failed_result = result["tool_results"]["s2:not_exists"]
    assert success_result["source"] == "travel_catalog"
    assert isinstance(success_result.get("fetched_at"), str)
    assert success_result["ttl_seconds"] == 86400
    assert failed_result["fallback_suggestion"] is not None


@pytest.mark.asyncio
async def test_tool_result_meta_overrides_default_source_profile():
    @tool
    async def get_weather(city: str, days: int = 3) -> dict:
        """Get weather."""
        _ = (city, days)
        return {
            "report": "weather ok",
            "_meta": {
                "source": "weather_provider:test-provider",
                "fetched_at": "2026-03-07T12:00:00+00:00",
                "ttl_seconds": 60,
                "is_stale": True,
                "provider_used": "test-provider",
                "provider_chain": ["primary-provider", "test-provider"],
                "fallback_used": True,
            },
        }

    def itinerary_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "get_weather",
                "params": {"city": "北京", "days": 2},
                "description": "weather",
                "depends_on": [],
            }
        ]

    agent = build_travel_agent(
        llm=FakeLLM("itinerary"),
        tools=[get_weather],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"itinerary": itinerary_plan},
    )

    result = await agent.ainvoke(
        create_initial_state(
            user_message="查天气",
            session_id="meta-override-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    tool_result = result["tool_results"]["s1:get_weather"]
    assert tool_result["source"] == "weather_provider:test-provider"
    assert tool_result["fetched_at"] == "2026-03-07T12:00:00+00:00"
    assert tool_result["ttl_seconds"] == 60
    assert tool_result["is_stale"] is True
    assert tool_result["provider_used"] == "test-provider"
    assert tool_result["provider_chain"] == ["primary-provider", "test-provider"]
    assert tool_result["fallback_used"] is True
    assert tool_result["fallback_suggestion"] is not None
    assert result["execution_summary"]["fallback_steps"] == 1
