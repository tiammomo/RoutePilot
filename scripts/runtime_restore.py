"""Restore runtime data from a previously created backup archive."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

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

from scripts.runtime_backup import create_runtime_backup
from scripts.runtime_data_utils import DEFAULT_BACKUP_DIR, ensure_relative_path


def _load_manifest(archive_path: Path) -> dict[str, Any]:
    """Read and parse manifest payload from backup archive."""
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        return json.loads(archive.read("manifest.json").decode("utf-8"))


def restore_runtime_backup(
    archive_path: Path,
    project_root: Path = ROOT,
    *,
    create_safety_backup: bool = True,
    safety_output_dir: Path = DEFAULT_BACKUP_DIR,
) -> dict[str, Any]:
    """Restore runtime files from archive and optionally create pre-restore safety backup."""
    if not archive_path.exists():
        raise FileNotFoundError(f"Backup archive does not exist: {archive_path}")

    manifest = _load_manifest(archive_path)
    restored_files: list[str] = []
    safety_archive: str | None = None

    if create_safety_backup:
        backup_path, _ = create_runtime_backup(
            project_root=project_root,
            output_dir=safety_output_dir,
            label="pre-restore",
        )
        safety_archive = str(backup_path)

    with tempfile.TemporaryDirectory(prefix="runtime-restore-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(archive_path, mode="r") as archive:
            archive.extractall(temp_root)

        for item in manifest.get("files", []):
            relative = ensure_relative_path(str(item["relative_path"]))
            source = temp_root / relative
            target = project_root / relative
            if not source.exists():
                raise FileNotFoundError(f"Backup archive is missing declared file: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored_files.append(str(relative).replace("\\", "/"))

    return {
        "archive_path": str(archive_path),
        "safety_archive": safety_archive,
        "restored_files": restored_files,
    }


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for runtime restore utility."""
    parser = argparse.ArgumentParser(description="Restore runtime data from backup archive.")
    parser.add_argument("--archive", required=True, help="Zip archive created by runtime_backup.py.")
    parser.add_argument(
        "--no-safety-backup",
        action="store_true",
        help="Skip automatic pre-restore safety backup.",
    )
    parser.add_argument(
        "--safety-output-dir",
        default=str(DEFAULT_BACKUP_DIR),
        help="Directory used for pre-restore safety backups.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for restoring runtime backup archives."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = restore_runtime_backup(
            archive_path=Path(args.archive),
            project_root=ROOT,
            create_safety_backup=not bool(args.no_safety_backup),
            safety_output_dir=Path(args.safety_output_dir),
        )
    except Exception as exc:
        print(f"Runtime restore failed: {exc}", file=sys.stderr)
        return 1

    print(f"Restored files: {len(result['restored_files'])}")
    if result.get("safety_archive"):
        print(f"Safety backup: {result['safety_archive']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
