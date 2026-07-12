"""Contract-test import setup kept independent from application internals."""

from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PACKAGE_SRC = REPOSITORY_ROOT / "packages/python/routepilot_contracts/src"
sys.path.insert(0, str(CONTRACT_PACKAGE_SRC))
