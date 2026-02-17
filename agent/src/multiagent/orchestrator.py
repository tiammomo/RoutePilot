"""
================================================================================
Multi-Agent Orchestrator - 多 Agent 协调器

核心编排组件，负责协调多个 Agent 完成复杂任务。
================================================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from multiagent.agent_factory import AgentFactory, AgentType, AgentInstance
from multiagent.message_bus import MessageBus, BusMode
from multiagent.protocols.communication import AgentMessage, MessageType
from multiagent.roles.planner import PlannerAgent, ExecutionPlan
from multiagent.roles.specialist import SpecialistAgent, TaskResult
from multiagent.roles.supervisor import SupervisorAgent, ReviewResult
from multiagent.collaboration.task_distributor import TaskDistributor
from multiagent.collaboration.result_merger import ResultMerger, MergedResult

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """协调器配置"""
    max_concurrent_tasks: int = 3
    enable_parallel_execution: bool = True
    enable_review: bool = True
    review_threshold: float = 60.0  # 审核阈值
    timeout: int = 300  # 超时时间（秒）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiAgentResult:
    """多 Agent 执行结果"""
    success: bool
    output: Any
    plan: Optional[ExecutionPlan] = None
    task_results: List[TaskResult] = field(default_factory=list)
    review_results: List[ReviewResult] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MultiAgentOrchestrator:
    """多 Agent 协调器

    负责：
    - 创建和管理多个 Agent
    - 协调 Agent 间的通信
    - 分发任务给 Specialist Agents
    - 审核结果
    - 合并最终输出
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        llm_client: Optional[Any] = None,
        tools: Optional[Dict[str, Callable]] = None
    ):
        """
        Args:
            config: 协调器配置
            llm_client: LLM 客户端
            tools: 可用工具字典
        """
        self.config = config or OrchestratorConfig()
        self.llm_client = llm_client
        self.tools = tools or {}

        # 组件初始化
        self.message_bus = MessageBus(mode=BusMode.ASYNC)
        self.agent_factory = AgentFactory(llm_client=llm_client)
        self.task_distributor = TaskDistributor()
        self.result_merger = ResultMerger()

        # Agent 实例
        self.planner: Optional[PlannerAgent] = None
        self.supervisor: Optional[SupervisorAgent] = None
        self.specialists: Dict[str, SpecialistAgent] = {}

        # 执行状态
        self._is_running = False
        self._current_session_id: Optional[str] = None

        # 初始化默认 Agent
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """初始化默认 Agent"""
        # 创建 Planner
        planner_instance = self.agent_factory.create_planner("planner_1")
        self.planner = PlannerAgent(
            agent_id=planner_instance.config.agent_id,
            llm_client=self.llm_client
        )

        # 注册到消息总线
        self.message_bus.register_agent(planner_instance.config.agent_id)

        # 创建 Supervisor
        supervisor_instance = self.agent_factory.create_supervisor("supervisor_1")
        self.supervisor = SupervisorAgent(
            agent_id=supervisor_instance.config.agent_id,
            llm_client=self.llm_client
        )
        self.message_bus.register_agent(supervisor_instance.config.agent_id)

        logger.info("Initialized multi-agent orchestrator with default agents")

    def create_specialist(self, domain: str, agent_id: Optional[str] = None) -> SpecialistAgent:
        """创建 Specialist Agent

        Args:
            domain: 专业领域
            agent_id: Agent ID

        Returns:
            SpecialistAgent 实例
        """
        instance = self.agent_factory.create_specialist(
            agent_id=agent_id,
            domain=domain,
            tools=list(self.tools.keys())
        )

        specialist = SpecialistAgent(
            agent_id=instance.config.agent_id,
            domain=domain,
            tools=self.tools,
            llm_client=self.llm_client
        )

        self.specialists[instance.config.agent_id] = specialist
        self.message_bus.register_agent(instance.config.agent_id)

        logger.info(f"Created specialist agent for domain: {domain}")
        return specialist

    async def process(self, user_request: str, session_id: Optional[str] = None) -> MultiAgentResult:
        """处理用户请求

        Args:
            user_request: 用户请求
            session_id: 会话 ID

        Returns:
            执行结果
        """
        import time

        start_time = time.time()
        self._is_running = True
        self._current_session_id = session_id or "default"

        logger.info(f"Processing request: {user_request[:50]}...")

        try:
            # 1. Planner Agent 创建执行计划
            plan = await self._planning(user_request)

            # 2. 分发任务给 Specialist Agents
            task_assignments = self.task_distributor.distribute(plan)

            # 3. 执行任务
            task_results = await self._execute_tasks(task_assignments)

            # 4. Supervisor Agent 审核（可选）
            review_results = []
            if self.config.enable_review:
                review_results = await self._supervise(task_results)

            # 5. 合并结果
            merged = await self.result_merger.merge(task_results, review_results)

            execution_time = time.time() - start_time

            result = MultiAgentResult(
                success=merged.success,
                output=merged.combined_output,
                plan=plan,
                task_results=task_results,
                review_results=review_results,
                execution_time=execution_time,
                metadata={
                    "session_id": self._current_session_id,
                    "agent_count": len(self.specialists) + 2,  # +2 for planner & supervisor
                    "review_enabled": self.config.enable_review
                }
            )

            logger.info(f"Request processed in {execution_time:.2f}s, success: {result.success}")
            return result

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            execution_time = time.time() - start_time
            return MultiAgentResult(
                success=False,
                output=None,
                execution_time=execution_time,
                metadata={"error": str(e)}
            )
        finally:
            self._is_running = False

    async def _planning(self, user_request: str) -> ExecutionPlan:
        """任务规划"""
        if not self.planner:
            raise RuntimeError("Planner not initialized")

        plan = await self.planner.create_plan(user_request)
        logger.debug(f"Created plan with {len(plan.tasks)} tasks")
        return plan

    async def _execute_tasks(self, task_assignments) -> List[TaskResult]:
        """执行任务"""
        results = []

        # 如果启用并行执行
        if self.config.enable_parallel_execution:
            # 按并行组执行
            for group in self._group_by_parallel(task_assignments):
                group_results = await asyncio.gather(*[
                    self._execute_single_task(assignment)
                    for assignment in group
                ])
                results.extend(group_results)
        else:
            # 串行执行
            for assignment in task_assignments:
                result = await self._execute_single_task(assignment)
                results.append(result)

        return results

    def _group_by_parallel(self, assignments) -> List[List]:
        """按并行组分组"""
        # 简化实现：每组最多 max_concurrent_tasks 个
        groups = []
        for i in range(0, len(assignments), self.config.max_concurrent_tasks):
            groups.append(assignments[i:i + self.config.max_concurrent_tasks])
        return groups

    async def _execute_single_task(self, assignment) -> TaskResult:
        """执行单个任务"""
        agent_id = assignment.assigned_agent_id

        # 获取或创建 Specialist
        if agent_id not in self.specialists:
            self.create_specialist(domain=assignment.parameters.get("domain", "general"), agent_id=agent_id)

        specialist = self.specialists[agent_id]

        # 执行任务
        result = await specialist.execute_task(
            task_id=assignment.task_id,
            task_description=assignment.parameters.get("description", ""),
            parameters={
                "tool": assignment.parameters.get("tools", [None])[0] if assignment.parameters.get("tools") else None,
                "params": assignment.parameters.get("metadata", {})
            }
        )

        return result

    async def _supervise(self, task_results: List[TaskResult]) -> List[ReviewResult]:
        """审核结果"""
        if not self.supervisor:
            return []

        review_results = []
        for result in task_results:
            review = await self.supervisor.review_result(
                task_id=result.task_id,
                task_description="",
                result=result.result
            )
            review_results.append(review)

        return review_results

    def get_status(self) -> Dict[str, Any]:
        """获取协调器状态"""
        return {
            "is_running": self._is_running,
            "current_session": self._current_session_id,
            "specialist_count": len(self.specialists),
            "message_bus_stats": self.message_bus.get_stats(),
            "agent_factory_stats": {
                "total_agents": len(self.agent_factory.list_agents())
            }
        }

    async def shutdown(self) -> None:
        """关闭协调器"""
        logger.info("Shutting down multi-agent orchestrator")

        # 注销所有 Agent
        for agent_id in list(self.specialists.keys()):
            self.message_bus.unregister_agent(agent_id)

        if self.planner:
            self.message_bus.unregister_agent(self.planner.agent_id)

        if self.supervisor:
            self.message_bus.unregister_agent(self.supervisor.agent_id)

        self.specialists.clear()
        self._is_running = False
