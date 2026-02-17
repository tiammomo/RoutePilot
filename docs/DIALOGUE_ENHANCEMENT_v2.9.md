# v2.9.0 对话增强设计

## 概述

v2.9.0 聚焦于提升对话质量，实现更自然的多轮对话和更好的上下文理解。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        TravelAgent                               │
│                                                                  │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────┐ │
│  │ DialoguePolicy │←──→│ ContextTracker │←──→│EntityLinker│ │
│  └────────────────┘    └────────────────┘    └────────────┘ │
│           ↑                                                        │
│           │                                                        │
│  ┌───────┴──────────────────────────────────────────────────┐   │
│  │                    Dialogue System                         │   │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────────┐    │   │
│  │  │  Intent  │  │  Entity  │  │    Dialogue     │    │   │
│  │  │Clarifier │  │ Extractor │  │     State       │    │   │
│  │  └──────────┘  └──────────┘  └───────────────────┘    │   │
│  └────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 模块设计

### 1. DialoguePolicy

**文件**: `agent/src/core/dialogue_policy.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DialogueAction(Enum):
    """对话动作"""
    RESPOND = "respond"           # 直接回复
    CLARIFY = "clarify"           # 澄清意图
    CONFIRM = "confirm"            # 确认信息
    ASK_MORE = "ask_more"          # 询问更多信息
    CHITCHAT = "chitchat"          # 闲聊
    END_SESSION = "end_session"   # 结束会话


class DialogueState(Enum):
    """对话状态"""
    INITIAL = "initial"           # 初始
    UNDERSTANDING = "understanding" # 理解中
    EXECUTING = "executing"       # 执行中
    RESPONDING = "responding"     # 回复中
    WAITING_CLARIFICATION = "waiting_clarification"  # 等待澄清
    COMPLETED = "completed"       # 完成


@dataclass
class ClarificationRequest:
    """澄清请求"""
    param_name: str
    question: str
    options: List[str] = field(default_factory=list)
    required: bool = True


@dataclass
class DialogueContext:
    """对话上下文"""
    session_id: str
    user_id: str
    state: DialogueState = DialogueState.INITIAL
    current_intent: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)
    missing_params: List[str] = field(default_factory=list)
    clarifications: List[ClarificationRequest] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DialoguePolicy:
    """对话策略管理器

    特性：
    - 动作选择策略
    - 意图澄清判断
    - 对话状态管理
    - 闲聊触发
    """

    # 闲聊触发关键词
    CHITCHAT_TRIGGERS = {
        "你好", "hello", "hi",
        "天气", "今天", "最近",
        "谢谢", "再见", "bye"
    }

    # 需要澄清的意图
    INTENT_REQUIRES_CLARIFICATION = {
        "plan_trip": ["destination", "dates"],
        "book_hotel": ["checkin", "checkout"],
        "find_restaurant": ["cuisine", "budget"]
    }

    def __init__(self):
        self._contexts: Dict[str, DialogueContext] = {}
        logger.info("DialoguePolicy initialized")

    def get_context(self, session_id: str) -> DialogueContext:
        """获取对话上下文"""
        if session_id not in self._contexts:
            self._contexts[session_id] = DialogueContext(
                session_id=session_id,
                user_id=""
            )
        return self._contexts[session_id]

    def select_action(
        self,
        context: DialogueContext,
        intent: Optional[str] = None,
        entities: Optional[Dict] = None
    ) -> DialogueAction:
        """选择对话动作

        Args:
            context: 对话上下文
            intent: 识别的意图
            entities: 实体信息

        Returns:
            选择的动作
        """
        # 更新上下文
        if intent:
            context.current_intent = intent
        if entities:
            context.entities.update(entities)

        # 检查是否需要澄清
        if intent in self.INTENT_REQUIRES_CLARIFICATION:
            required_params = self.INTENT_REQUIRES_CLARIFICATION[intent]
            missing = [p for p in required_params if p not in context.entities]
            if missing:
                context.missing_params = missing
                context.state = DialogueState.WAITING_CLARIFICATION
                return DialogueAction.CLARIFY

        # 检查是否需要确认
        if self._should_confirm(context):
            return DialogueAction.CONFIRM

        # 检查是否闲聊
        if self.should_chitchat(context):
            return DialogueAction.CHITCHAT

        # 默认直接回复
        context.state = DialogueState.RESPONDING
        return DialogueAction.RESPOND

    def should_clarify(
        self,
        intent: str,
        entities: Dict[str, Any]
    ) -> List[ClarificationRequest]:
        """判断是否需要澄清

        Args:
            intent: 意图
            entities: 已提取的实体

        Returns:
            澄清请求列表
        """
        if intent not in self.INTENT_REQUIRES_CLARIFICATION:
            return []

        required = self.INTENT_REQUIRES_CLARIFICATION[intent]
        clarifications = []

        for param in required:
            if param not in entities:
                question = self._generate_clarification_question(intent, param)
                clarifications.append(ClarificationRequest(
                    param_name=param,
                    question=question,
                    required=True
                ))

        return clarifications

    def should_chitchat(self, context: DialogueContext) -> bool:
        """判断是否闲聊

        Args:
            context: 对话上下文

        Returns:
            是否闲聊
        """
        # 基于历史对话密度
        if len(context.history) < 2:
            return False

        # 基于用户输入
        last_user_input = ""
        for msg in reversed(context.history):
            if msg.get("role") == "user":
                last_user_input = msg.get("content", "").lower()
                break

        # 检查触发词
        for trigger in self.CHITCHAT_TRIGGERS:
            if trigger in last_user_input:
                return True

        return False

    def _should_confirm(self, context: DialogueContext) -> bool:
        """判断是否需要确认"""
        # 高价值操作需要确认
        high_value_actions = {"book", "reserve", "payment"}
        intent = context.current_intent or ""

        return any(action in intent for action in high_value_actions)

    def _generate_clarification_question(
        self,
        intent: str,
        param: str
    ) -> str:
        """生成澄清问题"""
        questions = {
            ("plan_trip", "destination"): "您想去哪个城市旅游呢?",
            ("plan_trip", "dates"): "您计划什么时候出发?",
            ("book_hotel", "checkin"): "您计划什么时候入住?",
            ("book_hotel", "checkout"): "您计划什么时候退房?",
            ("find_restaurant", "cuisine"): "您想吃什么类型的菜?",
            ("find_restaurant", "budget"): "您的预算是多少?"
        }
        return questions.get((intent, param), f"请提供您的{param}")

    def update_state(self, session_id: str, state: DialogueState):
        """更新对话状态"""
        context = self.get_context(session_id)
        context.state = state

    def clear_context(self, session_id: str):
        """清除对话上下文"""
        if session_id in self._contexts:
            del self._contexts[session_id]


# 全局单例
dialogue_policy = DialoguePolicy()
```

