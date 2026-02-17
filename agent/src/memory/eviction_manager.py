"""
智能淘汰管理器 (Smart Eviction Manager)

提供多种记忆淘汰策略，支持动态调整和策略切换。
用于管理短期记忆的容量，确保重要信息不会被过早淘汰。

功能特点:
- 多种淘汰策略 (FIFO, LFU, Priority, Hybrid)
- 基于重要性的智能淘汰
- 支持策略动态切换
- 淘汰前预压缩保留关键信息

使用示例:
    manager = EvictionManager(max_size=20, min_importance=0.3)
    manager.add(memory_item)
    if manager.should_evict():
        candidates = manager.get_eviction_candidates(count=1)
        manager.evict(candidates)
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class EvictionStrategy(Enum):
    """淘汰策略枚举"""
    FIFO = "fifo"           # 先进先出
    LFU = "lfu"             # 最不频繁使用
    LRU = "lru"             # 最近最少使用
    PRIORITY = "priority"   # 基于优先级
    HYBRID = "hybrid"       # 混合策略
    ADAPTIVE = "adaptive"   # 自适应策略


@dataclass
class MemoryItem:
    """记忆项"""
    id: str
    content: Any
    importance: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "importance": self.importance,
            "timestamp": self.timestamp,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryItem':
        return cls(
            id=data.get('id', ''),
            content=data.get('content'),
            importance=data.get('importance', 0.5),
            timestamp=data.get('timestamp', datetime.now().isoformat()),
            access_count=data.get('access_count', 0),
            last_accessed=data.get('last_accessed', datetime.now().isoformat()),
            metadata=data.get('metadata', {})
        )


@dataclass
class EvictionConfig:
    """淘汰配置"""
    max_size: int = 20               # 最大容量
    min_importance: float = 0.3      # 最低重要性阈值
    buffer_ratio: float = 0.2        # 缓冲区比例
    enable_compression: bool = True  # 是否启用预压缩
    strategy: EvictionStrategy = EvictionStrategy.HYBRID
    custom_score_func: Optional[Callable[[MemoryItem], float]] = None


class EvictionManager:
    """
    智能淘汰管理器

    负责管理短期记忆的容量淘汰，支持多种策略：
    - FIFO: 先进先出，简单但可能丢失重要信息
    - LFU: 最不频繁使用，适合访问模式稳定的场景
    - LRU: 最近最少使用，适合会话场景
    - Priority: 基于重要性，保留高重要性记忆
    - Hybrid: 混合策略，综合考虑时间和重要性
    - Adaptive: 自适应，根据使用模式自动调整

    Attributes:
        config: 淘汰配置
        memories: 记忆存储（deque 实现自动大小限制）
        priority_queue: 优先级队列（用于快速查找）
    """

    def __init__(self, config: Optional[EvictionConfig] = None):
        """
        初始化淘汰管理器

        Args:
            config: 淘汰配置
        """
        self.config = config or EvictionConfig()
        self.max_size = self.config.max_size
        self.min_importance = self.config.min_importance

        # 主存储：使用 deque 实现自动淘汰
        self._storage: deque = deque(maxlen=int(self.max_size * (1 + self.config.buffer_ratio)))

        # 优先级索引：{importance: [items]}
        self._priority_index: Dict[float, List[MemoryItem]] = {}

        # 访问频率索引：{id: count}
        self._access_index: Dict[str, int] = {}

        # 当前策略
        self._current_strategy = self.config.strategy

        # 统计信息
        self._stats = {
            "total_evictions": 0,
            "eviction_reasons": {}
        }

    def add(self, item: MemoryItem) -> bool:
        """
        添加记忆项

        Args:
            item: 记忆项

        Returns:
            bool: 是否触发淘汰
        """
        # 更新访问信息
        item.last_accessed = datetime.now().isoformat()
        item.access_count = self._access_index.get(item.id, 0) + 1
        self._access_index[item.id] = item.access_count

        # 检查是否需要淘汰
        should_evict = len(self._storage) >= self.max_size

        if should_evict:
            # 先尝试淘汰低重要性记忆
            evicted = self._try_evict_low_importance()
            if not evicted:
                # 如果没有低重要性可淘汰，使用策略淘汰
                candidates = self._select_candidates(1)
                if candidates:
                    self._evict_items(candidates)
                    should_evict = True

        # 添加新记忆
        self._storage.append(item)
        self._update_priority_index(item)

        return should_evict

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """
        获取记忆项

        Args:
            memory_id: 记忆 ID

        Returns:
            Optional[MemoryItem]: 记忆项，不存在返回 None
        """
        for item in self._storage:
            if item.id == memory_id:
                # 更新访问信息
                item.last_accessed = datetime.now().isoformat()
                item.access_count += 1
                self._access_index[item.id] = item.access_count
                return item
        return None

    def get_recent(self, limit: int = 5) -> List[MemoryItem]:
        """
        获取最近的记忆

        Args:
            limit: 返回数量限制

        Returns:
            List[MemoryItem]: 最近的记忆列表
        """
        items = list(self._storage)
        return items[-limit:] if limit < len(items) else items

    def get_all(self) -> List[MemoryItem]:
        """
        获取所有记忆

        Returns:
            List[MemoryItem]: 所有记忆列表
        """
        return list(self._storage)

    def should_evict(self, new_importance: float = None) -> bool:
        """
        判断是否需要淘汰

        Args:
            new_importance: 新记忆的重要性分数

        Returns:
            bool: 是否需要淘汰
        """
        current_size = len(self._storage)

        if current_size < self.max_size:
            return False

        if new_importance is not None:
            # 检查是否有低重要性记忆可淘汰
            low_importance_count = sum(
                1 for item in self._storage
                if item.importance < self.min_importance
            )

            # 如果新记忆重要性高，且存在可淘汰的低重要性记忆
            if new_importance > self.min_importance and low_importance_count > 0:
                return True

        return current_size >= self.max_size

    def _try_evict_low_importance(self) -> bool:
        """
        尝试淘汰低重要性记忆

        Returns:
            bool: 是否成功淘汰
        """
        # 按重要性排序，找最低的
        sorted_items = sorted(
            self._storage,
            key=lambda x: (x.importance, x.timestamp)
        )

        # 找到第一个低于阈值的
        for item in sorted_items:
            if item.importance < self.min_importance:
                self._storage.remove(item)
                self._remove_from_priority_index(item)
                del self._access_index[item.id]

                self._stats["total_evictions"] += 1
                self._stats["eviction_reasons"]["low_importance"] = \
                    self._stats["eviction_reasons"].get("low_importance", 0) + 1

                logger.debug(f"淘汰低重要性记忆: {item.id} (importance={item.importance})")
                return True

        return False

    def _select_candidates(self, count: int = 1) -> List[MemoryItem]:
        """
        根据当前策略选择淘汰候选

        Args:
            count: 需要选择的数量

        Returns:
            List[MemoryItem]: 淘汰候选列表
        """
        items = list(self._storage)

        if not items:
            return []

        if self._current_strategy == EvictionStrategy.FIFO:
            # 按时间排序（最老的先淘汰）
            return [min(items, key=lambda x: x.timestamp)][:count]

        elif self._current_strategy == EvictionStrategy.LFU:
            # 按访问频率排序（最不常用的先淘汰）
            return [min(items, key=lambda x: x.access_count)][:count]

        elif self._current_strategy == EvictionStrategy.LRU:
            # 按最近访问时间排序（最久未访问的先淘汰）
            return [min(items, key=lambda x: x.last_accessed)][:count]

        elif self._current_strategy == EvictionStrategy.PRIORITY:
            # 按重要性排序（最低重要性的先淘汰）
            return [min(items, key=lambda x: x.importance)][:count]

        elif self._current_strategy == EvictionStrategy.HYBRID:
            # 综合考虑：重要性 × 访问频率 / 年龄
            scored = []
            for item in items:
                age_hours = self._get_age_hours(item.timestamp)
                importance = item.importance
                access = item.access_count + 1

                # 综合分数（越低越容易被淘汰）
                score = importance * 0.4 + (1 / (age_hours + 1)) * 0.3 + (access / 100) * 0.3
                scored.append((score, item))

            scored.sort(key=lambda x: x[0])
            return [item for _, item in scored[:count]]

        elif self._current_strategy == EvictionStrategy.ADAPTIVE:
            # 自适应：分析使用模式
            return self._adaptive_select(items, count)

        # 默认使用优先级策略
        return [min(items, key=lambda x: x.importance)][:count]

    def _adaptive_select(
        self,
        items: List[MemoryItem],
        count: int
    ) -> List[MemoryItem]:
        """自适应选择"""
        # 分析最近的使用模式
        recent_access = sum(
            item.access_count for item in items
            if self._get_age_hours(item.last_accessed) < 1
        )

        total_access = sum(item.access_count for item in items)
        recent_ratio = recent_access / (total_access + 1)

        # 如果最近访问频繁，使用 LRU
        if recent_ratio > 0.5:
            return [min(items, key=lambda x: x.last_accessed)][:count]

        # 如果访问均匀，使用 LFU
        return [min(items, key=lambda x: x.access_count)][:count]

    def _evict_items(self, items: List[MemoryItem]) -> None:
        """执行淘汰"""
        for item in items:
            if item in self._storage:
                self._storage.remove(item)
                self._remove_from_priority_index(item)
                del self._access_index[item.id]

                self._stats["total_evictions"] += 1
                self._stats["eviction_reasons"]["strategy"] = \
                    self._stats["eviction_reasons"].get("strategy", 0) + 1

                logger.debug(f"策略淘汰记忆: {item.id} (strategy={self._current_strategy.value})")

    def _update_priority_index(self, item: MemoryItem) -> None:
        """更新优先级索引"""
        rounded_importance = round(item.importance, 1)
        if rounded_importance not in self._priority_index:
            self._priority_index[rounded_importance] = []
        if item not in self._priority_index[rounded_importance]:
            self._priority_index[rounded_importance].append(item)

    def _remove_from_priority_index(self, item: MemoryItem) -> None:
        """从优先级索引中移除"""
        rounded_importance = round(item.importance, 1)
        if rounded_importance in self._priority_index:
            if item in self._priority_index[rounded_importance]:
                self._priority_index[rounded_importance].remove(item)

    def _get_age_hours(self, timestamp: str) -> float:
        """计算记忆的年龄（小时）"""
        try:
            from datetime import datetime
            msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return (datetime.now() - msg_time).total_seconds() / 3600
        except Exception:
            return 0

    def set_strategy(self, strategy: EvictionStrategy) -> None:
        """
        设置淘汰策略

        Args:
            strategy: 淘汰策略
        """
        self._current_strategy = strategy
        logger.info(f"淘汰策略已切换为: {strategy.value}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "current_size": len(self._storage),
            "max_size": self.max_size,
            "current_strategy": self._current_strategy.value,
            "total_evictions": self._stats["total_evictions"],
            "eviction_reasons": self._stats["eviction_reasons"],
            "priority_distribution": {
                f"{k}": len(v) for k, v in self._priority_index.items()
            }
        }

    def clear(self, keep_high_importance: bool = True) -> List[MemoryItem]:
        """
        清空记忆

        Args:
            keep_high_importance: 是否保留高重要性记忆

        Returns:
            List[MemoryItem]: 被清除的记忆列表
        """
        removed = []

        if keep_high_importance:
            # 只保留高重要性记忆
            to_remove = [
                item for item in self._storage
                if item.importance < self.min_importance
            ]
        else:
            to_remove = list(self._storage)

        for item in to_remove:
            self._storage.remove(item)
            self._remove_from_priority_index(item)
            del self._access_index[item.id]
            removed.append(item)

        return removed

    def access(self, memory_id: str) -> Optional[MemoryItem]:
        """
        访问记忆（更新访问时间）

        Args:
            memory_id: 记忆 ID

        Returns:
            Optional[MemoryItem]: 被访问的记忆项
        """
        item = self.get(memory_id)
        if item:
            item.last_accessed = datetime.now().isoformat()
            logger.debug(f"访问记忆: {memory_id}")
        return item

    def update_importance(
        self,
        memory_id: str,
        new_importance: float
    ) -> bool:
        """
        更新记忆的重要性

        Args:
            memory_id: 记忆 ID
            new_importance: 新的重要性分数

        Returns:
            bool: 是否更新成功
        """
        item = self.get(memory_id)
        if item:
            old_importance = item.importance
            self._remove_from_priority_index(item)
            item.importance = new_importance
            self._update_priority_index(item)
            logger.debug(f"更新重要性: {memory_id} ({old_importance} -> {new_importance})")
            return True
        return False

    def serialize(self) -> Dict[str, Any]:
        """序列化管理器状态"""
        return {
            "config": {
                "max_size": self.max_size,
                "min_importance": self.min_importance,
                "strategy": self._current_strategy.value
            },
            "memories": [item.to_dict() for item in self._storage],
            "stats": self._stats
        }

    def deserialize(self, data: Dict[str, Any]) -> None:
        """从序列化数据恢复"""
        config = data.get("config", {})
        self.max_size = config.get("max_size", 20)
        self.min_importance = config.get("min_importance", 0.3)

        strategy = config.get("strategy", "hybrid")
        self._current_strategy = EvictionStrategy(strategy)

        self._storage = deque(maxlen=int(self.max_size * 1.2))
        for mem_data in data.get("memories", []):
            item = MemoryItem.from_dict(mem_data)
            self._storage.append(item)
            self._update_priority_index(item)
            self._access_index[item.id] = item.access_count

        self._stats = data.get("stats", {"total_evictions": 0, "eviction_reasons": {}})
