"""
================================================================================
Specialist Agent - 专家 Agent

负责特定领域任务的执行。
================================================================================
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SpecialistAgent:
    """Specialist Agent

    负责：
    - 执行特定领域的任务
    - 调用相关工具
    - 返回执行结果
    """

    def __init__(
        self,
        agent_id: str,
        domain: str,
        tools: Optional[Dict[str, Callable]] = None,
        llm_client: Optional[Any] = None
    ):
        """
        Args:
            agent_id: Agent ID
            domain: 专业领域 (search, planning, recommendation, etc.)
            tools: 工具函数字典
            llm_client: LLM 客户端
        """
        self.agent_id = agent_id
        self.domain = domain
        self.tools = tools or {}
        self.llm_client = llm_client

        # 任务状态
        self._current_task: Optional[str] = None
        self._task_history: List[TaskResult] = []

    def register_tool(self, name: str, func: Callable) -> None:
        """注册工具"""
        self.tools[name] = func
        logger.debug(f"Registered tool {name} for specialist {self.agent_id}")

    async def execute_task(
        self,
        task_id: str,
        task_description: str,
        parameters: Dict[str, Any]
    ) -> TaskResult:
        """执行任务

        Args:
            task_id: 任务 ID
            task_description: 任务描述
            parameters: 任务参数

        Returns:
            任务结果
        """
        import time

        self._current_task = task_id
        start_time = time.time()

        logger.info(f"Specialist {self.agent_id} executing task {task_id}: {task_description}")

        try:
            # 确定需要使用的工具
            tool_name = parameters.get("tool")
            tool_params = parameters.get("params", {})

            if tool_name and tool_name in self.tools:
                # 执行工具
                tool_func = self.tools[tool_name]

                if hasattr(tool_func, '__call__'):
                    # 异步调用
                    if hasattr(tool_func, '__aCoroutine__') or \
                       (hasattr(tool_func, '__code__') and tool_func.__code__.co_flags & 0x80):
                        result = await tool_func(**tool_params)
                    else:
                        result = tool_func(**tool_params)
                else:
                    result = tool_func

                execution_time = time.time() - start_time
                task_result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    result=result,
                    execution_time=execution_time,
                    metadata={"tool": tool_name, "domain": self.domain}
                )
            else:
                # 没有特定工具，使用 LLM 生成响应
                if self.llm_client:
                    result = await self._generate_llm_response(task_description, parameters)
                else:
                    result = f"Task {task_id} processed by {self.domain} specialist"

                execution_time = time.time() - start_time
                task_result = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.COMPLETED,
                    result=result,
                    execution_time=execution_time,
                    metadata={"domain": self.domain, "llm_used": True}
                )

            self._task_history.append(task_result)
            logger.info(f"Task {task_id} completed in {execution_time:.2f}s")

            return task_result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Task {task_id} failed: {e}")

            task_result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
                metadata={"domain": self.domain}
            )
            self._task_history.append(task_result)

            return task_result
        finally:
            self._current_task = None

    async def _generate_llm_response(
        self,
        task_description: str,
        parameters: Dict[str, Any]
    ) -> str:
        """使用 LLM 生成响应"""
        # 这里简化处理，实际需要调用 LLM
        prompt = parameters.get("prompt", task_description)
        return f"Generated response for: {prompt}"

    def get_capabilities(self) -> Dict[str, Any]:
        """获取能力信息"""
        return {
            "agent_id": self.agent_id,
            "domain": self.domain,
            "available_tools": list(self.tools.keys()),
            "current_task": self._current_task,
            "tasks_completed": len([t for t in self._task_history if t.status == TaskStatus.COMPLETED]),
            "tasks_failed": len([t for t in self._task_history if t.status == TaskStatus.FAILED])
        }

    def get_task_history(self) -> List[TaskResult]:
        """获取任务历史"""
        return self._task_history.copy()
