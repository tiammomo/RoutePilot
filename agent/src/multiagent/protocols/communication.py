"""
================================================================================
Multi-Agent 通信协议

定义 Agent 间消息格式和消息类型。
================================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"           # 请求
    RESPONSE = "response"         # 响应
    TASK_ASSIGN = "task_assign"   # 任务分配
    TASK_COMPLETE = "task_complete" # 任务完成
    PROGRESS = "progress"         # 进度更新
    ERROR = "error"               # 错误通知
    APPROVAL = "approval"         # 审批请求
    HEARTBEAT = "heartbeat"       # 心跳


class MessagePriority(Enum):
    """消息优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class AgentMessage:
    """Agent 间消息"""

    sender: str                    # 发送者 ID
    receiver: str                   # 接收者 ID (可以是 "broadcast" 表示广播)
    message_type: MessageType       # 消息类型
    content: Any                    # 消息内容
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 关联 ID
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())  # 时间戳
    priority: MessagePriority = MessagePriority.NORMAL  # 优先级
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "sender": self.sender,
            "receiver": self.receiver,
            "message_type": self.message_type.value,
            "content": self.content,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """从字典反序列化"""
        return cls(
            sender=data["sender"],
            receiver=data["receiver"],
            message_type=MessageType(data["message_type"]),
            content=data["content"],
            correlation_id=data.get("correlation_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            priority=MessagePriority(data.get("priority", MessagePriority.NORMAL.value)),
            metadata=data.get("metadata", {})
        )

    def create_response(self, content: Any) -> 'AgentMessage':
        """创建响应消息"""
        return AgentMessage(
            sender=self.receiver,
            receiver=self.sender,
            message_type=MessageType.RESPONSE,
            content=content,
            correlation_id=self.correlation_id,
            priority=self.priority
        )


@dataclass
class TaskMessage:
    """任务相关消息"""

    task_id: str                    # 任务 ID
    task_type: str                  # 任务类型
    task_data: Dict[str, Any]       # 任务数据
    assigned_agent: Optional[str] = None  # 分配的 Agent
    status: str = "pending"         # 状态
    result: Optional[Any] = None     # 执行结果
    error: Optional[str] = None      # 错误信息
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_data": self.task_data,
            "assigned_agent": self.assigned_agent,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
