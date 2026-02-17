"""
记忆/状态管理模块 (Memory Manager)

本模块提供Agent的记忆管理功能，包括短期工作记忆和长期记忆的存储与检索。
采用双层记忆架构：工作记忆用于当前会话，长期记忆用于历史会话存档。

主要组件:
- Message: 对话消息数据类
- UserPreference: 用户偏好数据类
- MemoryManager: 记忆管理器核心类

功能特点:
- 工作记忆：限制长度的对话历史
- 长期记忆：历史会话存档和检索
- 用户偏好提取：从对话中自动提取用户偏好
- 会话存档：自动归档完成的会话
- 文件持久化：支持保存和加载记忆数据

使用示例:
    from memory.manager import MemoryManager

    # 创建记忆管理器
    memory = MemoryManager(max_working_memory=10, max_long_term_memory=50)

    # 添加对话消息
    memory.add_message('user', '我想去北京旅游')
    memory.add_message('assistant', '北京有很多历史文化景点')

    # 获取对话历史
    history = memory.get_conversation_history()

    # 获取用户偏好
    preferences = memory.get_user_preference()

    # 存档当前会话
    memory.archive_current_session()

    # 保存到文件
    memory.save_to_file('memory.json')
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class Message:
    """
    对话消息数据类

    表示一条对话消息，包含角色、内容和时间戳。

    属性:
        role: str 消息角色，'user'或'assistant'
        content: str 消息内容
        timestamp: str 时间戳，ISO格式
    """

    def __init__(self, role: str, content: str, timestamp: Optional[str] = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Message':
        """从字典创建Message实例"""
        return cls(data['role'], data['content'], data.get('timestamp'))


class UserPreference:
    """
    用户偏好数据类

    存储用户的旅行偏好信息，支持从对话文本中自动提取偏好。

    提取的偏好类型:
        - budget_range: 预算范围 (min, max)
        - travel_days: 旅行天数
        - interest_tags: 兴趣标签列表
        - preferred_cities: 偏好城市列表
        - season_preference: 季节偏好
        - travel_companions: 旅行同伴

    提取规则:
        - 预算: 识别"元"、"块"和数字
        - 天数: 识别"X天"模式
        - 兴趣: 识别关键词映射到标准标签
    """

    def __init__(self):
        self.budget_range: Optional[tuple] = None
        self.travel_days: Optional[int] = None
        self.interest_tags: List[str] = []
        self.preferred_cities: List[str] = []
        self.season_preference: Optional[str] = None
        self.travel_companions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "budget_range": self.budget_range,
            "travel_days": self.travel_days,
            "interest_tags": self.interest_tags,
            "preferred_cities": self.preferred_cities,
            "season_preference": self.season_preference,
            "travel_companions": self.travel_companions
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """从字典加载偏好"""
        self.budget_range = tuple(data['budget_range']) if data.get('budget_range') else None
        self.travel_days = data.get('travel_days')
        self.interest_tags = data.get('interest_tags', [])
        self.preferred_cities = data.get('preferred_cities', [])
        self.season_preference = data.get('season_preference')
        self.travel_companions = data.get('travel_companions')

    def update_from_text(self, text: str) -> None:
        """
        从文本中提取用户偏好

        扫描文本内容，提取旅行相关的偏好信息并更新。

        Args:
            text: str 用户输入文本
        """
        text_lower = text.lower()

        # 提取预算
        if '预算' in text or '元' in text or '块' in text:
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                nums = [int(n) for n in numbers]
                if len(nums) >= 2:
                    self.budget_range = (min(nums), max(nums))
                elif len(nums) == 1:
                    self.budget_range = (0, nums[0])

        # 提取天数
        if '天' in text:
            import re
            match = re.search(r'(\d+)\s*天', text)
            if match:
                self.travel_days = int(match.group(1))

        # 提取兴趣标签
        interest_keywords = {
            '历史': '历史文化',
            '文化': '历史文化',
            '自然': '自然风光',
            '风景': '自然风光',
            '美食': '美食',
            '海边': '海滨度假',
            '海滨': '海滨度假',
            '购物': '现代都市',
            '休闲': '休闲养生'
        }
        for keyword, tag in interest_keywords.items():
            if keyword in text and tag not in self.interest_tags:
                self.interest_tags.append(tag)


class MemoryManager:
    """
    记忆管理器核心类

    负责管理Agent的工作记忆和长期记忆，实现对话历史的存储、
    用户偏好的提取、会话的存档和检索等功能。

    记忆层次结构:
    1. 工作记忆 (Working Memory)
       - conversation_history: 对话历史（固定长度deque）
       - user_preference: 用户偏好（自动从对话提取）
       - session_state: 会话状态（当前会话的上下文）

    2. 长期记忆 (Long-term Memory)
       - long_term_memory: 已存档的会话列表
       - 支持持久化到文件

    工作流程:
    1. 收到消息后添加到对话历史
    2. 如果是用户消息，自动提取偏好
    3. 对话历史超过限制时自动淘汰旧消息
    4. 存档时保存完整会话信息
    """

    def __init__(self, max_working_memory: int = 10, max_long_term_memory: int = 50):
        """
        初始化记忆管理器

        Args:
            max_working_memory: int 工作记忆最大消息数
            max_long_term_memory: int 长期记忆最大存档数
        """
        self.max_working_memory = max_working_memory
        self.max_long_term_memory = max_long_term_memory

        # 工作记忆：对话历史（固定长度deque）
        self.conversation_history: deque = deque(maxlen=max_working_memory)

        # 用户偏好
        self.user_preference = UserPreference()

        # 会话状态
        self.session_state: Dict[str, Any] = {
            "session_id": f"session_{int(time.time())}",
            "start_time": datetime.now().isoformat(),
            "last_recommended_cities": [],
            "last_recommended_attractions": [],
            "current_plan": None
        }

        # 长期记忆：已存档的会话列表
        self.long_term_memory: List[Dict[str, Any]] = []

    def add_message(self, role: str, content: str) -> None:
        """
        添加对话消息

        Args:
            role: str 消息角色，'user'或'assistant'
            content: str 消息内容
        """
        message = Message(role, content)
        self.conversation_history.append(message)

        # 如果是用户消息，自动提取偏好
        if role == 'user':
            self.user_preference.update_from_text(content)

    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """
        获取对话历史

        Args:
            limit: int 可选，返回最近N条消息

        Returns:
            List[Dict]: 消息列表
        """
        history = list(self.conversation_history)
        if limit:
            history = history[-limit:]
        return [msg.to_dict() for msg in history]

    def get_messages_for_llm(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """
        获取发送给LLM的消息格式

        转换为LLM API所需的格式（仅role和content）。

        Args:
            limit: int 可选，返回最近N条消息

        Returns:
            List[Dict]: 消息列表 [{'role': '...', 'content': '...'}]
        """
        history = self.get_conversation_history(limit)
        return [{"role": msg['role'], "content": msg['content']} for msg in history]

    def update_session_state(self, key: str, value: Any) -> None:
        """
        更新会话状态

        Args:
            key: str 状态键
            value: Any 状态值
        """
        self.session_state[key] = value

    def get_session_state(self, key: str, default: Any = None) -> Any:
        """
        获取会话状态

        Args:
            key: str 状态键
            default: Any 默认值

        Returns:
            Any: 状态值
        """
        return self.session_state.get(key, default)

    def clear_conversation(self, archive: bool = True) -> None:
        """
        清除对话历史

        Args:
            archive: bool 是否先存档当前会话
        """
        if archive:
            self._archive_session()

        self.conversation_history.clear()
        self.session_state['session_id'] = f"session_{int(time.time())}"
        self.session_state['start_time'] = datetime.now().isoformat()

    def _archive_session(self) -> None:
        """归档当前会话到长期记忆"""
        messages = self.get_conversation_history()
        session_state = self.session_state.copy()
        user_preference = self.user_preference.to_dict()

        summary = self._generate_session_summary(messages, session_state)

        archive_record = {
            'session_id': session_state.get('session_id'),
            'start_time': session_state.get('start_time'),
            'end_time': datetime.now().isoformat(),
            'message_count': len(messages),
            'summary': summary,
            'user_preference': user_preference,
            'session_state': {
                'last_recommended_cities': session_state.get('last_recommended_cities', []),
                'last_recommended_attractions': session_state.get('last_recommended_attractions', []),
                'current_plan': session_state.get('current_plan')
            },
            'messages': messages
        }

        self.long_term_memory.append(archive_record)

        # 限制长期记忆大小
        while len(self.long_term_memory) > self.max_long_term_memory:
            self.long_term_memory.pop(0)

    def _generate_session_summary(self, messages: List[Dict], session_state: Dict) -> str:
        """
        生成会话摘要

        Args:
            messages: List[Dict] 消息列表
            session_state: Dict 会话状态

        Returns:
            str: 会话摘要字符串
        """
        summary_parts = []

        user_messages = [m for m in messages if m.get('role') == 'user']
        if user_messages:
            summary_parts.append(f"用户消息数: {len(user_messages)}")

        recommended_cities = session_state.get('last_recommended_cities', [])
        if recommended_cities:
            summary_parts.append(f"推荐城市: {', '.join(recommended_cities[:5])}")

        current_plan = session_state.get('current_plan')
        if current_plan:
            route_plan = current_plan.get('route_plan', [])
            if route_plan:
                summary_parts.append(f"已规划路线")

        return " | ".join(summary_parts) if summary_parts else "一般对话"

    def archive_current_session(self) -> Dict[str, Any]:
        """
        归档当前会话

        Returns:
            Dict: 归档的会话记录
        """
        self._archive_session()
        return self.long_term_memory[-1] if self.long_term_memory else {}

    def get_archived_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取已存档的会话列表

        Args:
            limit: int 返回的最大数量

        Returns:
            List[Dict]: 会话摘要列表
        """
        archives = []
        for record in reversed(self.long_term_memory[-limit:]):
            archives.append({
                'session_id': record['session_id'],
                'start_time': record['start_time'],
                'end_time': record['end_time'],
                'message_count': record['message_count'],
                'summary': record['summary']
            })
        return archives

    def get_archive_detail(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取存档会话详情

        Args:
            session_id: str 会话ID

        Returns:
            Optional[Dict]: 会话详情，不存在返回None
        """
        for record in self.long_term_memory:
            if record['session_id'] == session_id:
                return record
        return None

    def get_long_term_memory(self) -> List[Dict[str, Any]]:
        """
        获取所有长期记忆

        Returns:
            List[Dict]: 长期记忆列表
        """
        return self.long_term_memory

    def set_long_term_memory(self, memory: List[Dict[str, Any]]) -> None:
        """
        设置长期记忆

        Args:
            memory: List[Dict] 记忆列表
        """
        self.long_term_memory = memory[-self.max_long_term_memory:]

    def get_user_preference(self) -> Dict[str, Any]:
        """
        获取用户偏好

        Returns:
            Dict: 用户偏好字典
        """
        return self.user_preference.to_dict()

    def set_user_preference(self, preference_data: Dict[str, Any]) -> None:
        """
        设置用户偏好

        Args:
            preference_data: Dict 偏好数据
        """
        self.user_preference.from_dict(preference_data)

    def save_to_file(self, filepath: str) -> None:
        """
        保存记忆到文件

        Args:
            filepath: str 文件路径
        """
        data = {
            "session_state": self.session_state,
            "conversation_history": self.get_conversation_history(),
            "user_preference": self.user_preference.to_dict(),
            "long_term_memory": self.long_term_memory
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_from_file(self, filepath: str) -> bool:
        """
        从文件加载记忆

        Args:
            filepath: str 文件路径

        Returns:
            bool: 是否加载成功
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.session_state = data.get('session_state', {})

            self.conversation_history.clear()
            for msg_data in data.get('conversation_history', []):
                msg = Message.from_dict(msg_data)
                self.conversation_history.append(msg)

            self.user_preference.from_dict(data.get('user_preference', {}))

            self.long_term_memory = data.get('long_term_memory', [])

            return True
        except Exception as e:
            logger.error(f"加载记忆失败: {e}")
            return False

    def get_context_summary(self) -> str:
        """
        获取上下文摘要

        用于展示当前用户偏好和会话状态的简洁摘要。

        Returns:
            str: 格式化的摘要字符串
        """
        summary_parts = []

        pref = self.user_preference
        if pref.budget_range:
            summary_parts.append(f"预算范围：{pref.budget_range[0]}-{pref.budget_range[1]}元/天")
        if pref.travel_days:
            summary_parts.append(f"旅行天数：{pref.travel_days}天")
        if pref.interest_tags:
            summary_parts.append(f"兴趣偏好：{', '.join(pref.interest_tags)}")
        if pref.preferred_cities:
            summary_parts.append(f"偏好城市：{', '.join(pref.preferred_cities)}")

        if self.session_state.get('last_recommended_cities'):
            summary_parts.append(f"已推荐城市：{', '.join(self.session_state['last_recommended_cities'])}")

        return "\n".join(summary_parts) if summary_parts else "暂无用户偏好信息"

    # ==========================================================================
    # 增强功能集成（v2.0）
    # ==========================================================================

    def get_enhanced_conversation_history(
        self,
        limit: Optional[int] = None,
        include_importance: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取增强版对话历史（包含重要性评分）

        Args:
            limit: 可选，返回最近N条消息
            include_importance: 是否包含重要性评分

        Returns:
            List[Dict]: 消息列表（包含 importance 字段）
        """
        history = list(self.conversation_history)
        if limit:
            history = history[-limit:]

        result = []
        for i, msg in enumerate(history):
            msg_dict = msg.to_dict()

            if include_importance:
                # 根据位置计算重要性
                importance = self._calculate_message_importance(msg_dict, i, len(history))
                msg_dict['importance'] = importance

            result.append(msg_dict)

        return result

    def _calculate_message_importance(
        self,
        message: Dict,
        position: int,
        total: int
    ) -> float:
        """计算单条消息的重要性分数"""
        base_importance = 0.5

        # 用户消息略高
        if message.get('role') == 'user':
            base_importance += 0.1

        # 最近的消息略高
        recency_boost = (position / total) * 0.2
        base_importance += recency_boost

        # 检查是否包含关键词
        content = message.get('content', '').lower()
        keywords = ['预算', '喜欢', '计划', '决定', '偏好']
        for kw in keywords:
            if kw in content:
                base_importance += 0.05
                break

        return min(base_importance, 1.0)

    def archive_with_enhanced_summary(
        self,
        session_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        增强版存档（生成更详细的摘要）

        Args:
            session_data: 可选的额外会话数据

        Returns:
            Dict: 存档记录
        """
        messages = self.get_enhanced_conversation_history()
        session_state = self.session_state.copy()
        user_preference = self.user_preference.to_dict()

        # 生成增强摘要
        summary = self._generate_enhanced_summary(messages, session_state)

        archive_record = {
            'session_id': session_state.get('session_id'),
            'start_time': session_state.get('start_time'),
            'end_time': datetime.now().isoformat(),
            'message_count': len(messages),
            'summary': summary,
            'user_preference': user_preference,
            'enhanced_data': {
                'avg_importance': self._calculate_avg_importance(messages),
                'topics': self._extract_topics(messages),
                'key_decisions': self._extract_decisions(messages),
                'session_state': {
                    'last_recommended_cities': session_state.get('last_recommended_cities', []),
                    'last_recommended_attractions': session_state.get('last_recommended_attractions', []),
                    'current_plan': session_state.get('current_plan')
                }
            },
            'messages': messages
        }

        # 添加额外会话数据
        if session_data:
            archive_record.update(session_data)

        self.long_term_memory.append(archive_record)

        # 限制长期记忆大小
        while len(self.long_term_memory) > self.max_long_term_memory:
            self.long_term_memory.pop(0)

        return archive_record

    def _generate_enhanced_summary(
        self,
        messages: List[Dict],
        session_state: Dict
    ) -> str:
        """生成增强摘要"""
        parts = []

        # 用户消息统计
        user_msgs = [m for m in messages if m.get('role') == 'user']
        if user_msgs:
            parts.append(f"用户消息数: {len(user_msgs)}")

        # 关键信息
        recommended_cities = session_state.get('last_recommended_cities', [])
        if recommended_cities:
            parts.append(f"推荐城市: {', '.join(recommended_cities[:3])}")

        current_plan = session_state.get('current_plan')
        if current_plan:
            parts.append(f"已规划路线: 是")

        return " | ".join(parts) if parts else "一般对话"

    def _calculate_avg_importance(self, messages: List[Dict]) -> float:
        """计算平均重要性"""
        if not messages:
            return 0.5

        importances = [m.get('importance', 0.5) for m in messages]
        return sum(importances) / len(importances)

    def _extract_topics(self, messages: List[Dict]) -> List[str]:
        """提取主题"""
        topics = set()
        content_all = " ".join(m.get('content', '') for m in messages).lower()

        topic_keywords = {
            "城市推荐": ["城市", "推荐", "景点"],
            "行程规划": ["行程", "计划", "路线", "天"],
            "预算": ["预算", "花费", "钱"],
            "交通": ["交通", "怎么去", "飞机", "火车"],
            "住宿": ["住宿", "酒店", "民宿"]
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in content_all for kw in keywords):
                topics.add(topic)

        return list(topics)

    def _extract_decisions(self, messages: List[Dict]) -> List[str]:
        """提取决策点"""
        decisions = []
        for msg in messages:
            content = msg.get('content', '')
            if any(kw in content for kw in ['决定', '选择', "就这个", "好的"]):
                decisions.append(content[:50])

        return decisions

    def get_compressed_context(
        self,
        max_tokens: int = 2000
    ) -> List[Dict[str, str]]:
        """
        获取压缩后的上下文（用于 LLM）

        根据 token 限制自动压缩对话历史。

        Args:
            max_tokens: 最大 token 数

        Returns:
            List[Dict]: 压缩后的消息列表
        """
        history = self.get_conversation_history()

        # 估算当前 token 消耗
        current_tokens = self._estimate_tokens(history)

        if current_tokens <= max_tokens:
            return history

        # 需要压缩
        compressed = []

        # 1. 保留系统消息（如果有）
        system_msgs = [m for m in history if m.get('role') == 'system']
        compressed.extend(system_msgs)

        # 2. 保留最近的消息
        remaining_tokens = max_tokens - self._estimate_tokens(system_msgs)
        recent_msgs = history[-10:]  # 最多保留最近10条

        # 3. 压缩早期消息为摘要
        early_msgs = history[:-10] if len(history) > 10 else []
        if early_msgs:
            summary = self._compress_early_messages(early_msgs)
            compressed.append({
                "role": "system",
                "content": f"[历史对话摘要] {summary}"
            })

        compressed.extend(recent_msgs)

        return compressed

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """估算 token 数量"""
        total = 0
        for msg in messages:
            total += len(msg.get('role', '')) + len(msg.get('content', ''))
        return int(total / 1.5)  # 粗略估计：1.5 字/token

    def _compress_early_messages(self, messages: List[Dict]) -> str:
        """压缩早期消息为摘要"""
        user_msgs = [m.get('content', '') for m in messages if m.get('role') == 'user']

        if not user_msgs:
            return "早期对话"

        # 提取关键信息
        keywords = set()
        for msg in user_msgs:
            for kw in ['预算', '天数', '城市', '喜欢', '计划']:
                if kw in msg:
                    keywords.add(kw)

        if keywords:
            return f"讨论了{'、'.join(keywords)}相关的内容"
        return f"共 {len(user_msgs)} 条用户消息"

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆系统统计信息

        Returns:
            Dict: 统计信息
        """
        return {
            "working_memory": {
                "current_size": len(self.conversation_history),
                "max_size": self.max_working_memory,
                "usage_ratio": len(self.conversation_history) / max(self.max_working_memory, 1)
            },
            "long_term_memory": {
                "current_size": len(self.long_term_memory),
                "max_size": self.max_long_term_memory,
                "usage_ratio": len(self.long_term_memory) / max(self.max_long_term_memory, 1)
            },
            "user_preference": self.user_preference.to_dict(),
            "session_info": {
                "session_id": self.session_state.get('session_id'),
                "start_time": self.session_state.get('start_time')
            }
        }

    def clear_all_data(self) -> None:
        """清除所有记忆数据（谨慎使用）"""
        self.conversation_history.clear()
        self.long_term_memory.clear()
        self.user_preference = UserPreference()
        self.session_state = {
            "session_id": f"session_{int(datetime.now().timestamp())}",
            "start_time": datetime.now().isoformat(),
            "last_recommended_cities": [],
            "last_recommended_attractions": [],
            "current_plan": None
        }
