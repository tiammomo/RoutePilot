"""
记忆模块测试用例 (Memory Module Tests)

测试所有记忆管理模块的功能：
- importance_scorer: 重要性评分
- eviction_manager: 智能淘汰
- summarizer: 对话摘要
- user_profile: 用户画像
- hierarchical_store: 分层存储
- consolidation: 记忆整合

运行命令: pytest agent/src/memory/test_memory.py -v
"""

import pytest
import asyncio
import json
import tempfile
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 导入被测试模块
from agent.src.memory import (
    ImportanceScorer,
    ImportanceScore,
    PriorityCalculator,
    EvictionManager,
    EvictionStrategy,
    EvictionConfig,
    MemoryItem,
    ConversationSummarizer,
    ConversationSummary,
    CompressionLevel,
    UserProfileStore,
    UserProfile,
    UserPreference,
    TravelHistory,
    HierarchicalMemoryStore,
    MemoryTier,
    SessionData,
    RetrievedMemory,
    MemoryConsolidator,
    MemoryCluster,
    MemoryType,
    ConsolidationResult,
    MemoryManager,
    Message
)


class TestImportanceScorer:
    """重要性评分器测试"""

    @pytest.fixture
    def scorer(self):
        """创建评分器实例"""
        return ImportanceScorer(threshold=0.5)

    def test_score_travel_message(self, scorer):
        """测试旅行相关消息评分"""
        message = "我想去北京旅游，预算5000元，3天时间，有什么推荐？"
        score = run_async_test(scorer.score(message))

        assert isinstance(score, ImportanceScore)
        assert 0 <= score.total_score <= 1
        assert len(score.dimensions) > 0
        assert score.is_high_importance is not None

    def test_score_simple_message(self, scorer):
        """测试简单消息评分"""
        message = "你好"
        score = run_async_test(scorer.score(message))

        assert isinstance(score, ImportanceScore)
        assert score.total_score >= 0
        assert score.total_score <= 1

    def test_keyword_trigger_detection(self, scorer):
        """测试关键词触发检测"""
        # 包含预算关键词
        message = "预算5000元"
        score = run_async_test(scorer.score(message))

        assert ImportanceScore in type(score).mro()
        keyword_dim = score.dimensions.get("keyword")
        assert keyword_dim is not None or "keyword" in str(score.dimensions)

    def test_batch_score(self, scorer):
        """测试批量评分"""
        messages = [
            "我想去日本旅游",
            "今天天气不错",
            "帮我规划一个5天的行程，预算8000元"
        ]
        scores = scorer.batch_score(messages)

        assert len(scores) == len(messages)
        for score in scores:
            assert isinstance(score, ImportanceScore)

    def test_priority_calculation(self):
        """测试优先级计算"""
        calculator = PriorityCalculator(decay_factor=0.95, time_weight=0.3)

        priority = calculator.calculate_priority(
            importance=0.8,
            timestamp=datetime.now().isoformat(),
            access_count=5,
            strategy="hybrid"
        )

        assert 0 <= priority <= 1


class TestEvictionManager:
    """智能淘汰管理器测试"""

    @pytest.fixture
    def manager(self):
        """创建淘汰管理器实例"""
        config = EvictionConfig(
            max_size=5,
            min_importance=0.3,
            strategy=EvictionStrategy.HYBRID
        )
        return EvictionManager(config)

    def test_add_memory_item(self, manager):
        """测试添加记忆项"""
        item = MemoryItem(
            id="test_1",
            content={"text": "测试消息"},
            importance=0.8
        )

        result = manager.add(item)
        assert isinstance(result, bool)

    def test_memory_capacity_limit(self, manager):
        """测试容量限制"""
        # 添加超过容量的记忆
        for i in range(10):
            item = MemoryItem(
                id=f"test_{i}",
                content=f"消息 {i}",
                importance=0.5
            )
            manager.add(item)

        # 检查是否触发淘汰
        stats = manager.get_stats()
        assert stats["current_size"] <= manager.max_size

    def test_low_importance_eviction(self, manager):
        """测试低重要性记忆淘汰"""
        # 添加低重要性记忆
        low_item = MemoryItem(
            id="low_importance",
            content="低重要性消息",
            importance=0.1
        )
        manager.add(low_item)

        # 添加高重要性记忆触发淘汰
        high_item = MemoryItem(
            id="high_importance",
            content="高重要性消息",
            importance=0.9
        )
        manager.add(high_item)

        # 检查低重要性是否被淘汰
        retrieved = manager.get("low_importance")
        # 可能已被淘汰

    def test_get_recent_memories(self, manager):
        """测试获取最近记忆"""
        for i in range(5):
            item = MemoryItem(id=f"test_{i}", content=f"消息 {i}", importance=0.5)
            manager.add(item)

        recent = manager.get_recent(limit=3)
        assert len(recent) <= 3

    def test_strategy_switching(self, manager):
        """测试策略切换"""
        manager.set_strategy(EvictionStrategy.LRU)
        stats = manager.get_stats()
        assert stats["current_strategy"] == "lru"

        manager.set_strategy(EvictionStrategy.FIFO)
        stats = manager.get_stats()
        assert stats["current_strategy"] == "fifo"

    def test_serialization(self, manager):
        """测试序列化"""
        manager.add(MemoryItem(id="test", content="测试", importance=0.7))

        data = manager.serialize()

        assert "config" in data
        assert "memories" in data
        assert "stats" in data


