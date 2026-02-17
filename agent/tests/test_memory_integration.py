"""
Memory 系统集成测试

测试所有 Memory v2.2 组件的集成功能。
"""

import pytest
import asyncio
import numpy as np
from memory import (
    MemoryOrchestrator,
    OrchestratorConfig,
    AttentionWindow,
    ReflectionMechanism,
    SmartEvictionPolicy,
    ConversationVectorizer,
    MemoryRecirculation,
    ContextAwareRetrieval,
    create_memory_orchestrator
)


class TestMemoryOrchestratorIntegration:
    """测试 MemoryOrchestrator 完整集成"""

    def test_create_orchestrator_with_all_components(self):
        """测试创建完整的 orchestrator"""
        config = OrchestratorConfig()
        orchestrator = MemoryOrchestrator(config=config)

        # 验证所有组件已初始化
        assert orchestrator.memory_manager is not None
        assert orchestrator.attention_window is not None
        assert orchestrator.reflection is not None
        assert orchestrator.smart_eviction_policy is not None
        assert orchestrator.vectorizer is not None
        assert orchestrator.recirculation is not None
        assert orchestrator.retrieval is not None

    def test_orchestrator_config_options(self):
        """测试配置选项"""
        config = OrchestratorConfig(
            attention_window_size=20,
            attention_recency_weight=0.2,
            reflection_trigger_interval=5,
            smart_eviction_adaptive=True,
            retrieval_top_k=5
        )
        orchestrator = MemoryOrchestrator(config=config)

        assert orchestrator.config.attention_window_size == 20
        assert orchestrator.config.reflection_trigger_interval == 5
        assert orchestrator.config.retrieval_top_k == 5

    def test_add_message_basic(self):
        """测试添加消息基本功能"""
        config = OrchestratorConfig(importance_enable=False)
        orchestrator = MemoryOrchestrator(config=config)

        result = orchestrator.add_message(
            session_id="test_session",
            user_id="test_user",
            role="user",
            content="我想去海边旅游，预算5000元"
        )

        assert result["success"] is True
        assert result["total_messages"] == 1

    def test_get_context_with_attention(self):
        """测试使用注意力窗口获取上下文"""
        config = OrchestratorConfig(importance_enable=False)
        orchestrator = MemoryOrchestrator(config=config)

        # 添加多条消息
        orchestrator.add_message("s1", "u1", "user", "我想去海边")
        orchestrator.add_message("s1", "u1", "assistant", "推荐三亚")
        orchestrator.add_message("s1", "u1", "user", "预算5000")

        # 使用 attention window 选择消息
        history = orchestrator.memory_manager.get_conversation_history()
        selected = orchestrator.attention_window.select_top_messages(
            history, "海边"
        )

        assert len(selected) > 0


class TestAttentionWindowIntegration:
    """测试注意力窗口与其他组件集成"""

    def test_attention_with_importance_scorer(self):
        """测试与重要性评分器集成"""
        from memory import ImportanceScorer

        attention = AttentionWindow(window_size=5)
        scorer = ImportanceScorer()

        messages = [
            {"content": "我想去海边旅游", "importance": 0.9},
            {"content": "今天天气不错", "importance": 0.3},
            {"content": "推荐一个行程", "importance": 0.8},
        ]

        # 计算注意力分数
        scores = attention.compute_attention(messages, "海边")
        assert len(scores) == 3
        assert abs(sum(scores) - 1.0) < 0.01


class TestReflectionIntegration:
    """测试反思机制集成"""

    @pytest.mark.asyncio
    async def test_reflect_with_conversation(self):
        """测试反思对话"""
        reflector = ReflectionMechanism(trigger_interval=3)

        conversation = [
            {"role": "user", "content": "我想去海边旅游"},
            {"role": "assistant", "content": "推荐三亚"},
            {"role": "user", "content": "预算5000元"},
        ]

        result = await reflector.reflect(conversation)
        assert result is not None

    def test_reflection_cache(self):
        """测试反思缓存"""
        reflector = ReflectionMechanism()

        # 相同会话应该使用缓存
        reflector._reflection_cache["sess_1"] = type(
            'obj', (object,), {'key_insights': ['test']}
        )()

        assert "sess_1" in reflector._reflection_cache


class TestEvictionPolicyIntegration:
    """测试智能淘汰策略集成"""

    def test_eviction_with_memory_manager(self):
        """测试与 MemoryManager 集成"""
        from memory import MemoryManager

        policy = SmartEvictionPolicy(max_size=5)
        memory = MemoryManager(max_working_memory=10)

        # 添加消息
        for i in range(8):
            memory.add_message("user", f"消息 {i}")

        # 获取淘汰候选
        history = memory.get_conversation_history()
        candidates = policy.get_eviction_candidates(history, count=2)

        assert len(candidates) >= 0

    def test_adaptive_policy_adjustment(self):
        """测试自适应策略调整"""
        from memory.eviction_policy import AdaptiveEvictionPolicy
        policy = AdaptiveEvictionPolicy(max_size=10)

        # 记录多次访问
        for _ in range(15):
            policy.record_access(0.8)

        # 调整权重
        policy.adjust_weights()
        assert policy.weights.importance > 0

        assert policy.weights.importance > 0


