"""
================================================================================
节点类型定义 (Node Types)

定义 Agent 工作流中的各种节点类型，支持灵活的节点组合和工作流编排。

节点分类:
- Action Node: 执行单一操作，如 LLM 调用
- Agent Node: 智能体节点，可自主决策
- Preparation Node: 准备节点，初始化资源
- Loop Node: 循环节点，重复执行子节点
- Decision Node: 决策节点，根据条件分支
- Persistence Node: 持久化节点，保存结果

================================================================================
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime


class NodeCategory(Enum):
    """节点类别"""
    ACTION = "action"           # 动作节点
    AGENT = "agent"             # 智能体节点
    PREPARATION = "preparation" # 准备节点
    LOOP = "loop"               # 循环节点
    DECISION = "decision"       # 决策节点
    PERSISTENCE = "persistence" # 持久化节点


class NodeStatus(Enum):
    """节点执行状态"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"     # 执行中
    SUCCESS = "success"      # 成功
    FAILED = "failed"       # 失败
    SKIPPED = "skipped"     # 跳过
    CANCELLED = "cancelled" # 取消


@dataclass
class NodeResult:
    """节点执行结果"""
    status: NodeStatus
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == NodeStatus.SUCCESS


@dataclass
class NodeConfig:
    """节点配置"""
    node_id: str
    node_type: str
    category: NodeCategory
    name: str
    description: str = ""
    timeout_ms: int = 30000
    retry_count: int = 0
    conditions: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNode:
    """
    节点基类

    所有节点的父类，定义通用接口和行为。

    属性:
        config: 节点配置
        status: 当前状态
        result: 执行结果
    """

    def __init__(self, config: NodeConfig):
        self.config = config
        self.status = NodeStatus.PENDING
        self.result: Optional[NodeResult] = None
        self._context: Dict[str, Any] = {}

    @property
    def node_id(self) -> str:
        return self.config.node_id

    @property
    def node_type(self) -> str:
        return self.config.node_type

    @property
    def category(self) -> NodeCategory:
        return self.config.category

    def set_context(self, key: str, value: Any) -> None:
        """设置上下文"""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文"""
        return self._context.get(key, default)

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行节点

        Args:
            context: 共享上下文

        Returns:
            NodeResult: 执行结果
        """
        raise NotImplementedError

    def validate(self) -> bool:
        """验证节点配置"""
        return bool(self.config.node_id and self.config.node_type)


