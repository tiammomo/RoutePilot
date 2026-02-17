"""
================================================================================
ReAct 旅游助手 Agent - 核心实现模块
================================================================================

本模块实现了基于 ReAct (Reasoning and Acting) 模式的旅游智能体。

功能概述：
- 提供完整的旅游相关工具集（城市搜索、景点查询、路线规划、预算计算等）
- 集成 LLM 进行自然语言理解和回答生成
- 支持同步和流式两种处理模式
- 维护对话历史和用户偏好

ReAct 模式流程：
1. 接收用户输入，分析意图
2. 选择合适的工具执行
3. 收集工具执行结果
4. 使用 LLM 生成最终回答

核心组件：
- create_travel_tools: 旅游工具工厂函数
- 工具执行函数: _search_cities, _query_attractions, _generate_route 等
- ReActTravelAgent: 旅游助手主类

使用示例：
```python
agent = ReActTravelAgent(config_path="config/llm_config.yaml")
result = await agent.process("北京三日游推荐")
```

================================================================================
"""

import json
import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

# 注意：Python 路径应在启动脚本（run_agent.py）中统一配置
# 本模块使用绝对导入，请确保运行时 PYTHONPATH 包含 agent 目录
# 例如：sys.path.insert(0, '/path/to/Shuai-Travel-Agent/agent')

from core.react_agent import ReActAgent, ToolInfo, Action, Thought, AgentState, ActionStatus
from core.style_config import style_manager, ReplyStyle, StyleConfig
from core.intent_recognizer import intent_recognizer, IntentRecognizer, IntentResult, IntentType, SentimentType
from core.decision_engine import decision_engine, DecisionEngine, Decision, DecisionType, ContextInfo
from core.travel_tools import create_travel_tools
from core.extended_tools import create_extended_tools  # v2.3.0 新增
from core.workflow_engine import WorkflowEngine  # v2.3.0 新增
from core.response_generator import ResponseGenerator, ReasoningBuilder
from config.config_manager import ConfigManager
from memory.manager import MemoryManager
from memory.factory import create_memory_orchestrator  # v2.1 统一记忆协调器
from llm.client import LLMClient
from enum import Enum

# 导入依赖注入容器（可选）
try:
    from di import Container, get_container
    DI_AVAILABLE = True
except ImportError:
    DI_AVAILABLE = False


class ChatMode(Enum):
    """对话模式枚举"""
    DIRECT = "direct"       # 直接调用 LLM
    REACT = "react"         # ReAct 推理模式
    PLAN = "plan"           # 规划后执行模式


# ==============================================================================
# ReAct 旅游助手主类
# ==============================================================================

