"""
================================================================================
配置热更新模块 (Configuration Hot-Reload)

提供配置热加载功能，支持：
- Nacos 配置中心集成
- 本地配置文件监听
- 配置变化自动重载
- 多环境配置切换

使用示例:
```python
from infrastructure.config_hot_reload import ConfigHotReload, get_config_reloader

# 创建配置热重载器
reloader = await get_config_reloader()

# 获取配置
config = reloader.get("app")

# 监听配置变化
reloader.on_change("app", lambda key, value: print(f"配置变化: {key}"))

# 手动刷新配置
await reloader.reload("app")
```

================================================================================
"""

import asyncio
import json
import logging
import os
import re
import yaml
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigSource(Enum):
    """配置来源"""
    NACOS = "nacos"
    LOCAL = "local"
    MEMORY = "memory"


@dataclass
class ConfigItem:
    """配置项"""
    key: str
    value: Any
    source: ConfigSource
    data_id: Optional[str] = None
    last_updated: Optional[datetime] = None
    version: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source.value,
            "data_id": self.data_id,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "version": self.version
        }


@dataclass
class ConfigReloadPolicy:
    """配置重载策略"""
    enable_hot_reload: bool = True
    reload_interval: int = 30  # 秒
    max_retries: int = 3
    retry_interval: int = 5
    validate_on_reload: bool = True
    backup_before_reload: bool = True


