#!/usr/bin/env python3
"""
================================================================================
ConfigManager 单元测试

测试配置管理器的核心功能：
- 配置文件加载
- 环境变量替换
- 模型配置获取
- 嵌套配置访问
- 多配置文件分层加载

运行方式:
    PYTHONPATH=agent/src python3 -m pytest agent/tests/test_config_manager.py -v

================================================================================
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from typing import Dict, Any

# 确保 agent/src 在路径中
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "agent" / "src"))

from config.config_manager import ConfigManager


# =============================================================================
# 测试夹具 (Fixtures)
# =============================================================================

@pytest.fixture
def temp_config_dir():
    """创建临时配置目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_llm_config(temp_config_dir):
    """创建示例 LLM 配置文件"""
    config_content = """
default_model: minimax-m2-5

models:
  minimax-m2-5:
    name: "MiniMax M2.5"
    provider: anthropic
    model: "MiniMax-M2.5"
    api_base: "https://api.minimaxi.com/anthropic"
    api_key: "test-api-key"
    temperature: 0.7
    max_tokens: 2000
    timeout: 60
    max_retries: 3

  gpt-4o-mini:
    name: "GPT-4o Mini"
    provider: openai
    model: "gpt-4o-mini"
    api_base: "https://api.openai.com/v1"
    api_key: "sk-test-key"
    temperature: 0.5
    max_tokens: 1000

agent:
  name: "TestAgent"
  max_steps: 5
"""
    config_path = os.path.join(temp_config_dir, "llm_config.yaml")
    with open(config_path, 'w') as f:
        f.write(config_content)
    return config_path


@pytest.fixture
def sample_agent_config(temp_config_dir):
    """创建示例 Agent 配置文件"""
    config_content = """
agent:
  name: "TravelAgent"
  version: "1.0.0"

react:
  max_steps: 10
  max_reasoning_depth: 5

memory:
  working:
    max_size: 10
  short_term:
    max_messages: 20

tools:
  enabled:
    - search_cities
    - query_attractions
"""
    config_path = os.path.join(temp_config_dir, "agent_config.yaml")
    with open(config_path, 'w') as f:
        f.write(config_content)
    return config_path


@pytest.fixture
def sample_infra_config(temp_config_dir):
    """创建示例基础设施配置文件 (v3.x: 简化配置)"""
    config_content = """
# v3.x: 已移除 grpc/redis/milvus 配置，使用内存存储
cache:
  enabled: true
  ttl: 3600

rate_limit:
  enabled: true
  requests_per_minute: 60
"""
    config_path = os.path.join(temp_config_dir, "infrastructure_config.yaml")
    with open(config_path, 'w') as f:
        f.write(config_content)
    return config_path


# =============================================================================
# 测试用例
# =============================================================================

class TestConfigManager:
    """ConfigManager 测试类"""

    def test_load_llm_config(self, sample_llm_config):
        """测试加载 LLM 配置文件"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        assert config_manager.default_model_id == "minimax-m2-5"
        assert "minimax-m2-5" in config_manager.models_config
        assert "gpt-4o-mini" in config_manager.models_config

    def test_get_model_config(self, sample_llm_config):
        """测试获取模型配置"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        model_config = config_manager.get_model_config("minimax-m2-5")
        assert model_config["provider"] == "anthropic"
        assert model_config["model"] == "MiniMax-M2.5"

    def test_get_default_model_config(self, sample_llm_config):
        """测试获取默认模型配置"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        default_config = config_manager.get_default_model_config()
        assert default_config["name"] == "MiniMax M2.5"

    def test_get_nested_config(self, sample_llm_config):
        """测试获取嵌套配置"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        # 使用 get_config 方法
        assert config_manager.get_config("agent.name") == "TestAgent"
        assert config_manager.get_config("nonexistent.key", "default") == "default"

    def test_env_var_replacement(self, temp_config_dir):
        """测试环境变量替换"""
        # 设置环境变量
        os.environ["TEST_API_KEY"] = "env-api-key"

        config_content = """
default_model: test-model

models:
  test-model:
    name: "Test Model"
    provider: openai
    api_key: "${TEST_API_KEY}"
"""
        config_path = os.path.join(temp_config_dir, "test_config.yaml")
        with open(config_path, 'w') as f:
            f.write(config_content)

        config_manager = ConfigManager(config_path, load_additional=False)
        model_config = config_manager.get_model_config("test-model")

        assert model_config["api_key"] == "env-api-key"

        # 清理环境变量
        del os.environ["TEST_API_KEY"]

    def test_load_additional_configs(self, temp_config_dir, sample_llm_config, sample_agent_config):
        """测试加载额外配置文件"""
        config_manager = ConfigManager(sample_llm_config, load_additional=True)

        # 验证 Agent 配置已加载
        agent_config = config_manager.get_agent_config()
        assert "react" in agent_config
        assert agent_config["react"]["max_steps"] == 10

    def test_get_agent_config(self, sample_llm_config, sample_agent_config):
        """测试获取 Agent 详细配置"""
        config_manager = ConfigManager(sample_llm_config, load_additional=True)

        agent_config = config_manager.get_agent_config()
        assert "memory" in agent_config
        assert agent_config["memory"]["working"]["max_size"] == 10

    def test_get_infrastructure_config(self, sample_llm_config, sample_infra_config):
        """测试获取基础设施配置"""
        config_manager = ConfigManager(sample_llm_config, load_additional=True)

        infra_config = config_manager.get_infrastructure_config()
        assert "cache" in infra_config
        assert infra_config["cache"]["enabled"] is True

    def test_travel_knowledge(self, sample_llm_config):
        """测试旅游知识数据"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        # 测试获取城市信息
        city_info = config_manager.get_city_info("北京")
        assert city_info is not None
        assert "region" in city_info
        assert "tags" in city_info

        # 测试搜索城市
        cities = config_manager.search_cities_by_tag("美食")
        assert isinstance(cities, list)

        # 测试获取所有城市
        all_cities = config_manager.get_all_cities()
        assert "北京" in all_cities
        assert "上海" in all_cities


class TestConfigEdgeCases:
    """边界情况测试"""

    def test_missing_config_file(self):
        """测试配置文件不存在"""
        with pytest.raises(FileNotFoundError):
            ConfigManager("nonexistent_config.yaml")

    def test_invalid_model_id(self, sample_llm_config):
        """测试无效的模型 ID"""
        config_manager = ConfigManager(sample_llm_config, load_additional=False)

        with pytest.raises(ValueError):
            config_manager.get_model_config("nonexistent-model")

    def test_empty_models_config(self, temp_config_dir):
        """测试空的模型配置"""
        config_content = """
default_model: test-model
"""
        config_path = os.path.join(temp_config_dir, "empty_config.yaml")
        with open(config_path, 'w') as f:
            f.write(config_content)

        with pytest.raises(ValueError):
            ConfigManager(config_path, load_additional=False)


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
