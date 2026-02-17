"""
================================================================================
Multi-Agent Orchestration Framework

多 Agent 编排框架，提供多 Agent 协作能力。
================================================================================

模块结构：
- orchestrator.py: 核心协调器
- agent_factory.py: Agent 工厂
- message_bus.py: 消息总线
- protocols/: 通信协议
- roles/: 角色 Agent
- collaboration/: 协作组件
"""

from multiagent.orchestrator import (
    MultiAgentOrchestrator,
    MultiAgentResult,
    OrchestratorConfig
)
from multiagent.agent_factory import (
    AgentFactory,
    AgentType,
    AgentConfig,
    AgentInstance
)
from multiagent.message_bus import (
    MessageBus,
    BusMode
)
from multiagent.protocols.communication import (
    AgentMessage,
    MessageType,
    MessagePriority
)

__version__ = "2.4.0"

__all__ = [
    # Orchestrator
    "MultiAgentOrchestrator",
    "MultiAgentResult",
    "OrchestratorConfig",
    # Agent Factory
    "AgentFactory",
    "AgentType",
    "AgentConfig",
    "AgentInstance",
    # Message Bus
    "MessageBus",
    "BusMode",
    "AgentMessage",
    "MessageType",
    "MessagePriority",
    # Protocols
    "TaskMessage",
    "NegotiationProposal",
    "NegotiationState",
    "ResourceRequest",
    "ResourceAllocation",
    # Roles
    "PlannerAgent",
    "SpecialistAgent",
    "SupervisorAgent",
    # Collaboration
    "TaskDistributor",
    "ResultMerger",
    "MergedResult"
]

# 协议导出
from multiagent.protocols import (
    TaskMessage,
    NegotiationProposal,
    NegotiationState,
    ResourceRequest,
    ResourceAllocation
)

# 角色导出
from multiagent.roles import (
    PlannerAgent,
    ExecutionPlan,
    SubTask,
    PlanComplexity,
    SpecialistAgent,
    TaskResult,
    TaskStatus,
    SupervisorAgent,
    ReviewResult,
    ReviewStatus,
    QualityMetrics
)

# 协作组件导出
from multiagent.collaboration import (
    TaskDistributor,
    TaskAssignment,
    ResultMerger,
    MergedResult
)
