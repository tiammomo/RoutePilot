from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_quality_gate(
    *,
    golden_report: Path,
    benchmark_report: Path,
    baseline_benchmark_report: Path | None,
    min_golden_pass_rate: float,
    max_golden_hallucination_rate: float,
    min_benchmark_success_rate: float,
    max_benchmark_hallucination_rate: float,
    max_benchmark_fallback_steps_total: int,
    max_success_rate_regression: float,
    max_hallucination_rate_regression: float,
    max_fallback_steps_regression: int,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    golden = _load_json(golden_report)
    benchmark = _load_json(benchmark_report)
    benchmark_agg = benchmark.get("aggregate", {}) if isinstance(benchmark, dict) else {}

    golden_pass_rate = _safe_float(golden.get("pass_rate"), 0.0)
    golden_hallucination_rate = _safe_float(golden.get("hallucination_rate"), 1.0)
    benchmark_success_rate = _safe_float(benchmark_agg.get("avg_success_rate"), 0.0)
    benchmark_hallucination_rate = _safe_float(benchmark_agg.get("hallucination_rate"), 1.0)
    benchmark_fallback_steps_total = _safe_int(benchmark_agg.get("fallback_steps_total"), 0)

    if golden_pass_rate < min_golden_pass_rate:
        reasons.append(
            f"golden pass_rate {golden_pass_rate:.4f} < min {min_golden_pass_rate:.4f}"
        )
    if golden_hallucination_rate > max_golden_hallucination_rate:
        reasons.append(
            f"golden hallucination_rate {golden_hallucination_rate:.4f} > max {max_golden_hallucination_rate:.4f}"
        )
    if benchmark_success_rate < min_benchmark_success_rate:
        reasons.append(
            f"benchmark avg_success_rate {benchmark_success_rate:.4f} < min {min_benchmark_success_rate:.4f}"
        )
    if benchmark_hallucination_rate > max_benchmark_hallucination_rate:
        reasons.append(
            f"benchmark hallucination_rate {benchmark_hallucination_rate:.4f} > max {max_benchmark_hallucination_rate:.4f}"
        )
    if benchmark_fallback_steps_total > max_benchmark_fallback_steps_total:
        reasons.append(
            f"benchmark fallback_steps_total {benchmark_fallback_steps_total} > max {max_benchmark_fallback_steps_total}"
        )

    if baseline_benchmark_report and baseline_benchmark_report.exists():
        baseline = _load_json(baseline_benchmark_report)
        baseline_agg = baseline.get("aggregate", {}) if isinstance(baseline, dict) else {}
        baseline_success_rate = _safe_float(baseline_agg.get("avg_success_rate"), 0.0)
        baseline_hallucination_rate = _safe_float(baseline_agg.get("hallucination_rate"), 0.0)
        baseline_fallback_steps_total = _safe_int(baseline_agg.get("fallback_steps_total"), 0)

        if benchmark_success_rate + max_success_rate_regression < baseline_success_rate:
            reasons.append(
                "benchmark avg_success_rate regression exceeded: "
                f"current={benchmark_success_rate:.4f}, baseline={baseline_success_rate:.4f}, "
                f"max_regression={max_success_rate_regression:.4f}"
            )
        if benchmark_hallucination_rate - baseline_hallucination_rate > max_hallucination_rate_regression:
            reasons.append(
                "benchmark hallucination_rate regression exceeded: "
                f"current={benchmark_hallucination_rate:.4f}, baseline={baseline_hallucination_rate:.4f}, "
                f"max_regression={max_hallucination_rate_regression:.4f}"
            )
        if benchmark_fallback_steps_total - baseline_fallback_steps_total > max_fallback_steps_regression:
            reasons.append(
                "benchmark fallback_steps_total regression exceeded: "
                f"current={benchmark_fallback_steps_total}, baseline={baseline_fallback_steps_total}, "
                f"max_regression={max_fallback_steps_regression}"
            )

    return len(reasons) == 0, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality gate for golden/benchmark reports.")
    parser.add_argument(
        "--golden-report",
        default="docs/benchmarks/agent_golden_eval_latest.json",
        help="Golden eval report path.",
    )
    parser.add_argument(
        "--benchmark-report",
        default="docs/benchmarks/agent_benchmark_latest.json",
        help="Benchmark report path.",
    )
    parser.add_argument(
        "--baseline-benchmark-report",
        default="docs/benchmarks/agent_benchmark_baseline.json",
        help="Optional benchmark baseline report path for regression checks.",
    )
    parser.add_argument("--min-golden-pass-rate", type=float, default=0.96)
    parser.add_argument("--max-golden-hallucination-rate", type=float, default=0.05)
    parser.add_argument("--min-benchmark-success-rate", type=float, default=0.6)
    parser.add_argument("--max-benchmark-hallucination-rate", type=float, default=0.05)
    parser.add_argument("--max-benchmark-fallback-steps-total", type=int, default=5)
    parser.add_argument("--max-success-rate-regression", type=float, default=0.05)
    parser.add_argument("--max-hallucination-rate-regression", type=float, default=0.02)
    parser.add_argument("--max-fallback-steps-regression", type=int, default=2)
    args = parser.parse_args()

    passed, reasons = run_quality_gate(
        golden_report=Path(args.golden_report),
        benchmark_report=Path(args.benchmark_report),
        baseline_benchmark_report=Path(args.baseline_benchmark_report),
        min_golden_pass_rate=args.min_golden_pass_rate,
        max_golden_hallucination_rate=args.max_golden_hallucination_rate,
        min_benchmark_success_rate=args.min_benchmark_success_rate,
        max_benchmark_hallucination_rate=args.max_benchmark_hallucination_rate,
        max_benchmark_fallback_steps_total=args.max_benchmark_fallback_steps_total,
        max_success_rate_regression=args.max_success_rate_regression,
        max_hallucination_rate_regression=args.max_hallucination_rate_regression,
        max_fallback_steps_regression=args.max_fallback_steps_regression,
    )
    if passed:
        print("Quality gate passed.")
        return 0

    print("Quality gate failed:")
    for item in reasons:
        print(f"- {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
