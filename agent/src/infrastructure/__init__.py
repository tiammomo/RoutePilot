# Infrastructure Layer - 基础设施层
#
# 提供 HTTP 客户端、Snowflake ID、Redis 消息队列、Milvus 向量数据库、Nacos 配置中心等基础设施

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

from .redis_queue import (
    RedisQueue,
    RedisConfig,
    QueueMessage,
    QueueType,
    DistributedLock,
    create_redis_queue,
    create_distributed_lock
)

from .milvus_vector import (
    MilvusVectorStore,
    MilvusConfig,
    CollectionSchema,
    SearchResult,
    DistanceMetric,
    IndexType,
    VectorProcessor,
    create_milvus_store
)

from .nacos_client import (
    NacosClient,
    NacosConfig,
    ServiceInfo,
    ConfigInfo,
    ConfigListener,
    ConfigManager,
    create_nacos_client
)

from .config_hot_reload import (
    ConfigHotReload,
    ConfigReloadPolicy,
    ConfigSource,
    ConfigItem,
    get_config_reloader,
    create_config_reloader,
    reset_config_reloader
)

from .infra_config import (
    InfraConfig,
    RedisConfig,
    MilvusConfig,
    NacosConfig as NacosConfigType,
    MinioConfig,
    MySQLConfig,
    AppConfig,
    ConfigLoader,
    get_config,
    print_connection_info,
    create_redis_queue_config,
    create_milvus_store_config,
    create_nacos_client_config
)

# 新增: LLM 响应缓存模块
from .llm_cache import (
    LLMResponseCache,
    LLMCacheMiddleware,
    CacheConfig,
    CacheStats,
    create_llm_cache,
    check_cache_health
)

# 新增: API 限流模块
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

# 新增: 用户偏好向量存储模块
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

# 新增: 实时消息推送模块
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

# 新增: 基础设施监控模块
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

# 新增: 对话历史向量化存储模块
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

# 新增: 配置版本管理模块
from .config_version_manager import (
    ConfigVersionManager,
    NacosConfigVersionManager,
    ConfigVersion,
    ConfigDiff,
    ConfigStatus,
    VersionManagerConfig,
    create_version_manager,
    check_version_manager_health
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
    # Redis Queue
    'RedisQueue',
    'RedisConfig',
    'QueueMessage',
    'QueueType',
    'DistributedLock',
    'create_redis_queue',
    'create_distributed_lock',
    # Milvus Vector
    'MilvusVectorStore',
    'MilvusConfig',
    'CollectionSchema',
    'SearchResult',
    'DistanceMetric',
    'IndexType',
    'VectorProcessor',
    'create_milvus_store',
    # Nacos Config
    'NacosClient',
    'NacosConfig',
    'ServiceInfo',
    'ConfigInfo',
    'ConfigListener',
    'ConfigManager',
    'create_nacos_client',
    # Config Hot Reload
    'ConfigHotReload',
    'ConfigReloadPolicy',
    'ConfigSource',
    'ConfigItem',
    'get_config_reloader',
    'create_config_reloader',
    'reset_config_reloader',
    # Config Loader
    'InfraConfig',
    'RedisConfig',
    'MilvusConfig',
    'MinioConfig',
    'MySQLConfig',
    'AppConfig',
    'ConfigLoader',
    'get_config',
    'print_connection_info',
    'create_redis_queue_config',
    'create_milvus_store_config',
    'create_nacos_client_config',
    # LLM Response Cache (NEW)
    'LLMResponseCache',
    'LLMCacheMiddleware',
    'CacheConfig',
    'CacheStats',
    'create_llm_cache',
    'check_cache_health',
    # Rate Limiter (NEW)
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
    # User Preference Store (NEW)
    'UserPreferenceStore',
    'UserPreference',
    'PreferenceEmbeddingGenerator',
    'VectorStoreConfig',
    'PreferenceCategory',
    'RecommendationResult',
    'create_user_preference_store',
    'check_preference_store_health',
    # Real-time Pusher (NEW)
    'RealtimePusher',
    'WebSocketManager',
    'EventType',
    'PushPriority',
    'PushMessage',
    'RealtimeConfig',
    'create_realtime_pusher',
    'check_realtime_health',
    # Infrastructure Monitor (NEW)
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
    # Conversation Store (NEW)
    'ConversationVectorStore',
    'Conversation',
    'Message',
    'ConversationStatus',
    'ConversationSearchResult',
    'ConversationStoreConfig',
    'ConversationEmbeddingGenerator',
    'create_conversation_store',
    'check_conversation_store_health',
    # Config Version Manager (NEW)
    'ConfigVersionManager',
    'NacosConfigVersionManager',
    'ConfigVersion',
    'ConfigDiff',
    'ConfigStatus',
    'VersionManagerConfig',
    'create_version_manager',
    'check_version_manager_health'
]