### 2. ContextTracker

**文件**: `agent/src/memory/context_tracker.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class TrackedEntity:
    """追踪的实体"""
    id: str
    type: str           # city, attraction, hotel, etc.
    value: str          # 北京, 故宫
    mentions: int = 0   # 提及次数
    last_mentioned: str = ""  # 最后提及的时间
    turns_ago: int = 0  # 多少轮之前


@dataclass
class EntityReference:
    """实体引用"""
    text: str           # 引用的文本
    type: str          # 代词/指示词
    resolved_to: Optional[str] = None  # 解析到的实体ID


class ContextTracker:
    """上下文追踪器

    特性：
    - 跨轮次实体追踪
    - 代词消歧
    - 实体续接
    - 上下文恢复
    """

    # 代词映射
    PRONOUN_MAPPING = {
        "它": "previously_mentioned",
        "这个": "previously_mentioned",
        "那个": "previously_mentioned",
        "那里": "location",
        "这里": "location"
    }

    def __init__(self, max_tracked: int = 50, max_turns: int = 10):
        self._tracked_entities: Dict[str, Dict[str, TrackedEntity]] = defaultdict(dict)
        self._references: Dict[str, List[EntityReference]] = defaultdict(list)
        self._turn_count: Dict[str, int] = defaultdict(int)
        self._max_tracked = max_tracked
        self._max_turns = max_turns
        logger.info("ContextTracker initialized")

    def track_entity(
        self,
        session_id: str,
        entity_type: str,
        value: str,
        turn_id: Optional[int] = None
    ) -> str:
        """追踪实体

        Args:
            session_id: 会话ID
            entity_type: 实体类型
            value: 实体值
            turn_id: 轮次ID

        Returns:
            实体ID
        """
        entity_id = f"{entity_type}:{value}"

        if entity_id not in self._tracked_entities[session_id]:
            self._tracked_entities[session_id][entity_id] = TrackedEntity(
                id=entity_id,
                type=entity_type,
                value=value
            )

        entity = self._tracked_entities[session_id][entity_id]
        entity.mentions += 1
        entity.last_mentioned = datetime.now().isoformat()

        if turn_id is not None:
            entity.turns_ago = self._turn_count[session_id] - turn_id
        else:
            entity.turns_ago = 0

        return entity_id

    def track_entities_from_ner(
        self,
        session_id: str,
        entities: Dict[str, Any],
        turn_id: Optional[int] = None
    ) -> Dict[str, str]:
        """从NER结果追踪实体

        Args:
            session_id: 会话ID
            entities: NER识别的实体
            turn_id: 轮次ID

        Returns:
            {entity_type: entity_id}
        """
        entity_ids = {}

        for entity_type, value in entities.items():
            if isinstance(value, list):
                for v in value:
                    entity_id = self.track_entity(session_id, entity_type, str(v), turn_id)
                    entity_ids[entity_type] = entity_id
            else:
                entity_id = self.track_entity(session_id, entity_type, str(value), turn_id)
                entity_ids[entity_type] = entity_id

        return entity_ids

    def resolve_reference(
        self,
        session_id: str,
        reference: str,
        reference_type: str = "pronoun"
    ) -> Optional[TrackedEntity]:
        """消歧引用

        Args:
            session_id: 会话ID
            reference: 引用的文本 (它/这个)
            reference_type: 引用类型

        Returns:
            解析到的实体
        """
        if session_id not in self._tracked_entities:
            return None

        entities = self._tracked_entities[session_id]

        if reference_type == "pronoun":
            # 返回最近提到的实体
            sorted_entities = sorted(
                entities.values(),
                key=lambda e: e.turns_ago
            )
            for entity in sorted_entities:
                if entity.turns_ago <= 2:  # 2轮以内
                    return entity

        return None

    def get_active_entities(
        self,
        session_id: str,
        entity_type: Optional[str] = None,
        max_turns: int = 5
    ) -> List[TrackedEntity]:
        """获取活跃实体

        Args:
            session_id: 会话ID
            entity_type: 实体类型过滤
            max_turns: 最多多少轮之前

        Returns:
            活跃实体列表
        """
        if session_id not in self._tracked_entities:
            return []

        entities = self._tracked_entities[session_id].values()

        # 过滤
        if entity_type:
            entities = [e for e in entities if e.type == entity_type]

        entities = [e for e in entities if e.turns_ago <= max_turns]

        # 按提及次数排序
        return sorted(entities, key=lambda e: e.mentions, reverse=True)

    def increment_turn(self, session_id: str):
        """增加轮次计数"""
        self._turn_count[session_id] += 1

        # 清理过期实体
        self._cleanup_expired_entities(session_id)

    def get_entity_mentions(
        self,
        session_id: str,
        entity_id: str
    ) -> int:
        """获取实体提及次数"""
        if session_id not in self._tracked_entities:
            return 0
        entity = self._tracked_entities[session_id].get(entity_id)
        return entity.mentions if entity else 0

    def _cleanup_expired_entities(self, session_id: str):
        """清理过期实体"""
        if session_id not in self._tracked_entities:
            return

        expired = [
            eid for eid, entity in self._tracked_entities[session_id].items()
            if entity.turns_ago > self._max_turns
        ]

        for eid in expired:
            del self._tracked_entities[session_id][eid]

    def clear_session(self, session_id: str):
        """清除会话追踪"""
        if session_id in self._tracked_entities:
            del self._tracked_entities[session_id]
        if session_id in self._references:
            del self._references[session_id]
        if session_id in self._turn_count:
            del self._turn_count[session_id]


# 全局单例
context_tracker = ContextTracker()
```

