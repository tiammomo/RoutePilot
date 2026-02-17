"""
记忆管理器工厂 (Memory Manager Factory) - v2.2

根据配置创建合适的记忆管理器：
- RedisMemoryManager: 使用 Redis 作为后端（生产环境）
- MemoryManager: 纯内存模式（开发/测试环境）
- 新增 v2.2: AttentionWindow, ReflectionMechanism, SmartEvictionPolicy 等组件工厂

使用示例:
    from memory.factory import (
        create_memory_manager,
        create_redis_memory_manager,
        create_attention_window,
        create_reflection_mechanism
    )

    # 自动检测配置创建
    memory = create_memory_manager()

    # 创建新组件
    attention = create_attention_window(config)
    reflection = create_reflection_mechanism(config, llm_client)
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# v2.2 新组件
from .attention import AttentionWindow
from .reflection import ReflectionMechanism
from .eviction_policy import SmartEvictionPolicy, AdaptiveEvictionPolicy
from .vectorizer import ConversationVectorizer
from .recirculation import MemoryRecirculation, RecirculationRule
from .retrieval import ContextAwareRetrieval


def create_memory_manager(
    config: Optional[Dict[str, Any]] = None,
    use_redis: Optional[bool] = None,
    **kwargs
) -> Any:
    """
    创建记忆管理器

    Args:
        config: 配置字典，包含 redis 配置
        use_redis: 是否使用 Redis，None 表示自动检测
        **kwargs: 其他参数传递给具体的记忆管理器

    Returns:
        MemoryManager 或 RedisMemoryManager 实例
    """
    # 检查是否应该使用 Redis
    if use_redis is None:
        # 从配置中检测
        if config and config.get("redis", {}).get("enabled", False):
            use_redis = True
        else:
            # 检查环境变量
            use_redis = __import__("os").get("USE_REDIS_MEMORY", "").lower() in ("true", "1", "yes")

    if use_redis:
        return create_redis_memory_manager(config, **kwargs)
    else:
        from .manager import MemoryManager
        return MemoryManager(
            max_working_memory=kwargs.get("max_working_memory", 10),
            max_long_term_memory=kwargs.get("max_long_term_memory", 50)
        )


def create_redis_memory_manager(
    config: Optional[Dict[str, Any]] = None,
    **kwargs
):
    """
    创建 Redis 记忆管理器

    Args:
        config: 配置字典，包含 redis 配置
        **kwargs: 其他参数

    Returns:
        RedisMemoryManager 实例
    """
    from .redis_memory import RedisMemoryManager

    # 从配置或 kwargs 中提取参数
    if config and "redis" in config:
        redis_config = config["redis"]
        host = redis_config.get("host", "localhost")
        port = redis_config.get("port", 6379)
        db = redis_config.get("db", 0)
        password = redis_config.get("password", "")
        key_prefix = redis_config.get("key_prefix", "travel:")
        ttl = redis_config.get("ttl", 86400)
        max_history = redis_config.get("max_history", 50)
    else:
        host = kwargs.get("host", "localhost")
        port = kwargs.get("port", 6379)
        db = kwargs.get("db", 0)
        password = kwargs.get("password", "")
        key_prefix = kwargs.get("key_prefix", "travel:")
        ttl = kwargs.get("ttl", 86400)
        max_history = kwargs.get("max_history", 50)

    # 检查是否降级
    fallback = kwargs.get("fallback", True)

    logger.info(f"[MemoryFactory] 创建 Redis 记忆管理器: {host}:{port}")

    return RedisMemoryManager(
        host=host,
        port=port,
        db=db,
        password=password if password else None,
        key_prefix=key_prefix,
        ttl=ttl,
        max_history=max_history,
        fallback=fallback
    )


def get_memory_stats(config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    获取记忆系统统计信息

    Args:
        config: 可选配置

    Returns:
        Dict: 统计信息
    """
    try:
        manager = create_memory_manager(config)
        return manager.get_stats()
    except Exception as e:
        return {"error": str(e)}


