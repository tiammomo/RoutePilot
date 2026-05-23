from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from quantpilot_market_data.models import (
    Adjustment,
    AnnouncementItem,
    AssetType,
    FinancialReportItem,
    KlineBar,
    KlinePeriod,
    KlineResponse,
    MarketCode,
    RealtimeQuote,
    SymbolResolveResult,
)

EASTMONEY_REALTIME_QUOTE_PATH = "/api/qt/ulist.np/get"
EASTMONEY_KLINE_PATH = "/api/qt/stock/kline/get"
EASTMONEY_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_ANNOUNCEMENT_URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
DEFAULT_EASTMONEY_BASE_URLS = (
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
)
DEFAULT_EASTMONEY_KLINE_BASE_URLS = (
    "https://push2his.eastmoney.com",
    "https://push2his.eastmoney.com",
)

KNOWN_SECURITY_ALIASES: dict[str, str] = {
    "沪深300": "1.000300",
    "沪深 300": "1.000300",
    "HS300": "1.000300",
    "上证指数": "1.000001",
    "上证综指": "1.000001",
    "上证": "1.000001",
    "深证成指": "0.399001",
    "深成指": "0.399001",
    "创业板指": "0.399006",
    "创业板指数": "0.399006",
    "科创50": "1.000688",
    "科创 50": "1.000688",
    "中证500": "1.000905",
    "中证 500": "1.000905",
    "中证1000": "1.000852",
    "中证 1000": "1.000852",
    "沪深300ETF": "1.510300",
    "沪深300 ETF": "1.510300",
    "300ETF": "1.510300",
}

KNOWN_INDEX_CODES = {
    "000300",
    "000688",
    "000852",
    "000905",
    "399001",
    "399006",
    "399300",
}

QUOTE_FIELDS = ",".join(
    [
        "f2",  # 最新价
        "f3",  # 涨跌幅，单位：%
        "f4",  # 涨跌额
        "f5",  # 成交量
        "f6",  # 成交额
        "f12",  # 代码
        "f13",  # 东方财富市场编号
        "f14",  # 名称
        "f15",  # 最高价
        "f16",  # 最低价
        "f17",  # 开盘价
        "f18",  # 昨收
        "f20",  # 总市值
        "f21",  # 流通市值
        "f124",  # 行情时间，Unix 秒
    ]
)


class EastMoneyError(RuntimeError):
    """东方财富行情接口异常。"""


@dataclass(frozen=True)
class EastMoneyConfig:
    timeout_seconds: float = 8.0
    base_urls: tuple[str, ...] = DEFAULT_EASTMONEY_BASE_URLS
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )


