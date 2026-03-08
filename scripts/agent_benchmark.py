from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.src.graph.builder import build_travel_agent
from agent.src.graph.state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state


@dataclass
class Scenario:
    name: str
    intent: str
    user_message: str


class _StructuredIntentLLM:
    def __init__(self, schema, intent: str):
        self._schema = schema
        self._intent = intent

    def invoke(self, _messages):
        return self._schema(
            intent=self._intent,
            confidence=1.0,
            entities={"city": "北京", "days": 3, "query": "北京"},
            requires_tools=True,
        )


class BenchmarkLLM:
    def __init__(self, intent: str):
        self._intent = intent

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _StructuredIntentLLM(schema, self._intent)

    def invoke(self, _messages):
        return AIMessage(content="benchmark-ok")


@tool
async def search_cities(query: str) -> dict[str, Any]:
    """Search cities for benchmark."""
    return {
        "report": f"cities:{query}",
        "_meta": {
            "source": "benchmark:cities-primary",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 3600,
            "is_stale": False,
            "provider_used": "cities-primary",
            "provider_chain": ["cities-primary", "cities-secondary"],
            "fallback_used": False,
        },
    }


@tool
async def query_attractions(city: str, category: str | None = None) -> dict[str, Any]:
    """Query attractions for benchmark."""
    _ = category
    return {
        "report": f"attractions:{city}",
        "_meta": {
            "source": "benchmark:attractions-primary",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 3600,
            "is_stale": False,
            "provider_used": "attractions-primary",
            "provider_chain": ["attractions-primary", "attractions-secondary"],
            "fallback_used": False,
        },
    }


@tool
async def get_weather(city: str, days: int = 3) -> dict[str, Any]:
    """Get weather for benchmark."""
    return {
        "report": f"weather:{city}:{days}",
        "_meta": {
            "source": "benchmark:weather-fallback",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 1800,
            "is_stale": False,
            "provider_used": "weather-secondary",
            "provider_chain": ["weather-primary", "weather-secondary"],
            "fallback_used": True,
        },
    }


@tool
async def calculate_budget(destination: str, days: int, people: int = 1, accommodation_level: str = "medium") -> dict[str, Any]:
    """Calculate budget for benchmark."""
    return {
        "report": f"budget:{destination}:{days}:{people}:{accommodation_level}",
        "_meta": {
            "source": "benchmark:budget-ruleset",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 86400,
            "is_stale": False,
            "provider_used": "budget-ruleset",
            "provider_chain": ["budget-ruleset"],
            "fallback_used": False,
        },
    }


@tool
async def get_travel_tips(destination: str, season: str | None = None) -> dict[str, Any]:
    """Get travel tips for benchmark."""
    return {
        "report": f"tips:{destination}:{season or ''}",
        "_meta": {
            "source": "benchmark:tips-primary",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": 43200,
            "is_stale": False,
            "provider_used": "tips-primary",
            "provider_chain": ["tips-primary"],
            "fallback_used": False,
        },
    }