class ConfigHotReload:
    """
    配置热重载管理器

    提供配置的集中管理、热加载、变化通知等功能。
    支持 Nacos 和本地配置两种模式。
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        policy: Optional[ConfigReloadPolicy] = None
    ):
        """
        初始化配置热重载管理器

        Args:
            config_path: 配置文件路径
            policy: 重载策略
        """
        self.config_path = config_path
        self.policy = policy or ConfigReloadPolicy()

        # 配置存储
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._config_items: Dict[str, ConfigItem] = {}

        # 监听器
        self._listeners: Dict[str, Set[Callable]] = {}
        self._global_listeners: Set[Callable] = set()

        # Nacos 客户端
        self._nacos_client = None
        self._nacos_enabled = False

        # 监控任务
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

        # 版本跟踪
        self._versions: Dict[str, int] = {}

        # 加载本地配置
        self._load_local_config()

    def _load_local_config(self):
        """加载本地配置文件"""
        if not self.config_path:
            # 尝试查找配置文件
            possible_paths = [
                Path(".claude/infrastructure.yaml"),
                Path(__file__).parent.parent.parent / ".claude" / "infrastructure.yaml",
                Path("config/infrastructure.yaml"),
            ]
            for path in possible_paths:
                if path.exists():
                    self.config_path = str(path)
                    break

        if self.config_path and Path(self.config_path).exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}

                for key, value in data.items():
                    self._configs[key] = value
                    self._config_items[key] = ConfigItem(
                        key=key,
                        value=value,
                        source=ConfigSource.LOCAL,
                        last_updated=datetime.now()
                    )

                logger.info(f"[ConfigHotReload] 加载本地配置: {self.config_path}")
            except Exception as e:
                logger.error(f"[ConfigHotReload] 加载本地配置失败: {e}")

    async def initialize_nacos(
        self,
        server_addresses: Optional[List[str]] = None,
        namespace: str = "",
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> bool:
        """
        初始化 Nacos 客户端

        Args:
            server_addresses: Nacos 服务器地址
            namespace: 命名空间
            username: 用户名
            password: 密码

        Returns:
            bool: 是否成功
        """
        try:
            from .nacos_client import NacosClient, NacosConfig

            config = NacosConfig(
                server_addresses=server_addresses or ["http://localhost:8848"],
                namespace=namespace,
                username=username,
                password=password
            )

            self._nacos_client = NacosClient(config=config)
            connected = await self._nacos_client.connect()

            if connected:
                self._nacos_enabled = True
                logger.info(f"[ConfigHotReload] Nacos 连接成功")

                # 启动监控
                if self.policy.enable_hot_reload:
                    await self._start_monitor()

            return connected

        except ImportError:
            logger.warning("[ConfigHotReload] nacos-sdk-python 未安装")
            return False
        except Exception as e:
            logger.error(f"[ConfigHotReload] Nacos 连接失败: {e}")
            return False

    async def _start_monitor(self):
        """启动配置监控"""
        if self._monitor_task is None or self._monitor_task.done():
            self._running = True
            self._monitor_task = asyncio.create_task(self._monitor_configs())

    async def _monitor_configs(self):
        """监控配置变化"""
        while self._running:
            try:
                # 检查 Nacos 配置
                if self._nacos_enabled and self._nacos_client:
                    await self._check_nacos_configs()

                # 检查本地配置
                await self._check_local_configs()

            except Exception as e:
                logger.error(f"[ConfigHotReload] 监控异常: {e}")

            await asyncio.sleep(self.policy.reload_interval)

    async def _check_nacos_configs(self):
        """检查 Nacos 配置变化"""
        for key in list(self._configs.keys()):
            if key.startswith("nacos:"):
                data_id = key[5:]  # 移除 "nacos:" 前缀
                try:
                    content = await self._nacos_client.get_config(data_id)
                    if content:
                        new_value = yaml.safe_load(content)
                        if new_value != self._configs.get(key):
                            await self._on_config_change(key, new_value, ConfigSource.NACOS)
                except Exception as e:
                    logger.error(f"[ConfigHotReload] 检查 Nacos 配置失败: {key}, {e}")

    async def _check_local_configs(self):
        """检查本地配置变化"""
        if self.config_path and Path(self.config_path).exists():
            mtime = Path(self.config_path).stat().st_mtime
            key = "local"

            if key not in self._versions:
                self._versions[key] = mtime
                return

            if mtime > self._versions[key]:
                self._versions[key] = mtime
                try:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        new_value = yaml.safe_load(f) or {}

                    if new_value != self._configs.get(key):
                        await self._on_config_change(key, new_value, ConfigSource.LOCAL)
                except Exception as e:
                    logger.error(f"[ConfigHotReload] 重新加载本地配置失败: {e}")

    async def _on_config_change(
        self,
        key: str,
        new_value: Any,
        source: ConfigSource
    ):
        """配置变化处理"""
        old_value = self._configs.get(key)

        # 更新配置
        self._configs[key] = new_value
        self._config_items[key] = ConfigItem(
            key=key,
            value=new_value,
            source=source,
            last_updated=datetime.now(),
            version=self._config_items.get(key, ConfigItem(key, None, source)).version + 1
        )

        # 通知监听器
        self._notify_listeners(key, old_value, new_value)

        logger.info(f"[ConfigHotReload] 配置已更新: {key} ({source.value})")

    def _notify_listeners(self, key: str, old_value: Any, new_value: Any):
        """通知监听器"""
        # 全局监听器
        for listener in self._global_listeners:
            try:
                listener(key, old_value, new_value)
            except Exception as e:
                logger.error(f"[ConfigHotReload] 全局监听器回调失败: {e}")

        # 特定配置监听器
        if key in self._listeners:
            for listener in self._listeners[key]:
                try:
                    listener(key, old_value, new_value)
                except Exception as e:
                    logger.error(f"[ConfigHotReload] 监听器回调失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔
            default: 默认值

        Returns:
            Any: 配置值
        """
        # 直接键
        if key in self._configs:
            return self._configs[key]

        # 点号分隔的键
        keys = key.split(".")
        value = self._configs

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置节

        Args:
            section: 配置节名称

        Returns:
            Dict: 配置节内容
        """
        return self._configs.get(section, {})

    def set(self, key: str, value: Any, source: ConfigSource = ConfigSource.MEMORY):
        """
        设置配置值

        Args:
            key: 配置键
            value: 配置值
            source: 配置来源
        """
        old_value = self._configs.get(key)
        self._configs[key] = value
        self._config_items[key] = ConfigItem(
            key=key,
            value=value,
            source=source,
            last_updated=datetime.now(),
            version=self._config_items.get(key, ConfigItem(key, None, source)).version + 1
        )

        if old_value != value:
            self._notify_listeners(key, old_value, value)

    async def load_from_nacos(self, data_id: str, key: Optional[str] = None) -> bool:
        """
        从 Nacos 加载配置

        Args:
            data_id: Nacos data_id
            key: 配置键，为空则使用 data_id

        Returns:
            bool: 是否成功
        """
        if not self._nacos_enabled:
            logger.warning("[ConfigHotReload] Nacos 未启用")
            return False

        try:
            content = await self._nacos_client.get_config(data_id)
            if content is None:
                return False

            value = yaml.safe_load(content)
            config_key = key or f"nacos:{data_id}"

            await self._on_config_change(config_key, value, ConfigSource.NACOS)
            return True

        except Exception as e:
            logger.error(f"[ConfigHotReload] 从 Nacos 加载失败: {data_id}, {e}")
            return False

    async def reload(self, key: str) -> bool:
        """
        手动重新加载配置

        Args:
            key: 配置键

        Returns:
            bool: 是否成功
        """
        if key.startswith("nacos:"):
            data_id = key[5:]
            return await self.load_from_nacos(data_id, key)

        if key == "local":
            await self._check_local_configs()
            return True

        return False

    def on_change(self, key: str, callback: Callable):
        """
        监听配置变化

        Args:
            key: 配置键，"" 表示监听所有
            callback: 回调函数 (key, old_value, new_value)
        """
        if key == "":
            self._global_listeners.add(callback)
        else:
            if key not in self._listeners:
                self._listeners[key] = set()
            self._listeners[key].add(callback)

    def off_change(self, key: str, callback: Optional[Callable] = None):
        """
        取消监听配置变化

        Args:
            key: 配置键
            callback: 回调函数，为 None 则取消所有
        """
        if key == "":
            if callback:
                self._global_listeners.discard(callback)
            else:
                self._global_listeners.clear()
        else:
            if callback and key in self._listeners:
                self._listeners[key].discard(callback)
            else:
                self._listeners.pop(key, None)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "config_count": len(self._configs),
            "nacos_enabled": self._nacos_enabled,
            "running": self._running,
            "listener_count": len(self._global_listeners) + sum(
                len(s) for s in self._listeners.values()
            ),
            "configs": {
                k: {
                    "source": v.source.value,
                    "version": v.version,
                    "last_updated": v.last_updated.isoformat() if v.last_updated else None
                }
                for k, v in self._config_items.items()
            }
        }

    async def close(self):
        """关闭连接"""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._nacos_client:
            await self._nacos_client.close()

        logger.info("[ConfigHotReload] 已关闭")


# =============================================================================
# 工厂函数和便捷函数
# =============================================================================

_config_reloader: Optional[ConfigHotReload] = None


async def get_config_reloader(
    config_path: Optional[str] = None,
    nacos_enabled: bool = False,
    **nacos_kwargs
) -> ConfigHotReload:
    """
    获取配置热重载器（单例）

    Args:
        config_path: 配置文件路径
        nacos_enabled: 是否启用 Nacos
        **nacos_kwargs: Nacos 连接参数

    Returns:
        ConfigHotReload: 配置热重载器实例
    """
    global _config_reloader

    if _config_reloader is None:
        _config_reloader = ConfigHotReload(config_path=config_path)

        if nacos_enabled:
            await _config_reloader.initialize_nacos(**nacos_kwargs)

    return _config_reloader


async def create_config_reloader(
    config_path: Optional[str] = None,
    nacos_enabled: bool = False,
    **nacos_kwargs
) -> ConfigHotReload:
    """
    创建配置热重载器（新实例）

    Args:
        config_path: 配置文件路径
        nacos_enabled: 是否启用 Nacos
        **nacos_kwargs: Nacos 连接参数

    Returns:
        ConfigHotReload: 配置热重载器实例
    """
    reloader = ConfigHotReload(config_path=config_path)

    if nacos_enabled:
        await reloader.initialize_nacos(**nacos_kwargs)

    return reloader


def reset_config_reloader():
    """重置配置热重载器（用于测试）"""
    global _config_reloader
    _config_reloader = None
