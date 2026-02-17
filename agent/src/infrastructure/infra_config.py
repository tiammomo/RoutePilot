"""
================================================================================
基础设施配置加载器 (Infrastructure Config Loader)

从 YAML 配置文件加载基础设施连接配置，支持环境变量覆盖。

功能特点:
- YAML 配置文件解析
- 环境变量覆盖
- 默认值支持
- 配置验证

使用示例:
```python
from infrastructure.infra_config import InfraConfig, get_config

config = get_config()

# Redis 配置
redis_config = config.redis
print(f"Redis: {redis_config.host}:{redis_config.port}")

# Milvus 配置
milvus_config = config.milvus
print(f"Milvus: {milvus_config.host}:{milvus_config.port}")

# Nacos 配置
nacos_config = config.nacos
print(f"Nacos: {nacos_config.server_addresses}")
```

================================================================================
"""

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)


# =============================================================================
# 配置数据类
# =============================================================================

@dataclass
class RedisPoolConfig:
    """Redis 连接池配置"""
    max_connections: int = 50
    timeout: float = 5.0


@dataclass
class RedisQueuesConfig:
    """Redis 队列配置"""
    task_queue: str = "travel:tasks"
    message_queue: str = "travel:messages"
    event_queue: str = "travel:events"


@dataclass
class RedisTTLConfig:
    """Redis TTL 配置"""
    session: int = 86400
    cache: int = 3600
    rate_limit: int = 60


@dataclass
class RedisConfig:
    """Redis 配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    pool: RedisPoolConfig = field(default_factory=RedisPoolConfig)
    queues: RedisQueuesConfig = field(default_factory=RedisQueuesConfig)
    key_prefix: str = "travel:"
    ttl: RedisTTLConfig = field(default_factory=RedisTTLConfig)

    def get_url(self) -> str:
        """获取 Redis 连接 URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class MilvusCollectionConfig:
    """Milvus 集合配置"""
    name: str
    dimension: int = 1024
    metric_type: str = "COSINE"
    index_type: str = "FLAT"


@dataclass
class MilvusConnectionConfig:
    """Milvus 连接配置"""
    timeout: float = 30.0
    pool_size: int = 10


@dataclass
class MilvusConfig:
    """Milvus 配置"""
    host: str = "localhost"
    port: int = 19530
    db_name: str = "default"
    user: str = ""
    password: str = ""
    secure: bool = False
    collections: Dict[str, MilvusCollectionConfig] = field(default_factory=dict)
    connection: MilvusConnectionConfig = field(default_factory=MilvusConnectionConfig)

    def get_address(self) -> str:
        """获取 Milvus 地址"""
        return f"{self.host}:{self.port}"


@dataclass
class NacosClusterConfig:
    """Nacos 集群配置"""
    enabled: bool = False
    nodes: List[str] = field(default_factory=list)


@dataclass
class NacosConfig:
    """Nacos 配置"""
    server_addresses: List[str] = field(default_factory=lambda: ["http://localhost:8848"])
    namespace: str = "travel-agent"
    group: str = "DEFAULT_GROUP"
    username: str = "nacos"
    password: str = "nacos"
    data_id_prefix: str = "travel-agent-"
    heartbeat_interval: float = 5.0
    timeout: float = 5.0
    cluster: NacosClusterConfig = field(default_factory=NacosClusterConfig)

    def get_server_addresses(self) -> str:
        """获取服务器地址字符串"""
        return ",".join(self.server_addresses)


@dataclass
class MinioMilvusConfig:
    """MinIO Milvus 配置"""
    bucket: str = "milvus"
    path: str = "file"


@dataclass
class MinioConfig:
    """MinIO 配置"""
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    secure: bool = False
    bucket: str = "travel-agent"
    milvus: MinioMilvusConfig = field(default_factory=MinioMilvusConfig)


@dataclass
class MySQLPoolConfig:
    """MySQL 连接池配置"""
    size: int = 10
    timeout: float = 30.0


@dataclass
class MySQLConfig:
    """MySQL 配置"""
    host: str = "localhost"
    port: int = 3306
    username: str = "root"
    password: str = "rootpassword"
    database: str = "nacos_config"
    pool: MySQLPoolConfig = field(default_factory=MySQLPoolConfig)

    def get_url(self) -> str:
        """获取 MySQL 连接 URL"""
        return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class AgentConfig:
    """Agent 配置"""
    max_steps: int = 10
    timeout: float = 60.0


