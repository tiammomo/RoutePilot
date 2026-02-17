"""
================================================================================
多 Agent 协商协议

定义 Agent 间协商相关的消息类型和协议。
================================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NegotiationState(Enum):
    """协商状态"""
    PROPOSED = "proposed"       # 已提议
    ACCEPTED = "accepted"       # 已接受
    REJECTED = "rejected"       # 已拒绝
    COUNTERED = "countered"     # 已还价
    WITHDRAWN = "withdrawn"     # 已撤回
    EXPIRED = "expired"         # 已过期


@dataclass
class NegotiationProposal:
    """协商提议"""

    proposal_id: str
    proposer: str               # 提议者
    receiver: str               # 接收者
    proposal_type: str          # 提议类型 (task_sharing, resource_allocation, etc.)
    content: Dict[str, Any]     # 提议内容
    state: NegotiationState = NegotiationState.PROPOSED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def accept(self) -> 'NegotiationProposal':
        """接受提议"""
        self.state = NegotiationState.ACCEPTED
        self.metadata["accepted_at"] = datetime.now().isoformat()
        return self

    def reject(self, reason: str = "") -> 'NegotiationProposal':
        """拒绝提议"""
        self.state = NegotiationState.REJECTED
        self.metadata["reject_reason"] = reason
        return self

    def counter(self, new_content: Dict[str, Any]) -> 'NegotiationProposal':
        """还价"""
        self.state = NegotiationState.COUNTERED
        self.metadata["counter_proposal"] = new_content
        return self


@dataclass
class ResourceRequest:
    """资源请求"""

    request_id: str
    requester: str              # 请求者
    resource_type: str          # 资源类型 (cpu, memory, time, etc.)
    amount: float               # 数量
    priority: int = 1           # 优先级
    deadline: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceAllocation:
    """资源分配"""

    allocation_id: str
    resource_type: str
    allocated_to: str            # 分配给
    amount: float
    allocated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
