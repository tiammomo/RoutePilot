"""
================================================================================
LLM 响应缓存模块 (LLM Response Cache)

提供基于内存的 LLM 响应缓存功能，支持：
- 提示词哈希快速查找
- TTL 过期机制
- 缓存命中率统计
- LRU 淘汰策略

注意: 已移除 Redis 依赖，使用纯内存存储

使用示例:
```python
from infrastructure.llm_cache import LLMResponseCache

cache = LLMResponseCache()

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
import threading
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict

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
    key_prefix: str = "llm:cache:"
    default_ttl: int = 3600  # 1小时
    max_size: int = 1000  # 最大缓存条目数
    enabled: bool = True


class MemoryCache:
    """简单的内存缓存实现，支持 TTL 和 LRU"""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self._cache: OrderedDict = OrderedDict()
        self._expiry: Dict[str, float] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        """获取缓存值"""
        with self._lock:
            if key not in self._cache:
                return None
            # 检查过期
            if key in self._expiry and time.time() > self._expiry[key]:
                del self._cache[key]
                del self._expiry[key]
                return None
            # 移动到末尾（LRU）
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                # LRU 淘汰
                while len(self._cache) >= self._max_size:
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                    if oldest_key in self._expiry:
                        del self._expiry[oldest_key]
            self._cache[key] = value
            ttl = ttl or self._default_ttl
            self._expiry[key] = time.time() + ttl

    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._expiry:
                    del self._expiry[key]
                return True
            return False

    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配的键"""
        with self._lock:
            # 简单实现，不支持通配符
            if pattern == "*":
                return list(self._cache.keys())
            return [k for k in self._cache.keys() if pattern in k]

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._expiry.clear()

    def cleanup_expired(self) -> int:
        """清理过期项"""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, exp in self._expiry.items() if now > exp]
            for key in expired_keys:
                if key in self._cache:
                    del self._cache[key]
                del self._expiry[key]
            return len(expired_keys)


