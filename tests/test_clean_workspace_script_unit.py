"""Safety contract for the repository cleanup command."""

from __future__ import annotations

from scripts.clean_workspace import ROOT, targets


def test_cleanup_targets_only_reproducible_workspace_output() -> None:
    relative = {path.relative_to(ROOT).as_posix() for path in targets()}

    assert ".cache" in relative
    assert "artifacts/ci" in relative
    assert "apps/web/.next" in relative
    assert "tsconfig.tsbuildinfo" in relative
    assert not {
        ".env",
        ".env.local",
        ".venv",
        "apps/web/node_modules",
        "data",
        "deploy/compose/.env.v1.local",
    } & relative