async def run_benchmark() -> dict[str, Any]:
    import time

    scenarios = [
        Scenario(name="recommend-city", intent="recommend", user_message="推荐旅行地"),
        Scenario(name="attractions-city", intent="attractions", user_message="北京景点推荐"),
        Scenario(name="itinerary-city", intent="itinerary", user_message="做一个北京三日行程"),
        Scenario(name="budget-city", intent="budget", user_message="北京3天2人预算大概多少"),
        Scenario(name="tips-city", intent="tips", user_message="去北京春季旅行有什么建议"),
    ]

    runs: list[dict[str, Any]] = []
    tools = [search_cities, query_attractions, get_weather, calculate_budget, get_travel_tips]

    for item in scenarios:
        started = time.perf_counter()
        agent = build_travel_agent(
            llm=BenchmarkLLM(item.intent),
            tools=tools,
            system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
        state = create_initial_state(
            user_message=item.user_message,
            session_id=f"bench-{item.name}",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
            run_id=f"bench-{item.name}",
        )
        result = await agent.ainvoke(state)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        summary = result.get("execution_summary", {}) or {}
        steps = (result.get("execution_stats", {}) or {}).get("steps", [])
        first_token_latency_ms = min((int(step.get("duration_ms", 0) or 0) for step in steps), default=0)
        hallucination = bool(result.get("answer")) and int(summary.get("success_steps", 0) or 0) == 0
        runs.append(
            {
                "scenario": item.name,
                "intent": item.intent,
                "success_rate": summary.get("success_rate", 0.0),
                "tool_hit_rate": summary.get("tool_hit_rate", summary.get("success_rate", 0.0)),
                "fallback_steps": summary.get("fallback_steps", 0),
                "avg_duration_ms": summary.get("avg_duration_ms", 0),
                "first_token_latency_ms": first_token_latency_ms,
                "elapsed_ms": elapsed_ms,
                "hallucination": hallucination,
                "latency_percentiles_ms": summary.get("latency_percentiles_ms", {}),
                "error_code_distribution": summary.get("error_code_distribution", {}),
            }
        )

    aggregate = {
        "scenario_count": len(runs),
        "avg_success_rate": round(sum(float(r["success_rate"]) for r in runs) / len(runs), 4) if runs else 0.0,
        "avg_tool_hit_rate": round(sum(float(r["tool_hit_rate"]) for r in runs) / len(runs), 4) if runs else 0.0,
        "avg_duration_ms": int(sum(int(r["avg_duration_ms"]) for r in runs) / len(runs)) if runs else 0,
        "avg_first_token_latency_ms": int(sum(int(r["first_token_latency_ms"]) for r in runs) / len(runs)) if runs else 0,
        "avg_elapsed_ms": int(sum(int(r["elapsed_ms"]) for r in runs) / len(runs)) if runs else 0,
        "hallucination_rate": round(sum(1 for r in runs if r.get("hallucination")) / len(runs), 4) if runs else 0.0,
        "fallback_steps_total": int(sum(int(r["fallback_steps"]) for r in runs)),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregate": aggregate,
        "runs": runs,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "agent_benchmark_latest.json"
    md_path = output_dir / "agent_benchmark_latest.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Agent Benchmark Report",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- scenario_count: {report.get('aggregate', {}).get('scenario_count', 0)}",
        f"- avg_success_rate: {report.get('aggregate', {}).get('avg_success_rate', 0.0)}",
        f"- avg_tool_hit_rate: {report.get('aggregate', {}).get('avg_tool_hit_rate', 0.0)}",
        f"- avg_elapsed_ms: {report.get('aggregate', {}).get('avg_elapsed_ms', 0)}",
        f"- avg_first_token_latency_ms: {report.get('aggregate', {}).get('avg_first_token_latency_ms', 0)}",
        f"- avg_duration_ms: {report.get('aggregate', {}).get('avg_duration_ms', 0)} (step average, auxiliary)",
        f"- hallucination_rate: {report.get('aggregate', {}).get('hallucination_rate', 0.0)}",
        f"- fallback_steps_total: {report.get('aggregate', {}).get('fallback_steps_total', 0)}",
        "",
        "## Runs",
        "",
    ]

    for run in report.get("runs", []):
        lines.append(
                f"- {run.get('scenario')} ({run.get('intent')}): "
                f"success_rate={run.get('success_rate')}, "
                f"tool_hit_rate={run.get('tool_hit_rate')}, "
                f"elapsed_ms={run.get('elapsed_ms')}, "
                f"avg_duration_ms={run.get('avg_duration_ms')}, "
                f"first_token_latency_ms={run.get('first_token_latency_ms')}, "
                f"fallback_steps={run.get('fallback_steps')}"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run synthetic benchmark for travel agent runtime.")
    parser.add_argument(
        "--output-dir",
        default="docs/benchmarks",
        help="Directory for generated benchmark report files.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_benchmark())
    json_path, md_path = write_report(report, Path(args.output_dir))
    print(f"Benchmark JSON report: {json_path}")
    print(f"Benchmark Markdown report: {md_path}")


if __name__ == "__main__":
    main()
