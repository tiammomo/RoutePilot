"""
================================================================================
Task Distributor - 任务分发器

负责将执行计划分发给合适的 Agent 执行。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from multiagent.roles.planner import ExecutionPlan, SubTask

logger = logging.getLogger(__name__)


@dataclass
class TaskAssignment:
    """任务分配"""
    task_id: str
    assigned_agent_id: str
    agent_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)


class TaskDistributor:
    """任务分发器

    负责：
    - 分析任务需求
    - 选择合适的 Agent
    - 分配任务
    - 跟踪分配状态
    """

    def __init__(self):
        """初始化"""
        self._assignments: Dict[str, TaskAssignment] = {}
        self._agent_workload: Dict[str, int] = {}  # Agent 工作负载

    def distribute(self, plan: ExecutionPlan) -> List[TaskAssignment]:
        """分发任务

        Args:
            plan: 执行计划

        Returns:
            任务分配列表
        """
        assignments = []

        # 按优先级排序
        sorted_tasks = sorted(plan.tasks, key=lambda t: t.priority)

        for task in sorted_tasks:
            # 选择最合适的 Agent
            agent_id = self._select_agent(task)

            assignment = TaskAssignment(
                task_id=task.task_id,
                assigned_agent_id=agent_id,
                agent_type="specialist",
                parameters={
                    "description": task.description,
                    "tools": task.required_tools,
                    "dependencies": task.dependencies,
                    "priority": task.priority,
                    "metadata": task.metadata
                }
            )

            assignments.append(assignment)
            self._assignments[task.task_id] = assignment
            self._agent_workload[agent_id] = self._agent_workload.get(agent_id, 0) + 1

        logger.info(f"Distributed {len(assignments)} tasks")
        return assignments

    def _select_agent(self, task: SubTask) -> str:
        """选择最合适的 Agent

        根据任务需求和 Agent 能力选择最佳 Agent。
        简化实现：使用负载均衡
        """
        # 简单负载均衡：选择工作负载最少的 Agent
        # 实际实现需要根据 Agent 能力和任务需求匹配
        if not self._agent_workload:
            return "specialist_1"

        min_workload_agent = min(self._agent_workload.items(), key=lambda x: x[1])
        return min_workload_agent[0]

    def get_assignment(self, task_id: str) -> Optional[TaskAssignment]:
        """获取任务分配"""
        return self._assignments.get(task_id)

    def get_agent_assignments(self, agent_id: str) -> List[TaskAssignment]:
        """获取 Agent 的所有任务分配"""
        return [a for a in self._assignments.values() if a.assigned_agent_id == agent_id]

    def update_status(self, task_id: str, status: str) -> None:
        """更新任务状态"""
        if task_id in self._assignments:
            self._assignments[task_id].parameters["status"] = status

    def get_workload_stats(self) -> Dict[str, int]:
        """获取工作负载统计"""
        return self._agent_workload.copy()
