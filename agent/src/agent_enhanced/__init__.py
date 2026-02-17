"""
================================================================================
Agent Enhanced - 智能编排增强模块

v2.5.0 新增：自适应工作流、性能评估、反馈学习循环
================================================================================
"""

from agent_enhanced.adaptive_workflow import (
    AdaptiveWorkflow,
    TaskComplexity,
    ExecutionStrategy,
    TaskProfile,
    ExecutionResult
)

from agent_enhanced.evaluator import (
    AgentEvaluator,
    MetricType,
    MetricSnapshot,
    EvaluationResult,
    SessionMetrics
)

from agent_enhanced.feedback_loop import (
    FeedbackLoop,
    FeedbackType,
    FeedbackCategory,
    UserFeedback,
    LearningInsight,
    StrategyAdjustment
)

__version__ = "2.5.0"

__all__ = [
    # Adaptive Workflow
    "AdaptiveWorkflow",
    "TaskComplexity",
    "ExecutionStrategy",
    "TaskProfile",
    "ExecutionResult",
    # Evaluator
    "AgentEvaluator",
    "MetricType",
    "MetricSnapshot",
    "EvaluationResult",
    "SessionMetrics",
    # Feedback Loop
    "FeedbackLoop",
    "FeedbackType",
    "FeedbackCategory",
    "UserFeedback",
    "LearningInsight",
    "StrategyAdjustment"
]
