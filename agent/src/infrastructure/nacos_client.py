"""
================================================================================
基础设施层 - Nacos 配置中心 (Nacos Configuration Center)

提供 Nacos 配置中心的集成支持，支持配置管理、服务发现、动态配置更新等功能。

功能特点:
- 配置获取和监听
- 配置管理
- 服务注册
- 服务发现
- 命名空间隔离

使用示例:
```python
from infrastructure.nacos_client import NacosClient, ConfigListener

client = NacosClient(
    server_addresses=["localhost:8848"],
    namespace="travel-agent"
)

# 获取配置
config = await client.get_config("app.yaml")

# 监听配置变化
def on_change(data):
    print(f"配置变化: {data}")
await client.subscribe("app.yaml", on_change)
```

================================================================================
"""

import asyncio
import json
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class NacosError(Exception):
    """Nacos 错误"""
    pass


@dataclass
class NacosConfig:
    """Nacos 配置"""

    def __init__(
        self,
        server_addresses: List[str] = None,
        namespace: str = "",
        group: str = "DEFAULT_GROUP",
        username: Optional[str] = None,
        password: Optional[str] = None,
        data_id_prefix: str = "",
        timeout: float = 5.0,
        heartbeat_interval: float = 5.0,
        retry_times: int = 3
    ):
        self.server_addresses = server_addresses or ["localhost:8848"]
        self.namespace = namespace
        self.group = group
        self.username = username
        self.password = password
        self.data_id_prefix = data_id_prefix
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.retry_times = retry_times


@dataclass
class ServiceInfo:
    """服务信息"""
    name: str
    ip: str
    port: int
    cluster_name: str = "default"
    metadata: Dict[str, str] = field(default_factory=dict)
    weight: float = 1.0
    enabled: bool = True
    healthy: bool = True
    ephemeral: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "serviceName": self.name,
            "ip": self.ip,
            "port": self.port,
            "clusterName": self.cluster_name,
            "metadata": self.metadata,
            "weight": self.weight,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "ephemeral": self.ephemeral
        }


@dataclass
class ConfigInfo:
    """配置信息"""
    data_id: str
    group: str
    content: str
    namespace: str = ""
    md5: str = ""
    type_: str = "yaml"
    app_name: str = ""
    created_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataId": self.data_id,
            "group": self.group,
            "content": self.content,
            "namespace": self.namespace,
            "md5": self.md5,
            "type": self.type_,
            "appName": self.app_name,
            "createdTime": self.created_time
        }


class ConfigListener:
    """配置监听器"""

    def __init__(self, data_id: str, group: str, callback: Callable):
        """
        初始化监听器

        Args:
            data_id: 配置 ID
            group: 配置组
            callback: 回调函数
        """
        self.data_id = data_id
        self.group = group
        self.callback = callback
        self.last_content: Optional[str] = None


