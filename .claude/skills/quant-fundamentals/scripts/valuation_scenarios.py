#!/usr/bin/env python3
"""基于 dashboard-data.json 生成估值情景摘要。"""

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
        cleaned = value.replace(",", "").replace("%", "").strip()
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def first_numeric(records: list[JsonRecord], keys: tuple[str, ...]) -> float | None:
    for record in records:
        for key in keys:
            value = numeric(record.get(key))
            if value is not None:
                return value
    return None


def get_assets(data: JsonRecord) -> list[JsonRecord]:
    assets = data.get("assets")
    if isinstance(assets, list) and assets:
        return [item for item in assets if isinstance(item, dict)]
    return [data]


def get_reports(asset: JsonRecord) -> list[JsonRecord]:
    financials = as_record(asset.get("financials")) or as_record(asset.get("fundamentals")) or {}
    reports = financials.get("reports") or asset.get("reports")
    if isinstance(reports, list):
        return [item for item in reports if isinstance(item, dict)]
    return []


def get_fundamental_summary(asset: JsonRecord) -> JsonRecord:
    indicators = as_record(asset.get("fundamentalIndicators")) or as_record(asset.get("fundamental_indicators")) or {}
    return as_record(indicators.get("summary")) or as_record(asset.get("fundamentalSummary")) or {}


def symbol_of(asset: JsonRecord, index: int) -> str:
    quote = as_record(asset.get("quote")) or {}
    return str(asset.get("symbol") or quote.get("symbol") or f"asset_{index + 1}")


def name_of(asset: JsonRecord, index: int) -> str:
    quote = as_record(asset.get("quote")) or {}
    return str(asset.get("name") or quote.get("name") or symbol_of(asset, index))


def infer_base_metrics(asset: JsonRecord) -> tuple[JsonRecord, list[str]]:
    quote = as_record(asset.get("quote")) or {}
    reports = get_reports(asset)
    latest_report = reports[0] if reports else {}
    summary = get_fundamental_summary(asset)
    warnings: list[str] = []

    price = numeric(quote.get("price")) or numeric(asset.get("price"))
    market_cap = (
        numeric(quote.get("market_cap"))
        or numeric(quote.get("total_market_cap"))
        or numeric(summary.get("market_cap"))
    )
    eps = (
        numeric(summary.get("eps_ttm"))
        or numeric(summary.get("eps"))
        or first_numeric(reports, ("eps", "basic_eps", "diluted_eps"))
    )
    pe = (
        numeric(quote.get("pe_ttm"))
        or numeric(quote.get("pe"))
        or numeric(summary.get("pe_ttm"))
        or numeric(summary.get("pe"))
    )
    pb = numeric(quote.get("pb")) or numeric(summary.get("pb"))
    roe = numeric(summary.get("roe")) or numeric(summary.get("weighted_roe")) or first_numeric(reports, ("weighted_roe", "roe"))
    revenue = (
        numeric(summary.get("latest_revenue"))
        or numeric(latest_report.get("revenue"))
        or numeric(latest_report.get("operating_revenue"))
    )
    net_profit = (
        numeric(summary.get("latest_parent_net_profit"))
        or numeric(latest_report.get("parent_net_profit"))
        or numeric(latest_report.get("net_profit"))
    )

    if pe is None and price is not None and eps is not None and eps > 0:
        pe = price / eps
    if eps is None and market_cap is not None and net_profit is not None and net_profit > 0 and price is not None:
        total_shares = market_cap / price if price > 0 else None
        eps = net_profit / total_shares if total_shares else None
    if pe is None and market_cap is not None and net_profit is not None and net_profit > 0:
        pe = market_cap / net_profit

    if price is None:
        warnings.append("缺少最新价，无法计算情景上行/下行空间。")
    if eps is None:
        warnings.append("缺少 EPS 或可推导 EPS 的净利润/市值数据，估值情景仅能展示基础估值。")
    if pe is None:
        warnings.append("缺少 PE 口径，无法构建 PE/EPS 情景。")

    return (
        {
            "price": round_or_none(price, 4),
            "market_cap": round_or_none(market_cap, 2),
            "eps": round_or_none(eps, 4),
            "pe_ttm": round_or_none(pe, 4),
            "pb": round_or_none(pb, 4),
            "roe": round_or_none(roe, 4),
            "revenue": round_or_none(revenue, 2),
            "net_profit": round_or_none(net_profit, 2),
        },
        warnings,
    )


def build_scenarios(metrics: JsonRecord) -> list[JsonRecord]:
    price = numeric(metrics.get("price"))
    eps = numeric(metrics.get("eps"))
    pe = numeric(metrics.get("pe_ttm"))
    if price is None or eps is None or eps <= 0 or pe is None or pe <= 0:
        return []

    cases = [
        ("bear", "防守情景", -5.0, pe * 0.8, "盈利下修且估值收缩，优先观察风险暴露。"),
        ("base", "中性情景", 5.0, pe, "盈利温和修复，估值维持当前中枢。"),
        ("bull", "进攻情景", 15.0, pe * 1.2, "盈利改善且估值扩张，需要成交额和趋势确认。"),
    ]
    rows: list[JsonRecord] = []
    for case_id, name, eps_growth_pct, pe_multiple, interpretation in cases:
        forward_eps = eps * (1 + eps_growth_pct / 100)
        implied_price = forward_eps * pe_multiple
        rows.append(
            {
                "case": case_id,
                "name": name,
                "assumptions": {
                    "eps_growth_pct": round(eps_growth_pct, 2),
                    "pe_multiple": round(pe_multiple, 4),
                },
                "forward_eps": round_or_none(forward_eps, 4),
                "implied_price": round_or_none(implied_price, 4),
                "upside_pct": round_or_none((implied_price / price - 1) * 100 if price else None, 4),
                "interpretation": interpretation,
            }
        )
    return rows


def valuation_for_asset(asset: JsonRecord, index: int) -> JsonRecord:
    metrics, warnings = infer_base_metrics(asset)
    scenarios = build_scenarios(metrics)
    if not scenarios and not warnings:
        warnings.append("可用估值字段不足，暂不输出情景价格。")
    return {
        "symbol": symbol_of(asset, index),
        "name": name_of(asset, index),
        "method": "pe_eps_scenario",
        "base_metrics": metrics,
        "scenarios": scenarios,
        "warnings": warnings,
        "not_investment_advice": True,
    }


def build_valuation(data: JsonRecord) -> JsonRecord:
    assets = get_assets(data)
    rows = [valuation_for_asset(asset, index) for index, asset in enumerate(assets)]
    warnings = [warning for row in rows for warning in row["warnings"]]
    return {
        "method": "pe_eps_scenario",
        "assets": rows,
        "data_quality": {
            "status": "warning" if warnings else "ok",
            "warnings": warnings,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 QuantPilot 估值情景摘要。")
    parser.add_argument("input", help="data_file/final/dashboard-data.json")
    parser.add_argument("-o", "--output", help="输出 JSON 路径；不传则打印到 stdout。")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("输入 JSON 必须是对象。")

    result = build_valuation(data)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
