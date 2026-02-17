"""
================================================================================
统一异常处理模块 (Unified Exception Handling)

提供项目统一的异常类定义和异常处理装饰器/函数。

功能特点：
1. 定义项目特定的异常类（继承自基础异常类）
2. 提供异常处理装饰器
3. 支持异常上下文记录和日志
4. 友好的错误信息格式化

使用示例:
```python
from core.exceptions import TravelAgentError, handle_exceptions, ErrorContext

@handle_exceptions(default_return={"success": False})
async def my_function():
    raise TravelAgentError("城市不存在", ErrorContext.CITY_NOT_FOUND)
```

================================================================================
"""

import logging
import traceback
from functools import wraps
from typing import Any, Dict, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorContext(Enum):
    """异常上下文类型"""
    # 配置相关
    CONFIG_LOAD = "config_load"
    CONFIG_PARSE = "config_parse"
    CONFIG_VALIDATE = "config_validate"

    # 工具执行相关
    TOOL_EXECUTION = "tool_execution"
    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_PARAM_ERROR = "tool_param_error"

    # LLM 相关
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_TIMEOUT = "llm_timeout"
    LLM_API_ERROR = "llm_api_error"

    # 记忆相关
    MEMORY_STORE = "memory_store"
    MEMORY_RETRIEVE = "memory_retrieve"
    MEMORY_DELETE = "memory_delete"

    # 城市/旅游数据相关
    CITY_NOT_FOUND = "city_not_found"
    CITY_DATA_ERROR = "city_data_error"
    ATTRACTION_NOT_FOUND = "attraction_not_found"

    # 推理/决策相关
    REASONING_ERROR = "reasoning_error"
    DECISION_ERROR = "decision_error"
    INTENT_RECOGNITION = "intent_recognition"

    # 文件 I/O 相关
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_NOT_FOUND = "file_not_found"

    # 通用
    UNKNOWN = "unknown"


@dataclass
class ErrorDetail:
    """错误详情"""
    context: ErrorContext
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    original_exception: Optional[Exception] = None
    stack_trace: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "context": self.context.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "extra_data": self.extra_data
        }


class TravelAgentError(Exception):
    """
    旅游助手基础异常类

    所有项目特定异常都应继承此类。

    Attributes:
        message: 错误消息
        context: 错误上下文
        error_code: 错误代码（可选）
        details: 错误详情
    """

    def __init__(
        self,
        message: str,
        context: ErrorContext = ErrorContext.UNKNOWN,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.context = context
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()

    def __str__(self) -> str:
        """字符串表示"""
        base = f"[{self.context.value}] {self.message}"
        if self.error_code:
            base = f"[{self.error_code}] {base}"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": False,
            "error": self.message,
            "context": self.context.value,
            "error_code": self.error_code,
            "details": self.details,
            "timestamp": self.timestamp
        }


class ConfigurationError(TravelAgentError):
    """配置相关异常"""

    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        if config_file:
            details['config_file'] = config_file
        super().__init__(
            message,
            context=ErrorContext.CONFIG_LOAD,
            error_code="CONFIG_ERROR",
            details=details
        )


