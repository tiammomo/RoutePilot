"""
对话向量化 (Conversation Vectorizer)

将对话转换为向量，用于语义相似度检索。

用途:
- 语义相似度检索
- 相关对话推荐
- 上下文补全

使用示例:
    from memory.vectorizer import ConversationVectorizer

    vectorizer = ConversationVectorizer(llm_client)
    vector = await vectorizer.embed_text("我想去海边旅游")
    # 返回: [0.12, -0.34, ...]

    # 会话向量化
    session_vector = await vectorizer.vectorize_session(session_data)
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)


class ConversationVectorizer:
    """
    对话向量化器

    策略: 多粒度向量化
    - 会话摘要向量 (粗粒度)
    - 关键事实向量 (细粒度)
    - 用户画像向量 (抽象)

    支持两种模式:
    1. LLM 嵌入模式: 使用 LLM API 获取向量
    2. TF-IDF 回退模式: 使用 TF-IDF 特征（无需外部 API）
    """

    # 旅行相关关键词（用于特征提取）
    TRAVEL_KEYWORDS = [
        "旅游", "旅行", "游玩", "度假", "出行", "目的地", "景点", "景区",
        "城市", "海岛", "山区", "古镇", "草原", "沙漠",
        "预算", "费用", "花费", "便宜", "贵", "性价比",
        "几天", "日程", "行程", "安排", "计划",
        "喜欢", "偏好", "想要", "兴趣", "风格",
        "美食", "历史", "文化", "自然", "风景",
        "人少", "人多", "拥挤", "安静", "热闹",
        "春天", "夏天", "秋天", "冬天", "季节"
    ]

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        embedding_dim: int = 1536,
        use_tfidf_fallback: bool = True
    ):
        """
        初始化对话向量化器

        Args:
            llm_client: LLM 客户端，用于生成嵌入
            embedding_dim: 嵌入向量维度
            use_tfidf_fallback: 是否使用 TF-IDF 回退
        """
        self.llm_client = llm_client
        self.embedding_dim = embedding_dim
        self.use_tfidf_fallback = use_tfidf_fallback
        self._tfidf_vectorizer = None

    async def embed_text(
        self,
        text: str,
        use_cache: bool = True
    ) -> np.ndarray:
        """
        将文本转换为向量

        Args:
            text: 输入文本
            use_cache: 是否使用缓存

        Returns:
            np.ndarray: 嵌入向量
        """
        if not text:
            return np.zeros(self.embedding_dim)

        # 优先使用 LLM 嵌入
        if self.llm_client:
            try:
                return await self._llm_embed(text)
            except Exception as e:
                logger.warning(f"LLM embed failed: {e}")

        # 回退到 TF-IDF
        if self.use_tfidf_fallback:
            return self._tfidf_embed(text)

        # 返回零向量
        return np.zeros(self.embedding_dim)

    async def _llm_embed(self, text: str) -> np.ndarray:
        """
        使用 LLM 生成嵌入

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 嵌入向量
        """
        # 尝试使用 LLM 的嵌入功能
        if hasattr(self.llm_client, 'embed'):
            return await self.llm_client.embed(text)

        # 如果 LLM 客户端没有 embed 方法，使用简单哈希
        return self._simple_hash_embed(text)

    def _simple_hash_embed(self, text: str) -> np.ndarray:
        """
        简单哈希嵌入（作为回退）

        基于文本特征生成伪向量

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 嵌入向量
        """
        # 基于关键词生成特征
        features = np.zeros(self.embedding_dim)

        text_lower = text.lower()
        for i, keyword in enumerate(self.TRAVEL_KEYWORDS):
            if keyword in text_lower:
                # 分散到不同维度
                idx = hash(keyword) % self.embedding_dim
                features[idx] = 1.0

        # 添加文本长度特征
        features[hash("length") % self.embedding_dim] = len(text) / 1000.0

        # 归一化
        norm = np.linalg.norm(features)
        if norm > 0:
            features = features / norm

        return features

    def _tfidf_embed(self, text: str) -> np.ndarray:
        """
        TF-IDF 嵌入

        Args:
            text: 输入文本

        Returns:
            np.ndarray: 嵌入向量
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            # 初始化 TF-IDF 向量化器
            if self._tfidf_vectorizer is None:
                self._tfidf_vectorizer = TfidfVectorizer(
                    max_features=self.embedding_dim,
                    ngram_range=(1, 2)
                )
                # 训练（使用关键词）
                self._tfidf_vectorizer.fit([ " ".join(self.TRAVEL_KEYWORDS)])

            # 转换
            vector = self._tfidf_vectorizer.transform([text])
            return vector.toarray()[0]

        except ImportError:
            logger.warning("sklearn not available, using hash embed")
            return self._simple_hash_embed(text)

    async def vectorize_session(
        self,
        session_data: Dict[str, Any]
    ) -> np.ndarray:
        """
        会话向量化 - 多粒度

        Args:
            session_data: 会话数据，应包含 summary, key_facts, user_preferences

        Returns:
            np.ndarray: 会话向量
        """
        vectors = []

        # 1. 摘要向量
        summary = session_data.get("summary", "")
        if summary:
            summary_vec = await self.embed_text(summary)
            vectors.append(summary_vec * 0.5)  # 权重较高

        # 2. 关键事实向量
        key_facts = session_data.get("key_facts", [])
        if key_facts:
            facts_text = " | ".join(key_facts)
            facts_vec = await self.embed_text(facts_text)
            vectors.append(facts_vec * 0.3)

        # 3. 用户偏好向量
        user_prefs = session_data.get("user_preferences", {})
        if user_prefs:
            pref_text = self._serialize_preferences(user_prefs)
            pref_vec = await self.embed_text(pref_text)
            vectors.append(pref_vec * 0.2)

        # 4. 主题向量
        topics = session_data.get("topics", [])
        if topics:
            topics_text = " ".join(topics)
            topics_vec = await self.embed_text(topics_text)
            vectors.append(topics_vec * 0.1)

        # 加权平均
        if vectors:
            return np.mean(vectors, axis=0)

        return np.zeros(self.embedding_dim)

    def _serialize_preferences(self, prefs: Dict[str, Any]) -> str:
        """
        序列化用户偏好为文本

        Args:
            prefs: 用户偏好字典

        Returns:
            str: 序列化文本
        """
        parts = []

        for key, value in prefs.items():
            if value is None:
                continue
            if isinstance(value, list):
                if value:
                    parts.append(f"{key}: {', '.join(map(str, value))}")
            else:
                parts.append(f"{key}: {value}")

        return " | ".join(parts)

    async def compute_similarity(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray
    ) -> float:
        """
        计算向量相似度

        Args:
            vec1: 向量 1
            vec2: 向量 2

        Returns:
            float: 余弦相似度 [-1, 1]
        """
        # 归一化
        vec1 = vec1 / (np.linalg.norm(vec1) + 1e-8)
        vec2 = vec2 / (np.linalg.norm(vec2) + 1e-8)

        # 余弦相似度
        return float(np.dot(vec1, vec2))

    async def find_similar_sessions(
        self,
        query_vector: np.ndarray,
        session_vectors: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        查找相似会话

        Args:
            query_vector: 查询向量
            session_vectors: 会话向量列表，每项包含 session_id 和 vector
            top_k: 返回前 k 个结果

        Returns:
            List[Dict]: 相似会话列表
        """
        similarities = []

        for session in session_vectors:
            sim = await self.compute_similarity(
                query_vector,
                session.get("vector", np.zeros(self.embedding_dim))
            )
            similarities.append({
                "session_id": session.get("session_id"),
                "similarity": sim,
                "data": session.get("data", {})
            })

        # 按相似度降序排序
        similarities.sort(key=lambda x: x["similarity"], reverse=True)

        return similarities[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "embedding_dim": self.embedding_dim,
            "llm_client": self.llm_client is not None,
            "use_tfidf_fallback": self.use_tfidf_fallback,
            "tfidf_available": self._tfidf_vectorizer is not None
        }
