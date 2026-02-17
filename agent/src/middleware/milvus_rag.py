"""
================================================================================
Milvus RAG 检索模块 (Milvus RAG Retrieval)

提供基于 Milvus 向量数据库的 RAG 检索功能，支持：
- Milvus 向量存储和检索
- 自动降级到内存模式
- 混合检索（向量 + 关键词）

使用示例:
```python
from middleware.milvus_rag import create_milvus_retriever

# 创建检索器
retriever = await create_milvus_retriever(
    collection_name="travel_documents",
    embedding_model=embedding_model
)

# 检索文档
results = await retriever.retrieve("北京旅游推荐", top_k=5)
```

================================================================================
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .rag import (
    RAGRetriever,
    DocumentChunker,
    RetrievalResult,
    RetrievalContext,
    RetrievalStrategy,
)

logger = logging.getLogger(__name__)


class MilvusRAGStatus(Enum):
    """Milvus RAG 状态"""
    DISABLED = "disabled"          # 已禁用
    CONNECTING = "connecting"       # 连接中
    READY = "ready"                 # 就绪
    FALLBACK = "fallback"           # 回退到内存模式
    ERROR = "error"                 # 错误


@dataclass
class MilvusRAGConfig:
    """Milvus RAG 配置"""
    # 集合配置
    collection_name: str = "travel_documents"
    dim: int = 1024

    # Milvus 连接配置
    host: str = "localhost"
    port: int = 19530
    db_name: str = "default"

    # 功能开关
    enable_vector_search: bool = True
    enable_hybrid_search: bool = True
    fallback_to_memory: bool = True

    # 索引配置
    metric_type: str = "COSINE"
    index_type: str = "FLAT"

    def get_address(self) -> str:
        """获取 Milvus 地址"""
        return f"{self.host}:{self.port}"


class MilvusRAGRetriever:
    """
    Milvus RAG 检索器

    基于 Milvus 向量数据库的 RAG 检索器，支持自动降级到内存模式。
    """

    def __init__(
        self,
        config: Optional[MilvusRAGConfig] = None,
        embedding_model: Optional[Any] = None,
        chunker: Optional[DocumentChunker] = None
    ):
        """
        初始化 Milvus RAG 检索器

        Args:
            config: Milvus RAG 配置
            embedding_model: 嵌入模型
            chunker: 文档分块器
        """
        self.config = config or MilvusRAGConfig()
        self.embedding_model = embedding_model
        self.chunker = chunker or DocumentChunker()

        # Milvus 向量存储
        self._milvus_store = None

        # 内存回退模式
        self._memory_retriever: Optional[RAGRetriever] = None

        # 状态
        self._status = MilvusRAGStatus.DISABLED
        self._error_message: Optional[str] = None

        logger.info(f"[MilvusRAGRetriever] 初始化完成，vector_search={self.config.enable_vector_search}")

    @property
    def status(self) -> MilvusRAGStatus:
        """获取当前状态"""
        return self._status

    @property
    def is_milvus_ready(self) -> bool:
        """Milvus 是否就绪"""
        return self._status == MilvusRAGStatus.READY

    @property
    def is_using_memory(self) -> bool:
        """是否使用内存模式"""
        return self._status == MilvusRAGStatus.FALLBACK or self._status == MilvusRAGStatus.DISABLED

    async def initialize(self) -> bool:
        """
        初始化 Milvus 连接

        Returns:
            bool: 是否成功
        """
        if not self.config.enable_vector_search:
            self._status = MilvusRAGStatus.DISABLED
            self._setup_memory_retriever()
            return True

        self._status = MilvusRAGStatus.CONNECTING

        try:
            from infrastructure.milvus_vector import (
                MilvusVectorStore,
                MilvusConfig,
                DistanceMetric,
                IndexType
            )
            from pymilvus import connections

            # 创建 Milvus 配置
            milvus_config = MilvusConfig(
                host=self.config.host,
                port=self.config.port,
                db_name=self.config.db_name
            )

            # 创建向量存储
            self._milvus_store = MilvusVectorStore(
                collection_name=self.config.collection_name,
                dim=self.config.dim,
                config=milvus_config,
                distance_metric=DistanceMetric(self.config.metric_type),
                index_type=IndexType(self.config.index_type)
            )

            # 连接 Milvus
            await self._milvus_store.connect()

            # 创建集合
            await self._milvus_store.create_collection()

            self._status = MilvusRAGStatus.READY
            logger.info(f"[MilvusRAGRetriever] Milvus 连接成功: {self.config.get_address()}")
            return True

        except ImportError:
            self._error_message = "pymilvus 未安装"
            logger.warning(f"[MilvusRAGRetriever] pymilvus 未安装，降级到内存模式")
            return self._fallback_to_memory()

        except Exception as e:
            self._error_message = str(e)
            logger.error(f"[MilvusRAGRetriever] Milvus 连接失败: {e}")
            return self._fallback_to_memory()

    def _setup_memory_retriever(self) -> None:
        """设置内存回退检索器"""
        self._memory_retriever = RAGRetriever(
            chunker=self.chunker,
            enable_vector_search=False,
            embedding_model=None
        )
        logger.info("[MilvusRAGRetriever] 使用内存回退模式")

    def _fallback_to_memory(self) -> bool:
        """降级到内存模式"""
        if self.config.fallback_to_memory:
            self._status = MilvusRAGStatus.FALLBACK
            self._setup_memory_retriever()
            logger.info("[MilvusRAGRetriever] 已降级到内存模式")
            return True
        else:
            self._status = MilvusRAGStatus.ERROR
            return False

    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        source: str = "default"
    ) -> int:
        """
        添加文档

        Args:
            documents: 文档列表
            source: 来源标识

        Returns:
            int: 添加的块数
        """
        # 分块处理
        chunks = []
        for doc in documents:
            if isinstance(doc, str):
                doc_chunks = self.chunker.chunk(doc, source)
            else:
                content = doc.get('content', '')
                doc_chunks = self.chunker.chunk(content, source)
                for chunk in doc_chunks:
                    chunk['metadata'].update({
                        k: v for k, v in doc.items()
                        if k not in ['content', 'id']
                    })
            chunks.extend(doc_chunks)

        # 根据模式存储
        if self.is_milvus_ready and self._milvus_store:
            return await self._add_to_milvus(chunks, source)
        else:
            return await self._memory_add_documents(chunks, source)

    async def _add_to_milvus(
        self,
        chunks: List[Dict[str, Any]],
        source: str
    ) -> int:
        """添加到 Milvus"""
        if not self.embedding_model:
            logger.warning("[MilvusRAGRetriever] 未配置嵌入模型，无法生成向量")
            return 0

        try:
            from infrastructure.milvus_vector import VectorProcessor

            # 提取文本
            texts = [chunk.get('content', '') for chunk in chunks]

            # 生成向量
            processor = VectorProcessor(self.embedding_model)
            vectors = await processor.embed_texts(texts)

            # 准备载荷
            payloads = []
            for chunk in chunks:
                payload = {
                    **chunk.get('metadata', {}),
                    "content": chunk.get('content', ''),
                    "source": source,
                    "chunk_id": chunk.get('id', ''),
                    "chunk_index": chunk.get('chunk_index', 0)
                }
                payloads.append(payload)

            # 插入向量
            ids = await self._milvus_store.insert(vectors, payloads)

            logger.info(f"[MilvusRAGRetriever] 添加文档到 Milvus: {len(ids)} 块")
            return len(ids)

        except Exception as e:
            logger.error(f"[MilvusRAGRetriever] 添加到 Milvus 失败: {e}")
            self._fallback_to_memory()
            return await self._memory_add_documents(chunks, source)

    async def _memory_add_documents(
        self,
        chunks: List[Dict[str, Any]],
        source: str
    ) -> int:
        """添加到内存存储"""
        if self._memory_retriever:
            return await self._memory_retriever.add_documents(chunks, source)
        return 0

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID,
        source_filter: Optional[List[str]] = None
    ) -> RetrievalContext:
        """
        检索文档

        Args:
            query: 查询文本
            top_k: 返回结果数
            strategy: 检索策略
            source_filter: 来源过滤

        Returns:
            RetrievalContext: 检索上下文
        """
        # 内存模式
        if self.is_using_memory and self._memory_retriever:
            return await self._memory_retriever.retrieve(
                query, top_k, strategy, source_filter
            )

        # Milvus 模式
        if self.is_milvus_ready:
            return await self._milvus_retrieve(query, top_k, source_filter)

        # 未初始化，回退到内存
        self._setup_memory_retriever()
        return await self._memory_retriever.retrieve(
            query, top_k, strategy, source_filter
        )

    async def _milvus_retrieve(
        self,
        query: str,
        top_k: int,
        source_filter: Optional[List[str]] = None
    ) -> RetrievalContext:
        """Milvus 检索"""
        import time
        start_time = time.time()

        if not self.embedding_model:
            # 回退到关键词检索
            return await self._keyword_only_retrieve(query, top_k)

        try:
            from infrastructure.milvus_vector import VectorProcessor

            # 生成查询向量
            processor = VectorProcessor(self.embedding_model)
            query_vector = await processor.embed_query(query)

            # 构建过滤表达式
            filter_expr = None
            if source_filter:
                filter_expr = f"source in {source_filter}"

            # 搜索
            results = await self._milvus_store.search(
                query_vector=query_vector,
                top_k=top_k * 2,  # 获取更多结果用于混合
                filter_expr=filter_expr,
                output_fields=["payload"]
            )

            # 转换结果
            retrieval_results = []
            for r in results:
                payload = r.payload or {}
                content = payload.get('content', '')

                retrieval_results.append(RetrievalResult(
                    id=payload.get('chunk_id', str(r.id)),
                    content=content,
                    score=r.score,
                    source=payload.get('source', ''),
                    metadata={k: v for k, v in payload.items()
                              if k not in ['content', 'source', 'chunk_id']}
                ))

            # 按分数排序
            retrieval_results.sort(key=lambda x: x.score, reverse=True)
            retrieval_results = retrieval_results[:top_k]

            retrieval_time = (time.time() - start_time) * 1000

            return RetrievalContext(
                query=query,
                results=retrieval_results,
                total_score=sum(r.score for r in retrieval_results),
                retrieval_time_ms=retrieval_time,
                strategy=RetrievalStrategy.SEMANTIC
            )

        except Exception as e:
            logger.error(f"[MilvusRAGRetriever] Milvus 检索失败: {e}")
            return await self._keyword_only_retrieve(query, top_k)

    async def _keyword_only_retrieve(
        self,
        query: str,
        top_k: int
    ) -> RetrievalContext:
        """关键词检索（回退）"""
        if self._memory_retriever:
            return await self._memory_retriever.retrieve(
                query, top_k, RetrievalStrategy.KEYWORD
            )

        # 完全回退到关键词检索
        return RetrievalContext(
            query=query,
            results=[],
            total_score=0.0,
            retrieval_time_ms=0.0,
            strategy=RetrievalStrategy.KEYWORD
        )

    async def delete_by_source(self, source: str) -> int:
        """按来源删除文档"""
        if self.is_milvus_ready and self._milvus_store:
            try:
                filter_expr = f"source == '{source}'"
                return await self._milvus_store.delete_by_filter(filter_expr)
            except Exception as e:
                logger.error(f"[MilvusRAGRetriever] 删除失败: {e}")

        return 0

    async def clear(self) -> None:
        """清空索引"""
        if self.is_milvus_ready and self._milvus_store:
            try:
                from pymilvus import utility
                utility.drop_collection(self.config.collection_name)
                await self._milvus_store.create_collection()
                logger.info(f"[MilvusRAGRetriever] 已清空集合: {self.config.collection_name}")
            except Exception as e:
                logger.error(f"[MilvusRAGRetriever] 清空失败: {e}")

        if self._memory_retriever:
            self._memory_retriever.clear()

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "status": self._status.value,
            "milvus_address": self.config.get_address(),
            "collection_name": self.config.collection_name,
            "fallback_enabled": self.config.fallback_to_memory
        }

        if self.is_milvus_ready and self._milvus_store:
            try:
                count = await self._milvus_store.get_count()
                stats["milvus_documents"] = count
            except Exception:
                pass

        if self._memory_retriever:
            memory_stats = self._memory_retriever.get_stats()
            stats.update({
                "memory_sources": memory_stats.get("document_sources", []),
                "memory_chunks": memory_stats.get("total_chunks", 0)
            })

        return stats

    async def close(self) -> None:
        """关闭连接"""
        if self._milvus_store:
            await self._milvus_store.close()
            self._milvus_store = None

        logger.info("[MilvusRAGRetriever] 连接已关闭")


# =============================================================================
# 工厂函数
# =============================================================================

async def create_milvus_retriever(
    config: Optional[Dict[str, Any]] = None,
    embedding_model: Optional[Any] = None,
    **kwargs
) -> MilvusRAGRetriever:
    """
    创建 Milvus RAG 检索器

    Args:
        config: 配置字典
        embedding_model: 嵌入模型
        **kwargs: 其他配置参数

    Returns:
        MilvusRAGRetriever: 检索器实例
    """
    # 构建配置
    rag_config = MilvusRAGConfig()

    if config:
        rag_config.collection_name = config.get('collection_name', rag_config.collection_name)
        rag_config.dim = config.get('dim', rag_config.dim)
        rag_config.host = config.get('host', rag_config.host)
        rag_config.port = config.get('port', rag_config.port)
        rag_config.db_name = config.get('db_name', rag_config.db_name)
        rag_config.enable_vector_search = config.get('enable_vector_search', rag_config.enable_vector_search)
        rag_config.enable_hybrid_search = config.get('enable_hybrid_search', rag_config.enable_hybrid_search)
        rag_config.fallback_to_memory = config.get('fallback_to_memory', rag_config.fallback_to_memory)
        rag_config.metric_type = config.get('metric_type', rag_config.metric_type)
        rag_config.index_type = config.get('index_type', rag_config.index_type)

    # 覆盖 kwargs
    for key, value in kwargs.items():
        if hasattr(rag_config, key):
            setattr(rag_config, key, value)

    # 创建检索器
    retriever = MilvusRAGRetriever(
        config=rag_config,
        embedding_model=embedding_model
    )

    # 初始化
    await retriever.initialize()

    return retriever


async def create_hybrid_retriever(
    embedding_model: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Tuple[MilvusRAGRetriever, RAGRetriever]:
    """
    创建混合检索器

    同时返回 Milvus 检索器和内存检索器，用于需要同时使用两种模式的场景。

    Returns:
        Tuple: (MilvusRAGRetriever, MemoryRAGRetriever)
    """
    # 创建 Milvus 检索器
    milvus_retriever = await create_milvus_retriever(
        config=config,
        embedding_model=embedding_model,
        **kwargs
    )

    # 创建纯内存检索器（用于关键词检索）
    memory_retriever = RAGRetriever(
        chunker=None,
        enable_vector_search=False,
        embedding_model=None
    )

    return milvus_retriever, memory_retriever


def get_rag_retriever_factory() -> Dict[str, str]:
    """
    获取 RAG 检索器工厂信息

    Returns:
        Dict: 可用的检索器类型
    """
    return {
        "memory": "middleware.rag.RAGRetriever - 纯内存检索器",
        "milvus": "middleware.milvus_rag.MilvusRAGRetriever - Milvus 向量检索器",
        "hybrid": "middleware.milvus_rag.create_hybrid_retriever - 混合检索器"
    }
