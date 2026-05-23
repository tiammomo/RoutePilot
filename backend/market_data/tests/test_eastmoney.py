from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantpilot_market_data.api import create_app
from quantpilot_market_data.cache import MarketDataCache
from quantpilot_market_data.fundamentals import build_fundamental_indicators
from quantpilot_market_data.indicators import build_technical_indicators
from quantpilot_market_data.providers.eastmoney import (
    normalize_secid,
    parse_announcements_payload,
    parse_financial_reports_payload,
    parse_kline_payload,
    parse_quote_payload,
    parse_symbol_suggest_payload,
    parse_tencent_kline_payload,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("600519", "1.600519"),
        ("SH600519", "1.600519"),
        ("000001", "0.000001"),
        ("SZ000001", "0.000001"),
        ("300750", "0.300750"),
        ("1.600519", "1.600519"),
        ("0.000001", "0.000001"),
    ],
)
def test_normalize_secid(raw: str, expected: str) -> None:
    assert normalize_secid(raw) == expected


def test_parse_quote_payload_scales_fields() -> None:
    quote = parse_quote_payload(
        "1.600519",
        {
            "rc": 0,
            "rt": 11,
            "data": {
                "total": 1,
                "diff": [
                    {
                        "f2": 1290.2,
                        "f3": -1.59,
                        "f4": -20.8,
                        "f5": 49157,
                        "f6": 6372389482.0,
                        "f12": "600519",
                        "f13": 1,
                        "f14": "贵州茅台",
                        "f15": 1311.91,
                        "f16": 1290.12,
                        "f17": 1310.95,
                        "f18": 1311.0,
                        "f20": 1615679031393,
                        "f21": 1615679031393,
                        "f124": 1779437507,
                    }
                ],
            },
        },
    )

    assert quote.symbol == "600519"
    assert quote.secid == "1.600519"
    assert quote.name == "贵州茅台"
    assert quote.market == "SH"
    assert quote.price == Decimal("1290.2")
    assert quote.open == Decimal("1310.95")
    assert quote.high == Decimal("1311.91")
    assert quote.low == Decimal("1290.12")
    assert quote.previous_close == Decimal("1311.0")
    assert quote.change_percent == Decimal("-1.59")
    assert quote.volume == 49157
    assert quote.amount == Decimal("6372389482.0")
    assert quote.quote_time == datetime.fromtimestamp(1779437507, tz=UTC)


def test_parse_symbol_suggest_payload() -> None:
    results = parse_symbol_suggest_payload(
        "茅台",
        {
            "QuotationCodeTable": {
                "Data": [
                    {
                        "Code": "600519",
                        "Name": "贵州茅台",
                        "QuoteID": "1.600519",
                        "PinYin": "GZMT",
                    }
                ]
            }
        },
    )

    assert len(results) == 1
    assert results[0].symbol == "600519"
    assert results[0].name == "贵州茅台"
    assert results[0].market == "SH"
    assert results[0].secid == "1.600519"


def test_parse_kline_payload() -> None:
    kline = parse_kline_payload(
        "1.600519",
        "daily",
        "qfq",
        {
            "rc": 0,
            "data": {
                "code": "600519",
                "market": 1,
                "name": "贵州茅台",
                "klines": [
                    "2026-05-22,1310.95,1290.20,1311.91,1290.12,49157,6372389482.00,1.66,-1.59,-20.80,0.39"
                ],
            },
        },
    )

    assert kline.symbol == "600519"
    assert kline.market == "SH"
    assert kline.bars[0].date == "2026-05-22"
    assert kline.bars[0].open == Decimal("1310.95")
    assert kline.bars[0].close == Decimal("1290.20")
    assert kline.bars[0].turnover == Decimal("0.39")


def test_parse_tencent_kline_payload() -> None:
    kline = parse_tencent_kline_payload(
        "0.002156",
        "daily",
        "qfq",
        {
            "code": 0,
            "data": {
                "sz002156": {
                    "qfqday": [
                        ["2026-05-21", "64.000", "61.760", "66.880", "61.410", "2396680.000"],
                        ["2026-05-22", "61.810", "63.440", "64.340", "60.130", "2008252.000"],
                    ],
                    "qt": {"sz002156": ["51", "通富微电", "002156"]},
                }
            },
        },
    )

    assert kline.symbol == "002156"
    assert kline.name == "通富微电"
    assert kline.source == "tencent"
    assert kline.market == "SZ"
    assert kline.bars[1].date == "2026-05-22"
    assert kline.bars[1].open == Decimal("61.810")
    assert kline.bars[1].close == Decimal("63.440")
    assert kline.bars[1].change_percent is not None
    assert kline.bars[1].volume == 2008252


def test_build_technical_indicators_from_kline() -> None:
    kline = parse_kline_payload(
        "1.600519",
        "daily",
        "qfq",
        {
            "rc": 0,
            "data": {
                "code": "600519",
                "market": 1,
                "name": "贵州茅台",
                "klines": [build_kline_test_row(day) for day in range(1, 22)],
            },
        },
    )

    indicators = build_technical_indicators(kline)

    assert indicators.symbol == "600519"
    assert len(indicators.points) == 21
    assert indicators.points[4].ma5 == Decimal("103.0000")
    assert indicators.points[19].ma20 == Decimal("110.5000")
    assert indicators.points[-1].return_pct is not None
    assert indicators.summary.latest_close == Decimal("121")
    assert indicators.summary.period_return_pct == Decimal("19.8020")
    assert indicators.summary.max_drawdown_pct == Decimal("0.0000")
    assert indicators.summary.volatility_annualized_pct is not None


