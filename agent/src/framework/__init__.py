# Framework Layer - 框架层
#
# 提供 Agent 引擎抽象、工具链、状态管理等框架能力

from .node_types import (
    NodeCategory,
    NodeStatus,
    NodeResult,
    NodeConfig,
    BaseNode,
    ActionNode,
    AgentNode,
    LoopNode,
    DecisionNode,
    PreparationNode,
    PersistenceNode
)

from .state_manager import (
    StateManager,
    StateSnapshot,
    WorkflowStatus
)

__all__ = [
    # Node Types
    'NodeCategory',
    'NodeStatus',
    'NodeResult',
    'NodeConfig',
    'BaseNode',
    'ActionNode',
    'AgentNode',
    'LoopNode',
    'DecisionNode',
    'PreparationNode',
    'PersistenceNode',
    # State Manager
    'StateManager',
    'StateSnapshot',
    'WorkflowStatus'
]
