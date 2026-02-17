# Middleware Layer - 中间件层
#
# 提供 RAG 检索、文档处理等中间件服务

from .rag import (
    RAGRetriever,
    RetrievalResult,
    RetrievalContext,
    RetrievalStrategy,
    DocumentChunker
)

from .milvus_rag import (
    MilvusRAGRetriever,
    MilvusRAGConfig,
    MilvusRAGStatus,
    create_milvus_retriever,
    create_hybrid_retriever,
    get_rag_retriever_factory
)

__all__ = [
    # 内存 RAG
    'RAGRetriever',
    'RetrievalResult',
    'RetrievalContext',
    'RetrievalStrategy',
    'DocumentChunker',
    # Milvus RAG
    'MilvusRAGRetriever',
    'MilvusRAGConfig',
    'MilvusRAGStatus',
    'create_milvus_retriever',
    'create_hybrid_retriever',
    'get_rag_retriever_factory'
]
