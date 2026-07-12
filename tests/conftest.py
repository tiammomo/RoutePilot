"""Shared path bootstrap and stable markers for the clean V1 test suite."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def pytest_collection_modifyitems(config, items) -> None:
    """Classify explicit stateful suites without filename registries."""

    del config
    for item in items:
        name = Path(str(item.fspath)).name
        if "integration" in name or "e2e" in name:
            item.add_marker("integration")
        else:
            item.add_marker("unit")