def create_memory_orchestrator(
    config: Optional[Dict[str, Any]] = None,
    use_redis: Optional[bool] = None,
    llm_client: Optional[Any] = None,
    **kwargs
) -> Any:
    """
    创建记忆协调器 (MemoryOrchestrator)

    统一协调所有记忆子系统：
    - MemoryManager: 基础对话历史
    - ImportanceScorer: 消息重要性评分
    - EvictionManager: 智能淘汰
    - ConversationSummarizer: 上下文压缩
    - UserProfileStore: 用户画像
    - HierarchicalMemoryStore: 分层长期存储
    - MemoryConsolidator: 记忆整合
    - RedisMemoryManager: 可选 Redis 后端

    Args:
        config: 配置字典
        use_redis: 是否使用 Redis 后端
        llm_client: LLM 客户端 (用于摘要生成)
        **kwargs: 其他参数

    Returns:
        MemoryOrchestrator 实例

    使用示例:
        from memory.factory import create_memory_orchestrator

        orchestrator = create_memory_orchestrator(
            config={"max_working_memory": 50},
            llm_client=llm_client
        )

        # 添加消息
        orchestrator.add_message("session_1", "user_1", "user", "我喜欢去海边")

        # 获取上下文
        context = orchestrator.get_context_for_llm("session_1", "user_1")

        # 结束会话
        orchestrator.end_session("session_1", "user_1")
    """
    from .orchestrator import MemoryOrchestrator, OrchestratorConfig

    # 构建配置
    orchestrator_config = OrchestratorConfig()

    if config:
        # 从 config 提取记忆配置
        memory_config = config.get("memory", config)

        # 基础配置
        if "max_working_memory" in memory_config:
            orchestrator_config.max_working_memory = memory_config["max_working_memory"]
        if "max_long_term_memory" in memory_config:
            orchestrator_config.max_long_term_memory = memory_config["max_long_term_memory"]

        # 重要性评分配置
        importance = memory_config.get("importance", {})
        if "enable" in importance:
            orchestrator_config.importance_enable = importance["enable"]
        if "threshold" in importance:
            orchestrator_config.importance_threshold = importance["threshold"]

        # 淘汰配置
        eviction = memory_config.get("eviction", {})
        if "enable" in eviction:
            orchestrator_config.eviction_enable = eviction["enable"]
        if "strategy" in eviction:
            orchestrator_config.eviction_strategy = eviction["strategy"]
        if "max_size" in eviction:
            orchestrator_config.eviction_max_size = eviction["max_size"]

        # 摘要配置
        summarization = memory_config.get("summarization", {})
        if "enable" in summarization:
            orchestrator_config.summarization_enable = summarization["enable"]
        if "max_tokens" in summarization:
            orchestrator_config.summarization_max_tokens = summarization["max_tokens"]
        if "compression_level" in summarization:
            orchestrator_config.compression_level = summarization["compression_level"]

        # 用户画像配置
        user_profile = memory_config.get("user_profile", {})
        if "enable" in user_profile:
            orchestrator_config.user_profile_enable = user_profile["enable"]

        # 分层存储配置
        hierarchical = memory_config.get("hierarchical", {})
        if "enable" in hierarchical:
            orchestrator_config.hierarchical_enable = hierarchical["enable"]
        if "hot_size" in hierarchical:
            orchestrator_config.hot_size = hierarchical["hot_size"]
        if "warm_size" in hierarchical:
            orchestrator_config.warm_size = hierarchical["warm_size"]

        # 整合配置
        consolidation = memory_config.get("consolidation", {})
        if "enable" in consolidation:
            orchestrator_config.consolidation_enable = consolidation["enable"]

        # Redis 配置
        redis_cfg = memory_config.get("redis", {})
        if "enable" in redis_cfg:
            orchestrator_config.redis_enable = redis_cfg["enable"]
        if "host" in redis_cfg:
            orchestrator_config.redis_host = redis_cfg["host"]
        if "port" in redis_cfg:
            orchestrator_config.redis_port = redis_cfg["port"]

    # 合并 kwargs
    for key, value in kwargs.items():
        if hasattr(orchestrator_config, key):
            setattr(orchestrator_config, key, value)

    # 自动检测 Redis
    if use_redis is None:
        if config and config.get("redis", {}).get("enabled"):
            use_redis = True
        else:
            use_redis = __import__("os").get("USE_REDIS_MEMORY", "").lower() in ("true", "1", "yes")

    logger.info("[MemoryFactory] 创建 MemoryOrchestrator")

    return MemoryOrchestrator(
        config=orchestrator_config,
        llm_client=llm_client,
        use_redis=use_redis,
        redis_config=config.get("redis") if config else None
    )


# =============================================================================
# v2.2 新组件工厂方法
# =============================================================================