class EastMoneyClient:
    """东方财富行情、公告和财务摘要客户端。"""

    def __init__(self, config: EastMoneyConfig | None = None) -> None:
        self.config = config or EastMoneyConfig(base_urls=_get_base_urls_from_env())

    async def get_realtime_quote(self, symbol_or_secid: str) -> RealtimeQuote:
        quotes = await self.get_realtime_quotes([symbol_or_secid])
        if not quotes:
            raise EastMoneyError(f"东方财富未返回行情数据：{symbol_or_secid}")
        return quotes[0]

    async def get_realtime_quotes(self, symbols_or_secids: list[str]) -> list[RealtimeQuote]:
        secids = [normalize_secid(raw_symbol) for raw_symbol in symbols_or_secids]
        async with self._create_http_client() as client:
            payload = await self._request_quotes(secids, client=client)
            return parse_quote_list_payload(secids, payload)

    async def resolve_symbol(self, query: str, count: int = 5) -> list[SymbolResolveResult]:
        params = {
            "input": query.strip(),
            "type": "14",
            "count": str(count),
        }
        async with self._create_http_client() as client:
            response = await client.get(EASTMONEY_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        return parse_symbol_suggest_payload(query, payload)

    async def get_kline(
        self,
        symbol_or_secid: str,
        *,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 120,
        end: str = "20500101",
    ) -> KlineResponse:
        secid = normalize_secid(symbol_or_secid)
        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": _period_to_klt(period),
            "fqt": _adjustment_to_fqt(adjustment),
            "end": end,
            "lmt": str(limit),
        }

        errors: list[str] = []
        async with self._create_http_client() as client:
            for base_url in DEFAULT_EASTMONEY_KLINE_BASE_URLS:
                try:
                    response = await client.get(
                        f"{base_url.rstrip('/')}{EASTMONEY_KLINE_PATH}",
                        params=params,
                    )
                    response.raise_for_status()
                    return parse_kline_payload(secid, period, adjustment, response.json())
                except httpx.HTTPError as error:
                    errors.append(f"{base_url}: {error}")
            if period in {"daily", "weekly", "monthly"}:
                try:
                    response = await client.get(
                        TENCENT_KLINE_URL,
                        params={
                            "param": _build_tencent_kline_param(
                                secid,
                                period=period,
                                adjustment=adjustment,
                                limit=limit,
                            ),
                        },
                    )
                    response.raise_for_status()
                    return parse_tencent_kline_payload(
                        secid,
                        period,
                        adjustment,
                        response.json(),
                    )
                except httpx.HTTPError as error:
                    errors.append(f"tencent-kline: {error}")
        raise EastMoneyError(f"东方财富 K 线请求失败：{'；'.join(errors)}")

    async def get_financial_reports(
        self,
        symbol_or_secid: str,
        limit: int = 8,
    ) -> list[FinancialReportItem]:
        symbol = normalize_secid(symbol_or_secid).split(".", 1)[1]
        params = {
            "reportName": "RPT_LICO_FN_CPD",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{symbol}")',
            "pageNumber": "1",
            "pageSize": str(limit),
            "sortTypes": "-1",
            "sortColumns": "REPORTDATE",
            "source": "WEB",
            "client": "WEB",
        }

        async with self._create_http_client() as client:
            response = await client.get(EASTMONEY_DATACENTER_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        return parse_financial_reports_payload(symbol, payload)

    async def get_announcements(
        self,
        symbol_or_secid: str,
        limit: int = 20,
    ) -> list[AnnouncementItem]:
        secid = normalize_secid(symbol_or_secid)
        market_id, symbol = secid.split(".", 1)
        params = {
            "sr": "-1",
            "page_size": str(limit),
            "page_index": "1",
            "ann_type": "A",
            "client_source": "web",
            "stock_list": f"{symbol},{market_id}",
        }

        async with self._create_http_client() as client:
            response = await client.get(EASTMONEY_ANNOUNCEMENT_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        return parse_announcements_payload(symbol, payload)

    async def _request_quotes(
        self,
        secids: list[str],
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        params = {
            "secids": ",".join(secids),
            "fields": QUOTE_FIELDS,
            "fltt": "2",
            "invt": "2",
        }

        async def request(active_client: httpx.AsyncClient) -> dict[str, Any]:
            errors: list[str] = []
            for base_url in self.config.base_urls:
                quote_url = f"{base_url.rstrip('/')}{EASTMONEY_REALTIME_QUOTE_PATH}"
                try:
                    response = await active_client.get(quote_url, params=params)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPError as error:
                    errors.append(f"{base_url}: {error}")
            try:
                raise EastMoneyError("；".join(errors))
            except EastMoneyError as error:
                raise EastMoneyError(f"东方财富行情请求失败：{error}") from error

        if client is not None:
            return await request(client)

        async with self._create_http_client() as active_client:
            return await request(active_client)

    def _create_http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.config.timeout_seconds,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "User-Agent": self.config.user_agent,
                "Referer": "https://quote.eastmoney.com/",
            },
        )


def _get_base_urls_from_env() -> tuple[str, ...]:
    raw_value = os.getenv("EASTMONEY_BASE_URLS", "")
    values = tuple(value.strip() for value in raw_value.split(",") if value.strip())
    return values or DEFAULT_EASTMONEY_BASE_URLS


def normalize_secid(symbol_or_secid: str) -> str:
    """把股票代码转成东方财富 secid。

    规则先覆盖常见 A 股：
    - 6/9 开头：上海，market=1
    - 0/2/3 开头：深圳，market=0
    - 4/8 开头：北京，market=0
    - 已经传入 0.xxxxxx / 1.xxxxxx / 2.xxxxxx 时原样使用
    """

    value = symbol_or_secid.strip()
    if not value:
        raise ValueError("股票代码不能为空")

    alias = KNOWN_SECURITY_ALIASES.get(value) or KNOWN_SECURITY_ALIASES.get(value.upper())
    if alias:
        return alias

    if "." in value:
        market, code = value.split(".", 1)
        if market.isdigit() and code.isdigit() and len(code) == 6:
            return f"{market}.{code}"
        raise ValueError(f"无效的东方财富 secid：{symbol_or_secid}")

    code = value.upper().removeprefix("SH").removeprefix("SZ").removeprefix("BJ")
    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效的股票代码：{symbol_or_secid}")

    if code in KNOWN_INDEX_CODES:
        return f"{'1' if code.startswith('000') else '0'}.{code}"
    if code.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "588")):
        return f"1.{code}"
    if code.startswith(("15", "16", "18")):
        return f"0.{code}"

    if code.startswith(("6", "9")):
        return f"1.{code}"
    if code.startswith(("0", "2", "3", "4", "8")):
        return f"0.{code}"

    raise ValueError(f"无法推断东方财富市场编号：{symbol_or_secid}")


