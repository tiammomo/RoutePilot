"""
Redis 记忆存储模块 (Redis Memory Store)

提供 Redis 作为后端的记忆存储，支持：
- 对话历史存储
- 会话状态管理
- 用户偏好存储（带 TTL）
- 分布式会话支持

使用示例:
    from memory.redis_memory import RedisMemoryManager

    # 创建 Redis 记忆管理器
    memory = RedisMemoryManager(
        host="localhost",
        port=6379,
        key_prefix="travel:",
        ttl=86400  # 24小时
    )

    # 添加对话消息
    memory.add_message(session_id, 'user', '我想去北京旅游')

    # 获取对话历史
    history = memory.get_conversation_history(session_id)
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class RedisMemoryManager:
    """
    Redis 记忆管理器

    使用 Redis 作为后端存储，支持分布式会话和自动过期。
    如果 Redis 不可用，会自动降级到内存模式。

    功能:
    - 对话历史（带长度限制和自动过期）
    - 会话状态（JSON 存储）
    - 用户偏好（带 TTL 自动过期）
    - 长期记忆（归档存储）

    与 MemoryManager 接口兼容:
    - add_message()
    - get_conversation_history()
    - get_user_preference()
    - archive_current_session()
    - clear_conversation()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str = None,
        key_prefix: str = "travel:",
        ttl: int = 86400,
        max_history: int = 50,
        fallback: bool = True
    ):
        """
        初始化 Redis 记忆管理器

        Args:
            host: Redis 主机地址
            port: Redis 端口
            db: Redis 数据库编号
            password: Redis 密码
            key_prefix: 键前缀
            ttl: 默认过期时间（秒）
            max_history: 最大对话历史条数
            fallback: 是否在 Redis 不可用时降级到内存模式
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.key_prefix = key_prefix
        self.ttl = ttl
        self.max_history = max_history
        self.fallback = fallback

        # Redis 客户端
        self._redis_client = None
        self._redis_available = False

        # 内存降级模式
        self._memory_mode = False
        self._memory_storage: Dict[str, Any] = {}

        # 初始化连接
        self._connect()

    def _connect(self) -> None:
        """尝试连接 Redis"""
        try:
            # 使用同步 Redis 客户端
            import redis as redis_sync

            self._redis_client = redis_sync.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                decode_responses=True
            )

            # 测试连接
            self._redis_client.ping()
            self._redis_available = True
            logger.info(f"[RedisMemoryManager] 连接到 Redis {self.host}:{self.port} 成功")

        except Exception as e:
            if self.fallback:
                self._memory_mode = True
                logger.warning(f"[RedisMemoryManager] Redis 连接失败，降级到内存模式: {e}")
            else:
                raise e

    async def _async_connect(self) -> None:
        """异步连接 Redis（可选，用于异步操作）"""
        pass  # 同步客户端已足够，不再需要异步连接

    def _get_key(self, session_id: str, *parts) -> str:
        """生成 Redis 键"""
        return f"{self.key_prefix}memory:{session_id}:{':'.join(parts)}"

    # =========================================================================
    # 对话历史操作
    # =========================================================================

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        添加对话消息

        Args:
            session_id: 会话 ID
            role: 角色 ('user' 或 'assistant')
            content: 消息内容
        """
        if self._memory_mode:
            self._memory_add_message(session_id, role, content)
            return

        try:
            key = self._get_key(session_id, "history")
            message = json.dumps({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            }, ensure_ascii=False)

            # 添加到列表右侧
            self._redis_client.rpush(key, message)

            # 修剪列表长度
            self._redis_client.ltrim(key, -self.max_history, -1)

            # 更新会话活跃时间
            self._redis_client.hset(
                self._get_key(session_id, "meta"),
                mapping={"last_active": datetime.now().isoformat()}
            )

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 添加消息失败: {e}")
            if self.fallback:
                self._memory_mode = True
                self._memory_add_message(session_id, role, content)

    def _memory_add_message(self, session_id: str, role: str, content: str) -> None:
        """内存模式：添加消息"""
        if "histories" not in self._memory_storage:
            self._memory_storage["histories"] = {}

        if session_id not in self._memory_storage["histories"]:
            self._memory_storage["histories"][session_id] = []

        self._memory_storage["histories"][session_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_conversation_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        获取对话历史

        Args:
            session_id: 会话 ID
            limit: 可选，返回最近 N 条消息

        Returns:
            List[Dict]: 消息列表
        """
        if self._memory_mode:
            return self._memory_get_history(session_id, limit)

        try:
            key = self._get_key(session_id, "history")
            raw_history = self._redis_client.lrange(key, 0, -1)

            history = []
            for item in raw_history:
                msg = json.loads(item)
                history.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg.get("timestamp", "")
                })

            # 限制返回数量
            if limit and limit > 0:
                history = history[-limit:]

            return history

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 获取历史失败: {e}")
            return self._memory_get_history(session_id, limit)

    def _memory_get_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """内存模式：获取历史"""
        histories = self._memory_storage.get("histories", {})
        history = histories.get(session_id, [])

        if limit and limit > 0:
            history = history[-limit:]

        return history

    def clear_conversation(self, session_id: str, archive: bool = True) -> None:
        """
        清除对话历史

        Args:
            session_id: 会话 ID
            archive: 是否先存档
        """
        if archive:
            self.archive_current_session(session_id)

        if self._memory_mode:
            if "histories" in self._memory_storage:
                self._memory_storage["histories"].pop(session_id, None)
            return

        try:
            key = self._get_key(session_id, "history")
            self._redis_client.delete(key)
            self._redis_client.delete(self._get_key(session_id, "meta"))

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 清除对话失败: {e}")

    # =========================================================================
    # 用户偏好操作
    # =========================================================================

    def get_user_preference(self, session_id: str) -> Dict[str, Any]:
        """
        获取用户偏好

        Args:
            session_id: 会话 ID

        Returns:
            Dict: 用户偏好字典
        """
        if self._memory_mode:
            return self._memory_get_preference(session_id)

        try:
            key = self._get_key(session_id, "preference")
            data = self._redis_client.hgetall(key)

            # 转换类型
            if data.get("budget_range"):
                import ast
                try:
                    data["budget_range"] = ast.literal_eval(data["budget_range"])
                except:
                    pass

            if data.get("interest_tags"):
                data["interest_tags"] = json.loads(data["interest_tags"])

            if data.get("preferred_cities"):
                data["preferred_cities"] = json.loads(data["preferred_cities"])

            return data if data else {}

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 获取偏好失败: {e}")
            return self._memory_get_preference(session_id)

    def _memory_get_preference(self, session_id: str) -> Dict[str, Any]:
        """内存模式：获取偏好"""
        preferences = self._memory_storage.get("preferences", {})
        return preferences.get(session_id, {})

    def set_user_preference(
        self,
        session_id: str,
        preference_data: Dict[str, Any]
    ) -> None:
        """
        设置用户偏好

        Args:
            session_id: 会话 ID
            preference_data: 偏好数据
        """
        if self._memory_mode:
            self._memory_set_preference(session_id, preference_data)
            return

        try:
            key = self._get_key(session_id, "preference")

            # 准备数据
            data = preference_data.copy()
            if "budget_range" in data and data["budget_range"]:
                data["budget_range"] = str(data["budget_range"])
            if "interest_tags" in data:
                data["interest_tags"] = json.dumps(data["interest_tags"])
            if "preferred_cities" in data:
                data["preferred_cities"] = json.dumps(data["preferred_cities"])

            # 存储并设置过期
            self._redis_client.hset(key, mapping=data)
            self._redis_client.expire(key, self.ttl)

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 设置偏好失败: {e}")
            if self.fallback:
                self._memory_set_preference(session_id, preference_data)

    def _memory_set_preference(
        self,
        session_id: str,
        preference_data: Dict[str, Any]
    ) -> None:
        """内存模式：设置偏好"""
        if "preferences" not in self._memory_storage:
            self._memory_storage["preferences"] = {}
        self._memory_storage["preferences"][session_id] = preference_data

    # =========================================================================
    # 会话状态操作
    # =========================================================================

    def update_session_state(
        self,
        session_id: str,
        key: str,
        value: Any
    ) -> None:
        """
        更新会话状态

        Args:
            session_id: 会话 ID
            key: 状态键
            value: 状态值
        """
        if self._memory_mode:
            self._memory_update_state(session_id, key, value)
            return

        try:
            key_full = self._get_key(session_id, "state", key)
            self._redis_client.set(
                key_full,
                json.dumps(value, ensure_ascii=False),
                ex=self.ttl
            )

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 更新状态失败: {e}")
            if self.fallback:
                self._memory_update_state(session_id, key, value)

    def get_session_state(
        self,
        session_id: str,
        key: str,
        default: Any = None
    ) -> Any:
        """
        获取会话状态

        Args:
            session_id: 会话 ID
            key: 状态键
            default: 默认值

        Returns:
            Any: 状态值
        """
        if self._memory_mode:
            return self._memory_get_state(session_id, key, default)

        try:
            key_full = self._get_key(session_id, "state", key)
            data = self._redis_client.get(key_full)
            if data:
                return json.loads(data)
            return default

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 获取状态失败: {e}")
            return self._memory_get_state(session_id, key, default)

    def _memory_update_state(
        self,
        session_id: str,
        key: str,
        value: Any
    ) -> None:
        """内存模式：更新状态"""
        if "states" not in self._memory_storage:
            self._memory_storage["states"] = {}
        if session_id not in self._memory_storage["states"]:
            self._memory_storage["states"][session_id] = {}
        self._memory_storage["states"][session_id][key] = value

    def _memory_get_state(
        self,
        session_id: str,
        key: str,
        default: Any = None
    ) -> Any:
        """内存模式：获取状态"""
        states = self._memory_storage.get("states", {})
        session_states = states.get(session_id, {})
        return session_states.get(key, default)

    # =========================================================================
    # 存档操作
    # =========================================================================

    def archive_current_session(self, session_id: str) -> Dict[str, Any]:
        """
        归档当前会话

        Args:
            session_id: 会话 ID

        Returns:
            Dict: 归档记录
        """
        history = self.get_conversation_history(session_id)
        state = self._get_full_state(session_id)
        preference = self.get_user_preference(session_id)

        archive = {
            "session_id": session_id,
            "start_time": state.get("start_time", datetime.now().isoformat()),
            "end_time": datetime.now().isoformat(),
            "message_count": len(history),
            "summary": self._generate_summary(history, state),
            "user_preference": preference,
            "messages": history
        }

        # 存储归档
        archive_key = self._get_key(session_id, "archive")
        archive_data = json.dumps(archive, ensure_ascii=False)

        if not self._memory_mode:
            try:
                self._redis_client.rpush(archive_key, archive_data)
                self._redis_client.expire(archive_key, self.ttl * 7)  # 归档保留更久
            except Exception as e:
                logger.error(f"[RedisMemoryManager] 归档失败: {e}")

        # 添加到长期记忆列表
        self._add_to_long_term_memory(archive)

        return archive

    def _get_full_state(self, session_id: str) -> Dict[str, Any]:
        """获取完整会话状态"""
        if self._memory_mode:
            states = self._memory_storage.get("states", {})
            return states.get(session_id, {})

        try:
            pattern = self._get_key(session_id, "state", "*")
            keys = self._redis_client.keys(pattern)
            state = {}
            for key in keys:
                data = self._redis_client.get(key)
                if data:
                    # 提取状态键名
                    state_key = key.split(":")[-1]
                    state[state_key] = json.loads(data)
            return state
        except:
            return {}

    def _generate_summary(self, history: List, state: Dict) -> str:
        """生成会话摘要"""
        parts = []
        user_msgs = [m for m in history if m.get("role") == "user"]
        if user_msgs:
            parts.append(f"用户消息数: {len(user_msgs)}")

        if state.get("last_recommended_cities"):
            parts.append(f"推荐城市: {', '.join(state.get('last_recommended_cities', [])[:3])}")

        return " | ".join(parts) if parts else "一般对话"

    def _add_to_long_term_memory(self, archive: Dict) -> None:
        """添加到长期记忆"""
        if "archives" not in self._memory_storage:
            self._memory_storage["archives"] = []

        self._memory_storage["archives"].append(archive)

        # 限制数量
        max_archives = 100
        while len(self._memory_storage["archives"]) > max_archives:
            self._memory_storage["archives"].pop(0)

    def get_archived_sessions(
        self,
        session_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取已存档的会话列表

        Args:
            session_id: 可选，按会话 ID 筛选
            limit: 返回的最大数量

        Returns:
            List[Dict]: 归档列表
        """
        if self._memory_mode:
            archives = self._memory_storage.get("archives", [])
            if session_id:
                archives = [a for a in archives if a.get("session_id") == session_id]
            return archives[-limit:]

        try:
            if session_id:
                pattern = self._get_key(session_id, "archive")
                raw_archives = self._redis_client.lrange(pattern, 0, limit)
            else:
                # 获取所有归档（跨会话）
                pattern = f"{self.key_prefix}memory:*:archive"
                keys = self._redis_client.keys(pattern)

                archives = []
                for key in keys[:100]:  # 限制数量
                    raw = self._redis_client.lrange(key, -1, -1)
                    if raw:
                        archives.append(json.loads(raw[0]))

                return sorted(archives, key=lambda x: x.get("end_time", ""))[-limit:]

            return [json.loads(a) for a in raw_archives]

        except Exception as e:
            logger.error(f"[RedisMemoryManager] 获取归档失败: {e}")
            return self._memory_storage.get("archives", [])[-limit:]

    # =========================================================================
    # 统计信息
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆系统统计信息

        Returns:
            Dict: 统计信息
        """
        if self._memory_mode:
            return {
                "mode": "memory",
                "history_count": len(self._memory_storage.get("histories", {})),
                "archive_count": len(self._memory_storage.get("archives", []))
            }

        try:
            return {
                "mode": "redis",
                "host": self.host,
                "port": self.port,
                "connected": self._redis_available,
                "ttl": self.ttl,
                "max_history": self.max_history
            }
        except Exception as e:
            return {"mode": "unknown", "error": str(e)}

    def close(self) -> None:
        """关闭连接"""
        if self._redis_client:
            self._redis_client.close()
            logger.info("[RedisMemoryManager] Redis 连接已关闭")
