"""
Production 模块单元测试
"""

import pytest
import asyncio
from production.sandbox import (
    AgentSandbox,
    ResourceLimits,
    SandboxState,
    TimeoutError
)
from production.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerGroup,
    CircuitState,
    CircuitConfig,
    CircuitOpenError
)
from production.monitor import (
    AgentMonitor,
    LogLevel
)


class TestAgentSandbox:
    """Agent 沙箱测试"""

    def test_initialization(self):
        """测试初始化"""
        sandbox = AgentSandbox()
        assert sandbox.state == SandboxState.IDLE

    def test_initialization_with_limits(self):
        """测试带限制初始化"""
        limits = ResourceLimits(max_execution_time=10, max_network_calls=5)
        sandbox = AgentSandbox(limits)

        assert sandbox.limits.max_execution_time == 10
        assert sandbox.limits.max_network_calls == 5

    @pytest.mark.asyncio
    async def test_execute_sync_function(self):
        """测试执行同步函数"""
        sandbox = AgentSandbox(ResourceLimits(max_execution_time=5))

        def add(a, b):
            return a + b

        result = await sandbox.execute(add, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_execute_simple(self):
        """测试简单执行"""
        sandbox = AgentSandbox()
        result = await sandbox.execute(lambda: 42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_execute_async_function(self):
        """测试执行异步函数"""
        sandbox = AgentSandbox(ResourceLimits(max_execution_time=5))

        async def async_add(a, b):
            return a + b

        result = await sandbox.execute(async_add, 2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_timeout(self):
        """测试超时"""
        sandbox = AgentSandbox(ResourceLimits(max_execution_time=0.1))

        async def slow_func():
            await asyncio.sleep(1)
            return "done"

        with pytest.raises(TimeoutError):
            await sandbox.execute(slow_func)

    def test_record_network_call(self):
        """测试记录网络调用"""
        sandbox = AgentSandbox(ResourceLimits(allowed_domains=["example.com"]))

        result = sandbox.record_network_call("api.example.com")
        assert result is True

    def test_record_network_call_denied(self):
        """测试拒绝网络调用"""
        sandbox = AgentSandbox(ResourceLimits(allowed_domains=["example.com"]))

        result = sandbox.record_network_call("evil.com")
        assert result is False

    def test_get_stats(self):
        """测试获取统计"""
        sandbox = AgentSandbox()
        stats = sandbox.get_stats()

        assert "state" in stats
        assert "limits" in stats
        assert "usage" in stats


class TestCircuitBreaker:
    """熔断器测试"""

    def test_initialization(self):
        """测试初始化"""
        breaker = CircuitBreaker("test")
        assert breaker.name == "test"
        assert breaker.state == CircuitState.CLOSED

    def test_initialization_with_config(self):
        """测试带配置初始化"""
        config = CircuitConfig(failure_threshold=3, timeout=30)
        breaker = CircuitBreaker("test", config)

        assert breaker.config.failure_threshold == 3
        assert breaker.config.timeout == 30

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """测试成功调用"""
        breaker = CircuitBreaker("test")

        async def success():
            return "ok"

        result = await breaker.call(success)
        assert result == "ok"
        assert breaker.metrics.successful_calls == 1

    @pytest.mark.asyncio
    async def test_failed_call(self):
        """测试失败调用"""
        breaker = CircuitBreaker("test", CircuitConfig(failure_threshold=2))

        async def fail():
            raise ValueError("error")

        with pytest.raises(ValueError):
            await breaker.call(fail)

        assert breaker.metrics.failed_calls == 1

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """测试达到阈值后打开熔断器"""
        breaker = CircuitBreaker("test", CircuitConfig(failure_threshold=2))

        async def fail():
            raise ValueError("error")

        async def success():
            return "ok"

        # 触发第一次失败
        with pytest.raises(ValueError):
            await breaker.call(fail)

        # 触发第二次失败，应该打开熔断器
        with pytest.raises(ValueError):
            await breaker.call(fail)

        # 现在应该打开
        assert breaker.state == CircuitState.OPEN

        # 再次调用应该被拒绝
        with pytest.raises(CircuitOpenError):
            await breaker.call(success)

    def test_manual_reset(self):
        """测试手动重置"""
        breaker = CircuitBreaker("test")
        breaker._state = CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    def test_get_stats(self):
        """测试获取统计"""
        breaker = CircuitBreaker("test")
        stats = breaker.get_stats()

        assert "name" in stats
        assert "state" in stats
        assert "metrics" in stats


class TestCircuitBreakerGroup:
    """熔断器组测试"""

    def test_initialization(self):
        """测试初始化"""
        group = CircuitBreakerGroup()
        assert len(group._breakers) == 0

    def test_add_breaker(self):
        """测试添加熔断器"""
        group = CircuitBreakerGroup()
        breaker = group.add_breaker("test")

        assert breaker is not None
        assert group.get_breaker("test") is breaker

    def test_remove_breaker(self):
        """测试移除熔断器"""
        group = CircuitBreakerGroup()
        group.add_breaker("test")

        result = group.remove_breaker("test")
        assert result is True

    def test_get_group_state(self):
        """测试获取组状态"""
        group = CircuitBreakerGroup()
        group.add_breaker("test1")
        group.add_breaker("test2")

        assert group.get_group_state() == "healthy"


class TestAgentMonitor:
    """Agent 监控器测试"""

    def test_initialization(self):
        """测试初始化"""
        monitor = AgentMonitor("test-service")
        assert monitor.service_name == "test-service"

    def test_record_metric(self):
        """测试记录指标"""
        monitor = AgentMonitor()
        monitor.record_metric("test_metric", 100)

        metric = monitor.get_metric("test_metric")
        assert metric["sum"] == 100

    def test_increment_counter(self):
        """测试递增计数器"""
        monitor = AgentMonitor()
        monitor.increment_counter("requests")
        monitor.increment_counter("requests")

        metric = monitor.get_metric("requests")
        assert metric["count"] == 2

    def test_set_gauge(self):
        """测试设置仪表值"""
        monitor = AgentMonitor()
        monitor.set_gauge("temperature", 25.5)

        metric = monitor.get_metric("temperature")
        assert metric["sum"] == 25.5

    def test_log(self):
        """测试日志"""
        monitor = AgentMonitor()
        monitor.info("test message", key="value")

        logs = monitor.get_logs(limit=10)
        assert len(logs) == 1
        assert logs[0].message == "test message"

    def test_log_levels(self):
        """测试日志级别"""
        monitor = AgentMonitor()
        monitor.debug("debug")
        monitor.info("info")
        monitor.warning("warning")
        monitor.error("error")
        monitor.critical("critical")

        logs = monitor.get_logs()
        assert len(logs) == 5

    def test_start_trace(self):
        """测试开始追踪"""
        monitor = AgentMonitor()
        trace_id = monitor.start_trace("test_operation")

        assert trace_id is not None

    def test_health_check(self):
        """测试健康检查"""
        monitor = AgentMonitor()

        def basic_check():
            return True

        monitor.register_health_check("basic", basic_check)

    @pytest.mark.asyncio
    async def test_check_health(self):
        """测试健康检查执行"""
        monitor = AgentMonitor()

        async def healthy():
            return True

        monitor.register_health_check("test", healthy)

        result = await monitor.check_health()
        assert result["status"] == "healthy"

    def test_get_summary(self):
        """测试获取摘要"""
        monitor = AgentMonitor()
        monitor.record_metric("test", 100)

        summary = monitor.get_summary()
        assert "service_name" in summary
        assert "metrics_count" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