### 3. EntityLinker

**文件**: `agent/src/reasoner/entity_linker.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class EntityCandidate:
    """实体候选"""
    id: str
    name: str
    type: str
    score: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkResult:
    """链接结果"""
    text: str
    original: str
    linked_entity: Optional[EntityCandidate]
    confidence: float


class EntityLinker:
    """实体链接器

    特性：
    - 实体识别
    - 实体消歧
    - 候选排序
    - 知识库匹配
    """

    def __init__(self):
        self._knowledge_base: Dict[str, Dict[str, Any]] = {}
        self._alias_map: Dict[str, str] = {}  # 别名到标准名的映射
        self._type_entities: Dict[str, Set[str]] = defaultdict(set)
        logger.info("EntityLinker initialized")

    def add_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        aliases: Optional[List[str]] = None,
        attributes: Optional[Dict] = None
    ):
        """添加实体到知识库

        Args:
            entity_id: 实体ID
            name: 实体名称
            entity_type: 实体类型
            aliases: 别名列表
            attributes: 属性
        """
        self._knowledge_base[entity_id] = {
            "name": name,
            "type": entity_type,
            "attributes": attributes or {}
        }

        self._type_entities[entity_type].add(entity_id)

        # 别名映射
        if aliases:
            for alias in aliases:
                self._alias_map[alias.lower()] = name

        # 名称映射
        self._alias_map[name.lower()] = name

    def link(
        self,
        text: str,
        entity_type: Optional[str] = None,
        candidates: int = 5
    ) -> List[LinkResult]:
        """链接实体

        Args:
            text: 输入文本
            entity_type: 实体类型过滤
            candidates: 返回候选数量

        Returns:
            链接结果列表
        """
        # 简单实现：基于知识库的匹配
        results = []
        text_lower = text.lower()

        # 检查是否是已知别名
        for alias, standard_name in self._alias_map.items():
            if alias in text_lower:
                # 找到匹配的实体
                for eid, info in self._knowledge_base.items():
                    if info["name"] == standard_name:
                        if entity_type and info["type"] != entity_type:
                            continue

                        results.append(LinkResult(
                            text=text,
                            original=alias,
                            linked_entity=EntityCandidate(
                                id=eid,
                                name=info["name"],
                                type=info["type"],
                                score=1.0,
                                attributes=info.get("attributes", {})
                            ),
                            confidence=1.0
                        ))
                        break

        return results

    def disambiguate(
        self,
        text: str,
        candidates: List[EntityCandidate]
    ) -> EntityCandidate:
        """消歧

        Args:
            text: 上下文文本
            candidates: 候选实体

        Returns:
            最佳匹配实体
        """
        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # 简单消歧：选择属性最多的
        best = max(candidates, key=lambda c: len(c.attributes))
        return best

    def get_entity_by_name(
        self,
        name: str,
        entity_type: Optional[str] = None
    ) -> Optional[EntityCandidate]:
        """根据名称获取实体

        Args:
            name: 实体名称
            entity_type: 实体类型

        Returns:
            实体
        """
        standard_name = self._alias_map.get(name.lower(), name)

        for eid, info in self._knowledge_base.items():
            if info["name"] == standard_name:
                if entity_type and info["type"] != entity_type:
                    continue

                return EntityCandidate(
                    id=eid,
                    name=info["name"],
                    type=info["type"],
                    score=1.0,
                    attributes=info.get("attributes", {})
                )

        return None

    def search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10
    ) -> List[EntityCandidate]:
        """搜索实体

        Args:
            query: 查询词
            entity_type: 实体类型
            limit: 返回数量

        Returns:
            匹配的实体列表
        """
        results = []
        query_lower = query.lower()

        for eid, info in self._knowledge_base.items():
            if entity_type and info["type"] != entity_type:
                continue

            # 名称匹配
            name_lower = info["name"].lower()
            score = 0.0

            if query_lower == name_lower:
                score = 1.0
            elif query_lower in name_lower:
                score = 0.8
            elif name_lower in query_lower:
                score = 0.6

            if score > 0:
                results.append(EntityCandidate(
                    id=eid,
                    name=info["name"],
                    type=info["type"],
                    score=score,
                    attributes=info.get("attributes", {})
                ))

        # 排序返回
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]


# 全局单例
entity_linker = EntityLinker()
```

