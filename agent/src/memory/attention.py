"""
注意力窗口 (Attention Window)

决定哪些记忆被 LLM 关注的核心组件。

核心思想：不是所有记忆都同等重要
- 位置编码: 越新的记忆越重要
- 重要性编码: 高分记忆优先
- 相关性编码: 与当前任务相关的记忆优先

使用示例:
    from memory.attention import AttentionWindow

    window = AttentionWindow(window_size=10)
    scores = window.compute_attention(messages, current_query)
    # 返回: [0.15, 0.08, 0.25, ...]
"""

import math
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class AttentionWindow:
    """
    注意力窗口 - 决定哪些记忆被 LLM 关注

    通过三维度加权计算注意力分数：
    1. 位置分数 (recency): 越新的消息权重越高
    2. 重要性分数 (importance): ImportanceScorer 输出的分数
    3. 相关性分数 (relevance): 与当前查询的关键词重叠度
    """

    def __init__(
        self,
        window_size: int = 10,
        recency_weight: float = 0.3,
        importance_weight: float = 0.4,
        relevance_weight: float = 0.3
    ):
        """
        初始化注意力窗口

        Args:
            window_size: 注意力窗口大小，控制返回的消息数量
            recency_weight: 位置权重
            importance_weight: 重要性权重
            relevance_weight: 相关性权重
        """
        self.window_size = window_size
        self.weights = {
            "recency": recency_weight,
            "importance": importance_weight,
            "relevance": relevance_weight
        }
        # 验证权重和为 1
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"Attention weights sum to {total}, normalizing to 1.0"
            )
            for key in self.weights:
                self.weights[key] /= total

    def compute_attention(
        self,
        messages: List[Dict[str, Any]],
        current_query: str = ""
    ) -> List[float]:
        """
        计算每条消息的注意力分数

        Args:
            messages: 消息列表，每条消息应包含 content 和可选的 importance
            current_query: 当前查询，用于计算相关性

        Returns:
            List[float]: 每条消息的注意力分数，归一化为概率分布
        """
        if not messages:
            return []

        scores = []
        n = len(messages)

        for i, msg in enumerate(messages):
            # 1. 位置分数 (越新越高，使用指数位置编码)
            recency = math.pow(0.95, n - i - 1)

            # 2. 重要性分数 (如果有 importance 字段则使用，否则用默认值)
            importance = msg.get("importance", 0.5)

            # 3. 相关性分数 (关键词重叠)
            relevance = self._compute_relevance(
                msg.get("content", ""),
                current_query
            ) if current_query else 0.0

            # 加权求和
            total = (
                self.weights["recency"] * recency +
                self.weights["importance"] * importance +
                self.weights["relevance"] * relevance
            )
            scores.append(total)

        # Softmax 归一化
        return self._softmax(scores)

    def _compute_relevance(self, content: str, query: str) -> float:
        """
        计算内容与查询的相关性

        Args:
            content: 消息内容
            query: 查询文本

        Returns:
            float: 相关性分数 [0, 1]
        """
        if not content or not query:
            return 0.0

        # 简单关键词匹配
        query_words = set(self._tokenize(query))
        content_words = set(self._tokenize(content))

        if not query_words:
            return 0.0

        overlap = len(query_words & content_words)
        return min(overlap / len(query_words), 1.0)

    def _tokenize(self, text: str) -> List[str]:
        """
        简单分词

        Args:
            text: 输入文本

        Returns:
            List[str]: 单词列表
        """
        # 简单按空格和标点分割
        import re
        words = re.findall(r'\w+', text.lower())
        return words

    def _softmax(self, scores: List[float]) -> List[float]:
        """
        Softmax 归一化

        Args:
            scores: 原始分数

        Returns:
            List[float]: 归一化后的概率分布
        """
        if not scores:
            return []

        # 防止数值溢出
        max_score = max(scores)
        exp_scores = [math.exp(s - max_score) for s in scores]
        sum_exp = sum(exp_scores)

        if sum_exp == 0:
            return [1.0 / len(scores)] * len(scores)

        return [e / sum_exp for e in exp_scores]

    def select_top_messages(
        self,
        messages: List[Dict[str, Any]],
        current_query: str = ""
    ) -> List[Dict[str, Any]]:
        """
        选择注意力最高的消息

        Args:
            messages: 消息列表
            current_query: 当前查询

        Returns:
            List[Dict]: 按注意力分数排序的消息列表
        """
        if not messages:
            return []

        # 计算注意力分数
        attention_scores = self.compute_attention(messages, current_query)

        # 为每条消息附加分数
        scored_messages = [
            {**msg, "_attention_score": score}
            for msg, score in zip(messages, attention_scores)
        ]

        # 按分数降序排序
        scored_messages.sort(key=lambda x: x["_attention_score"], reverse=True)

        # 截取窗口大小
        return scored_messages[:self.window_size]

    def get_context_window(
        self,
        messages: List[Dict[str, Any]],
        current_query: str = "",
        include_scores: bool = False
    ) -> List[Dict[str, Any]]:
        """
        获取上下文字符串

        Args:
            messages: 消息列表
            current_query: 当前查询
            include_scores: 是否在返回消息中包含注意力分数

        Returns:
            List[Dict]: 过滤和排序后的消息列表
        """
        selected = self.select_top_messages(messages, current_query)

        if not include_scores:
            # 移除内部分数字段
            return [
                {k: v for k, v in msg.items() if k != "_attention_score"}
                for msg in selected
            ]

        return selected

    def get_stats(self) -> Dict[str, Any]:
        """
        获取注意力窗口统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "window_size": self.window_size,
            "weights": self.weights
        }
