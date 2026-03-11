"""Travel API client with mock providers and metadata."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent.tools.travel_api")


class TravelAPIClient:
    """Unified travel data adapter. Currently backed by mock data."""

    def __init__(self, use_cache: bool = True):
        """Initialize TravelAPIClient and prepare runtime dependencies.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            use_cache: Boolean flag `use_cache` that toggles runtime behavior.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self.use_cache = use_cache
        self._cache: Dict[str, Any] = {}
        self._cache_meta: Dict[str, str] = {}

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC timestamp in ISO-8601 format.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        return datetime.now(timezone.utc).isoformat()

    def _get_cache(self, key: str, *, bypass_cache: bool = False) -> Optional[Any]:
        """Get cache from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            bypass_cache: When true, skip cache and force live data-provider request.
        
        Returns:
            Optional[Any]: Computed value returned to the caller.
        """
        if bypass_cache:
            return None
        if self.use_cache and key in self._cache:
            return self._cache[key]
        return None

    def _set_cache(self, key: str, value: Any) -> None:
        """Store response payload into cache with metadata.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            value: Input field `value` used for normalization or matching rules.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        if self.use_cache:
            self._cache[key] = value
            self._cache_meta[key] = self._now_iso()

    def _build_meta(self, key: str, source: str, ttl_seconds: int) -> Dict[str, Any]:
        """Build meta for downstream processing.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            source: Input field `source` used for normalization or matching rules.
            ttl_seconds: Time-related setting `ttl_seconds` used by scheduling/retry windows.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        fetched_at = self._cache_meta.get(key, self._now_iso())
        is_stale = False
        try:
            fetched_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - fetched_dt.astimezone(timezone.utc)
            is_stale = age > timedelta(seconds=ttl_seconds)
        except Exception:
            is_stale = False
        return {
            "source": source,
            "fetched_at": fetched_at,
            "ttl_seconds": ttl_seconds,
            "is_stale": is_stale,
        }

    @staticmethod
    def _refresh_meta(refresh_attempted: bool, refresh_success: bool) -> Dict[str, Any]:
        """Build refresh-status metadata for fallback results.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            refresh_attempted: Whether stale-data refresh was attempted for this result.
            refresh_success: Whether stale-data refresh completed successfully.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return {
            "refresh_attempted": bool(refresh_attempted),
            "refresh_success": bool(refresh_success),
        }

    @staticmethod
    def _weather_provider_chain() -> List[str]:
        """Resolve failover provider chain for weather queries.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        primary = os.getenv("WEATHER_API_PROVIDER", "mock-weather-provider").strip() or "mock-weather-provider"
        fallback = os.getenv("WEATHER_API_FALLBACK_PROVIDER", "mock-weather-fallback").strip() or "mock-weather-fallback"
        if primary == fallback:
            return [primary]
        return [primary, fallback]

    @staticmethod
    def _is_provider_down(provider: str) -> bool:
        """Check whether provider is marked unavailable in process state.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            provider: Provider identifier used in fallback selection logic.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        down_list = [item.strip() for item in os.getenv("WEATHER_DOWN_PROVIDERS", "").split(",") if item.strip()]
        return provider in down_list

    @staticmethod
    def _provider_chain(primary_env: str, fallback_env: str, primary_default: str, fallback_default: str) -> List[str]:
        """Resolve generic provider failover chain order.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            primary_env: Primary environment-variable name used to resolve provider credential.
            fallback_env: Fallback environment-variable name used when primary credential is empty.
            primary_default: Default primary credential value when environment variable is absent.
            fallback_default: Default fallback credential value when environment variable is absent.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        primary = os.getenv(primary_env, primary_default).strip() or primary_default
        fallback = os.getenv(fallback_env, fallback_default).strip() or fallback_default
        if primary == fallback:
            return [primary]
        return [primary, fallback]

    @staticmethod
    def _is_provider_down_by_env(provider: str, down_env: str) -> bool:
        """Check provider-down override flag from environment variables.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            provider: Provider identifier used in fallback selection logic.
            down_env: Environment-variable name used to mark provider-down override state.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        down_list = [item.strip() for item in os.getenv(down_env, "").split(",") if item.strip()]
        return provider in down_list

    async def search_cities(self, query: str) -> Dict[str, Any]:
        """Search cities with provider fallback, caching, and normalization.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            query: Query text or request query parameters.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        cache_key = f"city:{query}"
        providers = self._provider_chain(
            primary_env="CITIES_API_PROVIDER",
            fallback_env="CITIES_API_FALLBACK_PROVIDER",
            primary_default="mock-cities-provider",
            fallback_default="mock-cities-fallback",
        )
        primary_provider = providers[0]
        selected_provider = primary_provider
        fallback_used = False
        if self._is_provider_down_by_env(primary_provider, "CITIES_DOWN_PROVIDERS"):
            if len(providers) > 1 and not self._is_provider_down_by_env(providers[1], "CITIES_DOWN_PROVIDERS"):
                selected_provider = providers[1]
                fallback_used = True
                logger.warning(
                    "Cities primary provider unavailable, switched to fallback provider: %s -> %s",
                    primary_provider,
                    selected_provider,
                )
            else:
                raise RuntimeError(f"No available cities provider. primary={primary_provider}")
        source = f"cities_provider:{selected_provider}"
        ttl_seconds = 86400
        cached = self._get_cache(cache_key)
        if cached:
            cached_result = dict(cached)
            cached_meta = dict(cached_result.get("_meta", {}))
            cached_result["_meta"] = {
                **cached_meta,
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            }
            return cached_result

        await asyncio.sleep(0.05)
        cities_db: List[Dict[str, Any]] = [
            {
                "id": "101010100",
                "name": "北京",
                "pinyin": "beijing",
                "province": "北京",
                "description": "中国首都，历史文化名城。",
                "highlights": ["故宫", "长城", "天坛", "颐和园"],
                "best_time": "春秋季",
                "weather": "四季分明",
                "rating": 4.8,
            },
            {
                "id": "101020100",
                "name": "上海",
                "pinyin": "shanghai",
                "province": "上海",
                "description": "国际化都市，城市休闲与人文并重。",
                "highlights": ["外滩", "豫园", "陆家嘴", "新天地"],
                "best_time": "春秋季",
                "weather": "亚热带季风气候",
                "rating": 4.7,
            },
            {
                "id": "101230400",
                "name": "丽江",
                "pinyin": "lijiang",
                "province": "云南",
                "description": "古城与雪山并存，适合慢游。",
                "highlights": ["丽江古城", "玉龙雪山", "束河古镇"],
                "best_time": "春秋季",
                "weather": "高原气候",
                "rating": 4.8,
            },
        ]

        q = query.lower().strip()
        results = [
            city
            for city in cities_db
            if q in city["name"].lower()
            or q in city["pinyin"].lower()
            or q in city["province"].lower()
            or q in city["description"].lower()
        ]
        if not results:
            results = cities_db[:2]

        result = {
            "query": query,
            "total": len(results),
            "data": results,
            "_meta": {
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            },
        }
        self._set_cache(cache_key, result)
        result["_meta"] = {
            **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
            "provider_chain": providers,
            "provider_used": selected_provider,
            "fallback_used": fallback_used,
        }
        return result

    async def search_attractions(
        self,
        city: str,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Search attractions with provider fallback and output normalization.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            city: Target city name/code used by city or map operations.
            category: Input field `category` used for normalization or matching rules.
            page: Numeric control parameter `page` used for bounds or pagination.
            page_size: Numeric control parameter `page_size` used for bounds or pagination.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        cache_key = f"attractions:{city}:{category}:{page}:{page_size}"
        providers = self._provider_chain(
            primary_env="ATTRACTIONS_API_PROVIDER",
            fallback_env="ATTRACTIONS_API_FALLBACK_PROVIDER",
            primary_default="mock-attractions-provider",
            fallback_default="mock-attractions-fallback",
        )
        primary_provider = providers[0]
        selected_provider = primary_provider
        fallback_used = False
        if self._is_provider_down_by_env(primary_provider, "ATTRACTIONS_DOWN_PROVIDERS"):
            if len(providers) > 1 and not self._is_provider_down_by_env(providers[1], "ATTRACTIONS_DOWN_PROVIDERS"):
                selected_provider = providers[1]
                fallback_used = True
                logger.warning(
                    "Attractions primary provider unavailable, switched to fallback provider: %s -> %s",
                    primary_provider,
                    selected_provider,
                )
            else:
                raise RuntimeError(f"No available attractions provider. primary={primary_provider}")
        source = f"attraction_provider:{selected_provider}"
        ttl_seconds = 21600
        cached = self._get_cache(cache_key)
        if cached:
            cached_result = dict(cached)
            cached_meta = dict(cached_result.get("_meta", {}))
            cached_result["_meta"] = {
                **cached_meta,
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            }
            return cached_result

        await asyncio.sleep(0.08)
        attractions_db: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
            "北京": {
                "historical": [
                    {"id": "a001", "name": "故宫", "desc": "明清皇宫", "ticket": "60元", "hours": "8:30-17:00", "rating": 4.9},
                    {"id": "a002", "name": "八达岭长城", "desc": "长城经典段", "ticket": "40-65元", "hours": "7:00-18:00", "rating": 4.8},
                ],
                "natural": [
                    {"id": "a003", "name": "颐和园", "desc": "皇家园林", "ticket": "30元", "hours": "6:30-18:00", "rating": 4.8},
                ],
            },
            "上海": {
                "historical": [
                    {"id": "a101", "name": "豫园", "desc": "江南古典园林", "ticket": "40元", "hours": "8:30-17:00", "rating": 4.6},
                ],
                "entertainment": [
                    {"id": "a102", "name": "外滩", "desc": "黄浦江沿岸地标", "ticket": "免费", "hours": "全天", "rating": 4.8},
                ],
            },
        }

        city_bucket = attractions_db.get(city, {})
        if category:
            items = city_bucket.get(category, [])
        else:
            items = [it for values in city_bucket.values() for it in values]

        start = max(0, (page - 1) * page_size)
        data = items[start : start + page_size]
        result = {
            "city": city,
            "category": category,
            "page": page,
            "page_size": page_size,
            "total": len(items),
            "data": data,
            "_meta": {
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            },
        }
        self._set_cache(cache_key, result)
        result["_meta"] = {
            **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
            "provider_chain": providers,
            "provider_used": selected_provider,
            "fallback_used": fallback_used,
        }
        return result

    async def search_hotels(
        self,
        city: str,
        district: Optional[str] = None,
        check_in: Optional[str] = None,
        check_out: Optional[str] = None,
        price_range: Optional[tuple] = None,
        page: int = 1,
        page_size: int = 20,
        bypass_cache: bool = False,
    ) -> Dict[str, Any]:
        """Search hotels with date normalization, cache, and failover.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            city: Target city name/code used by city or map operations.
            district: Text input `district` used for parsing, prompt assembly, or display.
            check_in: Hotel check-in date used by accommodation lookup requests.
            check_out: Hotel check-out date used by accommodation lookup requests.
            price_range: Input field `price_range` used for normalization or matching rules.
            page: Numeric control parameter `page` used for bounds or pagination.
            page_size: Numeric control parameter `page_size` used for bounds or pagination.
            bypass_cache: When true, skip cache and force live data-provider request.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        _ = (check_in, check_out)
        cache_key = f"hotels:{city}:{district}:{price_range}:{page}:{page_size}"
        providers = self._provider_chain(
            primary_env="HOTELS_API_PROVIDER",
            fallback_env="HOTELS_API_FALLBACK_PROVIDER",
            primary_default="mock-hotels-provider",
            fallback_default="mock-hotels-fallback",
        )
        primary_provider = providers[0]
        selected_provider = primary_provider
        fallback_used = False
        if self._is_provider_down_by_env(primary_provider, "HOTELS_DOWN_PROVIDERS"):
            if len(providers) > 1 and not self._is_provider_down_by_env(providers[1], "HOTELS_DOWN_PROVIDERS"):
                selected_provider = providers[1]
                fallback_used = True
                logger.warning(
                    "Hotels primary provider unavailable, switched to fallback provider: %s -> %s",
                    primary_provider,
                    selected_provider,
                )
            else:
                raise RuntimeError(f"No available hotels provider. primary={primary_provider}")
        source = f"hotel_provider:{selected_provider}"
        ttl_seconds = 1800
        cached = self._get_cache(cache_key, bypass_cache=bypass_cache)
        if cached:
            cached_result = dict(cached)
            cached_meta = dict(cached_result.get("_meta", {}))
            cached_result["_meta"] = {
                **cached_meta,
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                **self._refresh_meta(refresh_attempted=False, refresh_success=False),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            }
            return cached_result

        await asyncio.sleep(0.1)
        hotels = [
            {"id": "h001", "name": f"{city}中心酒店", "district": "市中心", "rating": 4.7, "price": 580},
            {"id": "h002", "name": f"{city}商务酒店", "district": "金融区", "rating": 4.5, "price": 420},
            {"id": "h003", "name": f"{city}度假酒店", "district": "景区", "rating": 4.8, "price": 760},
        ]
        if district:
            hotels = [h for h in hotels if h["district"] == district]
        if price_range:
            hotels = [h for h in hotels if price_range[0] <= h["price"] <= price_range[1]]

        start = max(0, (page - 1) * page_size)
        result = {
            "city": city,
            "page": page,
            "page_size": page_size,
            "total": len(hotels),
            "data": hotels[start : start + page_size],
            "_meta": {
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                **self._refresh_meta(refresh_attempted=bypass_cache, refresh_success=bypass_cache),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            },
        }
        self._set_cache(cache_key, result)
        result["_meta"] = {
            **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
            **self._refresh_meta(refresh_attempted=bypass_cache, refresh_success=bypass_cache),
            "provider_chain": providers,
            "provider_used": selected_provider,
            "fallback_used": fallback_used,
        }
        return result

    async def get_weather(self, city: str, days: int = 7, bypass_cache: bool = False) -> Dict[str, Any]:
        """Get weather from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            city: Target city name/code used by city or map operations.
            days: Trip duration in days used by budget estimation logic.
            bypass_cache: When true, skip cache and force live data-provider request.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        cache_key = f"weather:{city}:{days}"
        ttl_seconds = 1800
        providers = self._weather_provider_chain()
        primary_provider = providers[0]
        cached = self._get_cache(cache_key, bypass_cache=bypass_cache)
        if cached:
            cached_result = dict(cached)
            cached_meta = dict(cached_result.get("_meta", {}))
            source = str(cached_meta.get("source", f"weather_provider:{primary_provider}"))
            cached_result["_meta"] = {
                **cached_meta,
                **self._build_meta(cache_key, source=source, ttl_seconds=ttl_seconds),
                **self._refresh_meta(refresh_attempted=False, refresh_success=False),
            }
            return cached_result

        selected_provider = primary_provider
        fallback_used = False
        if self._is_provider_down(primary_provider):
            if len(providers) > 1 and not self._is_provider_down(providers[1]):
                selected_provider = providers[1]
                fallback_used = True
                logger.warning(
                    "Weather primary provider unavailable, switched to fallback provider: %s -> %s",
                    primary_provider,
                    selected_provider,
                )
            else:
                raise RuntimeError(f"No available weather provider. primary={primary_provider}")

        await asyncio.sleep(0.08)
        weather_types = ["晴", "多云", "阴", "小雨", "晴"]
        temps = [(18, 28), (20, 30), (19, 27), (17, 25), (20, 29)]

        today = datetime.now(timezone.utc).date()
        forecast = []
        for i in range(max(1, days)):
            low, high = temps[i % len(temps)]
            forecast.append(
                {
                    "date": (today + timedelta(days=i)).isoformat(),
                    "weather": weather_types[i % len(weather_types)],
                    "temp_low": low,
                    "temp_high": high,
                    "wind": "东南风3-4级",
                    "pm25": "35",
                }
            )

        result = {
            "city": city,
            "current": {
                "weather": "晴",
                "temp": 25,
                "humidity": "65%",
                "wind": "东南风2级",
            },
            "forecast": forecast,
            "_meta": {
                **self._build_meta(
                    cache_key,
                    source=f"weather_provider:{selected_provider}",
                    ttl_seconds=ttl_seconds,
                ),
                **self._refresh_meta(refresh_attempted=bypass_cache, refresh_success=bypass_cache),
                "provider_chain": providers,
                "provider_used": selected_provider,
                "fallback_used": fallback_used,
            },
        }
        self._set_cache(cache_key, result)
        result["_meta"] = {
            **self._build_meta(
                cache_key,
                source=f"weather_provider:{selected_provider}",
                ttl_seconds=ttl_seconds,
            ),
            **self._refresh_meta(refresh_attempted=bypass_cache, refresh_success=bypass_cache),
            "provider_chain": providers,
            "provider_used": selected_provider,
            "fallback_used": fallback_used,
        }
        return result


_travel_api_client: Optional[TravelAPIClient] = None


def get_travel_api_client() -> TravelAPIClient:
    """Return singleton travel api client."""

    global _travel_api_client
    if _travel_api_client is None:
        _travel_api_client = TravelAPIClient()
    return _travel_api_client
