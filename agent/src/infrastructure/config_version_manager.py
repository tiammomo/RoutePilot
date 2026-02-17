"""
================================================================================
配置版本管理模块 (Config Version Manager)

提供 Nacos 配置的版本管理和回滚功能，支持：
- 配置变更历史记录
- 配置版本对比
- 配置回滚
- 配置审计

使用示例:
```python
from infrastructure.config_version_manager import (
    ConfigVersionManager, ConfigVersion,
    create_version_manager
)

# 创建版本管理器
manager = await create_version_manager()

# 保存配置版本
version_id = await manager.save_version(
    config_id="travel-agent-llm",
    config_data={"provider": "openai", "model": "gpt-4"},
    operator="admin"
)

# 获取版本历史
history = await manager.get_version_history("travel-agent-llm", limit=10)

# 回滚到指定版本
await manager.rollback("travel-agent-llm", version_id)

# 对比两个版本
diff = await manager.compare_versions("travel-agent-llm", v1, v2)
```

================================================================================
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from difflib import unified_diff

logger = logging.getLogger(__name__)


class ConfigStatus(Enum):
    """配置状态"""
    ACTIVE = "active"
    DELETED = "deleted"
    ROLLBACK = "rollback"


@dataclass
class ConfigVersion:
    """配置版本"""
    id: str
    config_id: str
    version: int
    data: Dict[str, Any]
    checksum: str
    operator: str
    comment: str
    created_at: float = field(default_factory=time.time)
    status: ConfigStatus = ConfigStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "config_id": self.config_id,
            "version": self.version,
            "data": self.data,
            "checksum": self.checksum,
            "operator": self.operator,
            "comment": self.comment,
            "created_at": self.created_at,
            "status": self.status.value,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigVersion':
        return cls(
            id=data["id"],
            config_id=data["config_id"],
            version=data["version"],
            data=data["data"],
            checksum=data["checksum"],
            operator=data["operator"],
            comment=data["comment"],
            created_at=data.get("created_at", time.time()),
            status=ConfigStatus(data.get("status", "active")),
            metadata=data.get("metadata", {})
        )


@dataclass
class ConfigDiff:
    """配置差异"""
    added: Dict[str, Any] = field(default_factory=dict)
    removed: Dict[str, Any] = field(default_factory=dict)
    changed: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    added_keys: List[str] = field(default_factory=list)
    removed_keys: List[str] = field(default_factory=list)
    changed_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": {k: {"old": v[0], "new": v[1]} for k, v in self.changed.items()},
            "added_keys": self.added_keys,
            "removed_keys": self.removed_keys,
            "changed_keys": self.changed_keys
        }


@dataclass
class VersionManagerConfig:
    """版本管理器配置"""
    # 存储后端
    storage_backend: str = "redis"  # redis, nacos, mysql
    # Redis 配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_key_prefix: str = "config:version:"
    # Nacos 配置
    nacos_server_addresses: List[str] = field(default_factory=lambda: ["http://localhost:38848"])
    nacos_namespace: str = "travel-agent"
    # 版本保留
    max_versions_per_config: int = 100
    retention_days: int = 90
    # 功能开关
    enable_auto_snapshot: bool = True
    snapshot_interval: int = 300  # 5分钟


class ConfigVersionManager:
    """
    配置版本管理器

    管理配置的历史版本，支持回滚和对比。
    """

    def __init__(
        self,
        config: Optional[VersionManagerConfig] = None,
        redis_client: Optional[Any] = None
    ):
        """
        初始化版本管理器

        Args:
            config: 配置
            redis_client: Redis 客户端
        """
        self.config = config or VersionManagerConfig()
        self._redis_client = redis_client
        self._initialized = False

    @property
    def client(self):
        """获取 Redis 客户端"""
        if self._redis_client is None:
            import redis.asyncio as redis
            self._redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                decode_responses=True
            )
        return self._redis_client

    def _get_version_key(self, config_id: str) -> str:
        """获取版本列表 key"""
        return f"{self.config.redis_key_prefix}versions:{config_id}"

    def _get_data_key(self, version_id: str) -> str:
        """获取版本数据 key"""
        return f"{self.config.redis_key_prefix}data:{version_id}"

    def _get_latest_version_key(self, config_id: str) -> str:
        """获取最新版本号 key"""
        return f"{self.config.redis_key_prefix}latest:{config_id}"

    def _generate_checksum(self, data: Dict[str, Any]) -> str:
        """生成校验和"""
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode()).hexdigest()

    def _generate_id(self, config_id: str, version: int) -> str:
        """生成版本 ID"""
        timestamp = int(time.time())
        hash_part = hashlib.md5(f"{config_id}{version}{timestamp}".encode()).hexdigest()[:8]
        return f"{config_id}:v{version}:{hash_part}"

    async def initialize(self) -> bool:
        """初始化"""
        try:
            await self.client.ping()
            self._initialized = True
            logger.info("[ConfigVersionManager] 初始化成功")
            return True
        except Exception as e:
            logger.error(f"[ConfigVersionManager] 初始化失败: {e}")
            return False

    async def save_version(
        self,
        config_id: str,
        data: Dict[str, Any],
        operator: str = "system",
        comment: str = ""
    ) -> str:
        """
        保存配置版本

        Args:
            config_id: 配置 ID
            data: 配置数据
            operator: 操作者
            comment: 备注

        Returns:
            str: 版本 ID
        """
        if not self._initialized:
            await self.initialize()

        try:
            # 生成校验和
            checksum = self._generate_checksum(data)

            # 获取当前版本号
            latest_key = self._get_latest_version_key(config_id)
            current_version = await self.client.get(latest_key)
            version = int(current_version) + 1 if current_version else 1

            # 生成版本 ID
            version_id = self._generate_id(config_id, version)

            # 创建版本对象
            config_version = ConfigVersion(
                id=version_id,
                config_id=config_id,
                version=version,
                data=data,
                checksum=checksum,
                operator=operator,
                comment=comment
            )

            # 保存版本数据
            data_key = self._get_data_key(version_id)
            await self.client.setex(
                data_key,
                self.config.retention_days * 86400,
                json.dumps(config_version.to_dict(), ensure_ascii=False)
            )

            # 更新版本列表（有序集合）
            versions_key = self._get_version_key(config_id)
            await self.client.zadd(versions_key, {version_id: version})
            await self.client.expire(versions_key, self.config.retention_days * 86400)

            # 更新最新版本号
            await self.client.set(latest_key, version)

            # 清理旧版本
            await self._cleanup_old_versions(config_id)

            logger.info(f"[ConfigVersionManager] 保存版本: {version_id}")
            return version_id

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 保存版本失败: {e}")
            return ""

    async def _cleanup_old_versions(self, config_id: str) -> int:
        """清理旧版本"""
        try:
            versions_key = self._get_version_key(config_id)

            # 获取所有版本
            versions = await self.client.zrange(versions_key, 0, -1)

            # 超过最大保留数
            if len(versions) > self.config.max_versions_per_config:
                to_remove = versions[:len(versions) - self.config.max_versions_per_config]

                for version_id in to_remove:
                    data_key = self._get_data_key(version_id)
                    await self.client.delete(data_key)

                await self.client.zremrangebyscore(
                    versions_key,
                    0,
                    versions[len(versions) - self.config.max_versions_per_config] - 1
                )

                return len(to_remove)

            return 0

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 清理旧版本失败: {e}")
            return 0

    async def get_version(
        self,
        config_id: str,
        version: Optional[int] = None
    ) -> Optional[ConfigVersion]:
        """
        获取配置版本

        Args:
            config_id: 配置 ID
            version: 版本号，None 表示最新版本

        Returns:
            Optional[ConfigVersion]: 版本对象
        """
        if not self._initialized:
            await self.initialize()

        try:
            # 如果没有指定版本，获取最新版本号
            if version is None:
                latest_key = self._get_latest_version_key(config_id)
                version_str = await self.client.get(latest_key)
                if not version_str:
                    return None
                version = int(version_str)

            # 查找版本 ID
            versions_key = self._get_version_key(config_id)
            version_ids = await self.client.zrangebyscore(
                versions_key,
                version,
                version
            )

            if not version_ids:
                return None

            version_id = version_ids[0]

            # 获取版本数据
            data_key = self._get_data_key(version_id)
            data_json = await self.client.get(data_key)

            if data_json:
                return ConfigVersion.from_dict(json.loads(data_json))

            return None

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 获取版本失败: {e}")
            return None

    async def get_version_history(
        self,
        config_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ConfigVersion]:
        """
        获取配置版本历史

        Args:
            config_id: 配置 ID
            limit: 返回数量
            offset: 偏移量

        Returns:
            List[ConfigVersion]: 版本列表
        """
        if not self._initialized:
            await self.initialize()

        try:
            versions_key = self._get_version_key(config_id)

            # 获取版本 ID 列表（降序）
            version_ids = await self.client.zrevrange(
                versions_key,
                offset,
                offset + limit - 1
            )

            versions = []
            for version_id in version_ids:
                data_key = self._get_data_key(version_id)
                data_json = await self.client.get(data_key)

                if data_json:
                    versions.append(ConfigVersion.from_dict(json.loads(data_json)))

            return versions

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 获取版本历史失败: {e}")
            return []

    async def get_version_count(self, config_id: str) -> int:
        """获取版本数量"""
        if not self._initialized:
            await self.initialize()

        try:
            versions_key = self._get_version_key(config_id)
            return await self.client.zcard(versions_key)
        except Exception as e:
            logger.error(f"[ConfigVersionManager] 获取版本数量失败: {e}")
            return 0

    async def compare_versions(
        self,
        config_id: str,
        version_a: int,
        version_b: int
    ) -> ConfigDiff:
        """
        对比两个版本

        Args:
            config_id: 配置 ID
            version_a: 版本 A
            version_b: 版本 B

        Returns:
            ConfigDiff: 差异
        """
        version1 = await self.get_version(config_id, version_a)
        version2 = await self.get_version(config_id, version_b)

        if not version1 or not version2:
            return ConfigDiff()

        return self._calculate_diff(version1.data, version2.data)

    def _calculate_diff(
        self,
        data1: Dict[str, Any],
        data2: Dict[str, Any]
    ) -> ConfigDiff:
        """计算两个配置的差异"""
        diff = ConfigDiff()

        # 递归比较
        def compare_dict(d1: Dict, d2: Dict, prefix: str = ""):
            all_keys = set(d1.keys()) | set(d2.keys())

            for key in all_keys:
                full_key = f"{prefix}.{key}" if prefix else key

                if key not in d1:
                    diff.added_keys.append(full_key)
                    self._set_nested(diff.added, full_key.split("."), d2[key])
                elif key not in d2:
                    diff.removed_keys.append(full_key)
                    self._set_nested(diff.removed, full_key.split("."), d1[key])
                elif isinstance(d1[key], dict) and isinstance(d2[key], dict):
                    compare_dict(d1[key], d2[key], full_key)
                elif d1[key] != d2[key]:
                    if full_key not in diff.changed_keys:
                        diff.changed_keys.append(full_key)
                    diff.changed[full_key] = (d1[key], d2[key])
                else:
                    # 值相同，添加到 unchanged_keys（可选）
                    pass

        compare_dict(data1, data2)
        return diff

    def _set_nested(self, d: Dict, keys: List[str], value: Any) -> None:
        """设置嵌套字典"""
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value

    def generate_diff_text(
        self,
        data1: Dict[str, Any],
        data2: Dict[str, Any],
        from_label: str = "v1",
        to_label: str = "v2"
    ) -> str:
        """生成差异文本（统一格式）"""
        text1 = json.dumps(data1, indent=2, ensure_ascii=False)
        text2 = json.dumps(data2, indent=2, ensure_ascii=False)

        diff = list(unified_diff(
            text1.splitlines(keepends=True),
            text2.splitlines(keepends=True),
            fromfile=from_label,
            tofile=to_label
        ))

        return "".join(diff) if diff else "无差异"

    async def rollback(
        self,
        config_id: str,
        version: int,
        operator: str = "system"
    ) -> bool:
        """
        回滚到指定版本

        Args:
            config_id: 配置 ID
            version: 目标版本
            operator: 操作者

        Returns:
            bool: 是否成功
        """
        try:
            # 获取目标版本
            target_version = await self.get_version(config_id, version)
            if not target_version:
                logger.error(f"[ConfigVersionManager] 版本不存在: {version}")
                return False

            # 保存当前为新版本（作为回滚记录）
            new_version_id = await self.save_version(
                config_id=config_id,
                data=target_version.data,
                operator=operator,
                comment=f"回滚到版本 {version}"
            )

            logger.info(f"[ConfigVersionManager] 回滚到版本 {version}，新版本: {new_version_id}")
            return True

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 回滚失败: {e}")
            return False

    async def mark_deleted(
        self,
        config_id: str,
        version: int,
        operator: str = "system"
    ) -> bool:
        """
        标记版本为删除

        Args:
            config_id: 配置 ID
            version: 版本号
            operator: 操作者

        Returns:
            bool: 是否成功
        """
        try:
            version_obj = await self.get_version(config_id, version)
            if not version_obj:
                return False

            version_obj.status = ConfigStatus.DELETED

            # 更新数据
            data_key = self._get_data_key(version_obj.id)
            await self.client.set(
                data_key,
                json.dumps(version_obj.to_dict(), ensure_ascii=False)
            )

            logger.info(f"[ConfigVersionManager] 标记删除: {version_obj.id}")
            return True

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 标记删除失败: {e}")
            return False

    async def restore(
        self,
        config_id: str,
        version: int,
        operator: str = "system"
    ) -> bool:
        """
        恢复已删除的版本

        Args:
            config_id: 配置 ID
            version: 版本号
            operator: 操作者

        Returns:
            bool: 是否成功
        """
        try:
            version_obj = await self.get_version(config_id, version)
            if not version_obj or version_obj.status != ConfigStatus.DELETED:
                return False

            # 恢复状态
            version_obj.status = ConfigStatus.ACTIVE

            # 更新数据
            data_key = self._get_data_key(version_obj.id)
            await self.client.set(
                data_key,
                json.dumps(version_obj.to_dict(), ensure_ascii=False)
            )

            logger.info(f"[ConfigVersionManager] 恢复版本: {version_obj.id}")
            return True

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 恢复失败: {e}")
            return False

    async def search_versions(
        self,
        config_id: str,
        operator: Optional[str] = None,
        comment_contains: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 50
    ) -> List[ConfigVersion]:
        """
        搜索版本

        Args:
            config_id: 配置 ID
            operator: 操作者过滤
            comment_contains: 备注包含
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量

        Returns:
            List[ConfigVersion]: 版本列表
        """
        versions = await self.get_version_history(config_id, limit=100)

        # 过滤
        filtered = []
        for v in versions:
            if operator and v.operator != operator:
                continue
            if comment_contains and comment_contains not in v.comment:
                continue
            if start_time and v.created_at < start_time:
                continue
            if end_time and v.created_at > end_time:
                continue
            filtered.append(v)

        return filtered[:limit]

    async def get_audit_log(
        self,
        config_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取审计日志

        Args:
            config_id: 配置 ID
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量

        Returns:
            List[Dict]: 审计日志
        """
        versions = await self.get_version_history(config_id, limit=limit)

        logs = []
        for v in versions:
            if start_time and v.created_at < start_time:
                continue
            if end_time and v.created_at > end_time:
                continue

            logs.append({
                "timestamp": datetime.fromtimestamp(v.created_at).isoformat(),
                "version": v.version,
                "operator": v.operator,
                "action": "CREATE" if v.comment.startswith("回滚") else "UPDATE",
                "comment": v.comment,
                "checksum": v.checksum
            })

        return logs

    async def cleanup_expired_versions(self, config_id: str) -> int:
        """
        清理过期版本

        Args:
            config_id: 配置 ID

        Returns:
            int: 清理数量
        """
        try:
            cutoff_time = time.time() - (self.config.retention_days * 86400)

            versions = await self.get_version_history(config_id, limit=1000)

            cleaned = 0
            for v in versions:
                if v.created_at < cutoff_time:
                    await self.mark_deleted(config_id, v.version)
                    cleaned += 1

            logger.info(f"[ConfigVersionManager] 清理过期版本: {cleaned}")
            return cleaned

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 清理过期版本失败: {e}")
            return 0

    async def close(self) -> None:
        """关闭连接"""
        if self._redis_client:
            await self._redis_client.close()
        logger.info("[ConfigVersionManager] 连接已关闭")


