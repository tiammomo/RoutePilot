"""
================================================================================
API 限流模块 (API Rate Limiter)

提供基于 Redis 的多种限流算法，支持：
- 固定窗口限流
- 滑动窗口限流
- 令牌桶限流
- 分布式限流

使用示例:
```python
from infrastructure.rate_limiter import RateLimiter, FixedWindowLimiter

# 固定窗口限流 (每分钟 60 次)
limiter = FixedWindowLimiter(rate=60, window=60)
allowed = await limiter.allow_request(user_id)

# 滑动窗口限流
limiter = SlidingWindowLimiter(rate=60, window=60)
allowed = await limiter.allow_request(user_id)

# 令牌桶限流
limiter = TokenBucketLimiter(rate=10, burst=20)
allowed, remaining = await limiter.allow_request(user_id)
```

================================================================================
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """限流策略"""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"


@dataclass
class RateLimitResult:
    """限流结果"""
    allowed: bool
    remaining: int
    reset_at: float
    limit: int
    strategy: str

    @property
    def retry_after(self) -> Optional[float]:
        if self.allowed:
            return None
        return max(0, self.reset_at - time.time())


@dataclass
class RateLimitConfig:
    """限流配置"""
    rate: int = 60  # 速率 (请求数/窗口)
    window: int = 60  # 窗口大小 (秒)
    burst: Optional[int] = None  # 突发容量
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    prefix: str = "ratelimit"


class BaseRateLimiter(ABC):
    """限流器基类"""

    def __init__(self, config: RateLimitConfig, redis_client: Optional[redis.Redis] = None):
        self.config = config
        self._client: Optional[redis.Redis] = redis_client

    @property
    @abstractmethod
    def client(self) -> redis.Redis:
        pass

    @abstractmethod
    async def allow_request(self, identifier: str) -> RateLimitResult:
        """检查是否允许请求"""
        pass

    @abstractmethod
    async def get_usage(self, identifier: str) -> Tuple[int, float]:
        """获取当前使用量"""
        pass


class FixedWindowLimiter(BaseRateLimiter):
    """
    固定窗口限流器

    将时间划分为固定窗口，在每个窗口内限制请求数量。
    优点：实现简单，内存占用低
    缺点：窗口边界可能出现突发流量
    """

    def __init__(
        self,
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ):
        super().__init__(config, redis_client)
        self._client: Optional[redis.Redis] = redis_client

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._client

    def _get_window_key(self, identifier: str) -> str:
        """获取窗口键"""
        current_window = int(time.time() / self.config.window)
        return f"{self.config.prefix}:fixed:{identifier}:{current_window}"

    async def allow_request(self, identifier: str) -> RateLimitResult:
        """检查是否允许请求"""
        window_key = self._get_window_key(identifier)

        try:
            pipe = self.client.pipeline()
            pipe.incr(window_key)
            pipe.ttl(window_key)
            results = await pipe.execute()

            current = results[0]
            ttl = results[1]

            # 如果是新窗口，设置过期时间
            if ttl == -1:
                await self.client.expire(window_key, self.config.window)

            limit = self.config.rate
            remaining = max(0, limit - current)
            allowed = current <= limit

            reset_at = time.time() + (ttl if ttl > 0 else self.config.window)

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_at=reset_at,
                limit=limit,
                strategy=RateLimitStrategy.FIXED_WINDOW.value
            )

        except Exception as e:
            logger.error(f"[FixedWindowLimiter] 限流检查失败: {e}")
            # 出错时允许请求（降级策略）
            return RateLimitResult(
                allowed=True,
                remaining=self.config.rate,
                reset_at=time.time() + self.config.window,
                limit=self.config.rate,
                strategy=RateLimitStrategy.FIXED_WINDOW.value
            )

    async def get_usage(self, identifier: str) -> Tuple[int, float]:
        """获取当前使用量"""
        window_key = self._get_window_key(identifier)
        try:
            current = await self.client.get(window_key)
            current = int(current) if current else 0
            ttl = await self.client.ttl(window_key)
            reset_at = time.time() + (ttl if ttl > 0 else self.config.window)
            return current, reset_at
        except Exception as e:
            logger.error(f"[FixedWindowLimiter] 获取使用量失败: {e}")
            return 0, time.time()


class SlidingWindowLimiter(BaseRateLimiter):
    """
    滑动窗口限流器

    使用 Redis Sorted Set 实现精确的滑动窗口限流。
    优点：限流精确，避免边界突发
    缺点：内存占用较高
    """

    def __init__(
        self,
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ):
        super().__init__(config, redis_client)
        self._client: Optional[redis.Redis] = redis_client

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._client

    def _get_window_key(self, identifier: str) -> str:
        """获取窗口键"""
        return f"{self.config.prefix}:sliding:{identifier}"

    async def allow_request(self, identifier: str) -> RateLimitResult:
        """检查是否允许请求"""
        window_key = self._get_window_key(identifier)
        now = time.time()
        window_start = now - self.config.window

        try:
            pipe = self.client.pipeline()

            # 删除窗口外的请求记录
            pipe.zremrangebyscore(window_key, 0, window_start)

            # 统计当前窗口内的请求数
            pipe.zcard(window_key)

            # 添加当前请求
            member = f"{now}:{hashlib.md5(str(now).encode()).hexdigest()[:8]}"
            pipe.zadd(window_key, {member: now})

            # 设置过期时间
            pipe.expire(window_key, self.config.window + 1)

            results = await pipe.execute()
            current = results[1]

            limit = self.config.rate
            remaining = max(0, limit - current)
            allowed = current <= limit

            reset_at = now + self.config.window

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_at=reset_at,
                limit=limit,
                strategy=RateLimitStrategy.SLIDING_WINDOW.value
            )

        except Exception as e:
            logger.error(f"[SlidingWindowLimiter] 限流检查失败: {e}")
            return RateLimitResult(
                allowed=True,
                remaining=self.config.rate,
                reset_at=time.time() + self.config.window,
                limit=self.config.rate,
                strategy=RateLimitStrategy.SLIDING_WINDOW.value
            )

    async def get_usage(self, identifier: str) -> Tuple[int, float]:
        """获取当前使用量"""
        window_key = self._get_window_key(identifier)
        now = time.time()
        window_start = now - self.config.window

        try:
            # 清理过期记录并统计
            await self.client.zremrangebyscore(window_key, 0, window_start)
            count = await self.client.zcard(window_key)
            return count, now + self.config.window
        except Exception as e:
            logger.error(f"[SlidingWindowLimiter] 获取使用量失败: {e}")
            return 0, time.time()

    async def reset(self, identifier: str) -> bool:
        """重置限流器"""
        try:
            window_key = self._get_window_key(identifier)
            await self.client.delete(window_key)
            return True
        except Exception as e:
            logger.error(f"[SlidingWindowLimiter] 重置失败: {e}")
            return False


class TokenBucketLimiter(BaseRateLimiter):
    """
    令牌桶限流器

    以恒定速率添加令牌，请求需要获取令牌。
    优点：允许突发流量
    缺点：实现稍复杂
    """

    def __init__(
        self,
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ):
        super().__init__(config, redis_client)
        self._client: Optional[redis.Redis] = redis_client
        self._burst = config.burst or config.rate

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._client

    def _get_bucket_key(self, identifier: str) -> str:
        """获取桶键"""
        return f"{self.config.prefix}:token:{identifier}"

    async def allow_request(self, identifier: str) -> RateLimitResult:
        """检查是否允许请求"""
        bucket_key = self._get_bucket_key(identifier)
        now = time.time()

        # 令牌添加速率 (令牌/秒)
        rate = self.config.rate
        burst = self._burst

        try:
            pipe = self.client.pipeline()

            # 获取当前令牌数和最后添加时间
            pipe.hgetall(bucket_key)
            results = await pipe.execute()

            current_tokens = burst
            last_update = now

            if results and results[0]:
                bucket_data = results[0]
                last_update = float(bucket_data.get('last_update', now))
                tokens = float(bucket_data.get('tokens', burst))
                current_tokens = min(burst, tokens + (now - last_update) * rate)

            # 尝试获取令牌
            if current_tokens >= 1:
                new_tokens = current_tokens - 1
                allowed = True
            else:
                new_tokens = current_tokens
                allowed = False

            remaining = int(new_tokens)

            # 更新桶状态
            await self.client.hset(bucket_key, mapping={
                'tokens': str(new_tokens),
                'last_update': str(now)
            })
            await self.client.expire(bucket_key, int(self.config.window * 2))

            # 计算需要等待的时间（如果不允许）
            if not allowed:
                tokens_needed = 1 - current_tokens
                wait_time = tokens_needed / rate
                reset_at = now + wait_time
            else:
                reset_at = now + ((new_tokens + 1) / rate) if new_tokens < burst else now

            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_at=reset_at,
                limit=burst,
                strategy=RateLimitStrategy.TOKEN_BUCKET.value
            )

        except Exception as e:
            logger.error(f"[TokenBucketLimiter] 限流检查失败: {e}")
            return RateLimitResult(
                allowed=True,
                remaining=burst,
                reset_at=now,
                limit=burst,
                strategy=RateLimitStrategy.TOKEN_BUCKET.value
            )

    async def get_usage(self, identifier: str) -> Tuple[int, float]:
        """获取当前令牌数"""
        bucket_key = self._get_bucket_key(identifier)
        now = time.time()

        try:
            bucket_data = await self.client.hgetall(bucket_key)
            if not bucket_data:
                return self._burst, now

            last_update = float(bucket_data.get('last_update', now))
            tokens = float(bucket_data.get('tokens', self._burst))
            current_tokens = min(self._burst, tokens + (now - last_update) * self.config.rate)

            return int(current_tokens), now

        except Exception as e:
            logger.error(f"[TokenBucketLimiter] 获取使用量失败: {e}")
            return self._burst, now

    async def reset(self, identifier: str) -> bool:
        """重置令牌桶"""
        try:
            bucket_key = self._get_bucket_key(identifier)
            await self.client.delete(bucket_key)
            return True
        except Exception as e:
            logger.error(f"[TokenBucketLimiter] 重置失败: {e}")
            return False


# =============================================================================
# 限流中间件
# =============================================================================

class RateLimitMiddleware:
    """
    限流中间件

    集成到 FastAPI 应用中，提供装饰器和依赖注入。
    """

    def __init__(
        self,
        rate: int = 60,
        window: int = 60,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW,
        redis_host: str = "localhost",
        redis_port: int = 6379
    ):
        """
        初始化限流中间件

        Args:
            rate: 速率 (请求数/窗口)
            window: 窗口大小 (秒)
            strategy: 限流策略
            redis_host: Redis 主机
            redis_port: Redis 端口
        """
        self.config = RateLimitConfig(
            rate=rate,
            window=window,
            strategy=strategy
        )
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._limiter: Optional[BaseRateLimiter] = None

    @property
    def limiter(self) -> BaseRateLimiter:
        """获取限流器"""
        if self._limiter is None:
            if self.config.strategy == RateLimitStrategy.FIXED_WINDOW:
                self._limiter = FixedWindowLimiter(self.config)
            elif self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
                self._limiter = TokenBucketLimiter(self.config)
            else:
                self._limiter = SlidingWindowLimiter(self.config)
        return self._limiter

    async def check_limit(self, identifier: str) -> RateLimitResult:
        """检查限流"""
        return await self.limiter.allow_request(identifier)

    def get_identifier(self, request: Any) -> str:
        """从请求中提取标识符"""
        # 默认使用 IP 地址
        if hasattr(request, 'client'):
            return f"ip:{request.client.host}"

        # 尝试获取 header 中的用户 ID
        if hasattr(request, 'headers'):
            user_id = request.headers.get('X-User-ID')
            if user_id:
                return f"user:{user_id}"

        return f"anonymous:{id(request)}"


# =============================================================================
# 便捷函数
# =============================================================================

def create_rate_limiter(
    rate: int = 60,
    window: int = 60,
    strategy: str = "sliding_window",
    host: str = "localhost",
    port: int = 6379
) -> BaseRateLimiter:
    """
    创建限流器

    Args:
        rate: 速率 (请求数/窗口)
        window: 窗口大小 (秒)
        strategy: 限流策略
        host: Redis 主机
        port: Redis 端口

    Returns:
        BaseRateLimiter: 限流器实例
    """
    config = RateLimitConfig(
        rate=rate,
        window=window,
        strategy=RateLimitStrategy(strategy)
    )

    if strategy == "fixed_window":
        return FixedWindowLimiter(config)
    elif strategy == "token_bucket":
        return TokenBucketLimiter(config)
    else:
        return SlidingWindowLimiter(config)


async def check_rate_limit_health() -> Dict[str, Any]:
    """
    检查限流服务健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        limiter = create_rate_limiter()
        if hasattr(limiter, 'client'):
            await limiter.client.ping()
            return {"status": "healthy"}
        return {"status": "healthy", "note": "local mode"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# 别名
RateLimiter = SlidingWindowLimiter
