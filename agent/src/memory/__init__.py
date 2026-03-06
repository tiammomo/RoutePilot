# Memory Module - 记忆管理模块
#
# 提供完整的记忆管理解决方案，包括：
# - 短期记忆（对话历史）
# - 长期记忆（会话存档）
# - 重要性评分
# - 智能淘汰
# - 对话摘要
# - 用户画像
# - 分层存储
# - 记忆整合
# - 统一协调器
# - 注意力窗口
# - 反思机制
# - 记忆回流
# - 上下文检索
# 注意: 已移除 Redis 依赖，使用纯 Python 内存存储

# 核心管理器
from .manager import MemoryManager, Message, UserPreference

# 内存记忆存储（纯 Python）
from .factory import create_memory_manager, get_memory_stats

# 短期记忆优化
from .importance_scorer import ImportanceScorer, ImportanceScore, PriorityCalculator
from .eviction_manager import EvictionManager, EvictionStrategy, EvictionConfig, MemoryItem

# 对话摘要
from .summarizer import ConversationSummarizer, ConversationSummary, CompressionLevel

# 长期记忆优化
from .user_profile import UserProfileStore, UserProfile, UserPreference as EnhancedUserPreference, TravelHistory
from .hierarchical_store import HierarchicalMemoryStore, MemoryTier, SessionData, RetrievedMemory

# 记忆整合
from .consolidation import MemoryConsolidator, MemoryCluster, MemoryType, ConsolidationResult

# 统一协调器
from .orchestrator import MemoryOrchestrator, OrchestratorConfig, create_memory_orchestrator

# 注意力窗口
from .attention import AttentionWindow

# 反思机制
from .reflection import ReflectionMechanism, ReflectionResult

# 智能淘汰策略
from .eviction_policy import SmartEvictionPolicy, AdaptiveEvictionPolicy, EvictionWeights

# 对话向量化
from .vectorizer import ConversationVectorizer

# 记忆回流
from .recirculation import MemoryRecirculation, RecirculationRule, MemoryContent

# 上下文感知检索
from .retrieval import ContextAwareRetrieval

# 上下文追踪
from .context_tracker import ContextTracker, TrackedEntity, EntityReference, context_tracker

# LangChain Memory
from .chat_history import (
    SessionChatHistory,
    ChatHistoryManager,
    FileChatHistoryManager,
    get_chat_history_manager,
    get_file_chat_history_manager
)

__all__ = [
    # 核心
    'MemoryManager',
    'Message',
    'UserPreference',

    # 内存记忆存储（纯 Python）
    'create_memory_manager',
    'get_memory_stats',

    # 短期记忆
    'ImportanceScorer',
    'ImportanceScore',
    'PriorityCalculator',
    'EvictionManager',
    'EvictionStrategy',
    'EvictionConfig',
    'MemoryItem',

    # 摘要
    'ConversationSummarizer',
    'ConversationSummary',
    'CompressionLevel',

    # 长期记忆
    'UserProfileStore',
    'UserProfile',
    'TravelHistory',
    'HierarchicalMemoryStore',
    'MemoryTier',
    'SessionData',
    'RetrievedMemory',

    # 整合
    'MemoryConsolidator',
    'MemoryCluster',
    'MemoryType',
    'ConsolidationResult',

    # 统一协调器
    'MemoryOrchestrator',
    'OrchestratorConfig',
    'create_memory_orchestrator',

    # 注意力窗口
    'AttentionWindow',

    # 反思机制
    'ReflectionMechanism',
    'ReflectionResult',

    # 智能淘汰策略
    'SmartEvictionPolicy',
    'AdaptiveEvictionPolicy',
    'EvictionWeights',

    # 对话向量化
    'ConversationVectorizer',

    # 记忆回流
    'MemoryRecirculation',
    'RecirculationRule',
    'MemoryContent',

    # 上下文感知检索
    'ContextAwareRetrieval',

    # 上下文追踪
    'ContextTracker',
    'TrackedEntity',
    'EntityReference',
    'context_tracker',

    # LangChain Memory
    'SessionChatHistory',
    'ChatHistoryManager',
    'FileChatHistoryManager',
    'get_chat_history_manager',
    'get_file_chat_history_manager'
]
