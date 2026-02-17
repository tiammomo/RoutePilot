"""
================================================================================
旅游工具模块 (Travel Tools)

提供旅游助手的核心工具函数，包括城市搜索、景点查询、路线规划、预算计算等。
这些工具函数由 create_travel_tools 工厂函数组装成完整的工具列表。

功能模块：
1. 工具执行函数: _search_cities, _query_attractions, _generate_route 等
2. 工具工厂函数: create_travel_tools

使用示例:
```python
from core.travel_tools import create_travel_tools
from config.config_manager import ConfigManager

config = ConfigManager()
tools = create_travel_tools(config)
```

================================================================================
"""

import json
from typing import Dict, Any, List, Optional

from core.react_agent import ToolInfo
from config.config_manager import ConfigManager
from llm.client import LLMClient


# ==============================================================================
# 工具执行函数
# 这些函数是工具的具体实现，由 create_travel_tools 中定义的 lambda 调用
# ==============================================================================

def _search_cities(
    config_manager: ConfigManager,
    interests: List[str] = None,
    budget: tuple = None,
    season: str = None
) -> Dict[str, Any]:
    """
    搜索匹配的城市

    根据用户的兴趣标签、预算范围和出行季节，从数据库中搜索匹配的城市。

    Args:
        config_manager: 配置管理器
        interests: 用户兴趣标签列表，如 ["美食", "历史文化"]
        budget: 预算范围元组 (最低, 最高)，如 (1000, 5000)
        season: 出行季节，如 "春季", "夏季"

    Returns:
        Dict: 包含搜索结果的字典，格式为 {'success': bool, 'cities': [...]}

    Examples:
        >>> result = _search_cities(config_manager, ["美食"], (1000, 3000), "春季")
        >>> if result['success']:
        ...     for city in result['cities']:
        ...         print(city['name'])
    """
    from environment.travel_data import TravelData
    env = TravelData(config_manager)
    return env.search_cities(interests, budget, season)


def _query_attractions(config_manager: ConfigManager, cities: List[str]) -> Dict[str, Any]:
    """
    查询城市景点信息

    获取指定城市的景点列表和相关详细信息。

    Args:
        config_manager: 配置管理器
        cities: 要查询的城市名称列表

    Returns:
        Dict: 包含景点信息的字典，格式为 {'success': bool, 'data': {...}}

    Examples:
        >>> result = _query_attractions(config_manager, ["北京", "上海"])
        >>> if result['success']:
        ...     for city, info in result['data'].items():
        ...         print(f"{city}: {len(info.get('attractions', []))} 个景点")
    """
    from environment.travel_data import TravelData
    env = TravelData(config_manager)
    return env.query_attractions(cities)


def _generate_route(
    config_manager: ConfigManager,
    city: str,
    days: int
) -> Dict[str, Any]:
    """
    生成旅游路线规划

    根据城市信息和旅行天数，自动生成每日的景点游览路线。

    算法逻辑：
    1. 获取城市基本信息
    2. 提取城市景点列表
    3. 按天数分配景点，生成每日路线
    4. 计算预估费用

    Args:
        config_manager: 配置管理器
        city: 目标城市名称
        days: 旅行天数

    Returns:
        Dict: 路线规划结果，包含：
        - success: 是否成功
        - city: 城市名称
        - route_plan: 每日路线列表
        - total_cost_estimate: 费用估算

    Examples:
        >>> result = _generate_route(config_manager, "北京", 3)
        >>> if result['success']:
        ...     for day in result['route_plan']:
        ...         print(f"第{day['day']}天: {day['schedule']}")
    """
    from environment.travel_data import TravelData
    env = TravelData(config_manager)
    result = env.get_city_info(city)
    if not result.get('success'):
        return result

    city_info = result.get('info', {})
    attractions = city_info.get('attractions', [])

    # 生成路线计划
    # 策略：每天分配一个主要景点，按顺序循环
    route_plan = []
    for i in range(min(days, len(attractions))):
        attr = attractions[i] if i < len(attractions) else {'name': '自由活动'}
        route_plan.append({
            'day': i + 1,
            'attractions': [attr['name']] if isinstance(attr, dict) else [attr],
            'schedule': f'游览{attr.get("name", "自由活动")}'
        })

    # 计算费用估算
    # 门票费用 + 每日平均花费
    return {
        'success': True,
        'city': city,
        'route_plan': route_plan,
        'total_cost_estimate': {
            'tickets': sum(a.get('ticket', 0) for a in attractions[:days]),
            'total': sum(a.get('ticket', 0) for a in attractions[:days]) +
                     city_info.get('avg_budget_per_day', 400) * days
        }
    }


def _calculate_budget(config_manager: ConfigManager, city: str, days: int) -> Dict[str, Any]:
    """
    计算旅游预算

    根据城市物价水平和旅行天数，计算预计花费。

    Args:
        config_manager: 配置管理器
        city: 目标城市
        days: 旅行天数

    Returns:
        Dict: 预算计算结果，包含各项目的费用明细
    """
    from environment.travel_data import TravelData
    env = TravelData(config_manager)
    return env.calculate_budget(city, days)


