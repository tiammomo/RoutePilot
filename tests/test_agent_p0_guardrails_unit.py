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
    async def query_attractions(city: str, keyword: str) -> str:
        """Query attractions."""
        calls["count"] += 1
        return f"attractions:{city}:{keyword}"

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
            user_message="help me query attractions",
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
                "params": {"query": "鍖椾含"},
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
            user_message="鎺ㄨ崘鍩庡競",
            session_id="summary-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    summary = result.get("execution_summary", {})
    assert result.get("validation_status") == "warn"
    assert len(result.get("validation_errors", [])) == 1
    assert result.get("validation_errors", [])[0].get("code") == "TOOL_NOT_REGISTERED"
    assert "s2" in result.get("execution_state", {}).get("blocked", [])
    assert summary.get("total_steps") == 2
    assert summary.get("success_steps") == 1
    assert summary.get("failed_steps") == 0
    assert summary.get("blocked_steps") == 1
    assert summary.get("success_rate") == 0.5
    assert summary.get("fallback_rate") == 0.0
    assert summary.get("latency_percentiles_ms", {}).get("p95", 0) >= 0
    assert summary.get("retry_histogram", {}).get("1") == 2
    assert summary.get("error_code_distribution", {}).get("TOOL_NOT_REGISTERED") == 1
    assert summary["tool_metrics"]["search_cities"]["success"] == 1
    assert summary["tool_metrics"]["not_exists"]["blocked"] == 1


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
                "params": {"query": "涓婃捣"},
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
            user_message="鎺ㄨ崘鍩庡競",
            session_id="source-meta-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    success_result = result["tool_results"]["s1:search_cities"]
    failed_result = result["tool_results"]["s2:not_exists"]
    assert success_result["source"] == "travel_catalog"
    assert isinstance(success_result.get("fetched_at"), str)
    assert success_result["ttl_seconds"] == 86400
    assert failed_result["error_code"] == "TOOL_NOT_REGISTERED"
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
                "params": {"city": "鍖椾含", "days": 2},
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
            user_message="check weather",
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


@pytest.mark.asyncio
async def test_param_auto_correction_fills_missing_city():
    calls = {"city": None, "count": 0}

    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        calls["city"] = city
        calls["count"] += 1
        return f"attractions:{city}"

    def broken_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "query_attractions",
                "params": {},
                "description": "missing city",
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
            user_message="I want Beijing attractions",
            session_id="param-correct-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    assert calls["count"] == 1
    assert calls["city"] in {"北京", "鍖椾含"}
    tool_result = result["tool_results"]["s1:query_attractions"]
    assert tool_result["success"] is True


@pytest.mark.asyncio
async def test_loop_detection_blocks_repeated_same_tool_invocation():
    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        return f"attractions:{city}"

    def loop_plan(_entities: dict) -> list[dict]:
        return [
            {"step": 1, "step_id": "s1", "tool": "query_attractions", "params": {"city": "鍖椾含"}, "description": "1", "depends_on": []},
            {"step": 2, "step_id": "s2", "tool": "query_attractions", "params": {"city": "鍖椾含"}, "description": "2", "depends_on": []},
            {"step": 3, "step_id": "s3", "tool": "query_attractions", "params": {"city": "鍖椾含"}, "description": "3", "depends_on": []},
        ]

    agent = build_travel_agent(
        llm=FakeLLM("itinerary"),
        tools=[query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"itinerary": loop_plan},
    )

    result = await agent.ainvoke(
        create_initial_state(
            user_message="鍋氫釜鍖椾含琛岀▼",
            session_id="loop-detection-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    blocked_steps = result["execution_state"]["blocked"]
    assert "s3" in blocked_steps
    assert result["tool_results"]["s3:query_attractions"]["error_code"] == "LOOP_DETECTED"


@pytest.mark.asyncio
async def test_early_stop_after_terminal_tool_success():
    calls = {"budget": 0, "tips": 0}

    @tool
    async def calculate_budget(destination: str, days: int, people: int = 1, accommodation_level: str = "medium") -> str:  # noqa: ARG001
        """Calculate budget."""
        calls["budget"] += 1
        return "budget-ok"

    @tool
    async def get_travel_tips(destination: str, season: str | None = None) -> str:  # noqa: ARG001
        """Get travel tips."""
        calls["tips"] += 1
        return "tips-ok"

    def budget_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "calculate_budget",
                "params": {"destination": "鍖椾含", "days": 3, "people": 2, "accommodation_level": "medium"},
                "description": "core",
                "depends_on": [],
            },
            {
                "step": 2,
                "step_id": "s2",
                "tool": "get_travel_tips",
                "params": {"destination": "鍖椾含"},
                "description": "optional",
                "depends_on": [],
            },
        ]

    initial = create_initial_state(
        user_message="棰勭畻 3 澶?2 浜?鍖椾含",
        session_id="early-stop-session",
        system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    initial["max_parallelism"] = 1
    initial["parallelism"] = 1

    agent = build_travel_agent(
        llm=FakeLLM("budget"),
        tools=[calculate_budget, get_travel_tips],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"budget": budget_plan},
    )
    result = await agent.ainvoke(initial)

    assert calls["budget"] == 1
    assert calls["tips"] == 0
    assert result.get("early_stop_reason")


