"""
Multi-Agent Collaboration

任务分发和结果合并模块。
"""

from multiagent.collaboration.task_distributor import TaskDistributor, TaskAssignment
from multiagent.collaboration.result_merger import ResultMerger, MergedResult

__all__ = [
    "TaskDistributor",
    "TaskAssignment",
    "ResultMerger",
    "MergedResult"
]
