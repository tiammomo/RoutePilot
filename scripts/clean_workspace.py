"""Remove reproducible local build output without touching secrets or user data."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    ".cache",
    ".dev-logs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "apps/web/.next",
    "artifacts/ci",
)
FILES = (
    "apps/web/tsconfig.tsbuildinfo",
    "tsconfig.tsbuildinfo",
)
WALK_EXCLUDES = frozenset({".cache", ".git", ".next", ".venv", "artifacts", "node_modules"})


def targets() -> tuple[Path, ...]:
    """Return only reviewed, reproducible paths inside the repository."""

    fixed = [ROOT / relative for relative in (*DIRECTORIES, *FILES)]
    bytecode: list[Path] = []
    for current, directories, _files in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in WALK_EXCLUDES]
        if Path(current).name == "__pycache__":
            bytecode.append(Path(current))
            directories.clear()
    return tuple(sorted({*fixed, *bytecode}))


def remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the listed paths. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()
    existing = [path for path in targets() if path.exists() or path.is_symlink()]
    failures: list[Path] = []
    for path in existing:
        print(path.relative_to(ROOT))
        if args.apply:
            try:
                remove(path)
            except OSError as error:
                failures.append(path)
                print(f"  unable to remove: {error}")
    action = "removed" if args.apply else "would remove"
    print(f"{action} {len(existing) - len(failures)} reproducible workspace paths")
    print("preserved .env files, .venv, node_modules, PostgreSQL volumes and user data")
    if failures:
        print("some generated files are owned by another user; fix ownership and run again")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