class ToolExecutionError(TravelAgentError):
    """工具执行异常"""

    def __init__(
        self,
        tool_name: str,
        message: str,
        params: Optional[Dict] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        details['tool_name'] = tool_name
        if params:
            details['params'] = params
        super().__init__(
            message,
            context=ErrorContext.TOOL_EXECUTION,
            error_code="TOOL_ERROR",
            details=details
        )


class LLMError(TravelAgentError):
    """LLM 相关异常"""

    def __init__(
        self,
        message: str,
        model_id: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        if model_id:
            details['model_id'] = model_id
        super().__init__(
            message,
            context=ErrorContext.LLM_REQUEST,
            error_code="LLM_ERROR",
            details=details
        )


class MemoryError(TravelAgentError):
    """记忆存储异常"""

    def __init__(
        self,
        message: str,
        operation: str = "unknown",
        **kwargs
    ):
        details = kwargs.pop('details', {})
        details['operation'] = operation
        super().__init__(
            message,
            context=ErrorContext.MEMORY_STORE,
            error_code="MEMORY_ERROR",
            details=details
        )


class CityNotFoundError(TravelAgentError):
    """城市不存在异常"""

    def __init__(
        self,
        city_name: str,
        suggestions: Optional[list] = None
    ):
        details = {'city_name': city_name}
        if suggestions:
            details['suggestions'] = suggestions
        super().__init__(
            f"城市 '{city_name}' 未找到",
            context=ErrorContext.CITY_NOT_FOUND,
            error_code="CITY_NOT_FOUND",
            details=details
        )


class ValidationError(TravelAgentError):
    """参数验证异常"""

    def __init__(
        self,
        field_name: str,
        value: Any,
        reason: str,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        details['field_name'] = field_name
        details['value'] = str(value)
        details['reason'] = reason
        super().__init__(
            f"参数验证失败: {field_name} = {value}, 原因: {reason}",
            context=ErrorContext.CONFIG_VALIDATE,
            error_code="VALIDATION_ERROR",
            details=details
        )


def handle_exceptions(
    logger_obj: logging.Logger = logger,
    default_return: Any = None,
    reraise: bool = False,
    context: ErrorContext = ErrorContext.UNKNOWN
) -> Callable:
    """
    异常处理装饰器

    包装函数，自动捕获异常并返回友好的错误信息。

    Args:
        logger_obj: 日志记录器
        default_return: 异常时返回的默认值
        reraise: 是否重新抛出异常
        context: 异常上下文

    Returns:
        装饰器函数

    Examples:
        @handle_exceptions(default_return={"success": False})
        async def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except TravelAgentError as e:
                logger_obj.error(f"业务异常 in {func.__name__}: {e}")
                if reraise:
                    raise
                return default_return if default_return is not None else e.to_dict()
            except Exception as e:
                logger_obj.error(f"未知异常 in {func.__name__}: {e}")
                logger_obj.debug(traceback.format_exc())
                if reraise:
                    raise
                return default_return if default_return is not None else {
                    "success": False,
                    "error": str(e),
                    "context": context.value
                }

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except TravelAgentError as e:
                logger_obj.error(f"业务异常 in {func.__name__}: {e}")
                if reraise:
                    raise
                return default_return if default_return is not None else e.to_dict()
            except Exception as e:
                logger_obj.error(f"未知异常 in {func.__name__}: {e}")
                logger_obj.debug(traceback.format_exc())
                if reraise:
                    raise
                return default_return if default_return is not None else {
                    "success": False,
                    "error": str(e),
                    "context": context.value
                }

        # 根据函数是否为异步选择包装器
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class ErrorHandler:
    """
    异常处理器

    提供更细粒度的异常处理控制。
    """

    def __init__(self, logger_obj: logging.Logger = logger):
        self.logger = logger_obj
        self.error_counts: Dict[str, int] = {}

    def record_error(self, context: ErrorContext) -> None:
        """记录错误次数"""
        key = context.value
        self.error_counts[key] = self.error_counts.get(key, 0) + 1

    def get_error_count(self, context: ErrorContext) -> int:
        """获取特定类型错误的次数"""
        return self.error_counts.get(context.value, 0)

    def get_error_stats(self) -> Dict[str, int]:
        """获取所有错误统计"""
        return self.error_counts.copy()

    def handle(
        self,
        exception: Exception,
        context: ErrorContext = ErrorContext.UNKNOWN,
        extra_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        处理异常

        Args:
            exception: 异常对象
            context: 异常上下文
            extra_data: 额外数据

        Returns:
            Dict: 标准化的错误响应
        """
        self.record_error(context)

        if isinstance(exception, TravelAgentError):
            self.logger.error(f"[{context.value}] {exception.message}")
            return exception.to_dict()

        # 处理未知异常
        error_detail = ErrorDetail(
            context=context,
            message=str(exception),
            original_exception=exception,
            stack_trace=traceback.format_exc(),
            extra_data=extra_data or {}
        )

        self.logger.error(
            f"[{context.value}] 未知异常: {exception}",
            extra={'error_detail': error_detail.to_dict()}
        )

        return {
            "success": False,
            "error": str(exception),
            "context": context.value,
            "error_code": "UNKNOWN_ERROR",
            "details": extra_data or {},
            "timestamp": error_detail.timestamp
        }


def format_error_response(
    error: Exception,
    context: Optional[ErrorContext] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    格式化错误响应

    将异常转换为标准化的错误响应格式。

    Args:
        error: 异常对象
        context: 异常上下文
        include_details: 是否包含详细信息

    Returns:
        Dict: 标准化的错误响应
    """
    if isinstance(error, TravelAgentError):
        response = error.to_dict()
    else:
        response = {
            "success": False,
            "error": str(error),
            "context": (context or ErrorContext.UNKNOWN).value,
            "error_code": type(error).__name__.upper(),
            "timestamp": datetime.now().isoformat()
        }

    if not include_details and 'details' in response:
        del response['details']

    return response


def create_error_context() -> ErrorContext:
    """根据当前调用栈推断错误上下文"""
    import inspect
    frame = inspect.currentframe()
    if frame:
        func_name = frame.f_code.co_name
        if 'city' in func_name.lower():
            return ErrorContext.CITY_NOT_FOUND
        elif 'tool' in func_name.lower():
            return ErrorContext.TOOL_EXECUTION
        elif 'memory' in func_name.lower():
            return ErrorContext.MEMORY_STORE
        elif 'llm' in func_name.lower() or 'chat' in func_name.lower():
            return ErrorContext.LLM_REQUEST
    return ErrorContext.UNKNOWN
