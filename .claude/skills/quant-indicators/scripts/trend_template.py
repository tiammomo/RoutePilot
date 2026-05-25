#!/usr/bin/env python3
"""基于 K 线生成趋势模板和交易前检查项。"""

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
            parsed = float(value.replace(",", ""))
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return mean(values[-window:])


def max_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1)
    return max_dd * 100


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


def classify_trend(latest: float | None, ma20: float | None, ma60: float | None, drawdown_pct: float | None) -> tuple[str, int, list[str]]:
    score = 50
    reasons: list[str] = []
    if latest is not None and ma20 is not None:
        if latest >= ma20:
            score += 15
            reasons.append("收盘价站上 MA20")
        else:
            score -= 15
            reasons.append("收盘价低于 MA20")
    if ma20 is not None and ma60 is not None:
        if ma20 >= ma60:
            score += 15
            reasons.append("MA20 高于 MA60")
        else:
            score -= 15
            reasons.append("MA20 低于 MA60")
    if drawdown_pct is not None:
        if drawdown_pct <= -20:
            score -= 15
            reasons.append("阶段最大回撤较深")
        elif drawdown_pct >= -8:
            score += 5
            reasons.append("阶段回撤相对可控")

    if score >= 70:
        state = "strong"
    elif score >= 55:
        state = "repair"
    elif score >= 40:
        state = "neutral"
    else:
        state = "weak"
    return state, max(0, min(100, score)), reasons


def trend_for_asset(asset: JsonRecord, index: int) -> JsonRecord:
    bars = get_bars(asset)
    closes = [value for value in (numeric(bar.get("close")) for bar in bars) if value is not None and value > 0]
    volumes = [value for value in (numeric(bar.get("volume")) for bar in bars) if value is not None and value >= 0]
    warnings: list[str] = []
    if len(closes) < 60:
        warnings.append("K 线少于 60 条，趋势模板稳定性较弱。")

    latest = closes[-1] if closes else None
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    return_20d = (latest / closes[-21] - 1) * 100 if len(closes) >= 21 and latest is not None else None
    drawdown = max_drawdown(closes[-120:])
    avg_volume20 = moving_average(volumes, 20)
    volume_ratio = volumes[-1] / avg_volume20 if volumes and avg_volume20 else None
    state, score, reasons = classify_trend(latest, ma20, ma60, drawdown)

    return {
        "symbol": symbol_of(asset, index),
        "name": name_of(asset, index),
        "sample_size": len(closes),
        "state": state,
        "score": score,
        "metrics": {
            "latest_close": round_or_none(latest, 4),
            "ma20": round_or_none(ma20, 4),
            "ma60": round_or_none(ma60, 4),
            "return_20d_pct": round_or_none(return_20d, 4),
            "max_drawdown_120d_pct": round_or_none(drawdown, 4),
            "volume_ratio_20d": round_or_none(volume_ratio, 4),
        },
        "reasons": reasons,
        "triggers": {
            "confirm": "价格连续站稳 MA20，且量能不低于 20 日均量。",
            "reduce": "跌破 MA20 后无法快速收复，或阶段回撤继续扩大。",
            "observe": "等待成交额、公告或基本面数据确认，不直接输出交易指令。",
        },
        "warnings": warnings,
    }


def build_trend_template(data: JsonRecord) -> JsonRecord:
    rows = [trend_for_asset(asset, index) for index, asset in enumerate(get_assets(data))]
    warnings = [warning for row in rows for warning in row["warnings"]]
    return {
        "method": "ma20_ma60_volume_drawdown_template",
        "rows": rows,
        "data_quality": {
            "status": "warning" if warnings else "ok",
            "warnings": warnings,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 QuantPilot 趋势模板摘要。")
    parser.add_argument("input", help="data_file/final/dashboard-data.json")
    parser.add_argument("-o", "--output", help="输出 JSON 路径；不传则打印到 stdout。")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("输入 JSON 必须是对象。")

    result = build_trend_template(data)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
