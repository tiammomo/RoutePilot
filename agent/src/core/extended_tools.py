"""
================================================================================
扩展旅游工具集 (Extended Travel Tools)

提供更丰富的旅游相关工具，包括：
- 住宿搜索 (search_hotels)
- 航班查询 (search_flights)
- 餐饮搜索 (search_restaurants)
- 天气查询 (query_weather)
- 交通查询 (query_traffic)
- 活动查询 (query_events)
- 智能行程生成 (generate_itinerary)
- 路线优化 (optimize_route)
- 价格比较 (compare_prices)
- 时间估算 (estimate_time)
- 季节推荐 (recommend_season)
- 活动推荐 (recommend_activities)

================================================================================
"""

import random
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


# ==============================================================================
# 住宿相关工具
# ==============================================================================

def search_hotels(
    config_manager,
    city: str,
    check_in: Optional[str] = None,
    check_out: Optional[str] = None,
    guests: int = 1,
    budget: Optional[str] = None
) -> Dict[str, Any]:
    """
    搜索酒店

    Args:
        city: 城市名称
        check_in: 入住日期 (YYYY-MM-DD)
        check_out: 退房日期 (YYYY-MM-DD)
        guests: 入住人数
        budget: 预算范围 (如 "300-500", "500以上")

    Returns:
        酒店列表
    """
    # 模拟酒店数据
    hotels = [
        {
            "name": f"{city}王府井希尔顿酒店",
            "location": "市中心",
            "rating": 4.8,
            "price_per_night": 680,
            "amenities": ["WiFi", "早餐", "停车场", "健身房"],
            "distance_to_center": "0.5km"
        },
        {
            "name": f"{city}锦江之星",
            "location": "火车站附近",
            "rating": 4.2,
            "price_per_night": 258,
            "amenities": ["WiFi", "24小时前台"],
            "distance_to_center": "2km"
        },
        {
            "name": f"{city}香格里拉大酒店",
            "location": "金融区",
            "rating": 4.9,
            "price_per_night": 1280,
            "amenities": ["WiFi", "早餐", "游泳池", "SPA", "健身房"],
            "distance_to_center": "3km"
        }
    ]

    # 根据预算过滤
    if budget:
        if "-" in budget:
            low, high = map(int, budget.split("-"))
            hotels = [h for h in hotels if low <= h["price_per_night"] <= high]
        elif "以上" in budget:
            min_price = int(budget.replace("以上", ""))
            hotels = [h for h in hotels if h["price_per_night"] >= min_price]

    return {
        "city": city,
        "hotels": hotels,
        "count": len(hotels),
        "search_params": {
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "budget": budget
        }
    }


def search_restaurants(
    config_manager,
    city: str,
    cuisine: Optional[str] = None,
    district: Optional[str] = None,
    budget_per_person: Optional[str] = None
) -> Dict[str, Any]:
    """
    搜索餐厅

    Args:
        city: 城市名称
        cuisine: 菜系 (如 "川菜", "粤菜", "火锅")
        district: 区域
        budget_per_person: 人均预算 (如 "50-100", "100-200")

    Returns:
        餐厅列表
    """
    restaurants = [
        {
            "name": f"{city}老北京炸酱面馆",
            "cuisine": "京菜",
            "district": "东城区",
            "rating": 4.5,
            "price_per_person": 45,
            "recommended_dishes": ["炸酱面", "豆汁儿", "焦圈"],
            "opening_hours": "07:00-21:00"
        },
        {
            "name": f"{city}川味坊",
            "cuisine": "川菜",
            "district": "朝阳区",
            "rating": 4.7,
            "price_per_person": 88,
            "recommended_dishes": ["麻婆豆腐", "水煮鱼", "回锅肉"],
            "opening_hours": "10:00-22:00"
        },
        {
            "name": f"{city}海底捞火锅",
            "cuisine": "火锅",
            "district": "海淀区",
            "rating": 4.8,
            "price_per_person": 120,
            "recommended_dishes": ["麻辣锅底", "牛肉卷", "虾滑"],
            "opening_hours": "24小时"
        },
        {
            "name": f"{city}粤菜酒家",
            "cuisine": "粤菜",
            "district": "西城区",
            "rating": 4.6,
            "price_per_person": 150,
            "recommended_dishes": ["烤鸭", "虾饺", "肠粉"],
            "opening_hours": "11:00-14:00, 17:00-21:30"
        }
    ]

    # 过滤
    if cuisine:
        restaurants = [r for r in restaurants if cuisine in r["cuisine"]]
    if district:
        restaurants = [r for r in restaurants if r["district"] == district]
    if budget_per_person:
        if "-" in budget_per_person:
            low, high = map(int, budget_per_person.split("-"))
            restaurants = [r for r in restaurants if low <= r["price_per_person"] <= high]

    return {
        "city": city,
        "restaurants": restaurants,
        "count": len(restaurants)
    }