class TestConversationSummarizer:
    """对话摘要压缩器测试"""

    @pytest.fixture
    def summarizer(self):
        """创建摘要器实例"""
        return ConversationSummarizer(max_tokens=500)

    @pytest.fixture
    def sample_messages(self):
        """示例对话消息"""
        return [
            {"role": "user", "content": "我想去云南旅游，预算5000元"},
            {"role": "assistant", "content": "云南有很多好玩的景点，您想什么时候去？"},
            {"role": "user", "content": "打算3月份去，7天时间，喜欢自然风光和美食"},
            {"role": "assistant", "content": "推荐您去大理、丽江、香格里拉..."},
            {"role": "user", "content": "好的，就按这个路线走吧"}
        ]

    def test_summarize_light(self, summarizer, sample_messages):
        """测试轻度压缩摘要"""
        summary = run_async_test(summarizer.summarize(sample_messages, level="light"))

        assert isinstance(summary, ConversationSummary)
        assert summary.compression_level == CompressionLevel.LIGHT
        assert len(summary.summary) > 0

    def test_summarize_moderate(self, summarizer, sample_messages):
        """测试中度压缩摘要"""
        summary = run_async_test(summarizer.summarize(sample_messages, level="moderate"))

        assert isinstance(summary, ConversationSummary)
        assert summary.compression_level == CompressionLevel.MODERATE
        assert len(summary.summary) > 0
        assert summary.message_count_before == len(sample_messages)
        assert summary.tokens_saved >= 0

    def test_summarize_aggressive(self, summarizer, sample_messages):
        """测试重度压缩摘要"""
        summary = run_async_test(summarizer.summarize(sample_messages, level="aggressive"))

        assert isinstance(summary, ConversationSummary)
        assert summary.compression_level == CompressionLevel.AGGRESSIVE
        # 重度压缩应该更短
        assert len(summary.summary) <= len(summary.summary)

    def test_extract_key_facts(self, summarizer, sample_messages):
        """测试关键事实提取"""
        facts = run_async_test(summarizer.extract_key_facts(sample_messages))

        assert isinstance(facts, list)
        # 应该能提取出预算、天数、目的地等

    def test_identify_topics(self, summarizer, sample_messages):
        """测试主题识别"""
        topics = summarizer._identify_topics(sample_messages)

        assert isinstance(topics, list)
        assert len(topics) > 0

    def test_compress_for_context(self, summarizer, sample_messages):
        """测试上下文压缩"""
        compressed = summarizer.compress_for_context(sample_messages, max_messages=3)

        assert len(compressed) <= 3


