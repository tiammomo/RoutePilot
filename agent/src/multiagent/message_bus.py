"""
================================================================================
Message Bus - 消息总线

支持 Agent 间消息的发布/订阅、点对点发送、广播等功能。
================================================================================
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

from multiagent.protocols.communication import AgentMessage, MessageType

logger = logging.getLogger(__name__)


class BusMode(Enum):
    """消息总线模式"""
    SYNC = "sync"           # 同步模式
    ASYNC = "async"         # 异步模式


@dataclass
class Subscription:
    """订阅信息"""
    agent_id: str
    callback: Callable
    message_types: Optional[Set[MessageType]] = None  # None 表示接收所有类型
    filters: Optional[Callable[[AgentMessage], bool]] = None  # 自定义过滤器


@dataclass
class MessageEnvelope:
    """消息包装"""
    message: AgentMessage
    delivered: bool = False
    delivered_at: Optional[str] = None
    retry_count: int = 0


class MessageBus:
    """消息总线

    支持：
    - 点对点消息发送
    - 发布/订阅模式
    - 消息广播
    - 消息持久化（可选）
    - 消息过滤
    """

    def __init__(self, mode: BusMode = BusMode.ASYNC, enable_persistence: bool = False):
        """
        Args:
            mode: 总线模式
            enable_persistence: 是否启用消息持久化
        """
        self.mode = mode
        self.enable_persistence = enable_persistence

        # 订阅者: agent_id -> List[Subscription]
        self._subscribers: Dict[str, List[Subscription]] = defaultdict(list)

        # 消息队列: agent_id -> List[MessageEnvelope]
        self._message_queues: Dict[str, List[MessageEnvelope]] = defaultdict(list)

        # 已注册 Agent
        self._registered_agents: Set[str] = set()

        # 消息历史
        self._message_history: List[MessageEnvelope] = []
        self._max_history_size = 1000

        # 消息回调
        self._delivery_callbacks: List[Callable] = []

        # 消息统计
        self._stats = {
            "sent": 0,
            "delivered": 0,
            "broadcast": 0,
            "dropped": 0
        }

    def register_agent(self, agent_id: str) -> None:
        """注册 Agent"""
        self._registered_agents.add(agent_id)
        logger.info(f"Agent {agent_id} registered to message bus")

    def unregister_agent(self, agent_id: str) -> None:
        """注销 Agent"""
        self._registered_agents.discard(agent_id)
        if agent_id in self._subscribers:
            del self._subscribers[agent_id]
        if agent_id in self._message_queues:
            del self._message_queues[agent_id]
        logger.info(f"Agent {agent_id} unregistered from message bus")

    def subscribe(
        self,
        agent_id: str,
        callback: Callable,
        message_types: Optional[Set[MessageType]] = None,
        filters: Optional[Callable[[AgentMessage], bool]] = None
    ) -> None:
        """订阅消息

        Args:
            agent_id: 订阅者 ID
            callback: 回调函数
            message_types: 感兴趣的消息类型（None 表示所有）
            filters: 自定义过滤器
        """
        subscription = Subscription(
            agent_id=agent_id,
            callback=callback,
            message_types=message_types,
            filters=filters
        )
        self._subscribers[agent_id].append(subscription)
        logger.debug(f"Agent {agent_id} subscribed to message bus")

    def unsubscribe(self, agent_id: str) -> None:
        """取消订阅"""
        if agent_id in self._subscribers:
            del self._subscribers[agent_id]

    async def send(self, message: AgentMessage) -> bool:
        """发送消息（点对点）

        Args:
            message: 消息

        Returns:
            是否发送成功
        """
        if message.receiver not in self._registered_agents:
            logger.warning(f"Receiver {message.receiver} not registered")
            self._stats["dropped"] += 1
            return False

        # 包装消息
        envelope = MessageEnvelope(message=message)

        # 添加到接收者队列
        self._message_queues[message.receiver].append(envelope)

        # 尝试立即投递
        await self._deliver_to_agent(message.receiver, envelope)

        self._stats["sent"] += 1
        self._add_to_history(envelope)

        logger.debug(f"Message {message.correlation_id} sent from {message.sender} to {message.receiver}")
        return True

    async def broadcast(self, message: AgentMessage) -> int:
        """广播消息

        Args:
            message: 消息

        Returns:
            成功发送的数量
        """
        sent_count = 0
        message.receiver = "broadcast"

        for agent_id in self._registered_agents:
            if agent_id == message.sender:
                continue  # 不发送给自己

            envelope = MessageEnvelope(message=AgentMessage(
                sender=message.sender,
                receiver=agent_id,
                message_type=message.message_type,
                content=message.content,
                correlation_id=message.correlation_id,
                priority=message.priority,
                metadata=message.metadata
            ))

            self._message_queues[agent_id].append(envelope)
            await self._deliver_to_agent(agent_id, envelope)
            sent_count += 1

        self._stats["broadcast"] += sent_count
        logger.info(f"Broadcast from {message.sender} to {sent_count} agents")
        return sent_count

    async def _deliver_to_agent(self, agent_id: str, envelope: MessageEnvelope) -> None:
        """投递消息到 Agent"""
        subscriptions = self._subscribers.get(agent_id, [])

        for sub in subscriptions:
            # 检查消息类型过滤
            if sub.message_types and envelope.message.message_type not in sub.message_types:
                continue

            # 检查自定义过滤器
            if sub.filters and not sub.filters(envelope.message):
                continue

            # 调用回调
            try:
                if asyncio.iscoroutinefunction(sub.callback):
                    await sub.callback(envelope.message)
                else:
                    sub.callback(envelope.message)

                envelope.delivered = True
                envelope.delivered_at = datetime.now().isoformat()
                self._stats["delivered"] += 1
            except Exception as e:
                logger.error(f"Error delivering message to {agent_id}: {e}")

    async def receive(self, agent_id: str, timeout: float = 0) -> Optional[AgentMessage]:
        """接收消息

        Args:
            agent_id: 接收者 ID
            timeout: 超时时间（秒），0 表示立即返回

        Returns:
            消息，如果没有则返回 None
        """
        queue = self._message_queues.get(agent_id, [])

        if not queue:
            return None

        if timeout > 0:
            await asyncio.sleep(timeout)

        if queue:
            envelope = queue.pop(0)
            return envelope.message

        return None

    def get_pending_messages(self, agent_id: str) -> List[AgentMessage]:
        """获取待处理消息"""
        queue = self._message_queues.get(agent_id, [])
        return [envelope.message for envelope in queue if not envelope.delivered]

    def get_stats(self) -> Dict[str, Any]:
        """获取消息统计"""
        return {
            **self._stats,
            "registered_agents": len(self._registered_agents),
            "pending_messages": sum(len(q) for q in self._message_queues.values())
        }

    def _add_to_history(self, envelope: MessageEnvelope) -> None:
        """添加到历史记录"""
        self._message_history.append(envelope)
        if len(self._message_history) > self._max_history_size:
            self._message_history.pop(0)

    def get_history(self, limit: int = 100) -> List[AgentMessage]:
        """获取消息历史"""
        return [envelope.message for envelope in self._message_history[-limit:]]
