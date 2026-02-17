"""
================================================================================
旅游助手应用层 (Application Layer)

基于五层架构的旅游助手入口，实现节点化工作流编排。

架构说明:
- 应用层: 旅游问答、ReAct对话入口
- 算法层: RAG检索、向量搜索
- 中间件层: 文档解析、检索排序
- 框架层: Agent引擎、状态管理、节点类型
- 基础设施层: LLM服务、配置管理、记忆管理

工作流程:
1. 输入: 用户问题
2. 决策节点: 判断问题类型
3A. 简单对话 -> LLM直接回答
3B. 数据查询 -> 元数据提取 -> Agent循环 -> 答案生成

================================================================================
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime

from framework.state_manager import StateManager, WorkflowStatus
from framework.node_types import (
    NodeCategory, NodeStatus, NodeResult, NodeConfig,
    ActionNode, AgentNode, DecisionNode, LoopNode,
    PreparationNode, PersistenceNode
)
from core.travel_tools import create_travel_tools
from core.response_generator import ResponseGenerator
from core.exceptions import handle_exceptions, ErrorContext
from config.config_manager import ConfigManager
from memory.manager import MemoryManager
from llm.client import LLMClient

logger = logging.getLogger(__name__)


class TravelApplication:
    """
    旅游助手应用

    基于五层架构的统一入口，协调各层组件工作。

    Attributes:
        config_manager: 配置管理器
        memory_manager: 记忆管理器
        llm_client: LLM客户端
        state_manager: 状态管理器
        response_generator: 响应生成器
    """

    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """
        初始化应用

        Args:
            config_path: 配置文件路径
        """
        # 基础设施层
        self.config_manager = ConfigManager(config_path)
        self.llm_client = LLMClient(self.config_manager.get_default_model_config())
        self.memory_manager = MemoryManager(
            max_working_memory=self.config_manager.agent_config.get('max_working_memory', 10)
        )

        # 框架层
        self.state_manager = StateManager()
        self.response_generator = ResponseGenerator(self.llm_client)

        # 工具注册
        self.tools = create_travel_tools(self.config_manager)

        # 节点注册表
        self._node_registry: Dict[str, Any] = {}

        # 注册节点
        self._register_nodes()

        logger.info("[TravelApplication] 初始化完成")

    def _register_nodes(self) -> None:
        """注册节点到注册表"""
        # 注册工具执行器
        for tool_info, executor in self.tools:
            self._node_registry[tool_info.name] = executor

    async def process(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入

        工作流:
        1. 初始化状态
        2. 决策问题类型
        3. 根据类型执行不同分支

        Args:
            user_input: 用户输入

        Returns:
            Dict: 处理结果
        """
        self.state_manager.status = WorkflowStatus.RUNNING

        try:
            # 步骤1: 初始化上下文
            context = await self._init_context(user_input)

            # 步骤2: 决策问题类型
            is_complex = await self._decide_query_type(context)

            if is_complex:
                # 复杂查询分支
                result = await self._process_complex_query(context)
            else:
                # 简单对话分支
                result = await self._process_simple_query(context)

            self.state_manager.status = WorkflowStatus.COMPLETED
            return result

        except Exception as e:
            logger.error(f"[TravelApplication] 处理异常: {e}")
            self.state_manager.status = WorkflowStatus.FAILED
            return {
                "success": False,
                "error": str(e),
                "workflow_status": self.state_manager.status.value
            }

    async def _init_context(self, user_input: str) -> Dict[str, Any]:
        """初始化上下文"""
        context = {
            "input": user_input,
            "timestamp": datetime.now().isoformat(),
            "user_preference": self.memory_manager.get_user_preference(),
            "conversation_history": self.memory_manager.get_conversation_history()
        }

        # 更新状态
        self.state_manager.set_state("input", user_input)
        self.state_manager.set_state("context", context)

        # 添加到记忆
        self.memory_manager.add_message('user', user_input)

        self.state_manager.trace_execution("root", "context_init", {"input_length": len(user_input)})

        return context

    async def _decide_query_type(self, context: Dict[str, Any]) -> bool:
        """
        决策问题类型

        Returns:
            bool: True=复杂查询, False=简单对话
        """
        user_input = context.get('input', '')

        # 简单规则判断
        simple_indicators = ['你好', '在吗', '帮助', '谢谢', '再见']
        complex_indicators = ['旅游', '推荐', '攻略', '路线', '预算', '景点', '城市']

        # 检查是否为简单问候
        is_simple_greeting = any(ind in user_input for ind in simple_indicators) and len(user_input) < 20

        # 检查是否需要工具
        needs_tools = any(ind in user_input for ind in complex_indicators)

        is_complex = needs_tools and not is_simple_greeting

        # 记录决策
        self.state_manager.set_state("query_type", {
            "is_complex": is_complex,
            "is_simple_greeting": is_simple_greeting,
            "needs_tools": needs_tools
        })

        self.state_manager.trace_execution("decision", "query_type", {
            "is_complex": is_complex
        })

        return is_complex

    async def _process_simple_query(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理简单对话"""
        user_input = context.get('input', '')

        # 动作节点: LLM 对话
        self.state_manager.trace_execution("simple", "llm_start", {})

        result = self.llm_client.chat([
            {"role": "system", "content": "你是一个专业的旅游助手。"},
            {"role": "user", "content": user_input}
        ])

        answer = result.get('content', '抱歉，我没有理解您的意思。')

        # 添加助手回复到记忆
        self.memory_manager.add_message('assistant', answer)

        # 持久化节点: 保存结果
        self.state_manager.trace_execution("simple", "complete", {"answer_length": len(answer)})

        return {
            "success": True,
            "answer": answer,
            "mode": "direct",
            "query_type": "simple"
        }

    async def _process_complex_query(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理复杂查询"""
        user_input = context.get('input', '')
        history = []

        # 准备节点: 初始化
        self.state_manager.trace_execution("complex", "preparation", {})

        # 循环节点: ReAct 执行
        max_iterations = 10
        for i in range(max_iterations):
            iteration_data = {
                "iteration": i + 1
            }

            # 子节点1: 思考
            thought = await self._think_step(user_input, context, history)
            iteration_data["thought"] = thought

            # 子节点2: 行动选择
            action = await self._plan_step(user_input, context, history)

            if action is None:
                # 无需更多行动，跳过执行
                iteration_data["action"] = "none"
                iteration_data["result"] = "完成"
                history.append(iteration_data)
                break

            # 子节点3: 工具执行
            exec_result = await self._execute_step(action, context)
            iteration_data["action"] = action.get('tool_name', 'unknown')
            iteration_data["result"] = exec_result
            history.append(iteration_data)

            # 检查是否完成
            if self._check_completion(exec_result):
                break

        # 生成最终答案
        answer = await self._generate_final_answer(context, history)

        # 持久化结果
        self.state_manager.trace_execution("complex", "complete", {
            "iterations": len(history),
            "answer_length": len(answer)
        })

        return {
            "success": True,
            "answer": answer,
            "mode": "react",
            "iterations": len(history),
            "history": history,
            "workflow_id": self.state_manager.workflow_id
        }

    async def _think_step(
        self,
        user_input: str,
        context: Dict,
        history: List[Dict]
    ) -> str:
        """思考步骤"""
        # 分析用户意图
        recent_history = [h.get('result', {}) for h in history[-3:] if h.get('result')]

        thought_prompt = f"""用户请求: {user_input}

历史上下文: {recent_history}

请分析:
1. 用户想要什么信息？
2. 需要使用哪些工具？
3. 下一步应该做什么？

只返回分析结论。"""

        result = self.llm_client.chat([
            {"role": "system", "content": "你是旅游规划专家，擅长分析用户需求。"},
            {"role": "user", "content": thought_prompt}
        ])

        return result.get('content', '分析用户需求中...')

    async def _plan_step(
        self,
        user_input: str,
        context: Dict,
        history: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """规划步骤 - 选择要执行的工具"""
        # 检查是否需要更多工具
        if not history:
            # 首次调用，需要工具
            planning_prompt = f"""用户请求: {user_input}

请决定是否需要调用工具来回答这个问题。如果需要，返回 JSON:
{{"need_tool": true, "tool_name": "工具名", "parameters": {{...}}}}

如果不需要工具（可以直接回答），返回:
{{"need_tool": false, "reason": "原因"}}"""

            result = self.llm_client.chat([
                {"role": "system", "content": "你负责决定是否需要调用工具。"},
                {"role": "user", "content": planning_prompt}
            ])

            content = result.get('content', '')

            # 简单解析
            if '"need_tool": false' in content or 'need_tool' not in content.lower():
                return None

            # 尝试提取工具名
            import re
            tool_match = re.search(r'"tool_name":\s*"([^"]+)"', content)
            if tool_match:
                tool_name = tool_match.group(1)
                return {
                    "tool_name": tool_name,
                    "parameters": {"query": user_input}
                }

        return None

    async def _execute_step(
        self,
        action: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行步骤 - 调用工具"""
        tool_name = action.get('tool_name', '')
        params = action.get('parameters', {})

        # 查找工具
        executor = self._node_registry.get(tool_name)

        if executor is None:
            return {
                "success": False,
                "error": f"工具未找到: {tool_name}",
                "tool_name": tool_name
            }

        try:
            # 调用工具
            if callable(executor):
                result = executor(**params)
                if hasattr(result, '__await__'):
                    result = await result
            else:
                result = executor(params)

            return {
                "success": True,
                "output": result,
                "tool_name": tool_name
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_name": tool_name
            }

    def _check_completion(self, last_result: Dict) -> bool:
        """检查是否完成"""
        if not last_result.get('success', False):
            return True  # 失败也结束

        # 检查结果是否足够回答问题
        output = last_result.get('output', {})
        if isinstance(output, dict):
            has_content = output.get('success') or output.get('cities') or output.get('data')
            return bool(has_content)

        return bool(output)

    async def _generate_final_answer(
        self,
        context: Dict[str, Any],
        history: List[Dict]
    ) -> str:
        """生成最终答案"""
        user_input = context.get('input', '')

        # 收集工具结果
        tool_results = []
        for h in history:
            result = h.get('result', {})
            if result.get('success') and result.get('output'):
                tool_results.append({
                    "tool": result.get('tool_name'),
                    "result": result.get('output')
                })

        if not tool_results:
            # 无工具结果，直接回答
            direct_result = self.llm_client.chat([
                {"role": "system", "content": "你是一个专业的旅游助手。"},
                {"role": "user", "content": user_input}
            ])
            answer = direct_result.get('content', '抱歉，我没有找到相关信息。')
        else:
            # 使用响应生成器
            history_for_gen = [
                {'action': {'tool_name': t.get('tool'), 'result': t.get('result'), 'status': 'SUCCESS'}}
                for t in tool_results
            ]

            answer = await self.response_generator.generate_answer(history_for_gen)

        # 添加到记忆
        self.memory_manager.add_message('assistant', answer)

        return answer

    # ==================== 同步接口 ====================

    def process_sync(self, user_input: str) -> Dict[str, Any]:
        """同步处理接口"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.process(user_input))
        else:
            return loop.run_until_complete(self.process(user_input))

    def process_stream(
        self,
        user_input: str,
        callback=None
    ) -> Dict[str, Any]:
        """流式处理接口"""
        # 简化版本：直接返回同步结果
        result = self.process_sync(user_input)

        if callback:
            callback(result.get('answer', ''))

        return result

    # ==================== 统计和状态 ====================

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "workflow_id": self.state_manager.workflow_id,
            "status": self.state_manager.status.value,
            "registered_tools": list(self._node_registry.keys()),
            "memory_messages": len(self.memory_manager.get_conversation_history())
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "application": self.get_status(),
            "state": self.state_manager.get_stats()
        }

    def reset(self) -> None:
        """重置状态"""
        self.memory_manager.clear_conversation()
        self.state_manager.clear()
        self.state_manager.status = WorkflowStatus.IDLE


# ==================== 便捷函数 ====================

def create_travel_app(config_path: str = "config/llm_config.yaml") -> TravelApplication:
    """
    创建旅游应用实例

    Args:
        config_path: 配置文件路径

    Returns:
        TravelApplication: 应用实例
    """
    return TravelApplication(config_path)
