"""
================================================================================
Production - 生产级增强模块

v2.6.0 新增：安全沙箱、熔断器、可观测性监控
================================================================================
"""

from production.sandbox import (
    AgentSandbox,
    ResourceLimits,
    ResourceUsage,
    SandboxState,
    SandboxError,
    TimeoutError,
    ResourceExceededError
)

from production.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerGroup,
    CircuitState,
    CircuitConfig,
    CircuitMetrics,
    CircuitOpenError
)

from production.monitor import (
    AgentMonitor,
    LogLevel,
    MetricAggregator,
    LogEntry,
    TraceSpan
)

__version__ = "2.6.0"

__all__ = [
    # Sandbox
    "AgentSandbox",
    "ResourceLimits",
    "ResourceUsage",
    "SandboxState",
    "SandboxError",
    "TimeoutError",
    "ResourceExceededError",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitBreakerGroup",
    "CircuitState",
    "CircuitConfig",
    "CircuitMetrics",
    "CircuitOpenError",
    # Monitor
    "AgentMonitor",
    "LogLevel",
    "MetricAggregator",
    "LogEntry",
    "TraceSpan"
]