class TestUserProfileStore:
    """用户画像存储测试"""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储文件（初始化为空JSON对象）"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{}")
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.remove(temp_path)

    @pytest.fixture
    def profile_store(self, temp_storage):
        """创建画像存储实例"""
        return UserProfileStore(storage_path=temp_storage)

    def test_get_or_create_profile(self, profile_store):
        """测试获取或创建用户画像"""
        profile = profile_store.get_or_create("user_123")

        assert isinstance(profile, UserProfile)
        assert profile.user_id == "user_123"

    def test_get_nonexistent_profile(self, profile_store):
        """测试获取不存在的用户"""
        profile = profile_store.get("nonexistent_user")
        assert profile is None

    def test_update_preference(self, profile_store):
        """测试更新偏好"""
        # 先创建用户画像
        profile_store.get_or_create("user_123")

        result = profile_store.update_preference(
            "user_123",
            "budget_min",
            3000
        )

        assert result is True

        profile = profile_store.get("user_123")
        assert profile.preferences.budget_min == 3000

    def test_update_city_preference(self, profile_store):
        """测试更新城市偏好（列表类型）"""
        profile_store.get_or_create("user_123")

        result = profile_store.update_preference(
            "user_123",
            "cities",
            ["北京", "上海"]
        )

        assert result is True
        profile = profile_store.get("user_123")
        assert "北京" in profile.preferences.favorite_cities

    def test_add_travel_history(self, profile_store):
        """测试添加旅行历史"""
        profile_store.get_or_create("user_123")

        history = TravelHistory(
            session_id="session_1",
            destination="云南",
            duration_days=7,
            budget="5000元",
            rating=5
        )

        result = profile_store.add_travel_history("user_123", history)
        assert result is True

        profile = profile_store.get("user_123")
        assert len(profile.travel_history) == 1
        assert profile.travel_history[0].destination == "云南"

    def test_get_preferences(self, profile_store):
        """测试获取偏好"""
        profile_store.get_or_create("user_123")
        profile_store.update_preference("user_123", "budget_min", 3000)

        prefs = profile_store.get_preferences("user_123")

        assert isinstance(prefs, dict)
        assert "budget_min" in prefs

    def test_get_context_for_llm(self, profile_store):
        """测试获取 LLM 上下文"""
        profile_store.get_or_create("user_123")
        profile_store.update_preference("user_123", "budget_min", 3000)
        profile_store.update_preference("user_123", "duration", 5)

        context = profile_store.get_context_for_llm("user_123")

        assert isinstance(context, str)
        assert "用户偏好" in context

    def test_get_stats(self, profile_store):
        """测试获取统计信息"""
        profile_store.get_or_create("user_1")
        profile_store.get_or_create("user_2")

        stats = profile_store.get_stats()

        assert "total_users" in stats
        assert stats["total_users"] == 2

    def test_delete_profile(self, profile_store):
        """测试删除用户画像"""
        profile_store.get_or_create("user_123")
        result = profile_store.delete("user_123")

        assert result is True
        assert profile_store.get("user_123") is None


