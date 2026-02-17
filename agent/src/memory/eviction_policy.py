"""
智能淘汰策略 (Smart Eviction Policy)

基于多维度决策的淘汰策略。

淘汰考虑因素:
1. 重要性分数 (Importance Score)
2. 时间衰减 (Time Decay)
3. 访问频率 (Access Frequency)
4. 任务相关性 (Task Relevance)

使用示例:
    from memory.eviction_policy import SmartEvictionPolicy

    policy = SmartEvictionPolicy()
    priority = policy.compute_priority(message)
    # 返回: 0.75

    # 批量排序
    sorted_messages = policy.sort_by_priority(messages)
"""

import math
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EvictionWeights:
    """淘汰权重配置"""
    importance: float = 0.4
    time_decay: float = 0.3
    access_frequency: float = 0.3


class SmartEvictionPolicy:
    """
    智能淘汰策略 - 基于多维度决策

    核心算法:
    priority = w1 * importance + w2 * time_score + w3 * access_score

    其中:
    - importance: 重要性分数 [0, 1]
    - time_score: 时间衰减分数，使用指数衰减
    - access_score: 访问频率分数
    """

    # 时间衰减参数（小时）
    DECAY_HALF_LIFE = 24

    def __init__(
        self,
        weights: Optional[EvictionWeights] = None,
        min_priority: float = 0.1,
        max_size: int = 50
    ):
        """
        初始化智能淘汰策略

        Args:
            weights: 权重配置
            min_priority: 最低优先级阈值
            max_size: 最大容量
        """
        self.weights = weights or EvictionWeights()
        self.min_priority = min_priority
        self.max_size = max_size

    def compute_priority(self, msg: Dict[str, Any]) -> float:
        """
        计算消息优先级

        Args:
            msg: 消息字典，应包含 importance, timestamp, access_count 等字段

        Returns:
            float: 优先级分数 [0, 1]
        """
        # 1. 重要性分数 (0.4)
        importance = msg.get("importance", 0.5)

        # 2. 时间衰减 (0.3)
        time_score = self._compute_time_score(msg.get("timestamp", ""))

        # 3. 访问频率 (0.3)
        access_score = self._compute_access_score(
            msg.get("access_count", 1)
        )

        # 加权求和
        priority = (
            self.weights.importance * importance +
            self.weights.time_decay * time_score +
            self.weights.access_frequency * access_score
        )

        return max(0.0, min(1.0, priority))

    def _compute_time_score(self, timestamp: str) -> float:
        """
        计算时间衰减分数

        使用指数衰减: score = e^(-t / half_life)

        Args:
            timestamp: ISO 格式时间戳

        Returns:
            float: 时间分数 [0, 1]
        """
        if not timestamp:
            return 0.5  # 默认中间值

        try:
            msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(msg_time.tzinfo)

            # 计算小时差
            hours_old = (now - msg_time).total_seconds() / 3600

            # 指数衰减
            time_score = math.exp(-hours_old / self.DECAY_HALF_LIFE)
            return time_score

        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse timestamp: {e}")
            return 0.5

    def _compute_access_score(self, access_count: int) -> float:
        """
        计算访问频率分数

        使用对数缩放避免极端值

        Args:
            access_count: 访问次数

        Returns:
            float: 访问分数 [0, 1]
        """
        if access_count <= 0:
            return 0.0

        # 对数缩放：访问 10 次得 1 分
        return min(math.log1p(access_count) / math.log1p(10), 1.0)

    def should_evict(
        self,
        current_size: int,
        incoming_count: int = 1
    ) -> bool:
        """
        判断是否应该触发淘汰

        Args:
            current_size: 当前容量
            incoming_count: 即将进入的消息数量

        Returns:
            bool: 是否需要淘汰
        """
        return current_size + incoming_count > self.max_size

    def get_eviction_candidates(
        self,
        messages: List[Dict[str, Any]],
        count: int = 1
    ) -> List[Dict[str, Any]]:
        """
        获取应该被淘汰的消息候选

        Args:
            messages: 消息列表
            count: 需要淘汰的数量

        Returns:
            List[Dict]: 按优先级排序的待淘汰消息
        """
        if not messages:
            return []

        # 计算每条消息的优先级
        scored_messages = []
        for msg in messages:
            priority = self.compute_priority(msg)
            scored_messages.append({
                **msg,
                "_eviction_priority": priority
            })

        # 按优先级升序排序（低优先级的先淘汰）
        scored_messages.sort(key=lambda x: x["_eviction_priority"])

        # 返回待淘汰的消息
        return scored_messages[:count]

    def sort_by_priority(
        self,
        messages: List[Dict[str, Any]],
        ascending: bool = False
    ) -> List[Dict[str, Any]]:
        """
        按优先级排序消息

        Args:
            messages: 消息列表
            ascending: 是否升序（False = 重要消息排前面）

        Returns:
            List[Dict]: 排序后的消息列表
        """
        if not messages:
            return []

        # 计算优先级并排序
        scored_messages = [
            {**msg, "_priority": self.compute_priority(msg)}
            for msg in messages
        ]

        scored_messages.sort(
            key=lambda x: x["_priority"],
            reverse=not ascending
        )

        # 移除内部分数
        return [
            {k: v for k, v in msg.items() if not k.startswith("_")}
            for msg in scored_messages
        ]

    def get_stats(self) -> Dict[str, Any]:
        """
        获取策略统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "weights": {
                "importance": self.weights.importance,
                "time_decay": self.weights.time_decay,
                "access_frequency": self.weights.access_frequency
            },
            "min_priority": self.min_priority,
            "max_size": self.max_size,
            "decay_half_life_hours": self.DECAY_HALF_LIFE
        }


class AdaptiveEvictionPolicy(SmartEvictionPolicy):
    """
    自适应淘汰策略 - 根据使用情况动态调整权重

    特点：
    - 监控实际访问模式
    - 自动调整权重以优化命中率
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._access_history: List[int] = []
        self._adjustment_factor = 0.1

    def record_access(self, priority: float):
        """
        记录一次访问，用于自适应调整

        Args:
            priority: 被访问消息的优先级
        """
        self._access_history.append(priority)
        # 保持历史在合理大小
        if len(self._access_history) > 1000:
            self._access_history = self._access_history[-500:]

    def adjust_weights(self):
        """
        根据访问历史调整权重

        基于观察：如果高优先级消息被频繁访问，增加 importance 权重
        """
        if len(self._access_history) < 10:
            return

        # 计算高优先级访问比例
        high_priority_count = sum(1 for p in self._access_history if p > 0.7)
        high_priority_ratio = high_priority_count / len(self._access_history)

        # 动态调整
        if high_priority_ratio > 0.6:
            # 高优先级访问多，增加 importance 权重
            self.weights.importance = min(
                self.weights.importance + self._adjustment_factor,
                0.6
            )
        elif high_priority_ratio < 0.3:
            # 高优先级访问少，减少 importance 权重
            self.weights.importance = max(
                self.weights.importance - self._adjustment_factor,
                0.2
            )

        # 归一化权重
        total = sum([
            self.weights.importance,
            self.weights.time_decay,
            self.weights.access_frequency
        ])
        self.weights.importance /= total
        self.weights.time_decay /= total
        self.weights.access_frequency /= total

        logger.info(
            f"Adjusted weights: "
            f"importance={self.weights.importance:.2f}, "
            f"time_decay={self.weights.time_decay:.2f}, "
            f"access_frequency={self.weights.access_frequency:.2f}"
        )
