"""Unit tests for the dependency-free documentation quality gate."""

from __future__ import annotations

from pathlib import Path

from scripts.check_documentation import (
    REQUIRED_DOCUMENTS,
    check_compose_env_parity,
    check_document_index,
    check_local_links,
    check_required_documents,
)


def _minimum_tree(root: Path) -> None:
    for relative in REQUIRED_DOCUMENTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n", encoding="utf-8")
    index = root / "docs/README.md"
    index.write_text(
        "# Documentation\n\n"
        + "\n".join(
            f"- [Guide]({Path(relative).relative_to('docs').as_posix()})"
            if relative.startswith("docs/")
            else f"- [Guide](../{relative})"
            for relative in REQUIRED_DOCUMENTS
            if relative not in {"README.md", "docs/README.md"}
        )
        + "\n",
        encoding="utf-8",
    )
    compose = root / "deploy/compose"
    compose.mkdir(parents=True, exist_ok=True)
    (compose / "v1.env.example").write_text("ROUTEPILOT_TEST_VALUE=enabled\n", encoding="utf-8")
    (compose / "v1.yaml").write_text("value: ${ROUTEPILOT_TEST_VALUE:-enabled}\n", encoding="utf-8")
    (compose / "v1.preprod.yaml").write_text("services: {}\n", encoding="utf-8")


def test_documentation_gate_accepts_complete_local_tree(tmp_path: Path) -> None:
    _minimum_tree(tmp_path)
    (tmp_path / "README.md").write_text(
        "# RoutePilot\n\n[Documentation](docs/README.md)\n",
        encoding="utf-8",
    )

    assert check_required_documents(tmp_path) == []
    assert check_document_index(tmp_path) == []
    assert check_local_links(tmp_path) == []
    assert check_compose_env_parity(tmp_path) == []


def test_documentation_gate_reports_broken_links_and_unused_env(tmp_path: Path) -> None:
    _minimum_tree(tmp_path)
    (tmp_path / "README.md").write_text("# RoutePilot\n\n[Missing](docs/missing.md)\n", encoding="utf-8")
    (tmp_path / "deploy/compose/v1.env.example").write_text(
        "ROUTEPILOT_UNUSED_VALUE=1\n",
        encoding="utf-8",
    )

    assert any("broken local link" in error for error in check_local_links(tmp_path))
    assert any("ROUTEPILOT_UNUSED_VALUE" in error for error in check_compose_env_parity(tmp_path))


def test_documentation_gate_reports_an_orphaned_required_guide(tmp_path: Path) -> None:
    _minimum_tree(tmp_path)
    (tmp_path / "docs/README.md").write_text("# Documentation\n", encoding="utf-8")

    assert any("is not indexed" in error for error in check_document_index(tmp_path))