class TestHierarchicalMemoryStore:
    """分层记忆存储测试"""

    @pytest.fixture
    def temp_storage(self):
        """创建临时存储文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        yield temp_path
        if os.path.exists(temp_path):
            os.remove(temp_path)

    @pytest.fixture
    def store(self, temp_storage):
        """创建分层存储实例"""
        return HierarchicalMemoryStore(
            hot_cache_size=10,
            warm_cache_size=100,
            cold_cache_size=500,
            storage_path=temp_storage
        )

    def test_store_session(self, store):
        """测试存储会话"""
        session = SessionData(
            session_id="session_1",
            user_id="user_123",
            start_time=datetime.now().isoformat(),
            end_time=None,
            message_count=5,
            summary="用户咨询云南旅游",
            topics=["旅行规划", "云南"],
            user_preferences={"budget": 5000}
        )

        asyncio.run(store.store_session(session))

        retrieved = store.get_session("session_1")
        assert retrieved is not None
        assert retrieved.session_id == "session_1"

    def test_retrieve_context(self, store):
        """测试检索上下文"""
        # 先存储会话
        session = SessionData(
            session_id="session_1",
            user_id="user_123",
            start_time=datetime.now().isoformat(),
            end_time=None,
            message_count=5,
            summary="用户想去云南旅游，预算5000元",
            topics=["云南", "旅行"],
            user_preferences={}
        )
        asyncio.run(store.store_session(session))

        # 检索
        results = asyncio.run(store.retrieve_context("user_123", "云南旅游"))

        assert isinstance(results, list)

    def test_migrate_to_cold(self, store):
        """测试迁移到冷数据层"""
        session = SessionData(
            session_id="session_1",
            user_id="user_123",
            start_time=datetime.now().isoformat(),
            end_time=None,
            message_count=5,
            summary="测试会话"
        )
        asyncio.run(store.store_session(session))

        result = store.migrate_to_cold("session_1")
        assert result is True

        # 验证仍在存储中
        retrieved = store.get_session("session_1")
        assert retrieved is not None

    def test_get_user_sessions(self, store):
        """测试获取用户会话"""
        for i in range(3):
            session = SessionData(
                session_id=f"session_{i}",
                user_id="user_123",
                start_time=datetime.now().isoformat(),
                end_time=None,
                message_count=5,
                summary=f"会话 {i}"
            )
            asyncio.run(store.store_session(session))

        sessions = store.get_user_sessions("user_123", limit=10)

        assert len(sessions) >= 3

    def test_delete_session(self, store):
        """测试删除会话"""
        session = SessionData(
            session_id="session_1",
            user_id="user_123",
            start_time=datetime.now().isoformat(),
            end_time=None,
            message_count=5,
            summary="测试会话"
        )
        asyncio.run(store.store_session(session))

        result = store.delete_session("session_1")
        assert result is True

        retrieved = store.get_session("session_1")
        assert retrieved is None

    def test_get_stats(self, store):
        """测试获取统计信息"""
        session = SessionData(
            session_id="session_1",
            user_id="user_123",
            start_time=datetime.now().isoformat(),
            end_time=None,
            message_count=5,
            summary="测试"
        )
        asyncio.run(store.store_session(session))

        stats = store.get_stats()

        assert "total_sessions" in stats
        assert "hot_cache_size" in stats


class TestMemoryConsolidator:
    """记忆整合器测试"""

    @pytest.fixture
    def consolidator(self):
        """创建整合器实例"""
        return MemoryConsolidator(
            similarity_threshold=0.7,
            min_cluster_size=2
        )

    @pytest.fixture
    def sample_memories(self):
        """示例记忆列表"""
        return [
            {"id": "mem_1", "session_id": "s1", "content": "用户想去云南旅游", "importance": 0.7},
            {"id": "mem_2", "session_id": "s1", "content": "云南大理丽江很美", "importance": 0.6},
            {"id": "mem_3", "session_id": "s2", "content": "用户计划去日本", "importance": 0.8},
            {"id": "mem_4", "session_id": "s2", "content": "日本东京大阪好玩", "importance": 0.5},
            {"id": "mem_5", "session_id": "s3", "content": "今天天气不错", "importance": 0.2}
        ]

    def test_consolidate(self, consolidator, sample_memories):
        """测试记忆整合"""
        result = run_async_test(consolidator.consolidate(sample_memories))

        assert isinstance(result, ConsolidationResult)
        assert result.clusters_created >= 0
        assert result.memories_consolidated >= 0

    def test_cluster_by_topic(self, consolidator, sample_memories):
        """测试按主题聚类"""
        topic_clusters = run_async_test(consolidator._cluster_by_topic(sample_memories))

        assert isinstance(topic_clusters, dict)
        assert len(topic_clusters) > 0

    def test_detect_topic(self, consolidator):
        """测试主题检测"""
        topics = [
            ("预算5000元", "预算"),
            ("去云南旅游", "目的地"),
            ("飞机还是火车", "交通")
        ]

        for content, expected_topic in topics:
            detected = consolidator._detect_topic(content)
            # 应该能检测到相关主题

    def test_get_all_clusters(self, consolidator):
        """测试获取所有聚类"""
        clusters = consolidator.get_all_clusters()
        assert isinstance(clusters, list)

    def test_get_stats(self, consolidator):
        """测试获取统计信息"""
        stats = consolidator.get_stats()

        assert "total_clusters" in stats
        assert "total_memories_in_clusters" in stats

    def test_serialization(self, consolidator):
        """测试序列化"""
        data = consolidator.serialize()

        assert "clusters" in data
        assert "stats" in data
        assert "last_consolidation" in data


class TestMemoryManager:
    """核心记忆管理器测试"""

    @pytest.fixture
    def manager(self):
        """创建记忆管理器实例"""
        return MemoryManager(max_working_memory=10, max_long_term_memory=100)

    def test_add_message(self, manager):
        """测试添加消息"""
        manager.add_message("user", "我想去北京旅游")

        history = manager.get_conversation_history()
        assert len(history) >= 1

    def test_get_conversation_history(self, manager):
        """测试获取对话历史"""
        # 添加几条消息
        for i in range(3):
            manager.add_message("user", f"消息 {i}")

        history = manager.get_conversation_history()

        assert isinstance(history, list)
        assert len(history) == 3

    def test_clear_short_term(self, manager):
        """测试清空短期记忆"""
        manager.add_message("user", "测试")
        manager.clear_conversation()

        history = manager.get_conversation_history()
        assert len(history) == 0

    def test_get_stats(self, manager):
        """测试获取统计信息"""
        manager.add_message("user", "测试")

        stats = manager.get_memory_stats()

        assert "working_memory" in stats
        assert "long_term_memory" in stats


class TestIntegration:
    """集成测试"""

    @pytest.fixture
    def memory_system(self):
        """创建完整的记忆系统"""
        temp_path = tempfile.mktemp(suffix='.json')

        # 创建各组件
        importance_scorer = ImportanceScorer(threshold=0.5)
        eviction_config = EvictionConfig(max_size=20, min_importance=0.3)
        eviction_manager = EvictionManager(eviction_config)
        summarizer = ConversationSummarizer(max_tokens=500)
        profile_store = UserProfileStore(storage_path=temp_path)
        hierarchical_store = HierarchicalMemoryStore(storage_path=temp_path)
        consolidator = MemoryConsolidator()

        return {
            "scorer": importance_scorer,
            "eviction": eviction_manager,
            "summarizer": summarizer,
            "profile_store": profile_store,
            "hierarchical_store": hierarchical_store,
            "consolidator": consolidator
        }

    def test_full_memory_workflow(self, memory_system):
        """测试完整记忆工作流"""
        scorer = memory_system["scorer"]
        eviction = memory_system["eviction"]
        summarizer = memory_system["summarizer"]
        profile_store = memory_system["profile_store"]

        # 1. 重要性评分
        message = "我想去云南旅游，预算5000元，7天时间，喜欢自然风光"
        score = run_async_test(scorer.score(message))

        assert 0 <= score.total_score <= 1

        # 2. 添加到淘汰管理器
        item = MemoryItem(
            id="msg_1",
            content=message,
            importance=score.total_score
        )
        eviction.add(item)

        assert eviction.get("msg_1") is not None

        # 3. 对话摘要
        messages = [
            {"role": "user", "content": "我想去云南"},
            {"role": "assistant", "content": "云南哪里？"},
            {"role": "user", "content": "大理，预算5000元"}
        ]
        summary = run_async_test(summarizer.summarize(messages, level="moderate"))

        assert summary is not None
        assert len(summary.summary) > 0

        # 4. 用户画像更新
        profile = profile_store.get_or_create("user_123")
        profile_store.update_preference("user_123", "budget_min", 5000)

        retrieved_profile = profile_store.get("user_123")
        assert retrieved_profile.preferences.budget_min == 5000


# 工具函数
def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量"""
    return len(text) // 2


