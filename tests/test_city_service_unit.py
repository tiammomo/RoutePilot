"""Unit tests for the refactored city service facade."""

from __future__ import annotations

import sys
from pathlib import Path

from pytest import mark

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.services.city_service import CityService  # noqa: E402


def test_city_service_filters_by_region_and_tags():
    service = CityService()

    east_cities = service.list_cities(region="华东")
    food_or_leisure_cities = service.list_cities(tags="美食, 休闲, ,美食")

    assert east_cities
    assert all(item["region"] == "华东" for item in east_cities)
    assert food_or_leisure_cities
    assert any("美食" in item["tags"] for item in food_or_leisure_cities)
    assert any("休闲" in item["tags"] for item in food_or_leisure_cities)


def test_city_service_detail_and_attractions_return_copies():
    service = CityService()
    city = service.find_city("beijing")

    assert city is not None
    detail = service.build_city_detail(city)
    attractions = service.build_attractions(str(city["name"]))
    assert detail["id"] == "beijing"
    assert attractions

    detail["name"] = "mutated"
    attractions[0]["name"] = "mutated"

    fresh_detail = service.build_city_detail(city)
    fresh_attractions = service.build_attractions(str(city["name"]))
    assert fresh_detail["name"] == "北京"
    assert fresh_attractions[0]["name"] != "mutated"


def test_city_service_lists_sorted_regions_and_tags():
    service = CityService()

    regions = service.list_regions()
    tags = service.list_tags()

    assert regions == sorted(regions)
    assert len(regions) == len(set(regions))
    assert tags == sorted(tags)
    assert len(tags) == len(set(tags))


@mark.parametrize(
    ("city_id", "city_name"),
    [
        ("not-exists", "不存在城市"),
        ("missing", "Missing City"),
    ],
)
def test_city_service_handles_missing_cities(city_id: str, city_name: str):
    service = CityService()

    assert service.find_city(city_id) is None
    assert service.build_attractions(city_name) == []
