"""
================================================================================
LangGraph Agent 错误处理与重试机制
================================================================================

提供完整的错误处理和重试机制：
- 异常类定义
- 重试装饰器
- 错误恢复策略
- 降级处理

================================================================================
"""

import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Any, Optional, Type, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ============================================================================
# 异常类
# ============================================================================

class AgentError(Exception):
    """Agent 基类异常"""
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable


class LLMAgentError(AgentError):
    """LLM 调用异常"""
    pass


class ToolExecutionError(AgentError):
    """工具执行异常"""
    def __init__(self, tool_name: str, message: str, recoverable: bool = True):
        super().__init__(f"Tool '{tool_name}': {message}", recoverable)
        self.tool_name = tool_name


class IntentRecognitionError(AgentError):
    """意图识别异常"""
    pass


class RateLimitError(AgentError):
    """速率限制异常"""
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, recoverable=True)


class TimeoutError(AgentError):
    """超时异常"""
    def __init__(self, message: str = "Operation timeout"):
        super().__init__(message, recoverable=True)


class SessionError(AgentError):
    """会话异常"""
    pass


# ============================================================================
# 重试装饰器
# ============================================================================

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    指数退避重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数基数
        exceptions: 需要重试的异常类型
        on_retry: 重试回调函数 (exception, attempt)

    Example:
        @retry_with_backoff(max_retries=3, exceptions=(ConnectionError,))
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= max_retries:
                        logger.error(f"[Retry] Max retries ({max_retries}) reached for {func.__name__}")
                        raise

                    # 计算延迟
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    logger.warning(f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s...")

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(delay)

            raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= max_retries:
                        logger.error(f"[Retry] Max retries ({max_retries}) reached for {func.__name__}")
                        raise

                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    logger.warning(f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.2f}s...")

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(delay)

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def retry_on_rate_limit(max_retries: int = 3):
    """专门用于速率限制的重试装饰器"""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=2.0,
        max_delay=60.0,
        exceptions=(RateLimitError,),
        on_retry=lambda e, attempt: logger.warning(f"Rate limit hit, attempt {attempt + 1}")
    )


# ============================================================================
# 错误恢复策略
# ============================================================================

class ErrorRecoveryStrategy:
    """
    错误恢复策略

    根据错误类型自动选择恢复策略
    """

    def __init__(self):
        self.strategies = {
            ToolExecutionError: self._recover_tool_error,
            LLMAgentError: self._recover_llm_error,
            IntentRecognitionError: self._recover_intent_error,
            RateLimitError: self._recover_rate_limit,
            TimeoutError: self._recover_timeout,
        }

    def register_strategy(self, error_type: Type[Exception], handler: Callable):
        """注册自定义恢复策略"""
        self.strategies[error_type] = handler

    async def recover(self, error: Exception, context: dict) -> Any:
        """
        执行恢复

        Args:
            error: 发生的异常
            context: 上下文信息

        Returns:
            恢复后的结果
        """
        for error_type, handler in self.strategies.items():
            if isinstance(error, error_type):
                logger.info(f"[Recovery] Applying strategy for {error_type.__name__}")
                return await handler(error, context)

        # 默认策略
        logger.warning(f"[Recovery] No specific strategy for {type(error).__name__}, using fallback")
        return await self._fallback_recovery(error, context)

    async def _recover_tool_error(self, error: ToolExecutionError, context: dict) -> dict:
        """工具错误恢复：跳过当前工具，继续执行"""
        logger.info(f"[Recovery] Tool '{error.tool_name}' failed, skipping...")

        # 返回一个降级的结果，允许流程继续
        return {
            "success": False,
            "error": error.message,
            "skipped": True,
            "fallback_answer": "抱歉，当前工具暂时不可用，我将尝试用其他方式回答您的问题。"
        }

    async def _recover_llm_error(self, error: LLMAgentError, context: dict) -> dict:
        """LLM 错误恢复：使用缓存或降级模型"""
        logger.warning(f"[Recovery] LLM error: {error.message}")

        # 尝试使用缓存的响应
        if "cached_response" in context:
            logger.info("[Recovery] Using cached response")
            return {"success": True, "answer": context["cached_response"], "from_cache": True}

        # 返回降级回答
        return {
            "success": False,
            "error": error.message,
            "fallback_answer": "抱歉，服务暂时繁忙，请稍后重试。"
        }

    async def _recover_intent_error(self, error: IntentRecognitionError, context: dict) -> dict:
        """意图识别错误恢复：使用默认意图"""
        logger.warning(f"[Recovery] Intent recognition failed: {error.message}")

        # 返回默认意图
        return {
            "success": True,
            "intent": "general",
            "confidence": 0.0,
            "requires_tools": False,
            "entities": {}
        }

    async def _recover_rate_limit(self, error: RateLimitError, context: dict) -> dict:
        """速率限制恢复：等待后重试"""
        logger.warning(f"[Recovery] Rate limit: {error.message}")
        await asyncio.sleep(5)

        return {
            "success": False,
            "error": error.message,
            "retry_after": 5,
            "fallback_answer": "请求过于频繁，请稍后重试。"
        }

    async def _recover_timeout(self, error: TimeoutError, context: dict) -> dict:
        """超时恢复：使用简化流程"""
        logger.warning(f"[Recovery] Timeout: {error.message}")

        return {
            "success": False,
            "error": error.message,
            "fallback_answer": "请求超时，请稍后重试。"
        }

    async def _fallback_recovery(self, error: Exception, context: dict) -> dict:
        """默认恢复策略"""
        logger.error(f"[Recovery] Unhandled error: {error}")

        return {
            "success": False,
            "error": str(error),
            "fallback_answer": "发生了一些问题，请稍后重试。"
        }


