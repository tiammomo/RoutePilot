"""
================================================================================
实时消息推送模块 (Real-time Message Pusher)

提供基于 Redis Pub/Sub 的实时消息推送功能，支持：
- 用户通知推送
- 旅行更新推送
- 系统事件广播
- WebSocket 集成

使用示例:
```python
from infrastructure.realtime_pusher import (
    RealtimePusher, EventType, PushPriority,
    create_realtime_pusher
)

# 创建推送器
pusher = await create_realtime_pusher()

# 推送用户通知
await pusher.push_user_notification(
    user_id="user123",
    title="旅行提醒",
    message="您的航班即将起飞",
    data={"flight_id": "CA1234"}
)

# 推送旅行更新
await pusher.push_travel_update(
    user_id="user123",
    update_type="price_drop",
    message="目的地价格下降",
    data={"old_price": 1000, "new_price": 800}
)

# 订阅用户消息
async for msg in pusher.subscribe_user("user123"):
    print(f"收到消息: {msg}")
```

================================================================================
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set
import redis.asyncio as redis
from redis.asyncio.client import PubSub

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""
    # 用户通知
    USER_NOTIFICATION = "user.notification"
    USER_MESSAGE = "user.message"

    # 旅行相关
    TRAVEL_REMINDER = "travel.reminder"
    TRAVEL_UPDATE = "travel.update"
    TRAVEL_ALERT = "travel.alert"
    PRICE_CHANGE = "travel.price_change"
    WEATHER_ALERT = "travel.weather"

    # 系统事件
    SYSTEM_ANNOUNCEMENT = "system.announcement"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # 聊天相关
    CHAT_NEW_MESSAGE = "chat.new_message"
    CHAT_TYPING = "chat.typing"
    CHAT_READY = "chat.ready"


class PushPriority(Enum):
    """推送优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class PushMessage:
    """推送消息"""
    id: str
    event_type: EventType
    title: str
    message: str
    priority: PushPriority = PushPriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 3600  # 1小时过期

    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "event_type": self.event_type.value,
            "title": self.title,
            "message": self.message,
            "priority": self.priority.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "ttl": self.ttl
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> 'PushMessage':
        obj = json.loads(data)
        return cls(
            id=obj["id"],
            event_type=EventType(obj["event_type"]),
            title=obj["title"],
            message=obj["message"],
            priority=PushPriority(obj["priority"]),
            data=obj.get("data", {}),
            timestamp=obj.get("timestamp", time.time()),
            ttl=obj.get("ttl", 3600)
        )


