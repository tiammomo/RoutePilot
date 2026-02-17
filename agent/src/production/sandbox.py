"""
================================================================================
Agent Sandbox - Agent 执行沙箱

提供安全的执行环境，限制资源使用和操作范围。
================================================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型"""
    CPU_TIME = "cpu_time"           # CPU 时间
    MEMORY = "memory"               # 内存
    NETWORK_CALLS = "network_calls" # 网络调用
    FILE_SIZE = "file_size"        # 文件大小


@dataclass
class ResourceLimits:
    """资源限制"""
    max_execution_time: float = 30.0    # 最大执行时间（秒）
    max_memory_mb: int = 512            # 最大内存（MB）
    max_network_calls: int = 10         # 最大网络调用次数
    max_file_size_mb: int = 10          # 最大文件大小（MB）
    allowed_domains: List[str] = field(default_factory=list)  # 允许访问的域名
    allowed_paths: List[str] = field(default_factory=list)    # 允许访问的路径


@dataclass
class ResourceUsage:
    """资源使用情况"""
    cpu_time: float = 0.0
    memory_mb: float = 0.0
    network_calls: int = 0
    file_size_mb: float = 0.0


class SandboxState(Enum):
    """沙箱状态"""
    IDLE = "idle"
    RUNNING = "running"
    TIMEOUT = "timeout"
    RESOURCE_EXCEEDED = "resource_exceeded"
    COMPLETED = "completed"
    ERROR = "error"


class SandboxError(Exception):
    """沙箱错误"""
    pass


class TimeoutError(SandboxError):
    """超时错误"""
    pass


class ResourceExceededError(SandboxError):
    """资源超出限制错误"""
    pass


class AgentSandbox:
    """Agent 执行沙箱

    特性：
    - 执行时间限制
    - 资源使用监控
    - 网络访问控制
    - 操作审计日志
    """

    def __init__(self, limits: Optional[ResourceLimits] = None):
        """
        Args:
            limits: 资源限制配置
        """
        self.limits = limits or ResourceLimits()
        self._state = SandboxState.IDLE
        self._usage = ResourceUsage()
        self._start_time: Optional[float] = None
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def state(self) -> SandboxState:
        """获取沙箱状态"""
        return self._state

    @property
    def usage(self) -> ResourceUsage:
        """获取资源使用情况"""
        return self._usage

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """在沙箱中执行函数

        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            TimeoutError: 执行超时
            ResourceExceededError: 资源超出限制
        """
        self._state = SandboxState.RUNNING
        self._start_time = time.time()
        self._usage = ResourceUsage()
        self._audit_log = []

        self._log_action("start", {"function": func.__name__})

        try:
            # 检查是否异步函数
            if asyncio.iscoroutinefunction(func):
                result = await self._execute_with_timeout(func, *args, **kwargs)
            else:
                # 同步函数直接执行
                result = func(*args, **kwargs)

            self._state = SandboxState.COMPLETED
            self._log_action("complete", {"result_type": type(result).__name__})

            return result

        except asyncio.TimeoutError:
            self._state = SandboxState.TIMEOUT
            self._log_action("timeout", {"elapsed": time.time() - self._start_time})
            raise TimeoutError(f"Execution exceeded time limit of {self.limits.max_execution_time}s")

        except Exception as e:
            self._state = SandboxState.ERROR
            self._log_action("error", {"error": str(e)})
            raise

        finally:
            self._state = SandboxState.IDLE

    async def _execute_with_timeout(self, func: Callable, *args, **kwargs) -> Any:
        """带超时执行的包装器"""
        try:
            # 使用 asyncio.wait_for 添加超时
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.limits.max_execution_time
            )
            return result

        except asyncio.TimeoutError:
            self._state = SandboxState.TIMEOUT
            raise

    def check_limits(self) -> bool:
        """检查是否超出限制

        Returns:
            是否在限制内
        """
        if self._usage.cpu_time > self.limits.max_execution_time:
            return False

        if self._usage.network_calls > self.limits.max_network_calls:
            return False

        return True

    def record_network_call(self, domain: str) -> bool:
        """记录网络调用

        Args:
            domain: 目标域名

        Returns:
            是否允许调用
        """
        # 检查域名白名单
        if self.limits.allowed_domains:
            if not any(domain.endswith(d) or d in domain for d in self.limits.allowed_domains):
                self._log_action("network_denied", {"domain": domain})
                return False

        self._usage.network_calls += 1
        self._log_action("network_call", {"domain": domain})

        # 检查是否超出限制
        if self._usage.network_calls > self.limits.max_network_calls:
            self._state = SandboxState.RESOURCE_EXCEEDED
            raise ResourceExceededError(f"Network calls exceeded limit of {self.limits.max_network_calls}")

        return True

    def _log_action(self, action: str, details: Dict[str, Any]) -> None:
        """记录操作日志"""
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details,
            "usage": {
                "cpu_time": self._usage.cpu_time,
                "network_calls": self._usage.network_calls
            }
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """获取审计日志"""
        return self._audit_log.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取沙箱统计"""
        return {
            "state": self._state.value,
            "limits": {
                "max_execution_time": self.limits.max_execution_time,
                "max_network_calls": self.limits.max_network_calls
            },
            "usage": {
                "cpu_time": self._usage.cpu_time,
                "network_calls": self._usage.network_calls
            },
            "audit_entries": len(self._audit_log)
        }