# ============================================================================
# 错误处理中间件
# ============================================================================

class AgentErrorMiddleware:
    """
    Agent 错误处理中间件

    包装 Agent 执行，提供统一的错误处理
    """

    def __init__(self, recovery_strategy: Optional[ErrorRecoveryStrategy] = None):
        self.recovery_strategy = recovery_strategy or ErrorRecoveryStrategy()
        self.error_counts = {}

    async def execute_with_error_handling(
        self,
        func: Callable,
        *args,
        context: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        执行函数并处理错误

        Args:
            func: 要执行的函数
            *args: 位置参数
            context: 上下文信息
            **kwargs: 关键字参数

        Returns:
            执行结果
        """
        context = context or {}

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return {"success": True, "result": result}

        except Exception as e:
            # 记录错误
            error_type = type(e).__name__
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

            logger.error(f"[Middleware] Error in {func.__name__}: {e}")

            # 尝试恢复
            return await self.recovery_strategy.recover(e, context)

    def get_error_stats(self) -> dict:
        """获取错误统计"""
        return self.error_counts.copy()

    def reset_stats(self):
        """重置统计"""
        self.error_counts.clear()


# ============================================================================
# 降级处理
# ============================================================================

class FallbackHandler:
    """
    降级处理器

    当主要功能不可用时，提供备用方案
    """

    def __init__(self):
        self.fallbacks = {}

    def register_fallback(self, primary_func: str, fallback_func: Callable):
        """注册降级函数"""
        self.fallbacks[primary_func] = fallback_func

    async def execute(self, primary_func: str, *args, **kwargs) -> Any:
        """执行主函数，失败时使用降级"""
        if primary_func not in self.fallbacks:
            raise ValueError(f"No fallback registered for {primary_func}")

        fallback = self.fallbacks[primary_func]

        try:
            if asyncio.iscoroutinefunction(primary_func):
                return await primary_func(*args, **kwargs)
            else:
                return primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"[Fallback] Primary function failed, using fallback: {e}")

            if asyncio.iscoroutinefunction(fallback):
                return await fallback(*args, **kwargs)
            return fallback(*args, **kwargs)


# ============================================================================
# 全局单例
# ============================================================================

_error_recovery_strategy: Optional[ErrorRecoveryStrategy] = None
_error_middleware: Optional[AgentErrorMiddleware] = None


def get_error_recovery_strategy() -> ErrorRecoveryStrategy:
    """获取错误恢复策略单例"""
    global _error_recovery_strategy
    if _error_recovery_strategy is None:
        _error_recovery_strategy = ErrorRecoveryStrategy()
    return _error_recovery_strategy


def get_error_middleware() -> AgentErrorMiddleware:
    """获取错误处理中间件单例"""
    global _error_middleware
    if _error_middleware is None:
        _error_middleware = AgentErrorMiddleware(get_error_recovery_strategy())
    return _error_middleware
