from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from quantpilot_market_data.providers.eastmoney import normalize_secid, parse_quote_payload


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
