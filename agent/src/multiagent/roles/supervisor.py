"""
================================================================================
Supervisor Agent - 监督 Agent

负责结果审核、质量控制和任务验收。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from multiagent.roles.specialist import TaskResult, TaskStatus

logger = logging.getLogger(__name__)


class ReviewStatus(Enum):
    """审核状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


@dataclass
class ReviewResult:
    """审核结果"""
    task_id: str
    status: ReviewStatus
    score: float = 0.0  # 0-100
    feedback: str = ""
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityMetrics:
    """质量指标"""
    accuracy: float = 0.0        # 准确性
    completeness: float = 0.0     # 完整性
    relevance: float = 0.0        # 相关性
    coherence: float = 0.0       # 连贯性
    overall: float = 0.0          # 总体评分


class SupervisorAgent:
    """Supervisor Agent

    负责：
    - 审核任务结果
    - 评估质量指标
    - 提供改进建议
    - 决定是否需要重做
    """

    def __init__(self, agent_id: str, llm_client: Optional[Any] = None):
        """
        Args:
            agent_id: Agent ID
            llm_client: LLM 客户端
        """
        self.agent_id = agent_id
        self.llm_client = llm_client

        # 审核历史
        self._review_history: List[ReviewResult] = []

    async def review_result(
        self,
        task_id: str,
        task_description: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None
    ) -> ReviewResult:
        """审核任务结果

        Args:
            task_id: 任务 ID
            task_description: 任务描述
            result: 任务结果
            criteria: 审核标准

        Returns:
            审核结果
        """
        logger.info(f"Supervisor {self.agent_id} reviewing task {task_id}")

        # 评估质量
        metrics = await self._evaluate_quality(task_description, result, criteria)

        # 确定审核状态
        if metrics.overall >= 80:
            status = ReviewStatus.APPROVED
            feedback = "任务完成质量良好"
        elif metrics.overall >= 60:
            status = ReviewStatus.NEEDS_REVISION
            feedback = "任务基本完成，但需要小幅改进"
        else:
            status = ReviewStatus.REJECTED
            feedback = "任务完成质量不达标，需要重新执行"

        # 生成建议
        suggestions = self._generate_suggestions(metrics)

        review_result = ReviewResult(
            task_id=task_id,
            status=status,
            score=metrics.overall,
            feedback=feedback,
            suggestions=suggestions,
            metadata={
                "metrics": {
                    "accuracy": metrics.accuracy,
                    "completeness": metrics.completeness,
                    "relevance": metrics.relevance,
                    "coherence": metrics.coherence
                }
            }
        )

        self._review_history.append(review_result)
        logger.info(f"Review completed for task {task_id}: {status.value} (score: {metrics.overall})")

        return review_result

    async def review_batch(
        self,
        results: List[TaskResult],
        criteria: Optional[Dict[str, Any]] = None
    ) -> List[ReviewResult]:
        """批量审核

        Args:
            results: 任务结果列表
            criteria: 审核标准

        Returns:
            审核结果列表
        """
        review_results = []

        for result in results:
            review = await self.review_result(
                task_id=result.task_id,
                task_description="",
                result=result.result,
                criteria=criteria
            )
            review_results.append(review)

        return review_results

    async def _evaluate_quality(
        self,
        task_description: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None
    ) -> QualityMetrics:
        """评估质量指标"""
        # 基础评估：检查结果是否存在
        if result is None:
            return QualityMetrics(overall=0.0)

        # 类型检查
        if isinstance(result, dict):
            # 检查必要的字段
            required_fields = criteria.get("required_fields", []) if criteria else []
            completeness = sum(1 for f in required_fields if f in result) / max(len(required_fields), 1)
        elif isinstance(result, str):
            completeness = 1.0 if len(result) > 10 else 0.5
        elif isinstance(result, list):
            completeness = 1.0 if len(result) > 0 else 0.0
        else:
            completeness = 1.0

        # 基础指标（简化实现）
        metrics = QualityMetrics(
            accuracy=0.85,         # 默认准确性
            completeness=completeness,
            relevance=0.80,        # 默认相关性
            coherence=0.85,        # 默认连贯性
            overall=0.0
        )

        # 计算总体评分
        metrics.overall = (
            metrics.accuracy * 0.3 +
            metrics.completeness * 0.3 +
            metrics.relevance * 0.2 +
            metrics.coherence * 0.2
        ) * 100

        return metrics

    def _generate_suggestions(self, metrics: QualityMetrics) -> List[str]:
        """生成改进建议"""
        suggestions = []

        if metrics.completeness < 0.8:
            suggestions.append("建议补充更多详细信息以提高完整性")

        if metrics.relevance < 0.8:
            suggestions.append("建议检查内容是否与用户需求高度相关")

        if metrics.coherence < 0.8:
            suggestions.append("建议优化内容结构和逻辑连贯性")

        if not suggestions:
            suggestions.append("整体质量良好，继续保持")

        return suggestions

    def get_review_stats(self) -> Dict[str, Any]:
        """获取审核统计"""
        total = len(self._review_history)
        if total == 0:
            return {"total": 0, "approved": 0, "rejected": 0, "needs_revision": 0}

        approved = sum(1 for r in self._review_history if r.status == ReviewStatus.APPROVED)
        rejected = sum(1 for r in self._review_history if r.status == ReviewStatus.REJECTED)
        needs_revision = sum(1 for r in self._review_history if r.status == ReviewStatus.NEEDS_REVISION)
        avg_score = sum(r.score for r in self._review_history) / total

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "needs_revision": needs_revision,
            "approval_rate": approved / total * 100,
            "average_score": avg_score
        }

    def get_review_history(self) -> List[ReviewResult]:
        """获取审核历史"""
        return self._review_history.copy()
