"""
================================================================================
Planner Agent - 规划 Agent

负责任务分解、计划制定和执行流程规划。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class PlanComplexity(Enum):
    """计划复杂度"""
    SIMPLE = "simple"       # 简单 - 单步任务
    MEDIUM = "medium"       # 中等 - 多步串行
    COMPLEX = "complex"     # 复杂 - 多步并行


@dataclass
class SubTask:
    """子任务"""
    task_id: str
    description: str
    required_tools: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务 ID
    estimated_duration: int = 0  # 预计耗时（分钟）
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    original_request: str
    complexity: PlanComplexity
    tasks: List[SubTask]
    parallel_groups: List[List[str]] = field(default_factory=list)  # 可并行执行的任务组
    estimated_total_time: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlannerAgent:
    """Planner Agent

    负责：
    - 分析用户请求
    - 分解任务为子任务
    - 确定任务依赖关系
    - 生成执行计划
    """

    def __init__(self, agent_id: str, llm_client: Optional[Any] = None):
        """
        Args:
            agent_id: Agent ID
            llm_client: LLM 客户端（可选）
        """
        self.agent_id = agent_id
        self.llm_client = llm_client

    async def create_plan(self, user_request: str) -> ExecutionPlan:
        """创建执行计划

        Args:
            user_request: 用户请求

        Returns:
            执行计划
        """
        import uuid

        # 分析任务复杂度
        complexity = self._assess_complexity(user_request)

        # 分解任务
        tasks = await self._decompose_tasks(user_request, complexity)

        # 确定并行组
        parallel_groups = self._identify_parallel_groups(tasks)

        # 计算总耗时
        total_time = sum(t.estimated_duration for t in tasks)

        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_request=user_request,
            complexity=complexity,
            tasks=tasks,
            parallel_groups=parallel_groups,
            estimated_total_time=total_time
        )

        logger.info(f"Created plan {plan.plan_id} with {len(tasks)} tasks")
        return plan

    def _assess_complexity(self, request: str) -> PlanComplexity:
        """评估任务复杂度"""
        # 简单规则：如果请求包含多日、多地点、复杂规划等关键词
        complexity_indicators = {
            "simple": ["推荐", "告诉", "查询"],
            "medium": ["规划", "路线", "安排"],
            "complex": ["多日", "深度游", "详细规划", "完整行程"]
        }

        for indicator in complexity_indicators["complex"]:
            if indicator in request:
                return PlanComplexity.COMPLEX

        for indicator in complexity_indicators["medium"]:
            if indicator in request:
                return PlanComplexity.MEDIUM

        return PlanComplexity.SIMPLE

    async def _decompose_tasks(self, request: str, complexity: PlanComplexity) -> List[SubTask]:
        """分解任务"""
        import uuid

        # 如果有 LLM，使用 LLM 分解
        if self.llm_client:
            return await self._llm_decompose(request, complexity)

        # 否则使用规则分解
        return self._rule_based_decompose(request, complexity)

    async def _llm_decompose(self, request: str, complexity: PlanComplexity) -> List[SubTask]:
        """使用 LLM 分解任务"""
        import uuid

        # 构建提示词
        prompt = f"""分析以下用户请求，分解为具体的子任务：

用户请求：{request}

请返回 JSON 格式的子任务列表，每个子任务包含：
- task_id: 任务ID
- description: 任务描述
- required_tools: 需要的工具列表
- dependencies: 依赖的任务ID列表
- estimated_duration: 预计耗时（分钟）
- priority: 优先级（1-5）

返回格式：JSON 数组
"""

        # 这里简化处理，实际需要调用 LLM
        # 返回默认任务
        return self._rule_based_decompose(request, complexity)

    def _rule_based_decompose(self, request: str, complexity: PlanComplexity) -> List[SubTask]:
        """基于规则的分解"""
        import uuid

        tasks = []

        # 简单任务
        if complexity == PlanComplexity.SIMPLE:
            tasks.append(SubTask(
                task_id=str(uuid.uuid4()),
                description=f"处理请求: {request}",
                required_tools=["llm_chat"],
                priority=1
            ))

        # 中等复杂度
        elif complexity == PlanComplexity.MEDIUM:
            tasks.extend([
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="理解用户需求",
                    required_tools=["llm_chat"],
                    priority=1
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="收集相关信息",
                    required_tools=["search_cities", "query_attractions"],
                    dependencies=[],
                    priority=2
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="生成规划方案",
                    required_tools=["generate_route", "llm_chat"],
                    dependencies=[],
                    priority=3
                )
            ])

        # 复杂任务
        else:
            tasks.extend([
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="分析用户需求和偏好",
                    required_tools=["llm_chat"],
                    priority=1
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="搜索目的地信息",
                    required_tools=["search_cities"],
                    dependencies=[],
                    priority=2
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="查询景点详情",
                    required_tools=["query_attractions"],
                    dependencies=["task_2"],
                    priority=2
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="规划每日行程",
                    required_tools=["generate_route", "generate_itinerary"],
                    dependencies=["task_3"],
                    priority=3
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="计算预算",
                    required_tools=["calculate_budget"],
                    dependencies=["task_4"],
                    priority=4
                ),
                SubTask(
                    task_id=str(uuid.uuid4()),
                    description="整合并生成最终方案",
                    required_tools=["llm_chat"],
                    dependencies=["task_5"],
                    priority=5
                )
            ])

        return tasks

    def _identify_parallel_groups(self, tasks: List[SubTask]) -> List[List[str]]:
        """识别可并行执行的任务组"""
        # 简单实现：没有依赖的任务可以并行
        groups = []
        remaining = set(t.task_id for t in tasks)

        while remaining:
            # 找所有没有依赖的任务
            independent = []
            for task in tasks:
                if task.task_id in remaining:
                    deps = set(task.dependencies)
                    if not deps or not deps.intersection(remaining):
                        independent.append(task.task_id)

            if independent:
                groups.append(independent)
                remaining -= set(independent)
            else:
                # 如果有循环依赖，取任意一个
                if remaining:
                    groups.append([remaining.pop()])

        return groups
