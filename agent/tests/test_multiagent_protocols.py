"""
Multi-Agent 系统单元测试
"""

import pytest
from multiagent.protocols.communication import (
    AgentMessage,
    MessageType,
    MessagePriority,
    TaskMessage
)
from multiagent.protocols.negotiation import (
    NegotiationProposal,
    NegotiationState,
    ResourceRequest,
    ResourceAllocation
)


class TestAgentMessage:
    """Agent 消息测试"""

    def test_message_creation(self):
        """测试消息创建"""
        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={"action": "search", "query": "北京"}
        )
        assert msg.sender == "agent_1"
        assert msg.receiver == "agent_2"
        assert msg.message_type == MessageType.REQUEST

    def test_message_serialization(self):
        """测试消息序列化"""
        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={"key": "value"}
        )
        d = msg.to_dict()
        assert d["sender"] == "agent_1"
        assert d["message_type"] == "request"

    def test_message_deserialization(self):
        """测试消息反序列化"""
        data = {
            "sender": "agent_1",
            "receiver": "agent_2",
            "message_type": "response",
            "content": {"result": "ok"},
            "correlation_id": "corr-123",
            "timestamp": "2024-01-01T00:00:00",
            "priority": 1,
            "metadata": {}
        }
        msg = AgentMessage.from_dict(data)
        assert msg.sender == "agent_1"
        assert msg.message_type == MessageType.RESPONSE

    def test_create_response(self):
        """测试创建响应消息"""
        msg = AgentMessage(
            sender="agent_1",
            receiver="agent_2",
            message_type=MessageType.REQUEST,
            content={"action": "test"}
        )
        response = msg.create_response({"status": "ok"})
        assert response.sender == "agent_2"
        assert response.receiver == "agent_1"
        assert response.message_type == MessageType.RESPONSE
        assert response.correlation_id == msg.correlation_id


class TestTaskMessage:
    """任务消息测试"""

    def test_task_message_creation(self):
        """测试任务消息创建"""
        task = TaskMessage(
            task_id="task-1",
            task_type="search",
            task_data={"city": "北京"}
        )
        assert task.task_id == "task-1"
        assert task.status == "pending"

    def test_task_message_serialization(self):
        """测试任务消息序列化"""
        task = TaskMessage(
            task_id="task-1",
            task_type="search",
            task_data={"city": "北京"}
        )
        d = task.to_dict()
        assert d["task_id"] == "task-1"
        assert d["status"] == "pending"


class TestNegotiationProposal:
    """协商提议测试"""

    def test_proposal_creation(self):
        """测试提议创建"""
        proposal = NegotiationProposal(
            proposal_id="prop-1",
            proposer="agent_1",
            receiver="agent_2",
            proposal_type="task_sharing",
            content={"task_id": "task-1"}
        )
        assert proposal.state == NegotiationState.PROPOSED

    def test_proposal_accept(self):
        """测试接受提议"""
        proposal = NegotiationProposal(
            proposal_id="prop-1",
            proposer="agent_1",
            receiver="agent_2",
            proposal_type="task_sharing",
            content={}
        )
        proposal.accept()
        assert proposal.state == NegotiationState.ACCEPTED

    def test_proposal_reject(self):
        """测试拒绝提议"""
        proposal = NegotiationProposal(
            proposal_id="prop-1",
            proposer="agent_1",
            receiver="agent_2",
            proposal_type="task_sharing",
            content={}
        )
        proposal.reject("not enough resources")
        assert proposal.state == NegotiationState.REJECTED
        assert proposal.metadata["reject_reason"] == "not enough resources"


class TestResourceRequest:
    """资源请求测试"""

    def test_resource_request_creation(self):
        """测试资源请求创建"""
        request = ResourceRequest(
            request_id="req-1",
            requester="agent_1",
            resource_type="cpu",
            amount=0.5,
            priority=2
        )
        assert request.request_id == "req-1"
        assert request.amount == 0.5
        assert request.priority == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