def market_from_payload(secid: str, data: dict[str, Any]) -> MarketCode:
    market_id = data.get("f13")
    code = str(data.get("f12") or secid.split(".", 1)[-1])

    if market_id == 1 or code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "UNKNOWN"


def asset_type_from_payload(secid: str, data: dict[str, Any]) -> AssetType:
    raw_type = str(data.get("f14") or "")
    symbol = str(data.get("f12") or secid.split(".", 1)[-1])
    return infer_asset_type(symbol=symbol, secid=secid, name=raw_type)


def infer_asset_type(
    *,
    symbol: str,
    secid: str | None = None,
    name: str | None = None,
    raw: dict[str, Any] | None = None,
) -> AssetType:
    security_type_name = str((raw or {}).get("SecurityTypeName") or "")
    classify = str((raw or {}).get("Classify") or "")
    security_type = str((raw or {}).get("SecurityType") or "")
    market_id = secid.split(".", 1)[0] if secid and "." in secid else ""
    normalized_name = name or str((raw or {}).get("Name") or "")

    if symbol in KNOWN_INDEX_CODES or security_type_name == "指数" or classify.lower() == "index":
        return "index"
    if (
        "ETF" in normalized_name.upper()
        or security_type_name in {"基金", "ETF"}
        or classify.lower() in {"fund", "etf"}
        or security_type == "8"
    ):
        return "etf" if "ETF" in normalized_name.upper() else "fund"
    if symbol.startswith(("510", "511", "512", "513", "515", "516", "517", "518", "588")):
        return "etf"
    if market_id == "0" and symbol.startswith(("15", "16", "18")):
        return "etf"
    return "stock"


def market_from_secid(secid: str) -> MarketCode:
    market_id, code = secid.split(".", 1)
    if market_id == "1" or code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "UNKNOWN"


