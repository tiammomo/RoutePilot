from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_benchmark_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "agent_benchmark.py"
    spec = importlib.util.spec_from_file_location("agent_benchmark", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_benchmark_script_generates_report_files(tmp_path: Path):
    benchmark = _load_benchmark_module()
    report = await benchmark.run_benchmark()
    json_path, md_path = benchmark.write_report(report, tmp_path)

    assert report.get("aggregate", {}).get("scenario_count") == 5
    assert "avg_elapsed_ms" in report.get("aggregate", {})
    assert "avg_first_token_latency_ms" in report.get("aggregate", {})
    assert all("elapsed_ms" in run for run in report.get("runs", []))
    assert json_path.exists()
    assert md_path.exists()
    md_content = md_path.read_text(encoding="utf-8")
    assert "Agent Benchmark Report" in md_content
    assert "avg_elapsed_ms" in md_content
