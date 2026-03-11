"""Audit Python docstring coverage for module/class/function definitions.

Usage:
    python scripts/docstring_audit.py
    python scripts/docstring_audit.py --roots agent web scripts --max-output 200
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_ROOTS = ("agent", "web", "scripts")
DEFAULT_EXCLUDE_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


@dataclass(slots=True)
class MissingDocstring:
    """One missing-docstring finding."""

    kind: str
    file_path: str
    line: int
    symbol: str


def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield Python source files under roots while skipping cache/venv folders."""

    for root in roots:
        if not root.exists():
            continue
        for file_path in root.rglob("*.py"):
            if any(part in DEFAULT_EXCLUDE_DIRS for part in file_path.parts):
                continue
            yield file_path


def collect_missing_docstrings(file_path: Path) -> list[MissingDocstring]:
    """Collect missing module/class/function docstrings from a single file."""

    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    missing: list[MissingDocstring] = []

    if ast.get_docstring(tree) is None:
        missing.append(MissingDocstring("module", str(file_path), 1, "<module>"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and ast.get_docstring(node) is None:
            missing.append(MissingDocstring("class", str(file_path), int(node.lineno), node.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node) is None:
            missing.append(MissingDocstring("function", str(file_path), int(node.lineno), node.name))

    return missing


def build_parser() -> argparse.ArgumentParser:
    """Create command-line parser for docstring audit options."""

    parser = argparse.ArgumentParser(description="Audit Python docstring coverage.")
    parser.add_argument("--roots", nargs="*", default=list(DEFAULT_ROOTS), help="Root directories to scan.")
    parser.add_argument(
        "--max-output",
        type=int,
        default=120,
        help="Maximum number of missing entries to print.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when any missing docstring is found.",
    )
    return parser


def main() -> int:
    """Run docstring audit and print a concise report."""

    args = build_parser().parse_args()
    roots = [Path(root) for root in args.roots]

    missing: list[MissingDocstring] = []
    scanned_files = 0

    for file_path in iter_python_files(roots):
        scanned_files += 1
        try:
            missing.extend(collect_missing_docstrings(file_path))
        except SyntaxError as exc:
            missing.append(MissingDocstring("syntax_error", str(file_path), int(exc.lineno or 1), exc.msg))
        except UnicodeDecodeError as exc:
            missing.append(MissingDocstring("decode_error", str(file_path), 1, str(exc)))

    module_missing = sum(1 for item in missing if item.kind == "module")
    class_missing = sum(1 for item in missing if item.kind == "class")
    function_missing = sum(1 for item in missing if item.kind == "function")
    other_missing = len(missing) - module_missing - class_missing - function_missing

    print(f"scanned_files={scanned_files}")
    print(
        "missing_counts "
        f"module={module_missing} class={class_missing} function={function_missing} other={other_missing} total={len(missing)}"
    )

    if missing:
        print("sample_findings:")
        for item in missing[: max(0, args.max_output)]:
            print(f"{item.kind}|{item.file_path}:{item.line}|{item.symbol}")

    if args.strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

