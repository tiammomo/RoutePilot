from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.src.graph.builder import build_travel_agent
from agent.src.graph.state import TRAVEL_AGENT_SYSTEM_PROMPT, create_initial_state

TOOL_INTENTS = {"recommend", "attractions", "itinerary", "budget", "tips", "policy"}


@dataclass
class GoldenCase:
    case_id: str
    intent: str
    user_message: str
    entities: dict[str, Any]


class _StructuredIntentLLM:
    def __init__(self, schema, intent: str, entities: dict[str, Any], requires_tools: bool):
        self._schema = schema
        self._intent = intent
        self._entities = entities
        self._requires_tools = requires_tools

    def invoke(self, _messages):
        return self._schema(
            intent=self._intent,
            confidence=1.0,
            entities=self._entities,
            requires_tools=self._requires_tools,
        )


class GoldenLLM:
    def __init__(self, case: GoldenCase):
        self._case = case

    def bind_tools(self, _tools):
        return self

    def with_structured_output(self, schema, method=None):  # noqa: ARG002
        return _StructuredIntentLLM(
            schema=schema,
            intent=self._case.intent,
            entities=self._case.entities,
            requires_tools=self._case.intent in TOOL_INTENTS,
        )

    def invoke(self, _messages):
        return AIMessage(content="golden-ok")


@tool
async def search_cities(query: str) -> dict[str, Any]:
    """Search city."""
    return {"report": f"cities:{query}"}


@tool
async def query_attractions(city: str, category: str | None = None) -> dict[str, Any]:
    """Query attractions."""
    return {"report": f"attractions:{city}:{category or 'all'}"}


@tool
async def query_hotels(city: str, district: str | None = None) -> dict[str, Any]:
    """Query hotels."""
    return {"report": f"hotels:{city}:{district or 'all'}"}


@tool
async def calculate_budget(destination: str, days: int, people: int = 1, accommodation_level: str = "medium") -> dict[str, Any]:
    """Calculate budget."""
    return {"report": f"budget:{destination}:{days}:{people}:{accommodation_level}"}


@tool
async def plan_itinerary(destination: str, days: int, interests: str | None = None) -> dict[str, Any]:
    """Plan itinerary."""
    return {"report": f"plan:{destination}:{days}:{interests or ''}"}


@tool
async def get_travel_tips(destination: str, season: str | None = None) -> dict[str, Any]:
    """Get tips."""
    return {"report": f"tips:{destination}:{season or ''}"}


@tool
async def get_weather(city: str, days: int = 3) -> dict[str, Any]:
    """Get weather."""
    return {"report": f"weather:{city}:{days}"}


TOOLS = [
    search_cities,
    query_attractions,
    query_hotels,
    calculate_budget,
    plan_itinerary,
    get_travel_tips,
    get_weather,
]


def load_cases(path: Path) -> list[GoldenCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldenCase(
            case_id=item["case_id"],
            intent=item["intent"],
            user_message=item["user_message"],
            entities=item.get("entities", {}),
        )
        for item in raw
    ]