def _get_city_info(config_manager: ConfigManager, city: str) -> Dict[str, Any]:
    """
    获取城市详细信息

    获取指定城市的完整信息，包括区域、标签、季节、预算、景点等。

    Args:
        config_manager: 配置管理器
        city: 城市名称

    Returns:
        Dict: 城市详细信息，包含：
        - success: 是否成功
        - city: 城市名称
        - info: 详细信息字典
    """
    from environment.travel_data import TravelData
    env = TravelData(config_manager)
    return env.get_city_info(city)


def _llm_chat(
    config_manager: ConfigManager,
    query: str,
    context: str = ""
) -> Dict[str, Any]:
    """
    LLM 对话回答

    使用大语言模型生成回答，处理用户的一般性问题。

    Args:
        config_manager: 配置管理器
        query: 用户问题
        context: 对话上下文（可选）

    Returns:
        Dict: LLM 回答结果，格式为 {'success': bool, 'response': str}
    """
    llm_config = config_manager.get_default_model_config()
    llm_client = LLMClient(llm_config)

    messages = [{"role": "user", "content": query}]
    # 如果有上下文，添加到系统消息中
    if context:
        messages.insert(0, {"role": "system", "content": context})

    result = llm_client.chat(messages)

    # 标准化返回格式
    if isinstance(result, dict):
        if result.get('success') and 'content' in result:
            return {'success': True, 'response': result['content']}
        elif 'error' in result:
            return {'success': False, 'response': result['error']}
    return result


def _generate_recommendation(
    config_manager: ConfigManager,
    user_query: str,
    available_cities: List[str]
) -> Dict[str, Any]:
    """
    生成城市推荐

    根据用户需求和可用城市列表，使用 LLM 生成个性化推荐。

    Args:
        config_manager: 配置管理器
        user_query: 用户原始需求描述
        available_cities: 可选城市列表

    Returns:
        Dict: 推荐结果，包含推荐的城市列表和理由
    """
    llm_config = config_manager.get_default_model_config()
    llm_client = LLMClient(llm_config)
    return llm_client.generate_travel_recommendation(user_query, "", available_cities)


def _generate_route_plan(
    config_manager: ConfigManager,
    city: str,
    days: int,
    preferences: str = ""
) -> Dict[str, Any]:
    """
    生成详细路线计划

    使用 LLM 根据城市景点信息生成详细的每日行程规划。

    Args:
        config_manager: 配置管理器
        city: 目标城市
        days: 旅行天数
        preferences: 用户偏好描述

    Returns:
        Dict: 详细路线计划
    """
    city_info = config_manager.get_city_info(city)
    if not city_info:
        return {'success': False, 'error': f'未找到城市: {city}'}

    attractions = city_info.get('attractions', [])
    llm_config = config_manager.get_default_model_config()
    llm_client = LLMClient(llm_config)
    return llm_client.generate_route_plan(city, days, attractions, preferences)


# ==============================================================================
# 工具工厂函数
# ==============================================================================

