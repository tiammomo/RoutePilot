from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRICS = [
    ("avg_success_rate", "avg_success_rate", "higher"),
    ("avg_tool_hit_rate", "avg_tool_hit_rate", "higher"),
    ("avg_elapsed_ms", "avg_elapsed_ms", "lower"),
    ("fallback_steps_total", "fallback_steps_total", "lower"),
    ("hallucination_rate", "hallucination_rate", "lower"),
]


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _format_delta(current: float, baseline: float) -> str:
    delta = current - baseline
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.4f}"


def _build_aggregate_rows(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    rows = ["| metric | current | baseline | delta | direction |", "|---|---:|---:|---:|---|"]
    current_agg = current.get("aggregate", {}) if isinstance(current, dict) else {}
    baseline_agg = baseline.get("aggregate", {}) if isinstance(baseline, dict) else {}

    for key, label, direction in METRICS:
        if key in {"avg_elapsed_ms", "fallback_steps_total"}:
            cur_val = float(_safe_int(current_agg.get(key, 0)))
            base_val = float(_safe_int(baseline_agg.get(key, 0)))
        else:
            cur_val = _safe_float(current_agg.get(key, 0.0))
            base_val = _safe_float(baseline_agg.get(key, 0.0))
        rows.append(
            f"| {label} | {cur_val:.4f} | {base_val:.4f} | {_format_delta(cur_val, base_val)} | {direction} |"
        )
    return rows


def _build_scenario_rows(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    rows = ["| scenario | current_success | baseline_success | delta_success | current_elapsed_ms | baseline_elapsed_ms | delta_elapsed_ms | current_fallback | baseline_fallback | delta_fallback |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    current_runs = {str(item.get("scenario")): item for item in (current.get("runs", []) or []) if isinstance(item, dict)}
    baseline_runs = {str(item.get("scenario")): item for item in (baseline.get("runs", []) or []) if isinstance(item, dict)}
    scenario_names = sorted(set(current_runs.keys()) | set(baseline_runs.keys()))

    for name in scenario_names:
        cur = current_runs.get(name, {})
        base = baseline_runs.get(name, {})
        cur_success = _safe_float(cur.get("success_rate", 0.0))
        base_success = _safe_float(base.get("success_rate", 0.0))
        cur_elapsed = float(_safe_int(cur.get("elapsed_ms", 0)))
        base_elapsed = float(_safe_int(base.get("elapsed_ms", 0)))
        cur_fallback = float(_safe_int(cur.get("fallback_steps", 0)))
        base_fallback = float(_safe_int(base.get("fallback_steps", 0)))
        rows.append(
            "| {name} | {cur_success:.4f} | {base_success:.4f} | {delta_success} | {cur_elapsed:.0f} | {base_elapsed:.0f} | {delta_elapsed} | {cur_fallback:.0f} | {base_fallback:.0f} | {delta_fallback} |".format(
                name=name,
                cur_success=cur_success,
                base_success=base_success,
                delta_success=_format_delta(cur_success, base_success),
                cur_elapsed=cur_elapsed,
                base_elapsed=base_elapsed,
                delta_elapsed=_format_delta(cur_elapsed, base_elapsed),
                cur_fallback=cur_fallback,
                base_fallback=base_fallback,
                delta_fallback=_format_delta(cur_fallback, base_fallback),
            )
        )
    if not scenario_names:
        rows.append("| n/a | 0.0000 | 0.0000 | +0.0000 | 0 | 0 | +0.0000 | 0 | 0 | +0.0000 |")
    return rows


def build_markdown(
    *,
    current: dict[str, Any],
    baseline: dict[str, Any],
    current_path: Path,
    baseline_path: Path,
    baseline_missing: bool,
) -> str:
    lines = [
        "# Agent Benchmark Trend Report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- current_report: {current_path.as_posix()}",
        f"- baseline_report: {baseline_path.as_posix()}",
        f"- baseline_missing: {str(baseline_missing).lower()}",
        "",
        "## Aggregate Diff",
        "",
    ]
    lines.extend(_build_aggregate_rows(current, baseline))
    lines.extend(
        [
            "",
            "## Scenario Diff",
            "",
        ]
    )
    lines.extend(_build_scenario_rows(current, baseline))
    lines.append("")
    return "\n".join(lines)


def generate_trend_report(current_path: Path, baseline_path: Path, output_path: Path) -> Path:
    current_report = load_report(current_path)
    baseline_missing = not baseline_path.exists()
    baseline_report = load_report(baseline_path) if not baseline_missing else current_report
    markdown = build_markdown(
        current=current_report,
        baseline=baseline_report,
        current_path=current_path,
        baseline_path=baseline_path,
        baseline_missing=baseline_missing,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate trend report for benchmark current vs baseline.")
    parser.add_argument(
        "--current",
        default="docs/benchmarks/agent_benchmark_latest.json",
        help="Current benchmark report JSON path.",
    )
    parser.add_argument(
        "--baseline",
        default="docs/benchmarks/agent_benchmark_baseline.json",
        help="Baseline benchmark report JSON path.",
    )
    parser.add_argument(
        "--output",
        default="docs/benchmarks/agent_benchmark_trend_latest.md",
        help="Output markdown path.",
    )
    args = parser.parse_args()

    output = generate_trend_report(
        current_path=Path(args.current),
        baseline_path=Path(args.baseline),
        output_path=Path(args.output),
    )
    print(f"Benchmark trend report: {output}")


if __name__ == "__main__":
    main()
