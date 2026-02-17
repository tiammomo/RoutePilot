"""
对话摘要压缩器 (Conversation Summarizer)

将长对话压缩为摘要，保留关键信息，减少 token 消耗。
支持多种压缩策略和摘要生成方式。

功能特点:
- 多级压缩（轻度/中度/重度）
- 关键事实提取
- 用户偏好识别
- LLM 摘要生成
- 规则-based 快速摘要

使用示例:
    summarizer = ConversationSummarizer(llm_client)
    summary = await summarizer.summarize(messages, level="moderate")
    facts = await summarizer.extract_key_facts(messages)
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class CompressionLevel(Enum):
    """压缩级别"""
    LIGHT = "light"     # 轻度压缩，保留 80% 内容
    MODERATE = "moderate"  # 中度压缩，保留 50% 内容
    AGGRESSIVE = "aggressive"  # 重度压缩，保留 20% 内容


@dataclass
class ConversationSummary:
    """对话摘要"""
    summary: str
    compression_level: CompressionLevel
    key_facts: List[Dict[str, Any]] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    topics: List[str] = field(default_factory=list)
    message_count_before: int = 0
    message_count_after: int = 0
    tokens_saved: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "compression_level": self.compression_level.value,
            "key_facts": self.key_facts,
            "user_preferences": self.user_preferences,
            "topics": self.topics,
            "message_count_before": self.message_count_before,
            "message_count_after": self.message_count_after,
            "tokens_saved": self.tokens_saved
        }


@dataclass
class ExtractedFact:
    """提取的事实"""
    type: str  # budget, city, preference, plan, etc.
    value: Any
    confidence: float  # 0-1
    source_message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConversationSummarizer:
    """
    对话摘要压缩器

    提供多种摘要生成方式：
    1. 规则-based 快速摘要（无需 LLM）
    2. LLM 智能摘要（高质量，但需要 API）
    3. 混合模式（先规则后 LLM 优化）
    """

    # 预算模式
    BUDGET_PATTERNS = [
        r"预算(\d+)",
        r"(\d+)元",
        r"(\d+)块",
        r"大概(.+)元左右",
        r"花费(.+)"
    ]

    # 天数模式
    DAYS_PATTERNS = [
        r"(\d+)\s*天",
        r"(\d+)日",
        r"几天",
        r"多少天"
    ]

    # 城市模式
    CITY_PATTERNS = [
        r"去(.+)旅游",
        r"(.+)景点",
        r"在(.+)",
        r"(.+)城市"
    ]

    # 偏好关键词
    PREFERENCE_KEYWORDS = {
        "美食": ["美食", "好吃", "餐厅", "小吃"],
        "自然": ["自然", "风景", "风光", "山水"],
        "历史": ["历史", "古迹", "文化", "博物馆"],
        "购物": ["购物", "商场", "免税"],
        "海滩": ["海滩", "海边", "海滨", "沙滩"],
        "休闲": ["休闲", "放松", "度假"]
    }

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_tokens: int = 500,
        min_tokens: int = 100
    ):
        """
        初始化摘要压缩器

        Args:
            llm_client: 可选的 LLM 客户端
            max_tokens: 摘要最大 token 数
            min_tokens: 摘要最小 token 数
        """
        self.llm_client = llm_client
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens

    async def summarize(
        self,
        messages: List[Dict[str, str]],
        level: str = "moderate"
    ) -> ConversationSummary:
        """
        生成对话摘要

        Args:
            messages: 消息列表 [{role: 'user'|'assistant', content: '...'}]
            level: 压缩级别 (light/moderate/aggressive)

        Returns:
            ConversationSummary: 对话摘要
        """
        compression_level = CompressionLevel(level)

        if not messages:
            return ConversationSummary(
                summary="空对话",
                compression_level=compression_level
            )

        original_count = len(messages)

        # 根据压缩级别选择策略
        if self.llm_client and compression_level != CompressionLevel.LIGHT:
            # 使用 LLM 生成摘要
            summary = await self._llm_summarize(messages, compression_level)
        else:
            # 使用规则快速摘要
            summary = await self._rule_based_summarize(messages, compression_level)

        # 提取关键事实
        facts = await self.extract_key_facts(messages)
        summary.key_facts = [f.to_dict() for f in facts]

        # 提取用户偏好
        summary.user_preferences = await self._extract_preferences(messages)

        # 识别主题
        summary.topics = self._identify_topics(messages)

        summary.message_count_before = original_count
        summary.message_count_after = 1  # 摘要为一条消息
        summary.tokens_saved = self._estimate_tokens(messages) - self._estimate_tokens([{
            "role": "assistant",
            "content": summary.summary
        }])

        return summary

    async def _llm_summarize(
        self,
        messages: List[Dict[str, str]],
        level: CompressionLevel
    ) -> ConversationSummary:
        """使用 LLM 生成摘要"""
        # 根据压缩级别调整提示词
        if level == CompressionLevel.LIGHT:
            instruction = "保留大部分细节，生成稍短的摘要"
            target_length = "200-300字"
        elif level == CompressionLevel.MODERATE:
            instruction = "保留关键信息，去除冗余，生成简洁摘要"
            target_length = "100-150字"
        else:  # AGGRESSIVE
            instruction = "只保留最核心的信息，非常简洁"
            target_length = "50-80字"

        prompt = f"""请将以下对话压缩为{target_length}的摘要：

