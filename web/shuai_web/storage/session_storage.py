"""会话存储抽象和实现模块 (Session Storage Abstraction)

提供会话数据存储的抽象接口和两种实现方式：
- MemorySessionStorage: 内存存储（开发环境）
- FileSessionStorage: 文件存储（持久化存储）

主要组件:
- SessionStorage: 存储抽象基类
- MemorySessionStorage: 内存存储实现
- FileSessionStorage: 文件存储实现

功能特点:
- 统一的存储接口
- 自动更新最后活跃时间
- 过期会话清理
- 文件持久化支持

使用示例:
    # 内存存储（开发环境）
    from storage.session_storage import MemorySessionStorage

    storage = MemorySessionStorage()
    await storage.save('session-1', {'name': 'Test'})
    session = await storage.load('session-1')

    # 文件存储（生产环境）
    from storage.session_storage import FileSessionStorage

    storage = FileSessionStorage('data/sessions.json')
    await storage.save('session-1', {'name': 'Test'})

设计模式:
- 抽象工厂模式: SessionStorage定义接口
- 策略模式: 不同存储策略切换
- 模板方法模式: 公共逻辑在基类

存储数据模型:
    session: Dict[str, Any]
    {
        'session_id': str,
        'created_at': str,      // ISO格式时间
        'last_active': str,     // ISO格式时间，自动更新
        'message_count': int,
        'name': str,
        'model_id': str,
        'messages': [...],
        'user_preferences': {...}
    }
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import asyncio
import json
import os
import tempfile


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format.
    
    Purpose:
        Document service/API behavior, side effects, and integration expectations for maintainers.
    
    Returns:
        str: Normalized text string used by downstream logic.
    """
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_as_utc(value: Any) -> Optional[datetime]:
    """Parse ISO datetime string as UTC-aware datetime.
    
    Purpose:
        Document service/API behavior, side effects, and integration expectations for maintainers.
    
    Args:
        value: Input field `value` used for normalization or matching rules.
    
    Returns:
        Optional[datetime]: Computed value returned to the caller.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class SessionStorage(ABC):
    """
    会话存储抽象基类

    定义会话存储的标准接口，具体存储实现继承此类。

    存储操作:
        save(): 保存会话
        load(): 加载会话
        delete(): 删除会话
        list_all(): 列出所有
        cleanup(): 清理过期
    """

    @abstractmethod
    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        保存会话数据

        Args:
            session_id: str 会话唯一标识
            data: Dict[str, Any] 会话数据
        """
        pass

    @abstractmethod
    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        加载会话数据

        Args:
            session_id: str 会话ID

        Returns:
            Optional[Dict]: 会话数据，不存在返回None
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: str 要删除的会话ID

        Returns:
            bool: 是否删除成功
        """
        pass

    @abstractmethod
    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            Dict: {session_id: session_data, ...}
        """
        pass

    @abstractmethod
    async def cleanup(self, max_age_seconds: int) -> int:
        """
        清理过期会话

        Args:
            max_age_seconds: int 超过此秒数的会话视为过期

        Returns:
            int: 清理的会话数量
        """
        pass


class MemorySessionStorage(SessionStorage):
    """
    内存会话存储实现

    适用于开发环境的轻量级存储方案。
    数据存储在进程内存中，服务重启后数据丢失。

    特点:
        - 快速读写
        - 无持久化
        - 适合测试和开发
    """

    def __init__(self):
        """
        初始化内存存储
        """
        # 使用字典存储会话，key为session_id
        self._sessions: Dict[str, Dict[str, Any]] = {}

    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        保存会话到内存

        自动更新last_active时间戳。

        Args:
            session_id: str 会话ID
            data: Dict[str, Any] 会话数据
        """
        data['last_active'] = _utc_now_iso()
        self._sessions[session_id] = data

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        从内存加载会话

        Args:
            session_id: str 会话ID

        Returns:
            Optional[Dict]: 会话数据或None
        """
        return self._sessions.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """
        从内存删除会话

        Args:
            session_id: str 要删除的会话ID

        Returns:
            bool: 是否存在并删除成功
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            Dict: 所有会话的副本
        """
        return self._sessions.copy()

    async def cleanup(self, max_age_seconds: int) -> int:
        """
        清理过期会话

        根据last_active时间判断是否过期。

        Args:
            max_age_seconds: int 过期时间阈值（秒）

        Returns:
            int: 删除的会话数量
        """
        current_time = datetime.now(timezone.utc)
        expired_ids = []

        for session_id, data in self._sessions.items():
            last_active = _parse_iso_as_utc(data.get('last_active'))
            if last_active and (current_time - last_active).total_seconds() > max_age_seconds:
                expired_ids.append(session_id)

        for session_id in expired_ids:
            del self._sessions[session_id]

        return len(expired_ids)


