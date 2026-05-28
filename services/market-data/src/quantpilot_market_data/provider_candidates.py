from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field

CandidateProviderStatus = Literal["candidate", "testing", "blocked", "planned"]
CandidateProviderMarket = Literal["a-share", "global", "us", "macro", "fund", "mixed"]


class CandidateProvider(BaseModel):
    """待评估免费/免费层数据源，不直接进入主业务链路。"""

    id: str
    name: str
    market: CandidateProviderMarket
    status: CandidateProviderStatus = "candidate"
    requires_key: bool = False
    free_tier: str
    best_for: list[str] = Field(default_factory=list)
    docs_url: str | None = None
    probe_url: str | None = None
    limitations: list[str] = Field(default_factory=list)
    notes: str | None = None


class ProviderProbeResult(BaseModel):
    provider_id: str
    ok: bool
    status_code: int | None = None
    elapsed_ms: int | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    sample_keys: list[str] = Field(default_factory=list)


class CandidateProviderRegistry(BaseModel):
    providers: list[CandidateProvider]


class CandidateProviderProbeResponse(BaseModel):
    results: list[ProviderProbeResult]


CANDIDATE_PROVIDERS: list[CandidateProvider] = [
    CandidateProvider(
        id="tencent-a-share-kline",
        name="腾讯股票 K 线接口",
        market="a-share",
        status="testing",
        requires_key=False,
        free_tier="免 key 公开接口，非正式 SLA。",
        best_for=["A 股历史 K 线兜底", "东方财富历史接口异常时降级"],
        probe_url="https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,5,qfq",
        limitations=["非官方稳定 API，字段和频率可能变化。"],
    ),
    CandidateProvider(
        id="ths-public-kline",
        name="同花顺公开 K 线端点",
        market="a-share",
        status="testing",
        requires_key=False,
        free_tier="免 key 网页公开端点，非正式 SLA。",
        best_for=["A 股历史 K 线候选源", "东方财富历史域名不可达时的补充探针"],
        docs_url="https://quantapi.10jqka.com.cn/",
        probe_url="https://d.10jqka.com.cn/v6/line/hs_002156/01/all.js",
        limitations=[
            "网页端点返回压缩 JavaScript，需要单独解析。",
            "接入入库前必须验证复权口径、成交额、换手率和停牌样本。",
        ],
        notes="同花顺正式 iFinD/QuantAPI 需要授权；该候选源只记录公开网页端点连通性。",
    ),
    CandidateProvider(
        id="sina-a-share-quote",
        name="新浪财经实时行情",
        market="a-share",
        status="candidate",
        requires_key=False,
        free_tier="免 key 公开接口，非正式 SLA。",
        best_for=["A 股实时行情兜底", "盘口/快照字段补充"],
        probe_url="https://hq.sinajs.cn/list=sh600519",
        limitations=["需要合适 Referer/User-Agent，编码和字段需要单独适配。"],
    ),
    CandidateProvider(
        id="baostock-a-share-history",
        name="Baostock A 股历史行情",
        market="a-share",
        status="planned",
        requires_key=False,
        free_tier="免费 Python SDK。",
        best_for=["A 股历史日线", "成交额/换手率字段补齐", "复权历史样本"],
        docs_url="https://pypi.org/project/baostock/",
        limitations=["当前服务环境未安装 baostock 包，需作为后端 provider 接入后再做探针。"],
        notes="适合作为东方财富历史 K 线失败后的 A 股日线主兜底源。",
    ),
    CandidateProvider(
        id="akshare-python",
        name="AKShare 聚合接口",
        market="mixed",
        status="planned",
        requires_key=False,
        free_tier="免费开源 Python SDK。",
        best_for=["A 股/港股/基金等多源聚合", "东方财富、新浪、同花顺等网页接口快速验证"],
        docs_url="https://akshare.akfamily.xyz/data/stock/stock.html",
        limitations=[
            "当前服务环境未安装 akshare 包。",
            "部分接口仍依赖东方财富网页端点，必须逐接口探针，不能视为独立主源。",
        ],
    ),
    CandidateProvider(
        id="stooq-daily",
        name="Stooq 历史行情 CSV",
        market="global",
        status="candidate",
        requires_key=False,
        free_tier="免 key CSV 下载。",
        best_for=["美股/指数/外汇历史日线", "离线回测样本"],
        docs_url="https://stooq.com/",
        probe_url="https://stooq.com/q/d/l/?s=aapl.us&i=d",
        limitations=["主要覆盖海外市场，A 股覆盖有限；字段较简洁。"],
    ),
    CandidateProvider(
        id="stooq-index-daily",
        name="Stooq 指数历史行情 CSV",
        market="global",
        status="candidate",
        requires_key=False,
        free_tier="免 key CSV 下载。",
        best_for=["海外指数日线", "宏观市场代理指标", "回测基准"],
        docs_url="https://stooq.com/",
        probe_url="https://stooq.com/q/d/l/?s=%5Espx&i=d",
        limitations=["符号体系和交易所后缀需要单独映射；实时行情不是强项。"],
    ),
    CandidateProvider(
        id="yahoo-finance-chart",
        name="Yahoo Finance Chart API",
        market="global",
        status="candidate",
        requires_key=False,
        free_tier="免 key 非正式接口，适合低频研究测试。",
        best_for=["海外股票/ETF K 线", "区间成交量", "yfinance 后端适配验证"],
        docs_url="https://query1.finance.yahoo.com/",
        probe_url="https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=5d&interval=1d",
        limitations=["非官方公开接口，可能限流或调整返回结构；生产链路需要缓存和降级。"],
        notes="后续接入 yfinance 时优先封装在后端 provider 中，生成项目不得临时 pip install。",
    ),
    CandidateProvider(
        id="yahoo-finance-quote-summary",
        name="Yahoo Finance Quote Summary API",
        market="global",
        status="candidate",
        requires_key=False,
        free_tier="免 key 非正式接口，适合低频研究测试。",
        best_for=["海外公司概览", "估值倍数", "分红和财务摘要候选源"],
        docs_url="https://query1.finance.yahoo.com/",
        probe_url="https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL?modules=price,summaryDetail,defaultKeyStatistics",
        limitations=["非官方公开接口，模块字段可能变化；部分请求可能需要 cookie/crumb。"],
    ),
    CandidateProvider(
        id="alpha-vantage",
        name="Alpha Vantage",
        market="global",
        status="candidate",
        requires_key=True,
        free_tier="免费 key 可用，适合小流量测试；具体限额以官方文档为准。",
        best_for=["美股日线", "技术指标", "宏观和外汇补充"],
        docs_url="https://www.alphavantage.co/documentation/",
        limitations=["需要 API key；免费层有调用频率限制。"],
    ),
    CandidateProvider(
        id="finnhub",
        name="Finnhub",
        market="global",
        status="candidate",
        requires_key=True,
        free_tier="免费层适合开发测试；具体限额以官方文档为准。",
        best_for=["美股行情", "公司新闻", "基础公司资料"],
        docs_url="https://finnhub.io/docs/api",
        limitations=["需要 API key；部分数据在免费层不可用。"],
    ),
    CandidateProvider(
        id="twelve-data",
        name="Twelve Data",
        market="global",
        status="candidate",
        requires_key=True,
        free_tier="免费层适合小规模测试；按 credits 计费/限额以官方文档为准。",
        best_for=["海外股票/ETF/外汇/加密 K 线", "统一 time series 接口"],
        docs_url="https://twelvedata.com/docs",
        limitations=["需要 API key；免费层接口和频率有限。"],
    ),
    CandidateProvider(
        id="nasdaq-data-link",
        name="Nasdaq Data Link",
        market="macro",
        status="candidate",
        requires_key=True,
        free_tier="存在免费数据集和免费 API key；具体数据集权限以官方为准。",
        best_for=["宏观数据", "部分公开数据集", "历史研究数据"],
        docs_url="https://docs.data.nasdaq.com/",
        limitations=["不是所有数据集免费；字段契约随数据集变化。"],
    ),
    CandidateProvider(
        id="marketstack",
        name="Marketstack",
        market="global",
        status="candidate",
        requires_key=True,
        free_tier="免费层适合低频测试；通常存在延迟和月度请求限制。",
        best_for=["全球股票 EOD", "简单海外行情补充"],
        docs_url="https://marketstack.com/documentation",
        limitations=["需要 API key；免费层通常不适合实时高频。"],
    ),
]


