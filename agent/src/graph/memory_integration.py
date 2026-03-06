"""
================================================================================
LangGraph Agent 记忆集成模块
================================================================================

将 LangGraph 与 ChatHistory 集成：
- 跨会话记忆保持
- 对话摘要压缩
- 上下文管理

================================================================================
"""

import logging
from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)

# 尝试导入 memory 模块
try:
    from memory.chat_history import (
        ChatHistoryManager,
        get_chat_history_manager,
        SessionChatHistory
    )
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    ChatHistoryManager = None
    get_chat_history_manager = None
    SessionChatHistory = None
    logger.warning("Memory module not available, using in-memory fallback")


# ============================================================================
# 内存会话历史（备用）
# ============================================================================

class InMemoryHistory:
    """内存会话历史（ChatHistoryManager 不可用时的备用）"""

    def __init__(self):
        self._histories: Dict[str, List[Dict]] = {}

    def add_message(self, session_id: str, role: str, content: str):
        if session_id not in self._histories:
            self._histories[session_id] = []
        self._histories[session_id].append({"role": role, "content": content})

    def get_messages(self, session_id: str, limit: int = 10) -> List[Dict]:
        messages = self._histories.get(session_id, [])
        return messages[-limit:]

    def clear(self, session_id: str):
        if session_id in self._histories:
            del self._histories[session_id]


_in_memory_history = InMemoryHistory()


# ============================================================================
# 对话摘要器
# ============================================================================

class ConversationSummarizer:
    """
    对话摘要器

    当对话过长时自动生成摘要，压缩 token 使用
    """

    def __init__(
        self,
        llm: Runnable,
        summary_threshold: int = 20,
        summary_prompt: str = None
    ):
        """
        初始化

        Args:
            llm: LangChain LLM 实例
            summary_threshold: 触发摘要的消息数量阈值
            summary_prompt: 自定义摘要提示词
        """
        self.llm = llm
        self.summary_threshold = summary_threshold
        self.summary_prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT

    def should_summarize(self, messages: List[BaseMessage]) -> bool:
        """
        判断是否需要生成摘要

        Args:
            messages: 消息列表

        Returns:
            是否需要摘要
        """
        # 不计算系统消息
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        return len(non_system) >= self.summary_threshold

    async def summarize(self, messages: List[BaseMessage]) -> str:
        """
        生成对话摘要

        Args:
            messages: 消息列表

        Returns:
            摘要内容
        """
        # 提取对话内容
        conversation = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                conversation.append(f"用户: {msg.content}")
            elif isinstance(msg, AIMessage):
                conversation.append(f"助手: {msg.content}")

        conversation_text = "\n".join(conversation[-self.summary_threshold:])

        # 调用 LLM 生成摘要
        prompt = self.summary_prompt.format(conversation=conversation_text)

        response = self.llm.invoke([SystemMessage(content=prompt)])
        summary = response.content

        logger.info(f"[Summarizer] Generated summary, length: {len(summary)}")

        return summary

    def create_summary_message(self, summary: str) -> SystemMessage:
        """
        创建摘要消息

        Args:
            summary: 摘要内容

        Returns:
            系统消息
        """
        return SystemMessage(
            content=f"【对话摘要】以下是对之前对话的摘要：\n{summary}\n【结束摘要】"
        )


# ============================================================================
# 默认摘要提示词
# ============================================================================

DEFAULT_SUMMARY_PROMPT = """请简洁总结以下对话的要点，包括：
1. 用户的主要需求和意图
2. 已经获取的信息
3. 待解决的问题

对话内容：
{conversation}

请用 2-3 句话简洁总结："""


# ============================================================================
# Agent 记忆管理器
# ============================================================================