class ReActTravelAgent:
    """
    ReAct 旅游助手 Agent

    该类是旅游助手的核心入口，协调以下组件工作：
    1. ReActAgent: 负责推理和工具调用的循环
    2. MemoryManager: 负责对话历史的存储和管理
    3. LLMClient: 负责与大语言模型通信
    4. ConfigManager: 负责配置信息的读取

    处理流程：
    1. 接收用户输入
    2. 调用 ReActAgent 执行推理循环
    3. 收集工具执行结果
    4. 使用 LLM 生成最终回答
    5. 返回结构化结果

    Attributes:
        config_manager: 配置管理器实例
        memory_manager: 对话历史管理器
        llm_client: LLM 客户端实例
        react_agent: ReAct 智能体实例

    Examples:
        >>> agent = ReActTravelAgent(config_path="config/llm_config.yaml")
        >>> result = await agent.process("北京三日游推荐")
        >>> print(result["answer"])
    """

    def __init__(
        self,
        config_path: str = "config/llm_config.yaml",
        model_id: Optional[str] = None,
        max_steps: int = 10,
        # 依赖注入参数（可选）
        config_manager: Optional[ConfigManager] = None,
        memory_manager: Optional[MemoryManager] = None,
        memory_orchestrator: Optional[Any] = None,  # 新增：统一记忆协调器
        llm_client: Optional[LLMClient] = None,
        container: Optional[Container] = None
    ):
        """
        初始化旅游助手

        Args:
            config_path: 配置文件路径
            model_id: 使用的模型 ID，为 None 则使用默认模型
            max_steps: ReAct 循环的最大执行步骤数
            config_manager: 外部传入的配置管理器（用于依赖注入）
            memory_manager: 外部传入的记忆管理器（用于依赖注入）
            memory_orchestrator: 外部传入的记忆协调器（v2.1 新增，用于统一管理所有记忆子系统）
            llm_client: 外部传入的 LLM 客户端（用于依赖注入）
            container: 依赖注入容器（可选）
        """
        # 使用依赖注入或创建新实例
        self._container = container or get_container()

        if config_manager:
            self.config_manager = config_manager
        else:
            self.config_manager = ConfigManager(config_path)

        # 记忆协调器优先，其次是 MemoryManager
        self.memory_orchestrator = memory_orchestrator
        if memory_orchestrator:
            # 使用统一的记忆协调器
            self.memory_manager = memory_orchestrator.memory_manager
            self._use_orchestrator = True
        elif memory_manager:
            self.memory_manager = memory_manager
            self._use_orchestrator = False
        else:
            # 初始化记忆管理器
            agent_config = self.config_manager.get_agent_config()
            memory_config = agent_config.get('memory', {}).get('working', {}).get('max_size', 10)
            self.memory_manager = MemoryManager(max_working_memory=memory_config)
            self._use_orchestrator = False

        if llm_client:
            self.llm_client = llm_client
        else:
            # 获取模型配置并初始化 LLM 客户端
            if model_id:
                llm_config = self.config_manager.get_model_config(model_id)
            else:
                llm_config = self.config_manager.get_default_model_config()
            self.llm_client = LLMClient(llm_config)

        # 初始化响应生成器
        self.response_generator = ResponseGenerator(self.llm_client)

        # v2.3.0 新增：初始化工作流引擎（用于 PLAN 模式）
        self.workflow_engine = WorkflowEngine(
            agent=self,
            max_concurrent=3,
            enable_parallel=True
        )

        # 传递 llm_client 给 ReActAgent，使其能使用 LLM 进行思考
        # 这是 ReAct 模式的关键：让智能体能够自主思考和规划
        self.react_agent = ReActAgent(
            name="TravelReActAgent",
            max_steps=max_steps,
            max_reasoning_depth=5,
            llm_client=self.llm_client
        )

        # 注册工具和回调
        self._register_tools()
        self._register_callbacks()

    def _register_tools(self) -> None:
        """
        注册旅游工具到 ReActAgent

        将 create_travel_tools 创建的所有工具注册到 ReActAgent 的工具注册表中。
        同时注册扩展工具（v2.3.0 新增）。
        """
        # 注册基础工具
        tools = create_travel_tools(self.config_manager)
        for tool_info, executor in tools:
            self.react_agent.register_tool(tool_info, executor)

        # v2.3.0 新增：注册扩展工具
        extended_tools = create_extended_tools(self.config_manager)
        for tool_info, executor in extended_tools:
            self.react_agent.register_tool(tool_info, executor)

    def _register_callbacks(self) -> None:
        """
        注册事件回调函数

        用于将 ReActAgent 的思考和行动事件同步到记忆管理器中，
        以便维护完整的对话历史。
        """
        def on_thought(thought: Thought):
            """思考事件回调：将思考内容添加到记忆"""
            self.memory_manager.add_message('assistant', f"[思考] {thought.content}")

        def on_action(action: Action):
            """行动事件回调：根据状态记录不同消息"""
            if action.status == ActionStatus.RUNNING:
                self.memory_manager.add_message('assistant', f"[行动] 执行工具: {action.tool_name}")
            elif action.status == ActionStatus.SUCCESS:
                self.memory_manager.add_message('assistant', f"[完成] {action.tool_name}")
            elif action.status == ActionStatus.FAILED:
                self.memory_manager.add_message('assistant', f"[失败] {action.tool_name}: {action.error}")

        self.react_agent.add_thought_callback(on_thought)
        self.react_agent.add_action_callback(on_action)

    async def process(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入（非流式版本）

        这是主要的处理入口，接收用户输入，执行完整的 ReAct 循环，
        并返回结构化的处理结果。

        Args:
            user_input: 用户的输入文本

        Returns:
            Dict: 处理结果，包含：
            - success: 是否成功
            - answer: 生成的回答
            - reasoning: 推理过程信息
            - history: 执行历史

        Examples:
            >>> result = await agent.process("云南旅游推荐")
            >>> if result["success"]:
            ...     print(result["answer"])
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[Agent] 开始处理用户输入: {user_input[:50]}...")

        try:
            # 1. 将用户输入添加到对话历史
            self.memory_manager.add_message('user', user_input)

            # 2. 构建上下文信息
            context = {
                'user_query': user_input,
                'user_preference': self.memory_manager.get_user_preference()
            }

            # 2.1 v2.2 增强: 使用记忆协调器获取丰富上下文
            if self._use_orchestrator and self.memory_orchestrator:
                try:
                    # 使用 attention_window 过滤关键消息
                    history = self.memory_manager.get_conversation_history()
                    if self.memory_orchestrator.attention_window and len(history) > 5:
                        # 获取当前查询相关的重要消息
                        relevant_history = self.memory_orchestrator.attention_window.select_top_messages(
                            history, user_input
                        )
                        context['conversation_history'] = relevant_history

                    # 使用 retrieval 检索相关历史
                    if self.memory_orchestrator.retrieval:
                        import asyncio
                        retrieved = asyncio.run(
                            self.memory_orchestrator.retrieval.retrieve(
                                session_id=getattr(self, '_current_session_id', 'default'),
                                user_id='default_user',
                                current_query=user_input,
                                top_k=2
                            )
                        )
                        if retrieved:
                            context['historical_context'] = [
                                {"role": "system", "content": f"[相关历史] {r.content}"}
                                for r in retrieved
                            ]
                except Exception as e:
                    logger.warning(f"Context enrichment failed: {e}")

            # 3. 执行 ReAct 推理循环
            result = await self.react_agent.run(user_input, context)
            logger.info(f"[Agent] ReAct 执行完成, success={result.get('success')}, steps={len(result.get('history', []))}")

            if result.get('success'):
                # 4. 提取结果
                history = result.get('history', [])
                reasoning_text = self._build_reasoning_text(history)
                answer = self._extract_answer(history)
                logger.info(f"[Agent] 提取到答案: {answer[:100]}...")

                # 5. 添加助手回答到历史
                self.memory_manager.add_message('assistant', answer)

                return {
                    "success": True,
                    "answer": answer,
                    "reasoning": {
                        "text": reasoning_text,
                        "total_steps": len(history),
                        "tools_used": self._extract_tools_used(history)
                    },
                    "history": history
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', '处理失败'),
                    "reasoning": None,
                    "history": result.get('history', [])
                }

        except Exception as e:
            logger.error(f"[Agent] 处理异常: {e}")
            return {
                "success": False,
                "error": f"处理失败: {str(e)}",
                "reasoning": None
            }

    def process_sync(self, user_input: str) -> Dict[str, Any]:
        """
        同步处理用户输入

        用于 gRPC 调用等需要同步接口的场景。
        内部通过 asyncio.run() 包装异步的 process 方法。

        Args:
            user_input: 用户输入文本

        Returns:
            Dict: 处理结果，同 process 方法的返回格式
        """
        import asyncio
        try:
            # 尝试获取现有事件循环
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环，可以安全使用 asyncio.run()
            return asyncio.run(self.process(user_input))
        else:
            # 已有事件循环运行中，使用 loop.run_until_complete()
            return loop.run_until_complete(self.process(user_input))

    async def process_stream(self, user_input: str, answer_callback=None, done_callback=None, thinking_callback=None):
        """
        流式处理用户输入

        使用真正的 token 级别流式输出，提供更好的用户体验。
        特点：
        - 实时输出：每个 token 生成后立即通过回调发送
        - 真正的流式：使用 LLM 客户端的 chat_stream 方法
        - 回调机制：通过回调函数实现数据推送

        Args:
            user_input: 用户输入
            answer_callback: 回答内容回调函数，接收单个 token (str)
            done_callback: 完成回调函数，接收最终结果 (Dict)
            thinking_callback: 思考内容回调函数，接收思考内容 (str) 和耗时 (float)

        Returns:
            Dict: 最终处理结果

        Examples:
            >>> async def on_token(token):
            ...     print(token, end="", flush=True)
            >>> async def on_done(result):
            ...     print("\\n完成!")
            >>> await agent.process_stream("北京旅游", answer_callback=on_token, done_callback=on_done)
        """
        import logging
        import time as time_module
        logger = logging.getLogger(__name__)

        logger.info(f"[Agent] 开始流式处理用户输入: {user_input[:50]}...")
        start_time = time_module.time()

        try:
            # 添加用户输入到历史
            self.memory_manager.add_message('user', user_input)

            context = {
                'user_query': user_input,
                'user_preference': self.memory_manager.get_user_preference()
            }

            # 先运行 ReAct agent 获取思考历史
            # 设置思考流式回调
            if hasattr(self.react_agent, 'set_think_stream_callback') and thinking_callback:
                self.react_agent.set_think_stream_callback(thinking_callback)

            result = await self.react_agent.run(user_input, context)
            logger.info(f"[Agent] ReAct 执行完成, success={result.get('success')}, steps={len(result.get('history', []))}")

            if result.get('success'):
                history = result.get('history', [])
                reasoning_text = self._build_reasoning_text(history)
                answer = self._extract_answer(history)

                self.memory_manager.add_message('assistant', answer)

                # 构建 LLM 消息
                system_prompt = """你是一个专业的旅游助手。请根据用户的问题，提供详细、准确的旅游建议和规划。回答要简洁明了，条理清晰。"""
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]

                logger.info(f"[Agent] 开始流式生成答案...")

                # 使用 LLM 客户端的流式方法
                if hasattr(self.llm_client, 'chat_stream'):
                    token_count = 0
                    accumulated_answer = ""

                    # 遍历流式响应
                    for token in self.llm_client.chat_stream(messages, temperature=0.7):
                        token_count += 1
                        accumulated_answer += token

                        # 立即发送每个 token
                        if answer_callback:
                            answer_callback(token)

                        # 短暂延迟，确保前端有足够时间处理
                        await asyncio.sleep(0.01)

                    answer = accumulated_answer
                    logger.info(f"[Agent] 流式生成完成, 共 {token_count} tokens")

                else:
                    # 回退到非流式
                    logger.warning("[Agent] LLM 客户端不支持流式，使用批量发送")
                    chunks = self._split_into_chunks(answer)
                    for chunk in chunks:
                        if answer_callback:
                            answer_callback(chunk)
                        await asyncio.sleep(0.02)

                elapsed = time_module.time() - start_time
                logger.info(f"[Agent] 总耗时: {elapsed:.2f}秒")

                final_result = {
                    "success": True,
                    "answer": answer,
                    "reasoning": {
                        "text": reasoning_text,
                        "total_steps": len(history),
                        "tools_used": self._extract_tools_used(history)
                    },
                    "history": history
                }

                if done_callback:
                    done_callback(final_result)

                return final_result
            else:
                final_result = {
                    "success": False,
                    "error": result.get('error', '处理失败'),
                    "reasoning": None,
                    "history": result.get('history', [])
                }
                if done_callback:
                    done_callback(final_result)
                return final_result

        except Exception as e:
            logger.error(f"[Agent] 处理异常: {e}")
            import traceback
            traceback.print_exc()
            error_result = {
                "success": False,
                "error": f"处理失败: {str(e)}",
                "reasoning": None
            }
            if done_callback:
                done_callback(error_result)
            return error_result

    def _split_into_chunks(self, text: str, chunk_size: int = 3) -> List[str]:
        """将文本拆分成小块用于流式输出"""
        return ResponseGenerator.split_into_chunks(text, chunk_size)

    def _build_reasoning_text(self, history: List[Dict]) -> str:
        """构建推理过程文本"""
        return ReasoningBuilder.build_reasoning_text(history)

    def _extract_tools_used(self, history: List[Dict]) -> List[str]:
        """提取使用的工具列表"""
        return ReasoningBuilder.extract_tools_used(history)

    def _extract_answer(self, history: List[Dict]) -> str:
        """
        提取最终回答

        从执行历史中提取最终的回答内容。
        策略：
        1. 收集所有成功的工具执行结果
        2. 使用 LLM 生成活泼、结构化的回答

        Args:
            history: 执行历史列表

        Returns:
            str: 最终回答文本
        """
        # 收集所有工具执行结果
        tool_results = []
        has_successful_tools = False

        for step in reversed(history):
            action = step.get('action', {})
            if action.get('status') == 'SUCCESS':
                has_successful_tools = True
                result = action.get('result', {})
                tool_name = action.get('tool_name', '')
                if result:
                    tool_results.append({
                        'tool': tool_name,
                        'result': result
                    })

        # 如果有工具执行结果，使用 LLM 生成活泼的回答
        if has_successful_tools:
            return self._generate_answer(history)

        # 否则返回默认消息
        return '让我来帮你规划这次旅行吧！🎉'

    def _format_attractions_response(self, tool_result: Dict) -> str:
        """格式化景点响应数据"""
        return self.response_generator._format_attractions_response(tool_result)

    def _generate_answer(self, history: List[Dict], intent: IntentResult = None) -> str:
        """使用 LLM 生成最终回答"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.response_generator.generate_answer(history, intent))
        else:
            return loop.run_until_complete(self.response_generator.generate_answer(history, intent))

    def _format_attractions_response(self, tool_result: Dict) -> str:
        """
        获取对话历史

        Returns:
            list: 对话消息列表
        """
        return self.memory_manager.get_conversation_history()

    def clear_conversation(self, session_id: str = "default") -> None:
        """
        清除对话历史

        清空记忆管理器和 ReActAgent 的状态，准备接受新会话。
        如果使用 MemoryOrchestrator，会触发会话结束归档流程。

        Args:
            session_id: 会话 ID (v2.1 新增)
        """
        # 使用 orchestrator 进行带归档的清除
        if self._use_orchestrator and self.memory_orchestrator:
            # 获取当前 session_id
            session_state = self.memory_manager.get_session_state("session_id", "default")
            try:
                self.memory_orchestrator.end_session(session_state, "default_user")
            except Exception:
                pass

        self.memory_manager.clear_conversation()
        self.react_agent.reset()

    def set_memory_orchestrator(
        self,
        orchestrator: Any,
        session_id: str = "default"
    ) -> None:
        """
        设置记忆协调器

        可以在初始化后单独设置记忆协调器，用于启用高级记忆功能。

        Args:
            orchestrator: MemoryOrchestrator 实例
            session_id: 当前会话 ID
        """
        self.memory_orchestrator = orchestrator
        self.memory_manager = orchestrator.memory_manager
        self._use_orchestrator = True

    # ==========================================================================
    # 多模式对话处理
    # ==========================================================================

    async def process_with_mode(
        self,
        user_input: str,
        mode: ChatMode = ChatMode.REACT,
        answer_callback=None,
        done_callback=None,
        thinking_callback=None
    ) -> Dict[str, Any]:
        """
        根据指定模式处理用户输入

        支持三种对话模式：
        1. Direct Mode: 直接调用 LLM，快速响应简单问题
        2. ReAct Mode: 推理与行动交替，适合需要工具调用的场景
        3. Plan Mode: 先规划后执行，适合复杂任务

        Args:
            user_input: 用户输入
            mode: 对话模式
            answer_callback: 答案回调
            done_callback: 完成回调
            thinking_callback: 思考回调

        Returns:
            Dict: 处理结果
        """
        import logging
        import time as time_module
        logger = logging.getLogger(__name__)

        logger.info(f"[Agent] 开始处理 (mode={mode.value}): {user_input[:50]}...")
        start_time = time_module.time()

        # 添加用户输入到历史
        self.memory_manager.add_message('user', user_input)

        context = {
            'user_query': user_input,
            'user_preference': self.memory_manager.get_user_preference()
        }

        # 根据模式处理
        if mode == ChatMode.DIRECT:
            result = await self._process_direct_mode(user_input, answer_callback, done_callback, thinking_callback)
        elif mode == ChatMode.PLAN:
            result = await self._process_plan_mode(user_input, context, answer_callback, done_callback, thinking_callback)
        else:
            # 默认使用 ReAct 模式
            result = await self._process_react_mode(user_input, context, answer_callback, done_callback, thinking_callback)

        elapsed = time_module.time() - start_time
        logger.info(f"[Agent] 处理完成 (mode={mode.value}), 耗时: {elapsed:.2f}秒")

        return result

    async def _process_direct_mode(
        self,
        user_input: str,
        answer_callback=None,
        done_callback=None,
        thinking_callback=None
    ) -> Dict[str, Any]:
        """
        直接调用 LLM 模式

        特点：
        - 快速响应，无工具调用
        - 适合简单对话和一般问题
        - 不展示思考过程
        """
        import logging
        import asyncio
        logger = logging.getLogger(__name__)

        # 发送思考开始
        if thinking_callback:
            thinking_callback("【直接模式】直接生成回答...\n\n", 0.0)

        # 构建消息
        messages = [
            {"role": "system", "content": "你是一个专业的旅游助手。"},
            {"role": "user", "content": user_input}
        ]

        # 流式生成回答
        if hasattr(self.llm_client, 'chat_stream') and answer_callback:
            accumulated_answer = ""
            token_count = 0

            for token in self.llm_client.chat_stream(messages, temperature=0.7):
                token_count += 1
                accumulated_answer += token
                answer_callback(token)
                await asyncio.sleep(0.01)

            answer = accumulated_answer
            logger.info(f"[Agent] 直接模式完成, {token_count} tokens")
        else:
            # 非流式
            result = self.llm_client.chat(messages, temperature=0.7)
            answer = result.get('content', '抱歉，我没有理解您的意思。')

        # 添加助手回答到历史
        self.memory_manager.add_message('assistant', answer)

        result = {
            "success": True,
            "answer": answer,
            "mode": "direct",
            "reasoning": {
                "text": "<thinking>\n[Direct Mode]\n直接调用 LLM 生成回答\n</thinking>",
                "total_steps": 0,
                "tools_used": []
            },
            "history": []
        }

        # 调用完成回调
        if done_callback:
            done_callback(result)

        return result

    async def _process_plan_mode(
        self,
        user_input: str,
        context: Dict,
        answer_callback=None,
        done_callback=None,
        thinking_callback=None,
        use_workflow: bool = True  # v2.3.0 新增：是否使用工作流引擎
    ) -> Dict[str, Any]:
        """
        规划后执行模式

        特点：
        1. 先使用 LLM 生成完整的执行计划
        2. 再逐步执行计划中的步骤
        3. 最后生成最终回答

        适合复杂任务，如多日行程规划

        Args:
            use_workflow: v2.3.0 新增，是否使用 WorkflowEngine 执行计划
        """
        import logging
        import asyncio
        import json as json_util
        logger = logging.getLogger(__name__)

        # v2.3.0 新增：使用工作流引擎执行
        if use_workflow and self.workflow_engine:
            if thinking_callback:
                thinking_callback("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【规划模式 - 工作流引擎】\n正在分解任务并执行...\n\n", 0.0)

            # 使用 WorkflowEngine 执行
            workflow_result = await self.workflow_engine.execute_plan(
                user_input,
                context
            )

            if answer_callback and workflow_result.get("answer"):
                answer_callback(workflow_result["answer"])

            if done_callback:
                done_callback()

            return {
                "success": workflow_result.get("success", True),
                "answer": workflow_result.get("answer", ""),
                "reasoning": {
                    "text": "使用工作流引擎执行",
                    "mode": "workflow"
                },
                "task_results": workflow_result.get("task_results", []),
                "metadata": workflow_result.get("metadata", {})
            }

        step_times = []

        # Step 1: 生成执行计划（阶段一：制定计划）
        if thinking_callback:
            thinking_callback("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【规划模式 - 阶段一：制定计划】\n正在分析任务并生成执行计划...\n\n", 0.0)

        plan_start = asyncio.get_event_loop()
        plan_prompt = f"""用户请求: {user_input}

