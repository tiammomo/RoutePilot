"""
反思机制 (Reflection Mechanism)

从经验中提取高层次信息的组件。

触发条件:
- 每 N 条消息后 (trigger_interval)
- 会话结束时
- 用户明确要求时

使用示例:
    from memory.reflection import ReflectionMechanism

    reflector = ReflectionMechanism(llm_client, trigger_interval=10)
    result = await reflector.reflect(conversation_history)
    # 返回: {"key_insights": [...], "user_intents": [...], ...}
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    """反思结果"""
    key_insights: List[str] = field(default_factory=list)
    user_intents: List[str] = field(default_factory=list)
    knowledge_gaps: List[str] = field(default_factory=list)
    successful_actions: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_insights": self.key_insights,
            "user_intents": self.user_intents,
            "knowledge_gaps": self.knowledge_gaps,
            "successful_actions": self.successful_actions,
            "user_preferences": self.user_preferences,
            "timestamp": self.timestamp
        }


class ReflectionMechanism:
    """
    反思机制 - 从对话历史中提取高层次信息

    核心功能：
    1. 关键洞察提取：从对话中提取关键信息和知识
    2. 用户意图模式：识别用户的意图模式和偏好
    3. 知识缺口识别：识别系统未能满足的用户需求
    4. 成功行动记录：记录有效的辅助行为
    """

    # 旅行领域关键词模式
    TRAVEL_PATTERNS = {
        "destination": ["去", "到", "目的地", "城市", "景点", "景区"],
        "budget": ["预算", "花费", "费用", "便宜", "贵", "性价比"],
        "time": ["时间", "几天", "日程", "行程", "安排"],
        "preference": ["喜欢", "偏好", "想要", "兴趣", "风格"],
        "crowd": ["人少", "人多", "拥挤", "安静", "热闹"]
    }

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        trigger_interval: int = 10,
        min_messages: int = 5
    ):
        """
        初始化反思机制

        Args:
            llm_client: LLM 客户端，用于 LLM 反思
            trigger_interval: 触发反思的消息间隔
            min_messages: 最少消息数才能触发反思
        """
        self.llm_client = llm_client
        self.trigger_interval = trigger_interval
        self.min_messages = min_messages
        self._reflection_cache: Dict[str, ReflectionResult] = {}

    def should_reflect(self, message_count: int) -> bool:
        """
        判断是否应该触发反思

        Args:
            message_count: 当前消息数量

        Returns:
            bool: 是否应该触发反思
        """
        return message_count > 0 and (
            message_count % self.trigger_interval == 0
        )

    async def reflect(
        self,
        conversation_history: List[Dict[str, Any]],
        session_id: str = ""
    ) -> ReflectionResult:
        """
        执行反思

        Args:
            conversation_history: 对话历史
            session_id: 会话 ID（可选，用于缓存）

        Returns:
            ReflectionResult: 反思结果
        """
        # 检查缓存
        if session_id and session_id in self._reflection_cache:
            return self._reflection_cache[session_id]

        # 消息数量不足，使用基于规则的反思
        if len(conversation_history) < self.min_messages:
            result = self._rule_based_reflect(conversation_history)
        elif self.llm_client:
            # 使用 LLM 进行深度反思
            result = await self._llm_reflect(conversation_history)
        else:
            # 回退到基于规则的反思
            result = self._rule_based_reflect(conversation_history)

        # 缓存结果
        if session_id:
            self._reflection_cache[session_id] = result

        return result

    async def _llm_reflect(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> ReflectionResult:
        """
        使用 LLM 进行反思

        Args:
            conversation_history: 对话历史

        Returns:
            ReflectionResult: 反思结果
        """
        try:
            prompt = self._build_reflection_prompt(conversation_history)
            response = await self.llm_client.chat(prompt)
            return self._parse_reflection(response)
        except Exception as e:
            logger.warning(f"LLM reflection failed: {e}, using rule-based")
            return self._rule_based_reflect(conversation_history)

    def _rule_based_reflect(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> ReflectionResult:
        """
        基于规则的反思（无需 LLM）

        Args:
            conversation_history: 对话历史

        Returns:
            ReflectionResult: 反思结果
        """
        result = ReflectionResult(timestamp=self._get_timestamp())

        # 提取用户消息
        user_messages = [
            msg.get("content", "")
            for msg in conversation_history
            if msg.get("role") == "user"
        ]

        # 提取关键信息
        for msg in user_messages:
            # 提取目的地
            for pattern in self.TRAVEL_PATTERNS["destination"]:
                if pattern in msg:
                    result.key_insights.append(f"用户关注目的地信息")

            # 提取预算
            budget_match = re.search(r'(\d+)\s*元', msg)
            if budget_match:
                result.user_preferences["budget"] = budget_match.group(1)

            # 提取时间
            time_match = re.search(r'(\d+)\s*天', msg)
            if time_match:
                result.user_preferences["duration"] = time_match.group(1)

            # 提取偏好
            for pattern in self.TRAVEL_PATTERNS["preference"]:
                if pattern in msg:
                    result.user_intents.append(f"用户表达偏好: {pattern}")

        # 去重
        result.key_insights = list(set(result.key_insights))
        result.user_intents = list(set(result.user_intents))

        return result

    def _build_reflection_prompt(
        self,
        conversation_history: List[Dict[str, Any]]
    ) -> str:
        """
        构建反思提示词

        Args:
            conversation_history: 对话历史

        Returns:
            str: 反思提示词
        """
        # 格式化对话历史
        history_text = ""
        for msg in conversation_history[-20:]:  # 只取最近 20 条
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_text += f"{role}: {content}\n"

        prompt = f"""请分析以下对话历史，提取关键信息：

{history_text}

请以 JSON 格式返回分析结果，包含以下字段：
- key_insights: 关键洞察列表
- user_intents: 用户意图模式列表
- knowledge_gaps: 知识缺口列表
- successful_actions: 成功行动列表
- user_preferences: 用户偏好字典

请只返回 JSON，不要其他内容。"""

        return prompt

    def _parse_reflection(self, response: str) -> ReflectionResult:
        """
        解析 LLM 反思结果

        Args:
            response: LLM 响应

        Returns:
            ReflectionResult: 反思结果
        """
        import json

        result = ReflectionResult(timestamp=self._get_timestamp())

        try:
            # 尝试解析 JSON
            # 移除可能的 markdown 代码块标记
            response = re.sub(r'```json', '', response)
            response = re.sub(r'```', '', response)
            data = json.loads(response.strip())

            result.key_insights = data.get("key_insights", [])
            result.user_intents = data.get("user_intents", [])
            result.knowledge_gaps = data.get("knowledge_gaps", [])
            result.successful_actions = data.get("successful_actions", [])
            result.user_preferences = data.get("user_preferences", {})

        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to parse reflection: {e}")
            # 尝试基于关键词提取
            result.key_insights = self._extract_keywords(response)

        return result

    def _extract_keywords(self, text: str) -> List[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            List[str]: 关键词列表
        """
        keywords = []
        for category, patterns in self.TRAVEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    keywords.append(pattern)
        return list(set(keywords))[:5]

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()

    def clear_cache(self, session_id: str = ""):
        """
        清除缓存

        Args:
            session_id: 会话 ID，为空则清除所有
        """
        if session_id:
            self._reflection_cache.pop(session_id, None)
        else:
            self._reflection_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "trigger_interval": self.trigger_interval,
            "min_messages": self.min_messages,
            "cache_size": len(self._reflection_cache)
        }