class AgentMemoryManager:
    """
    Agent 记忆管理器

    整合会话历史和对话摘要
    """

    def __init__(
        self,
        history_manager=None,
        summarizer: ConversationSummarizer = None,
        max_history: int = 10,
        summary_threshold: int = 20
    ):
        """
        初始化

        Args:
            history_manager: 会话历史管理器
            summarizer: 对话摘要器
            max_history: 最大历史消息数
            summary_threshold: 摘要阈值
        """
        if MEMORY_AVAILABLE and history_manager is None:
            self.history_manager = get_chat_history_manager()
        else:
            self.history_manager = history_manager

        self.summarizer = summarizer
        self.max_history = max_history
        self.summary_threshold = summary_threshold
        self._in_memory = _in_memory_history

    def get_context(self, session_id: str) -> List[BaseMessage]:
        """
        获取对话上下文

        Args:
            session_id: 会话ID

        Returns:
            消息列表
        """
        if self.history_manager:
            history = self.history_manager.get(session_id)
            if history:
                messages = history.get_messages()
                if len(messages) > self.max_history:
                    messages = messages[-self.max_history:]
                return messages
        else:
            # 使用内存历史
            messages = self._in_memory.get_messages(session_id, self.max_history)
            result = []
            for msg in messages:
                if msg.get("role") == "user":
                    result.append(HumanMessage(content=msg.get("content", "")))
                elif msg.get("role") == "assistant":
                    result.append(AIMessage(content=msg.get("content", "")))
            return result

        return []

    async def add_message(self, session_id: str, role: str, content: str):
        """
        添加消息到历史

        Args:
            session_id: 会话ID
            role: 角色 (user/assistant)
            content: 消息内容
        """
        if self.history_manager:
            history = self.history_manager.get_or_create(session_id)

            if role == "user":
                history.add_user_message(content)
            elif role in ("assistant", "ai"):
                history.add_ai_message(content)

            # 检查是否需要摘要
            if self.summarizer:
                messages = history.get_messages()
                if self.summarizer.should_summarize(messages):
                    await self._summarize_and_replace(history, messages)
        else:
            # 使用内存历史
            self._in_memory.add_message(session_id, role, content)

    async def _summarize_and_replace(
        self,
        history,
        messages: List[BaseMessage]
    ):
        """摘要并替换历史"""
        if self.summarizer:
            summary = await self.summarizer.summarize(messages)
            summary_msg = self.summarizer.create_summary_message(summary)

            # 清除旧历史，添加摘要
            history.clear()
            history._history.add_message(summary_msg)

            logger.info(f"[MemoryManager] History summarized and replaced")

    def clear_history(self, session_id: str):
        """清除会话历史"""
        if self.history_manager:
            self.history_manager.delete(session_id)
        else:
            self._in_memory.clear(session_id)

    def list_sessions(self) -> List[str]:
        """列出所有会话"""
        if self.history_manager:
            return self.history_manager.list_sessions()
        return list(self._in_memory._histories.keys())


# ============================================================================
# 状态扩展
# ============================================================================

class AgentStateWithMemory:
    """
    带记忆的 Agent 状态

    扩展基础状态，添加记忆相关字段
    """

    @staticmethod
    def create(
        user_message: str,
        session_id: str,
        memory_manager: AgentMemoryManager,
        system_prompt: str = None
    ) -> Dict[str, Any]:
        """
        创建带记忆的状态

        Args:
            user_message: 用户消息
            session_id: 会话ID
            memory_manager: 记忆管理器
            system_prompt: 系统提示词

        Returns:
            状态字典
        """
        from .state import create_initial_state, TRAVEL_AGENT_SYSTEM_PROMPT

        # 创建基础状态
        state = create_initial_state(
            user_message=user_message,
            session_id=session_id,
            system_message=system_prompt or TRAVEL_AGENT_SYSTEM_PROMPT
        )

        # 获取历史上下文
        history_messages = memory_manager.get_context(session_id)

        # 将历史消息插入到系统消息之后
        if history_messages:
            # 保留系统消息和当前用户消息
            system_msg = state["messages"][0] if state["messages"] else None
            user_msg = state["messages"][-1] if state["messages"] else None

            # 重新构建消息列表
            new_messages = []
            if system_msg:
                new_messages.append(system_msg)

            # 添加历史消息
            new_messages.extend(history_messages)

            # 添加当前用户消息
            if user_msg:
                new_messages.append(user_msg)

            state["messages"] = new_messages
            state["has_history"] = True
        else:
            state["has_history"] = False

        return state


# ============================================================================
# 全局单例
# ============================================================================

_memory_manager: Optional[AgentMemoryManager] = None


def get_agent_memory_manager(
    llm: Runnable = None,
    max_history: int = 10,
    summary_threshold: int = 20
) -> AgentMemoryManager:
    """
    获取 Agent 记忆管理器单例

    Args:
        llm: LangChain LLM 实例
        max_history: 最大历史数
        summary_threshold: 摘要阈值

    Returns:
        AgentMemoryManager 实例
    """
    global _memory_manager

    if _memory_manager is None:
        # 创建摘要器（如果提供了 LLM）
        summarizer = None
        if llm:
            summarizer = ConversationSummarizer(
                llm=llm,
                summary_threshold=summary_threshold
            )

        _memory_manager = AgentMemoryManager(
            summarizer=summarizer,
            max_history=max_history,
            summary_threshold=summary_threshold
        )

    return _memory_manager


def reset_agent_memory_manager():
    """重置记忆管理器"""
    global _memory_manager
    _memory_manager = None
