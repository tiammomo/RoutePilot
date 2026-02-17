"""
工作流引擎单元测试

测试任务分解、任务队列、执行计划和结果聚合功能。
"""

import pytest
import asyncio
from core.workflow_engine import (
    WorkflowEngine,
    TaskDecomposer,
    TaskQueue,
    ResultAggregator,
    Task,
    TaskStatus,
    TaskPriority,
    ExecutionPlan
)


class TestTask:
    """任务单元测试"""

    def test_task_creation(self):
        """测试任务创建"""
        task = Task(name="test_task", description="Test task")
        assert task.name == "test_task"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL

    def test_task_is_ready(self):
        """测试任务就绪判断"""
        task = Task(
            task_id="task_1",
            depends_on=["dep_1", "dep_2"]
        )
        # 依赖未完成
        assert not task.is_ready(set())
        # 部分依赖完成
        assert not task.is_ready({"dep_1"})
        # 全部依赖完成
        assert task.is_ready({"dep_1", "dep_2"})

    def test_task_duration(self):
        """测试任务执行时长计算"""
        from datetime import datetime
        task = Task()
        task.start_time = datetime.now()
        task.end_time = datetime.now()
        assert task.duration_ms() >= 0

    def test_task_to_dict(self):
        """测试任务序列化"""
        task = Task(name="test", description="desc")
        d = task.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "desc"
        assert d["status"] == "pending"


class TestTaskQueue:
    """任务队列单元测试"""

    @pytest.mark.asyncio
    async def test_enqueue(self):
        """测试入队"""
        queue = TaskQueue()
        task = Task(name="test")
        await queue.enqueue(task)
        assert queue.size() == 1

    @pytest.mark.asyncio
    async def test_dequeue(self):
        """测试出队"""
        queue = TaskQueue()
        task = Task(name="test")
        await queue.enqueue(task)

        dequeued = await queue.dequeue()
        assert dequeued.name == "test"
        assert dequeued.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_mark_completed(self):
        """测试标记完成"""
        queue = TaskQueue()
        task = Task(name="test")
        await queue.enqueue(task)

        await queue.mark_completed(task.task_id)
        assert task.task_id in queue._completed

    @pytest.mark.asyncio
    async def test_mark_failed(self):
        """测试标记失败"""
        queue = TaskQueue()
        task = Task(name="test", depends_on=["dep_1"])
        await queue.enqueue(task)

        await queue.mark_failed("dep_1", "Error")
        # 依赖失败，当前任务应该被取消
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_priority_order(self):
        """测试优先级排序"""
        queue = TaskQueue()
        task1 = Task(name="low", priority=TaskPriority.LOW)
        task2 = Task(name="high", priority=TaskPriority.HIGH)
        task3 = Task(name="urgent", priority=TaskPriority.URGENT)

        await queue.enqueue(task1)
        await queue.enqueue(task2)
        await queue.enqueue(task3)

        first = await queue.dequeue()
        assert first.name == "urgent"

    @pytest.mark.asyncio
    async def test_dependency_ready(self):
        """测试依赖就绪"""
        queue = TaskQueue()
        task1 = Task(task_id="t1")
        task2 = Task(task_id="t2", depends_on=["t1"])

        await queue.enqueue(task1)
        await queue.enqueue(task2)

        # task2 依赖 task1，task1 未完成时 task2 不能出队
        dequeued = await queue.dequeue()
        assert dequeued.task_id == "t1"

        # task1 完成后，task2 才能出队
        await queue.mark_completed("t1")
        dequeued = await queue.dequeue()
        assert dequeued.task_id == "t2"


class TestTaskDecomposer:
    """任务分解器单元测试"""

    def test_initialization(self):
        """测试初始化"""
        decomposer = TaskDecomposer()
        assert decomposer.use_llm_decompose is False

    @pytest.mark.asyncio
    async def test_rule_based_decompose_trip(self):
        """测试基于规则的多日游分解"""
        decomposer = TaskDecomposer()
        tasks = await decomposer.decompose("帮我规划北京三日游")

        assert len(tasks) > 0
        assert tasks[0].name is not None

    @pytest.mark.asyncio
    async def test_rule_based_decompose_budget(self):
        """测试预算任务分解"""
        decomposer = TaskDecomposer()
        tasks = await decomposer.decompose("预算5000元够吗")

        assert len(tasks) > 0
        # 预算任务应该包含 calculate_budget
        task_names = [t.name for t in tasks]
        assert any("budget" in name or "calculate" in name for name in task_names)

    @pytest.mark.asyncio
    async def test_rule_based_decompose_attractions(self):
        """测试景点推荐分解"""
        decomposer = TaskDecomposer()
        tasks = await decomposer.decompose("有哪些好玩的景点")

        assert len(tasks) > 0

    def test_compute_execution_order(self):
        """测试执行顺序计算"""
        decomposer = TaskDecomposer()

        task1 = Task(task_id="t1")
        task2 = Task(task_id="t2", depends_on=["t1"])
        task3 = Task(task_id="t3", depends_on=["t1"])
        task4 = Task(task_id="t4", depends_on=["t2", "t3"])

        tasks = [task1, task2, task3, task4]
        order = decomposer.compute_execution_order(tasks)

        # t1 应该在第一层
        assert "t1" in order[0]
        # t2, t3 应该在第二层
        assert "t2" in order[1] or "t3" in order[1]
        # t4 应该在第三层
        assert "t4" in order[2]

    def test_task_type_mapping(self):
        """测试任务类型映射"""
        decomposer = TaskDecomposer()
        assert decomposer._get_task_type("search_cities") == "search"
        assert decomposer._get_task_type("query_attractions") == "query"
        assert decomposer._get_task_type("generate_route") == "plan"
        assert decomposer._get_task_type("calculate_budget") == "calculate"
        assert decomposer._get_task_type("generate_recommendation") == "recommend"


