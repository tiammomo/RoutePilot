"""
================================================================================
RAG 检索模块 (RAG Retrieval)

提供检索增强生成（RAG）功能，支持向量检索、文档处理和检索排序。

功能特点:
- 向量相似度检索
- 文档解析和分块
- 多路检索融合
- 检索结果排序
- 上下文压缩

使用示例:
```python
from middleware.rag import RAGRetriever

retriever = RAGRetriever()
results = await retriever.retrieve("北京旅游推荐", top_k=5)
```

================================================================================
"""

import re
import logging
import json
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class RetrievalStrategy(Enum):
    """检索策略"""
    SIMPLE = "simple"         # 简单检索
    HYBRID = "hybrid"         # 混合检索
    SEMANTIC = "semantic"     # 语义检索
    KEYWORD = "keyword"       # 关键词检索


@dataclass
class RetrievalResult:
    """检索结果"""
    id: str
    content: str
    score: float
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    highlights: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
            "highlights": self.highlights
        }


@dataclass
class RetrievalContext:
    """检索上下文"""
    query: str
    results: List[RetrievalResult]
    total_score: float
    retrieval_time_ms: float
    strategy: RetrievalStrategy

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "result_count": len(self.results),
            "total_score": self.total_score,
            "retrieval_time_ms": self.retrieval_time_ms,
            "strategy": self.strategy.value,
            "results": [r.to_dict() for r in self.results]
        }


class DocumentChunker:
    """
    文档分块器

    将长文档分割成适合检索的小块。

    策略:
    - 固定大小分块
    - 语义分块（按段落/句子）
    - 重叠分块
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: List[str] = None
    ):
        """
        初始化分块器

        Args:
            chunk_size: 块大小（字符数）
            chunk_overlap: 重叠大小
            separators: 分隔符列表
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ['\n\n', '\n', '。', '！', '？', '；', '.', '!', '?', ';']

    def chunk(self, text: str, source: str = "") -> List[Dict[str, Any]]:
        """
        分块处理

        Args:
            text: 输入文本
            source: 来源标识

        Returns:
            List[Dict]: 块列表
        """
        if not text:
            return []

        # 清理文本
        text = self._clean_text(text)

        # 尝试按段落分块
        paragraphs = self._split_by_paragraphs(text)

        if len(paragraphs) > 1 and sum(len(p) for p in paragraphs) > self.chunk_size:
            # 多段落，使用段落分块
            return self._chunk_by_paragraphs(paragraphs, source)

        # 单段落，使用句子分块
        sentences = self._split_by_sentences(text)
        return self._chunk_by_sentences(sentences, source)

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除特殊字符
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        return text.strip()

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割"""
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子分割"""
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in '。！？\n':
                if current.strip():
                    sentences.append(current.strip())
                current = ""

        if current.strip():
            sentences.append(current.strip())

        return sentences if sentences else [text]

    def _chunk_by_paragraphs(
        self,
        paragraphs: List[str],
        source: str
    ) -> List[Dict[str, Any]]:
        """按段落分块"""
        chunks = []
        current_chunk = ""
        current_size = 0

        for para in paragraphs:
            para_size = len(para)

            if current_size + para_size > self.chunk_size and current_chunk:
                # 保存当前块
                chunk_id = self._generate_chunk_id(current_chunk, source)
                chunks.append({
                    "id": chunk_id,
                    "content": current_chunk.strip(),
                    "source": source,
                    "chunk_index": len(chunks),
                    "metadata": {
                        "char_count": len(current_chunk)
                    }
                })

                # 重叠处理
                if self.chunk_overlap > 0:
                    words = current_chunk.split()
                    overlap_words = ' '.join(words[-self.chunk_overlap:]) if len(words) > self.chunk_overlap else current_chunk
                    current_chunk = overlap_words + " " + para
                else:
                    current_chunk = para
                current_size = len(current_chunk)
            else:
                current_chunk += ("\n\n" if current_chunk else "") + para
                current_size += para_size + 2

        # 保存最后一个块
        if current_chunk.strip():
            chunk_id = self._generate_chunk_id(current_chunk, source)
            chunks.append({
                "id": chunk_id,
                "content": current_chunk.strip(),
                "source": source,
                "chunk_index": len(chunks),
                "metadata": {
                    "char_count": len(current_chunk)
                }
            })

        return chunks

    def _chunk_by_sentences(
        self,
        sentences: List[str],
        source: str
    ) -> List[Dict[str, Any]]:
        """按句子分块"""
        chunks = []
        current_chunk = ""
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence)

            if current_size + sentence_size > self.chunk_size and current_chunk:
                # 保存当前块
                chunk_id = self._generate_chunk_id(current_chunk, source)
                chunks.append({
                    "id": chunk_id,
                    "content": current_chunk.strip(),
                    "source": source,
                    "chunk_index": len(chunks),
                    "metadata": {
                        "char_count": len(current_chunk),
                        "sentence_count": current_chunk.count('。') + current_chunk.count('!') + current_chunk.count('?')
                    }
                })

                # 重叠处理
                if self.chunk_overlap > 0:
                    overlap_chars = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else current_chunk
                    current_chunk = overlap_chars + sentence
                else:
                    current_chunk = sentence
                current_size = len(current_chunk)
            else:
                current_chunk += (" " if current_chunk else "") + sentence
                current_size += sentence_size + 1

        # 保存最后一个块
        if current_chunk.strip():
            chunk_id = self._generate_chunk_id(current_chunk, source)
            chunks.append({
                "id": chunk_id,
                "content": current_chunk.strip(),
                "source": source,
                "chunk_index": len(chunks),
                "metadata": {
                    "char_count": len(current_chunk)
                }
            })

        return chunks

    def _generate_chunk_id(self, content: str, source: str) -> str:
        """生成块ID"""
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{source}_{content_hash}"