class LLMResponseCache:
    """
    LLM 响应缓存（内存版本）

    基于内存的 LLM 响应缓存，支持：
    - 提示词哈希快速查找
    - TTL 过期机制
    - 命中率统计
    - LRU 内存优化
    """

    def __init__(
        self,
        config: Optional[CacheConfig] = None,
        memory_cache: Optional[MemoryCache] = None
    ):
        """
        初始化缓存

        Args:
            config: 缓存配置
            memory_cache: 内存缓存实例
        """
        self.config = config or CacheConfig()
        self._cache = memory_cache or MemoryCache(
            max_size=self.config.max_size,
            default_ttl=self.config.default_ttl
        )
        self._stats = CacheStats()
        self._enabled = self.config.enabled

    @property
    def stats(self) -> CacheStats:
        """获取缓存统计"""
        return self._stats

    def _get_cache_key(self, key: str) -> str:
        """生成缓存键"""
        return f"{self.config.key_prefix}{key}"

    def _hash_prompt(self, prompt: str) -> str:
        """对提示词进行哈希"""
        return hashlib.md5(prompt.encode('utf-8')).hexdigest()[:16]

    async def get(self, prompt: str) -> Optional[str]:
        """获取缓存的响应"""
        if not self._enabled:
            self._stats.misses += 1
            return None

        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            cached = self._cache.get(cache_key)

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
        """缓存响应"""
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

            self._cache.set(cache_key, json.dumps(cache_data, ensure_ascii=False), ttl)
            self._stats.sets += 1
            logger.debug(f"[LLMCache] 缓存已设置: {cache_key[:32]}..., ttl={ttl}s")
            return True

        except Exception as e:
            logger.error(f"[LLMCache] 设置缓存失败: {e}")
            return False

    async def delete(self, prompt: str) -> bool:
        """删除缓存"""
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            result = self._cache.delete(cache_key)

            if result:
                self._stats.deletes += 1
                logger.debug(f"[LLMCache] 缓存已删除: {cache_key[:32]}...")

            return result

        except Exception as e:
            logger.error(f"[LLMCache] 删除缓存失败: {e}")
            return False

    async def clear_pattern(self, pattern: str = "*") -> int:
        """清除匹配的缓存"""
        try:
            full_pattern = self._get_cache_key(pattern)
            keys = self._cache.keys(full_pattern)

            deleted = 0
            for key in keys:
                if self._cache.delete(key):
                    deleted += 1

            if deleted:
                logger.info(f"[LLMCache] 清除缓存: {deleted} 个键")

            return deleted

        except Exception as e:
            logger.error(f"[LLMCache] 清除缓存失败: {e}")
            return 0

    async def get_with_metadata(self, prompt: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """获取缓存的响应和元数据"""
        if not self._enabled:
            return None

        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            cached = self._cache.get(cache_key)

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
        """获取缓存剩余 TTL"""
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            if cache_key not in self._cache._expiry:
                return -2
            remaining = self._cache._expiry[cache_key] - time.time()
            return max(0, int(remaining))
        except Exception as e:
            logger.error(f"[LLMCache] 获取 TTL 失败: {e}")
            return -2

    async def refresh_ttl(self, prompt: str, ttl: Optional[int] = None) -> bool:
        """刷新缓存 TTL"""
        try:
            cache_key = self._get_cache_key(self._hash_prompt(prompt))
            value = self._cache.get(cache_key)
            if value:
                ttl = ttl or self.config.default_ttl
                self._cache.set(cache_key, value, ttl)
                return True
            return False
        except Exception as e:
            logger.error(f"[LLMCache] 刷新 TTL 失败: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """清理过期缓存"""
        try:
            count = self._cache.cleanup_expired()
            self._stats.expired += count
            if count > 0:
                logger.info(f"[LLMCache] 清理过期缓存: {count} 个")
            return count
        except Exception as e:
            logger.error(f"[LLMCache] 清理过期缓存失败: {e}")
            return 0

    async def clear(self) -> bool:
        """清空所有缓存"""
        try:
            self._cache.clear()
            self._stats = CacheStats()
            logger.info("[LLMCache] 缓存已清空")
            return True
        except Exception as e:
            logger.error(f"[LLMCache] 清空缓存失败: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 清理过期缓存
            expired = await self.cleanup_expired()

            return {
                "status": "healthy",
                "enabled": self._enabled,
                "size": len(self._cache._cache),
                "stats": {
                    "hits": self._stats.hits,
                    "misses": self._stats.misses,
                    "sets": self._stats.sets,
                    "deletes": self._stats.deletes,
                    "expired": self._stats.expired,
                    "hit_rate": round(self._stats.hit_rate, 4)
                },
                "cleaned_expired": expired
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# 工厂函数
def create_llm_cache(config: Optional[CacheConfig] = None) -> LLMResponseCache:
    """创建 LLM 缓存实例"""
    return LLMResponseCache(config=config)


async def check_cache_health() -> Dict[str, Any]:
    """检查缓存健康状态"""
    cache = create_llm_cache()
    return await cache.health_check()


class LLMCacheMiddleware:
    """LLM 缓存中间件"""

    def __init__(self, cache: Optional[LLMResponseCache] = None):
        self.cache = cache or LLMResponseCache()

    async def process_request(self, prompt: str) -> Optional[str]:
        """处理请求，检查缓存"""
        return await self.cache.get(prompt)

    async def process_response(self, prompt: str, response: str, ttl: int = 3600) -> bool:
        """处理响应，设置缓存"""
        return await self.cache.set(prompt, response, ttl=ttl)


# 导出
__all__ = [
    'LLMResponseCache',
    'CacheConfig',
    'CacheStats',
    'MemoryCache',
    'LLMCacheMiddleware',
    'create_llm_cache',
    'check_cache_health'
]