def parse_symbol_suggest_payload(query: str, payload: dict[str, Any]) -> list[SymbolResolveResult]:
    table = payload.get("QuotationCodeTable")
    data = table.get("Data") if isinstance(table, dict) else None
    if not isinstance(data, list):
        return []

    results: list[SymbolResolveResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        quote_id = str(item.get("QuoteID") or "")
        code = str(item.get("Code") or item.get("UnifiedCode") or "")
        if not quote_id and code:
            try:
                quote_id = normalize_secid(code)
            except ValueError:
                continue
        if not quote_id:
            continue
        results.append(
            SymbolResolveResult(
                query=query,
                symbol=code or quote_id.split(".", 1)[-1],
                name=_empty_to_none(item.get("Name")),
                asset_type=infer_asset_type(
                    symbol=code or quote_id.split(".", 1)[-1],
                    secid=quote_id,
                    name=_empty_to_none(item.get("Name")),
                    raw=item,
                ),
                market=market_from_secid(quote_id),
                secid=quote_id,
                raw=item,
            )
        )
    return results


def parse_kline_payload(
    secid: str,
    period: KlinePeriod,
    adjustment: Adjustment,
    payload: dict[str, Any],
) -> KlineResponse:
    rc = payload.get("rc")
    if rc != 0:
        raise EastMoneyError(f"东方财富 K 线接口返回异常 rc={rc}: {payload}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise EastMoneyError(f"东方财富未返回 K 线数据：{payload}")

    klines = data.get("klines")
    if not isinstance(klines, list):
        raise EastMoneyError(f"东方财富未返回 K 线列表：{payload}")

    return KlineResponse(
        symbol=str(data.get("code") or secid.split(".", 1)[-1]),
        name=_empty_to_none(data.get("name")),
        secid=secid,
        asset_type=infer_asset_type(
            symbol=str(data.get("code") or secid.split(".", 1)[-1]),
            secid=secid,
            name=_empty_to_none(data.get("name")),
        ),
        market=market_from_secid(secid),
        period=period,
        adjustment=adjustment,
        bars=[parse_kline_row(row) for row in klines if isinstance(row, str)],
        fetched_at=datetime.now(UTC),
    )


def parse_kline_row(row: str) -> KlineBar:
    parts = row.split(",")
    padded = parts + [""] * max(0, 11 - len(parts))
    return KlineBar(
        date=padded[0],
        open=_to_decimal(padded[1]),
        close=_to_decimal(padded[2]),
        high=_to_decimal(padded[3]),
        low=_to_decimal(padded[4]),
        volume=_to_int(padded[5]),
        amount=_to_decimal(padded[6]),
        amplitude=_to_decimal(padded[7]),
        change_percent=_to_decimal(padded[8]),
        change_amount=_to_decimal(padded[9]),
        turnover=_to_decimal(padded[10]),
    )


def parse_tencent_kline_payload(
    secid: str,
    period: KlinePeriod,
    adjustment: Adjustment,
    payload: dict[str, Any],
) -> KlineResponse:
    if payload.get("code") != 0:
        raise EastMoneyError(f"腾讯 K 线接口返回异常：{payload.get('msg') or payload}")

    market_id, symbol = secid.split(".", 1)
    key = ("sh" if market_id == "1" else "sz") + symbol
    data = payload.get("data")
    symbol_data = data.get(key) if isinstance(data, dict) else None
    if not isinstance(symbol_data, dict):
        raise EastMoneyError(f"腾讯未返回 K 线数据：{payload}")

    row_key = _tencent_kline_row_key(period, adjustment)
    rows = symbol_data.get(row_key)
    if not isinstance(rows, list):
        rows = symbol_data.get(_tencent_kline_row_key(period, "none"))
    if not isinstance(rows, list):
        raise EastMoneyError(f"腾讯未返回 K 线列表：{payload}")

    qt_data = symbol_data.get("qt")
    quote_row = qt_data.get(key) if isinstance(qt_data, dict) else None
    name = quote_row[1] if isinstance(quote_row, list) and len(quote_row) > 1 else None

    bars = [parse_tencent_kline_row(row) for row in rows if isinstance(row, list)]

    return KlineResponse(
        symbol=symbol,
        name=_empty_to_none(name),
        secid=secid,
        asset_type=infer_asset_type(symbol=symbol, secid=secid, name=_empty_to_none(name)),
        market=market_from_secid(secid),
        source="tencent",
        period=period,
        adjustment=adjustment,
        bars=enrich_kline_change_fields(bars),
        fetched_at=datetime.now(UTC),
    )


def parse_tencent_kline_row(row: list[Any]) -> KlineBar:
    padded = [str(value) for value in row] + [""] * max(0, 6 - len(row))
    open_value = _to_decimal(padded[1])
    close_value = _to_decimal(padded[2])
    previous_close = _to_decimal(row[7]) if len(row) > 7 else None
    change_amount = None
    change_percent = None
    if close_value is not None and previous_close is not None and previous_close != 0:
        change_amount = close_value - previous_close
        change_percent = (change_amount / previous_close) * Decimal("100")

    return KlineBar(
        date=padded[0],
        open=open_value,
        close=close_value,
        high=_to_decimal(padded[3]),
        low=_to_decimal(padded[4]),
        volume=_to_int(padded[5]),
        amount=None,
        amplitude=None,
        change_percent=change_percent,
        change_amount=change_amount,
        turnover=None,
    )


def enrich_kline_change_fields(bars: list[KlineBar]) -> list[KlineBar]:
    enriched: list[KlineBar] = []
    previous_close: Decimal | None = None

    for bar in bars:
        change_amount = bar.change_amount
        change_percent = bar.change_percent
        if (
            change_amount is None
            and change_percent is None
            and previous_close is not None
            and previous_close != 0
            and bar.close is not None
        ):
            change_amount = bar.close - previous_close
            change_percent = (change_amount / previous_close) * Decimal("100")

        enriched.append(
            bar.model_copy(
                update={
                    "change_amount": change_amount,
                    "change_percent": change_percent,
                }
            )
        )
        previous_close = bar.close

    return enriched


def parse_financial_reports_payload(
    symbol: str,
    payload: dict[str, Any],
) -> list[FinancialReportItem]:
    if payload.get("success") is False:
        raise EastMoneyError(f"东方财富财务摘要接口返回异常：{payload.get('message') or payload}")

    result = payload.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list):
        return []

    return [
        FinancialReportItem(
            symbol=str(item.get("SECURITY_CODE") or symbol),
            name=_empty_to_none(item.get("SECURITY_NAME_ABBR")),
            secucode=_empty_to_none(item.get("SECUCODE")),
            report_date=_parse_datetime(item.get("REPORTDATE")),
            data_type=_empty_to_none(item.get("DATATYPE")),
            basic_eps=_to_decimal(item.get("BASIC_EPS")),
            revenue=_to_decimal(item.get("TOTAL_OPERATE_INCOME")),
            parent_net_profit=_to_decimal(item.get("PARENT_NETPROFIT")),
            weighted_roe=_to_decimal(item.get("WEIGHTAVG_ROE")),
            gross_margin=_to_decimal(item.get("XSMLL")),
            revenue_yoy=_to_decimal(item.get("YSTZ")),
            net_profit_yoy=_to_decimal(item.get("SJLTZ")),
            notice_date=_parse_datetime(item.get("NOTICE_DATE")),
            raw=item,
        )
        for item in data
        if isinstance(item, dict)
    ]


def parse_announcements_payload(symbol: str, payload: dict[str, Any]) -> list[AnnouncementItem]:
    data = payload.get("data")
    items = data.get("list") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    announcements: list[AnnouncementItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code_info = _first_dict(item.get("codes"))
        art_code = str(item.get("art_code") or "")
        columns = item.get("columns")
        column_names = []
        if isinstance(columns, list):
            column_names = [
                str(column.get("column_name"))
                for column in columns
                if isinstance(column, dict) and column.get("column_name")
            ]
        announcements.append(
            AnnouncementItem(
                art_code=art_code,
                title=str(item.get("title_ch") or item.get("title") or ""),
                symbol=_empty_to_none(code_info.get("stock_code")) if code_info else symbol,
                name=_empty_to_none(code_info.get("short_name")) if code_info else None,
                notice_date=_parse_datetime(item.get("notice_date")),
                display_time=_parse_datetime(item.get("display_time")),
                columns=column_names,
                url=f"https://data.eastmoney.com/notices/detail/{symbol}/{art_code}.html"
                if art_code
                else None,
                pdf_url=f"https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf" if art_code else None,
                raw=item,
            )
        )
    return announcements


def parse_quote_list_payload(secids: list[str], payload: dict[str, Any]) -> list[RealtimeQuote]:
    rc = payload.get("rc")
    if rc != 0:
        raise EastMoneyError(f"东方财富接口返回异常 rc={rc}: {payload}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise EastMoneyError(f"东方财富未返回行情数据：{payload}")

    diff = data.get("diff")
    if not isinstance(diff, list):
        raise EastMoneyError(f"东方财富未返回行情列表：{payload}")

    requested_by_code = {secid.split(".", 1)[-1]: secid for secid in secids}
    return [
        parse_quote_item(requested_by_code.get(str(item.get("f12")), ""), item)
        for item in diff
        if isinstance(item, dict)
    ]


def parse_quote_payload(secid: str, payload: dict[str, Any]) -> RealtimeQuote:
    quotes = parse_quote_list_payload([secid], payload)
    if not quotes:
        raise EastMoneyError(f"东方财富未返回行情数据：{payload}")
    return quotes[0]


def parse_quote_item(secid: str, data: dict[str, Any]) -> RealtimeQuote:
    symbol = str(data.get("f12") or secid.split(".", 1)[-1])
    quote_time = _timestamp_to_datetime(data.get("f124"))

    return RealtimeQuote(
        symbol=symbol,
        secid=secid or f"{data.get('f13', '')}.{symbol}",
        name=_empty_to_none(data.get("f14")),
        asset_type=asset_type_from_payload(secid, data),
        market=market_from_payload(secid, data),
        price=_to_decimal(data.get("f2")),
        high=_to_decimal(data.get("f15")),
        low=_to_decimal(data.get("f16")),
        open=_to_decimal(data.get("f17")),
        previous_close=_to_decimal(data.get("f18")),
        change_percent=_to_decimal(data.get("f3")),
        volume=_to_int(data.get("f5")),
        amount=_to_decimal(data.get("f6")),
        market_cap=_to_decimal(data.get("f20")),
        float_market_cap=_to_decimal(data.get("f21")),
        quote_time=quote_time,
        fetched_at=datetime.now(UTC),
    )


def _empty_to_none(value: Any) -> str | None:
    if value in (None, "-", ""):
        return None
    return str(value)


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "-", ""):
        return None
    return Decimal(str(value))


def _scale_decimal(value: Any, divisor: int) -> Decimal | None:
    raw = _to_decimal(value)
    if raw is None:
        return None
    return raw / Decimal(divisor)


def _to_int(value: Any) -> int | None:
    if value in (None, "-", ""):
        return None
    return int(Decimal(str(value)))


def _timestamp_to_datetime(value: Any) -> datetime | None:
    seconds = _to_int(value)
    if seconds is None or seconds <= 0:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, "-", ""):
        return None
    text = str(value).replace(":", "-", 2) if str(value).count(":") > 2 else str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=UTC)
    except ValueError:
        return None


