from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_quality_gate_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "agent_quality_gate.py"
    spec = importlib.util.spec_from_file_location("agent_quality_gate", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_quality_gate_passes_with_healthy_reports(tmp_path: Path):
    gate = _load_quality_gate_module()
    golden = {"pass_rate": 0.98, "hallucination_rate": 0.0}
    benchmark = {
        "aggregate": {
            "avg_success_rate": 0.75,
            "hallucination_rate": 0.0,
            "fallback_steps_total": 2,
        }
    }
    baseline = {
        "aggregate": {
            "avg_success_rate": 0.74,
            "hallucination_rate": 0.0,
            "fallback_steps_total": 1,
        }
    }
    golden_path = tmp_path / "golden.json"
    benchmark_path = tmp_path / "benchmark.json"
    baseline_path = tmp_path / "baseline.json"
    _write_json(golden_path, golden)
    _write_json(benchmark_path, benchmark)
    _write_json(baseline_path, baseline)

    passed, reasons = gate.run_quality_gate(
        golden_report=golden_path,
        benchmark_report=benchmark_path,
        baseline_benchmark_report=baseline_path,
        min_golden_pass_rate=0.96,
        max_golden_hallucination_rate=0.05,
        min_benchmark_success_rate=0.6,
        max_benchmark_hallucination_rate=0.05,
        max_benchmark_fallback_steps_total=5,
        max_success_rate_regression=0.05,
        max_hallucination_rate_regression=0.02,
        max_fallback_steps_regression=2,
    )
    assert passed is True
    assert reasons == []


def test_quality_gate_fails_on_threshold_violations(tmp_path: Path):
    gate = _load_quality_gate_module()
    golden = {"pass_rate": 0.9, "hallucination_rate": 0.1}
    benchmark = {
        "aggregate": {
            "avg_success_rate": 0.4,
            "hallucination_rate": 0.2,
            "fallback_steps_total": 9,
        }
    }
    golden_path = tmp_path / "golden.json"
    benchmark_path = tmp_path / "benchmark.json"
    _write_json(golden_path, golden)
    _write_json(benchmark_path, benchmark)

    passed, reasons = gate.run_quality_gate(
        golden_report=golden_path,
        benchmark_report=benchmark_path,
        baseline_benchmark_report=tmp_path / "missing-baseline.json",
        min_golden_pass_rate=0.96,
        max_golden_hallucination_rate=0.05,
        min_benchmark_success_rate=0.6,
        max_benchmark_hallucination_rate=0.05,
        max_benchmark_fallback_steps_total=5,
        max_success_rate_regression=0.05,
        max_hallucination_rate_regression=0.02,
        max_fallback_steps_regression=2,
    )
    assert passed is False
    assert any("golden pass_rate" in item for item in reasons)
    assert any("benchmark avg_success_rate" in item for item in reasons)
