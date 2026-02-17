"""
重要性评分器 (Importance Scorer)

基于多维度评估对话消息的重要性分数，用于智能记忆管理。
支持关键词触发、意图明确度、情感强度和决策点等多种评估维度。

功能特点:
- 多维度综合评分 (0-1)
- 关键词触发机制
- 意图明确度检测
- 情感强度分析
- 决策点标记识别

使用示例:
    scorer = ImportanceScorer(llm_client)
    score = await scorer.score("我想去北京旅游，预算5000元", context)
    # 返回: 0.75
"""

import re
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ImportanceDimension(Enum):
    """重要性评估维度"""
    KEYWORD_TRIGGER = "keyword"      # 关键词触发
    INTENT_CLARITY = "intent"        # 意图明确度
    SENTIMENT = "sentiment"          # 情感强度
    DECISION_POINT = "decision"      # 决策点
    USER_PREFERENCE = "preference"   # 用户偏好


@dataclass
class ImportanceScore:
    """重要性评分结果"""
    total_score: float
    dimensions: Dict[ImportanceDimension, float]
    reasons: List[str]
    is_high_importance: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_score": self.total_score,
            "dimensions": {k.value: v for k, v in self.dimensions.items()},
            "reasons": self.reasons,
            "is_high_importance": self.is_high_importance
        }


