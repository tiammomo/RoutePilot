"""会话仓储接口模块 (Session Repository Interface)

定义会话数据访问的抽象接口规范。
采用抽象基类(ABC)模式，定义仓储必须实现的方法。

主要组件:
- SessionRepository: 会话仓储抽象接口

功能特点:
- 定义标准化的数据访问接口
- 支持异步操作
- 实现依赖倒置原则

使用示例:
    from repositories.session_repository import SessionRepository

    class CustomSessionRepository(SessionRepository):
        async def create(self, session_data: Dict) -> str:
            # 实现创建逻辑
            pass

        async def get(self, session_id: str) -> Optional[Dict]:
            # 实现获取逻辑
            pass

        # ... 实现其他抽象方法

设计模式:
- 仓库模式 (Repository Pattern): 数据访问抽象
- 抽象基类 (Abstract Base Class): 接口规范定义
- 异步接口 (Async Interface): 支持异步操作

接口方法:
    - create(): 创建新会话
    - get(): 获取会话
    - update(): 更新会话
    - delete(): 删除会话
    - list_all(): 列出所有会话
    - cleanup_expired(): 清理过期会话
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class SessionRepository(ABC):
    """
    会话仓储抽象接口

    定义会话数据访问的标准接口规范。
    具体实现类需要继承并实现所有抽象方法。

    数据模型:
        session_data: Dict[str, Any] 包含以下字段
        - session_id: str 会话唯一标识
        - created_at: str 创建时间 ISO格式
        - last_active: str 最后活动时间 ISO格式
        - message_count: int 消息数量
        - name: str 会话名称
        - model_id: str 使用的模型ID
        - messages: List[Dict] 消息列表
        - user_preferences: Dict 用户偏好
    """

    @abstractmethod
    async def create(self, session_data: Dict[str, Any]) -> str:
        """
        创建新会话

        Args:
            session_data: Dict[str, Any] 会话初始数据，至少包含name字段

        Returns:
            str: 新创建的会话ID

        初始数据通常包含:
            - name: str 会话名称
            - model_id: str (可选) 使用的模型，默认为 'gpt-4o-mini'
            - messages: List (可选) 初始消息列表
            - user_preferences: Dict (可选) 用户偏好
        """
        pass

    @abstractmethod
    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取会话

        Args:
            session_id: str 会话唯一标识

        Returns:
            Optional[Dict]: 会话数据，不存在返回None
        """
        pass

    @abstractmethod
    async def update(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """
        更新会话数据

        Args:
            session_id: str 要更新的会话ID
            session_data: Dict[str, Any] 要更新的字段和数据

        Note:
            实现应自动更新 last_active 时间戳
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: str 要删除的会话ID

        Returns:
            bool: 是否删除成功（会话存在且删除返回True）
        """
        pass

    @abstractmethod
    async def list_all(
        self,
        include_empty: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Args:
            include_empty: bool 是否包含空会话（无消息的会话）
            limit: int 返回结果数量限制，默认100

        Returns:
            List[Dict]: 会话数据列表，按最后活动时间降序排列
        """
        pass

    @abstractmethod
    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """
        清理过期会话

        Args:
            max_age_seconds: int 超过此秒数的会话视为过期

        Returns:
            int: 清理的会话数量
        """
        pass
