# Middleware Layer - 中间件层
#
# 提供 RAG 检索、文档处理等中间件服务
# 注意: 已移除 Milvus 依赖

from .rag import (
    RAGRetriever,
    RetrievalResult,
    RetrievalContext,
    RetrievalStrategy,
    DocumentChunker
)

__all__ = [
    # 内存 RAG
    'RAGRetriever',
    'RetrievalResult',
    'RetrievalContext',
    'RetrievalStrategy',
    'DocumentChunker'
]