class ImportanceScorer:
    """
    重要性评分器

    综合多个维度评估消息的重要性：
    1. 关键词触发 (+0.0-0.2): 检测旅行相关关键词
    2. 意图明确度 (+0.0-0.3): 检测明确的用户请求
    3. 情感强度 (+0.0-0.2): 分析消息情感倾向
    4. 决策点标记 (+0.0-0.3): 识别关键决策信息
    5. 用户偏好 (+0.0-0.2): 提取用户偏好信息
    """

    # 旅行相关关键词映射
    TRAVEL_KEYWORDS = {
        # 目的地相关
        "想去": 0.15, "要去": 0.15, "旅游": 0.12, "旅行": 0.12,
        "游玩": 0.10, "度假": 0.12, "出发": 0.10, "行程": 0.15,

        # 预算相关
        "预算": 0.18, "花费": 0.15, "费用": 0.15, "钱": 0.10,
        "便宜": 0.08, "贵": 0.08, "性价比": 0.12,

        # 时间相关
        "几天": 0.15, "多少天": 0.15, "时间": 0.10, "什么时候": 0.12,
        "季节": 0.12, "春天": 0.08, "夏天": 0.08, "秋天": 0.08, "冬天": 0.08,

        # 偏好相关
        "喜欢": 0.18, "想要": 0.12, "偏好": 0.15, "兴趣": 0.12,
        "美食": 0.10, "历史": 0.10, "自然": 0.10, "风景": 0.10,

        # 决策相关
        "决定": 0.20, "选择": 0.15, "确定": 0.15, "订": 0.18,
        "预约": 0.18, "预订": 0.18, "买票": 0.18
    }

    # 明确意图模式
    INTENT_PATTERNS = [
        r"我想去(.+)",
        r"推荐(.+)",
        r"帮我(.+)",
        r"计划(.+)",
        r"安排(.+)",
        r"怎么去(.+)",
        r"(.+)三日游",
        r"(.+)一日游",
        r"(.+)攻略",
    ]

    # 决策点模式
    DECISION_PATTERNS = [
        r"预算(\d+)",
        r"(\d+)天",
        r"去(.+)，(.+)",
        r"大概(.+)元左右",
        r"我想(.+)然后(.+)",
    ]

    def __init__(self, llm_client: Optional[Any] = None, threshold: float = 0.5):
        """
        初始化重要性评分器

        Args:
            llm_client: 可选的 LLM 客户端，用于高级分析
            threshold: 高重要性阈值，默认 0.5
        """
        self.llm_client = llm_client
        self.threshold = threshold

    async def score(self, message: str, context: Optional[Dict] = None) -> ImportanceScore:
        """
        评估消息的重要性分数

        Args:
            message: 消息内容
            context: 可选的上下文信息

        Returns:
            ImportanceScore: 包含总分、各维度分数和原因列表
        """
        dimensions = {}
        reasons = []

        # 1. 关键词触发评分
        keyword_score = self._score_keyword_trigger(message)
        dimensions[ImportanceDimension.KEYWORD_TRIGGER] = keyword_score
        if keyword_score > 0.1:
            reasons.append(f"包含旅行相关关键词 (+{keyword_score:.2f})")

        # 2. 意图明确度评分
        intent_score = self._score_intent_clarity(message)
        dimensions[ImportanceDimension.INTENT_CLARITY] = intent_score
        if intent_score > 0.15:
            reasons.append(f"用户意图明确 (+{intent_score:.2f})")

        # 3. 情感强度评分
        sentiment_score = self._score_sentiment(message)
        dimensions[ImportanceDimension.SENTIMENT] = sentiment_score
        if sentiment_score > 0.1:
            reasons.append(f"情感表达强烈 (+{sentiment_score:.2f})")

        # 4. 决策点评分
        decision_score = self._score_decision_point(message)
        dimensions[ImportanceDimension.DECISION_POINT] = decision_score
        if decision_score > 0.15:
            reasons.append(f"包含关键决策信息 (+{decision_score:.2f})")

        # 5. 用户偏好评分
        preference_score = self._score_user_preference(message)
        dimensions[ImportanceDimension.USER_PREFERENCE] = preference_score
        if preference_score > 0.1:
            reasons.append(f"包含用户偏好信息 (+{preference_score:.2f})")

        # 计算总分
        total_score = sum(dimensions.values())

        # 使用 LLM 进行高级分析（如果可用）
        if self.llm_client and total_score >= 0.3:
            llm_score = await self._llm_advanced_analysis(message, context)
            if llm_score is not None:
                # 综合 LLM 分析结果
                total_score = total_score * 0.7 + llm_score * 0.3
                dimensions[ImportanceDimension.INTENT_CLARITY] = (
                    dimensions.get(ImportanceDimension.INTENT_CLARITY, 0) * 0.5 +
                    llm_score * 0.5
                )

        # 限制总分不超过 1.0
        total_score = min(total_score, 1.0)

        return ImportanceScore(
            total_score=total_score,
            dimensions=dimensions,
            reasons=reasons if reasons else ["一般对话内容"],
            is_high_importance=total_score >= self.threshold
        )

    def _score_keyword_trigger(self, message: str) -> float:
        """关键词触发评分"""
        score = 0.0
        message_lower = message.lower()

        for keyword, weight in self.TRAVEL_KEYWORDS.items():
            if keyword in message:
                score += weight

        return min(score, 0.25)  # 最高 0.25

    def _score_intent_clarity(self, message: str) -> float:
        """意图明确度评分"""
        score = 0.0

        for pattern in self.INTENT_PATTERNS:
            if re.search(pattern, message):
                score += 0.15
                break

        # 检测请求动词
        request_verbs = ["推荐", "建议", "帮忙", "告诉", "介绍", "规划"]
        for verb in request_verbs:
            if verb in message:
                score += 0.08
                break

        return min(score, 0.35)  # 最高 0.35

    def _score_sentiment(self, message: str) -> float:
        """情感强度评分"""
        # 情感强烈的词
        strong_emotion_words = [
            "非常", "特别", "极其", "超级", "太", "好", "棒", "赞",
            "期待", "兴奋", "开心", "喜欢", "想", "要",
            "不喜欢", "讨厌", "失望", "无聊", "累"
        ]

        # 否定词
        negation_words = ["不", "没", "无", "非"]

        score = 0.0
        message_lower = message.lower()

        for word in strong_emotion_words:
            if word in message:
                score += 0.05

        # 检测否定情感
        has_negation = any(neg in message for neg in negation_words)
        if has_negation and score > 0:
            score -= 0.02  # 否定略微降低分数

        return max(min(score, 0.25), 0.0)  # 0-0.25

    def _score_decision_point(self, message: str) -> float:
        """决策点评分"""
        score = 0.0

        # 检测数字相关决策（预算、天数等）
        numbers = re.findall(r'\d+', message)
        if numbers:
            # 有数字且包含单位词
            units = ["天", "元", "块", "千", "百", "周", "月"]
            for unit in units:
                if unit in message:
                    score += 0.12
                    break
            else:
                # 只有数字没有单位
                score += 0.03

        # 检测并列结构（多个要求）
        if "，然后" in message or "，还有" in message or "以及" in message:
            score += 0.10

        # 检测比较级
        comparatives = ["最好", "比较", "更", "最", "第一"]
        for comp in comparatives:
            if comp in message:
                score += 0.05
                break

        return min(score, 0.30)  # 最高 0.30

    def _score_user_preference(self, message: str) -> float:
        """用户偏好评分"""
        score = 0.0

        # 检测偏好表达
        preference_exprs = [
            ("我喜欢", 0.12), ("我想要", 0.10), ("我偏好", 0.15),
            ("我喜欢", 0.12), ("我不喜欢", 0.10), ("讨厌", 0.08),
            ("曾经去过", 0.08), ("已经去过", 0.08)
        ]

        for expr, weight in preference_exprs:
            if expr in message:
                score += weight
                break

        # 检测特定偏好
        preferences = {
            "美食": 0.08, "历史": 0.08, "文化": 0.08,
            "自然": 0.08, "风景": 0.08, "海滩": 0.08,
            "购物": 0.06, "休闲": 0.06, "探险": 0.08
        }

        for pref, weight in preferences.items():
            if pref in message:
                score += weight

        return min(score, 0.25)  # 最高 0.25

    async def _llm_advanced_analysis(
        self,
        message: str,
        context: Optional[Dict] = None
    ) -> Optional[float]:
        """使用 LLM 进行高级分析（可选）"""
        try:
            prompt = f"""分析以下用户消息的重要性分数（0-1）：

消息：{message}

请判断这条消息对理解用户旅行偏好和需求的帮助程度。
只返回分数，不要其他内容。"""

            if self.llm_client:
                result = await self.llm_client.chat([
                    {"role": "system", "content": "你是消息重要性分析助手"},
                    {"role": "user", "content": prompt}
                ])

                if result.get('success'):
                    content = result.get('content', '')
                    # 尝试提取数字
                    match = re.search(r'0?\.?\d+', content)
                    if match:
                        score = float(match.group())
                        return max(min(score, 1.0), 0.0)

            return None
        except Exception as e:
            logger.warning(f"LLM 高级分析失败: {e}")
            return None

    def batch_score(self, messages: List[str]) -> List[ImportanceScore]:
        """
        批量评分（同步版本）

        Args:
            messages: 消息列表

        Returns:
            List[ImportanceScore]: 评分结果列表
        """
        import asyncio
        return asyncio.run(self.batch_score_async(messages))

    async def batch_score_async(
        self,
        messages: List[str]
    ) -> List[ImportanceScore]:
        """
        批量评分（异步版本）

        Args:
            messages: 消息列表

        Returns:
            List[ImportanceScore]: 评分结果列表
        """
        tasks = [self.score(msg) for msg in messages]
        return await asyncio.gather(*tasks)


