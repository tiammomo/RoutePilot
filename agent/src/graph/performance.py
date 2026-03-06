"""
================================================================================
LangGraph Agent 性能优化模块
================================================================================

提供性能优化功能：
- 缓存管理
- 并发控制
- 资源池
- 性能监控

================================================================================
"""

import asyncio
import logging
import time
import weakref
from collections import OrderedDict
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple
from datetime import datetime, timedelta
import hashlib
import json

logger = logging.getLogger(__name__)


# ============================================================================
# LRU 缓存
# ============================================================================

class LRUCache:
    """
    LRU 缓存实现

    支持 TTL（生存时间）和最大容量限制
    """

    def __init__(self, max_size: int = 100, ttl_seconds: Optional[float] = None):
        """
        初始化

        Args:
            max_size: 最大缓存数量
            ttl_seconds: 缓存生存时间（秒），None 表示无限制
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self._cache:
            self._misses += 1
            return None

        # 检查 TTL
        if self.ttl_seconds:
            timestamp = self._timestamps.get(key, 0)
            if time.time() - timestamp > self.ttl_seconds:
                self._delete(key)
                self._misses += 1
                return None

        # 移到末尾（最近使用）
        self._cache.move_to_end(key)
        self._hits += 1
        return self._cache[key]

    def set(self, key: str, value: Any):
        """设置缓存"""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                # 删除最旧的
                oldest = next(iter(self._cache))
                self._delete(oldest)

        self._cache[key] = value
        self._timestamps[key] = time.time()

    def _delete(self, key: str):
        """删除缓存项"""
        if key in self._cache:
            del self._cache[key]
        if key in self._timestamps:
            del self._timestamps[key]

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.2%}"
        }


# ============================================================================
# 语义缓存
# ============================================================================

class SemanticCache:
    """
    语义缓存

    基于 LLM 输出的相似度缓存，减少重复调用
    """

    def __init__(self, similarity_threshold: float = 0.9):
        """
        初始化

        Args:
            similarity_threshold: 相似度阈值
        """
        self.similarity_threshold = similarity_threshold
        self._cache: Dict[str, Tuple[Any, float]] = {}

    def _make_key(self, prompt: str) -> str:
        """生成缓存键（使用 prompt 的前 N 个字符作为键）"""
        # 简化：使用 prompt 的哈希
        return hashlib.sha256(prompt.encode()).hexdigest()[:32]

    def get(self, prompt: str) -> Optional[Any]:
        """获取缓存"""
        key = self._make_key(prompt)
        if key in self._cache:
            cached_value, _ = self._cache[key]
            logger.info(f"[SemanticCache] Cache hit for key: {key[:8]}...")
            return cached_value
        return None

    def set(self, prompt: str, value: Any):
        """设置缓存"""
        key = self._make_key(prompt)
        self._cache[key] = (value, time.time())
        logger.info(f"[SemanticCache] Cached response for key: {key[:8]}...")

    def clear(self):
        """清空缓存"""
        self._cache.clear()


# ============================================================================
# 并发控制
# ============================================================================

class ConcurrencyLimiter:
    """
    并发限制器

    限制同时执行的任务数量
    """

    def __init__(self, max_concurrent: int = 10):
        """
        初始化

        Args:
            max_concurrent: 最大并发数
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0

    async def __aenter__(self):
        await self._semaphore.acquire()
        self._active += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._active -= 1
        self._semaphore.release()

    @property
    def active_count(self) -> int:
        """当前活跃任务数"""
        return self._active

    @property
    def available_slots(self) -> int:
        """可用槽位"""
        return max(0, self.max_concurrent - self._active)


class RateLimiter:
    """
    速率限制器

    限制每秒钟的请求数
    """

    def __init__(self, rate: float = 10.0, burst: int = 20):
        """
        初始化

        Args:
            rate: 每秒请求数
            burst: 突发容量
        """
        self.rate = rate
        self.burst = burst
        self._tokens = burst
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1):
        """获取令牌"""
        async with self._lock:
            while self._tokens < tokens:
                await asyncio.sleep(0.01)
                self._refill()

            self._tokens -= tokens

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_update = now

    @property
    def available_tokens(self) -> float:
        """可用令牌数"""
        self._refill()
        return self._tokens


