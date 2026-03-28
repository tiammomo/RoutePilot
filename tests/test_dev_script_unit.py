from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_parser_accepts_cross_platform_image_flags():
    dev_module = load_module("test_dev_script_unit_dev", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "compose-up",
            "--python-base-image",
            "python:test",
            "--node-base-image",
            "node:test",
        ]
    )

    assert args.task == "compose-up"
    assert args.python_base_image == "python:test"
    assert args.node_base_image == "node:test"


def test_npm_environment_sets_safe_default():
    dev_module = load_module("test_dev_script_unit_dev_env", "scripts/dev.py")

    env = dev_module.npm_environment()

    assert env["NODE_OPTIONS"] == "--max-old-space-size=4096"


def test_resolve_repo_python_falls_back_to_current_interpreter(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_python", "scripts/dev.py")
    monkeypatch.setattr(dev_module, "REPO_ROOT", PROJECT_ROOT / "tests" / "missing-dev-root")

    assert dev_module.resolve_repo_python() == sys.executable