class RAGRetriever:
    """
    RAG 检索器

    提供向量检索和混合检索能力。
    """

    def __init__(
        self,
        chunker: Optional[DocumentChunker] = None,
        enable_vector_search: bool = False,
        embedding_model: Optional[Any] = None
    ):
        """
        初始化检索器

        Args:
            chunker: 文档分块器
            enable_vector_search: 是否启用向量检索
            embedding_model: 嵌入模型
        """
        self.chunker = chunker or DocumentChunker()
        self.enable_vector_search = enable_vector_search
        self.embedding_model = embedding_model

        # 文档存储
        self._documents: Dict[str, List[Dict[str, Any]]] = {}

        # 向量索引
        self._vector_index: Dict[str, List[float]] = {}

        # 关键词索引
        self._keyword_index: Dict[str, List[str]] = {}

        logger.info(f"[RAGRetriever] 初始化完成，vector_search={enable_vector_search}")

    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        source: str = "default"
    ) -> int:
        """
        添加文档

        Args:
            documents: 文档列表 [{"id": "...", "content": "..."}]
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
                # 保留原有元数据
                for chunk in doc_chunks:
                    chunk['metadata'].update({
                        k: v for k, v in doc.items()
                        if k not in ['content', 'id']
                    })
            chunks.extend(doc_chunks)

        # 存储文档
        if source not in self._documents:
            self._documents[source] = []
        self._documents[source].extend(chunks)

        # 更新索引
        self._update_keyword_index(chunks)

        # 如果启用向量检索，更新向量索引
        if self.enable_vector_search and self.embedding_model:
            for chunk in chunks:
                await self._index_chunk(chunk)

        logger.info(f"[RAGRetriever] 添加文档: {len(chunks)} 块")
        return len(chunks)

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
        import time
        start_time = time.time()

        # 获取候选文档
        if source_filter:
            candidates = []
            for source in source_filter:
                if source in self._documents:
                    candidates.extend(self._documents[source])
        else:
            candidates = []
            for source, docs in self._documents.items():
                candidates.extend(docs)

        if not candidates:
            return RetrievalContext(
                query=query,
                results=[],
                total_score=0.0,
                retrieval_time_ms=0.0,
                strategy=strategy
            )

        # 根据策略检索
        if strategy == RetrievalStrategy.KEYWORD:
            results = self._keyword_search(query, candidates, top_k)
        elif strategy == RetrievalStrategy.SEMANTIC and self.enable_vector_search:
            results = await self._semantic_search(query, candidates, top_k)
        else:
            # 混合检索
            results = await self._hybrid_search(query, candidates, top_k)

        # 计算总分数
        total_score = sum(r.score for r in results) if results else 0.0

        retrieval_time = (time.time() - start_time) * 1000

        return RetrievalContext(
            query=query,
            results=results[:top_k],
            total_score=total_score,
            retrieval_time_ms=retrieval_time,
            strategy=strategy
        )

    def _keyword_search(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int
    ) -> List[RetrievalResult]:
        """关键词检索"""
        query_keywords = self._extract_keywords(query)
        scored = []

        for doc in candidates:
            content = doc.get('content', '')
            doc_keywords = self._extract_keywords(content)

            # 计算关键词重叠
            overlap = len(set(query_keywords) & set(doc_keywords))
            if overlap > 0:
                score = overlap / max(len(query_keywords), 1)
                highlights = self._extract_highlights(content, query_keywords)

                result = RetrievalResult(
                    id=doc.get('id', ''),
                    content=content,
                    score=min(score * 2, 1.0),  # 增强分数
                    source=doc.get('source', ''),
                    metadata=doc.get('metadata', {}),
                    highlights=highlights
                )
                scored.append(result)

        # 按分数排序
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def _semantic_search(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int
    ) -> List[RetrievalResult]:
        """语义检索（向量检索）"""
        if not self.embedding_model:
            return self._keyword_search(query, candidates, top_k)

        # 生成查询向量
        query_embedding = await self.embedding_model.encode(query)

        scored = []
        for doc in candidates:
            chunk_id = doc.get('id', '')

            # 获取文档向量
            doc_embedding = self._vector_index.get(chunk_id)
            if doc_embedding is None:
                # 动态生成
                content = doc.get('content', '')
                doc_embedding = await self.embedding_model.encode(content)
                self._vector_index[chunk_id] = doc_embedding

            # 计算相似度
            score = self._cosine_similarity(query_embedding, doc_embedding)

            result = RetrievalResult(
                id=chunk_id,
                content=doc.get('content', ''),
                score=score,
                source=doc.get('source', ''),
                metadata=doc.get('metadata', {})
            )
            scored.append(result)

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def _hybrid_search(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int
    ) -> List[RetrievalResult]:
        """混合检索"""
        # 获取关键词和语义结果
        keyword_results = self._keyword_search(query, candidates, top_k * 2)
        semantic_results = await self._semantic_search(query, candidates, top_k * 2)

        # 合并结果
        merged: Dict[str, RetrievalResult] = {}

        for result in keyword_results:
            if result.id not in merged:
                merged[result.id] = result
            else:
                merged[result.id].score = max(merged[result.id].score, result.score)

        for result in semantic_results:
            if result.id not in merged:
                merged[result.id] = result
            else:
                # 语义分数权重更高
                merged[result.id].score = max(
                    merged[result.id].score * 0.5 + result.score * 1.5,
                    result.score
                )

        # 按分数排序
        results = sorted(merged.values(), key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _update_keyword_index(self, chunks: List[Dict]) -> None:
        """更新关键词索引"""
        for chunk in chunks:
            content = chunk.get('content', '')
            keywords = self._extract_keywords(content)
            chunk_id = chunk.get('id', '')

            for keyword in keywords:
                if keyword not in self._keyword_index:
                    self._keyword_index[keyword] = []
                if chunk_id not in self._keyword_index[keyword]:
                    self._keyword_index[keyword].append(chunk_id)

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        words = set()

        # 英文词（长度>=2）
        english_words = re.findall(r'[a-zA-Z]{2,}', text.lower())
        words.update(english_words)

        # 中文词 - 使用 jieba 如果可用，否则使用字符 n-gram
        try:
            import jieba
            chinese_words = list(jieba.cut(text))
            # 过滤：长度>=2 且不是纯停用词
            stopwords = {'的', '是', '在', '了', '和', '与', '或', '这', '那', '有', '没有', '也', '就', '都', '而', '及', '。', '，', '！', '？', '、', '"', '"', ''', ''', '：', ';', '；', '-', '—', '...', '……', ' ', '\n', '\t'}
            for w in chinese_words:
                if len(w) >= 2 and w not in stopwords and not re.match(r'^[\s\d]+$', w):
                    words.add(w)
        except ImportError:
            # 回退：使用字符 n-gram（2-4字词）
            chinese_chars = re.findall(r'[\u4e00-\u9fa5]', text)
            for i in range(len(chinese_chars)):
                for n in [2, 3, 4]:  # 2-4字词
                    if i + n <= len(chinese_chars):
                        word = ''.join(chinese_chars[i:i+n])
                        if word not in {'的', '是', '在', '了', '和', '与', '或'}:
                            words.add(word)

        # 过滤停用词
        stopwords = {'的', '是', '在', '了', '和', '与', '或', '这', '那', '有', '没有', '也', '就', '都', '而', '及'}
        result = [w for w in words if w not in stopwords]

        return result

    def _extract_highlights(self, content: str, keywords: List[str]) -> List[str]:
        """提取高亮片段"""
        highlights = []
        for keyword in keywords:
            if keyword.lower() in content.lower():
                idx = content.lower().find(keyword.lower())
                start = max(0, idx - 20)
                end = min(len(content), idx + len(keyword) + 20)
                highlights.append(content[start:end])
        return highlights[:3]

    async def _index_chunk(self, chunk: Dict) -> None:
        """索引单个块"""
        if not self.embedding_model:
            return

        content = chunk.get('content', '')
        chunk_id = chunk.get('id', '')

        embedding = await self.embedding_model.encode(content)
        self._vector_index[chunk_id] = embedding

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 * norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_chunks = sum(len(docs) for docs in self._documents.values())
        return {
            "document_sources": list(self._documents.keys()),
            "total_chunks": total_chunks,
            "vector_index_size": len(self._vector_index),
            "keyword_index_size": len(self._keyword_index),
            "vector_search_enabled": self.enable_vector_search
        }

    def clear(self) -> None:
        """清空索引"""
        self._documents.clear()
        self._vector_index.clear()
        self._keyword_index.clear()