@dataclass
class SessionConfig:
    """会话配置"""
    ttl: int = 86400
    max_per_user: int = 100


@dataclass
class AppConfig:
    """应用配置"""
    name: str = "travel-agent"
    environment: str = "development"
    log_level: str = "INFO"
    agent: AgentConfig = field(default_factory=AgentConfig)
    session: SessionConfig = field(default_factory=SessionConfig)


@dataclass
class InfraConfig:
    """基础设施配置"""
    redis: RedisConfig = field(default_factory=RedisConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    nacos: NacosConfig = field(default_factory=NacosConfig)
    minio: MinioConfig = field(default_factory=MinioConfig)
    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    app: AppConfig = field(default_factory=AppConfig)


# =============================================================================
# 配置加载器
# =============================================================================

class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._config: Optional[InfraConfig] = None

    def load(self) -> InfraConfig:
        """
        加载配置

        Returns:
            InfraConfig: 配置对象
        """
        if self._config is not None:
            return self._config

        # 读取配置文件
        config_data = self._read_yaml()

        # 构建配置对象
        self._config = self._build_config(config_data)

        # 应用环境变量覆盖
        self._apply_env_overrides()

        logger.info("[ConfigLoader] 配置加载完成")
        return self._config

    def _read_yaml(self) -> Dict[str, Any]:
        """读取 YAML 配置文件"""
        if self.config_path is None:
            # 尝试查找配置文件
            possible_paths = [
                Path(".claude/infrastructure.yaml"),
                Path(__file__).parent.parent.parent.parent / ".claude" / "infrastructure.yaml",
                Path("config/infrastructure.yaml"),
                Path("/home/ubuntu/.claude/infrastructure.yaml"),
            ]

            for path in possible_paths:
                if path.exists():
                    self.config_path = str(path)
                    break

        if self.config_path is None or not Path(self.config_path).exists():
            logger.warning(f"[ConfigLoader] 配置文件不存在，使用默认配置")
            return {}

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"[ConfigLoader] 读取配置文件失败: {e}")
            return {}

    def _build_config(self, data: Dict[str, Any]) -> InfraConfig:
        """构建配置对象"""
        redis_data = data.get("redis", {})
        milvus_data = data.get("milvus", {})
        nacos_data = data.get("nacos", {})
        minio_data = data.get("minio", {})
        mysql_data = data.get("mysql", {})
        app_data = data.get("app", {})

        # 构建 Redis 配置
        redis_config = RedisConfig(
            host=redis_data.get("host", "localhost"),
            port=redis_data.get("port", 6379),
            db=redis_data.get("db", 0),
            password=redis_data.get("password", ""),
            key_prefix=redis_data.get("key_prefix", "travel:"),
        )

        # 构建 Milvus 配置
        collections = {}
        for name, col_data in milvus_data.get("collections", {}).items():
            collections[name] = MilvusCollectionConfig(
                name=col_data.get("name", name),
                dimension=col_data.get("dimension", 1024),
                metric_type=col_data.get("metric_type", "COSINE"),
                index_type=col_data.get("index_type", "FLAT"),
            )

        milvus_config = MilvusConfig(
            host=milvus_data.get("host", "localhost"),
            port=milvus_data.get("port", 19530),
            db_name=milvus_data.get("db_name", "default"),
            user=milvus_data.get("user", ""),
            password=milvus_data.get("password", ""),
            secure=milvus_data.get("secure", False),
            collections=collections,
        )

        # 构建 Nacos 配置
        nacos_config = NacosConfig(
            server_addresses=nacos_data.get("server_addresses", ["http://localhost:8848"]),
            namespace=nacos_data.get("namespace", "travel-agent"),
            group=nacos_data.get("group", "DEFAULT_GROUP"),
            username=nacos_data.get("username", "nacos"),
            password=nacos_data.get("password", "nacos"),
            data_id_prefix=nacos_data.get("data_id_prefix", "travel-agent-"),
        )

        # 构建 MinIO 配置
        minio_config = MinioConfig(
            endpoint=minio_data.get("endpoint", "localhost:9000"),
            access_key=minio_data.get("access_key", "minioadmin"),
            secret_key=minio_data.get("secret_key", "minioadmin"),
            secure=minio_data.get("secure", False),
            bucket=minio_data.get("bucket", "travel-agent"),
        )

        # 构建 MySQL 配置
        mysql_config = MySQLConfig(
            host=mysql_data.get("host", "localhost"),
            port=mysql_data.get("port", 3306),
            username=mysql_data.get("username", "root"),
            password=mysql_data.get("password", "rootpassword"),
            database=mysql_data.get("database", "nacos_config"),
        )

        # 构建应用配置
        app_config = AppConfig(
            name=app_data.get("name", "travel-agent"),
            environment=app_data.get("environment", "development"),
            log_level=app_data.get("log_level", "INFO"),
        )

        return InfraConfig(
            redis=redis_config,
            milvus=milvus_config,
            nacos=nacos_config,
            minio=minio_config,
            mysql=mysql_config,
            app=app_config,
        )

    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        if self._config is None:
            return

        # Redis 环境变量
        if os.getenv("REDIS_HOST"):
            self._config.redis.host = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            self._config.redis.port = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_PASSWORD"):
            self._config.redis.password = os.getenv("REDIS_PASSWORD")

        # Milvus 环境变量
        if os.getenv("MILVUS_HOST"):
            self._config.milvus.host = os.getenv("MILVUS_HOST")
        if os.getenv("MILVUS_PORT"):
            self._config.milvus.port = int(os.getenv("MILVUS_PORT"))

        # Nacos 环境变量
        if os.getenv("NACOS_SERVER_ADDR"):
            self._config.nacos.server_addresses = [os.getenv("NACOS_SERVER_ADDR")]
        if os.getenv("NACOS_NAMESPACE"):
            self._config.nacos.namespace = os.getenv("NACOS_NAMESPACE")
        if os.getenv("NACOS_USERNAME"):
            self._config.nacos.username = os.getenv("NACOS_USERNAME")
        if os.getenv("NACOS_PASSWORD"):
            self._config.nacos.password = os.getenv("NACOS_PASSWORD")

        # MinIO 环境变量
        if os.getenv("MINIO_ENDPOINT"):
            self._config.minio.endpoint = os.getenv("MINIO_ENDPOINT")
        if os.getenv("MINIO_ACCESS_KEY"):
            self._config.minio.access_key = os.getenv("MINIO_ACCESS_KEY")
        if os.getenv("MINIO_SECRET_KEY"):
            self._config.minio.secret_key = os.getenv("MINIO_SECRET_KEY")

        # MySQL 环境变量
        if os.getenv("MYSQL_HOST"):
            self._config.mysql.host = os.getenv("MYSQL_HOST")
        if os.getenv("MYSQL_PORT"):
            self._config.mysql.port = int(os.getenv("MYSQL_PORT"))
        if os.getenv("MYSQL_USER"):
            self._config.mysql.username = os.getenv("MYSQL_USER")
        if os.getenv("MYSQL_PASSWORD"):
            self._config.mysql.password = os.getenv("MYSQL_PASSWORD")

    def save(self, config: InfraConfig, path: Optional[str] = None):
        """
        保存配置到文件

        Args:
            config: 配置对象
            path: 保存路径
        """
        save_path = path or self.config_path
        if save_path is None:
            save_path = ".claude/infrastructure.yaml"

        # 转换为字典
        data = {
            "redis": {
                "host": config.redis.host,
                "port": config.redis.port,
                "db": config.redis.db,
                "password": config.redis.password,
                "key_prefix": config.redis.key_prefix,
            },
            "milvus": {
                "host": config.milvus.host,
                "port": config.milvus.port,
                "db_name": config.milvus.db_name,
                "user": config.milvus.user,
                "password": config.milvus.password,
                "secure": config.milvus.secure,
            },
            "nacos": {
                "server_addresses": config.nacos.server_addresses,
                "namespace": config.nacos.namespace,
                "group": config.nacos.group,
                "username": config.nacos.username,
                "password": config.nacos.password,
            },
            "minio": {
                "endpoint": config.minio.endpoint,
                "access_key": config.minio.access_key,
                "secret_key": config.minio.secret_key,
            },
            "mysql": {
                "host": config.mysql.host,
                "port": config.mysql.port,
                "username": config.mysql.username,
                "password": config.mysql.password,
                "database": config.mysql.database,
            },
        }

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, indent=2)

        logger.info(f"[ConfigLoader] 配置已保存到: {save_path}")