@dataclass
class RealtimeConfig:
    """实时推送配置"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    key_prefix: str = "realtime:"
    # 频道前缀
    user_channel_prefix: str = "user:"
    global_channel_prefix: str = "global:"
    # 默认 TTL
    default_ttl: int = 3600
    # 最大重试次数
    max_retries: int = 3


class RealtimePusher:
    """
    实时消息推送器

    基于 Redis Pub/Sub 实现实时消息推送，支持：
    - 单用户推送
    - 全局广播
    - 事件订阅
    - 消息持久化
    """

    def __init__(
        self,
        config: Optional[RealtimeConfig] = None,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        初始化推送器

        Args:
            config: 配置
            redis_client: 已连接的 Redis 客户端
        """
        self.config = config or RealtimeConfig()
        self._client: Optional[redis.Redis] = redis_client
        self._pubsub: Optional[PubSub] = None
        self._subscriptions: Dict[str, Set[str]] = {}  # identifier -> channels
        self._message_handlers: Dict[EventType, List[Callable]] = {}

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
        return self._client

    def _get_user_channel(self, user_id: str) -> str:
        """获取用户频道"""
        return f"{self.config.key_prefix}{self.config.user_channel_prefix}{user_id}"

    def _get_global_channel(self, event_type: str) -> str:
        """获取全局频道"""
        return f"{self.config.key_prefix}{self.config.global_channel_prefix}{event_type}"

    def _get_event_channel(self, event_type: EventType) -> str:
        """获取事件类型频道"""
        return f"{self.config.key_prefix}event:{event_type.value}"

    async def push_user_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        priority: PushPriority = PushPriority.NORMAL,
        data: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None
    ) -> str:
        """
        推送用户通知

        Args:
            user_id: 用户 ID
            title: 标题
            message: 内容
            priority: 优先级
            data: 附加数据
            ttl: 过期时间

        Returns:
            str: 消息 ID
        """
        import hashlib

        # 生成消息 ID
        msg_id = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:12]

        # 创建消息
        push_msg = PushMessage(
            id=msg_id,
            event_type=EventType.USER_NOTIFICATION,
            title=title,
            message=message,
            priority=priority,
            data=data or {},
            ttl=ttl or self.config.default_ttl
        )

        # 发布到用户频道
        channel = self._get_user_channel(user_id)
        await self.client.publish(channel, push_msg.to_json())

        # 持久化到列表（用于离线消息）
        list_key = f"{self.config.key_prefix}notifications:{user_id}"
        await self.client.lpush(list_key, push_msg.to_json())
        await self.client.expire(list_key, push_msg.ttl)

        # 限制列表长度
        await self.client.ltrim(list_key, 0, 99)

        logger.info(f"[RealtimePusher] 推送通知给用户 {user_id}: {title}")
        return msg_id

    async def push_travel_update(
        self,
        user_id: str,
        update_type: str,
        message: str,
        priority: PushPriority = PushPriority.NORMAL,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        推送旅行更新

        Args:
            user_id: 用户 ID
            update_type: 更新类型 (price_drop, weather, reminder, etc.)
            message: 更新内容
            priority: 优先级
            data: 附加数据

        Returns:
            str: 消息 ID
        """
        import hashlib

        msg_id = hashlib.md5(f"{user_id}{update_type}{time.time()}".encode()).hexdigest()[:12]

        push_msg = PushMessage(
            id=msg_id,
            event_type=EventType.TRAVEL_UPDATE,
            title=f"旅行更新: {update_type}",
            message=message,
            priority=priority,
            data={
                "update_type": update_type,
                **(data or {})
            }
        )

        channel = self._get_user_channel(user_id)
        await self.client.publish(channel, push_msg.to_json())

        # 旅行更新持久化
        travel_key = f"{self.config.key_prefix}travel:{user_id}"
        await self.client.lpush(travel_key, push_msg.to_json())
        await self.client.expire(travel_key, 86400 * 7)  # 7天

        logger.info(f"[RealtimePusher] 推送旅行更新给 {user_id}: {update_type}")
        return msg_id

    async def push_price_alert(
        self,
        user_id: str,
        destination: str,
        old_price: float,
        new_price: float,
        currency: str = "CNY",
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        推送价格提醒

        Args:
            user_id: 用户 ID
            destination: 目的地
            old_price: 原价
            new_price: 新价
            currency: 货币
            data: 附加数据

        Returns:
            str: 消息 ID
        """
        price_change = ((old_price - new_price) / old_price * 100) if old_price > 0 else 0
        direction = "下降" if new_price < old_price else "上涨"

        return await self.push_travel_update(
            user_id=user_id,
            update_type="price_change",
            message=f"{destination}价格{direction}{price_change:.1f}% ({old_price}{currency} → {new_price}{currency})",
            priority=PushPriority.HIGH,
            data={
                "destination": destination,
                "old_price": old_price,
                "new_price": new_price,
                "currency": currency,
                "change_percent": price_change,
                "direction": direction,
                **(data or {})
            }
        )

    async def push_weather_alert(
        self,
        user_id: str,
        destination: str,
        weather_type: str,
        severity: str,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        推送天气预警

        Args:
            user_id: 用户 ID
            destination: 目的地
            weather_type: 天气类型
            severity: 严重程度 (info, warning, critical)
            message: 预警信息
            data: 附加数据

        Returns:
            str: 消息 ID
        """
        priority = PushPriority.URGENT if severity == "critical" else PushPriority.HIGH

        return await self.push_travel_update(
            user_id=user_id,
            update_type="weather_alert",
            message=f"{destination}: {message}",
            priority=priority,
            data={
                "destination": destination,
                "weather_type": weather_type,
                "severity": severity,
                **(data or {})
            }
        )

    async def broadcast_system_announcement(
        self,
        title: str,
        message: str,
        priority: PushPriority = PushPriority.NORMAL,
        target_users: Optional[List[str]] = None
    ) -> int:
        """
        广播系统公告

        Args:
            title: 标题
            message: 内容
            priority: 优先级
            target_users: 目标用户列表，None 表示全量广播

        Returns:
            int: 接收用户数
        """
        import hashlib

        msg_id = hashlib.md5(f"broadcast{time.time()}".encode()).hexdigest()[:12]

        push_msg = PushMessage(
            id=msg_id,
            event_type=EventType.SYSTEM_ANNOUNCEMENT,
            title=title,
            message=message,
            priority=priority
        )

        if target_users:
            # 指定用户推送
            count = 0
            for user_id in target_users:
                channel = self._get_user_channel(user_id)
                await self.client.publish(channel, push_msg.to_json())
                count += 1
            return count
        else:
            # 全局广播
            channel = self._get_global_channel("announcement")
            return await self.client.publish(channel, push_msg.to_json())

    async def subscribe_user(self, user_id: str) -> AsyncGenerator[PushMessage, None]:
        """
        订阅用户消息

        Args:
            user_id: 用户 ID

        Yields:
            PushMessage: 推送消息
        """
        pubsub = self.client.pubsub()
        channel = self._get_user_channel(user_id)
        await pubsub.subscribe(channel)

        self._subscriptions.setdefault(user_id, set()).add(channel)

        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    yield PushMessage.from_json(msg["data"])
                except Exception as e:
                    logger.error(f"[RealtimePusher] 解析消息失败: {e}")

    async def subscribe_events(
        self,
        event_types: List[EventType]
    ) -> AsyncGenerator[PushMessage, None]:
        """
        订阅事件类型

        Args:
            event_types: 事件类型列表

        Yields:
            PushMessage: 推送消息
        """
        pubsub = self.client.pubsub()

        for event_type in event_types:
            channel = self._get_event_channel(event_type)
            await pubsub.subscribe(channel)

        async for msg in pubsub.listen():
            if msg["type"] == "message":
                try:
                    yield PushMessage.from_json(msg["data"])
                except Exception as e:
                    logger.error(f"[RealtimePusher] 解析消息失败: {e}")

    async def get_user_notifications(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[PushMessage]:
        """
        获取用户通知历史

        Args:
            user_id: 用户 ID
            limit: 获取数量

        Returns:
            List[PushMessage]: 通知列表
        """
        list_key = f"{self.config.key_prefix}notifications:{user_id}"
        messages = await self.client.lrange(list_key, 0, limit - 1)

        return [PushMessage.from_json(msg) for msg in messages]

    async def get_travel_updates(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[PushMessage]:
        """
        获取用户旅行更新历史

        Args:
            user_id: 用户 ID
            limit: 获取数量

        Returns:
            List[PushMessage]: 更新列表
        """
        travel_key = f"{self.config.key_prefix}travel:{user_id}"
        messages = await self.client.lrange(travel_key, 0, limit - 1)

        return [PushMessage.from_json(msg) for msg in messages]

    async def mark_notification_read(
        self,
        user_id: str,
        message_id: str
    ) -> bool:
        """
        标记通知已读

        Args:
            user_id: 用户 ID
            message_id: 消息 ID

        Returns:
            bool: 是否成功
        """
        try:
            read_key = f"{self.config.key_prefix}read:{user_id}"
            await self.client.sadd(read_key, message_id)
            await self.client.expire(read_key, 86400 * 30)  # 30天
            return True
        except Exception as e:
            logger.error(f"[RealtimePusher] 标记已读失败: {e}")
            return False

    async def get_unread_count(self, user_id: str) -> int:
        """获取未读通知数"""
        try:
            list_key = f"{self.config.key_prefix}notifications:{user_id}"
            read_key = f"{self.config.key_prefix}read:{user_id}"

            # 获取所有通知
            notifications = await self.client.lrange(list_key, 0, -1)

            # 统计未读
            unread = 0
            for msg_json in notifications:
                try:
                    msg = PushMessage.from_json(msg_json)
                    is_read = await self.client.sismember(read_key, msg.id)
                    if not is_read:
                        unread += 1
                except Exception:
                    continue

            return unread
        except Exception as e:
            logger.error(f"[RealtimePusher] 获取未读数失败: {e}")
            return 0

    async def clear_user_notifications(self, user_id: str) -> bool:
        """清空用户通知"""
        try:
            await self.client.delete(
                f"{self.config.key_prefix}notifications:{user_id}",
                f"{self.config.key_prefix}travel:{user_id}",
                f"{self.config.key_prefix}read:{user_id}"
            )
            return True
        except Exception as e:
            logger.error(f"[RealtimePusher] 清空通知失败: {e}")
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._pubsub:
            await self._pubsub.close()
        if self._client:
            await self._client.close()
        logger.info("[RealtimePusher] 连接已关闭")


# =============================================================================
# WebSocket 集成
# =============================================================================

class WebSocketManager:
    """
    WebSocket 连接管理器

    管理 WebSocket 连接，与 Redis Pub/Sub 集成实现实时推送。
    """

    def __init__(self, pusher: Optional[RealtimePusher] = None):
        """
        初始化管理器

        Args:
            pusher: 实时推送器
        """
        self.pusher = pusher
        self._connections: Dict[str, Set[Any]] = {}  # user_id -> WebSocket connections
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None

    async def connect(self, user_id: str, websocket: Any) -> None:
        """
        建立 WebSocket 连接

        Args:
            user_id: 用户 ID
            websocket: WebSocket 连接
        """
        if user_id not in self._connections:
            self._connections[user_id] = set()

        self._connections[user_id].add(websocket)

        # 启动监听任务
        if not self._running:
            await self._start_listener()

        logger.info(f"[WebSocketManager] 用户 {user_id} 已连接")

    async def disconnect(self, user_id: str, websocket: Any) -> None:
        """断开 WebSocket 连接"""
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]

        logger.info(f"[WebSocketManager] 用户 {user_id} 已断开")

    async def send_personal_message(
        self,
        user_id: str,
        message: Dict[str, Any]
    ) -> int:
        """
        发送个人消息

        Args:
            user_id: 用户 ID
            message: 消息内容

        Returns:
            int: 发送的连接数
        """
        connections = self._connections.get(user_id, set())
        sent = 0

        for ws in connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as e:
                logger.error(f"[WebSocketManager] 发送消息失败: {e}")
                await self.disconnect(user_id, ws)

        return sent

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        广播消息

        Args:
            message: 消息内容

        Returns:
            int: 发送的连接数
        """
        sent = 0
        for user_id in self._connections:
            sent += await self.send_personal_message(user_id, message)
        return sent

    async def _start_listener(self) -> None:
        """启动消息监听任务"""
        if self._running:
            return

        self._running = True
        self._listener_task = asyncio.create_task(self._listen_messages())

    async def _listen_messages(self) -> None:
        """监听全局消息"""
        try:
            async for msg in self.pusher.subscribe_events([
                EventType.USER_NOTIFICATION,
                EventType.TRAVEL_UPDATE,
                EventType.SYSTEM_ANNOUNCEMENT
            ]):
                # 广播给所有在线用户
                await self.broadcast({
                    "type": msg.event_type.value,
                    "title": msg.title,
                    "message": msg.message,
                    "data": msg.data,
                    "timestamp": msg.timestamp
                })
        except asyncio.CancelledError:
            logger.info("[WebSocketManager] 监听任务已取消")
        except Exception as e:
            logger.error(f"[WebSocketManager] 监听错误: {e}")

    async def close(self) -> None:
        """关闭所有连接"""
        if self._listener_task:
            self._listener_task.cancel()

        for user_id, connections in self._connections.items():
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass

        self._connections.clear()
        logger.info("[WebSocketManager] 所有连接已关闭")


# =============================================================================
# 便捷函数
# =============================================================================

async def create_realtime_pusher(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None
) -> RealtimePusher:
    """
    创建实时推送器

    Args:
        host: Redis 主机
        port: Redis 端口
        db: 数据库编号
        password: 密码

    Returns:
        RealtimePusher: 推送器实例
    """
    config = RealtimeConfig(
        host=host,
        port=port,
        db=db,
        password=password
    )
    return RealtimePusher(config=config)


async def check_realtime_health() -> Dict[str, Any]:
    """
    检查实时推送服务健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        pusher = await create_realtime_pusher()
        await pusher.client.ping()
        await pusher.close()

        return {
            "status": "healthy",
            "service": "redis-pubsub"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