请制定一个详细的执行计划，以 JSON 格式返回：
{{
    "steps": [
        {{
            "step": 1,
            "action": "工具名称",
            "params": {{"参数": "值"}},
            "description": "步骤描述",
            "phase": "阶段标识 (planning/execution/generation)"
        }}
    ],
    "estimated_time": "预计总时间",
    "goal": "本次规划的最终目标"
}}"

只返回 JSON，不要其他内容。"""

        plan_result = self.llm_client.chat([
            {"role": "system", "content": "你是一个专业的旅游规划助手。"},
            {"role": "user", "content": plan_prompt}
        ], temperature=0.3)

        if not plan_result.get('success'):
            return {
                "success": False,
                "error": "规划生成失败",
                "mode": "plan"
            }

        plan_content = plan_result.get('content', '{}')
        plan_data = {}
        try:
            plan_data = json_util.loads(plan_content)
            logger.info(f"[Plan] 直接解析成功: {plan_data}")
        except json_util.JSONDecodeError:
            logger.warning(f"[Plan] 直接解析失败，尝试提取...")
            plan_data = self._extract_json_from_plan(plan_content)

        steps = plan_data.get('steps', [])
        goal = plan_data.get('goal', '完成用户请求')
        if not steps:
            logger.warning(f"[Plan] steps 为空，原始内容: {plan_content[:500]}...")
            # 尝试更宽松的解析
            if 'steps' in plan_content:
                import re
                # 匹配整个 steps 数组中的每个步骤对象
                step_pattern = re.compile(r'\{\s*"action"\s*:\s*"([^"]+)"\s*,\s*"params"\s*:\s*(\{[^}]*\})\s*,\s*"description"\s*:\s*"([^"]+)"\s*\}')
                step_matches = step_pattern.findall(plan_content)

                if step_matches:
                    logger.info(f"[Plan] 找到步骤: {step_matches}")
                    steps = []
                    for action, params_str, description in step_matches:
                        try:
                            params = json_util.loads(params_str) if params_str else {}
                        except:
                            params = {}
                        steps.append({
                            "action": action,
                            "params": params,
                            "description": description
                        })
                else:
                    # 尝试只提取 action
                    step_items = re.findall(r'"action"\s*:\s*"([^"]+)"', plan_content)
                    if step_items:
                        logger.info(f"[Plan] 只找到 action: {step_items}")
                        steps = [{"action": s, "params": {}, "description": s} for i, s in enumerate(step_items)]

        step_elapsed = (asyncio.get_event_loop().time() - plan_start.time()) if hasattr(plan_start, 'time') else 0
        step_times.append(("制定计划", step_elapsed))

        if thinking_callback:
            thinking_callback(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【规划模式】计划生成完成\n目标: {goal}\n共 {len(steps)} 个执行步骤\n\n", step_elapsed)

        # Step 2: 执行计划（阶段二：逐步执行）
        history = []
        reasoning_text = "[规划模式执行]\n\n"

        # 阶段标记
        phases = {
            'planning': '阶段二：分解任务',
            'execution': '阶段三：执行工具',
            'generation': '阶段四：生成回答'
        }

        for i, step in enumerate(steps):
            step_num = i + 1
            action_name = step.get('action', '')
            params = step.get('params', {})
            description = step.get('description', '')
            phase_key = step.get('phase', 'execution')
            phase_name = phases.get(phase_key, '执行工具')

            step_start = asyncio.get_event_loop()

            if thinking_callback:
                progress = f"[{step_num}/{len(steps)}]"
                thinking_callback(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【规划模式 - {phase_name}】\n{progress} {description}\n\n", 0.0)

            reasoning_text += f"\n{'=' * 40}\n"
            reasoning_text += f"步骤 {step_num} ({phase_name})\n"
            reasoning_text += f"描述: {description}\n"

            # 查找并执行工具
            result = {'success': False}
            if action_name and action_name != 'none':
                tool = self.react_agent.tool_registry.get_tool(action_name)
                if tool:
                    try:
                        result = await tool.execute(**params) if hasattr(tool, 'execute') else tool(params)
                        status = "成功" if result.get('success') else "部分成功"
                        reasoning_text += f"工具: {action_name} [{status}]\n"
                        if result.get('success'):
                            reasoning_text += f"结果: {str(result)[:100]}...\n"
                    except Exception as e:
                        reasoning_text += f"错误: {str(e)}\n"
                        result = {'success': False, 'error': str(e)}
                else:
                    reasoning_text += f"工具未找到: {action_name}\n"
                    result = {'success': False, 'error': f'Tool not found: {action_name}'}

            step_elapsed = (asyncio.get_event_loop().time() - step_start.time()) if hasattr(step_start, 'time') else 0
            step_times.append((f"步骤{step_num}", step_elapsed))

            history.append({
                'step': step_num,
                'phase': phase_name,
                'action': action_name,
                'params': params,
                'result': result,
                'description': description
            })

        # Step 3: 生成最终回答（阶段四：生成回答）
        if thinking_callback:
            thinking_callback("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【规划模式 - 阶段四：生成回答】\n正在整合执行结果...\n\n", 0.0)

        # 收集工具执行结果
        tool_results = [h.get('result', {}) for h in history if h.get('result', {}).get('success')]

        if tool_results:
            answer = self._generate_answer_from_results(user_input, tool_results)
        else:
            # 直接使用 LLM 生成回答
            final_prompt = f"""用户请求: {user_input}

