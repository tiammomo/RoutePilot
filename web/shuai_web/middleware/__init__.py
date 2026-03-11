"""
================================================================================
中间件模块
================================================================================

提供 FastAPI 中间件，包括：
- 请求日志中间件
- 速率限制中间件
- 请求超时中间件

使用示例:
    from middleware import RequestLoggingMiddleware, RateLimitMiddleware

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=100, window=60)

================================================================================
"""

import time
import logging
from collections import defaultdict
from collections import deque
from typing import Callable, Deque, Dict, Optional
from typing import TypeVar

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# 类型变量
F = TypeVar('F', bound=Callable)


# =============================================================================
# 请求日志中间件
# =============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件

    记录每个请求的以下信息：
    - 请求方法、路径
    - 客户端 IP
    - 响应状态码
    - 处理耗时
    """

    def __init__(self, app: ASGIApp, logger_name: str = "web.request"):
        """Initialize RequestLoggingMiddleware and prepare runtime dependencies.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            app: Input `app` consumed by this method.
            logger_name: Input `logger_name` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
        """
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录开始时间
        """Execute dispatch in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            request: Input `request` consumed by this method.
            call_next: Input `call_next` consumed by this method.
        
        Returns:
            Response: Result value produced by this method.
        """
        start_time = time.perf_counter()

        # 获取请求信息
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        query_params = str(request.query_params) if request.query_params else ""

        # 处理请求
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            self.logger.exception(f"Request failed: {method} {path}")
            raise

        # 计算耗时
        duration = (time.perf_counter() - start_time) * 1000

        # 记录日志
        self.logger.info(
            f"{method} {path}{query_params} | "
            f"status={status_code} | "
            f"duration={duration:.2f}ms | "
            f"client={client_ip}"
        )

        # 添加耗时 header
        response.headers["X-Process-Time"] = f"{duration:.2f}ms"

        return response


# =============================================================================
# 速率限制中间件
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    速率限制中间件

    基于滑动窗口算法实现请求速率限制。
    支持按 IP 或自定义键进行限制。

    配置参数:
        max_requests: 时间窗口内允许的最大请求数
        window: 时间窗口大小（秒）
        key_func: 自定义键函数，默认按 IP
        exclude_paths: 排除的路径列表
    """

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 100,
        window: int = 60,
        key_func: Optional[Callable[[Request], str]] = None,
        exclude_paths: Optional[list] = None
    ):
        """Initialize RateLimitMiddleware and prepare runtime dependencies.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            app: Input `app` consumed by this method.
            max_requests: Input `max_requests` consumed by this method.
            window: Input `window` consumed by this method.
            key_func: Input `key_func` consumed by this method.
            exclude_paths: Input `exclude_paths` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
        """
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self.key_func = key_func or self._default_key_func
        self.exclude_paths = exclude_paths or [
            "/",
            "/docs",
            "/redoc",
            "/rapidoc",
            "/openapi.json",
            "/api/health"
        ]

        # 存储请求记录：{key: deque([timestamp1, timestamp2, ...])}
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)

    def _default_key_func(self, request: Request) -> str:
        """默认键函数：使用客户端 IP"""
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, key: str, current_time: float) -> None:
        """清理过期的请求记录"""
        requests = self._requests[key]
        window_start = current_time - self.window

        # 移除超过窗口期的请求记录
        while requests and requests[0] < window_start:
            requests.popleft()

        # 如果没有记录了，删除键
        if not requests:
            del self._requests[key]

    def _check_rate_limit(self, key: str) -> tuple[bool, int]:
        """
        检查速率限制

        Returns:
            (是否允许, 剩余请求数)
        """
        current_time = time.time()
        self._clean_old_requests(key, current_time)

        requests = self._requests[key]
        current_count = len(requests)
        remaining = self.max_requests - current_count

        if current_count >= self.max_requests:
            return False, 0

        # 记录本次请求
        requests.append(current_time)
        return True, remaining

    def _is_excluded(self, path: str) -> bool:
        """检查路径是否排除限流"""
        for exclude in self.exclude_paths:
            if path.startswith(exclude):
                return True
        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 排除的路径直接通过
        """Execute dispatch in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            request: Input `request` consumed by this method.
            call_next: Input `call_next` consumed by this method.
        
        Returns:
            Response: Result value produced by this method.
        """
        if self._is_excluded(request.url.path):
            return await call_next(request)

        # 获取限流键
        key = self.key_func(request)

        # 检查速率限制
        allowed, remaining = self._check_rate_limit(key)

        if not allowed:
            # 返回 429 响应
            response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window} seconds.",
                        "details": {
                            "max_requests": self.max_requests,
                            "window_seconds": self.window
                        }
                    }
                }
            )
            response.headers["X-RateLimit-Limit"] = str(self.max_requests)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.window))
            return response

        # 处理请求
        response = await call_next(request)

        # 添加限流相关 headers
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + self.window))

        return response


# =============================================================================
# 请求超时中间件
# =============================================================================

class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    请求超时中间件

    为请求设置最大处理时间限制。
    """

    def __init__(self, app: ASGIApp, timeout: float = 30.0):
        """Initialize TimeoutMiddleware and prepare runtime dependencies.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            app: Input `app` consumed by this method.
            timeout: Input `timeout` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
        """
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Execute dispatch in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            request: Input `request` consumed by this method.
            call_next: Input `call_next` consumed by this method.
        
        Returns:
            Response: Result value produced by this method.
        """
        import asyncio

        try:
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Request timeout: {request.method} {request.url.path}")
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": f"Request processing timeout after {self.timeout} seconds"
                    }
                }
            )


# =============================================================================
# 便捷函数
# =============================================================================

def setup_middleware(app: FastAPI) -> None:
    """
    配置所有中间件

    Args:
        app: FastAPI 应用实例
    """
    # 添加请求日志中间件
    app.add_middleware(RequestLoggingMiddleware)

    # 添加速率限制中间件（100 请求/分钟）
    app.add_middleware(RateLimitMiddleware, max_requests=100, window=60)

    # 添加超时中间件（30 秒）
    app.add_middleware(TimeoutMiddleware, timeout=30.0)


__all__ = [
    "RequestLoggingMiddleware",
    "RateLimitMiddleware",
    "TimeoutMiddleware",
    "setup_middleware",
]
