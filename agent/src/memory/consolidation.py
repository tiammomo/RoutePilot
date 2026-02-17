"""
记忆整合器 (Memory Consolidator)

定期合并相似记忆，提取共性，减少存储空间同时保留关键信息。
支持自动化的记忆巩固和遗忘机制。

功能特点:
- 相似记忆聚类
- 记忆摘要合并
- 冗余消除
- 自动 Consolidation 调度
- 遗忘策略

使用示例:
    consolidator = MemoryConsolidator(llm_client)
    await consolidator.consolidate(memories)
    await consolidator.run_scheduled_consolidation()
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型"""
    CONVERSATION = "conversation"     # 对话记忆
    PREFERENCE = "preference"         # 偏好记忆
    FACT = "fact"                     # 事实记忆
    EXPERIENCE = "experience"         # 经验记忆


@dataclass
class MemoryCluster:
    """记忆聚类"""
    cluster_id: str
    memories: List[Dict[str, Any]] = field(default_factory=list)
    topic: str = ""
    merged_summary: str = ""
    importance_score: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_consolidated: str = field(default_factory=lambda: datetime.now().isoformat())
    consolidation_count: int = 0
    source_sessions: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "memories": self.memories,
            "topic": self.topic,
            "merged_summary": self.merged_summary,
            "importance_score": self.importance_score,
            "created_at": self.created_at,
            "last_consolidated": self.last_consolidated,
            "consolidation_count": self.consolidation_count,
            "source_sessions": list(self.source_sessions)
        }