# =============================================================================
# 便捷函数
# =============================================================================

@lru_cache(maxsize=1)
def get_config(config_path: Optional[str] = None) -> InfraConfig:
    """
    获取基础设施配置

    Args:
        config_path: 配置文件路径

    Returns:
        InfraConfig: 配置对象
    """
    loader = ConfigLoader(config_path)
    return loader.load()


def create_redis_queue_config(redis_config: Optional[RedisConfig] = None):
    """
    从配置创建 RedisQueue

    Args:
        redis_config: Redis 配置

    Returns:
        RedisQueue: Redis 队列实例
    """
    from .redis_queue import RedisQueue, RedisConfig

    if redis_config is None:
        config = get_config()
        redis_config = config.redis

    queue_config = RedisConfig(
        host=redis_config.host,
        port=redis_config.port,
        db=redis_config.db,
        password=redis_config.password if redis_config.password else None,
    )

    return RedisQueue("default", config=queue_config)


def create_milvus_store_config(milvus_config: Optional[MilvusConfig] = None):
    """
    从配置创建 MilvusVectorStore

    Args:
        milvus_config: Milvus 配置

    Returns:
        MilvusVectorStore: 向量存储实例
    """
    from .milvus_vector import MilvusVectorStore, MilvusConfig as MVConfig, DistanceMetric, IndexType

    if milvus_config is None:
        config = get_config()
        milvus_config = config.milvus

    # 获取第一个集合配置或使用默认
    if milvus_config.collections:
        first_collection = list(milvus_config.collections.values())[0]
        dim = first_collection.dimension
        metric = DistanceMetric(first_collection.metric_type)
        index_type = IndexType(first_collection.index_type)
    else:
        dim = 1024
        metric = DistanceMetric.COSINE
        index_type = IndexType.FLAT

    store_config = MVConfig(
        host=milvus_config.host,
        port=milvus_config.port,
        db_name=milvus_config.db_name,
        user=milvus_config.user,
        password=milvus_config.password,
        secure=milvus_config.secure,
    )

    return MilvusVectorStore(
        collection_name="default",
        dim=dim,
        config=store_config,
        distance_metric=metric,
        index_type=index_type,
    )


