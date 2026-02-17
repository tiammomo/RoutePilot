"""
================================================================================
基础设施层 - HTTP 客户端 (HTTP Client)

提供统一的 HTTP 客户端封装，支持连接池、重试、异步请求等功能。

功能特点:
- 同步/异步支持
- 连接池管理
- 自动重试机制
- 请求/响应拦截器
- 错误处理和超时控制

================================================================================
"""

import asyncio
import json
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime
from urllib.parse import urljoin
import aiohttp
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class HTTPMethod(Enum):
    """HTTP 方法"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HTTPContentType(Enum):
    """HTTP 内容类型"""
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    TEXT = "text/plain"
    HTML = "text/html"
    MULTIPART = "multipart/form-data"


@dataclass
class HTTPRequest:
    """HTTP 请求"""
    method: HTTPMethod
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    data: Any = None
    json_data: Any = None
    content_type: Optional[HTTPContentType] = None
    timeout: float = 30.0
    retry_count: int = 3
    follow_redirects: bool = True


@dataclass
class HTTPResponse:
    """HTTP 响应"""
    status_code: int
    text: str
    headers: Dict[str, str]
    url: str
    elapsed_ms: float
    request: HTTPRequest
    is_success: bool = True
    error: Optional[str] = None

    def json(self) -> Any:
        """解析 JSON"""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError:
            return None

    def raise_for_status(self) -> None:
        """检查状态码"""
        if not self.is_success:
            raise HTTPError(f"HTTP {self.status_code}: {self.text}", self)


class HTTPError(Exception):
    """HTTP 错误"""
    def __init__(self, message: str, response: HTTPResponse = None):
        super().__init__(message)
        self.response = response


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_attempts: int = 3,
        min_wait: float = 1.0,
        max_wait: float = 60.0,
        exponential_base: float = 2.0,
        retry_on_status: List[int] = None
    ):
        self.max_attempts = max_attempts
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.exponential_base = exponential_base
        self.retry_on_status = retry_on_status or [500, 502, 503, 504]


class RequestInterceptor:
    """请求拦截器"""

    def __init__(self):
        self._interceptors: List[Callable] = []

    def add(self, interceptor: Callable[[HTTPRequest], HTTPRequest]) -> None:
        """添加拦截器"""
        self._interceptors.append(interceptor)

    def execute(self, request: HTTPRequest) -> HTTPRequest:
        """执行所有拦截器"""
        for interceptor in self._interceptors:
            request = interceptor(request)
        return request


class ResponseInterceptor:
    """响应拦截器"""

    def __init__(self):
        self._interceptors: List[Callable] = []

    def add(self, interceptor: Callable[[HTTPResponse], HTTPResponse]) -> None:
        """添加拦截器"""
        self._interceptors.append(interceptor)

    def execute(self, response: HTTPResponse) -> HTTPResponse:
        """执行所有拦截器"""
        for interceptor in self._interceptors:
            response = interceptor(response)
        return response


class SyncHTTPClient:
    """
    同步 HTTP 客户端

    基于 httpx 的同步客户端，适合阻塞式调用。
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        retry_config: Optional[RetryConfig] = None,
        default_headers: Dict[str, str] = None
    ):
        """
        初始化客户端

        Args:
            base_url: 基础 URL
            timeout: 默认超时时间
            retry_config: 重试配置
            default_headers: 默认请求头
        """
        self.base_url = base_url
        self.default_timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.default_headers = default_headers or {}

        self._client: Optional[httpx.Client] = None
        self.request_interceptor = RequestInterceptor()
        self.response_interceptor = ResponseInterceptor()

    def _get_client(self) -> httpx.Client:
        """获取客户端实例"""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.default_timeout,
                follow_redirects=True
            )
        return self._client

    def close(self) -> None:
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None

    def _build_url(self, url: str) -> str:
        """构建完整 URL"""
        if self.base_url and not url.startswith(('http://', 'https://')):
            return urljoin(self.base_url, url)
        return url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    def request(self, req: HTTPRequest) -> HTTPResponse:
        """
        发送请求

        Args:
            req: HTTP 请求

        Returns:
            HTTPResponse: 响应
        """
        start_time = time.time()
        url = self._build_url(req.url)

        # 构建请求头
        headers = {**self.default_headers, **req.headers}
        if req.content_type:
            headers.setdefault('Content-Type', req.content_type.value)

        # 构建 httpx 请求参数
        kwargs = {
            'url': url,
            'headers': headers,
            'timeout': req.timeout,
            'follow_redirects': req.follow_redirects
        }

        if req.params:
            kwargs['params'] = req.params

        if req.json_data is not None:
            kwargs['json'] = req.json_data
        elif req.data is not None:
            kwargs['content'] = req.data

        # 执行拦截器
        req = self.request_interceptor.execute(req)

        try:
            client = self._get_client()

            # 发送请求
            response = client.request(
                method=req.method.value,
                **kwargs
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # 构建响应对象
            resp = HTTPResponse(
                status_code=response.status_code,
                text=response.text,
                headers=dict(response.headers),
                url=str(response.url),
                elapsed_ms=elapsed_ms,
                request=req,
                is_success=response.status_code < 400,
                error=response.text if response.status_code >= 400 else None
            )

            # 执行响应拦截器
            resp = self.response_interceptor.execute(resp)

            resp.raise_for_status()

            return resp

        except httpx.TimeoutException as e:
            logger.warning(f"HTTP 请求超时: {url}")
            raise
        except httpx.NetworkError as e:
            logger.warning(f"HTTP 网络错误: {url}")
            raise

    def get(self, url: str, **kwargs) -> HTTPResponse:
        """GET 请求"""
        req = HTTPRequest(method=HTTPMethod.GET, url=url, **kwargs)
        return self.request(req)

    def post(self, url: str, **kwargs) -> HTTPResponse:
        """POST 请求"""
        req = HTTPRequest(method=HTTPMethod.POST, url=url, **kwargs)
        return self.request(req)

    def put(self, url: str, **kwargs) -> HTTPResponse:
        """PUT 请求"""
        req = HTTPRequest(method=HTTPMethod.PUT, url=url, **kwargs)
        return self.request(req)

    def delete(self, url: str, **kwargs) -> HTTPResponse:
        """DELETE 请求"""
        req = HTTPRequest(method=HTTPMethod.DELETE, url=url, **kwargs)
        return self.request(req)

    def patch(self, url: str, **kwargs) -> HTTPResponse:
        """PATCH 请求"""
        req = HTTPRequest(method=HTTPMethod.PATCH, url=url, **kwargs)
        return self.request(req)


class AsyncHTTPClient:
    """
    异步 HTTP 客户端

    基于 aiohttp 的异步客户端，适合高并发场景。
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_connections: int = 100,
        default_headers: Dict[str, str] = None
    ):
        """
        初始化客户端

        Args:
            base_url: 基础 URL
            timeout: 默认超时时间
            max_connections: 最大连接数
            default_headers: 默认请求头
        """
        self.base_url = base_url
        self.default_timeout = timeout
        self.default_headers = default_headers or {}
        self.max_connections = max_connections

        self._session: Optional[aiohttp.ClientSession] = None
        self.request_interceptor = RequestInterceptor()
        self.response_interceptor = ResponseInterceptor()

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取会话实例"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.default_timeout)
            connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=10
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=self.default_headers
            )
        return self._session

    async def close(self) -> None:
        """关闭客户端"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _build_url(self, url: str) -> str:
        """构建完整 URL"""
        if self.base_url and not url.startswith(('http://', 'https://')):
            return urljoin(self.base_url, url)
        return url

    async def request(self, req: HTTPRequest) -> HTTPResponse:
        """
        发送请求

        Args:
            req: HTTP 请求

        Returns:
            HTTPResponse: 响应
        """
        start_time = time.time()
        url = self._build_url(req.url)

        # 构建请求头
        headers = {**self.default_headers, **req.headers}
        if req.content_type:
            headers.setdefault('Content-Type', req.content_type.value)

        # 构建 aiohttp 请求参数
        kwargs = {
            'timeout': aiohttp.ClientTimeout(total=req.timeout),
            'allow_redirects': req.follow_redirects
        }

        if req.params:
            kwargs['params'] = req.params

        if req.json_data is not None:
            kwargs['json'] = req.json_data
        elif req.data is not None:
            kwargs['data'] = req.data

        # 执行拦截器
        req = self.request_interceptor.execute(req)

        try:
            session = await self._get_session()

            # 发送请求
            async with session.request(
                method=req.method.value,
                url=url,
                headers=headers,
                **kwargs
            ) as response:

                elapsed_ms = (time.time() - start_time) * 1000
                text = await response.text()

                # 构建响应对象
                resp = HTTPResponse(
                    status_code=response.status,
                    text=text,
                    headers=dict(response.headers),
                    url=str(response.url),
                    elapsed_ms=elapsed_ms,
                    request=req,
                    is_success=response.status < 400,
                    error=text if response.status >= 400 else None
                )

                # 执行响应拦截器
                resp = self.response_interceptor.execute(resp)

                resp.raise_for_status()

                return resp

        except asyncio.TimeoutError:
            logger.warning(f"HTTP 请求超时: {url}")
            raise HTTPError(f"请求超时: {url}")
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP 客户端错误: {url}, {e}")
            raise HTTPError(str(e))

    async def get(self, url: str, **kwargs) -> HTTPResponse:
        """GET 请求"""
        req = HTTPRequest(method=HTTPMethod.GET, url=url, **kwargs)
        return await self.request(req)

    async def post(self, url: str, **kwargs) -> HTTPResponse:
        """POST 请求"""
        req = HTTPRequest(method=HTTPMethod.POST, url=url, **kwargs)
        return await self.request(req)

    async def put(self, url: str, **kwargs) -> HTTPResponse:
        """PUT 请求"""
        req = HTTPRequest(method=HTTPMethod.PUT, url=url, **kwargs)
        return await self.request(req)

    async def delete(self, url: str, **kwargs) -> HTTPResponse:
        """DELETE 请求"""
        req = HTTPRequest(method=HTTPMethod.DELETE, url=url, **kwargs)
        return await self.request(req)

    async def patch(self, url: str, **kwargs) -> HTTPResponse:
        """PATCH 请求"""
        req = HTTPRequest(method=HTTPMethod.PATCH, url=url, **kwargs)
        return await self.request(req)


class APIClient:
    """
    API 客户端

    基于 HTTP 客户端的通用 API 调用封装。
    """

    def __init__(
        self,
        base_url: str = "",
        async_mode: bool = False,
        **kwargs
    ):
        """
        初始化客户端

        Args:
            base_url: API 基础 URL
            async_mode: 是否使用异步模式
            **kwargs: 其他配置参数
        """
        self.base_url = base_url
        self.async_mode = async_mode

        if async_mode:
            self._client = AsyncHTTPClient(base_url=base_url, **kwargs)
        else:
            self._client = SyncHTTPClient(base_url=base_url, **kwargs)

    @property
    def client(self):
        """获取底层客户端"""
        return self._client

    def close(self) -> None:
        """关闭客户端"""
        if hasattr(self._client, 'close'):
            if asyncio.iscoroutinefunction(self._client.close):
                pass  # Async client, use await
            else:
                self._client.close()

    async def aclose(self) -> None:
        """异步关闭"""
        if hasattr(self._client, 'close'):
            if asyncio.iscoroutinefunction(self._client.close):
                await self._client.close()
            else:
                self._client.close()


def create_http_client(
    base_url: str = "",
    async_mode: bool = False,
    **kwargs
) -> APIClient:
    """
    创建 HTTP 客户端

    Args:
        base_url: 基础 URL
        async_mode: 异步模式
        **kwargs: 其他配置

    Returns:
        APIClient: API 客户端实例
    """
    return APIClient(base_url=base_url, async_mode=async_mode, **kwargs)