# ============================================================================
# 资源池
# ============================================================================

class ObjectPool:
    """
    对象池

    复用对象以减少创建开销
    """

    def __init__(self, factory: Callable, max_size: int = 10):
        """
        初始化

        Args:
            factory: 对象工厂函数
            max_size: 池最大容量
        """
        self.factory = factory
        self.max_size = max_size
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._created = 0

    async def acquire(self) -> Any:
        """获取对象"""
        try:
            obj = self._pool.get_nowait()
            logger.debug(f"[ObjectPool] Reused object (pool size: {self._pool.qsize()})")
            return obj
        except asyncio.QueueEmpty:
            if self._created < self.max_size:
                self._created += 1
                obj = await self._factory_wrapper()
                logger.debug(f"[ObjectPool] Created new object (total: {self._created})")
                return obj
            else:
                # 等待回收
                obj = await self._pool.get()
                logger.debug(f"[ObjectPool] Waited for object (pool size: {self._pool.qsize()})")
                return obj

    async def _factory_wrapper(self) -> Any:
        """工厂包装（支持异步）"""
        result = await self.factory()
        if asyncio.iscoroutine(result):
            return await result
        return result

    def release(self, obj: Any):
        """释放对象"""
        try:
            self._pool.put_nowait(obj)
            logger.debug(f"[ObjectPool] Released object (pool size: {self._pool.qsize()})")
        except asyncio.QueueFull:
            logger.debug(f"[ObjectPool] Pool full, discarding object")

    async def close(self):
        """关闭池"""
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._created = 0


# ============================================================================
# 性能监控
# ============================================================================

class PerformanceMonitor:
    """
    性能监控器

    记录和统计执行时间
    """

    def __init__(self):
        self._metrics: Dict[str, list] = {}
        self._start_times: Dict[str, float] = {}

    def start(self, operation: str):
        """开始计时"""
        self._start_times[operation] = time.time()

    def end(self, operation: str):
        """结束计时"""
        if operation not in self._start_times:
            return

        elapsed = time.time() - self._start_times[operation]

        if operation not in self._metrics:
            self._metrics[operation] = []

        self._metrics[operation].append(elapsed)
        del self._start_times[operation]

    def get_stats(self, operation: str) -> Optional[dict]:
        """获取统计"""
        if operation not in self._metrics:
            return None

        times = self._metrics[operation]
        return {
            "count": len(times),
            "total": sum(times),
            "avg": sum(times) / len(times),
            "min": min(times),
            "max": max(times)
        }

    def get_all_stats(self) -> dict:
        """获取所有统计"""
        return {
            operation: self.get_stats(operation)
            for operation in self._metrics
        }

    def reset(self):
        """重置统计"""
        self._metrics.clear()
        self._start_times.clear()


# ============================================================================
# 性能装饰器
# ============================================================================

def timed(operation_name: Optional[str] = None):
    """性能计时装饰器"""
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__name__

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(f"[Timed] {op_name} completed in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"[Timed] {op_name} failed after {elapsed:.3f}s: {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                logger.info(f"[Timed] {op_name} completed in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"[Timed] {op_name} failed after {elapsed:.3f}s: {e}")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def cached(cache: LRUCache):
    """缓存装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = cache._make_key(*args, **kwargs)
            result = cache.get(key)

            if result is not None:
                return result

            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            cache.set(key, result)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = cache._make_key(*args, **kwargs)
            result = cache.get(key)

            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.set(key, result)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# 全局单例
# ============================================================================

_llm_cache: Optional[LRUCache] = None
_semantic_cache: Optional[SemanticCache] = None
_performance_monitor: Optional[PerformanceMonitor] = None


def get_llm_cache() -> LRUCache:
    """获取 LLM 响应缓存"""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LRUCache(max_size=200, ttl_seconds=3600)
    return _llm_cache


def get_semantic_cache() -> SemanticCache:
    """获取语义缓存"""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache()
    return _semantic_cache


def get_performance_monitor() -> PerformanceMonitor:
    """获取性能监控器"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor
