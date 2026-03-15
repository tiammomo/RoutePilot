"""Unit tests for release manifest export script."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
    assert payload["applications"]["backend"]["image"].endswith("/shuai-travel-agent-backend")
    assert payload["applications"]["frontend"]["image"].endswith("/shuai-travel-agent-frontend")