async def run_case(case: GoldenCase) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    agent = build_travel_agent(
        llm=GoldenLLM(case),
        tools=TOOLS,
        system_prompt=TRAVEL_AGENT_SYSTEM_PROMPT,
    )
    result = await agent.ainvoke(
        create_initial_state(
            user_message=case.user_message,
            session_id=f"golden-{case.case_id}",
            system_message=TRAVEL_AGENT_SYSTEM_PROMPT,
        )
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    summary = result.get("execution_summary", {}) or {}
    stats_steps = (result.get("execution_stats", {}) or {}).get("steps", [])
    tool_results = result.get("tool_results", {}) or {}
    has_param_error = any(
        isinstance(item, dict) and item.get("error_code") == "PARAM_VALIDATION_ERROR"
        for item in tool_results.values()
    )
    first_token_latency_ms = 0
    if stats_steps:
        first_token_latency_ms = min(int(item.get("duration_ms", 0) or 0) for item in stats_steps)

    hallucination_flag = (
        case.intent in TOOL_INTENTS
        and str(result.get("answer", "")).strip()
        and int(summary.get("success_steps", 0) or 0) == 0
    )
    success = True
    reasons: list[str] = []
    if not str(result.get("answer", "")).strip():
        success = False
        reasons.append("empty_answer")
    if case.intent in TOOL_INTENTS:
        if summary.get("success_steps", 0) < 1:
            success = False
            reasons.append("no_success_steps")
        if has_param_error:
            success = False
            reasons.append("param_validation_error")
    return {
        "case_id": case.case_id,
        "intent": case.intent,
        "success": success,
        "reasons": reasons,
        "first_token_latency_ms": first_token_latency_ms,
        "elapsed_ms": elapsed_ms,
        "tool_hit_rate": summary.get("tool_hit_rate", summary.get("success_rate", 0.0)),
        "hallucination": hallucination_flag,
        "execution_summary": {
            "total_steps": summary.get("total_steps", 0),
            "success_steps": summary.get("success_steps", 0),
            "failed_steps": summary.get("failed_steps", 0),
            "blocked_steps": summary.get("blocked_steps", 0),
        },
    }


async def run_eval(dataset_path: Path) -> dict[str, Any]:
    cases = load_cases(dataset_path)
    results = []
    for case in cases:
        results.append(await run_case(case))
    passed = sum(1 for item in results if item["success"])
    total = len(results)
    pass_rate = (passed / total) if total else 0.0
    avg_first_token_latency_ms = (
        int(sum(int(item.get("first_token_latency_ms", 0) or 0) for item in results) / total) if total else 0
    )
    avg_elapsed_ms = int(sum(int(item.get("elapsed_ms", 0) or 0) for item in results) / total) if total else 0
    avg_tool_hit_rate = (
        round(sum(float(item.get("tool_hit_rate", 0.0) or 0.0) for item in results) / total, 4) if total else 0.0
    )
    hallucination_rate = (
        round(sum(1 for item in results if item.get("hallucination")) / total, 4) if total else 0.0
    )
    intent_aggregate: dict[str, dict[str, Any]] = {}
    for item in results:
        intent = str(item.get("intent") or "unknown")
        bucket = intent_aggregate.setdefault(
            intent,
            {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "avg_elapsed_ms": 0,
                "avg_tool_hit_rate": 0.0,
                "hallucination_rate": 0.0,
                "_elapsed_sum": 0,
                "_tool_hit_sum": 0.0,
                "_hallucination_sum": 0,
            },
        )
        bucket["total"] += 1
        if bool(item.get("success")):
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
        bucket["_elapsed_sum"] += int(item.get("elapsed_ms", 0) or 0)
        bucket["_tool_hit_sum"] += float(item.get("tool_hit_rate", 0.0) or 0.0)
        if bool(item.get("hallucination", False)):
            bucket["_hallucination_sum"] += 1

    for intent, bucket in intent_aggregate.items():
        bucket_total = int(bucket.get("total", 0) or 0)
        bucket["pass_rate"] = round((int(bucket.get("passed", 0) or 0) / bucket_total), 4) if bucket_total else 0.0
        bucket["avg_elapsed_ms"] = int((int(bucket.get("_elapsed_sum", 0) or 0) / bucket_total)) if bucket_total else 0
        bucket["avg_tool_hit_rate"] = (
            round(float(bucket.get("_tool_hit_sum", 0.0) or 0.0) / bucket_total, 4) if bucket_total else 0.0
        )
        bucket["hallucination_rate"] = (
            round(int(bucket.get("_hallucination_sum", 0) or 0) / bucket_total, 4) if bucket_total else 0.0
        )
        bucket.pop("_elapsed_sum", None)
        bucket.pop("_tool_hit_sum", None)
        bucket.pop("_hallucination_sum", None)

    covered_intents = sorted(intent_aggregate.keys())
    return {
        "dataset": str(dataset_path),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "covered_intents": covered_intents,
        "pass_rate": round(pass_rate, 4),
        "avg_first_token_latency_ms": avg_first_token_latency_ms,
        "avg_total_elapsed_ms": avg_elapsed_ms,
        "avg_tool_hit_rate": avg_tool_hit_rate,
        "hallucination_rate": hallucination_rate,
        "intent_aggregate": intent_aggregate,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden evaluation for ReAct agent quality gate.")
    parser.add_argument(
        "--dataset",
        default="tests/golden/agent_react_golden.json",
        help="Path to golden dataset json.",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.96,
        help="Minimal pass rate gate for CI.",
    )
    parser.add_argument(
        "--report",
        default="docs/benchmarks/agent_golden_eval_latest.json",
        help="Output report path.",
    )
    args = parser.parse_args()

    report = asyncio.run(run_eval(Path(args.dataset)))
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Golden eval report: {report_path}")
    print(f"Pass rate: {report['pass_rate']:.4f} (threshold={args.min_pass_rate:.4f})")
    if report["pass_rate"] < args.min_pass_rate:
        print("Golden eval failed quality gate.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
