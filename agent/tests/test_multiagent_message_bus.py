"""
MessageBus 单元测试
"""

import pytest
import asyncio
from multiagent.message_bus import MessageBus, BusMode
from multiagent.protocols.communication import AgentMessage, MessageType, MessagePriority


class TestMessageBus:
    """消息总线测试"""

    def test_initialization(self):
        """测试初始化"""
        bus = MessageBus(mode=BusMode.ASYNC)
        assert bus.mode == BusMode.ASYNC
        assert len(bus._registered_agents) == 0

    def test_register_agent(self):
        """测试注册 Agent"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        assert "agent_1" in bus._registered_agents

    def test_unregister_agent(self):
        """测试注销 Agent"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        bus.unregister_agent("agent_1")
        assert "agent_1" not in bus._registered_agents

    def test_subscribe(self):
        """测试订阅"""
        bus = MessageBus()

        def callback(msg):
            pass

        bus.subscribe("agent_1", callback)
        assert "agent_1" in bus._subscribers

    @pytest.mark.asyncio
    async def test_send_message(self):
        """测试发送消息"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")

        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={"test": "data"}
        )

        result = await bus.send(msg)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_unregistered(self):
        """测试发送到未注册的 Agent"""
        bus = MessageBus()
        bus.register_agent("agent_1")

        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={}
        )

        result = await bus.send(msg)
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """测试广播"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")
        bus.register_agent("agent_3")

        msg = AgentMessage(
            sender="agent_1",
            receiver="broadcast",
            message_type=MessageType.REQUEST,
            content={"test": "broadcast"}
        )

        count = await bus.broadcast(msg)
        assert count == 2  # agent_1 不接收自己的广播

    @pytest.mark.asyncio
    async def test_receive_message(self):
        """测试接收消息"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")

        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={"test": "data"}
        )

        await bus.send(msg)
        received = await bus.receive("agent_2")

        assert received is not None
        assert received.sender == "agent_1"
        assert received.content["test"] == "data"

    @pytest.mark.asyncio
    async def test_get_pending_messages(self):
        """测试获取待处理消息"""
        bus = MessageBus()
        bus.register_agent("agent_1")
        bus.register_agent("agent_2")

        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={}
        )

        await bus.send(msg)
        pending = bus.get_pending_messages("agent_2")

        assert len(pending) >= 1

    def test_get_stats(self):
        """测试获取统计信息"""
        bus = MessageBus()
        bus.register_agent("agent_1")

        stats = bus.get_stats()
        assert "sent" in stats
        assert "registered_agents" in stats
        assert stats["registered_agents"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