class PriorityCalculator:
    """
    优先级计算器

    结合重要性和时间计算综合优先级。
    支持多种淘汰策略：
    - FIFO (先进先出)
    - LFU (最不频繁使用)
    - Priority (基于重要性)
    - Hybrid (混合策略)
    """

    def __init__(self, decay_factor: float = 0.95, time_weight: float = 0.3):
        """
        初始化优先级计算器

        Args:
            decay_factor: 时间衰减因子
            time_weight: 时间在优先级中的权重
        """
        self.decay_factor = decay_factor
        self.time_weight = time_weight

    def calculate_priority(
        self,
        importance: float,
        timestamp: str,
        access_count: int = 1,
        strategy: str = "hybrid"
    ) -> float:
        """
        计算综合优先级

        Args:
            importance: 重要性分数 (0-1)
            timestamp: ISO 格式时间戳
            access_count: 访问次数
            strategy: 计算策略

        Returns:
            float: 综合优先级分数
        """
        from datetime import datetime

        try:
            msg_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            age_hours = (datetime.now() - msg_time).total_seconds() / 3600
        except Exception:
            age_hours = 0

        # 时间衰减（越老分数越低）
        time_factor = self.decay_factor ** (age_hours / 24)  # 每天衰减

        if strategy == "fifo":
            # FIFO: 只考虑时间
            return -age_hours

        elif strategy == "lfu":
            # LFU: 考虑访问频率
            return access_count * (1 + importance)

        elif strategy == "priority":
            # Priority: 只考虑重要性
            return importance

        elif strategy == "hybrid":
            # Hybrid: 综合考虑
            importance_weight = 1 - self.time_weight
            priority = (
                importance * importance_weight +
                (1 - time_factor) * self.time_weight
            )
            return priority

        else:
            return importance

    def select_eviction_candidates(
        self,
        memories: List[Dict[str, Any]],
        count: int = 1,
        strategy: str = "hybrid"
    ) -> List[Dict[str, Any]]:
        """
        选择需要淘汰的记忆候选

        Args:
            memories: 记忆列表，每项包含 importance, timestamp, access_count
            count: 需要淘汰的数量
            strategy: 选择策略

        Returns:
            List[Dict]: 需要淘汰的记忆列表
        """
        if not memories:
            return []

        # 计算每个记忆的优先级
        for mem in memories:
            mem['_priority_score'] = self.calculate_priority(
                importance=mem.get('importance', 0.5),
                timestamp=mem.get('timestamp', ''),
                access_count=mem.get('access_count', 1),
                strategy=strategy
            )

        # 按优先级排序（低优先级的先淘汰）
        sorted_memories = sorted(
            memories,
            key=lambda x: x.get('_priority_score', 0)
        )

        return sorted_memories[:count]
