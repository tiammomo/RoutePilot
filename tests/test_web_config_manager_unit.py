"""Unit tests for the web-layer model configuration manager."""

from __future__ import annotations

import pytest

from moyuan_web.config.config_manager import ConfigManager


def test_config_manager_loads_yaml_with_env_substitution_and_filters_active_models(tmp_path, monkeypatch):
    config_path = tmp_path / "llm_config.yaml"
    config_path.write_text(
        """
default_model: demo-model
models:
  demo-model:
    name: Demo
    provider: openai
    model: demo-model
    api_key: ${DEMO_API_KEY}
  placeholder-model:
    name: Placeholder
    provider: openai
    model: placeholder-model
    api_key: sk-YOUR_PLACEHOLDER
  replace-model:
    name: Replace Me
    provider: anthropic-compatible
    model: replace-model
    api_key: sk-cp-your-minimax-token
  blank-model:
    name: Blank
    provider: openai
    model: blank-model
    api_key: ""
travel_knowledge:
  cities:
    hangzhou:
      region: east
agent:
  name: DemoAgent
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEMO_API_KEY", "sk-demo")

    manager = ConfigManager(str(config_path))

    assert manager.get_default_model_id() == "demo-model"
    assert manager.get_model_config("demo-model")["provider"] == "openai"
    assert manager.get_config("agent.name") == "DemoAgent"
    assert manager.get_city_info("hangzhou") == {"region": "east"}
    assert manager.get_all_cities() == ["hangzhou"]
    assert manager.get_available_models() == [
        {
            "model_id": "demo-model",
            "name": "Demo",
            "provider": "openai",
            "model": "demo-model",
        }
    ]


def test_config_manager_raises_when_model_config_file_is_missing(tmp_path):
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError):
        ConfigManager(str(missing_path))