执行计划已完成。请根据以下信息生成最终回答：
{json_util.dumps(history, ensure_ascii=False, indent=2)}

请提供详细、结构化的回答。"""
            final_result = self.llm_client.chat([
                {"role": "system", "content": "你是一个专业的旅游助手。"},
                {"role": "user", "content": final_prompt}
            ], temperature=0.7)
            answer = final_result.get('content', '抱歉，处理过程中出现问题。')

        # 通过 answer_callback 发送最终回答给前端
        if answer_callback:
            answer_callback(answer)

        self.memory_manager.add_message('assistant', answer)

        # 构建推理文本
        reasoning_text += "\n执行完成。"
        full_reasoning = f"""<thinking>
[规划模式]
{reasoning_text}

[步骤耗时]
{chr(10).join([f"- {name}: {t:.2f}秒" for name, t in step_times])}
</thinking>"""

        result = {
            "success": True,
            "answer": answer,
            "mode": "plan",
            "reasoning": {
                "text": full_reasoning,
                "total_steps": len(steps),
                "tools_used": [h.get('action') for h in history if h.get('action')]
            },
            "history": history,
            "plan": steps
        }

        # 调用完成回调
        if done_callback:
            done_callback(result)

        return result

    def _extract_json_from_plan(self, content: str) -> Dict:
        """从计划文本中提取 JSON"""
        import re
        import json as json_util
        json_match = re.search(r'\{[^{}]*\}', content)
        if json_match:
            try:
                return json_util.loads(json_match.group())
            except json_util.JSONDecodeError:
                pass
        return {}

    def _generate_answer_from_results(self, user_input: str, results: List[Dict]) -> str:
        """根据工具执行结果生成回答"""
        import json
        prompt = f"""用户请求: {user_input}