def create_travel_tools(config_manager: ConfigManager) -> List[tuple]:
    """
    创建旅游助手工具列表

    该函数是旅游工具的工厂方法，负责创建所有可用的旅游相关工具。
    每个工具由两部分组成：
    1. ToolInfo: 工具的元数据描述（名称、参数、分类等）
    2. executor: 工具的实际执行函数

    工具列表包括：
    - search_cities: 根据条件搜索匹配的城市
    - query_attractions: 查询城市景点信息
    - generate_route: 生成旅游路线规划
    - calculate_budget: 计算旅游预算
    - get_city_info: 获取城市详细信息
    - llm_chat: LLM 对话回答
    - generate_city_recommendation: 生成城市推荐
    - generate_route_plan: 生成详细路线计划

    Args:
        config_manager: 配置管理器实例，用于获取城市数据等信息

    Returns:
        List[tuple]: 工具元组列表，每个元素为 (ToolInfo, executor_func)

    Examples:
        >>> tools = create_travel_tools(config_manager)
        >>> for tool_info, executor in tools:
        ...     agent.register_tool(tool_info, executor)
    """
    tools = []

    # ========== 工具1: 城市搜索 ==========
    # 根据用户兴趣、预算和季节偏好搜索匹配的城市
    tools.append((
        ToolInfo(
            name="search_cities",
            description="根据用户兴趣、预算和季节偏好搜索匹配的城市",
            parameters={
                'type': 'object',
                'properties': {
                    'interests': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': '用户兴趣标签列表，如 ["美食", "历史", "自然风光"]'
                    },
                    'budget_min': {'type': 'integer', 'description': '最低预算金额（元）'},
                    'budget_max': {'type': 'integer', 'description': '最高预算金额（元）'},
                    'season': {'type': 'string', 'description': '旅行季节，如 "春季", "夏季"'}
                }
            },
            required_params=[],  # 所有参数都是可选的
            category='travel',
            tags=['search', 'city', 'recommend']
        ),
        # 执行函数：调用内部函数处理搜索逻辑
        lambda interests=None, budget_min=None, budget_max=None, season=None:
            _search_cities(config_manager, interests, (budget_min, budget_max) if budget_min and budget_max else None, season)
    ))

    # ========== 工具2: 景点查询 ==========
    # 查询指定城市的景点信息
    tools.append((
        ToolInfo(
            name="query_attractions",
            description="查询指定城市的景点信息",
            parameters={
                'type': 'object',
                'properties': {
                    'cities': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': '要查询的城市名称列表'
                    }
                },
                'required': ['cities']  # cities 是必填参数
            },
            required_params=['cities'],
            category='travel',
            tags=['query', 'attraction', 'scenic']
        ),
        lambda cities: _query_attractions(config_manager, cities)
    ))

    # ========== 工具3: 路线生成 ==========
    # 为指定城市生成详细的旅游路线规划
    tools.append((
        ToolInfo(
            name="generate_route",
            description="为指定城市生成详细的旅游路线规划",
            parameters={
                'type': 'object',
                'properties': {
                    'city': {'type': 'string', 'description': '目标城市名称'},
                    'days': {'type': 'integer', 'description': '旅行天数，默认3天', 'default': 3}
                },
                'required': ['city']  # city 是必填参数
            },
            required_params=['city'],
            category='travel',
            tags=['route', 'plan', 'schedule']
        ),
        lambda city, days=3: _generate_route(config_manager, city, days)
    ))

    # ========== 工具4: 预算计算 ==========
    # 计算指定城市和天数的旅游预算
    tools.append((
        ToolInfo(
            name="calculate_budget",
            description="计算指定城市和天数的旅游预算",
            parameters={
                'type': 'object',
                'properties': {
                    'city': {'type': 'string', 'description': '目标城市'},
                    'days': {'type': 'integer', 'description': '旅行天数'}
                },
                'required': ['city', 'days']  # city 和 days 都是必填参数
            },
            required_params=['city', 'days'],
            category='travel',
            tags=['budget', 'cost', 'expense']
        ),
        lambda city, days: _calculate_budget(config_manager, city, days)
    ))

    # ========== 工具5: 城市信息 ==========
    # 获取指定城市的详细信息
    tools.append((
        ToolInfo(
            name="get_city_info",
            description="获取指定城市的详细信息",
            parameters={
                'type': 'object',
                'properties': {
                    'city': {'type': 'string', 'description': '城市名称'}
                },
                'required': ['city']
            },
            required_params=['city'],
            category='travel',
            tags=['city', 'info', 'detail']
        ),
        lambda city: _get_city_info(config_manager, city)
    ))

    # ========== 工具6: LLM 对话 ==========
    # 使用大语言模型进行对话回答
    tools.append((
        ToolInfo(
            name="llm_chat",
            description="使用大语言模型进行对话回答",
            parameters={
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': '用户问题'},
                    'context': {'type': 'string', 'description': '对话上下文'}
                },
                'required': ['query']
            },
            required_params=['query'],
            category='ai',
            tags=['chat', 'llm', 'ai']
        ),
        lambda query, context="": _llm_chat(config_manager, query, context)
    ))

    # ========== 工具7: 城市推荐 ==========
    # 根据用户需求生成个性化城市推荐
    tools.append((
        ToolInfo(
            name="generate_city_recommendation",
            description="根据用户需求生成个性化城市推荐",
            parameters={
                'type': 'object',
                'properties': {
                    'user_query': {'type': 'string', 'description': '用户原始需求'},
                    'available_cities': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': '可选城市列表'
                    }
                },
                'required': ['user_query', 'available_cities']
            },
            required_params=['user_query', 'available_cities'],
            category='ai',
            tags=['recommend', 'city', 'llm']
        ),
        lambda user_query, available_cities: _generate_recommendation(config_manager, user_query, available_cities)
    ))

    # ========== 工具8: 路线规划 ==========
    # 根据城市景点信息生成详细路线规划
    tools.append((
        ToolInfo(
            name="generate_route_plan",
            description="根据城市景点信息生成详细路线规划",
            parameters={
                'type': 'object',
                'properties': {
                    'city': {'type': 'string', 'description': '目标城市'},
                    'days': {'type': 'integer', 'description': '旅行天数'},
                    'preferences': {'type': 'string', 'description': '用户偏好'}
                },
                'required': ['city', 'days']
            },
            required_params=['city', 'days'],
            category='ai',
            tags=['route', 'plan', 'llm']
        ),
        lambda city, days, preferences="": _generate_route_plan(config_manager, city, days, preferences)
    ))

    return tools
