# =============================================================================
# Memory Orchestrator - 统一记忆协调器 (v2.2)
# =============================================================================
#
# 协调所有记忆子系统，提供统一的记忆管理接口。
# 整合了：重要性评分、智能淘汰、对话摘要、用户画像、分层存储、记忆整合
# 新增 (v2.2): 注意力窗口、反思机制、记忆回流、上下文检索
#
# =============================================================================

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import time
import logging
import asyncio

from .manager import MemoryManager, Message
from .importance_scorer import ImportanceScorer, ImportanceScore
from .eviction_manager import EvictionManager, EvictionStrategy, EvictionConfig, MemoryItem
from .summarizer import ConversationSummarizer
from .user_profile import UserProfileStore, UserProfile, TravelHistory
from .hierarchical_store import HierarchicalMemoryStore, MemoryTier, SessionData, RetrievedMemory
from .consolidation import MemoryConsolidator, ConsolidationResult

# v2.2 新增组件
from .attention import AttentionWindow
from .reflection import ReflectionMechanism, ReflectionResult
from .eviction_policy import SmartEvictionPolicy, AdaptiveEvictionPolicy
from .vectorizer import ConversationVectorizer
from .recirculation import MemoryRecirculation, RecirculationRule
from .retrieval import ContextAwareRetrieval

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """记忆协调器配置 (v2.2)"""

    # 基础配置
    max_working_memory: int = 50
    max_long_term_memory: int = 100

    # 重要性评分
    importance_enable: bool = True
    importance_threshold: float = 0.5

    # 智能淘汰
    eviction_enable: bool = True
    eviction_strategy: str = "hybrid"  # fifo/lfu/lru/priority/hybrid
    eviction_max_size: int = 30

    # 对话摘要
    summarization_enable: bool = True
    summarization_max_tokens: int = 2000
    compression_level: str = "moderate"  # light/moderate/aggressive

    # 用户画像
    user_profile_enable: bool = True

    # 分层存储
    hierarchical_enable: bool = True
    hot_size: int = 10
    warm_size: int = 50

    # 记忆整合
    consolidation_enable: bool = True
    consolidation_interval_hours: int = 24

    # ======== v2.2 新增配置 ========

    # 注意力窗口
    attention_window_enable: bool = True
    attention_window_size: int = 10
    attention_recency_weight: float = 0.3
    attention_importance_weight: float = 0.4
    attention_relevance_weight: float = 0.3

    # 反思机制
    reflection_enable: bool = True
    reflection_trigger_interval: int = 10
    reflection_min_messages: int = 5

    # 智能淘汰策略 (高级)
    smart_eviction_enable: bool = True
    smart_eviction_adaptive: bool = False

    # 对话向量化
    vectorizer_enable: bool = True
    vectorizer_embedding_dim: int = 1536
    vectorizer_use_tfidf_fallback: bool = True

    # 记忆回流
    recirculation_enable: bool = True
    recirculation_threshold: float = 0.7
    recirculation_frequency_trigger: int = 3

    # 上下文检索
    retrieval_enable: bool = True
    retrieval_top_k: int = 3


