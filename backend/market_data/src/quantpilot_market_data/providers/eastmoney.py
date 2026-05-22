from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from quantpilot_market_data.models import MarketCode, RealtimeQuote

EASTMONEY_REALTIME_QUOTE_PATH = "/api/qt/ulist.np/get"
DEFAULT_EASTMONEY_BASE_URLS = (
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
)

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
    """东方财富实时行情客户端。"""

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

    if "." in value:
        market, code = value.split(".", 1)
        if market.isdigit() and code.isdigit() and len(code) == 6:
            return f"{market}.{code}"
        raise ValueError(f"无效的东方财富 secid：{symbol_or_secid}")

    code = value.upper().removeprefix("SH").removeprefix("SZ").removeprefix("BJ")
    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效的股票代码：{symbol_or_secid}")

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
