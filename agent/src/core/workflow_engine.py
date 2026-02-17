"""
================================================================================
工作流引擎 (Workflow Engine)

提供任务分解、执行计划生成、子任务调度和结果聚合功能。
用于支持 PLAN 模式下的复杂多步骤任务处理。

功能特点:
- 智能任务分解：将用户请求分解为可执行的子任务
- 任务队列管理：支持顺序/并行执行策略
- 依赖管理：自动分析任务依赖并生成执行计划
- 结果聚合：将多个子任务结果合并为最终响应

使用示例:
```python
engine = WorkflowEngine(agent)
result = await engine.execute_plan("帮我规划北京三日游")

# 或者使用任务队列
queue = TaskQueue()
await queue.enqueue(Task(...))
task = await queue.dequeue()
```

================================================================================
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Callable
from datetime import datetime
from collections import deque
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"       # 待执行
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
    WAITING = "waiting"       # 等待依赖


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Task:
    """任务定义"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    task_type: str = "general"  # general, search, query, plan, calculate, recommend
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务 ID
    depends_on: List[str] = field(default_factory=list)  # 当前任务依赖的任务
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_ready(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否准备好执行（所有依赖已完成）"""
        return all(dep_id in completed_tasks for dep_id in self.depends_on)

    def duration_ms(self) -> float:
        """获取任务执行时长（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "status": self.status.value,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "depends_on": self.depends_on,
            "duration_ms": self.duration_ms(),
            "result": self.result,
            "error": self.error
        }


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_request: str = ""
    tasks: List[Task] = field(default_factory=list)
    execution_order: List[List[str]] = field(default_factory=list)  # 分层的任务执行顺序
    estimated_time_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_task(self, task_id: str) -> Optional[Task]:
        """根据 ID 获取任务"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None


class TaskQueue:
    """任务队列管理器"""

    def __init__(self, max_size: int = 100):
        self._queue: deque = deque(maxlen=max_size)
        self._waiting: Dict[str, Task] = {}  # 等待依赖的任务
        self._completed: Set[str] = set()
        self._lock = asyncio.Lock()

    async def enqueue(self, task: Task) -> None:
        """添加任务到队列"""
        async with self._lock:
            if task.status == TaskStatus.PENDING:
                self._queue.append(task)
                logger.debug(f"Task {task.task_id} enqueued: {task.name}")

    async def enqueue_batch(self, tasks: List[Task]) -> None:
        """批量添加任务"""
        for task in tasks:
            await self.enqueue(task)

    async def dequeue(self) -> Optional[Task]:
        """取出最高优先级的就绪任务"""
        async with self._lock:
            # 查找就绪的最高优先级任务
            ready_tasks = [
                t for t in self._queue
                if t.status == TaskStatus.PENDING and t.is_ready(self._completed)
            ]

            if not ready_tasks:
                return None

            # 按优先级排序
            ready_tasks.sort(key=lambda t: t.priority.value, reverse=True)
            task = ready_tasks[0]
            self._queue.remove(task)
            task.status = TaskStatus.RUNNING
            task.start_time = datetime.now()
            return task

    async def mark_completed(self, task_id: str) -> None:
        """标记任务完成"""
        async with self._lock:
            self._completed.add(task_id)
            # 检查是否有等待此任务的任务变得就绪
            newly_ready = [
                t for t in self._queue
                if t.status == TaskStatus.PENDING and task_id in t.depends_on
                and t.is_ready(self._completed)
            ]
            logger.debug(f"Task {task_id} completed, {len(newly_ready)} tasks now ready")

    async def mark_failed(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        async def _mark():
            for task in self._queue:
                if task.task_id == task_id:
                    task.status = TaskStatus.FAILED
                    task.error = error
                    task.end_time = datetime.now()
                    break
            # 取消所有依赖此任务的任务
            for task in self._queue:
                if task_id in task.depends_on:
                    task.status = TaskStatus.CANCELLED
                    task.error = f"Dependency failed: {error}"

        async with self._lock:
            await _mark()

    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._queue) == 0

    def size(self) -> int:
        """获取队列大小"""
        return len(self._queue)

    def get_pending_count(self) -> int:
        """获取待执行任务数"""
        return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    def get_completed_count(self) -> int:
        """获取已完成任务数"""
        return len(self._completed)


class TaskDecomposer:
    """任务分解器

    将用户请求分解为可执行的子任务序列。
    支持基于规则和基于 LLM 两种分解模式。
    """

    # 任务类型与工具的映射
    TASK_TOOL_MAPPING = {
        "search_cities": ["search_cities"],
        "search_attractions": ["query_attractions"],
        "get_city_info": ["get_city_info"],
        "generate_route": ["generate_route", "generate_route_plan"],
        "calculate_budget": ["calculate_budget"],
        "get_weather": ["query_weather"],
        "get_traffic": ["query_traffic"],
        "search_hotels": ["search_hotels"],
        "search_restaurants": ["search_restaurants"],
    }

    # 常见任务模式
    TASK_PATTERNS = [
        {
            "keywords": ["三日游", "五日游", "七天", "几天"],
            "task_type": "multi_day_trip",
            "default_tasks": ["search_cities", "get_city_info", "query_attractions",
                            "generate_route", "calculate_budget"]
        },
        {
            "keywords": ["预算", "花多少钱", "费用"],
            "task_type": "budget_calculation",
            "default_tasks": ["calculate_budget"]
        },
        {
            "keywords": ["景点", "好玩", "推荐"],
            "task_type": "attraction_recommend",
            "default_tasks": ["search_cities", "query_attractions", "generate_recommendation"]
        },
        {
            "keywords": ["路线", "行程", "规划"],
            "task_type": "route_planning",
            "default_tasks": ["get_city_info", "generate_route", "generate_route_plan"]
        },
    ]

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.use_llm_decompose = llm_client is not None

    async def decompose(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> List[Task]:
        """分解用户请求为任务列表

        Args:
            user_request: 用户请求
            context: 上下文信息（如用户偏好、历史对话等）

        Returns:
            任务列表
        """
        if self.use_llm_decompose:
            return await self._llm_decompose(user_request, context)
        else:
            return await self._rule_based_decompose(user_request, context)

    async def _rule_based_decompose(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> List[Task]:
        """基于规则的任务分解"""
        tasks = []
        request_lower = user_request.lower()

        # 检测任务模式
        matched_pattern = None
        for pattern in self.TASK_PATTERNS:
            if any(kw in request_lower for kw in pattern["keywords"]):
                matched_pattern = pattern
                break

        if matched_pattern:
            # 根据匹配的模式创建任务
            for i, task_name in enumerate(matched_pattern["default_tasks"]):
                task = Task(
                    name=task_name,
                    description=f"执行 {task_name} 任务",
                    task_type=self._get_task_type(task_name),
                    priority=TaskPriority.NORMAL
                )
                # 设置依赖关系
                if i > 0:
                    task.depends_on = [tasks[i-1].task_id]
                tasks.append(task)
        else:
            # 默认任务
            tasks.append(Task(
                name="general_request",
                description=user_request,
                task_type="general"
            ))

        logger.info(f"Decomposed into {len(tasks)} tasks")
        return tasks

    async def _llm_decompose(self, user_request: str, context: Optional[Dict[str, Any]] = None) -> List[Task]:
        """基于 LLM 的任务分解"""
        # 构建提示词
        prompt = self._build_decompose_prompt(user_request, context)

        try:
            # 调用 LLM
            response = await self.llm_client.chat([
                {"role": "user", "content": prompt}
            ])

            # 解析响应
            tasks = self._parse_llm_response(response)
            return tasks
        except Exception as e:
            logger.warning(f"LLM decompose failed: {e}, falling back to rule-based")
            return await self._rule_based_decompose(user_request, context)

    def _build_decompose_prompt(self, user_request: str, context: Optional[Dict[str, Any]]) -> str:
        """构建分解提示词"""
        return f"""你是一个任务分解助手。请将用户请求分解为可执行的子任务。

