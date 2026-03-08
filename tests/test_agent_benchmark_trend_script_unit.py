from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_trend_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "agent_benchmark_trend.py"
    spec = importlib.util.spec_from_file_location("agent_benchmark_trend", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_trend_script_generates_markdown_from_current_and_baseline(tmp_path: Path):
    trend = _load_trend_module()

    current = {
        "aggregate": {
            "avg_success_rate": 0.95,
            "avg_tool_hit_rate": 0.9,
            "avg_elapsed_ms": 120,
            "fallback_steps_total": 2,
            "hallucination_rate": 0.02,
        },
        "runs": [
            {"scenario": "recommend-city", "success_rate": 1.0, "elapsed_ms": 90, "fallback_steps": 0},
            {"scenario": "itinerary-city", "success_rate": 0.8, "elapsed_ms": 150, "fallback_steps": 2},
        ],
    }
    baseline = {
        "aggregate": {
            "avg_success_rate": 0.9,
            "avg_tool_hit_rate": 0.85,
            "avg_elapsed_ms": 140,
            "fallback_steps_total": 3,
            "hallucination_rate": 0.03,
        },
        "runs": [
            {"scenario": "recommend-city", "success_rate": 0.9, "elapsed_ms": 100, "fallback_steps": 1},
            {"scenario": "itinerary-city", "success_rate": 0.75, "elapsed_ms": 160, "fallback_steps": 2},
        ],
    }

    current_path = tmp_path / "current.json"
    baseline_path = tmp_path / "baseline.json"
    output_path = tmp_path / "trend.md"
    current_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    generated = trend.generate_trend_report(current_path, baseline_path, output_path)
    assert generated == output_path
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Agent Benchmark Trend Report" in content
    assert "Aggregate Diff" in content
    assert "Scenario Diff" in content
    assert "recommend-city" in content


def test_trend_script_handles_missing_baseline(tmp_path: Path):
    trend = _load_trend_module()
    current = {
        "aggregate": {
            "avg_success_rate": 1.0,
            "avg_tool_hit_rate": 1.0,
            "avg_elapsed_ms": 100,
            "fallback_steps_total": 0,
            "hallucination_rate": 0.0,
        },
        "runs": [],
    }

    current_path = tmp_path / "current.json"
    output_path = tmp_path / "trend.md"
    current_path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")

    trend.generate_trend_report(current_path, tmp_path / "missing-baseline.json", output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "baseline_missing: true" in content
