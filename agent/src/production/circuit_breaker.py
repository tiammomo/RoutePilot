"""
================================================================================
Circuit Breaker - 熔断器

防止故障传播，提供系统弹性。
================================================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常（关闭）
    OPEN = "open"           # 打开（熔断）
    HALF_OPEN = "half_open"  # 半开（尝试恢复）


@dataclass
class CircuitConfig:
    """熔断器配置"""
    failure_threshold: int = 5        # 触发熔断的失败次数
    success_threshold: int = 3        # 恢复需要的成功次数
    timeout: float = 60.0            # 熔断持续时间（秒）
    half_open_max_calls: int = 3     # 半开状态最大尝试次数


@dataclass
class CircuitMetrics:
    """熔断器指标"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: List[Dict[str, Any]] = field(default_factory=list)


class CircuitOpenError(Exception):
    """熔断器打开错误"""
    pass


class CircuitBreaker:
    """熔断器

    特性：
    - 失败计数自动熔断
    - 自动尝试恢复
    - 状态变化回调
    - 详细指标统计
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitConfig] = None,
        on_state_change: Optional[Callable] = None
    ):
        """
        Args:
            name: 熔断器名称
            config: 熔断器配置
            on_state_change: 状态变化回调
        """
        self.name = name
        self.config = config or CircuitConfig()
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0

        self._metrics = CircuitMetrics()

        logger.info(f"CircuitBreaker '{name}' initialized with state: {self._state.value}")

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        # 检查是否需要从 OPEN 转换到 HALF_OPEN
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to(CircuitState.HALF_OPEN)

        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """获取指标"""
        return self._metrics

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数（带熔断保护）

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            CircuitOpenError: 熔断器处于打开状态
        """
        self._metrics.total_calls += 1

        # 检查状态
        if self.state == CircuitState.OPEN:
            self._metrics.rejected_calls += 1
            raise CircuitOpenError(f"Circuit '{self.name}' is OPEN, call rejected")

        try:
            # 执行函数
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # 成功处理
            await self._on_success()
            return result

        except Exception as e:
            # 失败处理
            await self._on_failure(str(e))
            raise

    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试恢复"""
        if self._last_failure_time is None:
            return True

        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout

    async def _on_success(self) -> None:
        """处理成功"""
        self._metrics.successful_calls += 1

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1

            # 达到恢复阈值
            if self._success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)

        elif self._state == CircuitState.CLOSED:
            # 成功后重置失败计数
            self._failure_count = 0

    async def _on_failure(self, error: str) -> None:
        """处理失败"""
        self._metrics.failed_calls += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败，重新打开
            self._transition_to(CircuitState.OPEN)
            self._half_open_calls = 0

        elif self._state == CircuitState.CLOSED:
            # 达到失败阈值，打开熔断器
            if self._failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """状态转换"""
        old_state = self._state
        self._state = new_state

        # 重置计数器
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info(f"Circuit '{self.name}' CLOSED - recovered")

        elif new_state == CircuitState.OPEN:
            logger.warning(f"Circuit '{self.name}' OPEN - triggered by {self._failure_count} failures")

        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            logger.info(f"Circuit '{self.name}' HALF_OPEN - attempting recovery")

        # 记录状态变化
        self._metrics.state_changes.append({
            "timestamp": datetime.now().isoformat(),
            "from": old_state.value,
            "to": new_state.value
        })

        # 触发回调
        if self.on_state_change:
            try:
                self.on_state_change(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

    def reset(self) -> None:
        """手动重置熔断器"""
        self._transition_to(CircuitState.CLOSED)
        logger.info(f"Circuit '{self.name}' manually reset")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "metrics": {
                "total_calls": self._metrics.total_calls,
                "successful_calls": self._metrics.successful_calls,
                "failed_calls": self._metrics.failed_calls,
                "rejected_calls": self._metrics.rejected_calls,
                "success_rate": self._metrics.successful_calls / max(self._metrics.total_calls, 1)
            }
        }


class CircuitBreakerGroup:
    """熔断器组

    管理多个熔断器，支持批量操作。
    """

    def __init__(self):
        """初始化"""
        self._breakers: Dict[str, CircuitBreaker] = {}

    def add_breaker(
        self,
        name: str,
        config: Optional[CircuitConfig] = None,
        on_state_change: Optional[Callable] = None
    ) -> CircuitBreaker:
        """添加熔断器"""
        breaker = CircuitBreaker(name, config, on_state_change)
        self._breakers[name] = breaker
        return breaker

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """获取熔断器"""
        return self._breakers.get(name)

    def remove_breaker(self, name: str) -> bool:
        """移除熔断器"""
        if name in self._breakers:
            del self._breakers[name]
            return True
        return False

    async def call(self, breaker_name: str, func: Callable, *args, **kwargs) -> Any:
        """通过指定熔断器执行"""
        breaker = self._breakers.get(breaker_name)
        if not breaker:
            # 没有熔断器，直接执行
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        return await breaker.call(func, *args, **kwargs)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有熔断器统计"""
        return {
            name: breaker.get_stats()
            for name, breaker in self._breakers.items()
        }

    def get_group_state(self) -> str:
        """获取组状态"""
        if any(b.state == CircuitState.OPEN for b in self._breakers.values()):
            return "degraded"
        if any(b.state == CircuitState.HALF_OPEN for b in self._breakers.values()):
            return "recovering"
        return "healthy"
