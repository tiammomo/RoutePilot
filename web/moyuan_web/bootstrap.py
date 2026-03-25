"""Shared bootstrap helpers for path resolution/import setup."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"


def ensure_project_paths() -> None:
    """Ensure project and agent source paths are importable.

    Keep the repository root importable so package imports like
    `agent.travel_agent...` and `config...` remain stable across entrypoints.
    """
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
