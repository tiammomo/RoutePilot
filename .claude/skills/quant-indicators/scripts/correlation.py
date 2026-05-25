#!/usr/bin/env python3
"""基于 dashboard-data.json 计算多标的收益相关性。"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable
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
    raw = asset.get("symbol") or quote.get("symbol") or f"asset_{index + 1}"
    return str(raw)


def close_returns(bars: Iterable[JsonRecord]) -> dict[str, float]:
    ordered: list[tuple[str, float]] = []
    for index, bar in enumerate(bars):
        close = numeric(bar.get("close"))
        if close is None or close <= 0:
            continue
        date = str(bar.get("date") or bar.get("time") or index)
        ordered.append((date, close))

    returns: dict[str, float] = {}
    for (current_date, current_close), (_, previous_close) in zip(ordered[1:], ordered[:-1], strict=False):
        if previous_close > 0:
            returns[current_date] = math.log(current_close / previous_close)
    return returns


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    left_var = sum((a - left_mean) ** 2 for a in left)
    right_var = sum((b - right_mean) ** 2 for b in right)
    denominator = math.sqrt(left_var * right_var)
    if denominator == 0:
        return None
    return numerator / denominator


def build_correlation(data: JsonRecord) -> JsonRecord:
    series: dict[str, dict[str, float]] = {}
    sample_lengths: dict[str, int] = {}
    for index, asset in enumerate(get_assets(data)):
        symbol = symbol_of(asset, index)
        returns = close_returns(get_bars(asset))
        if returns:
            series[symbol] = returns
            sample_lengths[symbol] = len(returns)

    symbols = list(series)
    matrix: list[JsonRecord] = []
    pairs: list[JsonRecord] = []
    for left in symbols:
        row: JsonRecord = {"symbol": left}
        for right in symbols:
            common_dates = sorted(set(series[left]) & set(series[right]))
            left_values = [series[left][date] for date in common_dates]
            right_values = [series[right][date] for date in common_dates]
            corr = pearson(left_values, right_values)
            row[right] = round(corr, 4) if corr is not None else None
            if left < right:
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "correlation": round(corr, 4) if corr is not None else None,
                        "overlap": len(common_dates),
                    }
                )
        matrix.append(row)

    pairs.sort(
        key=lambda item: abs(item["correlation"]) if isinstance(item.get("correlation"), (int, float)) else -1,
        reverse=True,
    )
    return {
        "method": "pearson_log_return",
        "symbols": symbols,
        "sample_lengths": sample_lengths,
        "matrix": matrix,
        "top_pairs": pairs[:10],
        "data_quality": {
            "status": "ok" if len(symbols) >= 2 else "warning",
            "warnings": [] if len(symbols) >= 2 else ["相关性计算至少需要两个有历史 K 线的标的。"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="计算 QuantPilot dashboard-data 多标的收益相关性。")
    parser.add_argument("input", help="data_file/final/dashboard-data.json")
    parser.add_argument("-o", "--output", help="输出 JSON 路径；不传则打印到 stdout。")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("输入 JSON 必须是对象。")

    result = build_correlation(data)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
