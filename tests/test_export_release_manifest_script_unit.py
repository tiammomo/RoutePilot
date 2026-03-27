"""Unit tests for release manifest export script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.export_release_manifest import export_release_manifest


def test_export_release_manifest_writes_versions_and_images(tmp_path):
    output_path = tmp_path / "release-manifest.json"

    target = export_release_manifest(
        output_path,
        git_sha="abc1234",
        git_ref="v3.3.0",
        registry="ghcr.io",
        owner="tiammomo",
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert target == output_path
    assert payload["source"]["git_sha"] == "abc1234"
    assert payload["source"]["git_ref"] == "v3.3.0"
    assert payload["applications"]["backend"]["version"]
    assert payload["applications"]["frontend"]["version"]
    assert payload["applications"]["backend"]["image"].endswith("/moyuan-travel-agent-backend")
    assert payload["applications"]["frontend"]["image"].endswith("/moyuan-travel-agent-frontend")
    assert payload["quality"]["release_check_command"] == "python scripts/release_harness_scorecard.py --strict"
    assert payload["quality"]["artifacts"]["subagent_scorecard_report"] == "docs/benchmarks/agent_subagent_scorecard_latest.json"
    assert payload["quality"]["artifacts"]["delivery_snapshot"].endswith(
        "travelPlanDeliverySnapshot.test.ts.snap"
    )
