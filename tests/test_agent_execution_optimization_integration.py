from __future__ import annotations

from datetime import datetime

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from agent.src.graph.builder import build_travel_agent
from agent.src.graph.state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state


class _StructuredIntentLLM:
    def __init__(self, schema):
        self._schema = schema

    def invoke(self, _messages):
        return self._schema(
            intent="itinerary",
            confidence=1.0,
            entities={"city": "北京", "days": 3},
            requires_tools=True,
        )


class FakeLLM:
    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _StructuredIntentLLM(schema)

    def invoke(self, _messages):
        return AIMessage(content="ok")


@tool
async def query_attractions(city: str, category: str | None = None) -> str:  # noqa: ARG001
    """Query attractions."""
    import asyncio

    await asyncio.sleep(0.25)
    return f"attractions:{city}"


@tool
async def get_weather(city: str, days: int = 3) -> str:  # noqa: ARG001
    """Get weather."""
    import asyncio

    await asyncio.sleep(0.25)
    return f"weather:{city}:{days}"


@tool
async def plan_itinerary(destination: str, days: int = 3, interests: str | None = None) -> str:  # noqa: ARG001
    """Plan itinerary."""
    import asyncio

    await asyncio.sleep(0.1)
    return f"plan:{destination}:{days}"


@pytest.mark.asyncio
async def test_parallel_steps_have_close_start_times():
    agent = build_travel_agent(
        llm=FakeLLM(),
        tools=[query_attractions, get_weather, plan_itinerary],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="帮我做北京三日行程",
            session_id="parallel-execution-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    stats_steps = result.get("execution_stats", {}).get("steps", [])
    assert len(stats_steps) >= 3

    step_s1 = next(item for item in stats_steps if item.get("step_id") == "s1")
    step_s2 = next(item for item in stats_steps if item.get("step_id") == "s2")
    t1 = datetime.fromisoformat(step_s1["started_at"])
    t2 = datetime.fromisoformat(step_s2["started_at"])
    assert abs((t1 - t2).total_seconds()) < 0.2

    assert result.get("plan_id")
    assert "plan_steps" in (result.get("plan_explanation") or "")
