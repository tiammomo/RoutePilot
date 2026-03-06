"""
================================================================================
LangChain Memory 模块
================================================================================

基于 LangChain 的会话历史管理。
支持：
- ChatMessageHistory: 内存会话历史
- FileChatMessageHistory: 文件持久化会话历史
- 自动 Session 管理
- 消息序列化

使用示例:
```python
from memory.chat_history import ChatHistoryManager

# 创建管理器
manager = ChatHistoryManager()

# 添加消息
history = manager.get_or_create("session_123")
history.add_user_message("我想去北京旅游")
history.add_ai_message("北京是个不错的选择...")

# 获取消息
messages = history.get_messages()

# 清除历史
history.clear()

# 获取可序列化的消息（用于 API 响应）
serializable = history.to_serializable()
```

================================================================================
"""

import json
import os
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from langchain_core.chat_message_histories import ChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


class SerializableChatHistory:
    """可序列化的聊天历史（用于 API 响应）"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict[str, str]] = []

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_ai(self, content: str):
        self.messages.append({"role": "assistant", "content": content})

    def add_system(self, content: str):
        self.messages.append({"role": "system", "content": content})

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "messages": self.messages
        }


class SessionChatHistory:
    """
    单个会话的聊天历史

    封装 LangChain 的 ChatMessageHistory
    """

    def __init__(self, session_id: str):
        """
        初始化

        Args:
            session_id: 会话ID
        """
        self.session_id = session_id
        self._history = ChatMessageHistory()
        self._created_at = datetime.now()
        self._updated_at = datetime.now()

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def add_user_message(self, message: str):
        """添加用户消息"""
        self._history.add_user_message(message)
        self._updated_at = datetime.now()

    def add_ai_message(self, message: str):
        """添加 AI 消息"""
        self._history.add_ai_message(message)
        self._updated_at = datetime.now()

    def add_message(self, role: str, content: str):
        """
        添加消息

        Args:
            role: 角色 (user/ai/system)
            content: 消息内容
        """
        if role == "user":
            self._history.add_user_message(content)
        elif role == "assistant" or role == "ai":
            self._history.add_ai_message(content)
        elif role == "system":
            self._history.add_message(SystemMessage(content=content))
        self._updated_at = datetime.now()

    def get_messages(self) -> List[BaseMessage]:
        """获取所有消息"""
        return self._history.messages

    def get_serializable(self) -> SerializableChatHistory:
        """获取可序列化的版本"""
        serializable = SerializableChatHistory(self.session_id)
        for msg in self._history.messages:
            if isinstance(msg, HumanMessage):
                serializable.add_user(msg.content)
            elif isinstance(msg, AIMessage):
                serializable.add_ai(msg.content)
            elif isinstance(msg, SystemMessage):
                serializable.add_system(msg.content)
        return serializable

    def clear(self):
        """清除历史"""
        self._history.clear()
        self._updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "created_at": self._created_at.isoformat(),
            "updated_at": self._updated_at.isoformat(),
            "messages": [
                {
                    "type": type(msg).__name__,
                    "content": msg.content
                }
                for msg in self._history.messages
            ]
        }


class ChatHistoryManager:
    """
    聊天历史管理器

    支持多会话管理，内存存储
    """

    def __init__(self):
        """初始化"""
        self._histories: Dict[str, SessionChatHistory] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionChatHistory:
        """
        获取或创建会话历史

        Args:
            session_id: 会话ID

        Returns:
            SessionChatHistory 实例
        """
        with self._lock:
            if session_id not in self._histories:
                self._histories[session_id] = SessionChatHistory(session_id)
            return self._histories[session_id]

    def get(self, session_id: str) -> Optional[SessionChatHistory]:
        """
        获取会话历史

        Args:
            session_id: 会话ID

        Returns:
            SessionChatHistory 实例，不存在返回 None
        """
        return self._histories.get(session_id)

    def delete(self, session_id: str):
        """
        删除会话历史

        Args:
            session_id: 会话ID
        """
        with self._lock:
            if session_id in self._histories:
                del self._histories[session_id]

    def list_sessions(self) -> List[str]:
        """
        列出所有会话ID

        Returns:
            会话ID列表
        """
        return list(self._histories.keys())

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话信息

        Args:
            session_id: 会话ID

        Returns:
            会话信息字典
        """
        history = self.get(session_id)
        if history:
            return {
                "session_id": session_id,
                "created_at": history.created_at.isoformat(),
                "updated_at": history.updated_at.isoformat(),
                "message_count": len(history.get_messages())
            }
        return None

    def list_all_sessions_info(self) -> List[Dict[str, Any]]:
        """
        获取所有会话信息

        Returns:
            会话信息列表
        """
        return [
            self.get_session_info(sid)
            for sid in self.list_sessions()
            if self.get_session_info(sid)
        ]

    def clear_all(self):
        """清除所有会话"""
        with self._lock:
            self._histories.clear()


class FileChatHistoryManager(ChatHistoryManager):
    """
    文件持久化的聊天历史管理器

    支持将会话历史保存到文件
    """

    def __init__(self, storage_dir: str = "data/chat_history"):
        """
        初始化

        Args:
            storage_dir: 存储目录
        """
        super().__init__()
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.storage_dir / f"{session_id}.json"

    def save(self, session_id: str):
        """
        保存会话历史到文件

        Args:
            session_id: 会话ID
        """
        history = self.get(session_id)
        if not history:
            return

        file_path = self._get_file_path(session_id)
        data = history.to_dict()

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, session_id: str) -> bool:
        """
        从文件加载会话历史

        Args:
            session_id: 会话ID

        Returns:
            是否成功加载
        """
        file_path = self._get_file_path(session_id)
        if not file_path.exists():
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            history = self.get_or_create(session_id)
            for msg in data.get("messages", []):
                msg_type = msg.get("type", "")
                content = msg.get("content", "")

                if msg_type == "HumanMessage":
                    history.add_user_message(content)
                elif msg_type == "AIMessage":
                    history.add_ai_message(content)
                elif msg_type == "SystemMessage":
                    history.add_message("system", content)

            return True
        except Exception:
            return False

    def get_or_create(self, session_id: str) -> SessionChatHistory:
        """获取或创建会话，尝试从文件加载"""
        history = super().get_or_create(session_id)

        # 如果历史为空，尝试从文件加载
        if not history.get_messages():
            self.load(session_id)

        return history


# 全局单例
_chat_history_manager: Optional[ChatHistoryManager] = None


def get_chat_history_manager() -> ChatHistoryManager:
    """
    获取全局聊天历史管理器

    Returns:
        ChatHistoryManager 实例
    """
    global _chat_history_manager
    if _chat_history_manager is None:
        _chat_history_manager = ChatHistoryManager()
    return _chat_history_manager


def get_file_chat_history_manager(storage_dir: str = "data/chat_history") -> FileChatHistoryManager:
    """
    获取文件持久化的聊天历史管理器

    Args:
        storage_dir: 存储目录

    Returns:
        FileChatHistoryManager 实例
    """
    return FileChatHistoryManager(storage_dir)
