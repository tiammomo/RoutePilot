"""
================================================================================
Feedback Loop - 反馈学习循环

收集用户反馈，持续优化 Agent 行为。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """反馈类型"""
    UPVOTE = "upvote"           # 点赞
    DOWNVOTE = "downvote"       # 踩
    RATING = "rating"           # 评分 (1-5)
    CORRECTION = "correction"   # 纠正
    SUGGESTION = "suggestion"   # 建议


class FeedbackCategory(Enum):
    """反馈类别"""
    ACCURACY = "accuracy"       # 准确性
    COMPLETENESS = "completeness"  # 完整性
    TONE = "tone"               # 语气
    FORMAT = "format"           # 格式
    TIMING = "timing"           # 时效性
    OTHER = "other"


@dataclass
class UserFeedback:
    """用户反馈"""
    feedback_id: str
    session_id: str
    user_id: str
    feedback_type: FeedbackType
    rating: Optional[int] = None  # 1-5
    category: Optional[FeedbackCategory] = None
    content: Optional[str] = None  # 纠正内容或建议
    original_response: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningInsight:
    """学习洞察"""
    insight_id: str
    category: str
    pattern: str
    frequency: int
    suggested_action: str
    confidence: float  # 0-1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class StrategyAdjustment:
    """策略调整"""
    adjustment_id: str
    strategy_type: str
    current_value: Any
    suggested_value: Any
    reason: str
    confidence: float
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class FeedbackLoop:
    """反馈学习循环

    负责：
    - 收集用户反馈
    - 分析反馈模式
    - 生成学习洞察
    - 调整执行策略
    """

    def __init__(self):
        """初始化"""
        self._feedbacks: List[UserFeedback] = []
        self._insights: List[LearningInsight] = []
        self._adjustments: List[StrategyAdjustment] = []

        # 反馈统计
        self._category_stats: Dict[str, int] = defaultdict(int)
        self._rating_distribution: Dict[int, int] = defaultdict(int)

    def collect_feedback(
        self,
        session_id: str,
        user_id: str,
        feedback_type: FeedbackType,
        rating: Optional[int] = None,
        category: Optional[FeedbackCategory] = None,
        content: Optional[str] = None,
        original_response: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UserFeedback:
        """收集反馈

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            feedback_type: 反馈类型
            rating: 评分 (1-5)
            category: 反馈类别
            content: 反馈内容
            original_response: 原始回复
            metadata: 额外数据

        Returns:
            用户反馈
        """
        import uuid

        feedback = UserFeedback(
            feedback_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            feedback_type=feedback_type,
            rating=rating,
            category=category,
            content=content,
            original_response=original_response,
            metadata=metadata or {}
        )

        self._feedbacks.append(feedback)

        # 更新统计
        if category:
            self._category_stats[category.value] += 1

        if rating:
            self._rating_distribution[rating] += 1

        logger.info(f"Collected feedback: {feedback_type.value} from user {user_id}")
        return feedback

    def analyze_patterns(self, time_window: int = 100) -> List[LearningInsight]:
        """分析反馈模式

        Args:
            time_window: 分析最近 N 条反馈

        Returns:
            学习洞察列表
        """
        recent_feedbacks = self._feedbacks[-time_window:]
        insights = []

        # 分析评分趋势
        ratings = [f.rating for f in recent_feedbacks if f.rating is not None]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            if avg_rating < 3:
                insight = LearningInsight(
                    insight_id=str(datetime.now().timestamp()),
                    category="overall",
                    pattern="low_rating_trend",
                    frequency=len(ratings),
                    suggested_action="优化回答质量和准确性",
                    confidence=0.8
                )
                insights.append(insight)

        # 分析差评类别
        low_rated = [f for f in recent_feedbacks if f.rating and f.rating <= 2]
        category_counts = defaultdict(int)
        for f in low_rated:
            if f.category:
                category_counts[f.category.value] += 1

        if category_counts:
            most_common = max(category_counts.items(), key=lambda x: x[1])
            insight = LearningInsight(
                insight_id=str(datetime.now().timestamp()),
                category="category",
                pattern=f"low_rating_{most_common[0]}",
                frequency=most_common[1],
                suggested_action=f"重点改进 {most_common[0]} 方面的问题",
                confidence=0.7
            )
            insights.append(insight)

        # 分析纠正反馈
        corrections = [f for f in recent_feedbacks if f.feedback_type == FeedbackType.CORRECTION]
        if corrections:
            insight = LearningInsight(
                insight_id=str(datetime.now().timestamp()),
                category="correction",
                pattern="correction_feedback",
                frequency=len(corrections),
                suggested_action="分析纠正内容，更新知识库",
                confidence=0.9
            )
            insights.append(insight)

        self._insights.extend(insights)
        return insights

    def suggest_adjustments(self) -> List[StrategyAdjustment]:
        """建议策略调整

        Returns:
            策略调整列表
        """
        import uuid

        adjustments = []

        # 基于评分调整
        if self._rating_distribution:
            avg_rating = sum(r * c for r, c in self._rating_distribution.items()) / sum(self._rating_distribution.values())

            if avg_rating < 3:
                adjustments.append(StrategyAdjustment(
                    adjustment_id=str(uuid.uuid4()),
                    strategy_type="response_style",
                    current_value="balanced",
                    suggested_value="more_detailed",
                    reason=f"用户平均评分较低 ({avg_rating:.1f})，建议增加回答详细程度",
                    confidence=0.7
                ))

        # 基于反馈类别调整
        if self._category_stats.get(FeedbackCategory.ACCURACY.value, 0) > 5:
            adjustments.append(StrategyAdjustment(
                adjustment_id=str(uuid.uuid4()),
                strategy_type="verification",
                current_value="low",
                suggested_value="high",
                reason="准确性反馈较多，建议增加事实核查",
                confidence=0.6
            ))

        self._adjustments.extend(adjustments)
        return adjustments

    def get_feedback_summary(self) -> Dict[str, Any]:
        """获取反馈摘要

        Returns:
            反馈统计摘要
        """
        total = len(self._feedbacks)

        if total == 0:
            return {"total": 0, "message": "No feedback collected"}

        # 计算平均评分
        ratings = [f.rating for f in self._feedbacks if f.rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        # 计算点赞/踩比例
        upvotes = sum(1 for f in self._feedbacks if f.feedback_type == FeedbackType.UPVOTE)
        downvotes = sum(1 for f in self._feedbacks if f.feedback_type == FeedbackType.DOWNVOTE)

        return {
            "total_feedback": total,
            "average_rating": round(avg_rating, 2) if avg_rating else None,
            "upvotes": upvotes,
            "downvotes": downvotes,
            "category_distribution": dict(self._category_stats),
            "rating_distribution": dict(self._rating_distribution),
            "insights_count": len(self._insights),
            "adjustments_count": len(self._adjustments)
        }

    def get_recent_feedback(self, limit: int = 10) -> List[UserFeedback]:
        """获取最近反馈"""
        return self._feedbacks[-limit:]

    def clear_old_feedback(self, days: int = 30) -> int:
        """清理旧反馈

        Args:
            days: 保留最近 N 天的反馈

        Returns:
            清理数量
        """
        import uuid

        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self._feedbacks)

        self._feedbacks = [
            f for f in self._feedbacks
            if datetime.fromisoformat(f.timestamp) > cutoff
        ]

        cleared = original_count - len(self._feedbacks)
        logger.info(f"Cleared {cleared} old feedback entries")
        return cleared


# 导入 timedelta
from datetime import timedelta
