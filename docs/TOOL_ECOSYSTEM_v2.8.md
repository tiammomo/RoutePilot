# v2.8.0 工具生态扩展设计

## 概述

v2.8.0 聚焦于工具能力的扩展和生态建设，提供动态工具注册、学习和插件化扩展机制。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        TravelAgent                               │
│                                                                  │
│  ┌────────────────┐    ┌────────────────┐    ┌──────────────┐ │
│  │  ToolRegistry  │←──→│  ToolLearning  │←──→│ PluginSystem │ │
│  └────────────────┘    └────────────────┘    └──────────────┘ │
│           ↑                                                        │
│           │                                                        │
│  ┌───────┴────────────────────────────────────────────────┐     │
│  │                    Tool Ecosystem                      │     │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐  │     │
│  │  │  Base   │ │ Travel  │ │ Custom  │ │  External   │  │     │
│  │  │  Tool   │ │  Tools  │ │  Tools  │ │  Plugins   │  │     │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘  │     │
│  └──────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## 模块设计

### 1. ToolRegistry

**文件**: `agent/src/tools/registry.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """工具分类"""
    SEARCH = "search"           # 搜索
    RECOMMENDATION = "recommendation"  # 推荐
    PLANNING = "planning"       # 规划
    CALCULATION = "calculation" # 计算
    INFORMATION = "information" # 信息查询
    CUSTOM = "custom"          # 自定义


class ToolStatus(Enum):
    """工具状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


@dataclass
class ToolMetadata:
    """工具元数据"""
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""
    parameters_schema: Dict = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    status: ToolStatus = ToolStatus.ACTIVE


@dataclass
class ToolInfo:
    """工具信息"""
    metadata: ToolMetadata
    handler: Callable
    is_async: bool = False


class ToolRegistry:
    """工具注册中心

    特性：
    - 动态注册/注销工具
    - 工具发现和搜索
    - 版本管理
    - 分类和标签
    """

    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}
        self._category_index: Dict[ToolCategory, List[str]] = {}
        self._tag_index: Dict[str, List[str]] = {}
        logger.info("ToolRegistry initialized")

    def register(
        self,
        tool_id: str,
        name: str,
        description: str,
        handler: Callable,
        category: ToolCategory = ToolCategory.CUSTOM,
        tags: Optional[List[str]] = None,
        is_async: bool = False,
        **metadata
    ) -> str:
        """注册工具

        Args:
            tool_id: 工具唯一标识
            name: 工具名称
            description: 工具描述
            handler: 工具处理函数
            category: 工具分类
            tags: 标签列表
            is_async: 是否异步工具

        Returns:
            tool_id
        """
        if tool_id in self._tools:
            raise ValueError(f"Tool {tool_id} already registered")

        metadata_obj = ToolMetadata(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            **metadata
        )

        self._tools[tool_id] = ToolInfo(
            metadata=metadata_obj,
            handler=handler,
            is_async=is_async
        )

        # 更新索引
        self._update_indices(tool_id, metadata_obj)

        logger.info(f"Registered tool: {tool_id}")
        return tool_id

    def unregister(self, tool_id: str) -> bool:
        """注销工具

        Args:
            tool_id: 工具ID

        Returns:
            是否成功
        """
        if tool_id not in self._tools:
            return False

        tool_info = self._tools[tool_id]
        metadata = tool_info.metadata

        # 从索引中移除
        if metadata.category in self._category_index:
            self._category_index[metadata.category].remove(tool_id)

        for tag in metadata.tags:
            if tag in self._tag_index:
                self._tag_index[tag].remove(tool_id)

        del self._tools[tool_id]
        logger.info(f"Unregistered tool: {tool_id}")
        return True

    def get_tool(self, tool_id: str) -> Optional[ToolInfo]:
        """获取工具"""
        return self._tools.get(tool_id)

    def discover(self, query: str, top_k: int = 5) -> List[ToolInfo]:
        """发现工具

        基于名称、描述、标签进行语义搜索。

        Args:
            query: 查询关键词
            top_k: 返回数量

        Returns:
            匹配的工具列表
        """
        query_lower = query.lower()
        results = []

        for tool_id, tool_info in self._tools.items():
            metadata = tool_info.metadata
            score = 0

            # 名称匹配
            if query_lower in metadata.name.lower():
                score += 10

            # 描述匹配
            if query_lower in metadata.description.lower():
                score += 5

            # 标签匹配
            for tag in metadata.tags:
                if query_lower in tag.lower():
                    score += 3

            if score > 0:
                results.append((tool_id, tool_info, score))

        # 按分数排序
        results.sort(key=lambda x: x[2], reverse=True)
        return [r[1] for r in results[:top_k]]

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        status: Optional[ToolStatus] = None,
        tags: Optional[List[str]] = None
    ) -> List[ToolInfo]:
        """列出工具

        Args:
            category: 分类过滤
            status: 状态过滤
            tags: 标签过滤

        Returns:
            工具列表
        """
        results = []

        for tool_info in self._tools.values():
            metadata = tool_info.metadata

            # 分类过滤
            if category and metadata.category != category:
                continue

            # 状态过滤
            if status and metadata.status != status:
                continue

            # 标签过滤
            if tags and not any(t in metadata.tags for t in tags):
                continue

            results.append(tool_info)

        return results

    def get_stats(self) -> Dict:
        """获取统计信息"""
        category_count = {}
        status_count = {}

        for tool_info in self._tools.values():
            cat = tool_info.metadata.category.value
            sta = tool_info.metadata.status.value

            category_count[cat] = category_count.get(cat, 0) + 1
            status_count[sta] = status_count.get(sta, 0) + 1

        return {
            "total_tools": len(self._tools),
            "by_category": category_count,
            "by_status": status_count
        }

    def _update_indices(self, tool_id: str, metadata: ToolMetadata):
        """更新索引"""
        # 分类索引
        if metadata.category not in self._category_index:
            self._category_index[metadata.category] = []
        if tool_id not in self._category_index[metadata.category]:
            self._category_index[metadata.category].append(tool_id)

        # 标签索引
        for tag in metadata.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if tool_id not in self._tag_index[tag]:
                self._tag_index[tag].append(tool_id)


# 全局单例
tool_registry = ToolRegistry()
```

