from __future__ import annotations

import importlib.util
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


def test_ensure_config_from_example_creates_missing_file(tmp_path, monkeypatch):
    bootstrap_module = load_module(
        "test_bootstrap_script_unit_module", "scripts/bootstrap.py"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    example_path = config_dir / "llm_config.yaml.example"
    example_path.write_text("model: test\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap_module, "REPO_ROOT", tmp_path)

    bootstrap_module.ensure_config_from_example("llm_config.yaml")

    assert (config_dir / "llm_config.yaml").read_text(encoding="utf-8") == "model: test\n"


def test_current_venv_version_returns_none_when_python_missing(tmp_path):
    bootstrap_module = load_module(
        "test_bootstrap_script_unit_missing_python", "scripts/bootstrap.py"
    )

    assert bootstrap_module.current_venv_version(tmp_path / "missing-python") is None