class MemoryOrchestrator:
    """
    统一记忆协调器

    作为所有记忆操作的单一入口，协调各子系统工作：

    1. add_message() - 添加消息
       - 写入 MemoryManager
       - 计算重要性
       - 触发淘汰
       - 更新用户画像

    2. get_context_for_llm() - 获取上下文
       - 获取对话历史
       - 压缩上下文
       - 检索历史对话
       - 获取用户画像

    3. end_session() - 结束会话
       - 生成摘要
       - 存入分层存储
       - 合并用户画像
       - 触发整合
       - 归档

    注意: 已移除 Redis 依赖，使用纯 Python 内存存储

    使用示例:
        orchestrator = MemoryOrchestrator(config)
        orchestrator.add_message("session_1", "user_1", "user", "我喜欢去海边")
        context = orchestrator.get_context_for_llm("session_1", "user_1")
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        llm_client: Optional[Any] = None
    ):
        """
        初始化记忆协调器

        Args:
            config: 协调器配置，如为 None 则使用默认配置
            llm_client: LLM 客户端，用于摘要生成等

        注意: 已移除 Redis 依赖
        """
        self.config = config or OrchestratorConfig()
        self.llm_client = llm_client

        # 1. 基础记忆管理器
        self.memory_manager = MemoryManager(
            max_working_memory=self.config.max_working_memory,
            max_long_term_memory=self.config.max_long_term_memory
        )

        # 3. 重要性评分器
        self.importance_scorer: Optional[ImportanceScorer] = None
        if self.config.importance_enable:
            self.importance_scorer = ImportanceScorer(threshold=self.config.importance_threshold)

        # 4. 智能淘汰管理器
        self.eviction_manager: Optional[EvictionManager] = None
        if self.config.eviction_enable:
            eviction_config = EvictionConfig(
                max_size=self.config.eviction_max_size,
                strategy=EvictionStrategy[self.config.eviction_strategy.upper()]
            )
            self.eviction_manager = EvictionManager(config=eviction_config)

        # 5. 对话摘要器
        self.summarizer: Optional[ConversationSummarizer] = None
        if self.config.summarization_enable:
            self.summarizer = ConversationSummarizer(
                max_tokens=self.config.summarization_max_tokens,
                llm_client=llm_client
            )

        # 6. 用户画像存储
        self.user_profile_store: Optional[UserProfileStore] = None
        if self.config.user_profile_enable:
            self.user_profile_store = UserProfileStore()

        # 7. 分层长期存储
        self.hierarchical_store: Optional[HierarchicalMemoryStore] = None
        if self.config.hierarchical_enable:
            self.hierarchical_store = HierarchicalMemoryStore(
                hot_cache_size=self.config.hot_size * 10,
                warm_cache_size=self.config.warm_size * 10
            )

        # 8. 记忆整合器
        self.consolidator: Optional[MemoryConsolidator] = None
        if self.config.consolidation_enable:
            self.consolidator = MemoryConsolidator()

        # ======== v2.2 新增组件 ========

        # 9. 注意力窗口
        self.attention_window: Optional[AttentionWindow] = None
        if self.config.attention_window_enable:
            self.attention_window = AttentionWindow(
                window_size=self.config.attention_window_size,
                recency_weight=self.config.attention_recency_weight,
                importance_weight=self.config.attention_importance_weight,
                relevance_weight=self.config.attention_relevance_weight
            )

        # 10. 反思机制
        self.reflection: Optional[ReflectionMechanism] = None
        if self.config.reflection_enable:
            self.reflection = ReflectionMechanism(
                llm_client=llm_client,
                trigger_interval=self.config.reflection_trigger_interval,
                min_messages=self.config.reflection_min_messages
            )

        # 11. 智能淘汰策略 (高级)
        self.smart_eviction_policy: Optional[SmartEvictionPolicy] = None
        if self.config.smart_eviction_enable:
            if self.config.smart_eviction_adaptive:
                self.smart_eviction_policy = AdaptiveEvictionPolicy(max_size=self.config.eviction_max_size)
            else:
                self.smart_eviction_policy = SmartEvictionPolicy(max_size=self.config.eviction_max_size)

        # 12. 对话向量化器
        self.vectorizer: Optional[ConversationVectorizer] = None
        if self.config.vectorizer_enable:
            self.vectorizer = ConversationVectorizer(
                llm_client=llm_client,
                embedding_dim=self.config.vectorizer_embedding_dim,
                use_tfidf_fallback=self.config.vectorizer_use_tfidf_fallback
            )

        # 13. 记忆回流机制
        self.recirculation: Optional[MemoryRecirculation] = None
        if self.config.recirculation_enable:
            rule = RecirculationRule(
                threshold_trigger=self.config.recirculation_threshold,
                frequency_trigger=self.config.recirculation_frequency_trigger
            )
            self.recirculation = MemoryRecirculation(
                long_term_store=self.hierarchical_store,
                profile_store=self.user_profile_store,
                rule=rule
            )

        # 14. 上下文感知检索
        self.retrieval: Optional[ContextAwareRetrieval] = None
        if self.config.retrieval_enable:
            self.retrieval = ContextAwareRetrieval(
                hierarchical_store=self.hierarchical_store,
                profile_store=self.user_profile_store,
                vectorizer=self.vectorizer,
                default_top_k=self.config.retrieval_top_k
            )

        # 会话上下文映射
        self._session_contexts: Dict[str, Dict[str, Any]] = {}

        logger.info("MemoryOrchestrator initialized with all subsystems (v2.2)")

    def _get_or_create_session_context(self, session_id: str, user_id: str) -> Dict[str, Any]:
        """获取或创建会话上下文"""
        if session_id not in self._session_contexts:
            self._session_contexts[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "start_time": datetime.now().isoformat(),
                "message_count": 0,
                "importance_scores": []
            }
        return self._session_contexts[session_id]

    def add_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str
    ) -> Dict[str, Any]:
        """
        添加消息到记忆系统

        流程:
        1. 写入 MemoryManager.conversation_history
        2. 调用 ImportanceScorer 计算重要性
        3. 调用 EvictionManager 检查是否淘汰
        4. 更新 UserProfileStore 用户偏好

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            role: 角色 (user/assistant)
            content: 消息内容

        Returns:
            添加结果，包含重要性评分等信息
        """
        context = self._get_or_create_session_context(session_id, user_id)

        # 1. 写入基础记忆
        self.memory_manager.add_message(role, content)

        # 记录会话消息数
        context["message_count"] += 1

        result = {
            "success": True,
            "session_id": session_id,
            "role": role,
            "content_length": len(content),
            "total_messages": context["message_count"]
        }

        # 2. 计算重要性
        importance_score: Optional[ImportanceScore] = None
        if self.importance_scorer and role == "user":
            importance_score = self.importance_scorer.score(content, context)
            context["importance_scores"].append(importance_score.total_score)
            result["importance_score"] = importance_score.total_score

        # 3. 智能淘汰检查
        if self.eviction_manager and importance_score:
            memory_item = MemoryItem(
                id=f"{session_id}:{context['message_count']}",
                content=content,
                importance=importance_score.total_score if importance_score else 0.5,
                timestamp=datetime.now().isoformat(),
                access_count=1,
                metadata={"role": role}
            )
            self.eviction_manager.add(memory_item)

        # 4. 更新用户画像
        if self.user_profile_store and role == "user":
            # 从消息中提取偏好
            preference_data = self._extract_preference_from_message(content)
            if preference_data:
                # 从 MemoryManager 获取当前偏好
                current_pref = self.memory_manager.get_user_preference()
                if current_pref:
                    preference_data.update(current_pref)
                self.user_profile_store.merge_preferences(user_id, preference_data)

        return result

    def _extract_preference_from_message(self, content: str) -> Dict[str, Any]:
        """从消息中提取偏好"""
        preferences = {}

        # 预算相关
        budget_keywords = ["预算", "花多少钱", "价格", "费用"]
        for kw in budget_keywords:
            if kw in content:
                # 简单检测，实际可用正则
                if "2000" in content:
                    preferences["budget_range"] = "2000-4000"
                elif "3000" in content:
                    preferences["budget_range"] = "3000-5000"
                elif "5000" in content:
                    preferences["budget_range"] = "5000-8000"
                break

        # 天数相关
        days_keywords = ["天", "几天", "多少天"]
        for kw in days_keywords:
            if kw in content:
                import re
                match = re.search(r"(\d+)\s*天", content)
                if match:
                    preferences["travel_days"] = int(match.group(1))
                break

        # 目的地相关
        city_keywords = ["去", "到", "旅游"]
        for kw in city_keywords:
            if kw in content:
                import re
                match = re.search(r"去(.+?)旅游|到(.+?)玩", content)
                if match:
                    city = match.group(1) or match.group(2)
                    if city:
                        preferences["preferred_cities"] = [city.strip()]
                break

        return preferences

    async def get_context_for_llm(
        self,
        session_id: str,
        user_id: str,
        max_tokens: int = 2000
    ) -> List[Dict[str, str]]:
        """
        获取 LLM 上下文字符串

        流程:
        1. 获取当前会话历史
        2. 调用 ConversationSummarizer 压缩
        3. 检索相关历史对话 (HierarchicalMemoryStore)
        4. 获取用户画像摘要 (UserProfileStore)
        5. 拼接返回

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            max_tokens: 最大 token 数 (用于压缩)

        Returns:
            消息列表，可直接发送给 LLM
        """
        messages = []

        # 1. 获取当前会话历史
        history = self.memory_manager.get_conversation_history()

        # 2. 压缩上下文
        if self.summarizer and len(history) > 10:
            # 需要更多压缩
            compressed = self.summarizer.compress_for_context(
                history,
                max_messages=max(5, len(history) // 3)  # 保留至少5条或1/3
            )
            history = compressed if compressed else history
        elif len(history) > 20:
            # 简单截断
            history = history[-20:]

        messages.extend(history)

        # 3. 检索相关历史对话
        if self.hierarchical_store and history:
            last_user_msg = None
            for msg in reversed(history):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")
                    break

            if last_user_msg:
                try:
                    historical = await self.hierarchical_store.retrieve_context(
                        user_id=user_id,
                        query=last_user_msg,
                        top_k=2
                    )
                    # 添加历史上下文标记
                    if historical:
                        history_context = [
                            {"role": "system", "content": f"[历史对话 {h.tier.value}]"}
                            for h in historical[:1]  # 最多1条历史
                        ]
                        messages = history_context + messages
                except Exception as e:
                    logger.warning(f"Historical retrieval failed: {e}")

        # 4. 获取用户画像摘要
        if self.user_profile_store:
            try:
                profile_context = self.user_profile_store.get_context_for_llm(user_id)
                if profile_context:
                    messages.insert(0, {
                        "role": "system",
                        "content": f"[用户画像] {profile_context}"
                    })
            except Exception as e:
                logger.warning(f"User profile retrieval failed: {e}")

        return messages

    def get_user_preference(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        获取用户偏好（合并当前会话 + 历史画像）

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            合并后的用户偏好
        """
        # 1. 当前会话偏好
        session_preference = self.memory_manager.get_user_preference()

        # 2. 历史画像偏好
        profile_preference = {}
        if self.user_profile_store:
            try:
                profile = self.user_profile_store.get(user_id)
                if profile:
                    profile_preference = profile.preferences.to_dict() if hasattr(profile.preferences, 'to_dict') else {}
            except Exception as e:
                logger.warning(f"Get profile failed: {e}")

        # 3. 合并（当前会话优先）
        merged = {**profile_preference, **session_preference}
        return merged

    def end_session(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        结束会话，触发归档流程

        流程:
        1. 生成会话摘要 (ConversationSummarizer)
        2. 存入分层存储 (HierarchicalMemoryStore)
        3. 合并用户偏好 (UserProfileStore)
        4. 触发记忆整合 (MemoryConsolidator)
        5. 归档到 MemoryManager.long_term_memory

        Args:
            session_id: 会话 ID
            user_id: 用户 ID

        Returns:
            归档结果
        """
        result = {
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }

        context = self._session_contexts.get(session_id, {})
        history = self.memory_manager.get_conversation_history()

        if not history:
            result["skipped"] = True
            return result

        # 1. 生成会话摘要
        summary = ""
        if self.summarizer:
            try:
                summary_obj = self.summarizer.summarize(history)
                summary = summary_obj.summary
                result["summary"] = summary
                result["message_count"] = summary_obj.message_count_before
                result["tokens_saved"] = summary_obj.tokens_saved
            except Exception as e:
                logger.warning(f"Summarization failed: {e}")
                summary = f"{len(history)} 条对话记录"
        else:
            summary = f"{len(history)} 条对话记录"

        # 2. 存入分层存储
        if self.hierarchical_store:
            try:
                session_data = SessionData(
                    session_id=session_id,
                    user_id=user_id,
                    start_time=context.get("start_time", datetime.now().isoformat()),
                    end_time=datetime.now().isoformat(),
                    message_count=len(history),
                    summary=summary,
                    topics=[],  # 可从 summarizer 获取
                    user_preferences=self.memory_manager.get_user_preference(),
                    full_history=history,
                    embedding=None,  # 可选：生成 embedding
                    metadata={}
                )
                self.hierarchical_store.store_session(session_data)
                result["hierarchical_stored"] = True
            except Exception as e:
                logger.warning(f"Hierarchical store failed: {e}")

        # 3. 合并用户画像
        if self.user_profile_store:
            try:
                prefs = self.memory_manager.get_user_preference()
                if prefs:
                    self.user_profile_store.merge_preferences(user_id, prefs)

                # 记录旅行历史
                travel_history = TravelHistory(
                    session_id=session_id,
                    destination="",  # 可从对话提取
                    duration_days=prefs.get("travel_days"),
                    budget=prefs.get("budget_range"),
                    rating=None,
                    notes=summary,
                    created_at=datetime.now().isoformat()
                )
                self.user_profile_store.add_travel_history(user_id, travel_history)
                result["profile_updated"] = True
            except Exception as e:
                logger.warning(f"Profile update failed: {e}")

        # 4. 触发记忆整合
        if self.consolidator and self.hierarchical_store:
            try:
                memories = [h.to_dict() if hasattr(h, 'to_dict') else h for h in history]
                consolidation_result = self.consolidator.consolidate(memories)
                result["consolidated"] = True
                result["clusters_created"] = consolidation_result.clusters_created
            except Exception as e:
                logger.warning(f"Consolidation failed: {e}")

        # 5. 基础归档
        try:
            archived = self.memory_manager.archive_current_session()
            result["archived"] = True
            result["archive_id"] = archived.get("session_id") if archived else None
        except Exception as e:
            logger.warning(f"Archive failed: {e}")

        # 清理会话上下文
        if session_id in self._session_contexts:
            del self._session_contexts[session_id]

        # 清除当前会话记忆
        self.memory_manager.clear_conversation(archive=False)

        return result

    def clear_session(self, session_id: str, archive: bool = True) -> None:
        """
        清除会话记忆

        Args:
            session_id: 会话 ID
            archive: 是否归档
        """
        if archive:
            # 尝试归档
            context = self._session_contexts.get(session_id, {})
            user_id = context.get("user_id", "unknown")
            try:
                self.end_session(session_id, user_id)
            except Exception:
                pass
        else:
            self.memory_manager.clear_conversation(archive=False)

        if session_id in self._session_contexts:
            del self._session_contexts[session_id]

    async def search_historical_context(
        self,
        user_id: str,
        query: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        语义检索历史对话

        Args:
            user_id: 用户 ID
            query: 查询内容
            top_k: 返回数量

        Returns:
            历史对话列表
        """
        if not self.hierarchical_store:
            return []

        try:
            results = await self.hierarchical_store.retrieve_context(
                user_id=user_id,
                query=query,
                top_k=top_k
            )
            return [
                {
                    "session_id": r.data.session_id,
                    "summary": r.data.summary,
                    "tier": r.tier.value,
                    "relevance_score": r.relevance_score,
                    "match_reason": r.match_reason
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Historical search failed: {e}")
            return []

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆系统统计

        Returns:
            统计信息字典
        """
        stats = {
            "timestamp": datetime.now().isoformat(),
            "session_contexts": len(self._session_contexts),
            "memory_manager": {
                "conversation_count": len(self.memory_manager.conversation_history),
                "long_term_count": len(self.memory_manager.long_term_memory)
            }
        }

        if self.eviction_manager:
            stats["eviction"] = self.eviction_manager.get_stats()

        if self.user_profile_store:
            stats["user_profiles"] = {
                "total_users": len(self.user_profile_store._profiles)
            }

        if self.hierarchical_store:
            stats["hierarchical"] = self.hierarchical_store.get_stats()

        return stats

    # === 兼容接口 ===

    def get_conversation_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict]:
        """获取对话历史（兼容接口）"""
        return self.memory_manager.get_conversation_history(limit)

    def get_session_state(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取会话状态（兼容接口）"""
        return self.memory_manager.get_session_state(key, default)

    def update_session_state(self, session_id: str, key: str, value: Any) -> None:
        """更新会话状态（兼容接口）"""
        self.memory_manager.update_session_state(key, value)


def create_memory_orchestrator(
    config: Optional[Dict[str, Any]] = None,
    llm_client: Optional[Any] = None,
    **kwargs
) -> MemoryOrchestrator:
    """
    工厂函数：创建记忆协调器

    注意: 已移除 Redis 依赖

    Args:
        config: 配置字典
        llm_client: LLM 客户端
        **kwargs: 其他配置参数

    Returns:
        MemoryOrchestrator 实例
    """
    # 构建配置对象
    orchestrator_config = OrchestratorConfig()

    if config:
        for key, value in config.items():
            if hasattr(orchestrator_config, key):
                setattr(orchestrator_config, key, value)

    # 合并 kwargs
    for key, value in kwargs.items():
        if hasattr(orchestrator_config, key):
            setattr(orchestrator_config, key, value)

    return MemoryOrchestrator(
        config=orchestrator_config,
        llm_client=llm_client
    )
