"""
================================================================================
LangChain 旅游工具集
================================================================================

使用 LangChain @tool 装饰器定义的旅游相关工具。

支持两种模式:
1. 使用模拟数据（默认）
2. 使用真实 API（通过 travel_api.py）

工具列表:
- search_cities: 搜索旅游城市
- query_attractions: 查询城市景点
- query_hotels: 查询酒店信息
- calculate_budget: 计算旅行预算
- plan_itinerary: 规划行程路线
- get_travel_tips: 获取旅行建议
- get_weather: 获取天气预报

使用示例:
```python
from tools.travel_tools import get_travel_tools

# 获取所有工具
tools = get_travel_tools()

# 或者单独使用
from tools.travel_tools import search_cities, query_attractions
result = search_cities.invoke({"query": "北京"})
```

================================================================================
"""

import logging
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool, Tool
import json

# 配置日志
logger = logging.getLogger("agent.tools")

# 尝试导入真实 API 客户端
try:
    from tools.travel_api import get_travel_api_client, TravelAPIClient
    USE_REAL_API = True
except ImportError as e:
    USE_REAL_API = False
    logger.warning(f"Travel API client not available, using mock data: {e}")


# ============================================================================
# 工具实现
# ============================================================================

@tool
def search_cities(query: str) -> str:
    """
    搜索旅游城市

    根据关键词搜索推荐旅游城市，返回城市基本信息和小贴士。

    Args:
        query: 搜索关键词，可以是:
            - 城市名（如"北京"、"上海"）
            - 旅游类型（如"海滨"、"山地"）
            - 季节（如"冬季"、"夏季"）

    Returns:
        城市列表信息，包含城市名、简介、最佳旅行时间等
    """
    # 使用真实 API
    if USE_REAL_API:
        import asyncio
        client = get_travel_api_client()

        # 运行异步调用
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            cities = loop.run_until_complete(client.search_cities(query))

            if cities:
                output = "为您找到以下城市：\n\n"
                for city in cities:
                    output += f"📍 {city['name']} ({city['province']})\n"
                    output += f"   简介：{city['description']}\n"
                    output += f"   必游景点：{', '.join(city['highlights'][:3])}\n"
                    output += f"   最佳旅行时间：{city['best_time']}\n"
                    output += f"   评分：{'⭐' * int(city['rating'])}\n\n"
                return output
            else:
                return f"未找到与「{query}」相关的城市信息。"

        except Exception as e:
            logger.error(f"Failed to search cities with API: {e}", extra={"query": query})

    # 回退到模拟数据（API 调用失败时自动降级）
    city_database = {
        "北京": {
            "name": "北京",
            "description": "中国的首都，拥有悠久的历史和丰富的文化遗产",
            "highlights": ["故宫", "长城", "天安门", "颐和园"],
            "best_time": "春秋季节",
            "weather": "四季分明"
        },
        "上海": {
            "name": "上海",
            "description": "国际化大都市，中西文化交融",
            "highlights": ["外滩", "东方明珠", "豫园", "田子坊"],
            "best_time": "春秋季节",
            "weather": "亚热带季风气候"
        },
        "三亚": {
            "name": "三亚",
            "description": "海南岛最南端的热带海滨旅游城市",
            "highlights": ["亚龙湾", "天涯海角", "蜈支洲岛"],
            "best_time": "10月-次年3月",
            "weather": "热带季风气候"
        },
        "云南": {
            "name": "云南",
            "description": "七彩云南，拥有多元民族文化和壮丽自然风光",
            "highlights": ["丽江古城", "大理", "石林", "香格里拉"],
            "best_time": "春秋季节",
            "weather": "高原季风气候"
        }
    }

    query = query.strip()
    results = []

    if query in city_database:
        results.append(city_database[query])
    else:
        for city_name, city_info in city_database.items():
            if query in city_name or query in city_info.get("description", ""):
                results.append(city_info)

    if results:
        output = "为您找到以下城市：\n\n"
        for city in results:
            output += f"📍 {city['name']}\n"
            output += f"   简介：{city['description']}\n"
            output += f"   必游景点：{', '.join(city['highlights'][:3])}\n"
            output += f"   最佳旅行时间：{city['best_time']}\n"
            output += f"   气候：{city['weather']}\n\n"
        return output
    else:
        return f"未找到与「{query}」相关的城市信息。请尝试其他关键词，如：北京、上海、三亚、云南等。"


