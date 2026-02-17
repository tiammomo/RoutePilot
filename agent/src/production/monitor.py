"""
================================================================================
Agent Monitor - Agent 监控

提供指标收集、日志聚合、追踪等可观测性功能。
================================================================================
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import uuid

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricAggregator(Enum):
    """指标聚合方式"""
    SUM = "sum"
    AVG = "avg"
    MAX = "max"
    MIN = "min"
    COUNT = "count"


@dataclass
class MetricDefinition:
    """指标定义"""
    name: str
    type: str  # counter, gauge, histogram
    unit: str = ""
    description: str = ""
    aggregator: MetricAggregator = MetricAggregator.SUM


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    level: LogLevel
    message: str
    source: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceSpan:
    """追踪跨度"""
    span_id: str
    trace_id: str
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "ok"


class AgentMonitor:
    """Agent 监控器

    特性：
    - 指标收集
    - 日志聚合
    - 分布式追踪
    - 健康检查
    """

    def __init__(self, service_name: str = "agent"):
        """
        Args:
            service_name: 服务名称
        """
        self.service_name = service_name
        self._metrics: Dict[str, List[float]] = defaultdict(list)
        self._logs: List[LogEntry] = []
        self._traces: Dict[str, TraceSpan] = {}
        self._trace_stacks: Dict[str, List[str]] = defaultdict(list)

        # 配置
        self._max_logs = 10000
        self._max_traces = 1000

        # 健康检查回调
        self._health_checks: Dict[str, Callable] = {}

        logger.info(f"AgentMonitor initialized for service: {service_name}")

    # ==================== Metrics ====================

    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """记录指标

        Args:
            name: 指标名称
            value: 指标值
            tags: 标签
        """
        key = self._make_metric_key(name, tags)
        self._metrics[key].append(value)

        # 限制存储数量
        if len(self._metrics[key]) > 1000:
            self._metrics[key] = self._metrics[key][-1000:]

    def increment_counter(self, name: str, tags: Optional[Dict[str, str]] = None) -> None:
        """递增计数器"""
        key = self._make_metric_key(name, tags)
        if key not in self._metrics:
            self._metrics[key] = []
        self._metrics[key].append(1.0)

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """设置仪表值"""
        key = self._make_metric_key(name, tags)
        self._metrics[key] = [value]

    def get_metric(self, name: str, tags: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """获取指标统计

        Args:
            name: 指标名称
            tags: 标签

        Returns:
            指标统计 (sum, avg, max, min, count)
        """
        key = self._make_metric_key(name, tags)
        values = self._metrics.get(key, [])

        if not values:
            return {"sum": 0, "avg": 0, "max": 0, "min": 0, "count": 0}

        return {
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "max": max(values),
            "min": min(values),
            "count": len(values)
        }

    def get_all_metrics(self) -> Dict[str, Dict[str, float]]:
        """获取所有指标"""
        result = {}
        for key in self._metrics:
            # 解析原始名称和标签
            name = key.split("|")[0] if "|" in key else key
            result[key] = self.get_metric(name)
        return result

    def _make_metric_key(self, name: str, tags: Optional[Dict[str, str]] = None) -> str:
        """生成指标键"""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}|{tag_str}"

    # ==================== Logging ====================

    def log(
        self,
        level: LogLevel,
        message: str,
        source: str = "agent",
        trace_id: Optional[str] = None,
        **metadata
    ) -> None:
        """记录日志

        Args:
            level: 日志级别
            message: 日志消息
            source: 来源
            trace_id: 追踪 ID
            **metadata: 额外元数据
        """
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            source=source,
            trace_id=trace_id,
            metadata=metadata
        )

        self._logs.append(entry)

        # 限制存储数量
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

    def debug(self, message: str, **metadata) -> None:
        """调试日志"""
        self.log(LogLevel.DEBUG, message, **metadata)

    def info(self, message: str, **metadata) -> None:
        """信息日志"""
        self.log(LogLevel.INFO, message, **metadata)

    def warning(self, message: str, **metadata) -> None:
        """警告日志"""
        self.log(LogLevel.WARNING, message, **metadata)

    def error(self, message: str, **metadata) -> None:
        """错误日志"""
        self.log(LogLevel.ERROR, message, **metadata)

    def critical(self, message: str, **metadata) -> None:
        """严重日志"""
        self.log(LogLevel.CRITICAL, message, **metadata)

    def get_logs(
        self,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """获取日志

        Args:
            level: 日志级别过滤
            source: 来源过滤
            limit: 返回数量限制

        Returns:
            日志列表
        """
        logs = self._logs

        if level:
            logs = [l for l in logs if l.level == level]

        if source:
            logs = [l for l in logs if l.source == source]

        return logs[-limit:]

    # ==================== Tracing ====================

    def start_trace(self, operation_name: str, trace_id: Optional[str] = None, tags: Optional[Dict] = None) -> str:
        """开始追踪

        Args:
            operation_name: 操作名称
            trace_id: 追踪 ID（可选）
            tags: 标签

        Returns:
            trace_id
        """
        if trace_id is None:
            trace_id = str(uuid.uuid4())

        span_id = str(uuid.uuid4())[:8]

        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            operation_name=operation_name,
            start_time=time.time(),
            tags=tags or {}
        )

        self._traces[span_id] = span

        # 维护追踪栈
        self._trace_stacks[trace_id].append(span_id)

        return trace_id

    def end_trace(self, span_id: str, status: str = "ok", tags: Optional[Dict] = None) -> None:
        """结束追踪

        Args:
            span_id: 跨度 ID
            status: 状态
            tags: 额外标签
        """
        if span_id not in self._traces:
            return

        span = self._traces[span_id]
        span.end_time = time.time()
        span.duration = span.end_time - span.start_time
        span.status = status

        if tags:
            span.tags.update(tags)

    def add_trace_log(self, span_id: str, message: str, **fields) -> None:
        """添加追踪日志"""
        if span_id in self._traces:
            self._traces[span_id].logs.append({
                "timestamp": datetime.now().isoformat(),
                "message": message,
                **fields
            })

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """获取追踪

        Args:
            trace_id: 追踪 ID

        Returns:
            追踪跨度列表
        """
        span_ids = self._trace_stacks.get(trace_id, [])
        return [self._traces[sid] for sid in span_ids if sid in self._traces]

    def get_traces(self, limit: int = 100) -> List[TraceSpan]:
        """获取所有追踪"""
        traces = list(self._traces.values())
        traces.sort(key=lambda x: x.start_time, reverse=True)
        return traces[:limit]

    # ==================== Health Check ====================

    def register_health_check(self, name: str, check_func: Callable) -> None:
        """注册健康检查

        Args:
            name: 检查名称
            check_func: 检查函数 (async) -> bool
        """
        self._health_checks[name] = check_func

    async def check_health(self) -> Dict[str, Any]:
        """执行健康检查

        Returns:
            健康状态
        """
        results = {}

        for name, check_func in self._health_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                results[name] = {"status": "healthy" if result else "unhealthy", "healthy": result}
            except Exception as e:
                results[name] = {"status": "error", "error": str(e), "healthy": False}

        overall_healthy = all(r.get("healthy", False) for r in results.values())

        return {
            "service": self.service_name,
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "checks": results
        }

    # ==================== Summary ====================

    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要

        Returns:
            监控统计摘要
        """
        return {
            "service_name": self.service_name,
            "metrics_count": len(self._metrics),
            "logs_count": len(self._logs),
            "traces_count": len(self._traces),
            "health_checks": len(self._health_checks),
            "uptime": datetime.now().isoformat()
        }
