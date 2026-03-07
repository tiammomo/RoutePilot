"""会话仓储实现模块 (Session Repository Implementation)

提供SessionRepository接口的具体实现。
使用SessionStorage进行底层数据持久化。

主要组件:
- SessionRepositoryImpl: 会话仓储实现类

功能特点:
- 完整的会话CRUD操作
- 自动管理创建时间和最后活跃时间
- 会话过期清理
- 按最后活跃时间排序

使用示例:
    from storage.session_storage import MemorySessionStorage
    from repositories.session_repository_impl import SessionRepositoryImpl

    # 创建仓储实例
    storage = MemorySessionStorage()
    repository = SessionRepositoryImpl(storage)

    # 创建会话
    session_id = await repository.create({'name': '我的旅行计划'})

    # 获取会话
    session = await repository.get(session_id)

    # 更新会话
    await repository.update(session_id, {'name': '新的名称'})

    # 删除会话
    await repository.delete(session_id)

    # 列出所有会话
    sessions = await repository.list_all()

数据模型:
    session: Dict[str, Any] 包含以下字段
    - session_id: str 会话唯一标识（UUID格式）
    - created_at: str 创建时间（ISO格式）
    - last_active: str 最后活动时间（ISO格式）
    - message_count: int 消息数量
    - name: str 会话名称
    - model_id: str 使用的模型ID
    - messages: List[Dict] 消息历史
    - user_preferences: Dict 用户偏好设置
"""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from .session_repository import SessionRepository
from ..storage.session_storage import SessionStorage


class SessionRepositoryImpl(SessionRepository):
    """
    会话仓储实现类

    实现SessionRepository接口的所有方法。
    委托SessionStorage进行实际的数据存储操作。

    初始化参数:
        storage: SessionStorage 存储后端实例

    继承方法:
        继承自SessionRepository，实现所有抽象方法
    """

    def __init__(self, storage: SessionStorage):
        """
        初始化会话仓储实现

        Args:
            storage: SessionStorage 存储后端实例
        """
        self._storage = storage

    async def create(self, session_data: Dict[str, Any]) -> str:
        """
        创建新会话

        自动生成会话ID，设置创建时间和最后活跃时间。

        Args:
            session_data: Dict[str, Any] 包含name等字段的初始数据

        Returns:
            str: 新创建的会话ID
        """
        # 生成会话ID（优先使用传入的ID）
        session_id = session_data.get('session_id', str(uuid.uuid4()))
        now = datetime.now().isoformat()

        # 构建完整的会话数据
        session = {
            'session_id': session_id,
            'created_at': now,
            'last_active': now,
            'message_count': 0,
            'name': session_data.get('name'),
            'model_id': session_data.get('model_id', 'gpt-4o-mini'),
            'messages': session_data.get('messages', []),
            'user_preferences': session_data.get('user_preferences', {}),
        }

        # 保存到存储
        await self._storage.save(session_id, session)
        return session_id

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话数据

        Args:
            session_id: str 会话ID

        Returns:
            Optional[Dict]: 会话数据，不存在返回None
        """
        return await self._storage.load(session_id)

    async def update(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """
        更新会话数据

        自动更新last_active时间戳，保留原始创建时间。

        Args:
            session_id: str 要更新的会话ID
            session_data: Dict[str, Any] 要更新的字段
        """
        existing = await self._storage.load(session_id)
        if existing:
            merged = existing.copy()
            merged.update(session_data)
            merged['last_active'] = datetime.now().isoformat()
            merged['session_id'] = session_id
            merged['created_at'] = existing.get('created_at')
            await self._storage.save(session_id, merged)

    async def delete(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: str 要删除的会话ID

        Returns:
            bool: 是否删除成功
        """
        return await self._storage.delete(session_id)

    async def list_all(
        self,
        include_empty: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        列出所有会话

        过滤规则:
        - include_empty=True: 返回所有会话
        - include_empty=False: 返回有消息的会话或1小时内的活跃会话

        返回结果按最后活跃时间降序排列。

        Args:
            include_empty: bool 是否包含空会话
            limit: int 结果数量限制

        Returns:
            List[Dict]: 符合条件的会话列表
        """
        sessions = await self._storage.list_all()

        # 计算1小时前的时间戳
        one_hour_ago = datetime.now().timestamp() - 3600

        result = []
        for session_data in sessions.values():
            last_active = datetime.fromisoformat(
                session_data['last_active']
            ).timestamp()

            # 过滤逻辑
            if include_empty:
                result.append(session_data)
            elif session_data.get('message_count', 0) > 0 or last_active > one_hour_ago:
                result.append(session_data)

        # 按最后活跃时间降序排列
        result.sort(key=lambda x: x['last_active'], reverse=True)

        # 应用数量限制
        return result[:limit]

    async def cleanup_expired(self, max_age_seconds: int) -> int:
        """
        清理过期会话

        Args:
            max_age_seconds: int 超过此秒数的会话视为过期

        Returns:
            int: 清理的会话数量
        """
        return await self._storage.cleanup(max_age_seconds)
