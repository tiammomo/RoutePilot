"""
上下文感知检索 (Context-Aware Memory Retrieval)

基于 RAG (Retrieval-Augmented Generation) 的记忆检索。

检索策略:
1. 当前任务上下文匹配
2. 用户画像偏好匹配
3. 时间相关性
4. 多样性 (避免相似结果重复)

使用示例:
    from memory.retrieval import ContextAwareRetrieval

    retrieval = ContextAwareRetrieval(
        hierarchical_store=store,
        profile_store=profile_store,
        vectorizer=vectorizer
    )

    results = await retrieval.retrieve(
        session_id="sess_123",
        user_id="user_456",
        current_query="推荐一个适合带孩子的海岛",
        top_k=3
    )
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RetrievedMemory:
    """检索到的记忆"""
    session_id: str
    content: str
    relevance_score: float
    source: str  # "semantic" | "profile" | "time" | "diversity"
    metadata: Dict[str, Any]


class ContextAwareRetrieval:
    """
    上下文感知的记忆检索

    使用多路检索策略:
    1. 语义检索 - 基于向量相似度
    2. 画像检索 - 基于用户偏好匹配
    3. 时间检索 - 基于时间相关性
    4. 多样性 - 使用 RRF 重排序避免重复
    """

    # RRF 评分参数
    RRF_K = 60

    def __init__(
        self,
        hierarchical_store: Optional[Any] = None,
        profile_store: Optional[Any] = None,
        vectorizer: Optional[Any] = None,
        default_top_k: int = 3
    ):
        """
        初始化上下文感知检索

        Args:
            hierarchical_store: 分层记忆存储
            profile_store: 用户画像存储
            vectorizer: 向量化器
            default_top_k: 默认返回数量
        """
        self.hierarchical_store = hierarchical_store
        self.profile_store = profile_store
        self.vectorizer = vectorizer
        self.default_top_k = default_top_k

    async def retrieve(
        self,
        session_id: str,
        user_id: str,
        current_query: str,
        top_k: Optional[int] = None
    ) -> List[RetrievedMemory]:
        """
        检索相关记忆

        Args:
            session_id: 当前会话 ID
            user_id: 用户 ID
            current_query: 当前查询
            top_k: 返回数量

        Returns:
            List[RetrievedMemory]: 检索结果列表
        """
        top_k = top_k or self.default_top_k

        # 1. 获取用户画像
        profile = None
        if self.profile_store and hasattr(self.profile_store, 'get'):
            profile = self.profile_store.get(user_id)

        # 2. 扩展查询（融入用户偏好）
        expanded_query = self._expand_query(current_query, profile)

        # 3. 多路检索
        results = await self._multi_way_search(
            expanded_query,
            profile,
            user_id,
            top_k * 2  # 多取一些用于重排序
        )

        # 4. RRF 重排序
        reranked = self._rerank(results, top_k)

        logger.info(
            f"Retrieved {len(reranked)} memories for user={user_id}"
        )

        return reranked

    def _expand_query(
        self,
        query: str,
        profile: Optional[Any]
    ) -> str:
        """
        扩展查询，融入用户画像

        Args:
            query: 原始查询
            profile: 用户画像

        Returns:
            str: 扩展后的查询
        """
        if not profile:
            return query

        # 尝试获取画像上下文
        if hasattr(profile, 'to_context_string'):
            user_context = profile.to_context_string()
        elif isinstance(profile, dict):
            # 从字典构建上下文
            parts = []
            for key, value in profile.items():
                if value:
                    parts.append(f"{key}: {value}")
            user_context = " | ".join(parts)
        else:
            return query

        if user_context:
            return f"{query} [用户偏好: {user_context}]"

        return query

    async def _multi_way_search(
        self,
        expanded_query: str,
        profile: Optional[Any],
        user_id: str,
        limit: int
    ) -> List[RetrievedMemory]:
        """
        多路检索

        Args:
            expanded_query: 扩展后的查询
            profile: 用户画像
            user_id: 用户 ID
            limit: 限制数量

        Returns:
            List[RetrievedMemory]: 检索结果
        """
        results: List[RetrievedMemory] = []

        # 1. 语义检索
        if self.vectorizer and self.hierarchical_store:
            semantic_results = await self._semantic_search(
                expanded_query,
                user_id,
                limit
            )
            results.extend(semantic_results)

        # 2. 画像检索
        if profile:
            profile_results = await self._profile_search(
                expanded_query,
                profile,
                limit
            )
            results.extend(profile_results)

        # 3. 时间检索
        time_results = await self._time_search(user_id, limit)
        results.extend(time_results)

        return results

    async def _semantic_search(
        self,
        query: str,
        user_id: str,
        limit: int
    ) -> List[RetrievedMemory]:
        """
        语义检索

        Args:
            query: 查询文本
            user_id: 用户 ID
            limit: 限制数量

        Returns:
            List[RetrievedMemory]: 语义检索结果
        """
        results: List[RetrievedMemory] = []

        try:
            # 生成查询向量
            if not self.vectorizer:
                return results

            query_vector = await self.vectorizer.embed_text(query)

            # 从层级存储获取会话向量
            if self.hierarchical_store and hasattr(
                self.hierarchical_store, 'get_all_sessions'
            ):
                sessions = await self.hierarchical_store.get_all_sessions(user_id)

                # 计算相似度
                for session in sessions[:limit]:
                    session_vector = session.get("vector")
                    if session_vector is None:
                        continue

                    # 计算余弦相似度
                    similarity = self._cosine_similarity(
                        query_vector,
                        np.array(session_vector)
                    )

                    results.append(RetrievedMemory(
                        session_id=session.get("session_id", ""),
                        content=session.get("summary", ""),
                        relevance_score=float(similarity),
                        source="semantic",
                        metadata=session
                    ))

        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")

        return results

    async def _profile_search(
        self,
        query: str,
        profile: Any,
        limit: int
    ) -> List[RetrievedMemory]:
        """
        基于用户画像的检索

        Args:
            query: 查询文本
            profile: 用户画像
            limit: 限制数量

        Returns:
            List[RetrievedMemory]: 画像检索结果
        """
        results: List[RetrievedMemory] = []

        try:
            # 从画像中提取偏好
            preferences = {}
            if hasattr(profile, 'travel_preferences'):
                preferences = profile.travel_preferences
            elif isinstance(profile, dict):
                preferences = profile.get("travel_preferences", {})

            if not preferences:
                return results

            # 计算查询与画像的匹配度
            query_lower = query.lower()
            match_score = 0.0
            matched_prefs = []

            for key, value in preferences.items():
                if not value:
                    continue
                if isinstance(value, list):
                    for v in value:
                        if v.lower() in query_lower:
                            match_score += 0.2
                            matched_prefs.append(f"{key}: {v}")
                elif str(value).lower() in query_lower:
                    match_score += 0.2
                    matched_prefs.append(f"{key}: {value}")

            # 归一化分数
            match_score = min(match_score, 1.0)

            if match_score > 0:
                results.append(RetrievedMemory(
                    session_id="profile_match",
                    content=f"用户偏好: {', '.join(matched_prefs)}",
                    relevance_score=match_score,
                    source="profile",
                    metadata={"preferences": preferences}
                ))

        except Exception as e:
            logger.warning(f"Profile search failed: {e}")

        return results

    async def _time_search(
        self,
        user_id: str,
        limit: int
    ) -> List[RetrievedMemory]:
        """
        基于时间的检索

        Args:
            user_id: 用户 ID
            limit: 限制数量

        Returns:
            List[RetrievedMemory]: 时间检索结果
        """
        results: List[RetrievedMemory] = []

        try:
            # 获取最近的会话
            if self.hierarchical_store and hasattr(
                self.hierarchical_store, 'get_recent_sessions'
            ):
                recent = await self.hierarchical_store.get_recent_sessions(
                    user_id,
                    limit
                )

                # 分配时间分数（最近的分数更高）
                for i, session in enumerate(recent):
                    time_score = 1.0 - (i / len(recent)) if recent else 0

                    results.append(RetrievedMemory(
                        session_id=session.get("session_id", ""),
                        content=session.get("summary", ""),
                        relevance_score=time_score * 0.5,  # 时间权重较低
                        source="time",
                        metadata=session
                    ))

        except Exception as e:
            logger.warning(f"Time search failed: {e}")

        return results

    def _rerank(
        self,
        results: List[RetrievedMemory],
        top_k: int
    ) -> List[RetrievedMemory]:
        """
        使用 RRF (Reciprocal Rank Fusion) 重排序

        Args:
            results: 原始检索结果
            top_k: 返回数量

        Returns:
            List[RetrievedMemory]: 重排序后的结果
        """
        if not results:
            return []

        # 按 session_id 分组
        session_groups: Dict[str, List[RetrievedMemory]] = {}
        for r in results:
            if r.session_id not in session_groups:
                session_groups[r.session_id] = []
            session_groups[r.session_id].append(r)

        # 计算 RRF 分数
        rrf_scores: Dict[str, float] = {}
        for session_id, group in session_groups.items():
            rrf_score = 0.0
            for rank, mem in enumerate(group, 1):
                rrf_score += mem.relevance_score / (self.RRF_K + rank)
            rrf_scores[session_id] = rrf_score

        # 按 RRF 分数排序
        sorted_sessions = sorted(
            rrf_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # 构建最终结果
        final_results: List[RetrievedMemory] = []
        for session_id, _ in sorted_sessions[:top_k]:
            # 取该 session 最高分的结果
            best = max(session_groups[session_id], key=lambda x: x.relevance_score)
            final_results.append(best)

        return final_results

    def _cosine_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray
    ) -> float:
        """
        计算余弦相似度

        Args:
            vec1: 向量 1
            vec2: 向量 2

        Returns:
            float: 相似度 [-1, 1]
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "hierarchical_store": self.hierarchical_store is not None,
            "profile_store": self.profile_store is not None,
            "vectorizer": self.vectorizer is not None,
            "default_top_k": self.default_top_k,
            "rrf_k": self.RRF_K
        }
