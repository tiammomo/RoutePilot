"""
================================================================================
基础设施层 - Redis 消息队列 (Redis Message Queue)

提供基于 Redis 的消息队列支持，支持发布/订阅、任务队列、延迟队列等功能。

功能特点:
- 发布/订阅模式
- 任务队列
- 延迟队列
- 消息确认
- 分布式锁

使用示例:
```python
from infrastructure.redis_queue import RedisQueue, QueueType

# 创建任务队列
queue = RedisQueue("task_queue")
await queue.enqueue({"task": "process", "data": {...}})

# 创建发布/订阅
pubsub = await queue.subscribe("channel_name")
```

================================================================================
"""

import asyncio
import json
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable, List, AsyncGenerator
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio.client import PubSub

logger = logging.getLogger(__name__)


class QueueType(Enum):
    """队列类型"""
    FIFO = "fifo"           # 先进先出
    LIFO = "lifo"           # 后进先出
    PRIORITY = "priority"   # 优先级队列
    DELAYED = "delayed"     # 延迟队列


@dataclass
class QueueMessage:
    """队列消息"""
    id: str
    payload: Dict[str, Any]
    queue_type: QueueType = QueueType.FIFO
    priority: int = 0       # 优先级，数值越大优先级越高
    delay_seconds: int = 0   # 延迟秒数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    attempts: int = 0       # 处理尝试次数
    max_attempts: int = 3    # 最大尝试次数

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "payload": self.payload,
            "queue_type": self.queue_type.value,
            "priority": self.priority,
            "delay_seconds": self.delay_seconds,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts
        })

    @classmethod
    def from_json(cls, data: str) -> 'QueueMessage':
        obj = json.loads(data)
        return cls(
            id=obj["id"],
            payload=obj["payload"],
            queue_type=QueueType(obj["queue_type"]),
            priority=obj.get("priority", 0),
            delay_seconds=obj.get("delay_seconds", 0),
            created_at=obj.get("created_at", datetime.now().isoformat()),
            attempts=obj.get("attempts", 0),
            max_attempts=obj.get("max_attempts", 3)
        )


