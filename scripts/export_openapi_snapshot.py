"""Export stable OpenAPI snapshot for API contract review and regression checks."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from pathlib import Path

if __package__:
    _bootstrap_paths = importlib.import_module(f"{__package__}.bootstrap_paths")
else:
    _bootstrap_paths_path = Path(__file__).with_name("bootstrap_paths.py")
    _bootstrap_paths_spec = importlib.util.spec_from_file_location("bootstrap_paths", _bootstrap_paths_path)
    if _bootstrap_paths_spec is None or _bootstrap_paths_spec.loader is None:
        raise ImportError(f"Unable to load bootstrap_paths from {_bootstrap_paths_path}")
    _bootstrap_paths = importlib.util.module_from_spec(_bootstrap_paths_spec)
    _bootstrap_paths_spec.loader.exec_module(_bootstrap_paths)

ROOT = _bootstrap_paths.PROJECT_ROOT
ensure_project_paths = _bootstrap_paths.ensure_project_paths
ensure_project_paths()

from moyuan_web.main import create_app


DEFAULT_OUTPUT = ROOT / "docs" / "reference" / "openapi.snapshot.json"


def export_openapi_snapshot(output_path: Path = DEFAULT_OUTPUT, *, base_url: str = "http://localhost:38083") -> Path:
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
        default="http://localhost:38083",
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