工具执行结果:
{json.dumps(results, ensure_ascii=False, indent=2)}

请根据以上结果，生成一个结构清晰、内容丰富的旅游回答。"""
        result = self.llm_client.chat([
            {"role": "system", "content": "你是一个专业的旅游助手。"},
            {"role": "user", "content": prompt}
        ], temperature=0.7)
        return result.get('content', '处理完成')

    async def _process_react_mode(
        self,
        user_input: str,
        context: Dict,
        answer_callback=None,
        done_callback=None,
        thinking_callback=None
    ) -> Dict[str, Any]:
        """
        ReAct 推理模式

        特点：
        - 思考 → 行动 → 观察 → 评估循环
        - 支持动态工具调用
        - 展示完整的推理过程
        """
        import logging
        import asyncio
        import time as time_module
        logger = logging.getLogger(__name__)

        # 设置思考流式回调
        if hasattr(self.react_agent, 'set_think_stream_callback') and thinking_callback:
            self.react_agent.set_think_stream_callback(thinking_callback)

        # 执行 ReAct 循环
        result = await self.react_agent.run(user_input, context)
        logger.info(f"[Agent] ReAct 执行完成, success={result.get('success')}")

        if result.get('success'):
            history = result.get('history', [])
            reasoning_text = self._build_reasoning_text(history)
            answer = self._extract_answer(history)

            self.memory_manager.add_message('assistant', answer)

            # 构建 LLM 消息生成最终回答
            system_prompt = "你是一个专业的旅游助手。请根据用户的问题，提供详细、准确的旅游建议和规划。"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]

            # 流式生成最终回答
            if hasattr(self.llm_client, 'chat_stream') and answer_callback:
                token_count = 0
                accumulated_answer = ""

                for token in self.llm_client.chat_stream(messages, temperature=0.7):
                    token_count += 1
                    accumulated_answer += token
                    answer_callback(token)
                    await asyncio.sleep(0.01)

                answer = accumulated_answer
                logger.info(f"[Agent] ReAct 流式生成完成, {token_count} tokens")

            return {
                "success": True,
                "answer": answer,
                "mode": "react",
                "reasoning": {
                    "text": reasoning_text,
                    "total_steps": len(history),
                    "tools_used": self._extract_tools_used(history)
                },
                "history": history
            }
        else:
            return {
                "success": False,
                "error": result.get('error', '处理失败'),
                "mode": "react",
                "reasoning": None,
                "history": result.get('history', [])
            }