@tool
def query_attractions(city: str, category: Optional[str] = None) -> str:
    """
    查询城市景点

    获取特定城市的景点信息，支持按类别筛选。

    Args:
        city: 城市名称（如"北京"、"三亚"）
        category: 景点类别（可选），可选值：
            - natural: 自然风光
            - historical: 历史遗迹
            - entertainment: 娱乐休闲
            - food: 美食特产

    Returns:
        景点列表详细信息
    """
    # 使用真实 API
    if USE_REAL_API:
        import asyncio
        client = get_travel_api_client()

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(client.search_attractions(city, category))

            if result["data"]:
                output = f"🏞️ {city}景点推荐：\n\n"
                for att in result["data"]:
                    output += f"📌 {att['name']}\n"
                    output += f"   简介：{att['desc']}\n"
                    output += f"   门票：{att['ticket']}\n"
                    output += f"   开放时间：{att['hours']}\n"
                    output += f"   评分：{'⭐' * int(att['rating'])}\n"
                    output += f"   地址：{att.get('address', '暂无')}\n\n"
                return output
            else:
                return f"暂未找到「{city}」的景点信息"

        except Exception as e:
            logger.error(f"Failed to query attractions with API: {e}", extra={"city": city, "category": category})

    # 模拟数据
    attractions_db = {
        "北京": {
            "historical": [
                {"name": "故宫", "desc": "明清两代皇家宫殿", "ticket": "60元", "hours": "8:30-17:00"},
                {"name": "长城", "desc": "中国古代伟大工程", "ticket": "40-65元", "hours": "7:00-18:00"},
                {"name": "天坛", "desc": "皇帝祭天祈谷场所", "ticket": "34元", "hours": "6:30-21:00"}
            ],
            "natural": [
                {"name": "颐和园", "desc": "清代皇家园林", "ticket": "30元", "hours": "6:30-18:00"},
                {"name": "北海公园", "desc": "历史悠久的皇家园林", "ticket": "10元", "hours": "6:00-21:00"}
            ]
        },
        "三亚": {
            "natural": [
                {"name": "亚龙湾", "desc": "天下第一湾", "ticket": "免费", "hours": "全天"},
                {"name": "蜈支洲岛", "desc": "海岛度假胜地", "ticket": "168元", "hours": "8:00-18:30"},
                {"name": "天涯海角", "desc": "经典打卡地标", "ticket": "81元", "hours": "7:30-18:30"}
            ],
            "entertainment": [
                {"name": "亚特兰蒂斯", "desc": "水上乐园", "ticket": "298元", "hours": "10:00-22:00"}
            ]
        }
    }

    if city not in attractions_db:
        return f"抱歉，暂未收录「{city}」的景点信息。"

    attractions = attractions_db.get(city, {})

    if category and category in attractions:
        filtered = attractions[category]
    elif category:
        return f"「{city}」暂无「{category}」类景点"
    else:
        filtered = []
        for cat_attractions in attractions.values():
            filtered.extend(cat_attractions)

    if not filtered:
        return f"暂未找到「{city}」的景点信息"

    output = f"🏞️ {city}景点推荐：\n\n"
    for att in filtered:
        cat_display = category if category else "景点"
        output += f"📌 {att['name']} [{cat_display}]\n"
        output += f"   简介：{att['desc']}\n"
        output += f"   门票：{att['ticket']}\n"
        output += f"   开放时间：{att['hours']}\n\n"

    return output


