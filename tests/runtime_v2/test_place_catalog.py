"""Reviewed place-catalog quality and closure filtering tests."""

from __future__ import annotations

from datetime import date

from agent.travel_agent.runtime_v2 import ApprovedPlaceCatalog


def test_beijing_catalog_returns_distinct_officially_sourced_places() -> None:
    places = ApprovedPlaceCatalog().search(
        "北京",
        local_date=date(2026, 7, 21),
        query="历史文化 少排队",
        limit=8,
    )

    assert len(places) >= 6
    assert len({item.slug for item in places}) == len(places)
    assert all(item.source_uri.startswith("https://") for item in places)
    assert all(item.duration_minutes >= 60 for item in places)
    assert [item.name for item in places[:4]] == [
        "天坛公园",
        "前门大街与大栅栏历史街区",
        "景山公园",
        "什刹海历史文化街区",
    ]
    assert {"故宫博物院", "中国国家博物馆"}.issubset(
        {item.name for item in places}
    )


def test_beijing_catalog_excludes_known_monday_closures() -> None:
    places = ApprovedPlaceCatalog().search(
        "北京市",
        local_date=date(2026, 7, 20),
        query="历史文化",
        limit=8,
    )

    names = {item.name for item in places}
    assert "故宫博物院" not in names
    assert "中国国家博物馆" not in names
    assert {"天坛公园", "景山公园", "什刹海历史文化街区"}.issubset(names)


def test_catalog_fails_closed_for_unsupported_destinations() -> None:
    assert ApprovedPlaceCatalog().search(
        "未受审城市",
        local_date=date(2026, 7, 21),
        query="景点",
        limit=4,
    ) == ()
