"""
Model Manager - 模型管理器

统一管理 LLM 模型配置，支持模型切换、配置验证和状态检查。

主要功能:
- 模型配置加载和验证
- 模型切换和激活
- 模型状态检查
- 配置热更新

使用示例:
    from llm.manager import ModelManager

    manager = ModelManager('config/llm_config.yaml')
    models = manager.list_models()
    manager.switch_model('minimax-m2-5')
    config = manager.get_active_config()
"""

import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """模型状态枚举"""
    AVAILABLE = "available"      # 可用
    LOADING = "loading"          # 加载中
    ERROR = "error"              # 错误
    DISABLED = "disabled"        # 禁用


@dataclass
class ModelInfo:
    """模型信息数据类"""
    model_id: str
    name: str
    provider: str
    status: ModelStatus = ModelStatus.AVAILABLE
    last_check: Optional[str] = None
    error_message: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "provider": self.provider,
            "status": self.status.value,
            "last_check": self.last_check,
            "error_message": self.error_message,
            "config": self.config
        }


class ModelConfigValidator:
    """模型配置验证器"""

    # 必填字段
    REQUIRED_FIELDS = ['model', 'api_key']

    # 协议类型验证规则
    PROVIDER_RULES = {
        'openai': ['api_base', 'model'],
        'anthropic': ['api_base', 'model', 'api_version'],
        'google': ['api_base', 'model'],
        'ollama': ['api_base', 'model'],
        'openai-compatible': ['api_base', 'model']
    }

    @classmethod
    def validate(cls, config: Dict[str, Any], model_id: str) -> tuple[bool, List[str]]:
        """
        验证模型配置

        Args:
            config: 模型配置字典
            model_id: 模型ID

        Returns:
            (是否有效, 错误列表)
        """
        errors = []

        # 检查必填字段
        for field in cls.REQUIRED_FIELDS:
            if field not in config or not config.get(field):
                errors.append(f"缺少必填字段: {field}")

        # 检查协议特定字段
        provider = config.get('provider', '').lower()
        if provider in cls.PROVIDER_RULES:
            for field in cls.PROVIDER_RULES[provider]:
                if field not in config:
                    errors.append(f" provider={provider} 缺少字段: {field}")

        # 验证 API base URL 格式
        api_base = config.get('api_base', '')
        if api_base and not api_base.startswith(('http://', 'https://')):
            errors.append(f"api_base 格式无效: {api_base}")

        return len(errors) == 0, errors


class ModelManager:
    """
    模型管理器

    统一管理所有 LLM 模型的配置和状态。

    功能特点:
    - 支持动态加载和更新模型配置
    - 模型切换无需重启服务
    - 线程安全的配置访问
    - 自动验证配置有效性
    """

    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """
        初始化模型管理器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._lock = threading.RLock()
        self._models: Dict[str, ModelInfo] = {}
        self._active_model_id: Optional[str] = None
        self._config: Dict[str, Any] = {}
        self._callbacks: List[Callable] = []  # 模型变更回调

        # 加载配置
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.error(f"配置文件不存在: {self.config_path}")
                return

            with open(config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}

            # 解析模型配置
            self._parse_model_configs()

            # 设置默认模型
            default_model = self._config.get('default_model')
            if default_model and default_model in self._models:
                self._active_model_id = default_model

            logger.info(f"已加载 {len(self._models)} 个模型配置")
            logger.info(f"默认模型: {self._active_model_id}")

        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self._config = {}

    def _parse_model_configs(self):
        """解析模型配置"""
        models_config = self._config.get('models', {})
        for model_id, config in models_config.items():
            if not isinstance(config, dict):
                continue

            # 验证配置
            is_valid, errors = ModelConfigValidator.validate(config, model_id)
            status = ModelStatus.AVAILABLE if is_valid else ModelStatus.ERROR

            model_info = ModelInfo(
                model_id=model_id,
                name=config.get('name', model_id),
                provider=config.get('provider', ''),
                status=status,
                config=config
            )

            if not is_valid:
                model_info.error_message = '; '.join(errors)
                logger.warning(f"模型 {model_id} 配置无效: {errors}")

            self._models[model_id] = model_info

    def list_models(self) -> List[ModelInfo]:
        """列出所有模型"""
        with self._lock:
            return list(self._models.values())

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """获取指定模型信息"""
        with self._lock:
            return self._models.get(model_id)

    def get_active_model(self) -> Optional[ModelInfo]:
        """获取当前激活的模型"""
        with self._lock:
            if self._active_model_id:
                return self._models.get(self._active_model_id)
            return None

    def get_active_config(self) -> Optional[Dict[str, Any]]:
        """获取当前激活模型的配置"""
        model = self.get_active_model()
        return model.config if model else None

    def switch_model(self, model_id: str) -> bool:
        """
        切换激活的模型

        Args:
            model_id: 要切换的模型ID

        Returns:
            是否切换成功
        """
        with self._lock:
            if model_id not in self._models:
                logger.error(f"模型不存在: {model_id}")
                return False

            if self._models[model_id].status != ModelStatus.AVAILABLE:
                logger.error(f"模型不可用: {model_id}")
                return False

            old_model_id = self._active_model_id
            self._active_model_id = model_id
            logger.info(f"模型切换: {old_model_id} -> {model_id}")

            # 触发回调
            self._notify_callbacks(old_model_id, model_id)

            return True

    def add_model(self, model_id: str, config: Dict[str, Any]) -> bool:
        """
        添加新模型配置

        Args:
            model_id: 模型ID
            config: 模型配置

        Returns:
            是否添加成功
        """
        with self._lock:
            # 验证配置
            is_valid, errors = ModelConfigValidator.validate(config, model_id)
            if not is_valid:
                logger.error(f"模型配置无效: {errors}")
                return False

            model_info = ModelInfo(
                model_id=model_id,
                name=config.get('name', model_id),
                provider=config.get('provider', ''),
                status=ModelStatus.AVAILABLE,
                config=config
            )

            self._models[model_id] = model_info
            logger.info(f"添加模型: {model_id}")

            return True

    def remove_model(self, model_id: str) -> bool:
        """
        移除模型配置

        Args:
            model_id: 模型ID

        Returns:
            是否移除成功
        """
        with self._lock:
            if model_id == self._active_model_id:
                logger.error("不能移除当前激活的模型")
                return False

            if model_id in self._models:
                del self._models[model_id]
                logger.info(f"移除模型: {model_id}")
                return True

            return False

    def check_model_status(self, model_id: str) -> ModelStatus:
        """
        检查模型状态

        Args:
            model_id: 模型ID

        Returns:
            模型状态
        """
        model = self.get_model(model_id)
        if not model:
            return ModelStatus.ERROR

        # TODO: 实际检查模型可用性
        return model.status

    def on_model_change(self, callback: Callable):
        """
        注册模型变更回调

        Args:
            callback: 回调函数，参数: (old_model_id, new_model_id)
        """
        with self._lock:
            self._callbacks.append(callback)

    def _notify_callbacks(self, old_model_id: Optional[str], new_model_id: Optional[str]):
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                callback(old_model_id, new_model_id)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        with self._lock:
            return self._config.copy()

    def reload(self) -> bool:
        """
        重新加载配置

        Returns:
            是否加载成功
        """
        old_active = self._active_model_id
        self._models.clear()
        self._active_model_id = None
        self._load_config()

        # 尝试恢复之前的激活模型
        if old_active and old_active in self._models:
            self._active_model_id = old_active

        return len(self._models) > 0
