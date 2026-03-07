"""
================================================================================
统一异常处理模块
================================================================================

提供项目统一的异常类定义和异常处理机制。

异常类:
    - ShuaiTravelAgentError: 基础异常类
    - ConfigurationError: 配置错误
    - LLMError: LLM 调用错误
    - ToolExecutionError: 工具执行错误
    - SessionError: 会话管理错误
    - ValidationError: 数据验证错误
    - RateLimitError: 速率限制错误
    - ExternalServiceError: 外部服务错误

使用示例:
    from exceptions import ShuaiTravelAgentError, LLMError

    try:
        # 业务逻辑
        pass
    except LLMError as e:
        logger.error(f"LLM error: {e}")
        raise

================================================================================
"""

from typing import Any, Optional, Dict
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse


class ShuaiTravelAgentError(Exception):
    """项目基础异常类"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details
            }
        }

    def to_http_exception(self) -> HTTPException:
        """转换为 FastAPI HTTPException"""
        return HTTPException(
            status_code=self.status_code,
            detail={
                "code": self.code,
                "message": self.message,
                "details": self.details
            }
        )


class ConfigurationError(ShuaiTravelAgentError):
    """配置错误"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="CONFIG_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class LLMError(ShuaiTravelAgentError):
    """LLM 调用错误"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="LLM_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details
        )


class ToolExecutionError(ShuaiTravelAgentError):
    """工具执行错误"""

    def __init__(self, tool_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        details["tool_name"] = tool_name
        super().__init__(
            message=f"Tool '{tool_name}' execution failed: {message}",
            code="TOOL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class SessionError(ShuaiTravelAgentError):
    """会话管理错误"""

    def __init__(self, message: str, session_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if session_id:
            details["session_id"] = session_id
        super().__init__(
            message=message,
            code="SESSION_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class ValidationError(ShuaiTravelAgentError):
    """数据验证错误"""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class RateLimitError(ShuaiTravelAgentError):
    """速率限制错误"""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(
            message=message,
            code="RATE_LIMIT_ERROR",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details
        )


class ExternalServiceError(ShuaiTravelAgentError):
    """外部服务错误"""

    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        details["service"] = service
        super().__init__(
            message=f"External service '{service}' error: {message}",
            code="EXTERNAL_SERVICE_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details
        )


class NotFoundError(ShuaiTravelAgentError):
    """资源不存在错误"""

    def __init__(self, resource: str, resource_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        details["resource"] = resource
        if resource_id:
            details["resource_id"] = resource_id
        message = f"Resource '{resource}' not found"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


# =============================================================================
# 异常处理装饰器
# =============================================================================

def handle_exceptions(func):
    """异常处理装饰器

    将项目自定义异常转换为适当的 HTTP 响应
    """
    from functools import wraps
    import logging

    logger = logging.getLogger(__name__)

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ShuaiTravelAgentError as e:
            logger.error(f"Business error: {e.code} - {e.message}")
            return JSONResponse(
                status_code=e.status_code,
                content=e.to_dict()
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ShuaiTravelAgentError(
                    message="Internal server error",
                    code="INTERNAL_ERROR"
                ).to_dict()
            )

    return wrapper


__all__ = [
    "ShuaiTravelAgentError",
    "ConfigurationError",
    "LLMError",
    "ToolExecutionError",
    "SessionError",
    "ValidationError",
    "RateLimitError",
    "ExternalServiceError",
    "NotFoundError",
    "handle_exceptions",
]