@dataclass
class RedisConfig:
    """Redis 配置"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 50,
        decode_responses: bool = True,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.max_connections = max_connections
        self.decode_responses = decode_responses
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout


class RedisQueue:
    """
    Redis 消息队列

    提供基于 Redis 的多种队列模式支持。
    """

    def __init__(
        self,
        queue_name: str,
        config: Optional[RedisConfig] = None,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        初始化消息队列

        Args:
            queue_name: 队列名称
            config: Redis 配置
            redis_client: 已连接的 Redis 客户端
        """
        self.queue_name = queue_name
        self.config = config or RedisConfig()
        self._client: Optional[redis.Redis] = redis_client
        self._pubsub: Optional[PubSub] = None
        self._id_counter = 0

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                decode_responses=self.config.decode_responses,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout
            )
        return self._client

    async def close(self) -> None:
        """关闭连接"""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._client:
            await self._client.close()
            self._client = None

    async def enqueue(
        self,
        payload: Dict[str, Any],
        queue_type: QueueType = QueueType.FIFO,
        priority: int = 0,
        delay_seconds: int = 0
    ) -> str:
        """
        入队消息

        Args:
            payload: 消息内容
            queue_type: 队列类型
            priority: 优先级
            delay_seconds: 延迟秒数

        Returns:
            str: 消息 ID
        """
        import uuid
        self._id_counter += 1
        msg_id = f"{uuid.uuid4().hex[:8]}:{self._id_counter}"

        message = QueueMessage(
            id=msg_id,
            payload=payload,
            queue_type=queue_type,
            priority=priority,
            delay_seconds=delay_seconds
        )

        if queue_type == QueueType.DELAYED and delay_seconds > 0:
            # 延迟队列：先存入有序集合
            execute_at = time.time() + delay_seconds
            await self.client.zadd(
                f"{self.queue_name}:delayed",
                {message.to_json(): execute_at}
            )
        elif queue_type == QueueType.PRIORITY:
            # 优先级队列：使用有序集合
            # 分数 = -优先级（降序），时间戳（升序）
            score = -(priority * 1000000) + time.time()
            await self.client.zadd(
                f"{self.queue_name}:priority",
                {message.to_json(): score}
            )
        else:
            # 普通队列
            if queue_type == QueueType.LIFO:
                # 后进先出：使用 LPUSH
                await self.client.lpush(self.queue_name, message.to_json())
            else:
                # 先进先出：使用 RPUSH
                await self.client.rpush(self.queue_name, message.to_json())

        logger.info(f"[RedisQueue] 消息入队: {msg_id}")
        return msg_id

    async def dequeue(self, timeout: int = 0) -> Optional[QueueMessage]:
        """
        出队消息

        Args:
            timeout: 等待超时秒数，0 表示立即返回

        Returns:
            Optional[QueueMessage]: 消息，不存在返回 None
        """
        # 优先检查延迟队列
        now = time.time()
        delayed_messages = await self.client.zrange(
            f"{self.queue_name}:delayed",
            0,
            0,
            withscores=True
        )

        if delayed_messages:
            msg_json, execute_at = delayed_messages[0]
            if execute_at <= now:
                await self.client.zrem(
                    f"{self.queue_name}:delayed",
                    msg_json
                )
                message = QueueMessage.from_json(msg_json)
                message.queue_type = QueueType.FIFO  # 转换为普通消息
                return message

        # 检查优先级队列
        priority_messages = await self.client.zrange(
            f"{self.queue_name}:priority",
            0,
            0
        )
        if priority_messages:
            msg_json = priority_messages[0]
            await self.client.zrem(f"{self.queue_name}:priority", msg_json)
            return QueueMessage.from_json(msg_json)

        # 检查普通队列
        if timeout > 0:
            # BRPOP / BLPOP
            result = await self.client.blpop(self.queue_name, timeout=timeout)
            if result:
                _, msg_json = result
                return QueueMessage.from_json(msg_json)
        else:
            # RPOP / LPOP
            msg_json = await self.client.lpop(self.queue_name)
            if msg_json:
                return QueueMessage.from_json(msg_json)

        return None

    async def acknowledge(self, message: QueueMessage) -> bool:
        """
        确认消息处理成功

        Args:
            message: 已处理的消息

        Returns:
            bool: 是否成功
        """
        logger.info(f"[RedisQueue] 消息确认: {message.id}")
        return True

    async def retry(self, message: QueueMessage) -> bool:
        """
        重试消息

        Args:
            message: 消息

        Returns:
            bool: 是否成功重试
        """
        message.attempts += 1
        if message.attempts >= message.max_attempts:
            logger.warning(f"[RedisQueue] 消息重试次数超限: {message.id}")
            return False

        # 重新入队，添加延迟
        await self.enqueue(
            payload=message.payload,
            queue_type=QueueType.DELAYED,
            priority=message.priority,
            delay_seconds=2 ** message.attempts  # 指数退避
        )
        logger.info(f"[RedisQueue] 消息重试: {message.id}, 尝试次数: {message.attempts}")
        return True

    async def get_length(self) -> int:
        """获取队列长度"""
        return await self.client.llen(self.queue_name)

    async def clear(self) -> int:
        """清空队列"""
        count = await self.get_length()
        await self.client.delete(self.queue_name)
        logger.info(f"[RedisQueue] 清空队列: {count} 条消息")
        return count

    async def subscribe(self, channel: str) -> PubSub:
        """
        订阅频道

        Args:
            channel: 频道名称

        Returns:
            PubSub: 发布/订阅对象
        """
        self._pubsub = self.client.pubsub()
        await self._pubsub.subscribe(channel)
        logger.info(f"[RedisQueue] 订阅频道: {channel}")
        return self._pubsub

    async def publish(self, channel: str, message: Any) -> int:
        """
        发布消息

        Args:
            channel: 频道名称
            message: 消息内容

        Returns:
            int: 接收者数量
        """
        if isinstance(message, dict):
            message = json.dumps(message)
        result = await self.client.publish(channel, message)
        logger.info(f"[RedisQueue] 发布消息到 {channel}: {result} 个接收者")
        return result

    async def listen(self, pubsub: PubSub) -> AsyncGenerator[Any, None]:
        """
        监听消息

        Args:
            pubsub: 发布/订阅对象

        Yields:
            Any: 消息
        """
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    yield message["data"]