@pytest.mark.asyncio
async def test_plan_truncated_by_max_plan_steps(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_PLAN_STEPS", "2")

    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        return f"attractions:{city}"

    def long_plan(_entities: dict) -> list[dict]:
        return [
            {"step": 1, "step_id": "s1", "tool": "query_attractions", "params": {"city": "鍖椾含"}, "description": "1", "depends_on": []},
            {"step": 2, "step_id": "s2", "tool": "query_attractions", "params": {"city": "涓婃捣"}, "description": "2", "depends_on": []},
            {"step": 3, "step_id": "s3", "tool": "query_attractions", "params": {"city": "骞垮窞"}, "description": "3", "depends_on": []},
        ]

    agent = build_travel_agent(
        llm=FakeLLM("itinerary"),
        tools=[query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"itinerary": long_plan},
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="plan a trip",
            session_id="plan-truncate-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    assert len(result.get("plan", [])) == 2


@pytest.mark.asyncio
async def test_high_risk_query_forces_plan_routing():
    @tool
    async def search_cities(query: str) -> str:
        """Search cities."""
        return f"cities:{query}"

    agent = build_travel_agent(
        llm=FakeLLM("general"),
        tools=[search_cities],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    state = create_initial_state(
        user_message="check visa policy and ticket refund rules",
        session_id="risk-routing-session",
        system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    result = await agent.ainvoke(state)
    assert result.get("routing") == "plan"


@pytest.mark.asyncio
async def test_verifier_failed_then_retry_once_then_answer():
    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        return f"attractions:{city}"

    def broken_budget_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "query_attractions",
                "params": {"city": "鍖椾含"},
                "description": "wrong tool for budget",
                "depends_on": [],
            }
        ]

    agent = build_travel_agent(
        llm=FakeLLM("budget"),
        tools=[query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"budget": broken_budget_plan},
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="棰勭畻涓夊ぉ鍖椾含鏃呰",
            session_id="verify-retry-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    verify = result.get("verify_result") or {}
    assert verify.get("passed") is False
    assert result.get("verify_retry_count") == 1
    issue_types = {item.get("issue_type") for item in verify.get("issues", []) if isinstance(item, dict)}
    assert "required_tools_missing" in issue_types


@pytest.mark.asyncio
async def test_orchestrator_round_budget_and_fused_results(monkeypatch):
    monkeypatch.setenv("AGENT_ROUND_MAX_TOOLS", "1")

    @tool
    async def search_cities(query: str) -> dict:
        """Search cities."""
        return {"report": f"cities:{query}"}

    @tool
    async def query_attractions(city: str) -> dict:
        """Query attractions."""
        return {"report": f"attractions:{city}"}

    def recommend_plan(_entities: dict) -> list[dict]:
        return [
            {"step": 1, "step_id": "s1", "tool": "search_cities", "params": {"query": "鍖椾含"}, "description": "cities", "depends_on": []},
            {"step": 2, "step_id": "s2", "tool": "query_attractions", "params": {"city": "鍖椾含"}, "description": "atts", "depends_on": []},
        ]

    agent = build_travel_agent(
        llm=FakeLLM("recommend"),
        tools=[search_cities, query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"recommend": recommend_plan},
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="鎺ㄨ崘鍖椾含",
            session_id="orchestrator-budget-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    blocked_codes = {
        item.get("error_code")
        for item in (result.get("tool_results", {}) or {}).values()
        if isinstance(item, dict) and not item.get("success")
    }
    assert "ROUND_TOOL_BUDGET_EXCEEDED" in blocked_codes
    assert result.get("fused_tool_results") is not None


@pytest.mark.asyncio
async def test_strategy_primary_secondary_and_tool_lists():
    @tool
    async def search_cities(query: str) -> str:
        """Search cities."""
        return f"cities:{query}"

    @tool
    async def calculate_budget(destination: str, days: int, people: int = 1, accommodation_level: str = "medium") -> str:  # noqa: ARG001
        """Calculate budget."""
        return "budget-ok"

    agent = build_travel_agent(
        llm=FakeLLM("itinerary"),
        tools=[search_cities, calculate_budget],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="做一个北京三天行程并给预算",
            session_id="primary-secondary-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    strategy = result.get("strategy_detail") or {}
    assert strategy.get("primary_intent") == "itinerary"
    assert strategy.get("secondary_intent") == "budget"
    assert "plan_itinerary" in strategy.get("required_tools", [])
    assert "calculate_budget" in strategy.get("required_tools", [])
    assert strategy.get("requires_verification") is True


@pytest.mark.asyncio
async def test_high_risk_verify_required_without_verification_returns_nondeterministic_answer():
    @tool
    async def query_attractions(city: str) -> str:
        """Query attractions."""
        return f"attractions:{city}"

    def broken_plan(_entities: dict) -> list[dict]:
        return [
            {
                "step": 1,
                "step_id": "s1",
                "tool": "query_attractions",
                "params": {"city": "北京"},
                "description": "missing required verification tool",
                "depends_on": [],
            }
        ]

    agent = build_travel_agent(
        llm=FakeLLM("budget"),
        tools=[query_attractions],
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        planner_hooks={"budget": broken_plan},
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message="给我北京三天预算价格",
            session_id="verify-required-answer-session",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )

    strategy = result.get("strategy_detail") or {}
    verify = result.get("verify_result") or {}
    answer = str(result.get("answer") or "")
    assert strategy.get("requires_verification") is True
    assert verify.get("passed") is False
    assert "暂定建议而非确定结论" in answer
