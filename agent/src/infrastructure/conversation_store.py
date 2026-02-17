"""
================================================================================
对话历史向量存储模块 (Conversation Vector Store)

提供基于 Milvus 的对话历史存储和检索，支持：
- 对话历史向量化存储
- 相似对话检索
- 上下文增强回复
- 对话主题聚类

使用示例:
```python
from infrastructure.conversation_store import (
    ConversationVectorStore, Conversation,
    create_conversation_store
)

# 创建存储
store = await create_conversation_store()

# 存储对话
await store.store_conversation(
    session_id="session123",
    messages=[
        {"role": "user", "content": "我想去北京旅游"},
        {"role": "assistant", "content": "北京有很多好玩的地方..."}
    ],
    metadata={"user_id": "user123", "topic": "travel"}
)

# 搜索相似对话
similar = await store.search_similar_conversations(
    query="北京有什么美食",
    top_k=5
)

# 获取对话上下文
context = await store.get_conversation_context(session_id="session123")
```

================================================================================
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ConversationStatus(Enum):
    """对话状态"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class Message:
    """消息"""
    role: str  # user, assistant, system
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {})
        )


@dataclass
class Conversation:
    """对话"""
    session_id: str
    messages: List[Message]
    user_id: Optional[str] = None
    status: ConversationStatus = ConversationStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    vector_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "user_id": self.user_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "vector_id": self.vector_id
        }

    def get_summary(self) -> str:
        """获取对话摘要"""
        if not self.messages:
            return ""

        # 取前3条和后1条消息作为摘要
        preview = self.messages[:3]
        summary_parts = []

        for msg in preview:
            role = msg.role[:3]  # 取前3个字符
            content = msg.content[:50]  # 取前50个字符
            summary_parts.append(f"[{role}]: {content}")

        if len(self.messages) > 3:
            last_msg = self.messages[-1]
            summary_parts.append(f"... [{last_msg.role[:3]}]: {last_msg.content[:30]}")

        return " | ".join(summary_parts)

    def get_total_tokens(self) -> int:
        """估算总 token 数"""
        # 简单估算：平均 4 个字符 = 1 token
        return sum(len(m.content) // 4 for m in self.messages)


@dataclass
class ConversationSearchResult:
    """对话搜索结果"""
    session_id: str
    score: float
    messages: List[Message]
    summary: str
    metadata: Dict[str, Any]
    similarity: float = field(default_factory=lambda: 0.0)


@dataclass
class VectorStoreConfig:
    """向量存储配置"""
    host: str = "localhost"
    port: int = 19530
    db_name: str = "default"
    collection_name: str = "conversations"
    dimension: int = 768
    metric_type: str = "COSINE"
    index_type: str = "IVF_FLAT"


@dataclass
class ConversationStoreConfig:
    """对话存储配置"""
    # 对话存储
    max_messages_per_conversation: int = 100
    max_tokens_per_conversation: int = 16000

    # 检索配置
    default_top_k: int = 5
    min_similarity_threshold: float = 0.7

    # 自动归档
    auto_archive_days: int = 30
    archive_batch_size: int = 100

    # 向量配置
    vector_config: VectorStoreConfig = field(default_factory=VectorStoreConfig)


class ConversationEmbeddingGenerator:
    """
    对话嵌入生成器

    将对话内容转换为向量表示。
    """

    def __init__(self, embedding_model: Optional[Any] = None):
        """
        初始化嵌入生成器

        Args:
            embedding_model: 外部嵌入模型（可选）
        """
        self.embedding_model = embedding_model

    async def generate_conversation_embedding(
        self,
        conversation: Conversation
    ) -> List[float]:
        """
        生成对话向量

        Args:
            conversation: 对话对象

        Returns:
            List[float]: 向量
        """
        # 构建对话文本表示
        text = self._conversation_to_text(conversation)

        if self.embedding_model:
            return await self.embedding_model.encode(text)

        # 返回零向量（如果无嵌入模型）
        dim = self.embedding_model.dimension if self.embedding_model else 768
        return [0.0] * dim

    async def generate_query_embedding(
        self,
        query: str,
        context: Optional[str] = None
    ) -> List[float]:
        """
        生成查询向量

        Args:
            query: 查询文本
            context: 上下文信息

        Returns:
            List[float]: 向量
        """
        text = query
        if context:
            text = f"{context}\n\nQuery: {query}"

        if self.embedding_model:
            return await self.embedding_model.encode(text)

        dim = self.embedding_model.dimension if self.embedding_model else 768
        return [0.0] * dim

    def _conversation_to_text(self, conversation: Conversation) -> str:
        """将对话转换为文本"""
        parts = []

        # 添加元数据
        if conversation.user_id:
            parts.append(f"[User: {conversation.user_id}]")

        if conversation.metadata.get("topic"):
            parts.append(f"[Topic: {conversation.metadata['topic']}]")

        # 添加消息
        for msg in conversation.messages:
            role = msg.role.upper()
            content = msg.content.replace("\n", " ")
            parts.append(f"{role}: {content}")

        return " | ".join(parts)


class ConversationVectorStore:
    """
    对话历史向量存储

    基于 Milvus 存储对话历史，支持语义检索和上下文增强。
    """

    def __init__(
        self,
        config: Optional[ConversationStoreConfig] = None,
        embedding_generator: Optional[ConversationEmbeddingGenerator] = None
    ):
        """
        初始化对话存储

        Args:
            config: 存储配置
            embedding_generator: 嵌入生成器
        """
        self.config = config or ConversationStoreConfig()
        self.embedding_generator = embedding_generator or ConversationEmbeddingGenerator()
        self._initialized = False
        self._client = None

    @property
    def collection_name(self) -> str:
        """获取集合名称"""
        return self.config.vector_config.collection_name

    async def initialize(self) -> bool:
        """
        初始化 Milvus 连接

        Returns:
            bool: 是否成功
        """
        try:
            from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility

            cfg = self.config.vector_config

            # 连接 Milvus
            connections.connect(
                host=cfg.host,
                port=cfg.port,
                db_name=cfg.db_name
            )

            # 检查集合是否存在
            if not utility.has_collection(self.collection_name):
                # 定义 schema
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
                    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=cfg.dimension),
                    FieldSchema(name="session_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64, nullable=True),
                    FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=1000),
                    FieldSchema(name="first_message", dtype=DataType.VARCHAR, max_length=500),
                    FieldSchema(name="message_count", dtype=DataType.INT32),
                    FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=20),
                    FieldSchema(name="created_at", dtype=DataType.FLOAT),
                    FieldSchema(name="updated_at", dtype=DataType.FLOAT),
                    FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=4096)
                ]

                schema = CollectionSchema(fields=fields, description="Conversation history")

                # 创建集合
                collection = Collection(name=self.collection_name, schema=schema)

                # 创建索引
                index_params = {
                    "metric_type": cfg.metric_type,
                    "index_type": cfg.index_type,
                    "params": {"nlist": 1024}
                }
                collection.create_index(field_name="vector", index_params=index_params)

                logger.info(f"[ConversationStore] 创建集合: {self.collection_name}")
            else:
                collection = Collection(name=self.collection_name)
                collection.load()

            self._initialized = True
            logger.info(f"[ConversationStore] 初始化成功")
            return True

        except ImportError:
            logger.error("[ConversationStore] pymilvus 未安装")
            return False
        except Exception as e:
            logger.error(f"[ConversationStore] 初始化失败: {e}")
            return False

    async def store_conversation(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: ConversationStatus = ConversationStatus.ACTIVE
    ) -> str:
        """
        存储对话

        Args:
            session_id: 会话 ID
            messages: 消息列表
            user_id: 用户 ID
            metadata: 元数据
            status: 对话状态

        Returns:
            str: 向量 ID
        """
        if not self._initialized:
            if not await self.initialize():
                return ""

        try:
            from pymilvus import Collection

            # 创建对话对象
            conversation = Conversation(
                session_id=session_id,
                messages=[Message.from_dict(m) for m in messages],
                user_id=user_id,
                status=status,
                metadata=metadata or {}
            )

            # 生成向量
            vector = await self.embedding_generator.generate_conversation_embedding(conversation)

            # 生成唯一 ID
            vector_id = f"{session_id}_{int(time.time())}"

            # 准备数据
            summary = conversation.get_summary()[:1000]
            first_message = messages[0].get("content", "")[:500] if messages else ""
            message_count = len(messages)
            metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

            data = [
                [vector_id],  # id
                [vector],  # vector
                [session_id],  # session_id
                [user_id],  # user_id
                [summary],  # summary
                [first_message],  # first_message
                [message_count],  # message_count
                [status.value],  # status
                [time.time()],  # created_at
                [time.time()],  # updated_at
                [metadata_json]  # metadata
            ]

            collection = Collection(self.collection_name)
            collection.insert(data)

            logger.info(f"[ConversationStore] 存储对话: {session_id}")
            return vector_id

        except Exception as e:
            logger.error(f"[ConversationStore] 存储对话失败: {e}")
            return ""

    async def update_conversation(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新对话

        Args:
            session_id: 会话 ID
            messages: 新消息列表
            metadata: 新元数据

        Returns:
            bool: 是否成功
        """
        # 删除旧对话，存储新对话
        await self.delete_conversation(session_id)

        # 重新获取状态
        status = ConversationStatus.ACTIVE

        result = await self.store_conversation(
            session_id=session_id,
            messages=messages,
            metadata=metadata,
            status=status
        )

        return result != ""

    async def get_conversation(self, session_id: str) -> Optional[Conversation]:
        """
        获取对话

        Args:
            session_id: 会话 ID

        Returns:
            Optional[Conversation]: 对话对象
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)
            collection.load()

            # 查找对话
            results = collection.query(
                expr=f"session_id == '{session_id}'",
                output_fields=["*"],
                limit=1
            )

            if results:
                data = results[0]
                messages_json = data.get("metadata", "{}")
                messages_data = json.loads(messages_json).get("messages", [])

                return Conversation(
                    session_id=data["session_id"],
                    messages=[Message.from_dict(m) for m in messages_data],
                    user_id=data.get("user_id"),
                    status=ConversationStatus(data.get("status", "active")),
                    created_at=data.get("created_at", time.time()),
                    updated_at=data.get("updated_at", time.time()),
                    metadata=json.loads(data.get("metadata", "{}")),
                    vector_id=data.get("id")
                )

            return None

        except Exception as e:
            logger.error(f"[ConversationStore] 获取对话失败: {e}")
            return None

    async def search_similar_conversations(
        self,
        query: str,
        top_k: int = 5,
        user_id: Optional[str] = None,
        exclude_session_id: Optional[str] = None,
        min_similarity: float = 0.0
    ) -> List[ConversationSearchResult]:
        """
        搜索相似对话

        Args:
            query: 查询文本
            top_k: 返回数量
            user_id: 用户 ID（过滤）
            exclude_session_id: 排除的会话
            min_similarity: 最小相似度

        Returns:
            List[ConversationSearchResult]: 搜索结果
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            # 生成查询向量
            query_vector = await self.embedding_generator.generate_query_embedding(query)

            # 构建过滤表达式
            filters = []
            if user_id:
                filters.append(f"user_id == '{user_id}'")
            if exclude_session_id:
                filters.append(f"session_id != '{exclude_session_id}'")

            expr = " && ".join(filters) if filters else None

            # 搜索
            collection = Collection(self.collection_name)
            collection.load()

            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param={"metric_type": self.config.vector_config.metric_type, "params": {"nprobe": 10}},
                limit=top_k,
                expr=expr,
                output_fields=["session_id", "user_id", "summary", "first_message", "status", "metadata"]
            )

            search_results = []
            for hit in results[0]:
                data = hit.entity

                # 获取完整对话
                conversation = await self.get_conversation(data.get("session_id", ""))

                search_results.append(ConversationSearchResult(
                    session_id=data.get("session_id", ""),
                    score=hit.score,
                    messages=conversation.messages if conversation else [],
                    summary=data.get("summary", ""),
                    metadata={
                        "user_id": data.get("user_id"),
                        "status": data.get("status")
                    },
                    similarity=hit.score
                ))

            # 过滤低相似度
            if min_similarity > 0:
                search_results = [r for r in search_results if r.similarity >= min_similarity]

            return search_results

        except Exception as e:
            logger.error(f"[ConversationStore] 搜索对话失败: {e}")
            return []

    async def get_user_conversations(
        self,
        user_id: str,
        status: Optional[ConversationStatus] = None,
        limit: int = 20
    ) -> List[Conversation]:
        """
        获取用户的所有对话

        Args:
            user_id: 用户 ID
            status: 状态过滤
            limit: 返回数量

        Returns:
            List[Conversation]: 对话列表
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)
            collection.load()

            # 构建查询
            expr = f"user_id == '{user_id}'"
            if status:
                expr += f" && status == '{status.value}'"

            results = collection.query(
                expr=expr,
                output_fields=["*"],
                limit=limit,
                order_by="updated_at",
                hash_keys=[0]
            )

            conversations = []
            for data in results:
                conv = await self.get_conversation(data.get("session_id", ""))
                if conv:
                    conversations.append(conv)

            return conversations

        except Exception as e:
            logger.error(f"[ConversationStore] 获取用户对话失败: {e}")
            return []

    async def get_conversation_context(
        self,
        session_id: str,
        max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """
        获取对话上下文（用于 LLM 增强）

        Args:
            session_id: 会话 ID
            max_messages: 最大消息数

        Returns:
            List[Dict]: 消息列表
        """
        conversation = await self.get_conversation(session_id)

        if not conversation:
            return []

        # 截取最近的 N 条消息
        messages = conversation.messages[-max_messages:]

        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    async def find_contextual_conversations(
        self,
        current_session_id: str,
        query: str,
        max_results: int = 3
    ) -> List[Tuple[str, List[Dict[str, str]]]]:
        """
        查找相关历史对话作为上下文

        Args:
            current_session_id: 当前会话 ID
            query: 当前查询
            max_results: 最大结果数

        Returns:
            List[Tuple[会话ID, 消息列表]]: 相关对话
        """
        similar = await self.search_similar_conversations(
            query=query,
            top_k=max_results,
            exclude_session_id=current_session_id,
            min_similarity=self.config.min_similarity_threshold
        )

        results = []
        for result in similar:
            messages = [
                {"role": msg.role, "content": msg.content}
                for msg in result.messages
            ]
            results.append((result.session_id, messages))

        return results

    async def delete_conversation(self, session_id: str) -> bool:
        """
        删除对话

        Args:
            session_id: 会话 ID

        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            return True

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)
            collection.delete(f"session_id == '{session_id}'")

            logger.info(f"[ConversationStore] 删除对话: {session_id}")
            return True

        except Exception as e:
            logger.error(f"[ConversationStore] 删除对话失败: {e}")
            return False

    async def archive_old_conversations(
        self,
        days: int = 30,
        batch_size: int = 100
    ) -> int:
        """
        归档旧对话

        Args:
            days: 多少天前的对话
            batch_size: 每批处理数量

        Returns:
            int: 归档数量
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            cutoff_time = time.time() - (days * 86400)

            collection = Collection(self.collection_name)
            collection.load()

            # 查找需要归档的对话
            results = collection.query(
                expr=f"status == 'active' && updated_at < {cutoff_time}",
                output_fields=["id", "session_id"],
                limit=batch_size
            )

            archived = 0
            for data in results:
                await self.update_status(
                    data["session_id"],
                    ConversationStatus.ARCHIVED
                )
                archived += 1

            logger.info(f"[ConversationStore] 归档 {archived} 个旧对话")
            return archived

        except Exception as e:
            logger.error(f"[ConversationStore] 归档对话失败: {e}")
            return 0

    async def update_status(
        self,
        session_id: str,
        status: ConversationStatus
    ) -> bool:
        """
        更新对话状态

        Args:
            session_id: 会话 ID
            status: 新状态

        Returns:
            bool: 是否成功
        """
        if not self._initialized:
            return False

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            # 更新状态
            collection.update(
                expr=f"session_id == '{session_id}'",
                field_name="status",
                value=status.value
            )

            return True

        except Exception as e:
            logger.error(f"[ConversationStore] 更新状态失败: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        if not self._initialized:
            await self.initialize()

        try:
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            return {
                "collection_name": self.collection_name,
                "total_conversations": collection.num_entities,
                "active_conversations": 0,  # 需要查询统计
                "status": "healthy" if self._initialized else "not_initialized"
            }

        except Exception as e:
            logger.error(f"[ConversationStore] 获取统计失败: {e}")
            return {"error": str(e)}

    async def close(self) -> None:
        """关闭连接"""
        try:
            from pymilvus import connections
            connections.disconnect(self.config.vector_config.db_name)
            logger.info("[ConversationStore] 连接已关闭")
        except Exception as e:
            logger.error(f"[ConversationStore] 关闭连接失败: {e}")


# =============================================================================
# 便捷函数
# =============================================================================

async def create_conversation_store(
    host: str = "localhost",
    port: int = 19530,
    collection_name: str = "conversations",
    embedding_model: Optional[Any] = None
) -> ConversationVectorStore:
    """
    创建对话存储

    Args:
        host: Milvus 主机
        port: Milvus 端口
        collection_name: 集合名称
        embedding_model: 嵌入模型

    Returns:
        ConversationVectorStore: 存储实例
    """
    vector_config = VectorStoreConfig(
        host=host,
        port=port,
        collection_name=collection_name
    )

    store_config = ConversationStoreConfig(vector_config=vector_config)
    embedding_gen = ConversationEmbeddingGenerator(embedding_model)

    store = ConversationVectorStore(
        config=store_config,
        embedding_generator=embedding_gen
    )

    await store.initialize()
    return store


async def check_conversation_store_health() -> Dict[str, Any]:
    """
    检查对话存储健康状态

    Returns:
        Dict: 健康状态
    """
    try:
        store = await create_conversation_store()
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