class ActionNode(BaseNode):
    """
    动作节点

    执行单一操作的节点，如调用 LLM、发送消息等。
    特点：同步执行，快速返回。
    """

    def __init__(self, config: NodeConfig, action_func: Callable):
        super().__init__(config)
        self.action_func = action_func

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行动作"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()

        try:
            result = await self.action_func(context)
            execution_time = (time.time() - start_time) * 1000

            self.result = NodeResult(
                status=NodeStatus.SUCCESS,
                output=result,
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.SUCCESS

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result


class AgentNode(BaseNode):
    """
    智能体节点

    具有自主决策能力的节点，可进行复杂的推理和行动。
    特点：可调用工具，支持 ReAct 模式。
    """

    def __init__(
        self,
        config: NodeConfig,
        agent_factory: Callable,
        max_iterations: int = 5
    ):
        super().__init__(config)
        self.agent_factory = agent_factory
        self.max_iterations = max_iterations

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行智能体节点"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()

        try:
            # 创建智能体
            agent = self.agent_factory(context)

            # 执行推理
            result = await agent.run(context.get('input', ''), context)

            execution_time = (time.time() - start_time) * 1000

            self.result = NodeResult(
                status=NodeStatus.SUCCESS if result.get('success') else NodeStatus.FAILED,
                output=result,
                execution_time_ms=execution_time,
                metadata={'iterations': result.get('steps', [])}
            )

            self.status = NodeStatus.SUCCESS if result.get('success') else NodeStatus.FAILED

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result


class LoopNode(BaseNode):
    """
    循环节点

    重复执行子节点的容器，支持条件循环。
    特点：包含子节点列表，根据条件重复执行。
    """

    def __init__(
        self,
        config: NodeConfig,
        child_nodes: List[BaseNode],
        max_iterations: int = 10
    ):
        super().__init__(config)
        self.child_nodes = child_nodes
        self.max_iterations = max_iterations
        self.current_iteration = 0

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行循环"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()
        all_results = []

        try:
            for i in range(self.max_iterations):
                self.current_iteration = i + 1

                # 执行每个子节点
                iteration_results = []
                for node in self.child_nodes:
                    result = await node.execute(context)
                    iteration_results.append({
                        'node_id': node.node_id,
                        'result': result
                    })

                    # 如果某个节点失败，可能需要停止
                    if result.status == NodeStatus.FAILED:
                        if self.config.conditions.get('stop_on_failure', True):
                            break

                all_results.append({
                    'iteration': self.current_iteration,
                    'results': iteration_results
                })

                # 检查循环条件
                should_continue = self._check_condition(context)
                if not should_continue:
                    break

            execution_time = (time.time() - start_time) * 1000

            self.result = NodeResult(
                status=NodeStatus.SUCCESS,
                output={
                    'iterations': all_results,
                    'total_iterations': self.current_iteration
                },
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.SUCCESS

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result

    def _check_condition(self, context: Dict[str, Any]) -> bool:
        """检查循环条件"""
        # 默认继续循环
        return True


class DecisionNode(BaseNode):
    """
    决策节点

    根据条件决定执行路径的节点。
    特点：包含多个分支，根据条件选择。
    """

    def __init__(self, config: NodeConfig, decision_func: Callable):
        super().__init__(config)
        self.decision_func = decision_func
        self.branches: Dict[str, BaseNode] = {}
        self.default_branch: Optional[str] = None

    def add_branch(self, condition: str, node: BaseNode) -> None:
        """添加分支"""
        self.branches[condition] = node

    def set_default_branch(self, node: BaseNode) -> None:
        """设置默认分支"""
        self.default_branch = node.node_id
        self.branches['_default'] = node

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行决策"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()

        try:
            # 执行决策函数
            decision_result = self.decision_func(context)

            # 选择分支
            branch_key = decision_result.get('branch', '_default')
            selected_node = self.branches.get(branch_key)

            if selected_node is None and '_default' in self.branches:
                selected_node = self.branches['_default']

            if selected_node:
                result = await selected_node.execute(context)
                execution_time = (time.time() - start_time) * 1000
                self.result = NodeResult(
                    status=result.status,
                    output={
                        'decision': decision_result,
                        'branch': branch_key,
                        'node_output': result.output
                    },
                    execution_time_ms=execution_time
                )
            else:
                execution_time = (time.time() - start_time) * 1000
                self.result = NodeResult(
                    status=NodeStatus.SUCCESS,
                    output={'decision': decision_result, 'branch': 'none'},
                    execution_time_ms=execution_time
                )

            self.status = self.result.status

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result


class PreparationNode(BaseNode):
    """
    准备节点

    初始化资源和配置的节点。
    特点：执行准备操作，为后续节点准备环境。
    """

    def __init__(self, config: NodeConfig, prepare_func: Callable):
        super().__init__(config)
        self.prepare_func = prepare_func

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行准备"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()

        try:
            result = self.prepare_func(context)

            # 将准备结果添加到上下文
            if isinstance(result, dict):
                context.update(result)

            execution_time = (time.time() - start_time) * 1000

            self.result = NodeResult(
                status=NodeStatus.SUCCESS,
                output=result,
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.SUCCESS

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result


class PersistenceNode(BaseNode):
    """
    持久化节点

    保存结果到存储的节点。
    特点：异步写入，支持多种存储后端。
    """

    def __init__(
        self,
        config: NodeConfig,
        save_func: Callable,
        storage_type: str = "file"
    ):
        super().__init__(config)
        self.save_func = save_func
        self.storage_type = storage_type

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """执行持久化"""
        import time
        self.status = NodeStatus.RUNNING
        start_time = time.time()

        try:
            result = await self.save_func(context)

            execution_time = (time.time() - start_time) * 1000

            self.result = NodeResult(
                status=NodeStatus.SUCCESS,
                output=result,
                execution_time_ms=execution_time,
                metadata={'storage_type': self.storage_type}
            )
            self.status = NodeStatus.SUCCESS

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            self.result = NodeResult(
                status=NodeStatus.FAILED,
                error=str(e),
                execution_time_ms=execution_time
            )
            self.status = NodeStatus.FAILED

        return self.result
