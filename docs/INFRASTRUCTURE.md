# 基础设施服务指南

本文档描述小帅旅游助手使用的基础设施服务及其配置。

---

## 目录

- [Docker Compose 全栈部署](#docker-compose-全栈部署)
- [Docker Compose 启动](#docker-compose-启动)
- [服务连接信息](#服务连接信息)
- [手动启动服务](#手动启动服务)
- [配置管理](#配置管理)
- [健康检查](#健康检查)

---

## Docker Compose 全栈部署

当前 `docker-compose.yml` 包含完整的应用服务和基础设施服务，支持一键启动全栈环境。

### 服务总览

| 分类 | 服务 | 容器名 | 端口 | 说明 |
|------|------|--------|------|------|
| **应用** | Agent | agent | 50051 | gRPC AI 推理服务 |
| **应用** | Web | web | 38000 | FastAPI 后端 API |
| **应用** | Frontend | frontend | 33001 | Next.js 前端 (standalone) |
| **基础设施** | Redis | redis | 6379 | 消息队列/缓存 |
| **基础设施** | Milvus | milvus | 19530 | 向量数据库 |
| **基础设施** | Milvus etcd | milvus-etcd | 2379 | Milvus 元数据 |
| **基础设施** | Milvus MinIO | milvus-minio | 9001 | Milvus 存储 |
| **基础设施** | Nacos | nacos | 38848 | 配置中心 |
| **基础设施** | MySQL | mysql | 3306 | Nacos 数据库 |

### 应用服务 Dockerfile

| 服务 | Dockerfile | 构建方式 | 基础镜像 |
|------|-----------|----------|----------|
| Agent | `agent/Dockerfile` | 多阶段 (builder + runner) | python:3.10-slim |
| Web | `web/Dockerfile` | 多阶段 (builder + runner) | python:3.10-slim |
| Frontend | `frontend/Dockerfile` | 三阶段 (deps + builder + runner) | node:20-alpine |

### 依赖关系

```
frontend ──→ web ──→ agent ──→ redis (healthy)
                         └──→ milvus (healthy)
              └──→ redis (healthy)
              └──→ milvus (healthy)
nacos
mysql
```

### 网络配置

所有服务运行在 `shuai-network` (bridge) 网络中，服务间通过容器名互相访问。

---

## Docker Compose 启动

### 启动所有服务

```bash
# 前台运行
docker-compose up

# 后台运行
docker-compose up -d

# 构建并启动
docker-compose up -d --build

# 查看日志
docker-compose logs -f

# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

### 启动单个服务

```bash
# 仅启动基础设施
docker-compose up -d redis milvus-etcd milvus-minio milvus nacos mysql

# 仅启动应用服务 (需要基础设施先启动)
docker-compose up -d --build agent web frontend

# Redis
docker-compose up -d redis

# Milvus
docker-compose up -d milvus

# Nacos
docker-compose up -d nacos
```

---

## 服务连接信息

| 服务 | 端口 | 默认用户 | 默认密码 | 说明 |
|-----|------|---------|---------|------|
| Redis | 6379 | - | - | 消息队列 & 缓存 |
| Milvus | 19530 | - | - | 向量数据库 |
| Nacos | 38848 | nacos | nacos | 配置中心 |
| MySQL | 3306 | root | rootpassword | Nacos 数据库 |
| MinIO | 9000 | minioadmin | minioadmin | Milvus 存储 |

### 配置文件位置

所有连接配置保存在: `.claude/infrastructure.yaml`

```yaml
redis:
  host: "localhost"
  port: 6379

milvus:
  host: "localhost"
  port: 19530

nacos:
  server_addresses:
    - "http://localhost:38848"
  username: "nacos"
  password: "nacos"
```

---

## 手动启动服务

### 1. Redis

```bash
# 使用 Docker 启动
docker run -d \
  --name travel-agent-redis \
  -p 6379:6379 \
  -v redis_data:/data \
  redis:7-alpine \
  redis-server --appendonly yes

# 本地启动 (已安装 Redis)
redis-server --port 6379 --maxmemory 256mb
```

### 2. Milvus

```bash
# 使用 Docker 启动
docker run -d \
  --name travel-agent-milvus \
  -p 19530:19530 \
  -p 9091:9091 \
  -v milvus_data:/var/lib/milvus \
  -e ETCD_ENDPOINTS=localhost:2379 \
  -e MINIO_ADDRESS=localhost:9000 \
  milvusdb/milvus:v2.4.16

# 需要先启动 etcd 和 MinIO
docker run -d --name milvus-etcd \
  -p 2379:2379 \
  quay.io/coreos/etcd:v3.5.16

docker run -d --name milvus-minio \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

### 3. Nacos

```bash
# 使用 Docker 启动 (嵌入式数据库)
docker run -d \
  --name travel-agent-nacos \
  -p 38848:38848 \
  -p 39848:39848 \
  -v nacos_data:/home/nacos/data \
  nacos/nacos-server:v2.3.2

# 使用 Docker + MySQL
docker run -d \
  --name travel-agent-nacos \
  -p 38848:38848 \
  -e MODE=cluster \
  -e SPRING_DATASOURCE_PLATFORM=mysql \
  -e MYSQL_SERVICE_DB_NAME=nacos_config \
  -e MYSQL_SERVICE_DB_USER=root \
  -e MYSQL_SERVICE_DB_PASSWORD=rootpassword \
  nacos/nacos-server:v2.3.2
```

---

## 配置管理

### 使用配置加载器

```python
from infrastructure.infra_config import get_config, print_connection_info

# 获取配置
config = get_config()

# Redis 配置
print(f"Redis: {config.redis.host}:{config.redis.port}")

# Milvus 配置
print(f"Milvus: {config.milvus.host}:{config.milvus.port}")

# Nacos 配置
print(f"Nacos: {config.nacos.server_addresses}")

# 打印所有连接信息
print_connection_info()
```

### 环境变量覆盖

配置可以通过环境变量覆盖:

```bash
export REDIS_HOST=192.168.1.100
export REDIS_PORT=6380
export MILVUS_HOST=192.168.1.101
export NACOS_SERVER_ADDR=http://192.168.1.102:38848
```

### 创建服务实例

```python
from infrastructure.infra_config import (
    get_config,
    create_redis_queue_config,
    create_milvus_store_config,
    create_nacos_client_config
)

# 获取配置
config = get_config()

# 创建 Redis 队列
from infrastructure.redis_queue import RedisQueue
queue = RedisQueue(
    queue_name="travel_tasks",
    config=create_redis_queue_config()
)

# 创建 Milvus 向量存储
from infrastructure.milvus_vector import MilvusVectorStore
store = create_milvus_store_config()

# 创建 Nacos 客户端
from infrastructure.nacos_client import NacosClient
nacos = create_nacos_client_config()
```

---

## 健康检查

### 检查所有服务

```bash
# Redis
redis-cli -h localhost -p 6379 ping
# 期望: PONG

# Milvus
curl http://localhost:9091/healthz
# 期望: OK

# Nacos
curl http://localhost:38848/nacos/v1/ns/service/list
# 期望: {"services": [...]}
```

### Python 健康检查

```python
import asyncio
from infrastructure.infra_config import get_config

async def check_services():
    config = get_config()

    results = {}

    # 检查 Redis
    try:
        import redis.asyncio as redis
        r = redis.Redis(host=config.redis.host, port=config.redis.port)
        await r.ping()
        results["redis"] = "healthy"
    except Exception as e:
        results["redis"] = f"unhealthy: {e}"

    # 检查 Milvus
    try:
        from pymilvus import connections
        connections.connect(host=config.milvus.host, port=str(config.milvus.port))
        results["milvus"] = "healthy"
    except Exception as e:
        results["milvus"] = f"unhealthy: {e}"

    # 检查 Nacos
    try:
        import httpx
        r = httpx.get(f"{config.nacos.server_addresses[0]}/nacos/v1/ns/service/list")
        if r.status_code == 200:
            results["nacos"] = "healthy"
        else:
            results["nacos"] = "unhealthy"
    except Exception as e:
        results["nacos"] = f"unhealthy: {e}"

    return results

results = asyncio.run(check_services())
for service, status in results.items():
    print(f"{service}: {status}")
```

---

## RAG 检索服务

### 使用 Milvus RAG 检索器

```python
from middleware.milvus_rag import create_milvus_retriever

# 创建检索器
retriever = await create_milvus_retriever(
    collection_name="travel_documents",
    dim=1024,
    host="localhost",
    port=19530,
    embedding_model=embedding_model
)

# 检查状态
print(f"状态: {retriever.status}")
print(f"使用 Milvus: {retriever.is_milvus_ready}")
print(f"使用内存模式: {retriever.is_using_memory}")

# 添加文档
documents = [
    {"content": "北京是中国的首都，有悠久的历史。"},
    {"content": "上海是中国最大的城市，经济中心。"}
]
await retriever.add_documents(documents, source="travel")

# 检索文档
results = await retriever.retrieve("北京旅游推荐", top_k=5)
for r in results.results:
    print(f"  {r.content[:50]}... (score: {r.score:.4f})")

# 获取统计
stats = await retriever.get_stats()
print(stats)
```

### 混合检索器

```python
from middleware.milvus_rag import create_hybrid_retriever

# 创建混合检索器
milvus_retriever, memory_retriever = await create_hybrid_retriever(
    embedding_model=embedding_model
)

# Milvus 向量检索
vector_results = await milvus_retriever.retrieve(query, top_k=5)

# 内存关键词检索
keyword_results = await memory_retriever.retrieve(
    query, top_k=5, strategy=RetrievalStrategy.KEYWORD
)
```

---

## 配置热更新

### 使用 ConfigHotReload

```python
from infrastructure.config_hot_reload import get_config_reloader

# 获取配置热重载器
reloader = await get_config_reloader(
    config_path=".claude/infrastructure.yaml",
    nacos_enabled=True,
    server_addresses=["http://localhost:38848"],
    namespace="travel-agent"
)

# 获取配置
app_name = reloader.get("app.name")
redis_host = reloader.get("redis.host")

# 监听配置变化
def on_config_change(key, old_value, new_value):
    print(f"配置变化: {key}")
    print(f"  旧值: {old_value}")
    print(f"  新值: {new_value}")

reloader.on_change("app", on_config_change)

# 手动刷新配置
await reloader.reload("app")

# 获取统计信息
stats = reloader.get_stats()
print(stats)

# 关闭
await reloader.close()
```

### 配置重载策略

```python
from infrastructure.config_hot_reload import ConfigReloadPolicy

# 自定义重载策略
policy = ConfigReloadPolicy(
    enable_hot_reload=True,
    reload_interval=30,      # 每 30 秒检查一次
    max_retries=3,           # 最多重试 3 次
    validate_on_reload=True, # 重载时验证配置
    backup_before_reload=True # 重载前备份
)

reloader = ConfigHotReload(policy=policy)
```

---

## 组件详解

本节详细介绍每个 Docker 组件的作用、原理以及在项目中的具体用途。

### 1. Redis (redis:7-alpine)

#### 作用
Redis 是一个高性能的内存键值数据库，在本项目中承担以下职责：

| 功能 | 用途 |
|------|------|
| **消息队列** | 异步任务队列，处理后台任务 |
| **会话缓存** | 存储用户对话状态、临时数据 |
| **缓存层** | 缓存高频访问数据，减少数据库压力 |
| **分布式锁** | 保证并发场景下的数据一致性 |

#### 项目中的应用
```python
# 记忆系统 - 使用 Redis 存储对话历史
from memory.redis_memory import RedisMemoryManager

memory = RedisMemoryManager(
    host="localhost",
    port=6379,
    key_prefix="travel:",
    fallback=True  # 连接失败时自动降级到内存模式
)

# 存储对话
await memory.add_message(session_id, "user", "我想去北京旅游")
await memory.add_message(session_id, "assistant", "北京有很多好玩的景点...")

# 获取历史
history = await memory.get_conversation_history(session_id)
```

#### 核心命令
```bash
# 连接 Redis
redis-cli -h localhost -p 6379

# 查看所有键
KEYS travel:*

# 查看对话历史
LRANGE travel:session:xxx:messages 0 -1

# 查看缓存统计
INFO memory
```

---

### 2. Milvus (milvusdb/milvus:v2.5.10)

#### 作用
Milvus 是一个开源的向量数据库，专门用于存储和检索大规模向量数据：

| 功能 | 用途 |
|------|------|
| **向量存储** | 存储文档、用户查询的向量表示 |
| **相似度检索** | 基于向量相似度的语义搜索 |
| **RAG 检索** | 检索增强生成，获取相关上下文 |

#### 项目中的应用
```python
# RAG 检索器 - 使用 Milvus 进行语义搜索
from middleware.milvus_rag import create_milvus_retriever

retriever = await create_milvus_retriever(
    collection_name="travel_documents",
    dim=1024,  # 向量维度
    host="localhost",
    port=19530,
    fallback_to_memory=True  # 连接失败时降级
)

# 添加文档（自动转换为向量）
await retriever.add_documents([
    {"content": "北京故宫是中国古代宫廷建筑的精华", "source": "attractions"},
    {"content": "长城是世界上最著名的古代防御工程", "source": "attractions"}
])

# 语义搜索
results = await retriever.retrieve("北京有哪些历史古迹", top_k=5)
for r in results:
    print(f"{r.content} (相似度: {r.score:.4f})")
```

#### 依赖关系
```
Milvus 独立运行
    │
    ├── milvus-etcd (etcd:v3.5.16)
    │   └── 存储集群元数据
    │
    └── milvus-minio (minio)
        └── 存储向量数据文件
```

#### 核心命令
```bash
# 查看 Milvus 状态
curl http://localhost:9091/healthz

# 查看集合列表 (需要 Milvus CLI)
# milvus_cli collection list

# 查看集合统计
curl "http://localhost:9091/v2/vectordb/collections/get_stats"
```

---

### 3. Nacos (nacos/nacos-server:v2.3.2)

#### 作用
Nacos 是阿里巴巴开源的配置中心和服务发现平台：

| 功能 | 用途 |
|------|------|
| **配置管理** | 集中管理应用配置，支持热更新 |
| **配置变更监听** | 配置修改时自动通知应用 |
| **服务发现** | 管理服务实例地址（本项目未启用） |

#### 项目中的应用
```python
# 配置热更新 - 使用 Nacos 动态调整配置
from infrastructure.config_hot_reload import get_config_reloader

reloader = await get_config_reloader(
    config_path=".claude/infrastructure.yaml",
    nacos_enabled=True,
    server_addresses=["http://localhost:38848"],
    namespace="travel-agent"
)

# 获取配置
app_name = reloader.get("app.name")
log_level = reloader.get("app.log_level")

# 监听配置变化
def on_config_change(key, old_value, new_value):
    print(f"配置 {key} 已变更: {old_value} → {new_value}")

reloader.on_change("app", on_config_change)
```

#### Nacos 控制台
- **访问地址**: http://localhost:38848/nacos
- **默认用户名**: nacos
- **默认密码**: nacos

#### 核心操作
```bash
# 查看所有配置
curl "http://localhost:38848/nacos/v1/configs/list?dataId=&group=&pageNo=1&pageSize=10"

# 发布配置
curl -X POST "http://localhost:38848/nacos/v1/cs/configs" \
  -d "dataId=travel-agent.yaml" \
  -d "group=DEFAULT_GROUP" \
  -d "content=app:
  name: '小帅旅游助手'
  log_level: 'DEBUG'"

# 监听配置变化 (长轮询)
curl "http://localhost:38848/nacos/v1/cs/configs/listener" \
  -d "Listening-Configs=travel-agent.yaml"
```

---

### 4. MinIO (minio/minio:RELEASE.2023-03-20T20-16-18Z)

#### 作用
MinIO 是一个高性能的分布式对象存储服务：

| 功能 | 用途 |
|------|------|
| **Milvus 存储后端** | 存储 Milvus 的向量数据文件 |
| **文件存储** | 存储上传的文档、图片等 |
| **S3 兼容** | 使用 S3 API 访问 |

#### 项目中的角色
MinIO **仅作为 Milvus 的存储后端**使用，不直接被应用层调用。

#### MinIO 控制台
- **API 端口**: localhost:9000
- **控制台端口**: localhost:9001
- **用户名**: minioadmin
- **密码**: minioadmin

#### 核心命令
```bash
# 使用 mc (MinIO Client) 操作
mc alias set local http://localhost:9000 minioadmin minioadmin

# 查看 Milvus 存储桶
mc ls local/milvus

# 查看文件
mc ls local/milvus/files/
```

---

### 5. MySQL (mysql:8.0-debian)

#### 作用
MySQL 是最流行的关系型数据库之一：

| 功能 | 用途 |
|------|------|
| **Nacos 数据库** | 存储 Nacos 的配置数据（默认使用嵌入式数据库，可选） |
| **应用数据库** | 存储结构化业务数据（本项目当前未使用） |

#### 项目中的角色
MySQL **仅作为 Nacos 的持久化存储**使用，存储 Nacos 的配置数据。

#### 核心命令
```bash
# 连接 MySQL
mysql -h localhost -P 3306 -u root -prootpassword

# 查看 Nacos 数据库
SHOW DATABASES;
USE nacos_config;

# 查看配置表
SHOW TABLES;
SELECT * FROM config_info LIMIT 10;
```

---

### 6. etcd (quay.io/coreos/etcd:v3.5.16)

#### 作用
etcd 是一个分布式的键值存储系统：

| 功能 | 用途 |
|------|------|
| **Milvus 元数据** | 存储 Milvus 集群的元数据信息 |
| **一致性保证** | 保证 Milvus 集群数据一致性 |

#### 项目中的角色
etcd **仅作为 Milvus 的依赖服务**，不直接被应用层调用。

#### 核心命令
```bash
# 查看 etcd 集群状态
docker exec milvus-etcd etcdctl endpoint status --cluster

# 查看所有键
docker exec milvus-etcd etcdctl get --prefix /

# 健康检查
docker exec milvus-etcd etcdctl endpoint health
```

---

## Docker 可视化管理

### Redis Commander

访问: http://localhost:8081

```bash
docker run -d \
  --name redis-commander \
  -p 8081:8081 \
  -e REDIS_HOSTS=local:localhost:6379 \
  rediscommander/redis-commander:latest
```

---

## 常见问题

### 1. Redis 连接失败

```bash
# 检查 Redis 是否运行
docker ps | grep redis

# 查看 Redis 日志
docker logs redis

# 重启 Redis
docker restart redis
```

### 2. Milvus 连接失败

```bash
# 检查端口是否开放
telnet localhost 19530

# 查看 Milvus 日志
docker logs milvus

# 确保 etcd 和 MinIO 先启动
docker ps | grep milvus
```

### 3. Nacos 无法启动

```bash
# 查看日志
docker logs nacos

# 检查 MySQL 连接
mysql -h localhost -P 3306 -u root -prootpassword -e "SHOW DATABASES"
```

---

## 服务端口汇总

| 服务 | 端口 | 协议 | 用途 |
|-----|------|------|------|
| Redis | 6379 | TCP | 消息队列、缓存 |
| Milvus | 19530 | TCP | 向量存储 |
| Milvus | 9091 | HTTP | 健康检查 |
| Nacos | 38848 | HTTP | 配置中心 |
| Nacos | 39848 | TCP | 服务通信 |
| MinIO | 9000 | TCP | 对象存储 |
| MinIO | 9001 | HTTP | 控制台 |
| MySQL | 3306 | TCP | 数据库 |
| Redis Commander | 8081 | HTTP | 可视化管理 |

---

## 高级基础设施服务 (v0.0.1)

本节介绍 v0.0.1 版本新增的高级基础设施服务，这些服务充分利用 Redis 和 Milvus 提供更强大的功能支持。

### 1. LLM 响应缓存

#### 概述
LLMResponseCache 提供 Redis ベースの智能缓存层，通过 MD5 哈希对 LLM 响应进行缓存，显著减少重复请求的响应时间和 API 调用成本。

#### 核心功能
- **智能哈希**: 使用 MD5 对 prompt 进行唯一标识
- **TTL 管理**: 支持自定义过期时间
- **相似度检测**: 模糊匹配相似提示词
- **统计监控**: 提供缓存命中率统计

#### 使用示例
```python
from infrastructure.llm_cache import create_llm_cache, CacheConfig

# 创建缓存配置
config = CacheConfig(
    ttl=3600,           # 缓存时间（秒）
    max_memory=1000,    # 最大缓存条目数
    enable_similarity=True,  # 启用相似度检测
    similarity_threshold=0.9   # 相似度阈值
)

# 创建缓存实例
cache = await create_llm_cache(config)

# 缓存 LLM 响应
await cache.set("用户问题", "LLM 回答内容")

# 获取缓存响应
cached = await cache.get("用户问题")
if cached:
    print(f"命中缓存: {cached}")
else:
    print("未命中缓存")

# 获取统计信息
stats = cache.get_stats()
print(f"命中率: {stats.hit_rate:.2%}")
```

#### 缓存中间件
```python
from infrastructure.llm_cache import LLMCacheMiddleware

# 创建中间件
middleware = LLMCacheMiddleware(
    cache=cache,
    exclude_patterns=["admin:*"],  # 排除某些 key
    include_patterns=["llm:*"]    # 只包含某些 key
)

# 在 LLM 调用中使用
async def call_llm(prompt: str) -> str:
    cache_key = await middleware.get_key(prompt)

    # 检查缓存
    cached = await middleware.get(cache_key)
    if cached:
        return cached

    # 调用 LLM
    response = await actual_llm_call(prompt)

    # 缓存结果
    await middleware.set(cache_key, response)

    return response
```

---

### 2. API 限流器

#### 概述
RateLimiter 提供多种限流算法，保护 API 服务免受过载，支持固定窗口、滑动窗口和令牌桶算法。

#### 限流算法

| 算法 | 特点 | 适用场景 |
|------|------|---------|
| FixedWindow | 简单高效 | 粗粒度限流 |
| SlidingWindow | 平滑限流 | 精确限流 |
| TokenBucket | 支持突发流量 | API 突发请求 |

#### 使用示例
```python
from infrastructure.rate_limiter import (
    create_rate_limiter,
    RateLimitConfig,
    RateLimitStrategy
)

# 创建限流配置
config = RateLimitConfig(
    strategy=RateLimitStrategy.SLIDING_WINDOW,
    max_requests=100,      # 最大请求数
    window_seconds=60,     # 时间窗口（秒）
    burst_factor=1.5,      # 突发因子（令牌桶）
    block_duration=60      # 封禁时长（秒）
)

# 创建限流器
limiter = await create_rate_limiter(config)

# 检查请求是否允许
result = await limiter.check("user:123")
if result.allowed:
    print("请求允许")
else:
    print(f"请求被限流: {result.retry_after}秒后重试")

# 获取使用统计
usage = await limiter.get_usage("user:123")
print(f"已使用: {usage.used}/{usage.limit}")

# 手动释放令牌
await limiter.release("user:123")
```

#### 限流中间件
```python
from infrastructure.rate_limiter import RateLimitMiddleware

# 创建中间件
middleware = RateLimitMiddleware(
    limiter=limiter,
    key_generator=lambda request: request.user_id,
    on_rate_limit_exceeded=lambda key: log.warning(f"Rate limit exceeded for {key}")
)

# 应用到 FastAPI
app.add_middleware(middleware)
```

---

### 3. 用户偏好向量存储

#### 概述
UserPreferenceStore 利用 Milvus 向量存储用户偏好数据，支持个性化推荐和语义搜索。

#### 核心功能
- **偏好向量存储**: 将用户偏好转换为向量存储
- **相似度检索**: 找到偏好相似的用户
- **推荐生成**: 基于偏好生成个性化推荐
- **多类别支持**: 支持多种偏好类别

#### 使用示例
```python
from infrastructure.user_preference_store import (
    create_user_preference_store,
    UserPreference,
    PreferenceCategory,
    VectorStoreConfig
)

# 创建配置
config = VectorStoreConfig(
    collection_name="user_preferences",
    dimension=1024,
    host="localhost",
    port=19530
)

# 创建存储实例
pref_store = await create_user_preference_store(config)

# 添加用户偏好
await pref_store.add_preference(
    user_id="user_001",
    category=PreferenceCategory.TRAVEL_STYLE,
    content="喜欢自然风光，偏好徒步和露营",
    tags=["nature", "hiking", "camping"]
)

# 搜索相似偏好用户
results = await pref_store.search_similar_users(
    user_id="user_001",
    category=PreferenceCategory.TRAVEL_STYLE,
    top_k=5
)
for user, score in results:
    print(f"用户: {user}, 相似度: {score:.4f}")

# 获取个性化推荐
recommendations = await pref_store.get_recommendations(
    user_id="user_001",
    category=PreferenceCategory.DESTINATION,
    top_k=10
)
```

---

### 4. 实时消息推送

#### 概述
RealtimePusher 基于 Redis Pub/Sub 提供实时消息推送服务，支持 WebSocket 集成。

#### 核心功能
- **Redis Pub/Sub**: 高效的发布订阅机制
- **消息优先级**: 支持优先级队列
- **事件类型**: 支持多种事件类型
- **WebSocket 集成**: 支持 WebSocket 推送

#### 使用示例
```python
from infrastructure.realtime_pusher import (
    create_realtime_pusher,
    PushMessage,
    PushPriority,
    EventType
)

# 创建推送器
pusher = await create_realtime_pusher()

# 发送推送消息
message = PushMessage(
    user_id="user_001",
    event=EventType.TRAVEL_RECOMMENDATION,
    payload={"destination": "三亚", "price": 1999},
    priority=PushPriority.HIGH
)

await pusher.push(message)

# 批量推送
messages = [
    PushMessage(user_id=f"user_{i}", event=EventType.SYSTEM_NOTICE, payload={"msg": "Hello"})
    for i in range(100)
]
await pusher.batch_push(messages)

# 获取用户消息
inbox = await pusher.get_inbox("user_001")
for msg in inbox:
    print(f"消息: {msg.payload}")
```

#### WebSocket 集成
```python
from infrastructure.realtime_pusher import WebSocketManager

# 创建 WebSocket 管理器
ws_manager = WebSocketManager(pusher=pusher)

# 处理 WebSocket 连接
async def handle_websocket(websocket, user_id: str):
    await ws_manager.connect(websocket, user_id)

    try:
        async for message in ws_manager.listen(user_id):
            await websocket.send(message)
    finally:
        ws_manager.disconnect(user_id)
```

---

### 5. 基础设施监控

#### 概述
InfrastructureMonitor 提供全面的基础设施健康监控，支持 Redis、Milvus、Nacos、MinIO、MySQL 等服务。

#### 核心功能
- **健康检查**: 定期检查所有服务状态
- **指标收集**: 收集性能和资源指标
- **告警配置**: 支持自定义告警规则
- **历史追踪**: 记录历史健康状态

#### 使用示例
```python
from infrastructure.monitor import create_monitor, ServiceType

# 创建监控器
monitor = await create_monitor()

# 检查所有服务健康状态
health = await monitor.check_all()
for service, status in health.items():
    print(f"{service}: {status.status} - {status.message}")

# 检查特定服务
redis_health = await monitor.check_service(ServiceType.REDIS)
milvus_health = await monitor.check_service(ServiceType.MILVUS)

# 获取服务指标
metrics = await monitor.get_metrics(ServiceType.REDIS)
print(f"连接数: {metrics.connections}")
print(f"内存使用: {metrics.memory_used}")

# 配置告警
alert_config = AlertConfig(
    service=ServiceType.REDIS,
    check_interval=30,
    max_failures=3,
    notification_channels=["email", "webhook"]
)
await monitor.add_alert_rule(alert_config)
```

---

### 6. 对话历史向量存储

#### 概述
ConversationVectorStore 利用 Milvus 存储和检索对话历史，支持语义搜索和上下文管理。

#### 核心功能
- **对话存储**: 存储对话和消息
- **语义搜索**: 基于向量相似度搜索对话
- **上下文检索**: 获取相关历史对话
- **状态管理**: 管理对话状态

#### 使用示例
```python
from infrastructure.conversation_store import (
    create_conversation_store,
    Conversation,
    Message,
    ConversationStatus
)

# 创建存储实例
conv_store = await create_conversation_store()

# 创建新对话
conversation = Conversation(
    user_id="user_001",
    title="北京旅游咨询",
    status=ConversationStatus.ACTIVE
)
await conv_store.create(conversation)

# 添加消息
await conv_store.add_message(
    conversation_id=conversation.id,
    role="user",
    content="我想去北京旅游，推荐一些景点"
)
await conv_store.add_message(
    conversation_id=conversation.id,
    role="assistant",
    content="北京有很多著名景点，故宫、长城、颐和园等"
)

# 搜索相关对话
results = await conv_store.search(
    query="北京旅游推荐",
    user_id="user_001",
    top_k=5
)
for conv, score in results:
    print(f"对话: {conv.title}, 相似度: {score:.4f}")

# 获取对话历史
messages = await conv_store.get_messages(conversation.id)
```

---

### 7. 配置版本管理

#### 概述
ConfigVersionManager 提供配置版本管理功能，支持版本历史、对比和回滚。

#### 核心功能
- **版本存储**: 自动保存配置版本
- **版本对比**: 对比不同版本的差异
- **版本回滚**: 支持一键回滚到历史版本
- **变更追踪**: 记录配置变更历史

#### 使用示例
```python
from infrastructure.config_version_manager import (
    create_version_manager,
    ConfigVersion,
    ConfigStatus
)

# 创建版本管理器
version_manager = await create_version_manager()

# 保存配置版本
version = await version_manager.save(
    config_data={"app": {"name": "TravelAgent", "version": "0.0.1"}},
    description="更新应用配置",
    created_by="admin"
)
print(f"版本号: {version.version_id}")

# 获取配置历史
history = await version_manager.get_history(
    config_key="app",
    limit=10
)
for v in history:
    print(f"版本 {v.version_id}: {v.created_at} - {v.description}")

# 对比版本
diff = await version_manager.compare("v1", "v2")
print(f"新增: {diff.added}")
print(f"删除: {diff.removed}")
print(f"修改: {diff.modified}")

# 回滚到指定版本
rollback_result = await version_manager.rollback("v1")
print(f"回滚成功: {rollback_result.success}")

# 获取当前版本
current = await version_manager.get_current()
print(f"当前版本: {current.version_id}")
```

---

### 8. 高级服务集成示例

#### 综合使用示例
```python
import asyncio
from infrastructure.infra_config import get_config
from infrastructure.llm_cache import create_llm_cache, CacheConfig
from infrastructure.rate_limiter import create_rate_limiter, RateLimitConfig
from infrastructure.monitor import create_monitor, ServiceType
from infrastructure.conversation_store import create_conversation_store

async def main():
    config = get_config()

    # 1. 初始化缓存
    cache = await create_llm_cache(CacheConfig(ttl=3600))

    # 2. 初始化限流器
    limiter = await create_rate_limiter(
        RateLimitConfig(max_requests=100, window_seconds=60)
    )

    # 3. 初始化对话存储
    conv_store = await create_conversation_store()

    # 4. 初始化监控
    monitor = await create_monitor()

    # 检查基础设施健康
    health = await monitor.check_all()
    print("服务健康状态:", health)

    # 应用限流和缓存
    user_id = "user_001"
    prompt = "北京有哪些美食推荐？"

    # 检查限流
    result = await limiter.check(user_id)
    if not result.allowed:
        print(f"请求被限流，请 {result.retry_after} 秒后重试")
        return

    # 检查缓存
    cache_key = f"llm:{hash(prompt)}"
    cached = await cache.get(cache_key)
    if cached:
        print(f"命中缓存: {cached}")
        return

    # 模拟 LLM 调用
    response = "北京烤鸭、炸酱面、豆汁儿都是北京特色美食..."

    # 缓存响应
    await cache.set(cache_key, response, ttl=3600)

    # 记录使用
    await limiter.use(user_id)

    print(f"LLM 响应: {response}")

asyncio.run(main())
```

---

### 服务配置汇总

#### Redis 服务
| 服务 | 用途 | 关键配置 |
|------|------|---------|
| LLMResponseCache | LLM 响应缓存 | ttl, max_memory |
| RateLimiter | API 限流 | window, max_requests |
| RealtimePusher | 实时推送 | pubsub_channel |
| ConfigVersionManager | 配置版本 | version_ttl |

#### Milvus 服务
| 服务 | 用途 | 集合名称 |
|------|------|---------|
| UserPreferenceStore | 用户偏好 | user_preferences |
| ConversationVectorStore | 对话历史 | conversations |
| MilvusVectorStore | RAG 检索 | travel_documents |

---

### 常见问题

#### 1. 缓存未命中率高

```python
# 检查缓存配置
stats = cache.get_stats()
print(f"命中率: {stats.hit_rate}")
print(f"缓存大小: {stats.size}")

# 调整 TTL 或相似度阈值
config = CacheConfig(ttl=7200, enable_similarity=True)
```

#### 2. 限流过于严格

```python
# 调整限流配置
config = RateLimitConfig(
    max_requests=200,      # 增加请求数
    window_seconds=60,     # 扩大时间窗口
    burst_factor=2.0       # 增加突发因子
)
```

#### 3. Milvus 集合加载失败

```python
# 检查集合状态
store = await create_user_preference_store()
status = await store.get_collection_status()
print(status)

# 手动加载集合
await store.load_collection()
```
