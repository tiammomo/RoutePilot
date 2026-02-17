"""
用户画像存储 (User Profile Store)

结构化存储用户偏好和历史交互数据，支持高效的查询和更新。
用于长期记忆管理，快速获取用户特征。

功能特点:
- 结构化用户画像
- 偏好自动学习
- 旅行历史记录
- 兴趣标签管理
- 数据持久化支持

使用示例:
    store = UserProfileStore()
    profile = store.get_or_create("user_123")
    store.update_preference("user_123", "budget_range", (3000, 5000))
    prefs = store.get_preferences("user_123")
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PreferenceType(Enum):
    """偏好类型"""
    BUDGET = "budget"
    DURATION = "duration"
    DESTINATION = "destination"
    SEASON = "season"
    COMPANION = "companion"
    STYLE = "style"
    INTEREST = "interest"
    DIET = "diet"
    ACCOMMODATION = "accommodation"
    TRANSPORT = "transport"


@dataclass
class UserPreference:
    """用户偏好"""
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    budget_explanation: Optional[str] = None

    duration_days: Optional[int] = None
    duration_preference: Optional[str] = None  # 短途/长途

    favorite_regions: List[str] = field(default_factory=list)
    favorite_cities: List[str] = field(default_factory=list)
    avoided_cities: List[str] = field(default_factory=list)

    preferred_seasons: List[str] = field(default_factory=list)  # 春/夏/秋/冬
    travel_time_preference: Optional[str] = None  # 节假日/平日

    travel_companion: Optional[str] = None  # solo/couple/family/friends
    companion_notes: Optional[str] = None

    travel_style: Optional[str] = None  # 深度游/打卡游/休闲游
    pace_preference: Optional[str] = None  # 紧凑/适中/悠闲

    interest_tags: List[str] = field(default_factory=list)
    interest_weights: Dict[str, float] = field(default_factory=dict)  # 兴趣权重

    dietary_restrictions: List[str] = field(default_factory=list)
    food_preferences: List[str] = field(default_factory=list)
    cuisine_types: List[str] = field(default_factory=list)

    accommodation_type: Optional[str] = None  # 酒店/民宿/青旅
    accommodation_level: Optional[str] = None  # 豪华/舒适/经济

    transport_preference: Optional[str] = None  # 飞机/火车/自驾
    transport_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def merge(self, other: 'UserPreference') -> 'UserPreference':
        """合并另一个偏好"""
        merged = UserPreference()

        # 数值取更精确的
        if other.budget_min:
            merged.budget_min = min(
                self.budget_min or other.budget_min,
                other.budget_min
            )
        else:
            merged.budget_min = self.budget_min

        if other.budget_max:
            merged.budget_max = max(
                self.budget_max or other.budget_max,
                other.budget_max
            )
        else:
            merged.budget_max = self.budget_max

        # 列表合并（去重）
        merged.favorite_regions = list(set(self.favorite_regions + other.favorite_regions))
        merged.favorite_cities = list(set(self.favorite_cities + other.favorite_cities))
        merged.avoided_cities = list(set(self.avoided_cities + other.avoided_cities))
        merged.preferred_seasons = list(set(self.preferred_seasons + other.preferred_seasons))
        merged.interest_tags = list(set(self.interest_tags + other.interest_tags))

        # 单值取最新的
        merged.duration_days = other.duration_days or self.duration_days
        merged.travel_companion = other.travel_companion or self.travel_companion
        merged.travel_style = other.travel_style or self.travel_style
        merged.accommodation_type = other.accommodation_type or self.accommodation_type

        return merged

    def get_summary(self) -> str:
        """获取偏好摘要"""
        parts = []

        if self.budget_min and self.budget_max:
            parts.append(f"预算: {self.budget_min}-{self.budget_max}元/天")
        elif self.budget_min:
            parts.append(f"预算: ≥{self.budget_min}元/天")
        elif self.budget_max:
            parts.append(f"预算: ≤{self.budget_max}元/天")

        if self.duration_days:
            parts.append(f"天数: {self.duration_days}天")

        if self.favorite_cities:
            parts.append(f"偏好城市: {', '.join(self.favorite_cities[:3])}")

        if self.interest_tags:
            parts.append(f"兴趣: {', '.join(self.interest_tags[:3])}")

        return " | ".join(parts) if parts else "暂无偏好信息"


@dataclass
class TravelHistory:
    """旅行历史"""
    session_id: str
    destination: str
    duration_days: int
    budget: Optional[str] = None
    rating: Optional[int] = None  # 1-5
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    preferences: UserPreference = field(default_factory=UserPreference)
    travel_history: List[TravelHistory] = field(default_factory=list)
    interaction_count: int = 0
    last_interaction: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    profile_version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "preferences": self.preferences.to_dict(),
            "travel_history": [th.to_dict() for th in self.travel_history],
            "interaction_count": self.interaction_count,
            "last_interaction": self.last_interaction,
            "created_at": self.created_at,
            "profile_version": self.profile_version,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        prefs_data = data.get('preferences', {})
        preferences = UserPreference(**prefs_data) if prefs_data else UserPreference()

        travel_history = [
            TravelHistory(**th) for th in data.get('travel_history', [])
        ]

        return cls(
            user_id=data.get('user_id', ''),
            preferences=preferences,
            travel_history=travel_history,
            interaction_count=data.get('interaction_count', 0),
            last_interaction=data.get('last_interaction', datetime.now().isoformat()),
            created_at=data.get('created_at', datetime.now().isoformat()),
            profile_version=data.get('profile_version', 1),
            metadata=data.get('metadata', {})
        )


class UserProfileStore:
    """
    用户画像存储

    提供用户画像的增删改查功能：
    - 创建/获取用户画像
    - 更新用户偏好
    - 记录旅行历史
    - 合并偏好（从会话中学习）
    - 画像持久化
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        初始化用户画像存储

        Args:
            storage_path: 可选的存储文件路径
        """
        self.storage_path = storage_path
        self._profiles: Dict[str, UserProfile] = {}
        self._load_from_storage()

    def get_or_create(self, user_id: str) -> UserProfile:
        """
        获取或创建用户画像

        Args:
            user_id: 用户 ID

        Returns:
            UserProfile: 用户画像
        """
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)
            logger.info(f"创建新用户画像: {user_id}")

        return self._profiles[user_id]

    def get(self, user_id: str) -> Optional[UserProfile]:
        """
        获取用户画像

        Args:
            user_id: 用户 ID

        Returns:
            Optional[UserProfile]: 用户画像，不存在返回 None
        """
        return self._profiles.get(user_id)

    def update_preference(
        self,
        user_id: str,
        preference_type: str,
        value: Any
    ) -> bool:
        """
        更新单个偏好

        Args:
            user_id: 用户 ID
            preference_type: 偏好类型
            value: 偏好值

        Returns:
            bool: 是否更新成功
        """
        profile = self.get(user_id)
        if not profile:
            return False

        prefs = profile.preferences

        # 映射偏好类型到属性
        type_mapping = {
            "budget_min": "budget_min",
            "budget_max": "budget_max",
            "budget": "budget_explanation",
            "duration": "duration_days",
            "days": "duration_days",
            "city": "favorite_cities",
            "cities": "favorite_cities",
            "region": "favorite_regions",
            "season": "preferred_seasons",
            "companion": "travel_companion",
            "style": "travel_style",
            "interest": "interest_tags",
            "food": "food_preferences",
            "accommodation": "accommodation_type",
            "transport": "transport_preference"
        }

        attr = type_mapping.get(preference_type)
        if not attr:
            logger.warning(f"未知的偏好类型: {preference_type}")
            return False

        # 处理不同类型的值
        current_value = getattr(prefs, attr)

        if isinstance(current_value, list):
            # 列表类型：追加
            if isinstance(value, list):
                new_value = list(set(current_value + value))
            else:
                new_value = list(set(current_value + [value]))
            setattr(prefs, attr, new_value)
        else:
            # 单值类型：直接设置
            setattr(prefs, attr, value)

        profile.interaction_count += 1
        profile.last_interaction = datetime.now().isoformat()
        profile.profile_version += 1

        self._save_to_storage()
        return True

    def merge_preferences(
        self,
        user_id: str,
        session_preferences: Dict[str, Any]
    ) -> bool:
        """
        从会话偏好合并到用户画像

        Args:
            user_id: 用户 ID
            session_preferences: 会话中提取的偏好

        Returns:
            bool: 是否合并成功
        """
        profile = self.get(user_id)
        if not profile:
            return False

        # 转换为 UserPreference 对象
        session_prefs = UserPreference(
            budget_min=session_preferences.get('budget_range', [None, None])[0],
            budget_max=session_preferences.get('budget_range', [None, None])[1],
            duration_days=session_preferences.get('travel_days'),
            favorite_cities=session_preferences.get('preferred_cities', []),
            preferred_seasons=[session_preferences.get('season_preference')] if session_preferences.get('season_preference') else [],
            interest_tags=session_preferences.get('interest_tags', []),
            travel_companion=session_preferences.get('travel_companions')
        )

        # 合并偏好
        profile.preferences = profile.preferences.merge(session_prefs)
        profile.interaction_count += 1
        profile.last_interaction = datetime.now().isoformat()
        profile.profile_version += 1

        self._save_to_storage()
        return True

    def add_travel_history(
        self,
        user_id: str,
        history: TravelHistory
    ) -> bool:
        """
        添加旅行历史

        Args:
            user_id: 用户 ID
            history: 旅行历史

        Returns:
            bool: 是否添加成功
        """
        profile = self.get(user_id)
        if not profile:
            return False

        profile.travel_history.append(history)

        # 更新偏好
        if history.destination:
            if history.destination not in profile.preferences.favorite_cities:
                profile.preferences.favorite_cities.append(history.destination)

        if history.rating and history.rating >= 4:
            # 高评价目的地加入偏好
            if history.destination not in profile.preferences.favorite_cities:
                profile.preferences.favorite_cities.append(history.destination)

        profile.interaction_count += 1
        profile.last_interaction = datetime.now().isoformat()

        self._save_to_storage()
        return True

    def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户偏好（字典格式）

        Args:
            user_id: 用户 ID

        Returns:
            Dict: 偏好字典
        """
        profile = self.get(user_id)
        if not profile:
            return {}

        return profile.preferences.to_dict()

    def get_travel_history(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[TravelHistory]:
        """
        获取用户旅行历史

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            List[TravelHistory]: 旅行历史列表
        """
        profile = self.get(user_id)
        if not profile:
            return []

        return profile.travel_history[-limit:]

    def get_context_for_llm(self, user_id: str) -> str:
        """
        获取供 LLM 使用的上下文信息

        Args:
            user_id: 用户 ID

        Returns:
            str: 格式化的上下文信息
        """
        profile = self.get(user_id)
        if not profile:
            return "用户无历史偏好信息"

        prefs = profile.preferences
        parts = ["【用户偏好】"]

        if prefs.budget_min or prefs.budget_max:
            budget_str = ""
            if prefs.budget_min:
                budget_str += f"预算 ≥ {prefs.budget_min}元"
            if prefs.budget_max:
                budget_str += f"预算 ≤ {prefs.budget_max}元"
            parts.append(budget_str)

        if prefs.duration_days:
            parts.append(f"偏好天数: {prefs.duration_days}天")

        if prefs.favorite_cities:
            parts.append(f"偏好城市: {', '.join(prefs.favorite_cities[:3])}")

        if prefs.interest_tags:
            parts.append(f"兴趣标签: {', '.join(prefs.interest_tags[:3])}")

        if prefs.travel_style:
            parts.append(f"旅行风格: {prefs.travel_style}")

        if prefs.travel_companion:
            parts.append(f"出行同伴: {prefs.travel_companion}")

        return "\n".join(parts)

    def delete(self, user_id: str) -> bool:
        """
        删除用户画像

        Args:
            user_id: 用户 ID

        Returns:
            bool: 是否删除成功
        """
        if user_id in self._profiles:
            del self._profiles[user_id]
            self._save_to_storage()
            return True
        return False

    def get_all_user_ids(self) -> List[str]:
        """
        获取所有用户 ID

        Returns:
            List[str]: 用户 ID 列表
        """
        return list(self._profiles.keys())

    def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            Dict: 统计信息
        """
        total_users = len(self._profiles)
        total_interactions = sum(
            p.interaction_count for p in self._profiles.values()
        )
        total_history = sum(
            len(p.travel_history) for p in self._profiles.values()
        )

        return {
            "total_users": total_users,
            "total_interactions": total_interactions,
            "total_travel_history": total_history,
            "avg_interactions_per_user": total_interactions / max(total_users, 1)
        }

    def _save_to_storage(self) -> None:
        """保存到存储文件"""
        if not self.storage_path:
            return

        try:
            data = {
                user_id: profile.to_dict()
                for user_id, profile in self._profiles.items()
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户画像失败: {e}")

    def _load_from_storage(self) -> None:
        """从存储文件加载"""
        if not self.storage_path:
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for user_id, profile_data in data.items():
                self._profiles[user_id] = UserProfile.from_dict(profile_data)
            logger.info(f"加载用户画像: {len(self._profiles)} 个用户")
        except FileNotFoundError:
            logger.info("用户画像存储文件不存在，将创建新文件")
        except Exception as e:
            logger.error(f"加载用户画像失败: {e}")

    def export_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        导出用户画像

        Args:
            user_id: 用户 ID

        Returns:
            Optional[Dict]: 画像数据，不存在返回 None
        """
        profile = self.get(user_id)
        if profile:
            return profile.to_dict()
        return None

    def import_profile(self, data: Dict[str, Any]) -> bool:
        """
        导入用户画像

        Args:
            data: 画像数据

        Returns:
            bool: 是否导入成功
        """
        try:
            profile = UserProfile.from_dict(data)
            self._profiles[profile.user_id] = profile
            self._save_to_storage()
            return True
        except Exception as e:
            logger.error(f"导入用户画像失败: {e}")
            return False
