"""Shared bootstrap helpers for path resolution/import setup."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
AGENT_SRC = PROJECT_ROOT / "agent" / "src"


def ensure_project_paths() -> None:
    """Ensure project and agent source paths are importable.

    Keep agent/src at higher priority than project root for imports like
    `config.config_manager`.
    """
    for path in (str(PROJECT_ROOT), str(AGENT_SRC)):
        if path not in sys.path:
            sys.path.insert(0, path)
