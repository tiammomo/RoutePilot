"""Validate RoutePilot documentation links, coverage, and Compose env parity."""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = frozenset(
    {".git", ".next", ".venv", "artifacts", "node_modules", "__pycache__"}
)
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
ENV_NAME = re.compile(r"^(ROUTEPILOT_[A-Z0-9_]+)=", re.MULTILINE)
REQUIRED_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/product/user-guide.md",
    "docs/development/local-development.md",
    "docs/development/api-guide.md",
    "docs/development/agent-extension.md",
    "docs/development/artifact-contracts.md",
    "docs/development/provider-extension.md",
    "docs/operations/v1-platform.md",
    "docs/operations/rag-ingestion.md",
    "docs/operations/knowledge-base-maintenance.md",
    "docs/operations/troubleshooting.md",
    "docs/operations/observability.md",
    "docs/operations/backup-restore.md",
)


def documentation_files(root: Path) -> list[Path]:
    """Return repository Markdown while pruning generated and local dependency trees."""

    return sorted(
        path
        for path in root.rglob("*.md")
        if not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
    )


def check_required_documents(root: Path) -> list[str]:
    """Require the minimum user, developer, and operator documentation set."""

    return [f"missing required document: {path}" for path in REQUIRED_DOCUMENTS if not (root / path).is_file()]


def check_document_index(root: Path) -> list[str]:
    """Ensure the central index makes every required non-root guide discoverable."""

    index_path = root / "docs/README.md"
    if not index_path.is_file():
        return []
    index = index_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for relative in REQUIRED_DOCUMENTS:
        if relative in {"README.md", "docs/README.md"}:
            continue
        target = Path(os.path.relpath(root / relative, index_path.parent)).as_posix()
        if f"]({target})" not in index:
            errors.append(f"docs/README.md: required document is not indexed: {relative}")
    return errors


def _local_link_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    target = target.split(maxsplit=1)[0]
    if not target or target.startswith("#"):
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("//"):
        return None
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def check_local_links(root: Path) -> list[str]:
    """Reject broken, absolute, or repository-escaping local Markdown links."""

    errors: list[str] = []
    resolved_root = root.resolve()
    for document in documentation_files(root):
        content = document.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in MARKDOWN_LINK.finditer(line):
                target = _local_link_target(match.group(1))
                if target is None:
                    continue
                if target.startswith("/"):
                    errors.append(f"{document.relative_to(root)}:{line_number}: local link must be relative: {target}")
                    continue
                resolved = (document.parent / target).resolve()
                if not resolved.is_relative_to(resolved_root):
                    errors.append(f"{document.relative_to(root)}:{line_number}: link escapes repository: {target}")
                elif not resolved.exists():
                    errors.append(f"{document.relative_to(root)}:{line_number}: broken local link: {target}")
    return errors


def check_compose_env_parity(root: Path) -> list[str]:
    """Ensure every committed V1 env knob is actually interpolated by Compose."""

    example_path = root / "deploy/compose/v1.env.example"
    compose_paths = (root / "deploy/compose/v1.yaml", root / "deploy/compose/v1.preprod.yaml")
    if not example_path.is_file() or any(not path.is_file() for path in compose_paths):
        return ["Compose env parity inputs are missing"]
    names = sorted(set(ENV_NAME.findall(example_path.read_text(encoding="utf-8"))))
    compose = "\n".join(path.read_text(encoding="utf-8") for path in compose_paths)
    return [
        f"deploy/compose/v1.env.example: variable is not interpolated by Compose: {name}"
        for name in names
        if f"${{{name}" not in compose
    ]


def validate_documentation(root: Path = REPOSITORY_ROOT) -> list[str]:
    """Return all deterministic documentation failures."""

    return [
        *check_required_documents(root),
        *check_document_index(root),
        *check_local_links(root),
        *check_compose_env_parity(root),
    ]


def main() -> int:
    errors = validate_documentation()
    if errors:
        for error in errors:
            print(f"[docs] {error}", file=sys.stderr)
        return 1
    print("[docs] required coverage, local links, and Compose env parity verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
