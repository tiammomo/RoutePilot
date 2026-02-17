"""
================================================================================
Adaptive Workflow - 自适应工作流

根据任务复杂度动态选择执行策略。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度"""
    SIMPLE = "simple"       # 简单 - 直接回答
    MEDIUM = "medium"       # 中等 - 单 Agent + ReAct
    COMPLEX = "complex"     # 复杂 - 多 Agent 编排


class ExecutionStrategy(Enum):
    """执行策略"""
    DIRECT = "direct"           # 直接 LLM 回答
    REACT = "react"             # ReAct 推理
    WORKFLOW = "workflow"       # 工作流引擎
    MULTIAGENT = "multiagent"   # 多 Agent 编排


@dataclass
class TaskProfile:
    """任务画像"""
    original_request: str
    complexity: TaskComplexity
    estimated_steps: int
    requires_tools: List[str] = field(default_factory=list)
    requires_planning: bool = False
    requires_multiple_domains: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """执行结果"""
    strategy: ExecutionStrategy
    success: bool
    output: Any
    execution_time: float
    steps_taken: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class AdaptiveWorkflow:
    """自适应工作流

    根据任务特征动态选择最合适的执行策略。
    """

    # 复杂度关键词映射
    COMPLEXITY_KEYWORDS = {
        TaskComplexity.SIMPLE: ["推荐", "告诉", "查询", "什么是", "怎么"],
        TaskComplexity.MEDIUM: ["规划", "安排", "路线", "比较", "推荐"],
        TaskComplexity.COMPLEX: ["多日", "深度游", "完整行程", "详细规划", "综合"]
    }

    def __init__(
        self,
        direct_executor: Optional[Callable] = None,
        react_executor: Optional[Callable] = None,
        workflow_executor: Optional[Callable] = None,
        multiagent_executor: Optional[Callable] = None
    ):
        """
        Args:
            direct_executor: 直接执行器
            react_executor: ReAct 执行器
            workflow_executor: 工作流执行器
            multiagent_executor: 多 Agent 执行器
        """
        self.direct_executor = direct_executor
        self.react_executor = react_executor
        self.workflow_executor = workflow_executor
        self.multiagent_executor = multiagent_executor

    async def execute(self, user_request: str, **kwargs) -> ExecutionResult:
        """执行任务

        Args:
            user_request: 用户请求
            **kwargs: 额外参数

        Returns:
            执行结果
        """
        import time

        start_time = time.time()

        # 1. 评估任务复杂度
        profile = await self._assess_complexity(user_request)

        logger.info(f"Task complexity: {profile.complexity.value}, selecting strategy...")

        # 2. 选择执行策略
        strategy = self._select_strategy(profile)

        # 3. 执行
        result = await self._execute_with_strategy(strategy, user_request, profile, **kwargs)

        execution_time = time.time() - start_time

        return ExecutionResult(
            strategy=strategy,
            success=result.get("success", False),
            output=result.get("output"),
            execution_time=execution_time,
            steps_taken=result.get("steps", 1),
            metadata={
                "task_profile": {
                    "complexity": profile.complexity.value,
                    "estimated_steps": profile.estimated_steps
                }
            }
        )

    async def _assess_complexity(self, request: str) -> TaskProfile:
        """评估任务复杂度"""
        import re

        # 检查关键词
        complexity = TaskComplexity.SIMPLE
        for key, keywords in self.COMPLEXITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in request:
                    complexity = key
                    break
            if complexity != TaskComplexity.SIMPLE:
                break

        # 检查是否需要工具
        tool_keywords = ["搜索", "查询", "计算", "规划", "推荐"]
        requires_tools = any(kw in request for kw in tool_keywords)

        # 检查是否需要多域
        multi_domain_keywords = ["和", "以及", "还是", "或者"]
        requires_multiple_domains = any(kw in request for kw in multi_domain_keywords)

        # 检查是否需要规划
        planning_keywords = ["计划", "安排", "规划", "方案"]
        requires_planning = any(kw in request for kw in planning_keywords)

        # 估算步骤数
        if complexity == TaskComplexity.SIMPLE:
            estimated_steps = 1
        elif complexity == TaskComplexity.MEDIUM:
            estimated_steps = 3 if requires_tools else 2
        else:
            estimated_steps = 5 if requires_planning else 4

        return TaskProfile(
            original_request=request,
            complexity=complexity,
            estimated_steps=estimated_steps,
            requires_tools=requires_tools,
            requires_planning=requires_planning,
            requires_multiple_domains=requires_multiple_domains
        )

    def _select_strategy(self, profile: TaskProfile) -> ExecutionStrategy:
        """选择执行策略"""
        # 简单任务：直接 LLM
        if profile.complexity == TaskComplexity.SIMPLE:
            return ExecutionStrategy.DIRECT

        # 中等复杂度：ReAct 或工作流
        if profile.complexity == TaskComplexity.MEDIUM:
            if profile.requires_planning:
                return ExecutionStrategy.WORKFLOW
            return ExecutionStrategy.REACT

        # 复杂任务：多 Agent 编排
        return ExecutionStrategy.MULTIAGENT

    async def _execute_with_strategy(
        self,
        strategy: ExecutionStrategy,
        request: str,
        profile: TaskProfile,
        **kwargs
    ) -> Dict[str, Any]:
        """使用指定策略执行"""
        if strategy == ExecutionStrategy.DIRECT:
            if self.direct_executor:
                return await self.direct_executor(request, **kwargs)
            return {"success": True, "output": "Direct mode not configured"}

        elif strategy == ExecutionStrategy.REACT:
            if self.react_executor:
                return await self.react_executor(request, **kwargs)
            return {"success": True, "output": "ReAct mode not configured"}

        elif strategy == ExecutionStrategy.WORKFLOW:
            if self.workflow_executor:
                return await self.workflow_executor(request, **kwargs)
            return {"success": True, "output": "Workflow mode not configured"}

        elif strategy == ExecutionStrategy.MULTIAGENT:
            if self.multiagent_executor:
                return await self.multiagent_executor(request, **kwargs)
            return {"success": True, "output": "Multiagent mode not configured"}

        return {"success": False, "output": "Unknown strategy"}
