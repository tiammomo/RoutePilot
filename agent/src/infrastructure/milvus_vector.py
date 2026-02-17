"""
================================================================================
基础设施层 - Milvus 向量数据库 (Milvus Vector Database)

提供 Milvus 向量数据库的集成支持，支持向量存储、搜索、索引管理等功能。

功能特点:
- 向量插入和批量插入
- 向量搜索
- 集合管理
- 索引管理
- 混合搜索支持

使用示例:
```python
from infrastructure.milvus_vector import MilvusVectorStore, DistanceMetric

store = MilvusVectorStore(
    collection_name="travel_documents",
    dim=1024
)

# 存储向量
ids = await store.insert(vectors, payloads)

# 搜索相似向量
results = await store.search(query_vector, top_k=10)
```

================================================================================
"""

import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class DistanceMetric(Enum):
    """距离度量"""
    COSINE = "COSINE"       # 余弦相似度
    L2 = "L2"              # 欧氏距离
    IP = "IP"              # 内积


class IndexType(Enum):
    """索引类型"""
    FLAT = "FLAT"
    IVF_FLAT = "IVF_FLAT"
    IVF_SQ8 = "IVF_SQ8"
    HNSW = "HNSW"
    SCANN = "SCANN"


@dataclass
class MilvusConfig:
    """Milvus 配置"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        db_name: str = "default",
        user: Optional[str] = None,
        password: Optional[str] = None,
        secure: bool = False,
        timeout: float = 30.0,
        pool_size: int = 10
    ):
        self.host = host
        self.port = port
        self.db_name = db_name
        self.user = user
        self.password = password
        self.secure = secure
        self.timeout = timeout
        self.pool_size = pool_size


@dataclass
class SearchResult:
    """搜索结果"""
    id: int
    score: float
    payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "payload": self.payload
        }


@dataclass
class CollectionSchema:
    """集合模式"""
    fields: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""
    enable_dynamic: bool = True


class MilvusVectorStore:
    """
    Milvus 向量存储

    提供 Milvus 向量数据库的操作接口。
    """

    def __init__(
        self,
        collection_name: str,
        dim: int,
        config: Optional[MilvusConfig] = None,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        index_type: IndexType = IndexType.FLAT,
        index_params: Optional[Dict[str, Any]] = None
    ):
        """
        初始化向量存储

        Args:
            collection_name: 集合名称
            dim: 向量维度
            config: Milvus 配置
            distance_metric: 距离度量
            index_type: 索引类型
            index_params: 索引参数
        """
        self.collection_name = collection_name
        self.dim = dim
        self.config = config or MilvusConfig()
        self.distance_metric = distance_metric
        self.index_type = index_type
        self.index_params = index_params or self._get_default_index_params()
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None

    def _get_default_index_params(self) -> Dict[str, Any]:
        """获取默认索引参数"""
        if self.index_type == IndexType.FLAT:
            return {"metric_type": self.distance_metric.value}
        elif self.index_type == IndexType.IVF_FLAT:
            return {
                "metric_type": self.distance_metric.value,
                "nlist": 1024
            }
        elif self.index_type == IndexType.HNSW:
            return {
                "metric_type": self.distance_metric.value,
                "M": 16,
                "efConstruction": 200
            }
        return {"metric_type": self.distance_metric.value}

    async def connect(self) -> None:
        """连接 Milvus"""
        try:
            from pymilvus import connections, Collection

            connections.connect(
                host=self.config.host,
                port=str(self.config.port),
                db_name=self.config.db_name,
                user=self.config.user,
                password=self.config.password,
                secure=self.config.secure,
                timeout=self.config.timeout
            )

            self._client = connections._fetch_handler()

            # 检查集合是否存在
            from pymilvus import utility
            if utility.has_collection(self.collection_name):
                self._collection = Collection(self.collection_name)
                self._collection.load()
                logger.info(f"[Milvus] 加载已存在的集合: {self.collection_name}")
            else:
                logger.info(f"[Milvus] 集合不存在，将创建: {self.collection_name}")

            logger.info(f"[Milvus] 连接成功: {self.config.host}:{self.config.port}")

        except ImportError:
            logger.warning("[Milvus] pymilvus 未安装，使用模拟模式")
            self._client = "mock"

    async def create_collection(
        self,
        schema: Optional[CollectionSchema] = None
    ) -> bool:
        """
        创建集合

        Args:
            schema: 集合模式

        Returns:
            bool: 是否成功
        """
        try:
            from pymilvus import (
                connections, Collection, CollectionSchema,
                FieldSchema, DataType, utility
            )

            if not self._client or self._client == "mock":
                logger.warning("[Milvus] 未连接，跳过创建集合")
                return False

            if utility.has_collection(self.collection_name):
                logger.info(f"[Milvus] 集合已存在: {self.collection_name}")
                self._collection = Collection(self.collection_name)
                return True

            # 默认字段
            fields = schema.fields if schema else [
                FieldSchema(
                    name="id",
                    dtype=DataType.INT64,
                    is_primary=True,
                    auto_id=True
                ),
                FieldSchema(
                    name="vector",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.dim
                ),
                FieldSchema(
                    name="payload",
                    dtype=DataType.JSON,
                    enable_dynamic=True
                ),
                FieldSchema(
                    name="created_at",
                    dtype=DataType.VARCHAR,
                    max_length=64
                )
            ]

            collection_schema = CollectionSchema(
                fields=fields,
                description=schema.description if schema else "Travel documents collection",
                enable_dynamic=getattr(schema, 'enable_dynamic', True) if schema else True
            )

            self._collection = Collection(
                name=self.collection_name,
                schema=collection_schema
            )

            # 创建索引
            index_params = {
                "metric_type": self.distance_metric.value,
                "index_type": self.index_type.value,
                "params": self.index_params
            }
            self._collection.create_index(
                field_name="vector",
                index_params=index_params
            )

            self._collection.load()
            logger.info(f"[Milvus] 创建集合成功: {self.collection_name}")
            return True

        except ImportError:
            logger.warning("[Milvus] pymilvus 未安装")
            return False

    async def insert(
        self,
        vectors: Union[List[List[float]], np.ndarray],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[int]] = None
    ) -> List[int]:
        """
        插入向量

        Args:
            vectors: 向量列表或 numpy 数组
            payloads: 载荷列表
            ids: 指定 ID 列表

        Returns:
            List[int]: 插入的 ID 列表
        """
        if self._collection is None or self._client == "mock":
            logger.warning("[Milvus] 集合未加载，返回模拟 ID")
            return list(range(len(vectors)))

        if isinstance(vectors, np.ndarray):
            vectors = vectors.tolist()

        # 准备数据
        data = [vectors]

        if payloads:
            now = datetime.now().isoformat()
            data.append([
                {**payload, "created_at": now}
                for payload in payloads
            ])

        # 插入数据
        result = self._collection.insert(data)
        ids = result.primary_keys

        logger.info(f"[Milvus] 插入 {len(ids)} 条向量")
        return ids

    async def search(
        self,
        query_vector: Union[List[float], np.ndarray],
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        output_fields: Optional[List[str]] = None
    ) -> List[SearchResult]:
        """
        搜索相似向量

        Args:
            query_vector: 查询向量
            top_k: 返回数量
            filter_expr: 过滤表达式
            output_fields: 输出字段

        Returns:
            List[SearchResult]: 搜索结果
        """
        if self._collection is None or self._client == "mock":
            logger.warning("[Milvus] 集合未加载，返回空结果")
            return []

        if isinstance(query_vector, np.ndarray):
            query_vector = query_vector.tolist()

        search_params = {
            "metric_type": self.distance_metric.value,
            "params": {"nprobe": 10}
        }

        result = self._collection.search(
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=output_fields or ["payload"]
        )

        results = []
        for hits in result:
            for hit in hits:
                payload = None
                if hasattr(hit, 'entity') and hasattr(hit.entity, 'get'):
                    payload = hit.entity.get('payload')
                elif hasattr(hit, 'payload'):
                    payload = hit.payload

                results.append(SearchResult(
                    id=hit.id,
                    score=hit.score,
                    payload=payload
                ))

        logger.info(f"[Milvus] 搜索完成，返回 {len(results)} 条结果")
        return results

    async def batch_search(
        self,
        query_vectors: Union[List[List[float]], np.ndarray],
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        output_fields: Optional[List[str]] = None
    ) -> List[List[SearchResult]]:
        """
        批量搜索

        Args:
            query_vectors: 查询向量列表
            top_k: 返回数量
            filter_expr: 过滤表达式
            output_fields: 输出字段

        Returns:
            List[List[SearchResult]]: 每个查询的结果列表
        """
        if self._collection is None or self._client == "mock":
            return [[] for _ in query_vectors]

        if isinstance(query_vectors, np.ndarray):
            query_vectors = query_vectors.tolist()

        search_params = {
            "metric_type": self.distance_metric.value,
            "params": {"nprobe": 10}
        }

        result = self._collection.search(
            data=query_vectors,
            anns_field="vector",
            param=search_params,
            limit=top_k,
            expr=filter_expr,
            output_fields=output_fields or ["payload"]
        )

        all_results = []
        for hits in result:
            results = []
            for hit in hits:
                payload = None
                if hasattr(hit, 'entity') and hasattr(hit.entity, 'get'):
                    payload = hit.entity.get('payload')
                elif hasattr(hit, 'payload'):
                    payload = hit.payload

                results.append(SearchResult(
                    id=hit.id,
                    score=hit.score,
                    payload=payload
                ))
            all_results.append(results)

        logger.info(f"[Milvus] 批量搜索完成: {len(query_vectors)} 个查询")
        return all_results

    async def delete_by_id(self, ids: List[int]) -> int:
        """
        按 ID 删除

        Args:
            ids: ID 列表

        Returns:
            int: 删除数量
        """
        if self._collection is None or self._client == "mock":
            return len(ids)

        expr = f"id in {ids}"
        result = self._collection.delete(expr)
        count = result.delete_count

        logger.info(f"[Milvus] 删除 {count} 条记录")
        return count

    async def delete_by_filter(self, filter_expr: str) -> int:
        """
        按条件删除

        Args:
            filter_expr: 过滤表达式

        Returns:
            int: 删除数量
        """
        if self._collection is None or self._client == "mock":
            return 0

        result = self._collection.delete(filter_expr)
        count = result.delete_count

        logger.info(f"[Milvus] 按条件删除 {count} 条记录")
        return count

    async def get_count(self) -> int:
        """获取集合中的向量数量"""
        if self._collection is None or self._client == "mock":
            return 0

        return self._collection.num_entities

    async def flush(self) -> bool:
        """刷新数据到磁盘"""
        if self._collection is None or self._client == "mock":
            return False

        self._collection.flush()
        logger.info("[Milvus] 数据已刷新")
        return True

    async def compact(self) -> bool:
        """压缩集合"""
        if self._collection is None or self._client == "mock":
            return False

        self._collection.compact()
        logger.info("[Milvus] 集合已压缩")
        return True

    async def drop_collection(self) -> bool:
        """删除集合"""
        try:
            from pymilvus import utility

            if self._collection:
                self._collection.release()
                self._collection = None

            utility.drop_collection(self.collection_name)
            logger.info(f"[Milvus] 集合已删除: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"[Milvus] 删除集合失败: {e}")
            return False

    async def close(self) -> None:
        """关闭连接"""
        if self._collection:
            self._collection.release()
            self._collection = None

        if self._client and self._client != "mock":
            try:
                from pymilvus import connections
                connections.disconnect()
            except Exception:
                pass

        logger.info("[Milvus] 连接已关闭")


class VectorProcessor:
    """
    向量处理器

    提供向量生成、处理、管理功能。
    """

    def __init__(self, embedding_model: Optional[Any] = None):
        """
        初始化向量处理器

        Args:
            embedding_model: 嵌入模型
        """
        self.embedding_model = embedding_model

    async def embed_texts(
        self,
        texts: List[str],
        normalize: bool = True
    ) -> List[List[float]]:
        """
        生成文本向量

        Args:
            texts: 文本列表
            normalize: 是否归一化

        Returns:
            List[List[float]]: 向量列表
        """
        if self.embedding_model is None:
            logger.warning("[VectorProcessor] 未配置嵌入模型，返回随机向量")
            import random
            dim = 1024
            vectors = [[random.random() for _ in range(dim)] for _ in texts]
            if normalize:
                for v in vectors:
                    norm = sum(x * x for x in v) ** 0.5
                    v[:] = [x / norm for x in v]
            return vectors

        # 使用实际模型
        try:
            vectors = self.embedding_model.encode(texts).tolist()
            if normalize:
                import numpy as np
                vectors = np.array(vectors)
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                vectors = (vectors / norms).tolist()
            return vectors
        except Exception as e:
            logger.error(f"[VectorProcessor] 生成向量失败: {e}")
            raise

    async def embed_query(self, query: str) -> List[float]:
        """
        生成查询向量

        Args:
            query: 查询文本

        Returns:
            List[float]: 向量
        """
        vectors = await self.embed_texts([query])
        return vectors[0]

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
        separators: List[str] = ["。", "！", "？", "\n", "；", "，", ".", "!", "?", ",", ";"]
    ) -> List[str]:
        """
        分割文本

        Args:
            text: 文本
            chunk_size: 块大小
            overlap: 重叠大小
            separators: 分隔符列表

        Returns:
            List[str]: 文本块列表
        """
        chunks = []
        current_chunk = ""
        current_length = 0

        for char in text:
            current_chunk += char
            current_length += 1

            # 检查是否到达分隔符
            if char in separators and current_length >= chunk_size // 2:
                chunks.append(current_chunk.strip())
                current_chunk = ""
                current_length = 0
            # 检查是否达到最大块大小
            elif current_length >= chunk_size:
                chunks.append(current_chunk.strip())
                current_chunk = current_chunk[-overlap:] if overlap > 0 else ""
                current_length = len(current_chunk)

        # 添加剩余内容
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        if not chunks:
            chunks = [text]

        return chunks


# 便捷函数
def create_milvus_store(
    collection_name: str,
    dim: int,
    host: str = "localhost",
    port: int = 19530,
    distance_metric: DistanceMetric = DistanceMetric.COSINE,
    index_type: IndexType = IndexType.FLAT
) -> MilvusVectorStore:
    """
    创建 Milvus 向量存储

    Args:
        collection_name: 集合名称
        dim: 向量维度
        host: 主机地址
        port: 端口
        distance_metric: 距离度量
        index_type: 索引类型

    Returns:
        MilvusVectorStore: 向量存储实例
    """
    config = MilvusConfig(host=host, port=port)
    return MilvusVectorStore(
        collection_name=collection_name,
        dim=dim,
        config=config,
        distance_metric=distance_metric,
        index_type=index_type
    )