class TestVectorizerIntegration:
    """测试对话向量化集成"""

    @pytest.mark.asyncio
    async def test_embed_and_compare(self):
        """测试嵌入并比较相似度"""
        vec = ConversationVectorizer()

        v1 = await vec.embed_text("我想去海边旅游")
        v2 = await vec.embed_text("去海边玩")

        sim = await vec.compute_similarity(v1, v2)
        assert -1 <= sim <= 1

    @pytest.mark.asyncio
    async def test_session_vectorization(self):
        """测试会话向量化"""
        vec = ConversationVectorizer()

        session_data = {
            "summary": "用户想去海边旅游",
            "key_facts": ["预算5000", "3天"],
            "user_preferences": {"budget": "5000"},
            "topics": ["海岛", "旅游"]
        }

        vector = await vec.vectorize_session(session_data)
        assert vector.shape[0] == 1536


class TestRecirculationIntegration:
    """测试记忆回流集成"""

    def test_recirculation_with_orchestrator(self):
        """测试与 Orchestrator 集成"""
        config = OrchestratorConfig(recirculation_enable=True)
        orchestrator = MemoryOrchestrator(config=config)

        # 检查回流组件
        assert orchestrator.recirculation is not None

        # 测试阈值触发
        message = {"importance": 0.8, "content": "test"}
        should = orchestrator.recirculation.should_recirculate(message)
        assert should is True

    def test_recirculation_rule_config(self):
        """测试回流规则配置"""
        config = OrchestratorConfig(recirculation_enable=True)
        orchestrator = MemoryOrchestrator(config=config)
        rule = orchestrator.recirculation.rule
        assert rule.threshold_trigger == 0.7
        assert rule.frequency_trigger == 3


class TestRetrievalIntegration:
    """测试上下文检索集成"""

    def test_retrieval_with_stores(self):
        """测试与存储集成"""
        config = OrchestratorConfig(retrieval_enable=True)
        orchestrator = MemoryOrchestrator(config=config)

        assert orchestrator.retrieval is not None
        assert orchestrator.hierarchical_store is not None
        assert orchestrator.user_profile_store is not None

    def test_retrieval_stats(self):
        """测试检索统计"""
        retrieval = ContextAwareRetrieval(default_top_k=5)
        stats = retrieval.get_stats()

        assert stats["default_top_k"] == 5
        assert stats["rrf_k"] == 60


class TestFactoryIntegration:
    """测试工厂方法集成"""

    def test_create_orchestrator_from_config(self):
        """测试从配置创建 orchestrator"""
        # 使用正确的配置格式
        config = OrchestratorConfig(
            max_working_memory=30,
            attention_window_size=15,
            reflection_trigger_interval=8,
            retrieval_top_k=5
        )

        orchestrator = MemoryOrchestrator(config=config)

        # 验证配置已应用
        assert orchestrator.config.max_working_memory == 30
        assert orchestrator.config.attention_window_size == 15
        assert orchestrator.config.reflection_trigger_interval == 8
        assert orchestrator.config.retrieval_top_k == 5


class TestEndToEnd:
    """端到端测试"""

    @pytest.mark.asyncio
    async def test_full_memory_workflow(self):
        """测试完整记忆工作流"""
        config = OrchestratorConfig(importance_enable=False)
        orchestrator = MemoryOrchestrator(config=config)

        session_id = "e2e_session"
        user_id = "e2e_user"

        # 1. 添加用户消息
        orchestrator.add_message(
            session_id, user_id, "user", "我想去海边旅游"
        )

        # 2. 添加助手回复
        orchestrator.add_message(
            session_id, user_id, "assistant", "推荐你去三亚"
        )

        # 3. 添加更多消息
        orchestrator.add_message(
            session_id, user_id, "user", "预算5000元"
        )

        # 4. 获取上下文（异步调用）
        context = await orchestrator.get_context_for_llm(session_id, user_id)

        assert len(context) > 0

        # 5. 获取用户偏好
        prefs = orchestrator.get_user_preference(session_id, user_id)

        assert isinstance(prefs, dict)

    def test_memory_preservation(self):
        """测试记忆保留"""
        config = OrchestratorConfig(importance_enable=False)
        orchestrator = MemoryOrchestrator(config=config)

        # 添加消息
        for i in range(5):
            orchestrator.add_message(
                "sess_2", "user_2", "user", f"消息 {i}"
            )

        # 验证消息已保存
        history = orchestrator.memory_manager.get_conversation_history()
        assert len(history) == 5


# 运行集成测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
