"""
================================================================================
Agent Evaluator - Agent 性能评估器

收集和分析 Agent 运行指标，提供性能评估和改进建议。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """指标类型"""
    RESPONSE_TIME = "response_time"           # 响应时间
    TOOL_USAGE = "tool_usage"                 # 工具使用效率
    TASK_COMPLETION = "task_completion"       # 任务完成率
    REASONING_QUALITY = "reasoning_quality"   # 推理质量
    USER_SATISFACTION = "user_satisfaction"  # 用户满意度
    ERROR_RATE = "error_rate"                 # 错误率
    TOKEN_USAGE = "token_usage"              # Token 使用量


@dataclass
class MetricSnapshot:
    """指标快照"""
    timestamp: str
    metric_type: MetricType
    value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """评估结果"""
    overall_score: float
    metrics: Dict[str, float]
    suggestions: List[str]
    trend: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMetrics:
    """会话指标"""
    session_id: str
    user_id: str
    start_time: str
    end_time: Optional[str] = None
    request_count: int = 0
    total_response_time: float = 0.0
    tool_calls: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: List[str] = field(default_factory=list)
    user_feedback: Optional[int] = None  # 1-5 评分


class AgentEvaluator:
    """Agent 性能评估器

    负责：
    - 收集运行指标
    - 计算性能评分
    - 生成改进建议
    - 跟踪性能趋势
    """

    def __init__(self):
        """初始化"""
        self._metrics: List[MetricSnapshot] = []
        self._sessions: Dict[str, SessionMetrics] = {}
        self._current_session: Optional[str] = None

        # 评分权重
        self._weights = {
            MetricType.RESPONSE_TIME: 0.2,
            MetricType.TOOL_USAGE: 0.2,
            MetricType.TASK_COMPLETION: 0.25,
            MetricType.REASONING_QUALITY: 0.2,
            MetricType.ERROR_RATE: 0.15
        }

    def start_session(self, session_id: str, user_id: str = "anonymous") -> None:
        """开始会话"""
        self._current_session = session_id
        self._sessions[session_id] = SessionMetrics(
            session_id=session_id,
            user_id=user_id,
            start_time=datetime.now().isoformat()
        )
        logger.info(f"Started metrics session: {session_id}")

    def end_session(self, session_id: str, user_feedback: Optional[int] = None) -> None:
        """结束会话"""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.end_time = datetime.now().isoformat()
            session.user_feedback = user_feedback
            logger.info(f"Ended metrics session: {session_id}")

        if self._current_session == session_id:
            self._current_session = None

    def record_request(self, session_id: str, response_time: float) -> None:
        """记录请求"""
        if session_id not in self._sessions:
            self.start_session(session_id)

        session = self._sessions[session_id]
        session.request_count += 1
        session.total_response_time += response_time

        # 记录响应时间指标
        self._record_metric(MetricType.RESPONSE_TIME, response_time)

    def record_tool_usage(self, session_id: str, tool_name: str) -> None:
        """记录工具使用"""
        if session_id in self._sessions:
            self._sessions[session_id].tool_calls[tool_name] += 1

            # 记录工具使用指标
            self._record_metric(MetricType.TOOL_USAGE, 1.0, {"tool": tool_name})

    def record_error(self, session_id: str, error: str) -> None:
        """记录错误"""
        if session_id in self._sessions:
            self._sessions[session_id].errors.append(error)

            # 记录错误率指标
            self._record_metric(MetricType.ERROR_RATE, 1.0, {"error": error})

    def record_task_completion(self, session_id: str, success: bool) -> None:
        """记录任务完成"""
        value = 1.0 if success else 0.0
        self._record_metric(MetricType.TASK_COMPLETION, value)

    def _record_metric(self, metric_type: MetricType, value: float, metadata: Optional[Dict] = None) -> None:
        """记录指标"""
        snapshot = MetricSnapshot(
            timestamp=datetime.now().isoformat(),
            metric_type=metric_type,
            value=value,
            metadata=metadata or {}
        )
        self._metrics.append(snapshot)

    async def evaluate(self, session_id: Optional[str] = None, time_window_hours: int = 24) -> EvaluationResult:
        """评估性能

        Args:
            session_id: 会话 ID（可选）
            time_window_hours: 评估时间窗口（小时）

        Returns:
            评估结果
        """
        # 过滤指标
        cutoff_time = datetime.now() - timedelta(hours=time_window_hours)
        recent_metrics = [
            m for m in self._metrics
            if datetime.fromisoformat(m.timestamp) > cutoff_time
        ]

        # 计算各项指标
        metrics = await self._calculate_metrics(recent_metrics)

        # 计算总体评分
        overall_score = self._calculate_overall_score(metrics)

        # 生成建议
        suggestions = self._generate_suggestions(metrics)

        # 计算趋势
        trend = await self._calculate_trend(recent_metrics)

        return EvaluationResult(
            overall_score=overall_score,
            metrics=metrics,
            suggestions=suggestions,
            trend=trend,
            metadata={
                "session_id": session_id,
                "time_window_hours": time_window_hours,
                "samples": len(recent_metrics)
            }
        )

    async def _calculate_metrics(self, metrics: List[MetricSnapshot]) -> Dict[str, float]:
        """计算各项指标"""
        result = {}

        # 响应时间（取平均值，越小越好）
        response_times = [m.value for m in metrics if m.metric_type == MetricType.RESPONSE_TIME]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            # 转换为评分（3秒内满分，超过30秒0分）
            result["response_time"] = max(0, min(100, (30 - avg_response_time) / 30 * 100))
        else:
            result["response_time"] = 50.0

        # 任务完成率
        completions = [m.value for m in metrics if m.metric_type == MetricType.TASK_COMPLETION]
        if completions:
            result["task_completion"] = sum(completions) / len(completions) * 100
        else:
            result["task_completion"] = 50.0

        # 错误率
        errors = [m.value for m in metrics if m.metric_type == MetricType.ERROR_RATE]
        if errors:
            error_rate = sum(errors) / max(len(response_times), 1)
            result["error_rate"] = (1 - error_rate) * 100
        else:
            result["error_rate"] = 100.0

        # 工具使用效率（简化为记录数/请求数）
        tool_usages = len([m for m in metrics if m.metric_type == MetricType.TOOL_USAGE])
        result["tool_usage"] = min(100, tool_usages * 10)

        # 推理质量（默认中等）
        result["reasoning_quality"] = 75.0

        return result

    def _calculate_overall_score(self, metrics: Dict[str, float]) -> float:
        """计算总体评分"""
        total = 0.0

        for metric_type, weight in self._weights.items():
            key = metric_type.value
            if key in metrics:
                total += metrics[key] * weight

        return round(total, 2)

    def _generate_suggestions(self, metrics: Dict[str, float]) -> List[str]:
        """生成改进建议"""
        suggestions = []

        if metrics.get("response_time", 100) < 60:
            suggestions.append("响应时间较长，考虑优化工具调用链或增加缓存")

        if metrics.get("error_rate", 100) < 80:
            suggestions.append("错误率较高，建议检查工具参数和错误处理逻辑")

        if metrics.get("task_completion", 100) < 70:
            suggestions.append("任务完成率偏低，可能需要增强 Agent 规划能力")

        if metrics.get("tool_usage", 0) < 20:
            suggestions.append("工具使用较少，可能存在工具匹配问题")

        if not suggestions:
            suggestions.append("整体性能良好，继续保持")

        return suggestions

    async def _calculate_trend(self, metrics: List[MetricSnapshot]) -> Dict[str, str]:
        """计算趋势"""
        # 简单实现：比较前后两个时间段的平均值
        if len(metrics) < 2:
            return {}

        mid = len(metrics) // 2
        first_half = metrics[:mid]
        second_half = metrics[mid:]

        trends = {}

        for metric_type in MetricType:
            first_avg = sum(m.value for m in first_half if m.metric_type == metric_type) / max(1, len([m for m in first_half if m.metric_type == metric_type]))
            second_avg = sum(m.value for m in second_half if m.metric_type == metric_type) / max(1, len([m for m in second_half if m.metric_type == metric_type]))

            if second_avg > first_avg * 1.1:
                trends[metric_type.value] = "improving"
            elif second_avg < first_avg * 0.9:
                trends[metric_type.value] = "declining"
            else:
                trends[metric_type.value] = "stable"

        return trends

    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话统计"""
        session = self._sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "request_count": session.request_count,
            "avg_response_time": session.total_response_time / max(session.request_count, 1),
            "tool_calls": dict(session.tool_calls),
            "error_count": len(session.errors),
            "user_feedback": session.user_feedback
        }

    def get_all_sessions(self) -> List[str]:
        """获取所有会话"""
        return list(self._sessions.keys())