@tool
def query_hotels(city: str, district: Optional[str] = None) -> str:
    """
    查询酒店信息

    获取特定城市的酒店信息。

    Args:
        city: 城市名称
        district: 商圈/区域（可选）

    Returns:
        酒店列表
    """
    if USE_REAL_API:
        import asyncio
        client = get_travel_api_client()

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(client.search_hotels(city, district))

            if result["data"]:
                output = f"🏨 {city}酒店推荐：\n\n"
                for hotel in result["data"]:
                    output += f"📌 {hotel['name']}\n"
                    output += f"   区域：{hotel['district']}\n"
                    output += f"   评分：{'⭐' * int(hotel['rating'])}\n"
                    output += f"   价格：¥{hotel['price']}/晚\n\n"
                return output
            else:
                return f"暂未找到「{city}」的酒店信息"

        except Exception as e:
            logger.error(f"Failed to query hotels with API: {e}", extra={"city": city, "district": district})

    return f"正在查询「{city}」酒店信息..."


@tool
def calculate_budget(
    destination: str,
    days: int,
    people: int = 1,
    accommodation_level: str = "medium"
) -> str:
    """
    计算旅行预算

    根据目的地、天数、人数和住宿等级估算旅行费用。

    Args:
        destination: 目的地城市
        days: 旅行天数
        people: 出行人数，默认1人
        accommodation_level: 住宿等级，可选：
            - economy: 经济型
            - medium: 中档
            - luxury: 豪华型

    Returns:
        预算明细表
    """
    base_costs = {
        "economy": {"food": 100, "transport": 50, "ticket": 80},
        "medium": {"food": 200, "transport": 100, "ticket": 150},
        "luxury": {"food": 500, "transport": 300, "ticket": 300}
    }

    hotel_costs = {
        "economy": 200,
        "medium": 500,
        "luxury": 1500
    }

    costs = base_costs.get(accommodation_level, base_costs["medium"])
    hotel_per_night = hotel_costs.get(accommodation_level, 500)

    total_food = costs["food"] * days * people
    total_transport = costs["transport"] * days * people
    total_ticket = costs["ticket"] * days * people
    total_hotel = hotel_per_night * (days - 1) * people

    total = total_food + total_transport + total_ticket + total_hotel

    output = f"💰 {destination} {days}天 {people}人 {accommodation_level}级别预算\n\n"
    output += f"┌─────────────┬────────────┐\n"
    output += f"│ 项目       │ 费用(元)   │\n"
    output += f"├─────────────┼────────────┤\n"
    output += f"│ 餐饮       │ {total_food:>10} │\n"
    output += f"│ 交通       │ {total_transport:>10} │\n"
    output += f"│ 门票       │ {total_ticket:>10} │\n"
    output += f"│ 住宿       │ {total_hotel:>10} │\n"
    output += f"├─────────────┼────────────┤\n"
    output += f"│ 合计       │ {total:>10} │\n"
    output += f"└─────────────┴────────────┘\n\n"
    output += f"📝 备注：以上为估算费用，实际可能因季节、具体行程有所差异。"

    return output


@tool
def plan_itinerary(
    destination: str,
    days: int,
    interests: Optional[str] = None
) -> str:
    """
    规划旅行路线

    根据目的地、天数和兴趣偏好生成详细行程安排。

    Args:
        destination: 目的地城市
        days: 旅行天数
        interests: 兴趣偏好（可选），如"历史人文"、"自然风光"、"美食"

    Returns:
        每日行程安排
    """
    itinerary_templates = {
        "北京": [
            ["天安门广场", "故宫", "王府井"],
            ["长城", "鸟巢", "水立方"],
            ["颐和园", "北京大学", "清华校园"],
            ["天坛", "雍和宫", "南锣鼓巷"],
            ["北海公园", "什刹海", "胡同游"]
        ],
        "上海": [
            ["外滩", "南京路", "豫园"],
            ["东方明珠", "陆家嘴", "磁悬浮"],
            ["田子坊", "新天地", "思南路"],
            ["上海迪士尼乐园"],
            ["朱家角", "七宝古镇"]
        ],
        "三亚": [
            ["亚龙湾", "海底世界"],
            ["蜈支洲岛", "海滨浴场"],
            ["天涯海角", "南山文化旅游区"],
            ["大小洞天", "椰梦长廊"],
            ["亚特兰蒂斯", "免税店"]
        ]
    }

    template = itinerary_templates.get(destination, [[f"自由探索{destination}"]] * days)

    output = f"🗓️ {destination} {days}日游行程规划\n\n"

    for i, day_plan in enumerate(template[:days], 1):
        output += f"📅 第{i}天\n"
        for j, spot in enumerate(day_plan, 1):
            output += f"   {j}. {spot}\n"
        output += "\n"

    if interests:
        output += f"💡 特别建议：根据您的「{interests}」兴趣，建议增加相关体验。\n"

    return output


