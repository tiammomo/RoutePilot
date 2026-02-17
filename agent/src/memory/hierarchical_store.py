"""
分层长期记忆存储 (Hierarchical Memory Store)

提供多层次的长期记忆存储架构，支持热点数据和冷数据的分层管理。
集成用户画像、热点缓存、向量检索（可选）等多种存储方式。

功能特点:
- 热点记忆 LRU 缓存
- 用户画像结构化存储
- 会话存档向量索引（可选）
- 自动冷热数据分层
- 记忆检索和查询

使用示例:
    store = HierarchicalMemoryStore()
    await store.store_session(session)
    context = await store.retrieve_context(user_id, query)
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import OrderedDict
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    """记忆层级"""
    HOT = "hot"         # 热点数据（内存缓存）
    WARM = "warm"       # 温数据（用户画像）
    COLD = "cold"       # 冷数据（会话存档）
    ARCHIVE = "archive" # 归档数据


@dataclass
class SessionData:
    """会话数据"""
    session_id: str
    user_id: Optional[str]
    start_time: str
    end_time: Optional[str]
    message_count: int
    summary: str
    topics: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    full_history: List[Dict[str, str]] = field(default_factory=list)
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "message_count": self.message_count,
            "summary": self.summary,
            "topics": self.topics,
            "user_preferences": self.user_preferences,
            "full_history": self.full_history,
            "metadata": self.metadata
            # 不保存 embedding，节省空间
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionData':
        return cls(
            session_id=data.get('session_id', ''),
            user_id=data.get('user_id'),
            start_time=data.get('start_time', datetime.now().isoformat()),
            end_time=data.get('end_time'),
            message_count=data.get('message_count', 0),
            summary=data.get('summary', ''),
            topics=data.get('topics', []),
            user_preferences=data.get('user_preferences', {}),
            full_history=data.get('full_history', []),
            metadata=data.get('metadata', {})
        )


@dataclass
class RetrievedMemory:
    """检索到的记忆"""
    data: SessionData
    tier: MemoryTier
    relevance_score: float = 0.0
    match_reason: str = ""


class LRUCache:
    """简单 LRU 缓存实现"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        # 移动到末尾（最近使用）
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            # 更新值并移动到末尾
            self._cache.move_to_end(key)
        else:
            # 添加新值
            self._cache[key] = value
            # 超出容量时淘汰最旧的
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        self._cache.clear()

    def keys(self) -> List[str]:
        return list(self._cache.keys())

    def values(self) -> List[Any]:
        return list(self._cache.values())

    def items(self) -> List[tuple]:
        return list(self._cache.items())

    def __len__(self) -> int:
        return len(self._cache)


