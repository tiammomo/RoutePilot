"""
扩展工具集单元测试
"""

import pytest
from core.extended_tools import (
    search_hotels,
    search_restaurants,
    search_flights,
    query_traffic,
    estimate_time,
    query_weather,
    query_events,
    recommend_season,
    recommend_activities,
    generate_itinerary,
    optimize_route,
    compare_prices,
    create_extended_tools
)


class TestSearchHotels:
    """酒店搜索测试"""

    def test_search_hotels_basic(self):
        """测试基本搜索"""
        # 使用 None 作为 config_manager
        result = search_hotels(None, "北京")
        assert "hotels" in result
        assert result["city"] == "北京"
        assert result["count"] > 0

    def test_search_hotels_with_budget(self):
        """测试预算筛选"""
        result = search_hotels(None, "北京", budget="300-500")
        assert all(h["price_per_night"] <= 500 for h in result["hotels"])


class TestSearchRestaurants:
    """餐厅搜索测试"""

    def test_search_restaurants_basic(self):
        """测试基本搜索"""
        result = search_restaurants(None, "北京")
        assert "restaurants" in result
        assert result["city"] == "北京"

    def test_search_restaurants_cuisine(self):
        """测试菜系筛选"""
        result = search_restaurants(None, "北京", cuisine="川菜")
        assert len(result["restaurants"]) > 0


class TestSearchFlights:
    """航班搜索测试"""

    def test_search_flights_basic(self):
        """测试基本搜索"""
        result = search_flights(None, "北京", "上海", "2026-03-01")
        assert "flights" in result
        assert result["from"] == "北京"
        assert result["to"] == "上海"


class TestQueryTraffic:
    """交通查询测试"""

    def test_query_traffic_transit(self):
        """测试公共交通"""
        result = query_traffic(None, "天安门", "故宫", mode="transit")
        assert "options" in result
        assert len(result["options"]) > 0

    def test_query_traffic_drive(self):
        """测试自驾"""
        result = query_traffic(None, "天安门", "长城", mode="drive")
        assert result["mode"] == "drive"


class TestEstimateTime:
    """时间估算测试"""

    def test_estimate_time_basic(self):
        """测试基本估算"""
        result = estimate_time(None, "故宫参观", "北京")
        assert "estimated_time" in result

    def test_estimate_time_group_size(self):
        """测试团队规模影响"""
        result1 = estimate_time(None, "故宫参观", "北京", group_size=1)
        result2 = estimate_time(None, "故宫参观", "北京", group_size=10)
        # 人数多，时间更长
        assert result1["estimated_time"] != result2["estimated_time"]


class TestQueryWeather:
    """天气查询测试"""

    def test_query_weather_basic(self):
        """测试基本天气查询"""
        result = query_weather(None, "北京")
        assert "temperature" in result
        assert "condition" in result
        assert "suggestion" in result


class TestQueryEvents:
    """活动查询测试"""

    def test_query_events_basic(self):
        """测试基本活动查询"""
        result = query_events(None, "北京")
        assert "events" in result

    def test_query_events_category(self):
        """测试分类筛选"""
        result = query_events(None, "北京", category="culture")
        assert all(e["category"] == "culture" for e in result["events"])


class TestRecommendSeason:
    """季节推荐测试"""

    def test_recommend_season_known_city(self):
        """测试已知城市"""
        result = recommend_season(None, "北京")
        assert "best_season" in result
        assert "spring" in result

    def test_recommend_season_unknown_city(self):
        """测试未知城市"""
        result = recommend_season(None, "某城市")
        assert "best_season" in result


class TestRecommendActivities:
    """活动推荐测试"""

    def test_recommend_activities_basic(self):
        """测试基本推荐"""
        result = recommend_activities(None, "北京", 3)
        assert "activities" in result

    def test_recommend_activities_with_preference(self):
        """测试偏好筛选"""
        result = recommend_activities(None, "北京", 3, preference="culture")
        assert all(a["category"] == "culture" for a in result["activities"])


class TestGenerateItinerary:
    """行程生成测试"""

    def test_generate_itinerary_basic(self):
        """测试基本行程生成"""
        result = generate_itinerary(None, "北京", 3)
        assert "itinerary" in result
        assert result["total_days"] == 3

    def test_generate_itinerary_days(self):
        """测试不同天数"""
        result = generate_itinerary(None, "上海", 5)
        assert len(result["itinerary"]) == 5


class TestOptimizeRoute:
    """路线优化测试"""

    def test_optimize_route_basic(self):
        """测试基本路线优化"""
        result = optimize_route(None, ["故宫", "长城", "天坛"])
        assert "optimized_route" in result

    def test_optimize_route_with_start(self):
        """测试带起始点"""
        result = optimize_route(None, ["故宫", "长城"], start_point="天安门")
        assert result["optimized_route"][0] == "天安门"


class TestComparePrices:
    """价格比较测试"""

    def test_compare_prices_basic(self):
        """测试基本价格比较"""
        result = compare_prices(None, ["酒店", "门票"])
        assert "comparison" in result

    def test_compare_prices_cities(self):
        """测试多城市比较"""
        result = compare_prices(None, ["酒店"], cities=["北京", "上海"])
        assert len(result["cities"]) == 2


class TestCreateExtendedTools:
    """工具创建测试"""

    def test_create_extended_tools(self):
        """测试工具创建"""
        tools = create_extended_tools(None)
        assert len(tools) > 0

    def test_tool_names(self):
        """测试工具名称"""
        tools = create_extended_tools(None)
        # 检查返回的工具数量
        assert len(tools) > 10
        # 至少有这几个工具
        tool_str = str(tools)
        assert "search_hotels" in tool_str
        assert "search_restaurants" in tool_str
        assert "query_weather" in tool_str


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
