"""Export release manifest describing app versions, build context, and image coordinates."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from shuai_web.app_meta import APP_NAME, APP_VERSION


DEFAULT_OUTPUT = ROOT / "artifacts" / "release" / "release-manifest.json"


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _load_frontend_version(project_root: Path) -> str:
    """Load frontend package version from package.json."""
    package_json = project_root / "frontend" / "package.json"
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    return str(payload.get("version") or "unknown")


def export_release_manifest(
    output_path: Path = DEFAULT_OUTPUT,
    *,
    git_sha: str,
    git_ref: str,
    registry: str,
    owner: str,
) -> Path:
    """Write one release manifest that release workflows can upload and publish."""
    owner = owner.strip().lower()
    registry = registry.rstrip("/")
    manifest: dict[str, Any] = {
        "created_at": utc_now_iso(),
        "source": {
            "git_sha": git_sha,
            "git_ref": git_ref,
        },
        "applications": {
            "backend": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "image": f"{registry}/{owner}/shuai-travel-agent-backend",
            },
            "frontend": {
                "name": "shuai-travel-agent-frontend",
                "version": _load_frontend_version(ROOT),
                "image": f"{registry}/{owner}/shuai-travel-agent-frontend",
            },
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for release manifest export utility."""
    parser = argparse.ArgumentParser(description="Export release manifest for ShuaiTravelAgent.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path for the release manifest.")
    parser.add_argument("--git-sha", required=True, help="Git SHA recorded in the release manifest.")
    parser.add_argument("--git-ref", required=True, help="Git ref or tag recorded in the release manifest.")
    parser.add_argument("--registry", default="ghcr.io", help="Container registry host.")
    parser.add_argument("--owner", required=True, help="Container/image owner or namespace.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for release manifest export."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = export_release_manifest(
        Path(args.output),
        git_sha=str(args.git_sha),
        git_ref=str(args.git_ref),
        registry=str(args.registry),
        owner=str(args.owner),
    )
    print(f"Release manifest exported to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
