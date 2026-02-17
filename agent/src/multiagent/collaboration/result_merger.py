"""
================================================================================
Result Merger - 结果合并器

负责将多个 Agent 的执行结果合并为统一输出。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from multiagent.roles.specialist import TaskResult, TaskStatus
from multiagent.roles.supervisor import ReviewResult, ReviewStatus

logger = logging.getLogger(__name__)


@dataclass
class MergedResult:
    """合并后的结果"""
    success: bool
    combined_output: Any
    task_results: List[TaskResult] = field(default_factory=list)
    review_results: List[ReviewResult] = field(default_factory=list)
    execution_summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResultMerger:
    """结果合并器

    负责：
    - 收集多个 Agent 的结果
    - 根据依赖关系排序
    - 合并为统一输出
    - 生成执行摘要
    """

    def __init__(self, merge_strategy: str = "sequential"):
        """
        Args:
            merge_strategy: 合并策略 (sequential, parallel, hierarchical)
        """
        self.merge_strategy = merge_strategy

    async def merge(
        self,
        task_results: List[TaskResult],
        review_results: Optional[List[ReviewResult]] = None
    ) -> MergedResult:
        """合并结果

        Args:
            task_results: 任务结果列表
            review_results: 审核结果列表（可选）

        Returns:
            合并后的结果
        """
        if not task_results:
            return MergedResult(
                success=False,
                combined_output=None,
                execution_summary={"error": "No results to merge"}
            )

        # 检查是否有失败的任务
        failed_tasks = [t for t in task_results if t.status == TaskStatus.FAILED]
        task_success = len(failed_tasks) == 0

        # 合并输出
        combined_output = self._combine_outputs(task_results)

        # 生成执行摘要
        summary = self._generate_summary(task_results)

        # 收集审核结果
        reviews = review_results or []
        approval_count = 0

        # 如果有审核结果，检查是否通过
        if reviews:
            approval_count = sum(1 for r in reviews if r.status == ReviewStatus.APPROVED)
            success = task_success and approval_count > 0
        else:
            # 没有审核结果时，仅根据任务成功与否判断
            success = task_success

        result = MergedResult(
            success=success,
            combined_output=combined_output,
            task_results=task_results,
            review_results=reviews,
            execution_summary=summary,
            metadata={
                "total_tasks": len(task_results),
                "successful_tasks": len(task_results) - len(failed_tasks),
                "failed_tasks": len(failed_tasks),
                "reviewed_tasks": len(reviews),
                "approved_tasks": approval_count
            }
        )

        logger.info(f"Merged {len(task_results)} results, success: {result.success}")
        return result

    def _combine_outputs(self, task_results: List[TaskResult]) -> Any:
        """组合输出"""
        if len(task_results) == 1:
            return task_results[0].result

        # 根据合并策略组合
        if self.merge_strategy == "sequential":
            return self._combine_sequential(task_results)
        elif self.merge_strategy == "parallel":
            return self._combine_parallel(task_results)
        else:
            return self._combine_hierarchical(task_results)

    def _combine_sequential(self, task_results: List[TaskResult]) -> str:
        """顺序组合"""
        outputs = []
        for result in task_results:
            if result.result:
                outputs.append(str(result.result))

        return "\n\n".join(outputs)

    def _combine_parallel(self, task_results: List[TaskResult]) -> Dict[str, Any]:
        """并行组合"""
        combined = {}
        for result in task_results:
            combined[result.task_id] = result.result
        return combined

    def _combine_hierarchical(self, task_results: List[TaskResult]) -> Dict[str, Any]:
        """分层组合"""
        # 按任务 ID 组织结果
        return {
            "results": {r.task_id: r.result for r in task_results},
            "by_status": {
                "completed": [r.task_id for r in task_results if r.status == TaskStatus.COMPLETED],
                "failed": [r.task_id for r in task_results if r.status == TaskStatus.FAILED]
            }
        }

    def _generate_summary(self, task_results: List[TaskResult]) -> Dict[str, Any]:
        """生成执行摘要"""
        total_time = sum(r.execution_time for r in task_results)
        completed = len([r for r in task_results if r.status == TaskStatus.COMPLETED])
        failed = len([r for r in task_results if r.status == TaskStatus.FAILED])

        return {
            "total_tasks": len(task_results),
            "completed": completed,
            "failed": failed,
            "total_execution_time": round(total_time, 2),
            "average_task_time": round(total_time / len(task_results), 2) if task_results else 0
        }

    async def merge_by_dependency(
        self,
        task_results: List[TaskResult],
        dependencies: Dict[str, List[str]]
    ) -> MergedResult:
        """按依赖关系合并

        Args:
            task_results: 任务结果
            dependencies: 任务依赖关系

        Returns:
            合并后的结果
        """
        # 构建依赖图
        result_map = {r.task_id: r for r in task_results}

        # 拓扑排序
        ordered = self._topological_sort(result_map, dependencies)

        # 按顺序合并
        ordered_results = [result_map[tid] for tid in ordered if tid in result_map]

        return await self.merge(ordered_results)

    def _topological_sort(
        self,
        result_map: Dict[str, TaskResult],
        dependencies: Dict[str, List[str]]
    ) -> List[str]:
        """拓扑排序"""
        in_degree = {tid: 0 for tid in result_map}

        # 计算入度
        for tid, deps in dependencies.items():
            if tid in in_degree:
                in_degree[tid] = len(deps)

        # 找到入度为 0 的节点
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        ordered = []

        while queue:
            node = queue.pop(0)
            ordered.append(node)

            # 更新依赖该节点的任务
            for tid, deps in dependencies.items():
                if node in deps:
                    in_degree[tid] -= 1
                    if in_degree[tid] == 0:
                        queue.append(tid)

        return ordered