# ==============================================================================
# 交通相关工具
# ==============================================================================

def search_flights(
    config_manager,
    from_city: str,
    to_city: str,
    departure_date: str,
    return_date: Optional[str] = None,
    passengers: int = 1
) -> Dict[str, Any]:
    """
    搜索航班

    Args:
        from_city: 出发城市
        to_city: 目的地城市
        departure_date: 出发日期 (YYYY-MM-DD)
        return_date: 返程日期 (可选)
        passengers: 乘客数量

    Returns:
        航班列表
    """
    flights = [
        {
            "airline": "中国国航",
            "flight_number": "CA1234",
            "departure_time": "08:30",
            "arrival_time": "10:45",
            "duration": "2h15m",
            "price": 680,
            "type": "直飞"
        },
        {
            "airline": "东方航空",
            "flight_number": "MU5678",
            "departure_time": "14:20",
            "arrival_time": "18:30",
            "duration": "4h10m",
            "price": 450,
            "type": "经停"
        },
        {
            "airline": "南方航空",
            "flight_number": "CZ9012",
            "departure_time": "19:00",
            "arrival_time": "21:15",
            "duration": "2h15m",
            "price": 820,
            "type": "直飞"
        }
    ]

    return {
        "from": from_city,
        "to": to_city,
        "departure_date": departure_date,
        "return_date": return_date,
        "passengers": passengers,
        "flights": flights,
        "count": len(flights)
    }


def query_traffic(
    config_manager,
    from_location: str,
    to_location: str,
    mode: str = "transit"
) -> Dict[str, Any]:
    """
    查询交通方式

    Args:
        from_location: 出发地
        to_location: 目的地
        mode: 交通方式 (transit/drive/taxi)

    Returns:
        交通方案
    """
    if mode == "transit":
        options = [
            {
                "type": "地铁",
                "route": "乘坐地铁1号线 → 换乘2号线",
                "duration": "35分钟",
                "cost": 5
            },
            {
                "type": "公交",
                "route": "乘坐公交22路 → 换乘18路",
                "duration": "55分钟",
                "cost": 3
            }
        ]
    elif mode == "drive":
        options = [
            {
                "type": "自驾",
                "route": "沿主干道行驶",
                "duration": "25分钟",
                "cost": 15,  # 停车费
                "distance": "12km"
            }
        ]
    else:
        options = [
            {
                "type": "出租车/网约车",
                "route": "全程",
                "duration": "20分钟",
                "cost": 45
            }
        ]

    return {
        "from": from_location,
        "to": to_location,
        "mode": mode,
        "options": options,
        "recommended": options[0] if options else None
    }


def estimate_time(
    config_manager,
    activity: str,
    location: str,
    group_size: int = 1
) -> Dict[str, Any]:
    """
    估算活动耗时

    Args:
        activity: 活动类型
        location: 地点
        group_size: 人数

    Returns:
        预估时间
    """
    time_estimates = {
        "故宫参观": {"min": 3, "max": 5, "unit": "小时"},
        "天安门广场": {"min": 0.5, "max": 1, "unit": "小时"},
        "长城游览": {"min": 4, "max": 6, "unit": "小时"},
        "颐和园游览": {"min": 2, "max": 4, "unit": "小时"},
        "故宫博物馆": {"min": 3, "max": 5, "unit": "小时"},
        "胡同游": {"min": 2, "max": 3, "unit": "小时"},
        "购物": {"min": 1, "max": 3, "unit": "小时"},
        "用餐": {"min": 1, "max": 2, "unit": "小时"}
    }

    estimate = time_estimates.get(activity, {"min": 1, "max": 2, "unit": "小时"})

    # 根据团队规模调整
    if group_size > 5:
        estimate["min"] += 0.5
        estimate["max"] += 1

    return {
        "activity": activity,
        "location": location,
        "group_size": group_size,
        "estimated_time": f"{estimate['min']}-{estimate['max']} {estimate['unit']}",
        "note": "实际时间可能因人流、天气等因素有所变化"
    }


# ==============================================================================
# 天气和活动相关工具
# ==============================================================================

