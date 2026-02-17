"""
记忆回流机制 (Memory Recirculation)

管理记忆在不同层次之间的流动。

回流触发条件:
1. 阈值触发: 重要性超过 0.7
2. 频率触发: 同一话题出现 3 次以上
3. 时间触发: 会话结束
4. 手动触发: 用户明确要求

使用示例:
    from memory.recirculation import MemoryRecirculation

    recirculation = MemoryRecirculation(
        threshold_trigger=0.7,
        frequency_trigger=3
    )

    # 检查是否需要回流
    if recirculation.should_recirculate(message, session_history):
        await recirculation.move_to_long_term(message, user_id)
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class RecirculationRule:
    """回流规则配置"""
    threshold_trigger: float = 0.7      # 重要性阈值
    frequency_trigger: int = 3           # 频率触发阈值
    time_trigger: bool = True            # 会话结束触发
    manual_trigger: bool = True          # 手动触发


@dataclass
class MemoryContent:
    """记忆内容"""
    id: str
    content: str
    importance: float
    topic: str = ""
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryRecirculation:
    """
    记忆回流机制

    管理记忆在工作记忆、短期记忆、长期记忆之间的流动。

    核心功能：
    1. 阈值触发 - 高重要性记忆自动回流
    2. 频率触发 - 频繁出现的话题回流
    3. 时间触发 - 会话结束时归档
    4. 手动触发 - 用户明确要求
    """

    def __init__(
        self,
        long_term_store: Optional[Any] = None,
        profile_store: Optional[Any] = None,
        rule: Optional[RecirculationRule] = None
    ):
        """
        初始化记忆回流机制

        Args:
            long_term_store: 长期记忆存储
            profile_store: 用户画像存储
            rule: 回流规则配置
        """
        self.long_term_store = long_term_store
        self.profile_store = profile_store
        self.rule = rule or RecirculationRule()

        # 话题频率跟踪
        self._topic_frequency: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # 待回流队列
        self._pending_recirculation: List[MemoryContent] = []

    def should_recirculate(
        self,
        message: Dict[str, Any],
        session_history: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        判断是否应该触发回流

        Args:
            message: 当前消息
            session_history: 会话历史

        Returns:
            bool: 是否应该回流
        """
        # 1. 阈值触发
        importance = message.get("importance", 0.0)
        if importance >= self.rule.threshold_trigger:
            logger.info(f"Threshold trigger: importance={importance}")
            return True

        # 2. 频率触发
        topic = self._extract_topic(message.get("content", ""))
        if topic and session_history:
            user_id = message.get("user_id", "default")
            self._topic_frequency[user_id][topic] += 1

            freq = self._topic_frequency[user_id][topic]
            if freq >= self.rule.frequency_trigger:
                logger.info(f"Frequency trigger: topic={topic}, freq={freq}")
                return True

        # 3. 时间触发 - 由外部调用 end_session 触发

        # 4. 手动触发 - 由外部参数触发

        return False

    def _extract_topic(self, content: str) -> str:
        """
        从内容中提取话题

        Args:
            content: 消息内容

        Returns:
            str: 话题标签
        """
        # 简单关键词匹配
        topics = {
            "目的地": ["去", "城市", "景点", "景区", "旅游"],
            "预算": ["预算", "费用", "花钱", "便宜", "贵"],
            "时间": ["几天", "时间", "日程", "行程"],
            "美食": ["美食", "好吃", "餐厅", "食物"],
            "住宿": ["酒店", "住宿", "民宿", "房间"],
            "交通": ["交通", "飞机", "火车", "高铁"]
        }

        for topic, keywords in topics.items():
            for keyword in keywords:
                if keyword in content:
                    return topic

        return "general"

    async def move_to_long_term(
        self,
        message: Dict[str, Any],
        user_id: str
    ) -> bool:
        """
        将记忆移动到长期存储

        Args:
            message: 消息内容
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        try:
            # 构建记忆内容
            memory = MemoryContent(
                id=f"mem_{datetime.now().timestamp()}",
                content=message.get("content", ""),
                importance=message.get("importance", 0.5),
                topic=self._extract_topic(message.get("content", "")),
                timestamp=datetime.now().isoformat(),
                metadata={
                    "role": message.get("role", "user"),
                    "session_id": message.get("session_id", "")
                }
            )

            # 存储到长期记忆
            if self.long_term_store and hasattr(self.long_term_store, 'store_memory'):
                await self.long_term_store.store_memory(user_id, memory)
                logger.info(f"Moved to long-term: {memory.id}")
                return True

            # 如果没有长期存储，加入待处理队列
            self._pending_recirculation.append(memory)
            return False

        except Exception as e:
            logger.error(f"Failed to move to long-term: {e}")
            return False

    async def end_session_recirculate(
        self,
        session_id: str,
        user_id: str,
        session_data: Dict[str, Any]
    ) -> List[str]:
        """
        会话结束时的回流处理

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            session_data: 会话数据

        Returns:
            List[str]: 回流的记忆 ID 列表
        """
        if not self.rule.time_trigger:
            return []

        recirculated_ids = []

        try:
            # 1. 归档会话摘要
            if self.long_term_store and hasattr(self.long_term_store, 'store_session'):
                session_id = await self.long_term_store.store_session(session_data)
                recirculated_ids.append(session_id)

            # 2. 更新用户画像
            if self.profile_store:
                await self._update_profile_from_session(
                    user_id,
                    session_data
                )

            # 3. 处理待回流队列
            for memory in self._pending_recirculation:
                if self.long_term_store and hasattr(self.long_term_store, 'store_memory'):
                    await self.long_term_store.store_memory(user_id, memory)
                    recirculated_ids.append(memory.id)

            self._pending_recirculation.clear()

            # 4. 清理话题频率
            if user_id in self._topic_frequency:
                del self._topic_frequency[user_id]

            logger.info(f"Session recirculated: {len(recirculated_ids)} items")

        except Exception as e:
            logger.error(f"End session recirculation failed: {e}")

        return recirculated_ids

    async def _update_profile_from_session(
        self,
        user_id: str,
        session_data: Dict[str, Any]
    ):
        """
        从会话数据更新用户画像

        Args:
            user_id: 用户 ID
            session_data: 会话数据
        """
        if not self.profile_store:
            return

        try:
            # 提取用户偏好
            preferences = self._extract_preferences(session_data)

            # 更新画像
            if hasattr(self.profile_store, 'update_preferences'):
                await self.profile_store.update_preferences(user_id, preferences)

        except Exception as e:
            logger.warning(f"Profile update failed: {e}")

    def _extract_preferences(
        self,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        从会话数据提取用户偏好

        Args:
            session_data: 会话数据

        Returns:
            Dict: 用户偏好
        """
        preferences = {}

        # 从 summary 提取
        summary = session_data.get("summary", "")
        if summary:
            # 预算
            budget_match = re.search(r'(\d+)\s*元', summary)
            if budget_match:
                preferences["budget"] = budget_match.group(1)

            # 时间
            time_match = re.search(r'(\d+)\s*天', summary)
            if time_match:
                preferences["duration"] = time_match.group(1)

        # 从 user_preferences 合并
        if "user_preferences" in session_data:
            preferences.update(session_data["user_preferences"])

        return preferences

    def get_pending_count(self) -> int:
        """
        获取待回流数量

        Returns:
            int: 待回流数量
        """
        return len(self._pending_recirculation)

    def clear_pending(self):
        """清除待回流队列"""
        self._pending_recirculation.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "rule": {
                "threshold_trigger": self.rule.threshold_trigger,
                "frequency_trigger": self.rule.frequency_trigger,
                "time_trigger": self.rule.time_trigger,
                "manual_trigger": self.rule.manual_trigger
            },
            "pending_count": len(self._pending_recirculation),
            "topic_tracking": {
                user_id: len(topics)
                for user_id, topics in self._topic_frequency.items()
            }
        }