用户请求：{user_request}

请以 JSON 数组格式返回任务列表，每个任务包含：
- name: 任务名称
- description: 任务描述
- task_type: 任务类型 (search/query/plan/calculate/recommend)
- depends_on: 依赖的前置任务名称列表

可用工具：search_cities, query_attractions, get_city_info, generate_route, generate_route_plan, calculate_budget, generate_recommendation

请确保任务有明确的依赖顺序。"""

    def _parse_llm_response(self, response: str) -> List[Task]:
        """解析 LLM 响应"""
        import json

        try:
            # 尝试提取 JSON
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            task_list = json.loads(response.strip())

            tasks = []
            for i, t in enumerate(task_list):
                task = Task(
                    name=t.get("name", f"task_{i}"),
                    description=t.get("description", ""),
                    task_type=t.get("task_type", "general"),
                    priority=TaskPriority.NORMAL
                )
                # 处理依赖
                if "depends_on" in t and t["depends_on"]:
                    task.depends_on = t["depends_on"]
                tasks.append(task)

            # 建立依赖关系
            for task in tasks:
                if task.depends_on:
                    dep_ids = []
                    for dep_name in task.depends_on:
                        for t in tasks:
                            if t.name == dep_name:
                                dep_ids.append(t.task_id)
                                break
                    task.depends_on = dep_ids

            return tasks

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return [Task(name="general", description=user_request, task_type="general")]

    def _get_task_type(self, task_name: str) -> str:
        """获取任务类型"""
        if "search" in task_name:
            return "search"
        elif "query" in task_name or "get_" in task_name:
            return "query"
        elif "generate_route" in task_name or "plan" in task_name:
            return "plan"
        elif "calculate" in task_name or "budget" in task_name:
            return "calculate"
        elif "recommend" in task_name:
            return "recommend"
        return "general"

    def compute_execution_order(self, tasks: List[Task]) -> List[List[str]]:
        """计算任务执行顺序（拓扑排序，返回分层列表）

        Args:
            tasks: 任务列表

        Returns:
            分层执行顺序，每层内的任务可以并行执行
        """
        # 构建依赖图
        in_degree = {t.task_id: 0 for t in tasks}
        graph = {t.task_id: [] for t in tasks}

        for task in tasks:
            for dep_id in task.depends_on:
                if dep_id in graph:
                    graph[dep_id].append(task.task_id)
                    in_degree[task.task_id] += 1

        # Kahn's algorithm with level tracking
        execution_order = []
        remaining = set(t.task_id for t in tasks)

        while remaining:
            # 找出所有入度为 0 的任务
            current_level = [tid for tid in remaining if in_degree[tid] == 0]

            if not current_level:
                # 存在循环依赖，选择任意一个
                current_level = [list(remaining)[0]]

            execution_order.append(current_level)

            # 移除当前层任务
            for tid in current_level:
                remaining.remove(tid)
                # 更新依赖任务的入度
                for next_tid in graph[tid]:
                    in_degree[next_tid] -= 1

        return execution_order


class ResultAggregator:
    """结果聚合器

    将多个子任务的结果聚合为最终响应。
    支持多种聚合策略：顺序拼接、模板填充、智能合并。
    """

    def __init__(self, aggregation_strategy: str = "template"):
        """
        Args:
            aggregation_strategy: 聚合策略 (template/sequential/merge)
        """
        self.aggregation_strategy = aggregation_strategy

    async def aggregate(
        self,
        tasks: List[Task],
        user_request: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """聚合任务结果

        Args:
            tasks: 已执行的任务列表
            user_request: 原始用户请求
            context: 上下文信息

        Returns:
            聚合后的结果
        """
        if self.aggregation_strategy == "template":
            return await self._template_aggregate(tasks, user_request, context)
        elif self.aggregation_strategy == "sequential":
            return await self._sequential_aggregate(tasks, user_request, context)
        elif self.aggregation_strategy == "merge":
            return await self._merge_aggregate(tasks, user_request, context)
        else:
            return await self._template_aggregate(tasks, user_request, context)

    async def _template_aggregate(
        self,
        tasks: List[Task],
        user_request: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """模板填充聚合"""
        # 按执行顺序排序任务
        sorted_tasks = sorted(tasks, key=lambda t: t.start_time or datetime.now())

        # 提取关键信息
        city_info = None
        attractions = None
        route = None
        budget = None

        for task in sorted_tasks:
            if task.status != TaskStatus.COMPLETED:
                continue

            if "city_info" in task.name or "get_city_info" in task.name:
                city_info = task.result
            elif "attractions" in task.name or "query_attractions" in task.name:
                attractions = task.result
            elif "route" in task.name:
                route = task.result
            elif "budget" in task.name or "calculate" in task.name:
                budget = task.result

        # 生成最终响应
        final_answer = self._build_response(
            city_info=city_info,
            attractions=attractions,
            route=route,
            budget=budget,
            user_request=user_request
        )

        return {
            "success": True,
            "answer": final_answer,
            "task_results": [t.to_dict() for t in sorted_tasks],
            "metadata": {
                "total_tasks": len(tasks),
                "completed_tasks": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
                "failed_tasks": sum(1 for t in tasks if t.status == TaskStatus.FAILED)
            }
        }

    async def _sequential_aggregate(
        self,
        tasks: List[Task],
        user_request: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """顺序拼接聚合"""
        results = []
        for task in tasks:
            if task.status == TaskStatus.COMPLETED:
                results.append({
                    "task": task.name,
                    "result": task.result
                })

        return {
            "success": True,
            "answer": "\n\n---\n\n".join(str(r["result"]) for r in results),
            "task_results": results
        }

    async def _merge_aggregate(
        self,
        tasks: List[Task],
        user_request: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """智能合并聚合"""
        merged = {}
        for task in tasks:
            if task.status == TaskStatus.COMPLETED and task.result:
                if isinstance(task.result, dict):
                    merged.update(task.result)
                else:
                    merged[task.name] = task.result

        return {
            "success": True,
            "answer": str(merged),
            "merged_data": merged,
            "task_results": [t.to_dict() for t in tasks]
        }

    def _build_response(
        self,
        city_info: Any,
        attractions: Any,
        route: Any,
        budget: Any,
        user_request: str
    ) -> str:
        """构建最终响应"""
        parts = []

        if city_info:
            parts.append(f"📍 **城市信息**\n{city_info}")

        if attractions:
            parts.append(f"🎯 **景点推荐**\n{attractions}")

        if route:
            parts.append(f"🗺️ **行程路线**\n{route}")

        if budget:
            parts.append(f"💰 **费用预算**\n{budget}")

        if not parts:
            return "抱歉，无法生成有效的旅行建议。"

        return "\n\n".join(parts)


class WorkflowEngine:
    """工作流引擎

    协调任务分解、任务队列执行和结果聚合的完整流程。
    支持同步和异步执行模式。
    """

    def __init__(
        self,
        agent,
        max_concurrent: int = 3,
        enable_parallel: bool = True
    ):
        """
        Args:
            agent: ReActTravelAgent 实例
            max_concurrent: 最大并发任务数
            enable_parallel: 是否允许并行执行
        """
        self.agent = agent
        self.max_concurrent = max_concurrent
        self.enable_parallel = enable_parallel
        self.task_queue = TaskQueue()
        self.decomposer = TaskDecomposer(agent.llm_client if agent else None)
        self.aggregator = ResultAggregator()
        self._executor: Optional[asyncio.Task] = None

    async def execute_plan(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行完整的任务计划

        Args:
            user_request: 用户请求
            context: 上下文信息

        Returns:
            执行结果
        """
        logger.info(f"WorkflowEngine: Starting plan execution for: {user_request[:50]}...")

        # 1. 任务分解
        tasks = await self.decomposer.decompose(user_request, context)
        logger.info(f"Decomposed into {len(tasks)} tasks")

        if not tasks:
            return {
                "success": False,
                "error": "任务分解失败",
                "answer": "抱歉，我无法理解您的请求。"
            }

        # 2. 计算执行顺序
        execution_order = self.decomposer.compute_execution_order(tasks)
        logger.info(f"Execution order: {execution_order}")

        # 3. 添加任务到队列
        await self.task_queue.enqueue_batch(tasks)

        # 4. 执行任务
        completed_tasks = []
        try:
            if self.enable_parallel:
                completed_tasks = await self._execute_parallel(execution_order, tasks)
            else:
                completed_tasks = await self._execute_sequential(tasks)
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "answer": "执行过程中出现错误，请稍后重试。"
            }

        # 5. 聚合结果
        result = await self.aggregator.aggregate(
            completed_tasks,
            user_request,
            context
        )

        logger.info(f"Workflow completed: {result.get('metadata', {})}")
        return result

    async def _execute_sequential(self, tasks: List[Task]) -> List[Task]:
        """顺序执行任务"""
        completed = []

        for task in tasks:
            result = await self._execute_task(task)
            completed.append(result)

            if result.status == TaskStatus.FAILED:
                logger.warning(f"Task {task.name} failed, stopping execution")
                break

        return completed

    async def _execute_parallel(self, execution_order: List[List[str]], tasks: List[Task]) -> List[Task]:
        """分层并行执行任务"""
        completed = []
        task_map = {t.task_id: t for t in tasks}

        for level in execution_order:
            # 并行执行当前层的任务
            level_tasks = [task_map[tid] for tid in level if tid in task_map]

            if not level_tasks:
                continue

            logger.info(f"Executing {len(level_tasks)} tasks in parallel")

            # 使用信号量控制并发
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def execute_with_limit(task):
                async with semaphore:
                    return await self._execute_task(task)

            results = await asyncio.gather(
                *[execute_with_limit(t) for t in level_tasks],
                return_exceptions=True
            )

            # 处理结果
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {level_tasks[i].name} raised exception: {result}")
                    level_tasks[i].status = TaskStatus.FAILED
                    level_tasks[i].error = str(result)
                completed.append(result if not isinstance(result, Exception) else level_tasks[i])

            # 检查是否有失败的任务
            failed = [t for t in level_tasks if t.status == TaskStatus.FAILED]
            if failed and not self._is_critical_task(failed[0]):
                logger.warning(f"Non-critical task failed, continuing...")

        return completed

    async def _execute_task(self, task: Task) -> Task:
        """执行单个任务"""
        logger.info(f"Executing task: {task.name}")

        try:
            # 调用 Agent 执行任务
            if self.agent and hasattr(self.agent, 'react_agent'):
                # 尝试通过 Agent 的工具执行
                result = await self._execute_via_agent(task)
            elif self.agent:
                # 使用本地方法
                result = await self._execute_local(task)
            else:
                # 无 Agent 时模拟执行
                result = await self._execute_mock(task)

            task.result = result
            task.status = TaskStatus.COMPLETED
            task.end_time = datetime.now()

            await self.task_queue.mark_completed(task.task_id)
            logger.info(f"Task {task.name} completed in {task.duration_ms()}ms")

        except Exception as e:
            logger.error(f"Task {task.name} failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.end_time = datetime.now()
            await self.task_queue.mark_failed(task.task_id, str(e))

        return task

    async def _execute_via_agent(self, task: Task) -> Any:
        """通过 Agent 的工具执行任务"""
        # 检查工具是否存在
        tool_name = task.name
        if not hasattr(self.agent.react_agent, 'tool_registry'):
            return await self._execute_local(task)

        registry = self.agent.react_agent.tool_registry
        if not hasattr(registry, 'get_tool') or not registry.get_tool(tool_name):
            # 工具不存在，使用本地执行
            return await self._execute_local(task)

        # 获取工具执行器
        tool_executor = registry.get_tool(tool_name)
        if tool_executor:
            try:
                # 执行工具
                result = await tool_executor(**task.input_data)
                return result
            except Exception as e:
                logger.warning(f"Tool execution failed: {e}, falling back to local")
                return await self._execute_local(task)

        return await self._execute_local(task)

    async def _execute_local(self, task: Task) -> Any:
        """本地执行任务"""
        # 根据任务类型调用不同的处理方法
        if task.task_type == "search":
            return await self._execute_search(task)
        elif task.task_type == "query":
            return await self._execute_query(task)
        elif task.task_type == "plan":
            return await self._execute_plan(task)
        elif task.task_type == "calculate":
            return await self._execute_calculate(task)
        elif task.task_type == "recommend":
            return await self._execute_recommend(task)
        else:
            return await self._execute_general(task)

    async def _execute_mock(self, task: Task) -> Any:
        """模拟执行任务（返回占位结果）"""
        return {
            "status": "mock_executed",
            "task": task.name,
            "message": f"Task '{task.name}' executed in mock mode",
            "input": task.input_data
        }

    async def _execute_search(self, task: Task) -> Any:
        """执行搜索任务"""
        # 调用搜索相关工具
        return {"status": "search_completed", "task": task.name}

    async def _execute_query(self, task: Task) -> Any:
        """执行查询任务"""
        return {"status": "query_completed", "task": task.name}

    async def _execute_plan(self, task: Task) -> Any:
        """执行规划任务"""
        return {"status": "plan_completed", "task": task.name}

    async def _execute_calculate(self, task: Task) -> Any:
        """执行计算任务"""
        return {"status": "calculate_completed", "task": task.name}

    async def _execute_recommend(self, task: Task) -> Any:
        """执行推荐任务"""
        return {"status": "recommend_completed", "task": task.name}

    async def _execute_general(self, task: Task) -> Any:
        """执行通用任务"""
        return {"status": "general_completed", "task": task.name}

    def _is_critical_task(self, task: Task) -> bool:
        """判断是否为关键任务"""
        critical_types = ["plan", "calculate"]
        return task.task_type in critical_types

    async def get_status(self) -> Dict[str, Any]:
        """获取工作流状态"""
        return {
            "queue_size": self.task_queue.size(),
            "pending_tasks": self.task_queue.get_pending_count(),
            "completed_tasks": self.task_queue.get_completed_count(),
            "is_running": self._executor is not None and not self._executor.done()
        }
