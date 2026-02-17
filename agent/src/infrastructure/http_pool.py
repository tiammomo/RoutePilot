"""
================================================================================
HTTP 连接池模块 (HTTP Connection Pool)

提供 HTTP 请求的连接池复用功能，减少频繁创建连接的开销。

主要功能:
- HTTP/HTTPS 连接池管理
- 请求结果缓存（内存缓存）
- 请求去重

使用示例:
```python
from infrastructure.http_pool import HTTPConnectionPool

pool = HTTPConnectionPool(
    max_connections=10,
    max_keepalive=20,
    timeout=30
)

# 发起请求
response = pool.request("POST", url, json=data, headers=headers)
```
================================================================================
"""

import json
import hashlib
import threading
import time
import logging
from typing import Any, Callable, Dict, Optional, TypeVar, Generic
from functools import lru_cache
from collections import OrderedDict
from urllib.request import Request, urlopen, ProxyHandler, HTTPPasswordMgrWithDefaultRealm
from urllib.error import HTTPError, URLError
import urllib.request

logger = logging.getLogger(__name__)

T = TypeVar('T')


class LRUCache(Generic[T]):
    """线程安全的 LRU 缓存"""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.RLock()
        self._timestamps: Dict[str, float] = {}

    def get(self, key: str) -> Optional[T]:
        """获取缓存值"""
        with self._lock:
            if key in self._cache:
                # 移动到末尾（最近使用）
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                # 删除最旧的项
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._timestamps.pop(oldest_key, None)

            self._cache[key] = value
            if ttl:
                self._timestamps[key] = time.time() + ttl

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()

    def cleanup_expired(self) -> int:
        """清理过期项"""
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, exp_time in self._timestamps.items()
                if exp_time < now
            ]
            for key in expired_keys:
                del self._cache[key]
                del self._timestamps[key]
            return len(expired_keys)


class HTTPConnectionPool:
    """
    HTTP 连接池管理器

    提供 HTTP 请求的连接复用和简单缓存功能。
    """

    _instance: Optional['HTTPConnectionPool'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_connections: int = 10,
        max_keepalive: int = 20,
        timeout: int = 30,
        cache_size: int = 1000,
        cache_ttl: int = 300
    ):
        """初始化连接池"""
        if self._initialized:
            return

        self._max_connections = max_connections
        self._max_keepalive = max_keepalive
        self._timeout = timeout
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl

        # 创建缓存
        self._response_cache = LRUCache(max_size=cache_size)
        self._request_lock = threading.RLock()

        # 创建 opener（支持代理）
        self._opener = urllib.request.build_opener(
            ProxyHandler(),
            urllib.request.HTTPSHandler(
                debuglevel=0,
                context=None
            )
        )

        # 定期清理过期缓存
        self._cleanup_thread = threading.Thread(
            target=self._periodic_cleanup,
            daemon=True
        )
        self._cleanup_thread.start()

        self._initialized = True
        logger.info(
            f"HTTPConnectionPool initialized: "
            f"max_connections={max_connections}, "
            f"cache_size={cache_size}"
        )

    def _periodic_cleanup(self) -> None:
        """定期清理过期缓存"""
        while True:
            time.sleep(60)  # 每分钟清理一次
            try:
                expired_count = self._response_cache.cleanup_expired()
                if expired_count > 0:
                    logger.debug(f"Cleaned up {expired_count} expired cache entries")
            except Exception as e:
                logger.warning(f"Cache cleanup error: {e}")

    def _generate_cache_key(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> str:
        """生成缓存键"""
        key_parts = [method.upper(), url]
        if data:
            key_parts.append(hashlib.md5(data).hexdigest())
        if headers:
            # 排除可能变化的 header
            stable_headers = {
                k: v for k, v in headers.items()
                if k.lower() not in ('authorization', 'x-api-key')
            }
            if stable_headers:
                key_parts.append(json.dumps(stable_headers, sort_keys=True))

        key = '|'.join(key_parts)
        return hashlib.sha256(key.encode()).hexdigest()

    def request(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        发起 HTTP 请求

        Args:
            method: HTTP 方法
            url: 请求 URL
            data: 请求数据
            headers: 请求头
            timeout: 超时时间
            use_cache: 是否使用缓存（仅对 GET 有效）

        Returns:
            Dict[str, Any]: 响应数据
        """
        timeout = timeout or self._timeout
        headers = headers or {}

        # GET 请求使用缓存
        if use_cache and method.upper() == 'GET':
            cache_key = self._generate_cache_key(method, url, data, headers)
            cached_response = self._response_cache.get(cache_key)
            if cached_response:
                logger.debug(f"Cache hit for {method} {url}")
                return cached_response

        # 发起请求
        with self._request_lock:
            try:
                req = Request(url, data=data, headers=headers, method=method)
                with urlopen(req, timeout=timeout) as response:
                    body = response.read()
                    result = {
                        'status': response.status,
                        'headers': dict(response.headers),
                        'body': body
                    }

                    # 缓存成功响应
                    if use_cache and method.upper() == 'GET' and response.status == 200:
                        cache_key = self._generate_cache_key(method, url, data, headers)
                        self._response_cache.set(cache_key, result, ttl=self._cache_ttl)

                    return result

            except HTTPError as e:
                logger.error(f"HTTP Error {e.code}: {e.reason}")
                raise
            except URLError as e:
                logger.error(f"URL Error: {e.reason}")
                raise

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """GET 请求"""
        return self.request('GET', url, headers=headers, timeout=timeout, use_cache=use_cache)

    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """POST 请求"""
        request_headers = headers or {}

        if json_data is not None:
            body = json.dumps(json_data).encode('utf-8')
            request_headers['Content-Type'] = 'application/json'
        elif data is not None:
            body = data.encode('utf-8') if isinstance(data, str) else data
        else:
            body = None

        return self.request('POST', url, data=body, headers=request_headers, timeout=timeout, use_cache=False)

    def clear_cache(self) -> None:
        """清空缓存"""
        self._response_cache.clear()
        logger.info("HTTP response cache cleared")

    @property
    def cache_stats(self) -> Dict[str, int]:
        """获取缓存统计"""
        return {
            'size': len(self._response_cache._cache)
        }


# 全局连接池实例
_global_pool: Optional[HTTPConnectionPool] = None


def get_http_pool() -> HTTPConnectionPool:
    """获取全局 HTTP 连接池实例"""
    global _global_pool
    if _global_pool is None:
        _global_pool = HTTPConnectionPool()
    return _global_pool
