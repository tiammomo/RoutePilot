"""
================================================================================
用户偏好向量存储模块 (User Preference Vector Store)

提供基于 Milvus 的用户偏好存储和检索，支持：
- 用户偏好向量存储
- 相似用户查找
- 个性化目的地推荐
- 偏好实时更新

使用示例:
```python
from infrastructure.user_preference_store import UserPreferenceStore

store = UserPreferenceStore(
    host="localhost",
    port=19530,
    collection_name="user_preferences"
)

# 存储用户偏好
await store.save_preferences(
    user_id="user123",
    preferences={
        "budget": "medium",
        "style": "adventure",
        "destinations": ["北京", "成都"],
        "activities": ["美食", "自然风光"]
    }
)

# 查找相似用户
similar_users = await store.find_similar_users("user123", top_k=5)

# 获取个性化推荐
recommendations = await store.get_recommendations("user123", query="海边度假")
```

================================================================================
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class PreferenceCategory(Enum):
    """偏好类别"""
    BUDGET = "budget"
    STYLE = "style"
    DESTINATION = "destination"
    ACTIVITY = "activity"
    SEASON = "season"
    ACCOMMODATION = "accommodation"
    TRANSPORT = "transport"


@dataclass
class UserPreference:
    """用户偏好"""
    user_id: str
    preferences: Dict[str, Any]
    vector: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "preferences": self.preferences,
            "vector": self.vector,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class RecommendationResult:
    """推荐结果"""
    item_id: str
    score: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorStoreConfig:
    """向量存储配置"""
    host: str = "localhost"
    port: int = 19530
    db_name: str = "default"
    collection_name: str = "user_preferences"
    dimension: int = 512
    metric_type: str = "COSINE"
    index_type: str = "FLAT"
    prefer_update: bool = True  # 偏好更新而非覆盖


class PreferenceEmbeddingGenerator:
    """
    偏好嵌入生成器

    将用户偏好转换为向量表示。
    """

    # 偏好到向量的映射（简化版，实际可接入 embedding API）
    BUDGET_EMBEDDINGS = {
        "economy": [0.1, 0.0, 0.0, 0.0, 0.0],
        "medium": [0.5, 0.0, 0.0, 0.0, 0.0],
        "luxury": [0.9, 0.0, 0.0, 0.0, 0.0],
        "budget": [0.0, 0.1, 0.0, 0.0, 0.0],
        "expensive": [0.0, 0.9, 0.0, 0.0, 0.0]
    }

    STYLE_EMBEDDINGS = {
        "adventure": [0.0, 0.0, 0.1, 0.0, 0.0],
        "relaxation": [0.0, 0.0, 0.9, 0.0, 0.0],
        "cultural": [0.0, 0.0, 0.0, 0.1, 0.0],
        "family": [0.0, 0.0, 0.0, 0.9, 0.0],
        "romantic": [0.0, 0.0, 0.0, 0.0, 0.1]
    }

    def __init__(self, embedding_model: Optional[Any] = None):
        """
        初始化嵌入生成器

        Args:
            embedding_model: 外部嵌入模型（可选）
        """
        self.embedding_model = embedding_model

    async def generate_preference_vector(
        self,
        preferences: Dict[str, Any]
    ) -> List[float]:
        """
        生成偏好向量

        Args:
            preferences: 偏好字典

        Returns:
            List[float]: 偏好向量
        """
        # 如果有外部嵌入模型，使用它
        if self.embedding_model:
            # 构建偏好文本
            pref_text = self._preferences_to_text(preferences)
            return await self.embedding_model.encode(pref_text)

        # 否则使用规则生成向量
        return self._rule_based_vector(preferences)

    def _preferences_to_text(self, preferences: Dict[str, Any]) -> str:
        """将偏好转换为文本"""
        parts = []

        if "budget" in preferences:
            parts.append(f"预算:{preferences['budget']}")
        if "style" in preferences:
            parts.append(f"风格:{preferences['style']}")
        if "destinations" in preferences:
            parts.append(f"想去:{' '.join(preferences['destinations'])}")
        if "activities" in preferences:
            parts.append(f"喜欢:{' '.join(preferences['activities'])}")

        return " ".join(parts) if parts else "旅行偏好"

    def _rule_based_vector(self, preferences: Dict[str, Any]) -> List[float]:
        """
        基于规则的向量生成

        生成一个固定维度的向量表示用户偏好。
        """
        # 基础向量
        vector = [0.0] * 512

        # 预算编码 (位置 0-99)
        budget = preferences.get("budget", "").lower()
        if "economy" in budget or "budget" in budget:
            vector[0] = 0.2
        elif "medium" in budget:
            vector[0] = 0.5
        elif "luxury" in budget or "expensive" in budget:
            vector[0] = 0.8

        # 风格编码 (位置 100-199)
        style = preferences.get("style", "").lower()
        if "adventure" in style:
            vector[100] = 0.9
        elif "relax" in style:
            vector[101] = 0.9
        elif "cultural" in style:
            vector[102] = 0.9
        elif "family" in style:
            vector[103] = 0.9
        elif "romantic" in style:
            vector[104] = 0.9

        # 目的地编码 (位置 200-299)
        destinations = preferences.get("destinations", [])
        for i, dest in enumerate(destinations[:5]):  # 最多5个
            dest_hash = self._hash_string(dest)
            vector[200 + (dest_hash % 50)] = 0.7

        # 活动编码 (位置 300-399)
        activities = preferences.get("activities", [])
        for i, activity in enumerate(activities[:5]):  # 最多5个
            activity_hash = self._hash_string(activity)
            vector[300 + (activity_hash % 50)] = 0.7

        # 季节偏好 (位置 400-499)
        season = preferences.get("season", "").lower()
        if "spring" in season:
            vector[400] = 0.8
        elif "summer" in season:
            vector[401] = 0.8
        elif "autumn" in season or "fall" in season:
            vector[402] = 0.8
        elif "winter" in season:
            vector[403] = 0.8

        # 归一化
        norm = sum(v * v for v in vector) ** 0.5
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def _hash_string(self, text: str) -> int:
        """字符串哈希"""
        return int(hashlib.md5(text.encode('utf-8')).hexdigest(), 16) % 1000


class UserPreferenceStore:
    """
    用户偏好向量存储

    基于 Milvus 存储用户偏好，支持相似用户查找和个性化推荐。
    """

    def __init__(
        self,
        config: Optional[VectorStoreConfig] = None,
        embedding_generator: Optional[PreferenceEmbeddingGenerator] = None
    ):
        """
        初始化用户偏好存储

        Args:
            config: 存储配置
            embedding_generator: 嵌入生成器
        """
        self.config = config or VectorStoreConfig()
        self.embedding_generator = embedding_generator or PreferenceEmbeddingGenerator()
        self._milvus_client = None
        self._initialized = False

    @property
    def collection_name(self) -> str:
        """获取集合名称"""
        return self.config.collection_name

    async def initialize(self) -> bool:
        """
        初始化 Milvus 连接

        Returns:
            bool: 是否成功
        """
        try:
            from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType
            from infrastructure.milvus_vector import MilvusVectorStore, MilvusConfig, DistanceMetric, IndexType

            # 连接 Milvus
            connections.connect(
                host=self.config.host,
                port=self.config.port,
                db_name=self.config.db_name
            )

            # 检查集合是否存在，不存在则创建
            from pymilvus import utility
            if not utility.has_collection(self.collection_name):
                # 定义集合 schema
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
                    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.config.dimension),
                    FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="preferences", dtype=DataType.VARCHAR, max_length=4096),
                    FieldSchema(name="created_at", dtype=DataType.FLOAT),
                    FieldSchema(name="updated_at", dtype=DataType.FLOAT)
                ]

                schema = CollectionSchema(fields=fields, description="User preferences")

                # 创建集合
                collection = Collection(name=self.collection_name, schema=schema)

                # 创建索引
                index_params = {
                    "metric_type": self.config.metric_type,
                    "index_type": self.config.index_type,
                    "params": {}
                }
                collection.create_index(field_name="vector", index_params=index_params)

                logger.info(f"[UserPreferenceStore] 创建集合: {self.collection_name}")
            else:
                collection = Collection(name=self.collection_name)
                collection.load()

            self._initialized = True
            logger.info(f"[UserPreferenceStore] 初始化成功: {self.config.host}:{self.config.port}")
            return True

        except ImportError:
            logger.error("[UserPreferenceStore] pymilvus 未安装")
            return False
        except Exception as e:
            logger.error(f"[UserPreferenceStore] 初始化失败: {e}")
            return False

    async def save_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any],
        vector: Optional[List[float]] = None
    ) -> bool:
        """
        保存用户偏好

        Args:
            user_id: 用户 ID
            preferences: 偏好字典
            vector: 预计算的向量（可选）

        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            from pymilvus import Collection

            # 生成向量
            if vector is None:
                vector = await self.embedding_generator.generate_preference_vector(preferences)

            # 生成唯一 ID
            preference_id = f"{user_id}_{int(time.time())}"

            # 序列化偏好
            preferences_json = json.dumps(preferences, ensure_ascii=False)

            # 准备插入数据
            collection = Collection(self.collection_name)
            data = [
                [preference_id],  # id
                [vector],  # vector
                [user_id],  # user_id
                [preferences_json],  # preferences
                [time.time()],  # created_at
                [time.time()]  # updated_at
            ]

            collection.insert(data)
            logger.info(f"[UserPreferenceStore] 保存偏好: user_id={user_id}")
            return True

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 保存偏好失败: {e}")
            return False

    async def update_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any],
        merge: bool = True
    ) -> bool:
        """
        更新用户偏好

        Args:
            user_id: 用户 ID
            preferences: 新偏好
            merge: 是否合并现有偏好

        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            from pymilvus import Collection

            # 如果需要合并，先获取现有偏好
            existing_prefs = {}
            if merge:
                existing_prefs = await self.get_preferences(user_id)
                if existing_prefs:
                    existing_prefs.update(preferences)
                    preferences = existing_prefs

            # 生成向量
            vector = await self.embedding_generator.generate_preference_vector(preferences)

            # 删除旧偏好，插入新偏好
            await self.delete_preferences(user_id)
            return await self.save_preferences(user_id, preferences, vector)

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 更新偏好失败: {e}")
            return False

    async def get_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户偏好

        Args:
            user_id: 用户 ID

        Returns:
            Optional[Dict]: 偏好字典，不存在返回 None
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)
            collection.load()

            # 查找最新的偏好记录
            expr = f"user_id == '{user_id}'"
            results = collection.query(
                expr=expr,
                output_fields=["preferences", "created_at"],
                limit=1,
                anns_field="vector",
                search_params={},
                data=[[0.0] * self.config.dimension]
            )

            if results:
                preferences_json = results[0].get("preferences", "{}")
                return json.loads(preferences_json)

            return None

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 获取偏好失败: {e}")
            return None

    async def find_similar_users(
        self,
        user_id: str,
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        查找相似用户

        Args:
            user_id: 用户 ID
            top_k: 返回数量

        Returns:
            List[Tuple[str, float]]: (用户ID, 相似度分数) 列表
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            # 获取目标用户的向量
            user_prefs = await self.get_preferences(user_id)
            if not user_prefs:
                logger.warning(f"[UserPreferenceStore] 用户偏好不存在: {user_id}")
                return []

            query_vector = await self.embedding_generator.generate_preference_vector(user_prefs)

            # 搜索相似用户
            collection = Collection(self.collection_name)
            collection.load()

            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param={"metric_type": self.config.metric_type, "params": {"nprobe": 10}},
                limit=top_k + 1,  # +1 因为可能包含自己
                expr=f"user_id != '{user_id}'",
                output_fields=["user_id"]
            )

            similar_users = []
            for hit in results[0]:
                similar_users.append((hit.entity.get("user_id", ""), hit.score))

            return similar_users

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 查找相似用户失败: {e}")
            return []

    async def get_recommendations(
        self,
        user_id: str,
        query: str = "",
        top_k: int = 10
    ) -> List[RecommendationResult]:
        """
        获取个性化推荐

        Args:
            user_id: 用户 ID
            query: 查询文本（如"海边度假"）
            top_k: 返回数量

        Returns:
            List[RecommendationResult]: 推荐结果列表
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            # 获取用户偏好
            user_prefs = await self.get_preferences(user_id)

            # 生成查询向量
            if query:
                # 如果有查询，结合用户偏好和查询
                combined_prefs = user_prefs or {}
                combined_prefs["query_hint"] = query
                query_vector = await self.embedding_generator.generate_preference_vector(combined_prefs)
            else:
                query_vector = await self.embedding_generator.generate_preference_vector(user_prefs or {})

            # 搜索相似偏好
            collection = Collection(self.collection_name)
            collection.load()

            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param={"metric_type": self.config.metric_type, "params": {"nprobe": 10}},
                limit=top_k,
                output_fields=["user_id", "preferences"]
            )

            recommendations = []
            for hit in results[0]:
                prefs_json = hit.entity.get("preferences", "{}")
                prefs = json.loads(prefs_json)

                # 生成推荐理由
                reason = self._generate_reason(prefs, user_prefs)

                recommendations.append(RecommendationResult(
                    item_id=hit.entity.get("user_id", ""),
                    score=hit.score,
                    reason=reason,
                    metadata=prefs
                ))

            return recommendations

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 获取推荐失败: {e}")
            return []

    def _generate_reason(
        self,
        preferences: Dict[str, Any],
        user_prefs: Optional[Dict[str, Any]]
    ) -> str:
        """生成推荐理由"""
        reasons = []

        if user_prefs:
            # 比较偏好差异
            if "destinations" in preferences and "destinations" in user_prefs:
                common = set(preferences.get("destinations", [])) & set(user_prefs.get("destinations", []))
                if common:
                    reasons.append(f"你们都想去: {', '.join(list(common)[:3])}")

            if "style" in preferences and preferences.get("style") == user_prefs.get("style"):
                reasons.append(f"风格相似: {preferences.get('style')}")

        return " | ".join(reasons) if reasons else "基于旅行偏好匹配"

    async def delete_preferences(self, user_id: str) -> bool:
        """
        删除用户偏好

        Args:
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            return True

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)
            expr = f"user_id == '{user_id}'"
            collection.delete(expr)
            logger.info(f"[UserPreferenceStore] 删除偏好: user_id={user_id}")
            return True

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 删除偏好失败: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection, utility

            collection = Collection(self.collection_name)
            stats = {
                "collection_name": self.collection_name,
                "num_entities": collection.num_entities,
                "is_loaded": collection.is_loaded
            }

            return stats

        except Exception as e:
            logger.error(f"[UserPreferenceStore] 获取统计失败: {e}")
            return {"error": str(e)}

    async def close(self) -> None:
        """关闭连接"""
        try:
            from pymilvus import connections
            connections.disconnect(self.config.db_name)
            logger.info("[UserPreferenceStore] 连接已关闭")
        except Exception as e:
            logger.error(f"[UserPreferenceStore] 关闭连接失败: {e}")


# =============================================================================
# 便捷函数
# =============================================================================

async def create_user_preference_store(
    host: str = "localhost",
    port: int = 19530,
    collection_name: str = "user_preferences",
    embedding_model: Optional[Any] = None
) -> UserPreferenceStore:
    """
    创建用户偏好存储

    Args:
        host: Milvus 主机
        port: Milvus 端口
        collection_name: 集合名称
        embedding_model: 嵌入模型

    Returns:
        UserPreferenceStore: 存储实例
    """
    config = VectorStoreConfig(
        host=host,
        port=port,
        collection_name=collection_name
    )
    embedding_gen = PreferenceEmbeddingGenerator(embedding_model)

    store = UserPreferenceStore(config=config, embedding_generator=embedding_gen)
    await store.initialize()

    return store


async def check_preference_store_health() -> Dict[str, Any]:
    """
    检查偏好存储健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        store = await create_user_preference_store()
        stats = await store.get_stats()
        await store.close()

        return {
            "status": "healthy",
            "stats": stats
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