class NacosClient:
    """
    Nacos 客户端

    提供 Nacos 配置中心和服务发现的功能接口。
    """

    def __init__(
        self,
        config: Optional[NacosConfig] = None,
        client: Any = None
    ):
        """
        初始化 Nacos 客户端

        Args:
            config: Nacos 配置
            client: 已连接的 Nacos 客户端
        """
        self.config = config or NacosConfig()
        self._client = client
        self._listeners: Dict[str, Set[ConfigListener]] = {}
        self._cache: Dict[str, ConfigInfo] = {}
        self._running = False
        self._monitor_tasks: List[asyncio.Task] = []

    async def connect(self) -> bool:
        """
        连接 Nacos 服务器

        Returns:
            bool: 是否成功
        """
        try:
            # 尝试导入 nacos-sdk-python
            try:
                from nacos import NacosClient as NacosSDKClient

                self._client = NacosSDKClient(
                    server_addresses=self.config.server_addresses,
                    namespace=self.config.namespace,
                    username=self.config.username,
                    password=self.config.password,
                    timeout=self.config.timeout
                )

                logger.info(f"[Nacos] 连接成功: {self.config.server_addresses}")
                return True

            except ImportError:
                logger.warning("[Nacos] nacos-sdk-python 未安装，使用模拟模式")
                self._client = "mock"
                return True

        except Exception as e:
            logger.error(f"[Nacos] 连接失败: {e}")
            return False

    async def get_config(
        self,
        data_id: str,
        group: Optional[str] = None
    ) -> Optional[str]:
        """
        获取配置

        Args:
            data_id: 配置 ID
            group: 配置组

        Returns:
            str: 配置内容，不存在返回 None
        """
        group = group or self.config.group
        cache_key = f"{group}:{data_id}"

        # 检查缓存
        if cache_key in self._cache:
            return self._cache[cache_key].content

        try:
            if self._client == "mock":
                # 模拟模式：尝试从文件加载
                content = self._load_from_file(data_id)
                if content:
                    self._cache[cache_key] = ConfigInfo(
                        data_id=data_id,
                        group=group,
                        content=content
                    )
                return content

            # 实际 Nacos 调用
            content = self._client.get_config(
                data_id=data_id,
                group=group
            )

            if content is not None:
                self._cache[cache_key] = ConfigInfo(
                    data_id=data_id,
                    group=group,
                    content=content
                )
                logger.info(f"[Nacos] 获取配置: {data_id} ({len(content)} bytes)")

            return content

        except Exception as e:
            logger.error(f"[Nacos] 获取配置失败: {data_id}, {e}")
            return None

    async def get_config_dict(
        self,
        data_id: str,
        group: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取配置并解析为字典

        Args:
            data_id: 配置 ID
            group: 配置组

        Returns:
            Dict: 配置字典
        """
        content = await self.get_config(data_id, group)
        if not content:
            return None

        # 根据扩展名解析
        if data_id.endswith(".yaml") or data_id.endswith(".yml"):
            import yaml
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError as e:
                logger.error(f"[Nacos] YAML 解析错误: {e}")
                return None
        elif data_id.endswith(".json"):
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"[Nacos] JSON 解析错误: {e}")
                return None
        else:
            # 尝试 YAML
            import yaml
            try:
                return yaml.safe_load(content)
            except:
                return None

    async def publish_config(
        self,
        data_id: str,
        content: str,
        group: Optional[str] = None,
        type_: str = "yaml"
    ) -> bool:
        """
        发布配置

        Args:
            data_id: 配置 ID
            content: 配置内容
            group: 配置组
            type_: 配置类型

        Returns:
            bool: 是否成功
        """
        group = group or self.config.group

        try:
            if self._client == "mock":
                # 模拟模式：保存到文件
                self._save_to_file(data_id, content)
                logger.info(f"[Nacos] 模拟发布配置: {data_id}")
                return True

            result = self._client.publish_config(
                data_id=data_id,
                group=group,
                content=content
            )

            if result:
                logger.info(f"[Nacos] 发布配置成功: {data_id}")
                # 更新缓存
                cache_key = f"{group}:{data_id}"
                self._cache[cache_key] = ConfigInfo(
                    data_id=data_id,
                    group=group,
                    content=content,
                    type_=type_
                )

            return result

        except Exception as e:
            logger.error(f"[Nacos] 发布配置失败: {data_id}, {e}")
            return False

    async def delete_config(
        self,
        data_id: str,
        group: Optional[str] = None
    ) -> bool:
        """
        删除配置

        Args:
            data_id: 配置 ID
            group: 配置组

        Returns:
            bool: 是否成功
        """
        group = group or self.config.group
        cache_key = f"{group}:{data_id}"

        try:
            if self._client == "mock":
                self._delete_file(data_id)
                self._cache.pop(cache_key, None)
                return True

            result = self._client.delete_config(
                data_id=data_id,
                group=group
            )

            if result:
                self._cache.pop(cache_key, None)
                logger.info(f"[Nacos] 删除配置: {data_id}")

            return result

        except Exception as e:
            logger.error(f"[Nacos] 删除配置失败: {data_id}, {e}")
            return False

    async def subscribe(
        self,
        data_id: str,
        callback: Callable[[str, str, str], None],
        group: Optional[str] = None
    ):
        """
        订阅配置变化

        Args:
            data_id: 配置 ID
            callback: 回调函数 (data_id, group, content)
            group: 配置组
        """
        group = group or self.config.group
        listener_key = f"{group}:{data_id}"

        if listener_key not in self._listeners:
            self._listeners[listener_key] = set()

        listener = ConfigListener(data_id, group, callback)
        self._listeners[listener_key].add(listener)

        logger.info(f"[Nacos] 订阅配置: {listener_key}")

        # 如果已有缓存，触发回调
        cache_key = listener_key
        if cache_key in self._cache:
            content = self._cache[cache_key].content
            callback(data_id, group, content)

        # 启动监控任务
        if not self._monitor_tasks:
            self._running = True
            self._monitor_tasks.append(asyncio.create_task(self._monitor_configs()))

    async def unsubscribe(
        self,
        data_id: str,
        callback: Optional[Callable] = None,
        group: Optional[str] = None
    ):
        """
        取消订阅

        Args:
            data_id: 配置 ID
            callback: 回调函数，为 None 则取消所有
            group: 配置组
        """
        group = group or self.config.group
        listener_key = f"{group}:{data_id}"

        if callback is None:
            self._listeners.pop(listener_key, None)
        else:
            if listener_key in self._listeners:
                self._listeners[listener_key] = {
                    l for l in self._listeners[listener_key]
                    if l.callback != callback
                }

        logger.info(f"[Nacos] 取消订阅: {listener_key}")

    async def _monitor_configs(self):
        """监控配置变化"""
        while self._running:
            try:
                # 检查配置变化
                for listener_key, listeners in self._listeners.items():
                    group, data_id = listener_key.split(":", 1)

                    try:
                        if self._client == "mock":
                            # 模拟模式：从文件读取
                            content = self._load_from_file(data_id)
                        else:
                            content = self._client.get_config(
                                data_id=data_id,
                                group=group
                            )

                        if content is None:
                            content = ""

                        # 检查是否有监听器
                        for listener in listeners:
                            if listener.last_content != content:
                                listener.last_content = content
                                try:
                                    listener.callback(data_id, group, content)
                                except Exception as e:
                                    logger.error(f"[Nacos] 回调错误: {e}")

                    except Exception as e:
                        logger.error(f"[Nacos] 检查配置失败: {listener_key}, {e}")

            except Exception as e:
                logger.error(f"[Nacos] 监控配置异常: {e}")

            await asyncio.sleep(self.config.heartbeat_interval)

    # ============ 服务注册与发现 ============

    async def register_service(
        self,
        service_info: ServiceInfo,
        group: Optional[str] = None
    ) -> bool:
        """
        注册服务

        Args:
            service_info: 服务信息
            group: 服务组

        Returns:
            bool: 是否成功
        """
        group = group or self.config.group

        try:
            if self._client == "mock":
                logger.info(f"[Nacos] 模拟注册服务: {service_info.name}")
                return True

            self._client.add_naming_instance(
                service_name=service_info.name,
                ip=service_info.ip,
                port=service_info.port,
                cluster_name=service_info.cluster_name,
                metadata=service_info.metadata,
                weight=service_info.weight,
                enabled=service_info.enabled,
                ephemeral=service_info.ephemeral
            )

            logger.info(f"[Nacos] 注册服务: {service_info.name}")
            return True

        except Exception as e:
            logger.error(f"[Nacos] 注册服务失败: {service_info.name}, {e}")
            return False

    async def deregister_service(
        self,
        service_name: str,
        ip: str,
        port: int,
        cluster: str = "default"
    ) -> bool:
        """
        注销服务

        Args:
            service_name: 服务名称
            ip: IP 地址
            port: 端口
            cluster: 集群名称

        Returns:
            bool: 是否成功
        """
        try:
            if self._client == "mock":
                return True

            self._client.remove_naming_instance(
                service_name=service_name,
                ip=ip,
                port=port,
                cluster_name=cluster
            )

            logger.info(f"[Nacos] 注销服务: {service_name}")
            return True

        except Exception as e:
            logger.error(f"[Nacos] 注销服务失败: {service_name}, {e}")
            return False

    async def get_all_instances(
        self,
        service_name: str,
        group: Optional[str] = None,
        healthy_only: bool = False
    ) -> List[ServiceInfo]:
        """
        获取服务实例列表

        Args:
            service_name: 服务名称
            group: 服务组
            healthy_only: 仅返回健康实例

        Returns:
            List[ServiceInfo]: 实例列表
        """
        group = group or self.config.group

        try:
            if self._client == "mock":
                return []

            instances = self._client.list_naming_instance(
                service_name=service_name,
                group_name=group,
                healthy_only=healthy_only
            )

            result = []
            for inst in instances.get("hosts", []):
                result.append(ServiceInfo(
                    name=service_name,
                    ip=inst.get("ip", ""),
                    port=inst.get("port", 0),
                    cluster_name=inst.get("clusterName", "default"),
                    metadata=inst.get("metadata", {}),
                    weight=inst.get("weight", 1.0),
                    enabled=inst.get("enabled", True),
                    healthy=inst.get("healthy", True)
                ))

            return result

        except Exception as e:
            logger.error(f"[Nacos] 获取服务实例失败: {service_name}, {e}")
            return []

    async def get_service(
        self,
        service_name: str,
        group: Optional[str] = None
    ) -> Optional[ServiceInfo]:
        """
        获取单个服务实例（随机或权重选择）

        Args:
            service_name: 服务名称
            group: 服务组

        Returns:
            Optional[ServiceInfo]: 实例信息
        """
        instances = await self.get_all_instances(service_name, group, healthy_only=True)
        if not instances:
            return None

        # 简单随机选择
        import random
        return random.choice(instances)

    # ============ 辅助方法 ============

    def _load_from_file(self, data_id: str) -> Optional[str]:
        """从文件加载配置"""
        base_path = Path("config")
        possible_paths = [
            base_path / data_id,
            base_path / f"{data_id}.yaml",
            base_path / f"{data_id}.yml"
        ]

        for path in possible_paths:
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8")
                except Exception:
                    pass
        return None

    def _save_to_file(self, data_id: str, content: str):
        """保存配置到文件"""
        base_path = Path("config")
        base_path.mkdir(exist_ok=True)

        # 添加 .yaml 后缀
        if not data_id.endswith(".yaml") and not data_id.endswith(".yml"):
            data_id = f"{data_id}.yaml"

        path = base_path / data_id
        path.write_text(content, encoding="utf-8")

    def _delete_file(self, data_id: str):
        """删除配置文件"""
        base_path = Path("config")

        # 尝试多个后缀
        for suffix in ["", ".yaml", ".yml"]:
            path = base_path / f"{data_id}{suffix}"
            if path.exists():
                path.unlink()
                break

    async def close(self):
        """关闭连接"""
        self._running = False

        # 取消监控任务
        for task in self._monitor_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._monitor_tasks.clear()

        # 注销服务
        # 清理监听器
        self._listeners.clear()
        self._cache.clear()

        logger.info("[Nacos] 连接已关闭")


class ConfigManager:
    """
    配置管理器

    提供更高级的配置管理功能，支持配置热加载、多环境切换等。
    """

    def __init__(
        self,
        nacos_client: NacosClient,
        app_name: str = "app",
        env: str = "default"
    ):
        """
        初始化配置管理器

        Args:
            nacos_client: Nacos 客户端
            app_name: 应用名称
            env: 环境名称
        """
        self.nacos = nacos_client
        self.app_name = app_name
        self.env = env
        self._configs: Dict[str, Any] = {}
        self._listeners: List[Callable] = []

    async def load_config(
        self,
        config_name: str,
        data_id: Optional[str] = None
    ) -> bool:
        """
        加载配置

        Args:
            config_name: 配置名称
            data_id: Nacos data_id，为空则自动生成

        Returns:
            bool: 是否成功
        """
        if data_id is None:
            data_id = f"{self.app_name}-{self.env}-{config_name}"

        content = await self.nacos.get_config(data_id)
        if content is None:
            logger.warning(f"[ConfigManager] 配置不存在: {data_id}")
            return False

        import yaml
        try:
            self._configs[config_name] = yaml.safe_load(content)
            logger.info(f"[ConfigManager] 加载配置: {config_name}")
            return True
        except Exception as e:
            logger.error(f"[ConfigManager] 解析配置失败: {config_name}, {e}")
            return False

    def get(self, config_name: str, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            config_name: 配置名称
            key: 配置键，支持点号分隔
            default: 默认值

        Returns:
            Any: 配置值
        """
        config = self._configs.get(config_name, {})
        keys = key.split(".")

        for k in keys:
            if isinstance(config, dict):
                config = config.get(k)
            else:
                return default

        return config if config is not None else default

    def get_section(self, config_name: str) -> Dict[str, Any]:
        """
        获取整个配置节

        Args:
            config_name: 配置名称

        Returns:
            Dict: 配置节内容
        """
        return self._configs.get(config_name, {})

    def add_change_listener(self, listener: Callable):
        """添加配置变化监听器"""
        self._listeners.append(listener)

    def _notify_change(self, config_name: str):
        """通知配置变化"""
        for listener in self._listeners:
            try:
                listener(config_name, self._configs.get(config_name))
            except Exception as e:
                logger.error(f"[ConfigManager] 通知监听器失败: {e}")


# 便捷函数
def create_nacos_client(
    server_addresses: List[str] = None,
    namespace: str = "",
    username: Optional[str] = None,
    password: Optional[str] = None
) -> NacosClient:
    """
    创建 Nacos 客户端

    Args:
        server_addresses: 服务器地址列表
        namespace: 命名空间
        username: 用户名
        password: 密码

    Returns:
        NacosClient: Nacos 客户端实例
    """
    config = NacosConfig(
        server_addresses=server_addresses,
        namespace=namespace,
        username=username,
        password=password
    )
    return NacosClient(config=config)