### 2. ToolLearning

**文件**: `agent/src/tools/learning.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolUsage:
    """工具使用记录"""
    tool_id: str
    timestamp: str
    success: bool
    context: Dict = field(default_factory=dict)
    duration: float = 0.0


@dataclass
class UserToolPreferences:
    """用户工具偏好"""
    user_id: str
    frequently_used: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    successful_tools: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    failed_tools: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_used: Dict[str, str] = field(default_factory=dict)


class ToolLearning:
    """工具学习器

    特性：
    - 记录工具使用情况
    - 学习用户偏好
    - 智能推荐工具
    """

    def __init__(self, redis_client=None):
        self._usage_history: List[ToolUsage] = []
        self._user_preferences: Dict[str, UserToolPreferences] = {}
        self._context_tools: Dict[str, List[str]] = defaultdict(list)
        self._redis = redis_client
        self._max_history = 10000
        logger.info("ToolLearning initialized")

    def record_usage(
        self,
        tool_id: str,
        success: bool,
        context: Optional[Dict] = None,
        duration: float = 0.0,
        user_id: Optional[str] = None
    ):
        """记录工具使用

        Args:
            tool_id: 工具ID
            success: 是否成功
            context: 使用上下文
            duration: 执行时长
            user_id: 用户ID
        """
        usage = ToolUsage(
            tool_id=tool_id,
            timestamp=datetime.now().isoformat(),
            success=success,
            context=context or {},
            duration=duration
        )

        self._usage_history.append(usage)

        # 限制历史长度
        if len(self._usage_history) > self._max_history:
            self._usage_history = self._usage_history[-self._max_history:]

        # 更新用户偏好
        if user_id:
            self._update_preferences(user_id, tool_id, success)

        # 更新上下文关联
        if context:
            self._update_context_association(tool_id, context)

    def recommend_tools(
        self,
        context: Optional[Dict] = None,
        user_id: Optional[str] = None,
        top_k: int = 3
    ) -> List[str]:
        """推荐工具

        Args:
            context: 当前上下文
            user_id: 用户ID
            top_k: 推荐数量

        Returns:
            推荐的工具ID列表
        """
        scores = defaultdict(float)

        # 基于用户的推荐
        if user_id and user_id in self._user_preferences:
            prefs = self._user_preferences[user_id]
            for tool_id, count in prefs.frequently_used.items():
                scores[tool_id] += count * 2.0

        # 基于上下文的推荐
        if context:
            query = context.get("query", "").lower()
            intent = context.get("intent", "")

            # 查询关键词关联
            for tool_id, related_queries in self._context_tools.items():
                for related in related_queries:
                    if related.lower() in query:
                        scores[tool_id] += 1.0

            # 意图关联
            if intent:
                for tool_id, related_intents in self._context_tools.items():
                    if intent in related_intents:
                        scores[tool_id] += 1.5

        # 基于历史的推荐
        recent_tools = [u.tool_id for u in self._usage_history[-10:]]
        for tool_id in recent_tools:
            scores[tool_id] += 0.5

        # 排序返回
        sorted_tools = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tools[:top_k]]

    def infer_preferences(self, user_id: str) -> UserToolPreferences:
        """推断用户偏好

        Args:
            user_id: 用户ID

        Returns:
            用户偏好
        """
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = UserToolPreferences(user_id=user_id)

        return self._user_preferences[user_id]

    def get_popular_tools(self, limit: int = 10) -> List[tuple]:
        """获取热门工具

        Returns:
            [(tool_id, usage_count), ...]
        """
        counts = defaultdict(int)
        for usage in self._usage_history:
            counts[usage.tool_id] += 1

        sorted_tools = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_tools[:limit]

    def get_success_rate(self, tool_id: str) -> float:
        """获取工具成功率

        Args:
            tool_id: 工具ID

        Returns:
            成功率 (0-1)
        """
        tool_usage = [u for u in self._usage_history if u.tool_id == tool_id]
        if not tool_usage:
            return 0.0

        success_count = sum(1 for u in tool_usage if u.success)
        return success_count / len(tool_usage)

    def _update_preferences(self, user_id: str, tool_id: str, success: bool):
        """更新用户偏好"""
        if user_id not in self._user_preferences:
            self._user_preferences[user_id] = UserToolPreferences(user_id=user_id)

        prefs = self._user_preferences[user_id]
        prefs.frequently_used[tool_id] += 1
        prefs.last_used[tool_id] = datetime.now().isoformat()

        if success:
            prefs.successful_tools[tool_id] += 1
        else:
            prefs.failed_tools[tool_id] += 1

    def _update_context_association(self, tool_id: str, context: Dict):
        """更新上下文关联"""
        query = context.get("query", "")
        intent = context.get("intent", "")

        if query:
            self._context_tools[tool_id].append(query)
            # 限制每个工具的上下文数量
            if len(self._context_tools[tool_id]) > 100:
                self._context_tools[tool_id] = self._context_tools[tool_id][-100:]

        if intent:
            key = f"intent:{intent}"
            if key not in self._context_tools[tool_id]:
                self._context_tools[tool_id].append(key)


# 全局单例
tool_learning = ToolLearning()
```