## 集成到 TravelAgent

```python
class TravelAgent:
    def __init__(self, config):
        # ... existing code ...

        # 初始化对话增强组件
        from core.dialogue_policy import dialogue_policy
        from memory.context_tracker import context_tracker
        from reasoner.entity_linker import entity_linker

        self.dialogue_policy = dialogue_policy
        self.context_tracker = context_tracker
        self.entity_linker = entity_linker

        # 初始化知识库
        self._init_knowledge_base()

    async def process(self, user_input: str, context: dict = None):
        # 获取对话上下文
        session_id = context.get("session_id", "default")
        dialog_context = self.dialogue_policy.get_context(session_id)

        # 追踪实体
        entities = self._extract_entities(user_input)
        self.context_tracker.track_entities_from_ner(session_id, entities)

        # 意图澄清检查
        clarifications = self.dialogue_policy.should_clarify(
            intent=context.get("intent"),
            entities=entities
        )

        if clarifications:
            # 需要澄清，返回澄清问题
            clarification_questions = [c.question for c in clarifications]
            return {"action": "clarify", "questions": clarification_questions}

        # 选择对话动作
        action = self.dialogue_policy.select_action(
            dialog_context,
            intent=context.get("intent"),
            entities=entities
        )

        # 处理不同动作
        if action == DialogueAction.CHITCHAT:
            return await self._handle_chitchat(user_input, context)
        elif action == DialogueAction.CONFIRM:
            return await self._handle_confirm(context)
        else:
            # 正常处理
            return await self._execute_normal(context)

        # 增加轮次
        self.context_tracker.increment_turn(session_id)
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `core/dialogue_policy.py` | 对话策略管理器 |
| `memory/context_tracker.py` | 上下文追踪器 |
| `reasoner/entity_linker.py` | 实体链接器 |
| `reasoner/__init__.py` | 模块导出更新 |

## 与现有模块的关系

```
现有模块                          新增模块
─────────────────────────────    ─────────────────
intent_recognizer  ──────→    dialogue_policy
                            context_tracker ← memory/manager
                            entity_linker  ← reasoner/
```

## 测试计划

```python
# tests/test_dialogue_policy.py
def test_select_action_clarify():
    policy = DialoguePolicy()
    context = policy.get_context("session1")

    action = policy.select_action(
        context,
        intent="plan_trip",
        entities={"city": "北京"}  # 缺少 dates
    )
    assert action == DialogueAction.CLARIFY

# tests/test_context_tracker.py
def test_track_entity():
    tracker = ContextTracker()
    entity_id = tracker.track_entity(
        "session1",
        "city",
        "北京"
    )
    active = tracker.get_active_entities("session1")
    assert len(active) == 1

# tests/test_entity_linker.py
def test_link_entity():
    linker = EntityLinker()
    linker.add_entity(
        "beijing_001",
        "北京",
        "city",
        aliases=["京城", "北平"]
    )

    results = linker.link("去北京玩")
    assert len(results) > 0
    assert results[0].linked_entity.name == "北京"
```