def create_attention_window(
    config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> AttentionWindow:
    """
    创建注意力窗口

    Args:
        config: 配置字典
        **kwargs: 直接参数

    Returns:
        AttentionWindow 实例
    """
    window_size = kwargs.get("window_size", 10)
    recency_weight = kwargs.get("recency_weight", 0.3)
    importance_weight = kwargs.get("importance_weight", 0.4)
    relevance_weight = kwargs.get("relevance_weight", 0.3)

    if config and "attention" in config:
        att_config = config["attention"]
        window_size = att_config.get("window_size", window_size)
        recency_weight = att_config.get("recency_weight", recency_weight)
        importance_weight = att_config.get("importance_weight", importance_weight)
        relevance_weight = att_config.get("relevance_weight", relevance_weight)

    return AttentionWindow(
        window_size=window_size,
        recency_weight=recency_weight,
        importance_weight=importance_weight,
        relevance_weight=relevance_weight
    )


def create_reflection_mechanism(
    config: Optional[Dict[str, Any]] = None,
    llm_client: Optional[Any] = None,
    **kwargs
) -> ReflectionMechanism:
    """
    创建反思机制

    Args:
        config: 配置字典
        llm_client: LLM 客户端
        **kwargs: 直接参数

    Returns:
        ReflectionMechanism 实例
    """
    trigger_interval = kwargs.get("trigger_interval", 10)
    min_messages = kwargs.get("min_messages", 5)

    if config and "reflection" in config:
        ref_config = config["reflection"]
        trigger_interval = ref_config.get("trigger_interval", trigger_interval)
        min_messages = ref_config.get("min_messages", min_messages)

    return ReflectionMechanism(
        llm_client=llm_client,
        trigger_interval=trigger_interval,
        min_messages=min_messages
    )


def create_smart_eviction_policy(
    config: Optional[Dict[str, Any]] = None,
    adaptive: bool = False,
    **kwargs
) -> SmartEvictionPolicy:
    """
    创建智能淘汰策略

    Args:
        config: 配置字典
        adaptive: 是否使用自适应策略
        **kwargs: 直接参数

    Returns:
        SmartEvictionPolicy 或 AdaptiveEvictionPolicy 实例
    """
    max_size = kwargs.get("max_size", 50)

    if config and "eviction" in config:
        evic_config = config["eviction"]
        max_size = evic_config.get("max_size", max_size)
        adaptive = evic_config.get("adaptive", adaptive)

    if adaptive:
        return AdaptiveEvictionPolicy(max_size=max_size)
    else:
        return SmartEvictionPolicy(max_size=max_size)


def create_vectorizer(
    config: Optional[Dict[str, Any]] = None,
    llm_client: Optional[Any] = None,
    **kwargs
) -> ConversationVectorizer:
    """
    创建对话向量化器

    Args:
        config: 配置字典
        llm_client: LLM 客户端
        **kwargs: 直接参数

    Returns:
        ConversationVectorizer 实例
    """
    embedding_dim = kwargs.get("embedding_dim", 1536)
    use_tfidf_fallback = kwargs.get("use_tfidf_fallback", True)

    if config and "vectorizer" in config:
        vec_config = config["vectorizer"]
        embedding_dim = vec_config.get("embedding_dim", embedding_dim)
        use_tfidf_fallback = vec_config.get("use_tfidf_fallback", use_tfidf_fallback)

    return ConversationVectorizer(
        llm_client=llm_client,
        embedding_dim=embedding_dim,
        use_tfidf_fallback=use_tfidf_fallback
    )


def create_recirculation(
    config: Optional[Dict[str, Any]] = None,
    long_term_store: Optional[Any] = None,
    profile_store: Optional[Any] = None,
    **kwargs
) -> MemoryRecirculation:
    """
    创建记忆回流机制

    Args:
        config: 配置字典
        long_term_store: 长期记忆存储
        profile_store: 用户画像存储
        **kwargs: 直接参数

    Returns:
        MemoryRecirculation 实例
    """
    threshold_trigger = kwargs.get("threshold_trigger", 0.7)
    frequency_trigger = kwargs.get("frequency_trigger", 3)

    if config and "recirculation" in config:
        recirc_config = config["recirculation"]
        threshold_trigger = recirc_config.get("threshold_trigger", threshold_trigger)
        frequency_trigger = recirc_config.get("frequency_trigger", frequency_trigger)

    rule = RecirculationRule(
        threshold_trigger=threshold_trigger,
        frequency_trigger=frequency_trigger
    )

    return MemoryRecirculation(
        long_term_store=long_term_store,
        profile_store=profile_store,
        rule=rule
    )


def create_context_retrieval(
    config: Optional[Dict[str, Any]] = None,
    hierarchical_store: Optional[Any] = None,
    profile_store: Optional[Any] = None,
    vectorizer: Optional[Any] = None,
    **kwargs
) -> ContextAwareRetrieval:
    """
    创建上下文感知检索

    Args:
        config: 配置字典
        hierarchical_store: 分层记忆存储
        profile_store: 用户画像存储
        vectorizer: 向量化器
        **kwargs: 直接参数

    Returns:
        ContextAwareRetrieval 实例
    """
    default_top_k = kwargs.get("default_top_k", 3)

    if config and "retrieval" in config:
        retr_config = config["retrieval"]
        default_top_k = retr_config.get("top_k", default_top_k)

    return ContextAwareRetrieval(
        hierarchical_store=hierarchical_store,
        profile_store=profile_store,
        vectorizer=vectorizer,
        default_top_k=default_top_k
    )