### 3. PluginSystem

**文件**: `agent/src/tools/plugin.py`

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import importlib.util
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PluginState(Enum):
    """插件状态"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginMetadata:
    """插件元数据"""
    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    entry_point: str = "main"
    config_schema: Dict = field(default_factory=dict)


@dataclass
class Plugin:
    """插件实例"""
    metadata: PluginMetadata
    state: PluginState
    module: Any = None
    config: Dict = field(default_factory=dict)
    error: Optional[str] = None


class PluginManager:
    """插件管理器

    特性：
    - 插件加载/卸载
    - 依赖管理
    - 配置管理
    - 热重载
    """

    def __init__(self, plugin_dir: str = "plugins"):
        self._plugins: Dict[str, Plugin] = {}
        self._plugin_dir = Path(plugin_dir)
        self._hooks: Dict[str, List[Callable]] = {
            "before_tool_call": [],
            "after_tool_call": [],
            "on_error": [],
            "on_load": [],
            "on_unload": []
        }
        logger.info(f"PluginManager initialized with dir: {plugin_dir}")

    def load_plugin(self, plugin_path: str) -> Plugin:
        """加载插件

        Args:
            plugin_path: 插件路径 (.py 文件或目录)

        Returns:
            插件实例
        """
        path = Path(plugin_path)

        if not path.exists():
            raise FileNotFoundError(f"Plugin not found: {plugin_path}")

        # 加载模块
        spec = importlib.util.spec_from_file_location(
            path.stem, path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)

        # 获取插件类
        plugin_class = getattr(module, "Plugin", None)
        if not plugin_class:
            raise ValueError(f"Plugin class not found in {plugin_path}")

        # 实例化
        plugin_instance = plugin_class()
        plugin_id = getattr(plugin_instance, "plugin_id", path.stem)

        metadata = PluginMetadata(
            plugin_id=plugin_id,
            name=getattr(plugin_instance, "name", path.stem),
            version=getattr(plugin_instance, "version", "1.0.0"),
            author=getattr(plugin_instance, "author", ""),
            description=getattr(plugin_instance, "description", "")
        )

        plugin = Plugin(
            metadata=metadata,
            state=PluginState.LOADED,
            module=plugin_instance
        )

        self._plugins[plugin_id] = plugin

        # 执行加载钩子
        self._execute_hooks("on_load", plugin_id)

        logger.info(f"Loaded plugin: {plugin_id}")
        return plugin

    def unload_plugin(self, plugin_id: str) -> bool:
        """卸载插件

        Args:
            plugin_id: 插件ID

        Returns:
            是否成功
        """
        if plugin_id not in self._plugins:
            return False

        plugin = self._plugins[plugin_id]

        # 调用插件的 unload 方法
        if hasattr(plugin.module, "unload"):
            plugin.module.unload()

        # 执行卸载钩子
        self._execute_hooks("on_unload", plugin_id)

        # 移除
        del self._plugins[plugin_id]

        logger.info(f"Unloaded plugin: {plugin_id}")
        return True

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """获取插件"""
        return self._plugins.get(plugin_id)

    def list_plugins(
        self,
        state: Optional[PluginState] = None
    ) -> List[Plugin]:
        """列出插件

        Args:
            state: 状态过滤

        Returns:
            插件列表
        """
        if state:
            return [p for p in self._plugins.values() if p.state == state]
        return list(self._plugins.values())

    def register_hook(self, hook_name: str, callback: Callable):
        """注册钩子

        Args:
            hook_name: 钩子名称
            callback: 回调函数
        """
        if hook_name not in self._hooks:
            raise ValueError(f"Unknown hook: {hook_name}")

        self._hooks[hook_name].append(callback)

    def execute_hook(self, hook_name: str, *args, **kwargs):
        """执行钩子"""
        if hook_name in self._hooks:
            for callback in self._hooks[hook_name]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Hook {hook_name} error: {e}")

    def _execute_hooks(self, hook_name: str, *args, **kwargs):
        """执行钩子 (内部)"""
        self.execute_hook(hook_name, *args, **kwargs)


# 全局单例
plugin_manager = PluginManager()
```

## 新增工具

### 天气工具

```python
class WeatherTool:
    """天气查询工具"""

    def __init__(self, api_key: str = None):
        self.name = "weather_tool"
        self.description = "查询目的地天气情况"
        self.plugin_id = "weather_tool"

    async def execute(self, city: str, date: str = None) -> Dict:
        """查询天气

        Args:
            city: 城市名称
            date: 日期 (可选, 默认今天)

        Returns:
            天气信息
        """
        # 实现天气API调用
        pass
```

### 酒店工具

```python
class HotelTool:
    """酒店搜索工具"""

    def __init__(self):
        self.name = "hotel_tool"
        self.description = "搜索和推荐酒店"
        self.plugin_id = "hotel_tool"

    async def execute(
        self,
        city: str,
        checkin: str,
        checkout: str,
        budget: str = "medium",
        **kwargs
    ) -> List[Dict]:
        """搜索酒店

        Args:
            city: 城市
            checkin: 入住日期
            checkout: 退房日期
            budget: 预算 (low/medium/high)

        Returns:
            酒店列表
        """
        pass
```

## 集成到 TravelAgent

```python
class TravelAgent:
    def __init__(self, config):
        # ... existing code ...

        # 初始化工具生态
        from tools.registry import tool_registry
        from tools.learning import tool_learning
        from tools.plugin import plugin_manager

        self.tool_registry = tool_registry
        self.tool_learning = tool_learning
        self.plugin_manager = plugin_manager

        # 注册内置工具
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """注册内置工具"""
        from core.travel_tools import create_travel_tools

        tools = create_travel_tools()
        for tool in tools:
            self.tool_registry.register(
                tool_id=tool.name,
                name=tool.name,
                description=tool.description,
                handler=tool.execute,
                category=ToolCategory.SEARCH
            )

    async def process(self, user_input: str, context: dict = None):
        # ... existing code ...

        # 工具推荐
        recommended_tools = self.tool_learning.recommend_tools(
            context=context,
            user_id=context.get("user_id"),
            top_k=3
        )

        # 如果没有明确指定工具,使用推荐的
        if not context.get("tools") and recommended_tools:
            context = context or {}
            context["recommended_tools"] = recommended_tools
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `tools/registry.py` | 工具注册中心 |
| `tools/learning.py` | 工具学习器 |
| `tools/plugin.py` | 插件系统 |
| `tools/__init__.py` | 模块导出 |

## 测试计划

```python
# tests/test_tool_registry.py
def test_register_tool():
    registry = ToolRegistry()
    tool_id = registry.register(
        tool_id="test_tool",
        name="Test Tool",
        description="A test tool",
        handler=lambda: "result"
    )
    assert tool_id == "test_tool"

def test_discover_tools():
    registry = ToolRegistry()
    # ... register tools ...
    results = registry.discover("search")
    assert len(results) > 0
```