class FileSessionStorage(SessionStorage):
    """
    文件会话存储实现

    使用JSON文件进行持久化存储。
    服务重启后数据不会丢失。

    特点:
        - 数据持久化
        - 支持服务重启
        - 适合生产环境
        - 自动创建目录
    """
    BACKUP_SUFFIX = ".bak"

    def __init__(self, file_path: str = "data/sessions.json"):
        """
        初始化文件存储

        Args:
            file_path: str JSON文件路径
        """
        # Ensure parent directory exists, including the case where only a filename is provided.
        directory = os.path.dirname(file_path) or "."
        os.makedirs(directory, exist_ok=True)
        self._file_path = file_path
        self._lock = asyncio.Lock()
        # 从文件加载现有数据
        self._sessions: Dict[str, Dict[str, Any]] = self._load_from_file()

    @classmethod
    def _backup_path(cls, path: str) -> str:
        """Return backup filepath for the primary sessions file.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            path: Filesystem path of the primary sessions JSON snapshot.
        
        Returns:
            str: Backup file path used for crash recovery.
        """
        return f"{path}{cls.BACKUP_SUFFIX}"

    @staticmethod
    def _load_json_file(path: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """Load one JSON snapshot file and validate top-level shape.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            path: Filesystem path of the candidate snapshot file.
        
        Returns:
            Optional[Dict[str, Dict[str, Any]]]: Parsed dict payload, otherwise None.
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _fsync_directory(path: str) -> None:
        """Best-effort directory fsync after atomic replace.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            path: Filesystem directory path for the target snapshot file.
        
        Returns:
            None: Side-effect only utility.
        """
        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)

    def _atomic_write_json(self, path: str, payload: Dict[str, Dict[str, Any]]) -> None:
        """Persist JSON payload atomically by temp-file + fsync + os.replace.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            path: Target snapshot file path.
            payload: Snapshot dictionary to persist.
        
        Returns:
            None: Side-effect only utility.
        """
        target_dir = os.path.dirname(path) or "."
        os.makedirs(target_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=target_dir,
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as tmp_file:
                json.dump(payload, tmp_file, indent=2, ensure_ascii=False)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(target_dir)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _load_from_file(self) -> Dict[str, Dict[str, Any]]:
        """
        从JSON文件加载会话数据

        Returns:
            Dict: 加载的会话数据，空文件返回空字典
        """
        primary = self._file_path
        backup = self._backup_path(primary)

        primary_payload = self._load_json_file(primary)
        if primary_payload is not None:
            return primary_payload

        backup_payload = self._load_json_file(backup)
        if backup_payload is None:
            return {}

        # Recovery path: rewrite primary from backup snapshot for subsequent reads.
        try:
            self._atomic_write_json(primary, backup_payload)
        except OSError:
            pass
        return backup_payload

    def _save_to_file(self) -> None:
        """
        将会话数据保存到JSON文件

        使用缩进格式和UTF-8编码。
        """
        self._atomic_write_json(self._file_path, self._sessions)
        self._atomic_write_json(self._backup_path(self._file_path), self._sessions)

    async def save(self, session_id: str, data: Dict[str, Any]) -> None:
        """
        保存会话到文件

        自动更新last_active并持久化。

        Args:
            session_id: str 会话ID
            data: Dict[str, Any] 会话数据
        """
        async with self._lock:
            data['last_active'] = _utc_now_iso()
            self._sessions[session_id] = data
            await asyncio.to_thread(self._save_to_file)

    async def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        从文件加载会话

        Args:
            session_id: str 会话ID

        Returns:
            Optional[Dict]: 会话数据或None
        """
        async with self._lock:
            return self._sessions.get(session_id)

    async def delete(self, session_id: str) -> bool:
        """
        从文件删除会话

        Args:
            session_id: str 要删除的会话ID

        Returns:
            bool: 是否删除成功
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                await asyncio.to_thread(self._save_to_file)
                return True
            return False

    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            Dict: 所有会话的副本
        """
        async with self._lock:
            return self._sessions.copy()

    async def cleanup(self, max_age_seconds: int) -> int:
        """
        清理过期会话

        Args:
            max_age_seconds: int 过期时间阈值（秒）

        Returns:
            int: 删除的会话数量
        """
        async with self._lock:
            current_time = datetime.now(timezone.utc)
            expired_ids = []

            for session_id, data in self._sessions.items():
                last_active = _parse_iso_as_utc(data.get('last_active'))
                if last_active and (current_time - last_active).total_seconds() > max_age_seconds:
                    expired_ids.append(session_id)

            for session_id in expired_ids:
                del self._sessions[session_id]

            if expired_ids:
                await asyncio.to_thread(self._save_to_file)

            return len(expired_ids)