class HierarchicalMemoryStore:
    """
    分层长期记忆存储

    架构：
    - HOT (热点): LRU 缓存最近活跃用户的会话
    - WARM (温数据): 用户画像和偏好信息
    - COLD (冷数据): 已存档的会话详情
    - ARCHIVE (归档): 非常旧的会话（可配置是否保留）

    功能：
    - 自动分层管理
    - 热点数据缓存
- 用户画像集成
    - 会话存档
    - 语义检索（需要 Embedding 模型）
    """

    def __init__(
        self,
        hot_cache_size: int = 100,
        warm_cache_size: int = 1000,
        cold_cache_size: int = 5000,
        enable_vector_search: bool = False,
        embedding_model: Optional[Any] = None,
        storage_path: Optional[str] = None
    ):
        """
        初始化分层记忆存储

        Args:
            hot_cache_size: 热点缓存大小
            warm_cache_size: 温数据缓存大小
            cold_cache_size: 冷数据缓存大小
            enable_vector_search: 是否启用向量检索
            embedding_model: 可选的 Embedding 模型
            storage_path: 存储文件路径
        """
        # 各层级存储
        self._hot_cache = LRUCache(max_size=hot_cache_size)  # 热点会话
        self._warm_cache: Dict[str, SessionData] = {}  # 温数据（按 user_id 索引）
        self._cold_cache: Dict[str, SessionData] = {}  # 冷数据（按 session_id 索引）

        # 向量检索（可选）
        self._enable_vector_search = enable_vector_search
        self._embedding_model = embedding_model
        self._vector_index: Dict[str, List[float]] = {}  # session_id -> embedding

        # 存储路径
        self._storage_path = storage_path

        # 统计信息
        self._stats = {
            "total_sessions": 0,
            "hot_hits": 0,
            "warm_hits": 0,
            "cold_hits": 0,
            "tier_migrations": 0
        }

    async def store_session(self, session: SessionData) -> None:
        """
        存储会话到合适层级

        Args:
            session: 会话数据
        """
        self._stats["total_sessions"] += 1

        # 直接放入热点层（最近活跃）
        self._hot_cache.set(session.session_id, session)

        # 如果有 user_id，也放入温数据层
        if session.user_id:
            if session.user_id not in self._warm_cache:
                self._warm_cache[session.user_id] = []
            self._warm_cache[session.user_id].append(session)

        # 生成向量索引（如果启用）
        if self._enable_vector_search and self._embedding_model:
            await self._index_session_embedding(session)

        # 尝试持久化
        self._save_to_storage()

        logger.debug(f"存储会话: {session.session_id} (层级: HOT)")

    async def _index_session_embedding(self, session: SessionData) -> None:
        """为会话生成并存储向量"""
        try:
            if self._embedding_model:
                # 使用摘要生成向量
                text = session.summary
                if session.topics:
                    text += " " + " ".join(session.topics)

                embedding = await self._embedding_model.encode(text)
                self._vector_index[session.session_id] = embedding
        except Exception as e:
            logger.warning(f"生成会话向量失败: {session.session_id}, {e}")

    async def retrieve_context(
        self,
        user_id: str,
        query: str,
        top_k: int = 3
    ) -> List[RetrievedMemory]:
        """
        检索用户相关上下文

        Args:
            user_id: 用户 ID
            query: 查询内容
            top_k: 返回结果数量

        Returns:
            List[RetrievedMemory]: 检索到的记忆列表
        """
        results: List[RetrievedMemory] = []

        # 1. 首先检查热点层（按 session_id）
        hot_keys = self._hot_cache.keys()
        for key in hot_keys:
            session = self._hot_cache.get(key)
            if session and session.user_id == user_id:
                relevance = self._calculate_relevance(session, query)
                results.append(RetrievedMemory(
                    data=session,
                    tier=MemoryTier.HOT,
                    relevance_score=relevance,
                    match_reason="热点缓存命中"
                ))
                self._stats["hot_hits"] += 1

        # 2. 检查温数据层
        if user_id in self._warm_cache:
            for session in self._warm_cache[user_id]:
                if session.session_id in [r.data.session_id for r in results]:
                    continue
                relevance = self._calculate_relevance(session, query)
                results.append(RetrievedMemory(
                    data=session,
                    tier=MemoryTier.WARM,
                    relevance_score=relevance,
                    match_reason="用户历史会话"
                ))
                self._stats["warm_hits"] += 1

        # 3. 冷数据层（按关键词匹配）
        for session_id, session in self._cold_cache.items():
            if session_id in [r.data.session_id for r in results]:
                continue
            relevance = self._calculate_relevance(session, query)
            if relevance > 0.1:  # 只返回相关度 > 0.1 的
                results.append(RetrievedMemory(
                    data=session,
                    tier=MemoryTier.COLD,
                    relevance_score=relevance,
                    match_reason="历史会话匹配"
                ))
                self._stats["cold_hits"] += 1

        # 4. 向量检索（如果启用）
        if self._enable_vector_search and self._embedding_model:
            vector_results = await self._vector_search(query, top_k)
            for result in vector_results:
                if result.data.session_id in [r.data.session_id for r in results]:
                    continue
                results.append(result)

        # 按相关度排序
        results.sort(key=lambda x: x.relevance_score, reverse=True)

        return results[:top_k]

    def _calculate_relevance(
        self,
        session: SessionData,
        query: str
    ) -> float:
        """计算会话与查询的相关度"""
        query_lower = query.lower()
        relevance = 0.0

        # 主题匹配
        for topic in session.topics:
            if topic.lower() in query_lower:
                relevance += 0.3

        # 摘要关键词匹配
        summary_lower = session.summary.lower()
        query_words = query_lower.split()
        for word in query_words:
            if word in summary_lower:
                relevance += 0.1

        # 用户偏好匹配
        prefs = session.user_preferences or {}
        interest_tags = prefs.get('interest_tags', [])
        for tag in interest_tags:
            if tag.lower() in query_lower:
                relevance += 0.2

        # 预算匹配
        budget = prefs.get('budget_range')
        if budget:
            if any(x in query_lower for x in ['预算', '钱', '花费', '元']):
                relevance += 0.1

        return min(relevance, 1.0)

    async def _vector_search(
        self,
        query: str,
        top_k: int
    ) -> List[RetrievedMemory]:
        """向量检索"""
        if not self._enable_vector_search or not self._embedding_model:
            return []

        try:
            # 生成查询向量
            query_embedding = await self._embedding_model.encode(query)

            # 计算相似度
            similarities = []
            for session_id, embedding in self._vector_index.items():
                sim = self._cosine_similarity(query_embedding, embedding)
                similarities.append((session_id, sim))

            # 排序并返回 top_k
            similarities.sort(key=lambda x: x[1], reverse=True)

            results = []
            for session_id, sim in similarities[:top_k]:
                session = self._get_session_by_id(session_id)
                if session:
                    results.append(RetrievedMemory(
                        data=session,
                        tier=MemoryTier.COLD,
                        relevance_score=sim,
                        match_reason="向量相似度匹配"
                    ))

            return results
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float]
    ) -> float:
        """计算余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 * norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _get_session_by_id(self, session_id: str) -> Optional[SessionData]:
        """根据 ID 获取会话"""
        # 热点层
        session = self._hot_cache.get(session_id)
        if session:
            return session

        # 温数据层
        for sessions in self._warm_cache.values():
            for s in sessions:
                if s.session_id == session_id:
                    return s

        # 冷数据层
        return self._cold_cache.get(session_id)

    def migrate_to_cold(self, session_id: str) -> bool:
        """
        将会话迁移到冷数据层

        Args:
            session_id: 会话 ID

        Returns:
            bool: 是否迁移成功
        """
        # 从热点层获取
        session = self._hot_cache.get(session_id)
        if not session:
            return False

        # 移除热点层
        self._hot_cache.delete(session_id)

        # 放入冷数据层
        self._cold_cache[session_id] = session

        # 如果有 user_id，从温数据层移除
        if session.user_id and session.user_id in self._warm_cache:
            self._warm_cache[session.user_id] = [
                s for s in self._warm_cache[session.user_id]
                if s.session_id != session_id
            ]

        # 如果有向量索引，也迁移
        if session_id in self._vector_index:
            # 向量索引保持在冷数据层
            pass

        self._stats["tier_migrations"] += 1
        self._save_to_storage()

        logger.debug(f"会话迁移到冷数据层: {session_id}")
        return True

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """
        获取会话（自动在各层查找）

        Args:
            session_id: 会话 ID

        Returns:
            Optional[SessionData]: 会话数据
        """
        return self._get_session_by_id(session_id)

    def get_user_sessions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[SessionData]:
        """
        获取用户的所有会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            List[SessionData]: 会话列表
        """
        sessions = []

        # 从热点层获取该用户的会话
        for key in self._hot_cache.keys():
            session = self._hot_cache.get(key)
            if session and session.user_id == user_id:
                sessions.append(session)

        # 从温数据层获取
        if user_id in self._warm_cache:
            sessions.extend(self._warm_cache[user_id])

        # 从冷数据层获取
        for session in self._cold_cache.values():
            if session.user_id == user_id:
                sessions.append(session)

        # 按时间排序
        sessions.sort(key=lambda x: x.start_time, reverse=True)

        return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 是否删除成功
        """
        deleted = False

        # 从热点层删除
        if self._hot_cache.delete(session_id):
            deleted = True

        # 从温数据层删除
        for user_id, sessions in list(self._warm_cache.items()):
            self._warm_cache[user_id] = [s for s in sessions if s.session_id != session_id]
            if not self._warm_cache[user_id]:
                del self._warm_cache[user_id]

        # 从冷数据层删除
        if session_id in self._cold_cache:
            del self._cold_cache[session_id]
            deleted = True

        if deleted:
            self._save_to_storage()

        return deleted

    def clear_user_data(self, user_id: str) -> int:
        """
        清除用户的所有数据

        Args:
            user_id: 用户 ID

        Returns:
            int: 删除的会话数量
        """
        count = 0

        # 从热点层清除
        keys_to_delete = []
        for key in self._hot_cache.keys():
            session = self._hot_cache.get(key)
            if session and session.user_id == user_id:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            self._hot_cache.delete(key)
            count += 1

        # 从温数据层清除
        if user_id in self._warm_cache:
            count += len(self._warm_cache[user_id])
            del self._warm_cache[user_id]

        # 从冷数据层清除
        ids_to_delete = [
            sid for sid, session in self._cold_cache.items()
            if session.user_id == user_id
        ]
        for sid in ids_to_delete:
            del self._cold_cache[sid]
            count += 1

        if count > 0:
            self._save_to_storage()

        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            Dict: 统计信息
        """
        total_sessions = (
            len(self._hot_cache) +
            sum(len(sessions) for sessions in self._warm_cache.values()) +
            len(self._cold_cache)
        )

        return {
            "total_sessions": total_sessions,
            "hot_cache_size": len(self._hot_cache),
            "warm_cache_users": len(self._warm_cache),
            "cold_cache_size": len(self._cold_cache),
            "vector_index_size": len(self._vector_index),
            "stats": self._stats
        }

    def _save_to_storage(self) -> None:
        """保存到存储文件"""
        if not self._storage_path:
            return

        try:
            data = {
                "cold_cache": {
                    sid: session.to_dict()
                    for sid, session in self._cold_cache.items()
                },
                "vector_index": self._vector_index
            }
            with open(self._storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记忆存储失败: {e}")

    def _load_from_storage(self) -> None:
        """从存储文件加载"""
        if not self._storage_path:
            return

        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 加载冷数据
            for sid, session_data in data.get("cold_cache", {}).items():
                self._cold_cache[sid] = SessionData.from_dict(session_data)

            # 加载向量索引
            self._vector_index = data.get("vector_index", {})

            logger.info(f"加载记忆存储: {len(self._cold_cache)} 个冷会话")
        except FileNotFoundError:
            logger.info("记忆存储文件不存在")
        except Exception as e:
            logger.error(f"加载记忆存储失败: {e}")

    def export_to_json(self) -> Dict[str, Any]:
        """导出所有数据（不含向量）"""
        return {
            "hot_cache": {
                sid: session.to_dict()
                for sid, session in zip(self._hot_cache.keys(), self._hot_cache.values())
            },
            "cold_cache": {
                sid: session.to_dict()
                for sid, session in self._cold_cache.items()
            },
            "warm_cache": {
                uid: [s.to_dict() for s in sessions]
                for uid, sessions in self._warm_cache.items()
            }
        }

    async def enable_vector_search(self, embedding_model: Any) -> None:
        """
        启用向量检索

        Args:
            embedding_model: Embedding 模型
        """
        self._enable_vector_search = True
        self._embedding_model = embedding_model

        # 为现有会话生成向量索引
        for session in self._cold_cache.values():
            if session.session_id not in self._vector_index:
                await self._index_session_embedding(session)

        logger.info("向量检索已启用")
