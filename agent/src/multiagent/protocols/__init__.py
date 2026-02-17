"""
Multi-Agent Protocols

通信和协商协议定义。
"""

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

__all__ = [
    "AgentMessage",
    "MessageType",
    "MessagePriority",
    "TaskMessage",
    "NegotiationProposal",
    "NegotiationState",
    "ResourceRequest",
    "ResourceAllocation"
]