def query_weather(
    config_manager,
    city: str,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    查询天气

    Args:
        city: 城市名称
        date: 日期 (YYYY-MM-DD)，默认为今天

    Returns:
        天气信息
    """
    weather_conditions = ["晴", "多云", "阴", "小雨", "晴转多云"]
    temps = range(15, 30)

    condition = random.choice(weather_conditions)
    temp = random.choice(list(temps))

    weather_info = {
        "city": city,
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "temperature": f"{temp}°C",
        "condition": condition,
        "humidity": f"{random.randint(40, 80)}%",
        "wind": f"{random.randint(5, 15)}km/h {random.choice(['东风', '南风', '西风', '北风'])}",
        "air_quality": random.choice(["优", "良", "轻度污染"]),
        "suggestion": _get_weather_suggestion(condition, temp)
    }

    return weather_info


def _get_weather_suggestion(condition: str, temp: int) -> str:
    """获取天气建议"""
    suggestions = []

    if "雨" in condition:
        suggestions.append("建议携带雨伞")
    if temp < 20:
        suggestions.append("建议携带薄外套")
    if temp > 26:
        suggestions.append("注意防晒，多喝水")

    if not suggestions:
        suggestions.append("天气适宜，适合外出")

    return "，".join(suggestions)


def query_events(
    config_manager,
    city: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    查询活动/事件

    Args:
        city: 城市名称
        start_date: 开始日期
        end_date: 结束日期
        category: 类别 (culture/exhibition/festival/sports)

    Returns:
        活动列表
    """
    events = [
        {
            "name": f"{city}国际马拉松",
            "category": "sports",
            "date": "2026-03-15",
            "location": "市中心广场",
            "price": 100,
            "description": "一年一度的国际马拉松赛事"
        },
        {
            "name": f"{city}艺术展",
            "category": "exhibition",
            "date": "2026-02-20至2026-03-10",
            "location": "国家博物馆",
            "price": 50,
            "description": "当代艺术作品展览"
        },
        {
            "name": f"{city}灯会",
            "category": "festival",
            "date": "2026-02-14",
            "location": "中山公园",
            "price": 0,
            "description": "传统元宵灯会活动"
        },
        {
            "name": f"{city}音乐会",
            "category": "culture",
            "date": "2026-02-28",
            "location": "音乐厅",
            "price": 280,
            "description": "交响乐演出"
        }
    ]

    # 过滤
    if category:
        events = [e for e in events if e["category"] == category]

    return {
        "city": city,
        "events": events,
        "count": len(events)
    }


def recommend_season(
    config_manager,
    destination: str
) -> Dict[str, Any]:
    """
    推荐最佳旅游季节

    Args:
        destination: 目的地

    Returns:
        季节推荐
    """
    season_info = {
        "北京": {
            "best_season": "春秋两季",
            "spring": "4-5月，气候宜人，适合赏花",
            "autumn": "9-10月，秋高气爽，适合登高",
            "summer": "6-8月，较热但可以避暑",
            "winter": "12-2月，较冷但有雪景"
        },
        "上海": {
            "best_season": "春秋两季",
            "spring": "3-5月，气候温和",
            "autumn": "9-11月，秋意渐浓",
            "summer": "6-8月，炎热多雨",
            "winter": "12-2月，湿冷"
        },
        "三亚": {
            "best_season": "冬季",
            "spring": "3-5月，气温适中",
            "autumn": "9-11月，台风季注意",
            "summer": "6-8月，炎热但便宜",
            "winter": "12-2月，温暖如夏"
        }
    }

    info = season_info.get(destination, {
        "best_season": "春秋两季",
        "spring": "气候宜人",
        "autumn": "秋高气爽",
        "summer": "注意防暑",
        "winter": "注意保暖"
    })

    return {
        "destination": destination,
        **info
    }


def recommend_activities(
    config_manager,
    city: str,
    days: int,
    preference: Optional[str] = None
) -> Dict[str, Any]:
    """
    推荐活动/体验

    Args:
        city: 城市名称
        days: 游玩天数
        preference: 偏好 (culture/nature/family/food)

    Returns:
        推荐活动列表
    """
    all_activities = {
        "北京": [
            {"name": "故宫深度游", "category": "culture", "duration": 4, "rating": 5},
            {"name": "八达岭长城", "category": "nature", "duration": 5, "rating": 5},
            {"name": "胡同骑游", "category": "culture", "duration": 2, "rating": 4},
            {"name": "天坛公园晨练", "category": "nature", "duration": 2, "rating": 4},
            {"name": "王府井美食", "category": "food", "duration": 2, "rating": 4}
        ],
        "上海": [
            {"name": "外滩夜景", "category": "culture", "duration": 2, "rating": 5},
            {"name": "迪士尼乐园", "category": "family", "duration": 1, "rating": 5},
            {"name": "豫园城隍庙", "category": "culture", "duration": 3, "rating": 4},
            {"name": "田子坊艺术区", "category": "culture", "duration": 2, "rating": 4},
            {"name": "上海美食探索", "category": "food", "duration": 3, "rating": 5}
        ]
    }

    activities = all_activities.get(city, [
        {"name": "城市观光", "category": "culture", "duration": 2, "rating": 4},
        {"name": "当地美食", "category": "food", "duration": 2, "rating": 4}
    ])

    # 根据偏好过滤
    if preference:
        activities = [a for a in activities if a["category"] == preference]

    # 根据天数推荐
    recommended = []
    total_time = 0
    for activity in activities:
        if total_time + activity["duration"] <= days * 8:  # 每天约8小时
            recommended.append(activity)
            total_time += activity["duration"]

    return {
        "city": city,
        "days": days,
        "preference": preference,
        "activities": recommended,
        "total_hours": total_time
    }


# ==============================================================================
# 路线规划相关工具
# ==============================================================================

def generate_itinerary(
    config_manager,
    city: str,
    days: int,
    interests: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    生成智能行程

    Args:
        city: 城市名称
        days: 天数
        interests: 兴趣标签 (culture/nature/food/shopping)

    Returns:
        每日行程安排
    """
    itinerary = []

    base_activities = {
        "北京": [
            ["天安门广场", "故宫", "景山公园"],
            ["八达岭长城", "明十三陵"],
            ["颐和园", "北京大学"],
            ["天坛公园", "前门大街", "王府井"],
            ["北海公园", "什刹海", "南锣鼓巷"]
        ],
        "上海": [
            ["外滩", "南京路", "豫园"],
            ["迪士尼乐园"],
            ["田子坊", "新天地", "思南路"],
            ["东方明珠", "陆家嘴", "科技馆"],
            ["朱家角古镇", "七宝古镇"]
        ]
    }

    activities = base_activities.get(city, [["城市观光"]] * days)

    for day in range(min(days, len(activities))):
        itinerary.append({
            "day": day + 1,
            "theme": _get_day_theme(day),
            "activities": activities[day] if day < len(activities) else ["自由活动"],
            "meals": {
                "breakfast": "酒店早餐",
                "lunch": "当地特色餐厅",
                "dinner": "美食街探索"
            },
            "tips": _get_day_tip(day, city)
        })

    return {
        "city": city,
        "total_days": days,
        "itinerary": itinerary,
        "estimated_cost": _estimate_trip_cost(city, days)
    }


def _get_day_theme(day: int) -> str:
    """获取每日主题"""
    themes = [
        "历史文化探索",
        "自然风光游览",
        "美食之旅",
        "现代都市体验",
        "休闲放松日"
    ]
    return themes[day % len(themes)]


def _get_day_tip(day: int, city: str) -> str:
    """获取每日提示"""
    tips = {
        "北京": [
            "建议提前预约故宫门票",
            "长城较远，建议穿舒适鞋子",
            "带好防晒用品",
            "胡同游可以租自行车",
            "最后一天可以购物"
        ],
        "上海": [
            "迪士尼建议工作日去",
            "外滩夜景最美",
            "田子坊适合拍照",
            "陆家嘴观景台视野好",
            "朱家角建议早去"
        ]
    }
    return tips.get(city, ["注意安全"])[day % 5]


def _estimate_trip_cost(city: str, days: int) -> Dict[str, Any]:
    """估算旅行费用"""
    cost_estimates = {
        "北京": {"budget": 500 * days, "mid": 1000 * days, "luxury": 2500 * days},
        "上海": {"budget": 450 * days, "mid": 900 * days, "luxury": 2200 * days},
        "三亚": {"budget": 400 * days, "mid": 800 * days, "luxury": 2000 * days}
    }

    default = {"budget": 400 * days, "mid": 800 * days, "luxury": 2000 * days}
    estimate = cost_estimates.get(city, default)

    return {
        "budget": f"约{estimate['budget']}元/经济型",
        "mid_range": f"约{estimate['mid']}元/舒适型",
        "luxury": f"约{estimate['luxury']}元/豪华型"
    }


def optimize_route(
    config_manager,
    attractions: List[str],
    start_point: Optional[str] = None,
    mode: str = "efficient"
) -> Dict[str, Any]:
    """
    优化游览路线

    Args:
        attractions: 景点列表
        start_point: 起始点
        mode: 优化模式 (efficient/shortest/ Scenic)

    Returns:
        优化后的路线
    """
    # 模拟路线优化
    optimized = {
        "efficient": "按位置分组，减少路程时间",
        "shortest": "选择最短路径",
        "scenic": "选择风景最优美的路线"
    }

    route = []
    if start_point:
        route.append(start_point)

    route.extend(attractions)

    return {
        "original_count": len(attractions),
        "optimized_route": route,
        "optimization_type": mode,
        "description": optimized.get(mode, optimized["efficient"]),
        "estimated_savings": "约30%路程时间"
    }


def compare_prices(
    config_manager,
    items: List[str],
    cities: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    比较价格

    Args:
        items: 要比较的商品/服务
        cities: 城市列表

    Returns:
        价格比较结果
    """
    if not cities:
        cities = ["北京", "上海"]

    comparison = {}

    for item in items:
        prices = {}
        for city in cities:
            # 模拟价格数据
            base_price = random.randint(100, 500)
            prices[city] = {
                "min": int(base_price * 0.8),
                "average": base_price,
                "max": int(base_price * 1.3)
            }

        comparison[item] = {
            "prices": prices,
            "best_city": min(cities, key=lambda c: prices[c]["average"]),
            "savings": max(prices[c]["average"] for c in cities) -
                       min(prices[c]["average"] for c in cities)
        }

    return {
        "items": items,
        "cities": cities,
        "comparison": comparison,
        "recommendation": f"推荐在{comparison[items[0]]['best_city']}购买"
    }


# ==============================================================================
# 工具注册函数
# ==============================================================================

def create_extended_tools(config_manager) -> list:
    """
    创建扩展工具列表

    Returns:
        [(ToolInfo, executor), ...]
    """
    from core.react_agent import ToolInfo

    tools = []

    # 住宿
    tools.append((
        ToolInfo(
            name="search_hotels",
            description="搜索酒店住宿信息，支持按城市、日期、人数、预算筛选",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, check_in=None, check_out=None, guests=1, budget=None:
            search_hotels(config_manager, city, check_in, check_out, guests, budget)
    ))

    # 餐饮
    tools.append((
        ToolInfo(
            name="search_restaurants",
            description="搜索餐厅，支持按城市、菜系、区域、预算筛选",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, cuisine=None, district=None, budget_per_person=None:
            search_restaurants(config_manager, city, cuisine, district, budget_per_person)
    ))

    # 航班
    tools.append((
        ToolInfo(
            name="search_flights",
            description="搜索航班信息，支持单程和往返",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda from_city, to_city, departure_date, return_date=None, passengers=1:
            search_flights(config_manager, from_city, to_city, departure_date, return_date, passengers)
    ))

    # 交通
    tools.append((
        ToolInfo(
            name="query_traffic",
            description="查询两地之间的交通方式",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda from_location, to_location, mode="transit":
            query_traffic(config_manager, from_location, to_location, mode)
    ))

    # 时间估算
    tools.append((
        ToolInfo(
            name="estimate_time",
            description="估算活动/景点游览所需时间",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda activity, location, group_size=1:
            estimate_time(config_manager, activity, location, group_size)
    ))

    # 天气
    tools.append((
        ToolInfo(
            name="query_weather",
            description="查询城市天气预报和出行建议",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, date=None:
            query_weather(config_manager, city, date)
    ))

    # 活动
    tools.append((
        ToolInfo(
            name="query_events",
            description="查询城市正在进行的活动/事件",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, start_date=None, end_date=None, category=None:
            query_events(config_manager, city, start_date, end_date, category)
    ))

    # 季节推荐
    tools.append((
        ToolInfo(
            name="recommend_season",
            description="推荐目的地的最佳旅游季节",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda destination:
            recommend_season(config_manager, destination)
    ))

    # 活动推荐
    tools.append((
        ToolInfo(
            name="recommend_activities",
            description="根据天数和偏好推荐活动",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, days, preference=None:
            recommend_activities(config_manager, city, days, preference)
    ))

    # 行程生成
    tools.append((
        ToolInfo(
            name="generate_itinerary",
            description="生成智能行程安排",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda city, days, interests=None:
            generate_itinerary(config_manager, city, days, interests)
    ))

    # 路线优化
    tools.append((
        ToolInfo(
            name="optimize_route",
            description="优化景点游览路线",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda attractions, start_point=None, mode="efficient":
            optimize_route(config_manager, attractions, start_point, mode)
    ))

    # 价格比较
    tools.append((
        ToolInfo(
            name="compare_prices",
            description="比较不同城市的价格",
            parameters={"type": "object", "properties": {}},
            category="travel"
        ),
        lambda items, cities=None:
            compare_prices(config_manager, items, cities)
    ))

    return tools