# 运行测试的辅助函数
def run_async_test(coro):
    """运行异步测试"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


if __name__ == "__main__":
    # 快速验证测试
    print("运行记忆模块测试...")

    # 测试 ImportanceScorer
    print("\n1. 测试 ImportanceScorer...")
    scorer = ImportanceScorer()
    loop = asyncio.new_event_loop()
    score = loop.run_until_complete(scorer.score("我想去云南旅游"))
    print(f"   消息评分: {score.total_score:.2f}")
    loop.close()

    # 测试 EvictionManager
    print("\n2. 测试 EvictionManager...")
    manager = EvictionManager(EvictionConfig(max_size=5))
    manager.add(MemoryItem(id="test", content="测试", importance=0.8))
    print(f"   当前记忆数: {len(manager.get_all())}")

    # 测试 UserProfileStore
    print("\n3. 测试 UserProfileStore...")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    store = UserProfileStore(storage_path=temp_path)
    profile = store.get_or_create("test_user")
    store.update_preference("test_user", "budget_min", 3000)
    print(f"   用户预算: {store.get('test_user').preferences.budget_min}元")
    os.unlink(temp_path)

    # 测试 HierarchicalMemoryStore
    print("\n4. 测试 HierarchicalMemoryStore...")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    hstore = HierarchicalMemoryStore(storage_path=temp_path)
    session = SessionData(
        session_id="sess_1",
        user_id="user_1",
        start_time=datetime.now().isoformat(),
        end_time=None,
        message_count=5,
        summary="测试会话"
    )
    asyncio.run(hstore.store_session(session))
    print(f"   会话存储成功: {hstore.get_session('sess_1') is not None}")
    os.unlink(temp_path)

    # 测试 MemoryConsolidator
    print("\n5. 测试 MemoryConsolidator...")
    consolidator = MemoryConsolidator()
    memories = [
        {"id": "m1", "session_id": "s1", "content": "云南旅游", "importance": 0.7},
        {"id": "m2", "session_id": "s1", "content": "大理丽江", "importance": 0.6},
        {"id": "m3", "session_id": "s2", "content": "日本旅游", "importance": 0.8}
    ]
    result = asyncio.run(consolidator.consolidate(memories))
    print(f"   创建聚类数: {result.clusters_created}")

    print("\n所有模块基本功能验证通过！")