@tool
def get_travel_tips(destination: str, season: Optional[str] = None) -> str:
    """
    获取旅行建议

    获取特定目的地或季节的旅行注意事项和小贴士。

    Args:
        destination: 目的地城市
        season: 旅行季节（可选），如"春季"、"夏季"、"秋季"、"冬季"

    Returns:
        旅行建议列表
    """
    tips_db = {
        "北京": {
            "general": [
                "提前预约故宫门票，现场可能无票",
                "长城建议穿舒适的鞋子",
                "秋季是最佳旅游季节",
                "地铁是最便捷的交通方式"
            ],
            "spring": ["早晚温差大，建议带薄外套", "春季可能有沙尘暴"],
            "summer": ["天气炎热，注意防暑", "多喝水，带遮阳帽"],
            "autumn": ["最佳旅游季节", "红叶观赏期10-11月"],
            "winter": ["天气寒冷，注意保暖", "暖气很足，室内外温差大"]
        },
        "三亚": {
            "general": [
                "带好防晒霜，紫外线强",
                "准备好泳衣和沙滩装备",
                "提前预订酒店和机票",
                "注意海上安全"
            ],
            "summer": ["台风季节，关注天气预报", "高温潮湿，注意防暑"],
            "winter": ["最佳旅游季节", "温暖如春"]
        }
    }

    tips = tips_db.get(destination, {}).get("general", [])

    if season:
        season_key = season.replace("季", "").lower()
        seasonal_tips = tips_db.get(destination, {}).get(season_key, [])
        tips.extend(seasonal_tips)

    if not tips:
        return f"暂未收录「{destination}」的旅行建议"

    output = f"📋 {destination} 旅行建议：\n\n"
    for i, tip in enumerate(tips, 1):
        output += f"{i}. {tip}\n"

    return output


@tool
def get_weather(city: str, days: int = 7) -> str:
    """
    获取天气预报

    获取目的地未来几天的天气情况。

    Args:
        city: 城市名称
        days: 查询天数，默认7天

    Returns:
        天气预报信息
    """
    if USE_REAL_API:
        import asyncio
        client = get_travel_api_client()

        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(client.get_weather(city, days))

            output = f"🌤️ {city}天气预报：\n\n"

            # 当前天气
            current = result.get("current", {})
            output += f"📍 当前：{current.get('weather', '未知')} {current.get('temp', '--')}°C\n"
            output += f"   湿度：{current.get('humidity', '--')}%  风力：{current.get('wind', '--')}\n\n"

            # 预报
            forecast = result.get("forecast", [])
            if forecast:
                output += "📅 预报：\n"
                for day in forecast[:days]:
                    output += f"   {day['date']}: {day['weather']} {day['temp_low']}~{day['temp_high']}°C\n"

            return output

        except Exception as e:
            logger.error(f"Failed to get weather with API: {e}", extra={"city": city, "days": days})

    return f"正在查询「{city}」{days}天内的天气情况..."


# ============================================================================
# 工具注册
# ============================================================================

def get_travel_tools() -> list[Tool]:
    """
    获取所有旅游相关工具

    Returns:
        LangChain Tool 对象列表
    """
    return [
        search_cities,
        query_attractions,
        query_hotels,
        calculate_budget,
        plan_itinerary,
        get_travel_tips,
        get_weather
    ]


def get_tool_by_name(name: str) -> Optional[Tool]:
    """
    根据名称获取工具

    Args:
        name: 工具名称

    Returns:
        Tool 对象，如果不存在返回 None
    """
    tools_map = {
        "search_cities": search_cities,
        "query_attractions": query_attractions,
        "query_hotels": query_hotels,
        "calculate_budget": calculate_budget,
        "plan_itinerary": plan_itinerary,
        "get_travel_tips": get_travel_tips,
        "get_weather": get_weather
    }
    return tools_map.get(name)
