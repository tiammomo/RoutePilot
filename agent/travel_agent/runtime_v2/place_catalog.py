"""Reviewed stable-place fallback with explicit official-source provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from routepilot_contracts.common import (
    CoordinateSystem,
    Freshness,
    FreshnessStatus,
    GeoPoint,
    MoneyRange,
    PlaceRef,
    SourceKind,
    SourceRef,
)

from .shared import utc_now

CATALOG_VERSION = "beijing-official-places-2026-07-12"
REVIEWED_AT = datetime(2026, 7, 12, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class CatalogPlace:
    slug: str
    name: str
    address: str
    latitude: str
    longitude: str
    source_name: str
    source_uri: str
    summary: str
    tags: tuple[str, ...]
    duration_minutes: int
    cost_min: str
    cost_max: str
    closed_weekdays: frozenset[int] = frozenset()

    def source(self) -> SourceRef:
        return SourceRef(
            source_id=f"source:catalog:{self.slug}",
            kind=SourceKind.RAG,
            name=self.source_name,
            version=CATALOG_VERSION,
            uri=self.source_uri,
            retrieved_at=utc_now(),
            publisher="官方页面，经 RoutePilot 结构化复核",
        )

    def freshness(self, source: SourceRef) -> Freshness:
        return Freshness(
            observed_at=REVIEWED_AT,
            status=FreshnessStatus.UNKNOWN,
            source=source,
        )

    def place_ref(self, source: SourceRef) -> PlaceRef:
        return PlaceRef(
            place_id=f"place:catalog:{self.slug}",
            display_name=self.name,
            address=self.address,
            country_code="CN",
            timezone="Asia/Shanghai",
            location=GeoPoint(
                latitude=Decimal(self.latitude),
                longitude=Decimal(self.longitude),
                coordinate_system=CoordinateSystem.WGS84,
                accuracy_meters=Decimal("100"),
            ),
            source=source,
        )

    def estimated_cost(self, source: SourceRef) -> MoneyRange:
        return MoneyRange(
            min_amount=self.cost_min,
            max_amount=self.cost_max,
            currency="CNY",
            basis="per_person",
            observed_at=REVIEWED_AT,
            source=source,
        )


BEIJING_PLACES: tuple[CatalogPlace, ...] = (
    CatalogPlace(
        slug="temple-of-heaven",
        name="天坛公园",
        address="北京市东城区天坛内东里7号",
        latitude="39.8822",
        longitude="116.4066",
        source_name="天坛公园官网",
        source_uri="https://www.tiantanpark.cn/aboutus.html",
        summary="明清皇家祭天建筑群，适合建筑、礼制与北京中轴线主题；票价、联票和开放区域需在出发前以官网为准。",
        tags=("历史文化", "古建筑", "中轴线", "公园"),
        duration_minutes=150,
        cost_min="15",
        cost_max="34",
    ),
    CatalogPlace(
        slug="qianmen-dashilar",
        name="前门大街与大栅栏历史街区",
        address="北京市东城区前门大街至西城区大栅栏街区",
        latitude="39.8968",
        longitude="116.3956",
        source_name="首都之窗·前门大栅栏商圈",
        source_uri="https://www.beijing.gov.cn/ywdt/zwzt/gjxxfxcs/gjf/xftyq/tyts/202404/t20240410_3615091.html",
        summary="北京中轴线南段的历史商业街区，可观察老字号、会馆和传统街巷；街区通行免费，具体消费由用户自行决定。",
        tags=("历史文化", "街区", "老字号", "中轴线", "少排队"),
        duration_minutes=90,
        cost_min="0",
        cost_max="0",
    ),
    CatalogPlace(
        slug="jingshan-park",
        name="景山公园",
        address="北京市西城区景山西街44号",
        latitude="39.9251",
        longitude="116.3967",
        source_name="北京市景山公园官网",
        source_uri="https://www.bjjspark.cn/",
        summary="北京中轴线制高点之一，适合从城市格局角度理解故宫与老城；开放时间和现场限流需临行核验。",
        tags=("历史文化", "中轴线", "城市景观", "公园"),
        duration_minutes=75,
        cost_min="2",
        cost_max="10",
    ),
    CatalogPlace(
        slug="shichahai",
        name="什刹海历史文化街区",
        address="北京市西城区前海、后海及西海沿岸",
        latitude="39.9370",
        longitude="116.3853",
        source_name="首都之窗·什刹海历史文化旅游风景区",
        source_uri="https://www.beijing.gov.cn/zhengce/zhengcefagui/201905/t20190522_58138.html",
        summary="由水域、历史街巷和民居共同构成的老城文化区域，适合傍晚步行；进入沿线单独景点前需另查预约和开放信息。",
        tags=("历史文化", "胡同", "街区", "散步", "少排队"),
        duration_minutes=120,
        cost_min="0",
        cost_max="0",
    ),
    CatalogPlace(
        slug="beihai-park",
        name="北海公园",
        address="北京市西城区文津街1号",
        latitude="39.9255",
        longitude="116.3890",
        source_name="北京市公园管理中心·北海公园",
        source_uri="https://gygl.beijing.gov.cn/mlgy/mlgy_lsmy/201911/t20191129_732583.html",
        summary="保存较完整的皇家园林，适合古典园林和老城水系主题；门票档位及园中园开放状态需临行核验。",
        tags=("历史文化", "皇家园林", "公园", "散步"),
        duration_minutes=120,
        cost_min="5",
        cost_max="20",
    ),
    CatalogPlace(
        slug="forbidden-city",
        name="故宫博物院",
        address="北京市东城区景山前街4号",
        latitude="39.9163",
        longitude="116.3972",
        source_name="故宫博物院官方导览",
        source_uri="https://www.dpm.org.cn/Visit.html",
        summary="明清宫廷建筑与文物收藏核心场所；通常周一闭馆且必须通过官方渠道预约，法定节假日安排以公告为准。",
        tags=("历史文化", "博物馆", "古建筑", "中轴线", "预约"),
        duration_minutes=180,
        cost_min="40",
        cost_max="60",
        closed_weekdays=frozenset({0}),
    ),
    CatalogPlace(
        slug="national-museum-china",
        name="中国国家博物馆",
        address="北京市东城区东长安街16号",
        latitude="39.9051",
        longitude="116.4011",
        source_name="中国国家博物馆官方服务页",
        source_uri="https://www.chnmuseum.cn/cg/",
        summary="以中国历史文化和国家级文物展览为核心；通常周一闭馆并实行预约，开放安排以官方服务页为准。",
        tags=("历史文化", "博物馆", "文物", "预约"),
        duration_minutes=150,
        cost_min="0",
        cost_max="0",
        closed_weekdays=frozenset({0}),
    ),
)


class ApprovedPlaceCatalog:
    """Return only reviewed places for an explicitly supported destination."""

    def search(
        self,
        destination: str,
        *,
        local_date: date,
        query: str,
        limit: int,
    ) -> tuple[CatalogPlace, ...]:
        if destination.strip() not in {"北京", "北京市"}:
            return ()
        # The reviewed sequence is a south-to-north route through the old city.
        # Relevance may decide eligibility in a future catalog version, but it
        # must not reorder places into a geographically wasteful zig-zag.
        del query
        available = [
            place for place in BEIJING_PLACES if local_date.weekday() not in place.closed_weekdays
        ]
        return tuple(available[: max(1, min(limit, 8))])


__all__ = ["ApprovedPlaceCatalog", "CatalogPlace"]