def build_kline_test_row(day: int) -> str:
    open_price = 100 + day
    close_price = 100 + day
    high_price = 101 + day
    low_price = 99 + day
    volume = 1000 + day
    return (
        f"2026-05-{day:02d},{open_price},{close_price},{high_price},"
        f"{low_price},{volume},10000,1,1,1,1"
    )


def test_parse_financial_reports_payload() -> None:
    reports = parse_financial_reports_payload(
        "600519",
        {
            "success": True,
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "SECUCODE": "600519.SH",
                        "REPORTDATE": "2026-03-31 00:00:00",
                        "DATATYPE": "2026年 一季报",
                        "BASIC_EPS": 21.76,
                        "TOTAL_OPERATE_INCOME": 54702912385.23,
                        "PARENT_NETPROFIT": 27242512886.45,
                        "WEIGHTAVG_ROE": 10.57,
                        "XSMLL": 89.7592,
                        "YSTZ": 6.336,
                        "SJLTZ": 1.47,
                    }
                ]
            },
        },
    )

    assert reports[0].symbol == "600519"
    assert reports[0].revenue == Decimal("54702912385.23")
    assert reports[0].parent_net_profit == Decimal("27242512886.45")
    assert reports[0].report_date == datetime(2026, 3, 31, tzinfo=UTC)


def test_build_fundamental_indicators_from_reports() -> None:
    reports = parse_financial_reports_payload(
        "600519",
        {
            "success": True,
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "REPORTDATE": "2026-03-31 00:00:00",
                        "DATATYPE": "2026年 一季报",
                        "TOTAL_OPERATE_INCOME": 100,
                        "PARENT_NETPROFIT": 50,
                        "WEIGHTAVG_ROE": 10,
                        "XSMLL": 90,
                        "YSTZ": 6,
                        "SJLTZ": 2,
                    },
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "REPORTDATE": "2025-12-31 00:00:00",
                        "DATATYPE": "2025年 年报",
                        "TOTAL_OPERATE_INCOME": 200,
                        "PARENT_NETPROFIT": 80,
                        "WEIGHTAVG_ROE": 20,
                        "XSMLL": 80,
                    },
                ]
            },
        },
    )

    indicators = build_fundamental_indicators("600519", reports)

    assert indicators.symbol == "600519"
    assert len(indicators.points) == 2
    assert indicators.points[0].net_margin == Decimal("50.0000")
    assert indicators.summary.latest_report_date == datetime(2026, 3, 31, tzinfo=UTC)
    assert indicators.summary.latest_revenue == Decimal("100")
    assert indicators.summary.avg_roe == Decimal("15.0000")
    assert indicators.summary.avg_gross_margin == Decimal("85.0000")
    assert indicators.data_quality.status == "warning"


def test_parse_announcements_payload() -> None:
    announcements = parse_announcements_payload(
        "600519",
        {
            "data": {
                "list": [
                    {
                        "art_code": "AN202605211822654865",
                        "codes": [
                            {
                                "short_name": "贵州茅台",
                                "stock_code": "600519",
                            }
                        ],
                        "columns": [{"column_name": "独立董事候选人声明"}],
                        "notice_date": "2026-05-22 00:00:00",
                        "display_time": "2026-05-21 20:58:04:412",
                        "title": "贵州茅台公告",
                    }
                ]
            }
        },
    )

    assert announcements[0].art_code == "AN202605211822654865"
    assert announcements[0].symbol == "600519"
    assert announcements[0].name == "贵州茅台"
    assert announcements[0].columns == ["独立董事候选人声明"]
    assert announcements[0].pdf_url is not None


def test_market_data_cache_round_trip(tmp_path: Path) -> None:
    cache = MarketDataCache(root=tmp_path, enabled=True)
    cache_key = cache.build_key("quote-realtime", {"symbol": "600519"})

    assert cache.read(cache_key) is None

    written = cache.write(
        cache_key,
        ttl_seconds=60,
        payload={"symbol": "600519", "price": "1290.2"},
    )
    assert written is not None

    cached = cache.read(cache_key)
    assert cached is not None
    assert cached.payload["symbol"] == "600519"
    assert cached.to_fetch_metadata("hit").cache_status == "hit"


def test_realtime_quote_endpoint_uses_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QUANTPILOT_MARKET_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("QUANTPILOT_QUOTE_CACHE_TTL_SECONDS", "60")

    call_count = 0

    async def fake_get_realtime_quote(self, symbol: str):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        return parse_quote_payload(
            "1.600519",
            {
                "rc": 0,
                "rt": 11,
                "data": {
                    "total": 1,
                    "diff": [
                        {
                            "f2": 1290.2,
                            "f3": -1.59,
                            "f5": 49157,
                            "f6": 6372389482.0,
                            "f12": "600519",
                            "f13": 1,
                            "f14": "贵州茅台",
                            "f15": 1311.91,
                            "f16": 1290.12,
                            "f17": 1310.95,
                            "f18": 1311.0,
                            "f20": 1615679031393,
                            "f21": 1615679031393,
                            "f124": 1779437507,
                        }
                    ],
                },
            },
        )

    monkeypatch.setattr(
        "quantpilot_market_data.providers.eastmoney.EastMoneyClient.get_realtime_quote",
        fake_get_realtime_quote,
    )

    with TestClient(create_app()) as test_client:
        first = test_client.get("/api/v1/quotes/realtime/600519")
        second = test_client.get("/api/v1/quotes/realtime/600519")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["fetch"]["cache_status"] == "miss"
    assert second.json()["fetch"]["cache_status"] == "hit"
    assert call_count == 1