@dataclass
class ConsolidationResult:
    """整合结果"""
    clusters_created: int = 0
    clusters_merged: int = 0
    memories_consolidated: int = 0
    memories_forgotten: int = 0
    tokens_saved: int = 0
    details: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MemoryConsolidator:
    """
    记忆整合器

    功能：
    1. 相似记忆聚类
    2. 生成合并摘要
    3. 消除冗余记忆
    4. 调度自动整合
    5. 遗忘低重要性记忆
    """

    # 聚类关键词
    TOPIC_KEYWORDS = {
        "旅行规划": ["计划", "行程", "路线", "安排", "攻略"],
        "预算": ["预算", "花费", "费用", "钱", "价格"],
        "目的地": ["城市", "景点", "地方", "去", "玩"],
        "交通": ["交通", "飞机", "火车", "高铁", "自驾"],
        "住宿": ["住宿", "酒店", "民宿", "宾馆"],
        "美食": ["美食", "好吃", "餐厅", "小吃", "食物"],
        "天气": ["天气", "季节", "温度", "气候"],
        "同伴": ["同伴", "家人", "朋友", "情侣", "孩子"]
    }

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        similarity_threshold: float = 0.7,
        min_cluster_size: int = 2,
        max_clusters: int = 100,
        consolidation_interval_hours: int = 24
    ):
        """
        初始化记忆整合器

        Args:
            llm_client: 可选的 LLM 客户端
            similarity_threshold: 相似度阈值
            min_cluster_size: 最小聚类大小
            max_clusters: 最大聚类数量
            consolidation_interval_hours: 自动整合间隔（小时）
        """
        self.llm_client = llm_client
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size
        self.max_clusters = max_clusters
        self.consolidation_interval = timedelta(hours=consolidation_interval_hours)

        # 聚类存储
        self._clusters: Dict[str, MemoryCluster] = {}

        # 上次整合时间
        self._last_consolidation = datetime.now()

        # 统计
        self._stats = {
            "total_consolidations": 0,
            "total_clusters_merged": 0,
            "total_memories_consolidated": 0
        }

    async def consolidate(
        self,
        memories: List[Dict[str, Any]]
    ) -> ConsolidationResult:
        """
        整合记忆列表

        Args:
            memories: 记忆列表

        Returns:
            ConsolidationResult: 整合结果
        """
        result = ConsolidationResult()

        if not memories:
            return result

        # 1. 按主题聚类
        topic_clusters = await self._cluster_by_topic(memories)

        # 2. 主题内相似度聚类
        similarity_clusters = await self._cluster_by_similarity(topic_clusters)

        # 3. 生成合并摘要
        for cluster in similarity_clusters:
            await self._generate_cluster_summary(cluster)

            # 计算重要性分数
            cluster.importance_score = self._calculate_cluster_importance(cluster)

            # 保存聚类
            cluster_id = cluster.cluster_id or f"cluster_{len(self._clusters)}"
            cluster.cluster_id = cluster_id

            self._clusters[cluster_id] = cluster
            result.clusters_created += 1
            result.memories_consolidated += len(cluster.memories)

        # 4. 限制聚类数量
        if len(self._clusters) > self.max_clusters:
            removed = await self._prune_clusters(
                len(self._clusters) - self.max_clusters
            )
            result.memories_forgotten = removed

        # 5. 更新统计
        self._stats["total_consolidations"] += 1
        self._stats["total_memories_consolidated"] += result.memories_consolidated

        logger.info(f"记忆整合完成: {result.memories_consolidated} 条记忆整合为 {result.clusters_created} 个聚类")

        return result

    async def _cluster_by_topic(
        self,
        memories: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """按主题聚类"""
        topic_buckets: Dict[str, List[Dict[str, Any]]] = {}

        for memory in memories:
            content = memory.get('content', '') or memory.get('summary', '')
            topic = self._detect_topic(content)

            if topic not in topic_buckets:
                topic_buckets[topic] = []

            topic_buckets[topic].append(memory)

        return topic_buckets

    def _detect_topic(self, content: str) -> str:
        """检测内容主题"""
        content_lower = content.lower()

        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in content_lower:
                    return topic

        return "其他"

    async def _cluster_by_similarity(
        self,
        topic_buckets: Dict[str, List[Dict[str, Any]]]
    ) -> List[MemoryCluster]:
        """在每个主题内按相似度聚类"""
        clusters = []

        for topic, memories in topic_buckets.items():
            if len(memories) < self.min_cluster_size:
                # 单个记忆也创建聚类
                for mem in memories:
                    cluster = MemoryCluster(
                        cluster_id=f"single_{mem.get('session_id', 'unknown')}",
                        memories=[mem],
                        topic=topic,
                        source_sessions={mem.get('session_id', '')}
                    )
                    clusters.append(cluster)
                continue

            # 相似度聚类
            used = set()
            for i, mem1 in enumerate(memories):
                if i in used:
                    continue

                cluster_memories = [mem1]
                used.add(i)

                for j, mem2 in enumerate(memories):
                    if j in used:
                        continue

                    # 计算相似度
                    similarity = self._calculate_similarity(mem1, mem2)
                    if similarity >= self.similarity_threshold:
                        cluster_memories.append(mem2)
                        used.add(j)

                if cluster_memories:
                    import uuid
                    cluster = MemoryCluster(
                        cluster_id=f"cluster_{uuid.uuid4().hex[:8]}",
                        memories=cluster_memories,
                        topic=topic,
                        source_sessions={
                            m.get('session_id', '') for m in cluster_memories
                            if m.get('session_id')
                        }
                    )
                    clusters.append(cluster)

        return clusters

    def _calculate_similarity(
        self,
        mem1: Dict[str, Any],
        mem2: Dict[str, Any]
    ) -> float:
        """计算两个记忆的相似度"""
        # 文本相似度
        content1 = mem1.get('content', '') or mem1.get('summary', '')
        content2 = mem2.get('content', '') or mem2.get('summary', '')

        # 关键词重叠
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        jaccard = len(intersection) / len(union) if union else 0

        # 会话 ID 相同
        same_session = 1.0 if mem1.get('session_id') == mem2.get('session_id') else 0.0

        # 综合相似度
        return jaccard * 0.7 + same_session * 0.3

    async def _generate_cluster_summary(self, cluster: MemoryCluster) -> None:
        """为聚类生成合并摘要"""
        if len(cluster.memories) == 1:
            # 单个记忆直接使用原摘要
            cluster.merged_summary = cluster.memories[0].get('summary', '')
            return

        # 收集所有内容
        contents = []
        for mem in cluster.memories:
            content = mem.get('content', '') or mem.get('summary', '')
            if content:
                contents.append(content[:500])  # 限制长度

        if not contents:
            cluster.merged_summary = ""
            return

        if self.llm_client:
            # 使用 LLM 生成摘要
            prompt = f"""以下是关于"{cluster.topic}"主题的多个记忆片段，请合并为一个简洁摘要：

{'='*50}
{'='.join(contents)}
{'='*50}

合并摘要（100字以内）："""

            try:
                result = await self.llm_client.chat([
                    {"role": "system", "content": "你是记忆整合专家"},
                    {"role": "user", "content": prompt}
                ])

                if result.get('success'):
                    cluster.merged_summary = result.get('content', '').strip()
                else:
                    cluster.merged_summary = self._fallback_summary(contents)
            except Exception as e:
                logger.warning(f"生成聚类摘要失败: {e}")
                cluster.merged_summary = self._fallback_summary(contents)
        else:
            # 使用规则摘要
            cluster.merged_summary = self._fallback_summary(contents)

        cluster.last_consolidated = datetime.now().isoformat()
        cluster.consolidation_count += 1

    def _fallback_summary(self, contents: List[str]) -> str:
        """规则-based 摘要"""
        # 合并所有唯一内容
        unique_contents = list(set(contents))
        combined = " | ".join(unique_contents[:3])  # 最多3条

        # 截断
        if len(combined) > 200:
            combined = combined[:200] + "..."

        return combined

    def _calculate_cluster_importance(self, cluster: MemoryCluster) -> float:
        """计算聚类的重要性分数"""
        if not cluster.memories:
            return 0.0

        # 平均重要性
        importance_scores = [
            m.get('importance', 0.5) for m in cluster.memories
        ]
        avg_importance = sum(importance_scores) / len(importance_scores)

        # 调整因子
        size_factor = min(len(cluster.memories) / 10, 1.0)  # 聚类越大越重要
        recency_factor = 1.0  # 可以添加时间权重

        return min(avg_importance * 0.6 + size_factor * 0.4, 1.0)

    async def _prune_clusters(self, count: int) -> int:
        """删除最不重要的聚类"""
        # 按重要性排序
        sorted_clusters = sorted(
            self._clusters.items(),
            key=lambda x: x[1].importance_score
        )

        removed = 0
        for cluster_id, cluster in sorted_clusters:
            if removed >= count:
                break

            # 只删除低重要性的
            if cluster.importance_score < 0.3:
                del self._clusters[cluster_id]
                removed += 1

        return removed

    async def run_scheduled_consolidation(self) -> ConsolidationResult:
        """
        运行计划整合

        Returns:
            ConsolidationResult: 整合结果
        """
        now = datetime.now()

        # 检查是否到达整合时间
        if now - self._last_consolidation < self.consolidation_interval:
            return ConsolidationResult()

        # 获取所有需要整合的聚类
        old_clusters = [
            cluster for cluster in self._clusters.values()
            if now - datetime.fromisoformat(cluster.last_consolidated) > self.consolidation_interval
        ]

        if not old_clusters:
            self._last_consolidation = now
            return ConsolidationResult()

        # 收集旧聚类的记忆
        memories_to_consolidate = []
        for cluster in old_clusters:
            memories_to_consolidate.extend(cluster.memories)

        # 整合
        result = await self.consolidate(memories_to_consolidate)

        # 删除已整合的旧聚类
        for cluster in old_clusters:
            if cluster.cluster_id in self._clusters:
                del self._clusters[cluster.cluster_id]

        self._last_consolidation = now
        return result

    def get_cluster(self, cluster_id: str) -> Optional[MemoryCluster]:
        """
        获取聚类

        Args:
            cluster_id: 聚类 ID

        Returns:
            Optional[MemoryCluster]: 聚类
        """
        return self._clusters.get(cluster_id)

    def get_all_clusters(self) -> List[MemoryCluster]:
        """
        获取所有聚类

        Returns:
            List[MemoryCluster]: 聚类列表
        """
        return list(self._clusters.values())

    def get_clusters_by_topic(self, topic: str) -> List[MemoryCluster]:
        """
        获取指定主题的聚类

        Args:
            topic: 主题

        Returns:
            List[MemoryCluster]: 聚类列表
        """
        return [
            c for c in self._clusters.values()
            if c.topic == topic
        ]

    def get_forgotten_memories(
        self,
        max_age_days: int = 30,
        min_importance: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        获取可遗忘的记忆

        Args:
            max_age_days: 最大年龄（天）
            min_importance: 最低重要性

        Returns:
            List[Dict]: 可遗忘的记忆列表
        """
        forgotten = []
        cutoff = datetime.now() - timedelta(days=max_age_days)

        for cluster in self._clusters.values():
            # 检查是否应该遗忘
            cluster_time = datetime.fromisoformat(cluster.last_consolidated)
            if cluster_time > cutoff:
                continue

            if cluster.importance_score < min_importance:
                for mem in cluster.memories:
                    mem['forget_reason'] = 'low_importance'
                    mem['forget_time'] = datetime.now().isoformat()
                    forgotten.append(mem)

        return forgotten

    async def forget_memories(
        self,
        memory_ids: List[str]
    ) -> int:
        """
        遗忘指定记忆

        Args:
            memory_ids: 记忆 ID 列表

        Returns:
            int: 遗忘的记忆数量
        """
        forgotten = 0

        for cluster_id in list(self._clusters.keys()):
            cluster = self._clusters[cluster_id]

            # 过滤掉要遗忘的记忆
            original_count = len(cluster.memories)
            cluster.memories = [
                m for m in cluster.memories
                if m.get('id') not in memory_ids
            ]

            forgotten += original_count - len(cluster.memories)

            # 如果聚类为空，删除聚类
            if not cluster.memories:
                del self._clusters[cluster_id]

        return forgotten

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        # 按主题统计
        topic_counts = {}
        for cluster in self._clusters.values():
            topic = cluster.topic
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        return {
            "total_clusters": len(self._clusters),
            "total_memories_in_clusters": sum(
                len(c.memories) for c in self._clusters.values()
            ),
            "topic_distribution": topic_counts,
            "avg_cluster_size": (
                sum(len(c.memories) for c in self._clusters.values()) /
                max(len(self._clusters), 1)
            ),
            "total_consolidations": self._stats["total_consolidations"],
            "last_consolidation": self._last_consolidation.isoformat()
        }

    def serialize(self) -> Dict[str, Any]:
        """序列化整合器状态"""
        return {
            "clusters": {
                cid: cluster.to_dict()
                for cid, cluster in self._clusters.items()
            },
            "stats": self._stats,
            "last_consolidation": self._last_consolidation.isoformat()
        }

    def deserialize(self, data: Dict[str, Any]) -> None:
        """从序列化数据恢复"""
        for cid, cluster_data in data.get("clusters", {}).items():
            cluster = MemoryCluster(
                cluster_id=cluster_data.get('cluster_id', cid),
                memories=cluster_data.get('memories', []),
                topic=cluster_data.get('topic', ''),
                merged_summary=cluster_data.get('merged_summary', ''),
                importance_score=cluster_data.get('importance_score', 0.5),
                created_at=cluster_data.get('created_at', datetime.now().isoformat()),
                last_consolidated=cluster_data.get('last_consolidated', datetime.now().isoformat()),
                consolidation_count=cluster_data.get('consolidation_count', 0),
                source_sessions=set(cluster_data.get('source_sessions', []))
            )
            self._clusters[cid] = cluster

        self._stats = data.get("stats", self._stats)
        last_consol = data.get("last_consolidation")
        if last_consol:
            self._last_consolidation = datetime.fromisoformat(last_consol)