class DistributedLock:
    """
    分布式锁

    基于 Redis 的分布式锁实现。
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        lock_name: str,
        timeout_seconds: int = 30,
        retry_interval: float = 0.1,
        max_retries: int = 100
    ):
        """
        初始化分布式锁

        Args:
            redis_client: Redis 客户端
            lock_name: 锁名称
            timeout_seconds: 锁超时时间
            retry_interval: 重试间隔
            max_retries: 最大重试次数
        """
        self.client = redis_client
        self.lock_name = f"lock:{lock_name}"
        self.timeout = timeout_seconds
        self.retry_interval = retry_interval
        self.max_retries = max_retries
        self.lock_value: Optional[str] = None

    async def acquire(self, blocking: bool = True) -> bool:
        """
        获取锁

        Args:
            blocking: 是否阻塞等待

        Returns:
            bool: 是否获取成功
        """
        import uuid
        self.lock_value = f"{uuid.uuid4().hex}:{time.time()}"

        retries = 0
        while True:
            # NX: 不存在时设置, EX: 超时时间
            success = await self.client.set(
                self.lock_name,
                self.lock_value,
                nx=True,
                ex=self.timeout
            )

            if success:
                logger.info(f"[DistributedLock] 获取锁成功: {self.lock_name}")
                return True

            if not blocking or retries >= self.max_retries:
                logger.warning(f"[DistributedLock] 获取锁失败: {self.lock_name}")
                return False

            retries += 1
            await asyncio.sleep(self.retry_interval)

    async def release(self) -> bool:
        """
        释放锁

        Returns:
            bool: 是否成功释放
        """
        if not self.lock_value:
            return False

        # 使用 Lua 脚本确保原子性
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self.client.eval(script, 1, self.lock_name, self.lock_value)
        self.lock_value = None

        if result:
            logger.info(f"[DistributedLock] 释放锁成功: {self.lock_name}")
        else:
            logger.warning(f"[DistributedLock] 释放锁失败: {self.lock_name}")

        return bool(result)

    async def extend(self, additional_seconds: int = 30) -> bool:
        """
        延长锁时间

        Args:
            additional_seconds: 延长时间

        Returns:
            bool: 是否成功
        """
        if not self.lock_value:
            return False

        # 检查锁是否还存在且属于当前持有者
        current_value = await self.client.get(self.lock_name)
        if current_value != self.lock_value:
            return False

        await self.client.expire(self.lock_name, additional_seconds)
        logger.info(f"[DistributedLock] 延长锁时间: {additional_seconds}秒")
        return True

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


# 便捷函数
def create_redis_queue(
    queue_name: str,
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None
) -> RedisQueue:
    """
    创建 Redis 消息队列

    Args:
        queue_name: 队列名称
        host: Redis 主机
        port: Redis 端口
        db: 数据库编号
        password: 密码

    Returns:
        RedisQueue: 消息队列实例
    """
    config = RedisConfig(host=host, port=port, db=db, password=password)
    return RedisQueue(queue_name, config=config)


def create_distributed_lock(
    redis_client: redis.Redis,
    lock_name: str,
    timeout_seconds: int = 30
) -> DistributedLock:
    """
    创建分布式锁

    Args:
        redis_client: Redis 客户端
        lock_name: 锁名称
        timeout_seconds: 超时时间

    Returns:
        DistributedLock: 分布式锁实例
    """
    return DistributedLock(redis_client, lock_name, timeout_seconds)