class TestResultAggregator:
    """结果聚合器单元测试"""

    def test_initialization(self):
        """测试初始化"""
        aggregator = ResultAggregator()
        assert aggregator.aggregation_strategy == "template"

        aggregator2 = ResultAggregator(aggregation_strategy="merge")
        assert aggregator2.aggregation_strategy == "merge"

    @pytest.mark.asyncio
    async def test_template_aggregate(self):
        """测试模板聚合"""
        from datetime import datetime

        aggregator = ResultAggregator(aggregation_strategy="template")

        tasks = [
            Task(
                name="get_city_info",
                task_type="query",
                status=TaskStatus.COMPLETED,
                result="北京是中国的首都",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            Task(
                name="generate_route",
                task_type="plan",
                status=TaskStatus.COMPLETED,
                result="Day 1: 天安门广场",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ]

        result = await aggregator.aggregate(tasks, "北京三日游")

        assert result["success"] is True
        assert "answer" in result
        assert result["metadata"]["total_tasks"] == 2
        assert result["metadata"]["completed_tasks"] == 2

    @pytest.mark.asyncio
    async def test_sequential_aggregate(self):
        """测试顺序聚合"""
        from datetime import datetime

        aggregator = ResultAggregator(aggregation_strategy="sequential")

        tasks = [
            Task(name="task1", status=TaskStatus.COMPLETED, result="Result 1"),
            Task(name="task2", status=TaskStatus.COMPLETED, result="Result 2")
        ]

        result = await aggregator.aggregate(tasks, "test")

        assert result["success"] is True
        assert "Result 1" in result["answer"]
        assert "Result 2" in result["answer"]

    @pytest.mark.asyncio
    async def test_merge_aggregate(self):
        """测试合并聚合"""
        from datetime import datetime

        aggregator = ResultAggregator(aggregation_strategy="merge")

        tasks = [
            Task(
                name="task1",
                status=TaskStatus.COMPLETED,
                result={"key1": "value1"}
            ),
            Task(
                name="task2",
                status=TaskStatus.COMPLETED,
                result={"key2": "value2"}
            )
        ]

        result = await aggregator.aggregate(tasks, "test")

        assert result["success"] is True
        assert "key1" in result["merged_data"]
        assert "key2" in result["merged_data"]

    @pytest.mark.asyncio
    async def test_aggregate_with_failed_task(self):
        """测试有失败任务的聚合"""
        from datetime import datetime

        aggregator = ResultAggregator()

        tasks = [
            Task(
                name="success_task",
                status=TaskStatus.COMPLETED,
                result="Success",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            Task(
                name="failed_task",
                status=TaskStatus.FAILED,
                error="Some error"
            )
        ]

        result = await aggregator.aggregate(tasks, "test")

        assert result["metadata"]["completed_tasks"] == 1
        assert result["metadata"]["failed_tasks"] == 1


class TestWorkflowEngine:
    """工作流引擎单元测试"""

    def test_initialization(self):
        """测试初始化"""
        engine = WorkflowEngine(agent=None)
        assert engine.agent is None
        assert engine.max_concurrent == 3
        assert engine.enable_parallel is True

    def test_initialization_custom(self):
        """测试自定义初始化"""
        engine = WorkflowEngine(agent=None, max_concurrent=5, enable_parallel=False)
        assert engine.max_concurrent == 5
        assert engine.enable_parallel is False

    @pytest.mark.asyncio
    async def test_execute_plan_with_none_agent(self):
        """测试无 Agent 的工作流执行"""
        engine = WorkflowEngine(agent=None)

        # 使用一个会创建默认任务但没有 agent 的场景
        result = await engine.execute_plan("随便什么")

        # 应该能够执行，但因为没有 agent，结果可能不完整
        assert "success" in result
        assert "answer" in result

    @pytest.mark.asyncio
    async def test_get_status(self):
        """测试状态获取"""
        engine = WorkflowEngine(agent=None)
        status = await engine.get_status()

        assert "queue_size" in status
        assert "pending_tasks" in status
        assert "completed_tasks" in status
        assert "is_running" in status


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流"""
        from datetime import datetime

        # 1. 任务分解
        decomposer = TaskDecomposer()
        tasks = await decomposer.decompose("北京三日游推荐")

        assert len(tasks) > 0

        # 2. 计算执行顺序
        execution_order = decomposer.compute_execution_order(tasks)
        assert len(execution_order) > 0

        # 3. 任务队列
        queue = TaskQueue()
        await queue.enqueue_batch(tasks)

        executed = []
        while not queue.is_empty():
            task = await queue.dequeue()
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = f"Executed: {task.name}"
                task.start_time = datetime.now()
                task.end_time = datetime.now()
                await queue.mark_completed(task.task_id)
                executed.append(task)

        assert len(executed) > 0

        # 4. 结果聚合
        aggregator = ResultAggregator()
        result = await aggregator.aggregate(executed, "北京三日游推荐")

        assert result["success"] is True
        assert result["metadata"]["completed_tasks"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
