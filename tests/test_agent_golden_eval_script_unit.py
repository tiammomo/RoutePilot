from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_golden_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "agent_golden_eval.py"
    spec = importlib.util.spec_from_file_location("agent_golden_eval", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_golden_eval_reports_intent_aggregate(tmp_path: Path):
    golden = _load_golden_module()
    dataset = [
        {"case_id": "R01", "intent": "recommend", "user_message": "推荐城市", "entities": {"query": "海边"}},
        {"case_id": "P01", "intent": "policy", "user_message": "签证政策提醒", "entities": {"topic": "签证政策"}},
        {"case_id": "F01", "intent": "fallback", "user_message": "工具超时时怎么降级", "entities": {"scenario": "tool_timeout"}},
    ]
    dataset_path = tmp_path / "golden.json"
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")

    report = await golden.run_eval(dataset_path)
    intent_aggregate = report.get("intent_aggregate", {})
    assert set(intent_aggregate.keys()) == {"recommend", "policy", "fallback"}
    assert report.get("covered_intents") == ["fallback", "policy", "recommend"]
    assert intent_aggregate["recommend"]["total"] == 1