def get_candidate_provider(provider_id: str) -> CandidateProvider | None:
    return next((provider for provider in CANDIDATE_PROVIDERS if provider.id == provider_id), None)


async def probe_candidate_provider(
    provider: CandidateProvider,
    timeout_seconds: float = 8.0,
) -> ProviderProbeResult:
    if provider.requires_key:
        return ProviderProbeResult(
            provider_id=provider.id,
            ok=False,
            error="该候选源需要 API key，当前只登记能力，不做无 key 探测。",
        )

    if not provider.probe_url:
        return ProviderProbeResult(
            provider_id=provider.id,
            ok=False,
            error="该候选源没有配置 probe_url。",
        )

    started = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={
                "User-Agent": "QuantPilot/0.1 provider-probe",
                "Referer": "https://finance.sina.com.cn/",
            },
            follow_redirects=True,
        ) as client:
            response = await client.get(provider.probe_url)
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        sample: object
        try:
            sample = response.json()
        except ValueError:
            sample = response.text[:200]

        sample_keys = list(sample.keys())[:12] if isinstance(sample, dict) else []
        return ProviderProbeResult(
            provider_id=provider.id,
            ok=200 <= response.status_code < 300 and bool(response.content),
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            sample_keys=sample_keys,
            error=None if 200 <= response.status_code < 300 else response.text[:200],
        )
    except Exception as error:
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return ProviderProbeResult(
            provider_id=provider.id,
            ok=False,
            elapsed_ms=elapsed_ms,
            error=str(error),
        )