def create_nacos_client_config(nacos_config: Optional[NacosConfig] = None):
    """
    从配置创建 NacosClient

    Args:
        nacos_config: Nacos 配置

    Returns:
        NacosClient: Nacos 客户端实例
    """
    from .nacos_client import NacosClient, NacosConfig as NCConfig

    if nacos_config is None:
        config = get_config()
        nacos_config = config.nacos

    client_config = NCConfig(
        server_addresses=nacos_config.server_addresses,
        namespace=nacos_config.namespace,
        group=nacos_config.group,
        username=nacos_config.username,
        password=nacos_config.password,
        data_id_prefix=nacos_config.data_id_prefix,
    )

    return NacosClient(config=client_config)


def print_connection_info():
    """打印所有连接信息"""
    config = get_config()

    print("\n" + "=" * 60)
    print("  小帅旅游助手 - 基础设施连接信息")
    print("=" * 60)

    print("\n[Redis]")
    print(f"  地址: {config.redis.host}:{config.redis.port}")
    print(f"  密码: {'***' if config.redis.password else '无'}")
    print(f"  键前缀: {config.redis.key_prefix}")

    print("\n[Milvus]")
    print(f"  地址: {config.milvus.host}:{config.milvus.port}")
    print(f"  数据库: {config.milvus.db_name}")
    print(f"  集合: {list(config.milvus.collections.keys())}")

    print("\n[Nacos]")
    print(f"  地址: {config.nacos.get_server_addresses()}")
    print(f"  命名空间: {config.nacos.namespace}")
    print(f"  用户: {config.nacos.username}")

    print("\n[MinIO]")
    print(f"  端点: {config.minio.endpoint}")
    print(f"  桶: {config.minio.bucket}")

    print("\n[MySQL]")
    print(f"  地址: {config.mysql.host}:{config.mysql.port}")
    print(f"  数据库: {config.mysql.database}")

    print("\n" + "=" * 60)