# =============================================================================
# Nacos 集成
# =============================================================================

class NacosConfigVersionManager(ConfigVersionManager):
    """
    Nacos 配置版本管理器

    扩展版本管理器，支持与 Nacos 配置中心集成。
    """

    def __init__(
        self,
        config: Optional[VersionManagerConfig] = None,
        nacos_client: Optional[Any] = None
    ):
        super().__init__(config)
        self._nacos_client = nacos_client

    async def sync_from_nacos(self, config_id: str, operator: str = "nacos") -> str:
        """
        从 Nacos 同步配置并保存版本

        Args:
            config_id: 配置 ID
            operator: 操作者

        Returns:
            str: 版本 ID
        """
        try:
            from .nacos_client import NacosClient

            if self._nacos_client is None:
                self._nacos_client = NacosClient()

            # 获取 Nacos 配置
            config_data = await self._nacos_client.get_config(config_id)

            if config_data:
                return await self.save_version(
                    config_id=config_id,
                    data=config_data,
                    operator=operator,
                    comment="从 Nacos 同步"
                )

            return ""

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 从 Nacos 同步失败: {e}")
            return ""

    async def publish_to_nacos(
        self,
        config_id: str,
        version: int,
        operator: str = "system"
    ) -> bool:
        """
        发布版本到 Nacos

        Args:
            config_id: 配置 ID
            version: 版本号
            operator: 操作者

        Returns:
            bool: 是否成功
        """
        try:
            version_obj = await self.get_version(config_id, version)
            if not version_obj:
                return False

            from .nacos_client import NacosClient

            if self._nacos_client is None:
                self._nacos_client = NacosClient()

            # 发布到 Nacos
            success = await self._nacos_client.publish_config(
                data_id=config_id,
                group="DEFAULT_GROUP",
                content=json.dumps(version_obj.data, ensure_ascii=False)
            )

            if success:
                logger.info(f"[ConfigVersionManager] 发布到 Nacos: {config_id} v{version}")

            return success

        except Exception as e:
            logger.error(f"[ConfigVersionManager] 发布到 Nacos 失败: {e}")
            return False


# =============================================================================
# 便捷函数
# =============================================================================

async def create_version_manager(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_prefix: str = "config:version:",
    max_versions: int = 100,
    retention_days: int = 90
) -> ConfigVersionManager:
    """
    创建版本管理器

    Args:
        redis_host: Redis 主机
        redis_port: Redis 端口
        redis_prefix: 键前缀
        max_versions: 最大版本数
        retention_days: 保留天数

    Returns:
        ConfigVersionManager: 版本管理器实例
    """
    config = VersionManagerConfig(
        redis_host=redis_host,
        redis_port=redis_port,
        redis_key_prefix=redis_prefix,
        max_versions_per_config=max_versions,
        retention_days=retention_days
    )

    manager = ConfigVersionManager(config=config)
    await manager.initialize()

    return manager


async def check_version_manager_health() -> Dict[str, Any]:
    """
    检查版本管理器健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        manager = await create_version_manager()
        await manager.client.ping()
        await manager.close()

        return {
            "status": "healthy",
            "service": "config-version-manager"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
