#!/usr/bin/env python3
"""基于 K 线和行情快照计算流动性摘要。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


JsonRecord = dict[str, Any]


def as_record(value: Any) -> JsonRecord | None:
    return value if isinstance(value, dict) else None


def numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def get_assets(data: JsonRecord) -> list[JsonRecord]:
    assets = data.get("assets")
    if isinstance(assets, list) and assets:
        return [item for item in assets if isinstance(item, dict)]
    return [data]


def get_bars(asset: JsonRecord) -> list[JsonRecord]:
    kline = as_record(asset.get("kline")) or as_record(asset.get("history")) or {}
    for key in ("bars", "data", "items"):
        bars = kline.get(key)
        if isinstance(bars, list):
            return [item for item in bars if isinstance(item, dict)]
    bars = asset.get("bars") or asset.get("klines") or asset.get("candles")
    if isinstance(bars, list):
        return [item for item in bars if isinstance(item, dict)]
    return []


def symbol_of(asset: JsonRecord, index: int) -> str:
    quote = as_record(asset.get("quote")) or {}
    return str(asset.get("symbol") or quote.get("symbol") or f"asset_{index + 1}")


def name_of(asset: JsonRecord, index: int) -> str:
    quote = as_record(asset.get("quote")) or {}
    return str(asset.get("name") or quote.get("name") or symbol_of(asset, index))


def turnover_proxy(asset: JsonRecord, latest_amount: float | None, avg_amount: float | None) -> float | None:
    quote = as_record(asset.get("quote")) or {}
    market_cap = numeric(quote.get("float_market_cap")) or numeric(quote.get("market_cap"))
    amount = latest_amount or avg_amount
    if not market_cap or not amount:
        return None
    return amount / market_cap * 100


def liquidity_for_asset(asset: JsonRecord, index: int) -> JsonRecord:
    bars = get_bars(asset)
    quote = as_record(asset.get("quote")) or {}
    recent = bars[-20:]
    volumes = [value for value in (numeric(bar.get("volume")) for bar in recent) if value is not None]
    amounts = [value for value in (numeric(bar.get("amount")) for bar in recent) if value is not None]

    return_pairs: list[tuple[float, float]] = []
    previous_close: float | None = None
    for bar in bars[-60:]:
        close = numeric(bar.get("close"))
        amount = numeric(bar.get("amount"))
        if close is not None and previous_close and previous_close > 0 and amount and amount > 0:
            daily_return = abs(close / previous_close - 1)
            return_pairs.append((daily_return, amount))
        if close is not None:
            previous_close = close

    amihud_values = [daily_return / amount for daily_return, amount in return_pairs if amount > 0]
    amihud = mean(amihud_values)
    latest_amount = numeric(quote.get("amount")) or (amounts[-1] if amounts else None)
    avg_amount20 = mean(amounts)
    avg_volume20 = mean(volumes)
    turnover = turnover_proxy(asset, latest_amount, avg_amount20)

    warnings: list[str] = []
    if len(bars) < 20:
        warnings.append("K 线样本少于 20 条，流动性均值稳定性较弱。")
    if avg_amount20 is None:
        warnings.append("缺少成交额字段，无法计算 20 日平均成交额。")
    if amihud is None:
        warnings.append("缺少连续收盘价或成交额，无法计算 Amihud 非流动性。")

    liquidity_score: str
    if avg_amount20 is None:
        liquidity_score = "unknown"
    elif avg_amount20 >= 1_000_000_000:
        liquidity_score = "high"
    elif avg_amount20 >= 100_000_000:
        liquidity_score = "medium"
    else:
        liquidity_score = "low"

    return {
        "symbol": symbol_of(asset, index),
        "name": name_of(asset, index),
        "sample_size": len(bars),
        "latest_amount": round_or_none(latest_amount, 2),
        "avg_amount_20d": round_or_none(avg_amount20, 2),
        "avg_volume_20d": round_or_none(avg_volume20, 2),
        "turnover_proxy_pct": round_or_none(turnover, 4),
        "amihud_illiquidity_x1e9": round_or_none(amihud * 1_000_000_000 if amihud is not None else None, 6),
        "liquidity_score": liquidity_score,
        "warnings": warnings,
    }


def build_liquidity(data: JsonRecord) -> JsonRecord:
    assets = get_assets(data)
    rows = [liquidity_for_asset(asset, index) for index, asset in enumerate(assets)]
    return {
        "method": "amount_volume_amihud_proxy",
        "window": "20d",
        "rows": rows,
        "data_quality": {
            "status": "warning" if any(row["warnings"] for row in rows) else "ok",
            "warnings": [warning for row in rows for warning in row["warnings"]],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="计算 QuantPilot dashboard-data 流动性摘要。")
    parser.add_argument("input", help="data_file/final/dashboard-data.json")
    parser.add_argument("-o", "--output", help="输出 JSON 路径；不传则打印到 stdout。")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("输入 JSON 必须是对象。")

    result = build_liquidity(data)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