{self._format_messages(messages)}

要求：
- {instruction}
- 保留用户偏好、目的地、预算、时间等关键信息
- 摘要用中文
- 只返回摘要内容，不要其他内容"""

        if self.llm_client:
            try:
                result = await self.llm_client.chat([
                    {"role": "system", "content": "你是对话摘要专家"},
                    {"role": "user", "content": prompt}
                ])

                if result.get('success'):
                    summary_text = result.get('content', '').strip()
                else:
                    summary_text = await self._rule_based_summarize(messages, level).summary
            except Exception as e:
                logger.warning(f"LLM 摘要生成失败: {e}")
                summary_text = await self._rule_based_summarize(messages, level).summary
        else:
            summary_text = await self._rule_based_summarize(messages, level).summary

        return ConversationSummary(
            summary=summary_text,
            compression_level=level
        )

    async def _rule_based_summarize(
        self,
        messages: List[Dict[str, str]],
        level: CompressionLevel
    ) -> ConversationSummary:
        """基于规则的快速摘要"""
        # 收集关键信息
        key_points = []

        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')

                # 检测预算
                budget = self._extract_budget(content)
                if budget:
                    key_points.append(f"预算: {budget}")

                # 检测天数
                days = self._extract_days(content)
                if days:
                    key_points.append(f"天数: {days}")

                # 检测目的地
                destination = self._extract_destination(content)
                if destination:
                    key_points.append(f"目的地: {destination}")

        # 根据压缩级别调整保留的信息量
        if level == CompressionLevel.LIGHT:
            # 保留所有关键点
            summary = "对话要点: " + " | ".join(key_points)
        elif level == CompressionLevel.MODERATE:
            # 只保留唯一的预算、天数、目的
            unique_points = list(dict.fromkeys(key_points))[:5]
            summary = "要点: " + " | ".join(unique_points)
        else:  # AGGRESSIVE
            # 极度压缩
            unique_points = list(dict.fromkeys(key_points))[:3]
            summary = " | ".join(unique_points) if unique_points else "一般对话"

        # 限制长度
        max_chars = {
            CompressionLevel.LIGHT: 300,
            CompressionLevel.MODERATE: 150,
            CompressionLevel.AGGRESSIVE: 80
        }
        max_char = max_chars.get(level, 150)

        if len(summary) > max_char:
            summary = summary[:max_char] + "..."

        return ConversationSummary(
            summary=summary,
            compression_level=level
        )

    async def extract_key_facts(self, messages: List[Dict[str, str]]) -> List[ExtractedFact]:
        """
        从对话中提取关键事实

        Args:
            messages: 消息列表

        Returns:
            List[ExtractedFact]: 提取的事实列表
        """
        facts = []

        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')

                # 提取预算
                budget = self._extract_budget(content)
                if budget:
                    facts.append(ExtractedFact(
                        type="budget",
                        value=budget,
                        confidence=0.9,
                        source_message=content[:100]
                    ))

                # 提取天数
                days = self._extract_days(content)
                if days:
                    facts.append(ExtractedFact(
                        type="days",
                        value=days,
                        confidence=0.9,
                        source_message=content[:100]
                    ))

                # 提取目的地
                destination = self._extract_destination(content)
                if destination:
                    facts.append(ExtractedFact(
                        type="destination",
                        value=destination,
                        confidence=0.7,
                        source_message=content[:100]
                    ))

                # 提取偏好
                for pref_type, keywords in self.PREFERENCE_KEYWORDS.items():
                    for keyword in keywords:
                        if keyword in content:
                            facts.append(ExtractedFact(
                                type="preference",
                                value=pref_type,
                                confidence=0.8,
                                source_message=content[:100]
                            ))
                            break  # 每种偏好类型只提取一次

        return facts

    async def _extract_preferences(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """提取用户偏好"""
        preferences = {
            "budget_range": None,
            "travel_days": None,
            "interest_tags": [],
            "preferred_cities": []
        }

        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')

                # 预算
                budget = self._extract_budget(content)
                if budget:
                    preferences["budget_range"] = budget

                # 天数
                days = self._extract_days(content)
                if days:
                    preferences["travel_days"] = days

                # 偏好标签
                for tag, keywords in self.PREFERENCE_KEYWORDS.items():
                    for keyword in keywords:
                        if keyword in content and tag not in preferences["interest_tags"]:
                            preferences["interest_tags"].append(tag)
                            break

        return preferences

    def _identify_topics(self, messages: List[Dict[str, str]]) -> List[str]:
        """识别对话主题"""
        topics = []
        content_all = " ".join(msg.get('content', '') for msg in messages)

        topic_keywords = {
            "目的地推荐": ["推荐", "城市", "景点", "去"],
            "行程规划": ["行程", "路线", "安排", "计划", "天"],
            "预算咨询": ["预算", "花费", "费用", "钱"],
            "美食探索": ["美食", "好吃", "餐厅", "小吃"],
            "交通出行": ["交通", "怎么去", "飞机", "火车"],
            "住宿选择": ["住宿", "酒店", "宾馆", "民宿"]
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in content_all for kw in keywords):
                topics.append(topic)

        return topics if topics else ["一般咨询"]

    def _extract_budget(self, text: str) -> Optional[str]:
        """提取预算"""
        for pattern in self.BUDGET_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_days(self, text: str) -> Optional[str]:
        """提取天数"""
        for pattern in self.DAYS_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_destination(self, text: str) -> Optional[str]:
        """提取目的地"""
        for pattern in self.CITY_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """格式化消息列表"""
        lines = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:200]  # 限制每条消息长度
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """估算 token 数量（粗略估计：中文约 1.5 字/token）"""
        total_chars = sum(
            len(msg.get('role', '')) + len(msg.get('content', ''))
            for msg in messages
        )
        return int(total_chars / 1.5)

    def compress_for_context(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """
        压缩消息列表用于 LLM 上下文

        策略：
        1. 如果消息数 <= max_messages，直接返回
        2. 否则保留系统消息 + 最近消息 + 摘要

        Args:
            messages: 消息列表
            max_messages: 最大消息数

        Returns:
            List[Dict[str, str]]: 压缩后的消息列表
        """
        if len(messages) <= max_messages:
            return messages

        # 分离系统消息和对话消息
        system_messages = [m for m in messages if m.get('role') == 'system']
        dialog_messages = [m for m in messages if m.get('role') != 'system']

        # 保留最近的消息
        recent_count = max_messages - len(system_messages) - 1  # 留一个位置给摘要
        recent_messages = dialog_messages[-recent_count:] if recent_count > 0 else []

        # 生成摘要替换早期消息
        early_messages = dialog_messages[:-recent_count] if recent_count > 0 else dialog_messages

        if early_messages:
            import asyncio
            summary = asyncio.run(self.summarize(early_messages, level="moderate"))

            compressed = [
                *system_messages,
                {"role": "system", "content": f"[历史对话摘要] {summary.summary}"},
                *recent_messages
            ]
        else:
            compressed = [*system_messages, *recent_messages]

        return compressed

    async def generate_session_report(
        self,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成会话报告

        Args:
            session_data: 会话数据

        Returns:
            Dict: 会话报告
        """
        messages = session_data.get('messages', [])

        # 生成摘要
        summary = await self.summarize(messages, level="moderate")

        # 提取关键事实
        facts = await self.extract_key_facts(messages)

        # 构建报告
        report = {
            "session_id": session_data.get('session_id'),
            "created_at": session_data.get('start_time'),
            "summary": summary.summary,
            "compression_level": summary.compression_level.value,
            "key_facts": [f.to_dict() for f in facts],
            "user_preferences": summary.user_preferences,
            "topics": summary.topics,
            "message_count": len(messages),
            "tokens_saved": summary.tokens_saved,
            "duration": self._calculate_duration(session_data)
        }

        return report

    def _calculate_duration(self, session_data: Dict[str, Any]) -> Optional[str]:
        """计算会话持续时间"""
        try:
            from datetime import datetime
            start = datetime.fromisoformat(session_data.get('start_time', ''))
            end_str = session_data.get('end_time')
            if end_str:
                end = datetime.fromisoformat(end_str)
                duration = end - start
                return str(duration)
        except Exception:
            pass
        return None
