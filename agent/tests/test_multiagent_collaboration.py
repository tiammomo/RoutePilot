"""
Collaboration 组件单元测试
"""

import pytest
from multiagent.collaboration.task_distributor import TaskDistributor, TaskAssignment
from multiagent.collaboration.result_merger import ResultMerger, MergedResult
from multiagent.roles.planner import ExecutionPlan, SubTask, PlanComplexity
from multiagent.roles.specialist import TaskResult, TaskStatus


class TestTaskDistributor:
    """任务分发器测试"""

    def test_initialization(self):
        """测试初始化"""
        distributor = TaskDistributor()
        assert len(distributor._assignments) == 0

    def test_distribute(self):
        """测试分发任务"""
        distributor = TaskDistributor()

        plan = ExecutionPlan(
            plan_id="plan-1",
            original_request="测试请求",
            complexity=PlanComplexity.SIMPLE,
            tasks=[
                SubTask(task_id="task_1", description="任务1", required_tools=["tool1"]),
                SubTask(task_id="task_2", description="任务2", required_tools=["tool2"])
            ]
        )

        assignments = distributor.distribute(plan)
        assert len(assignments) == 2
        assert assignments[0].task_id == "task_1"

    def test_get_assignment(self):
        """测试获取任务分配"""
        distributor = TaskDistributor()

        plan = ExecutionPlan(
            plan_id="plan-1",
            original_request="测试",
            complexity=PlanComplexity.SIMPLE,
            tasks=[
                SubTask(task_id="task_1", description="任务1", required_tools=[])
            ]
        )

        distributor.distribute(plan)
        assignment = distributor.get_assignment("task_1")

        assert assignment is not None
        assert assignment.task_id == "task_1"

    def test_get_workload_stats(self):
        """测试获取工作负载统计"""
        distributor = TaskDistributor()

        plan = ExecutionPlan(
            plan_id="plan-1",
            original_request="测试",
            complexity=PlanComplexity.SIMPLE,
            tasks=[
                SubTask(task_id="task_1", description="任务1", required_tools=[])
            ]
        )

        distributor.distribute(plan)
        stats = distributor.get_workload_stats()

        assert len(stats) > 0


class TestResultMerger:
    """结果合并器测试"""

    def test_initialization(self):
        """测试初始化"""
        merger = ResultMerger(merge_strategy="sequential")
        assert merger.merge_strategy == "sequential"

    @pytest.mark.asyncio
    async def test_merge_empty(self):
        """测试合并空结果"""
        merger = ResultMerger()
        result = await merger.merge([])

        assert result.success is False

    @pytest.mark.asyncio
    async def test_merge_single_result(self):
        """测试合并单个结果"""
        merger = ResultMerger()

        task_results = [
            TaskResult(
                task_id="task_1",
                status=TaskStatus.COMPLETED,
                result="test result"
            )
        ]

        merged = await merger.merge(task_results)
        assert merged.success is True
        assert merged.combined_output == "test result"

    @pytest.mark.asyncio
    async def test_merge_multiple_results(self):
        """测试合并多个结果"""
        merger = ResultMerger(merge_strategy="sequential")

        task_results = [
            TaskResult(task_id="task_1", status=TaskStatus.COMPLETED, result="result 1"),
            TaskResult(task_id="task_2", status=TaskStatus.COMPLETED, result="result 2")
        ]

        merged = await merger.merge(task_results)
        assert merged.success is True
        assert "result 1" in merged.combined_output

    @pytest.mark.asyncio
    async def test_merge_with_failures(self):
        """测试合并包含失败的结果"""
        merger = ResultMerger()

        task_results = [
            TaskResult(task_id="task_1", status=TaskStatus.COMPLETED, result="ok"),
            TaskResult(task_id="task_2", status=TaskStatus.FAILED, error="error occurred")
        ]

        merged = await merger.merge(task_results)
        assert merged.success is False

    def test_combine_sequential(self):
        """测试顺序组合"""
        merger = ResultMerger(merge_strategy="sequential")

        task_results = [
            TaskResult(task_id="task_1", status=TaskStatus.COMPLETED, result="first"),
            TaskResult(task_id="task_2", status=TaskStatus.COMPLETED, result="second")
        ]

        combined = merger._combine_outputs(task_results)
        assert "first" in combined
        assert "second" in combined

    def test_combine_parallel(self):
        """测试并行组合"""
        merger = ResultMerger(merge_strategy="parallel")

        task_results = [
            TaskResult(task_id="task_1", status=TaskStatus.COMPLETED, result="result 1"),
            TaskResult(task_id="task_2", status=TaskStatus.COMPLETED, result="result 2")
        ]

        combined = merger._combine_outputs(task_results)
        assert isinstance(combined, dict)
        assert "task_1" in combined

    def test_generate_summary(self):
        """测试生成摘要"""
        merger = ResultMerger()

        task_results = [
            TaskResult(task_id="task_1", status=TaskStatus.COMPLETED, result="ok", execution_time=1.5),
            TaskResult(task_id="task_2", status=TaskStatus.FAILED, result="fail", execution_time=0.5)
        ]

        summary = merger._generate_summary(task_results)
        assert summary["total_tasks"] == 2
        assert summary["completed"] == 1
        assert summary["failed"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
