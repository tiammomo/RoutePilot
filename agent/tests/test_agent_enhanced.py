"""
Agent Enhanced 模块单元测试
"""

import pytest
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
    EvaluationResult
)
from agent_enhanced.feedback_loop import (
    FeedbackLoop,
    FeedbackType,
    FeedbackCategory,
    UserFeedback
)


class TestAdaptiveWorkflow:
    """自适应工作流测试"""

    def test_initialization(self):
        """测试初始化"""
        workflow = AdaptiveWorkflow()
        assert workflow.direct_executor is None
        assert workflow.react_executor is None

    @pytest.mark.asyncio
    async def test_assess_complexity_simple(self):
        """测试简单任务评估"""
        workflow = AdaptiveWorkflow()
        profile = await workflow._assess_complexity("什么是故宫")

        assert profile.complexity in [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM]

    @pytest.mark.asyncio
    async def test_assess_complexity_medium(self):
        """测试中等复杂度评估"""
        workflow = AdaptiveWorkflow()
        profile = await workflow._assess_complexity("帮我规划北京一日游路线")

        assert profile.complexity in [TaskComplexity.MEDIUM, TaskComplexity.COMPLEX]

    @pytest.mark.asyncio
    async def test_assess_complexity_complex(self):
        """测试复杂任务评估"""
        workflow = AdaptiveWorkflow()
        profile = await workflow._assess_complexity("请帮我安排一个完整的多日深度游行程")

        assert profile.complexity in [TaskComplexity.MEDIUM, TaskComplexity.COMPLEX]

    def test_select_strategy_simple(self):
        """测试简单任务策略选择"""
        workflow = AdaptiveWorkflow()
        profile = TaskProfile(
            original_request="test",
            complexity=TaskComplexity.SIMPLE,
            estimated_steps=1
        )

        strategy = workflow._select_strategy(profile)
        assert strategy == ExecutionStrategy.DIRECT

    def test_select_strategy_medium(self):
        """测试中等任务策略选择"""
        workflow = AdaptiveWorkflow()

        # 需要规划
        profile = TaskProfile(
            original_request="规划路线",
            complexity=TaskComplexity.MEDIUM,
            estimated_steps=3,
            requires_planning=True
        )

        strategy = workflow._select_strategy(profile)
        assert strategy == ExecutionStrategy.WORKFLOW

    def test_select_strategy_complex(self):
        """测试复杂任务策略选择"""
        workflow = AdaptiveWorkflow()
        profile = TaskProfile(
            original_request="完整行程",
            complexity=TaskComplexity.COMPLEX,
            estimated_steps=5
        )

        strategy = workflow._select_strategy(profile)
        assert strategy == ExecutionStrategy.MULTIAGENT


class TestAgentEvaluator:
    """Agent 评估器测试"""

    def test_initialization(self):
        """测试初始化"""
        evaluator = AgentEvaluator()
        assert len(evaluator._metrics) == 0
        assert len(evaluator._sessions) == 0

    def test_start_session(self):
        """测试开始会话"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1", "user-1")

        assert "session-1" in evaluator._sessions
        session = evaluator._sessions["session-1"]
        assert session.session_id == "session-1"
        assert session.user_id == "user-1"

    def test_end_session(self):
        """测试结束会话"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1")
        evaluator.end_session("session-1", user_feedback=5)

        session = evaluator._sessions["session-1"]
        assert session.end_time is not None
        assert session.user_feedback == 5

    def test_record_request(self):
        """测试记录请求"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1")
        evaluator.record_request("session-1", 2.5)

        assert evaluator._sessions["session-1"].request_count == 1
        assert evaluator._sessions["session-1"].total_response_time == 2.5

    def test_record_tool_usage(self):
        """测试记录工具使用"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1")
        evaluator.record_tool_usage("session-1", "search_cities")

        tool_calls = evaluator._sessions["session-1"].tool_calls
        assert tool_calls["search_cities"] == 1

    def test_record_error(self):
        """测试记录错误"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1")
        evaluator.record_error("session-1", "Tool not found")

        errors = evaluator._sessions["session-1"].errors
        assert len(errors) == 1
        assert errors[0] == "Tool not found"

    @pytest.mark.asyncio
    async def test_evaluate_no_data(self):
        """测试评估无数据"""
        evaluator = AgentEvaluator()
        result = await evaluator.evaluate()

        assert result.overall_score >= 0
        assert len(result.suggestions) > 0

    def test_get_session_stats(self):
        """测试获取会话统计"""
        evaluator = AgentEvaluator()
        evaluator.start_session("session-1")
        evaluator.record_request("session-1", 1.0)
        evaluator.record_request("session-1", 2.0)

        stats = evaluator.get_session_stats("session-1")
        assert stats["request_count"] == 2
        assert stats["avg_response_time"] == 1.5


class TestFeedbackLoop:
    """反馈循环测试"""

    def test_initialization(self):
        """测试初始化"""
        loop = FeedbackLoop()
        assert len(loop._feedbacks) == 0

    def test_collect_upvote(self):
        """测试收集点赞"""
        loop = FeedbackLoop()
        feedback = loop.collect_feedback(
            session_id="session-1",
            user_id="user-1",
            feedback_type=FeedbackType.UPVOTE
        )

        assert feedback.feedback_type == FeedbackType.UPVOTE
        assert len(loop._feedbacks) == 1

    def test_collect_rating(self):
        """测试收集评分"""
        loop = FeedbackLoop()
        loop.collect_feedback(
            session_id="session-1",
            user_id="user-1",
            feedback_type=FeedbackType.RATING,
            rating=4
        )

        assert loop._rating_distribution[4] == 1

    def test_collect_category(self):
        """测试收集类别反馈"""
        loop = FeedbackLoop()
        loop.collect_feedback(
            session_id="session-1",
            user_id="user-1",
            feedback_type=FeedbackType.DOWNVOTE,
            category=FeedbackCategory.ACCURACY
        )

        assert loop._category_stats[FeedbackCategory.ACCURACY.value] == 1

    def test_analyze_patterns(self):
        """测试分析模式"""
        loop = FeedbackLoop()

        # 收集多条低评分反馈
        for i in range(5):
            loop.collect_feedback(
                session_id=f"session-{i}",
                user_id="user-1",
                feedback_type=FeedbackType.RATING,
                rating=2,
                category=FeedbackCategory.ACCURACY
            )

        insights = loop.analyze_patterns()
        assert len(insights) > 0

    def test_suggest_adjustments(self):
        """测试建议调整"""
        loop = FeedbackLoop()

        # 收集低评分
        for i in range(3):
            loop.collect_feedback(
                session_id=f"session-{i}",
                user_id="user-1",
                feedback_type=FeedbackType.RATING,
                rating=2
            )

        adjustments = loop.suggest_adjustments()
        assert len(adjustments) >= 0

    def test_get_feedback_summary(self):
        """测试获取反馈摘要"""
        loop = FeedbackLoop()
        loop.collect_feedback(
            session_id="session-1",
            user_id="user-1",
            feedback_type=FeedbackType.RATING,
            rating=5
        )

        summary = loop.get_feedback_summary()
        assert summary["total_feedback"] == 1
        assert summary["average_rating"] == 5.0

    def test_clear_old_feedback(self):
        """测试清理旧反馈"""
        loop = FeedbackLoop()
        loop.collect_feedback(
            session_id="session-1",
            user_id="user-1",
            feedback_type=FeedbackType.UPVOTE
        )

        cleared = loop.clear_old_feedback(days=0)
        assert cleared >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
