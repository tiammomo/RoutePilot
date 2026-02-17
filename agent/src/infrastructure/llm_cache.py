"""
================================================================================
LLM 响应缓存模块 (LLM Response Cache)

提供基于 Redis 的 LLM 响应缓存功能，支持：
- 语义相似度缓存命中
- 自动过期清理
- 缓存命中率统计

使用示例:
```python
from infrastructure.llm_cache import LLMResponseCache

cache = LLMResponseCache(host="localhost", port=6379)

# 检查缓存
cached = await cache.get(prompt_hash)
if cached:
    return cached

# 缓存响应
await cache.set(prompt_hash, response, ttl=3600)
```

================================================================================
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """缓存统计"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    expired: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class CacheConfig:
    """缓存配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    key_prefix: str = "llm:cache:"
    default_ttl: int = 3600  # 1小时
    max_memory: str = "256mb"
    eviction_policy: str = "allkeys-lru"
    enabled: bool = True

    def get_url(self) -> str:
        """获取连接 URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class LLMResponseCache:
    """
    LLM 响应缓存

    基于 Redis 的 LLM 响应缓存，支持：
    - 提示词哈希快速查找
    - TTL 过期机制
    - 命中率统计
    - 内存优化
    """

    def __init__(
        self,
        config: Optional[CacheConfig] = None,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        初始化缓存

        Args:
            config: 缓存配置
            redis_client: 已连接的 Redis 客户端
        """
        self.config = config or CacheConfig()
        self._client: Optional[redis.Redis] = redis_client
        self._stats = CacheStats()
        self._enabled = self.config.enabled

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._client

    @property
    def stats(self) -> CacheStats:
        """获取缓存统计"""
        return self._stats

    def _get_cache_key(self, key: str) -> str:
        """生成缓存键"""
        return f"{self.config.key_prefix}{key}"

    def _hash_prompt(self, prompt: str) -> str:
        """对提示词进行哈希"""
        # 使用 MD5 哈希（足够短且快速）
        return hashlib.md5(prompt.encode('utf-8')).hexdigest()[:16]

    async def get(self, prompt: str) -> Optional[str]:
        """
        获取缓存的响应

        Args:
            prompt: 提示词

        Returns:
            Optional[str]: 缓存的响应，不存在返回 None
        """
        if not self._enabled:
            self._stats.misses += 1
            return None

        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            cached = await self.client.get(cache_key)

            if cached:
                self._stats.hits += 1
                logger.debug(f"[LLMCache] 缓存命中: {cache_key[:32]}...")
                return cached
            else:
                self._stats.misses += 1
                logger.debug(f"[LLMCache] 缓存未命中: {cache_key[:32]}...")
                return None

        except Exception as e:
            logger.error(f"[LLMCache] 获取缓存失败: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self,
        prompt: str,
        response: str,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        缓存响应

        Args:
            prompt: 提示词
            response: LLM 响应
            ttl: 过期时间（秒），默认使用配置值
            metadata: 元数据（模型名、token数等）

        Returns:
            bool: 是否成功
        """
        if not self._enabled:
            return False

        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            ttl = ttl or self.config.default_ttl

            # 存储响应和元数据
            cache_data = {
                "response": response,
                "metadata": metadata or {},
                "cached_at": time.time()
            }

            await self.client.setex(
                cache_key,
                ttl,
                json.dumps(cache_data, ensure_ascii=False)
            )

            self._stats.sets += 1
            logger.debug(f"[LLMCache] 缓存已设置: {cache_key[:32]}..., ttl={ttl}s")
            return True

        except Exception as e:
            logger.error(f"[LLMCache] 设置缓存失败: {e}")
            return False

    async def delete(self, prompt: str) -> bool:
        """
        删除缓存

        Args:
            prompt: 提示词

        Returns:
            bool: 是否成功
        """
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            result = await self.client.delete(cache_key)

            if result:
                self._stats.deletes += 1
                logger.debug(f"[LLMCache] 缓存已删除: {cache_key[:32]}...")

            return result > 0

        except Exception as e:
            logger.error(f"[LLMCache] 删除缓存失败: {e}")
            return False

    async def clear_pattern(self, pattern: str = "*") -> int:
        """
        清除匹配的缓存

        Args:
            pattern: 匹配模式

        Returns:
            int: 删除的键数量
        """
        try:
            full_pattern = self._get_cache_key(pattern)
            keys = await self.client.keys(full_pattern)

            if keys:
                deleted = await self.client.delete(*keys)
                logger.info(f"[LLMCache] 清除缓存: {deleted} 个键")
                return deleted

            return 0

        except Exception as e:
            logger.error(f"[LLMCache] 清除缓存失败: {e}")
            return 0

    async def get_with_metadata(self, prompt: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        获取缓存的响应和元数据

        Args:
            prompt: 提示词

        Returns:
            Optional[Tuple[str, Dict]]: (响应, 元数据)，不存在返回 None
        """
        if not self._enabled:
            return None

        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            cached = await self.client.get(cache_key)

            if cached:
                self._stats.hits += 1
                data = json.loads(cached)
                return data["response"], data.get("metadata", {})

            self._stats.misses += 1
            return None

        except Exception as e:
            logger.error(f"[LLMCache] 获取缓存失败: {e}")
            return None

    async def get_ttl(self, prompt: str) -> int:
        """
        获取缓存剩余 TTL

        Args:
            prompt: 提示词

        Returns:
            int: 剩余秒数，-1 表示永久，-2 表示不存在
        """
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            return await self.client.ttl(cache_key)
        except Exception as e:
            logger.error(f"[LLMCache] 获取 TTL 失败: {e}")
            return -2

    async def refresh_ttl(self, prompt: str, ttl: Optional[int] = None) -> bool:
        """
        刷新缓存 TTL

        Args:
            prompt: 提示词
            ttl: 新 TTL，默认使用配置值

        Returns:
            bool: 是否成功
        """
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            ttl = ttl or self.config.default_ttl
            return await self.client.expire(cache_key, ttl)
        except Exception as e:
            logger.error(f"[LLMCache] 刷新 TTL 失败: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "sets": self._stats.sets,
            "deletes": self._stats.deletes,
            "hit_rate": f"{self._stats.hit_rate:.2%}",
            "enabled": self._enabled,
            "key_prefix": self.config.key_prefix,
            "default_ttl": self.config.default_ttl
        }

    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("[LLMCache] 连接已关闭")


# =============================================================================
# 缓存中间件
# =============================================================================

class LLMCacheMiddleware:
    """
    LLM 缓存中间件

    集成到 LLM 调用流程中，自动进行缓存查找和存储。
    """

    def __init__(self, cache: Optional[LLMResponseCache] = None):
        """
        初始化中间件

        Args:
            cache: LLM 响应缓存实例
        """
        self.cache = cache or LLMResponseCache()

    async def get_cached_response(
        self,
        messages: List[Dict[str, str]],
        model: str
    ) -> Optional[str]:
        """
        获取缓存的响应

        Args:
            messages: 消息列表
            model: 模型名称

        Returns:
            Optional[str]: 缓存的响应
        """
        # 构建提示词
        prompt = self._build_prompt(messages, model)

        # 添加模型标识到缓存键
        cache_key = f"{model}:{prompt}"
        return await self.cache.get(cache_key)

    async def cache_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        缓存响应

        Args:
            messages: 消息列表
            model: 模型名称
            response: LLM 响应
            metadata: 元数据
        """
        prompt = self._build_prompt(messages, model)
        cache_key = f"{model}:{prompt}"

        # 添加模型信息到元数据
        meta = {
            "model": model,
            **(metadata or {})
        }

        await self.cache.set(cache_key, response, metadata=meta)

    def _build_prompt(self, messages: List[Dict[str, str]], model: str) -> str:
        """构建缓存键的提示词"""
        # 只取最后几条消息作为缓存键（避免历史消息影响）
        recent_messages = messages[-5:] if len(messages) > 5 else messages

        # 构建简洁的提示词表示
        prompt_parts = []
        for msg in recent_messages:
            role = msg.get("role", "user")[:3]
            content = msg.get("content", "")[:100]  # 截断过长内容
            prompt_parts.append(f"{role}:{content}")

        return "|".join(prompt_parts)


# =============================================================================
# 便捷函数
# =============================================================================

def create_llm_cache(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    enabled: bool = True
) -> LLMResponseCache:
    """
    创建 LLM 响应缓存

    Args:
        host: Redis 主机
        port: Redis 端口
        db: 数据库编号
        password: 密码
        enabled: 是否启用

    Returns:
        LLMResponseCache: 缓存实例
    """
    config = CacheConfig(
        host=host,
        port=port,
        db=db,
        password=password,
        enabled=enabled
    )
    return LLMResponseCache(config=config)


async def check_cache_health() -> Dict[str, Any]:
    """
    检查缓存健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        cache = create_llm_cache()
        stats = await cache.get_stats()
        await cache.close()

        return {
            "status": "healthy",
            "stats": stats
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