def _period_to_klt(period: KlinePeriod) -> int:
    return {
        "daily": 101,
        "weekly": 102,
        "monthly": 103,
        "minute1": 1,
        "minute5": 5,
        "minute15": 15,
        "minute30": 30,
        "minute60": 60,
    }[period]


def _adjustment_to_fqt(adjustment: Adjustment) -> int:
    return {
        "none": 0,
        "qfq": 1,
        "hfq": 2,
    }[adjustment]


def _build_tencent_kline_param(
    secid: str,
    *,
    period: KlinePeriod,
    adjustment: Adjustment,
    limit: int,
) -> str:
    market_id, symbol = secid.split(".", 1)
    market_prefix = "sh" if market_id == "1" else "sz"
    period_value = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    }[period]
    adjustment_prefix = {
        "none": "",
        "qfq": "qfq",
        "hfq": "hfq",
    }[adjustment]
    return f"{market_prefix}{symbol},{period_value},,,{limit},{adjustment_prefix}"


def _tencent_kline_row_key(period: KlinePeriod, adjustment: Adjustment | str) -> str:
    period_value = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    }[period]
    if adjustment == "qfq":
        return f"qfq{period_value}"
    if adjustment == "hfq":
        return f"hfq{period_value}"
    return period_value


def _first_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return None
