# Infrastructure Layer - 基础设施层
#
# 提供 HTTP 客户端、Snowflake ID、SSE 流式输出等基础设施
# 注意: 已移除 Redis、Milvus、Nacos 等外部组件依赖

from .http_client import (
    SyncHTTPClient,
    AsyncHTTPClient,
    APIClient,
    HTTPRequest,
    HTTPResponse,
    HTTPMethod,
    HTTPContentType,
    HTTPError,
    create_http_client
)

from .snowflake import (
    SnowflakeGenerator,
    SnowflakeConfig,
    SnowflakeID,
    AsyncSnowflakeGenerator,
    generate_id,
    parse_id,
    get_generator,
    get_async_generator
)

from .prompt_manager import (
    PromptManager,
    PromptTemplate,
    PromptChain,
    PromptType,
    DynamicPrompt,
    get_prompt_manager,
    create_prompt_manager
)

from .streaming import (
    SSEStreamer,
    StreamManager,
    StreamEvent,
    EventType,
    StreamingConfig,
    ChunkProcessor,
    create_sse_streamer,
    create_stream_manager,
    create_chunk_processor
)

# 简化版: 内存缓存模块（不依赖 Redis）
from .llm_cache import (
    LLMResponseCache,
    LLMCacheMiddleware,
    CacheConfig,
    CacheStats,
    create_llm_cache,
    check_cache_health
)

# 简化版: API 限流模块（不依赖 Redis）
from .rate_limiter import (
    RateLimiter,
    BaseRateLimiter,
    FixedWindowLimiter,
    SlidingWindowLimiter,
    TokenBucketLimiter,
    RateLimitStrategy,
    RateLimitConfig,
    RateLimitResult,
    RateLimitMiddleware,
    create_rate_limiter,
    check_rate_limit_health
)

# 简化版: 用户偏好存储（不依赖 Milvus）
from .user_preference_store import (
    UserPreferenceStore,
    UserPreference,
    PreferenceEmbeddingGenerator,
    VectorStoreConfig,
    PreferenceCategory,
    RecommendationResult,
    create_user_preference_store,
    check_preference_store_health
)

# 简化版: 实时消息推送（不依赖 Redis）
from .realtime_pusher import (
    RealtimePusher,
    WebSocketManager,
    EventType,
    PushPriority,
    PushMessage,
    RealtimeConfig,
    create_realtime_pusher,
    check_realtime_health
)

# 简化版: 基础设施监控
from .monitor import (
    InfrastructureMonitor,
    HealthChecker,
    MetricsCollector,
    ServiceHealth,
    ServiceMetrics,
    ServiceType,
    ComponentStatus,
    AlertConfig,
    create_monitor,
    check_all_services
)

# 简化版: 对话历史存储（不依赖 Milvus）
from .conversation_store import (
    ConversationVectorStore,
    Conversation,
    Message,
    ConversationStatus,
    ConversationSearchResult,
    ConversationStoreConfig,
    ConversationEmbeddingGenerator,
    create_conversation_store,
    check_conversation_store_health
)

# 简化版: 基础配置管理（不依赖 Nacos）
from .infra_config import (
    InfraConfig,
    AppConfig,
    ConfigLoader,
    get_config,
    print_connection_info
)

__all__ = [
    # HTTP Client
    'SyncHTTPClient',
    'AsyncHTTPClient',
    'APIClient',
    'HTTPRequest',
    'HTTPResponse',
    'HTTPMethod',
    'HTTPContentType',
    'HTTPError',
    'create_http_client',
    # Snowflake ID
    'SnowflakeGenerator',
    'SnowflakeConfig',
    'SnowflakeID',
    'AsyncSnowflakeGenerator',
    'generate_id',
    'parse_id',
    'get_generator',
    'get_async_generator',
    # Prompt Manager
    'PromptManager',
    'PromptTemplate',
    'PromptChain',
    'PromptType',
    'DynamicPrompt',
    'get_prompt_manager',
    'create_prompt_manager',
    # Streaming
    'SSEStreamer',
    'StreamManager',
    'StreamEvent',
    'EventType',
    'StreamingConfig',
    'ChunkProcessor',
    'create_sse_streamer',
    'create_stream_manager',
    'create_chunk_processor',
    # LLM Response Cache (简化版 - 内存)
    'LLMResponseCache',
    'LLMCacheMiddleware',
    'CacheConfig',
    'CacheStats',
    'create_llm_cache',
    'check_cache_health',
    # Rate Limiter (简化版 - 内存)
    'RateLimiter',
    'BaseRateLimiter',
    'FixedWindowLimiter',
    'SlidingWindowLimiter',
    'TokenBucketLimiter',
    'RateLimitStrategy',
    'RateLimitConfig',
    'RateLimitResult',
    'RateLimitMiddleware',
    'create_rate_limiter',
    'check_rate_limit_health',
    # User Preference Store (简化版 - 内存)
    'UserPreferenceStore',
    'UserPreference',
    'PreferenceEmbeddingGenerator',
    'VectorStoreConfig',
    'PreferenceCategory',
    'RecommendationResult',
    'create_user_preference_store',
    'check_preference_store_health',
    # Real-time Pusher (简化版 - 内存)
    'RealtimePusher',
    'WebSocketManager',
    'EventType',
    'PushPriority',
    'PushMessage',
    'RealtimeConfig',
    'create_realtime_pusher',
    'check_realtime_health',
    # Infrastructure Monitor (简化版)
    'InfrastructureMonitor',
    'HealthChecker',
    'MetricsCollector',
    'ServiceHealth',
    'ServiceMetrics',
    'ServiceType',
    'ComponentStatus',
    'AlertConfig',
    'create_monitor',
    'check_all_services',
    # Conversation Store (简化版 - 内存)
    'ConversationVectorStore',
    'Conversation',
    'Message',
    'ConversationStatus',
    'ConversationSearchResult',
    'ConversationStoreConfig',
    'ConversationEmbeddingGenerator',
    'create_conversation_store',
    'check_conversation_store_health',
    # Config Loader (简化版 - 本地)
    'InfraConfig',
    'AppConfig',
    'ConfigLoader',
    'get_config',
    'print_connection_info'
]
