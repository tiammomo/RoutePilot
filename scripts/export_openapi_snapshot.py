"""Export stable OpenAPI snapshot for API contract review and regression checks."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.main import create_app


DEFAULT_OUTPUT = ROOT / "docs" / "reference" / "openapi.snapshot.json"


def export_openapi_snapshot(output_path: Path = DEFAULT_OUTPUT, *, base_url: str = "http://localhost:38000") -> Path:
    """Render current FastAPI OpenAPI schema into a stable, sorted JSON snapshot file."""
    app = create_app()
    schema = app.openapi()
    schema["servers"] = [{"url": base_url, "description": "Snapshot server"}]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for OpenAPI snapshot export utility."""
    parser = argparse.ArgumentParser(description="Export current OpenAPI schema snapshot.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output path for exported OpenAPI snapshot.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:38000",
        help="Server URL written into the snapshot schema.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for exporting OpenAPI snapshot."""
    parser = build_parser()
    args = parser.parse_args(argv)
    target = export_openapi_snapshot(Path(args.output), base_url=str(args.base_url))
    print(f"OpenAPI snapshot exported to: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
