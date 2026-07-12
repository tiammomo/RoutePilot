# RoutePilot Provider Gateway V1

This package is the only outbound boundary for time-sensitive travel facts.
RAG remains responsible for versioned structured/unstructured knowledge; it is
not authoritative for current routes, weather, inventory, prices or opening
status. Provider results always include `observed_at`, `valid_until`,
`freshness_status`, provider ID/version and capability provenance.

## Production capability matrix

| Port | V1 provider | Endpoint/version | Gateway cache ceiling | Target call SLA |
| --- | --- | --- | --- | --- |
| `PlaceSearchPort` | AMap | `GET https://restapi.amap.com/v3/place/text` or `/v3/place/around` | 15 min | deadline 4 s, at most 1 retry |
| `GeocodePort` | AMap | `GET https://restapi.amap.com/v3/geocode/geo` | 24 h | deadline 4 s, at most 1 retry |
| `RouteMatrixPort` | AMap | `GET https://restapi.amap.com/v3/distance` | 3 min | deadline 4 s for the bounded matrix, at most 1 retry |
| `OpeningHoursPort` | AMap | `GET https://restapi.amap.com/v5/place/detail?show_fields=business` | 5 min | deadline 4 s, batches of at most 10 IDs |
| `WeatherPort` | AMap | v3 reverse geocode + `GET /v3/weather/weatherInfo?extensions=all` | 5 min | one shared deadline across both calls |

The matrix port uses the official distance endpoint because it accepts up to
100 origins for one destination. V1 further caps requests at 25 origins and 10
destinations. AMap's route-planning 2.0 endpoints are currently v5, but they are
point-to-point route products and are not silently substituted for this matrix
contract.

Official references verified 2026-07-12:

- [AMap POI search](https://lbs.amap.com/api/webservice/guide/api/search/)
- [AMap geocoding](https://lbs.amap.com/api/webservice/guide/api/georegeo/)
- [AMap POI search 2.0 and ID detail](https://lbs.amap.com/api/webservice/guide/api-advanced/newpoisearch)
- [AMap weather forecast](https://lbs.amap.com/api/webservice/guide/api/weatherinfo)
- [AMap distance/path APIs](https://lbs.amap.com/api/webservice/guide/api/direction/)
- [AMap route planning 2.0](https://lbs.amap.com/api/webservice/guide/api/newroute)
- [AMap Web Service error codes](https://lbs.amap.com/api/webservice/guide/tools/info/)

The upstream product quota, availability and legal terms remain AMap's SLA,
not RoutePilot's. RoutePilot's 4-second target is a local per-operation deadline
and may return a safe `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMITED`,
`PROVIDER_CIRCUIT_OPEN` or `PROVIDER_UNAVAILABLE` response before that.

## Configuration and safety

- Optional server-only key: `ROUTEPILOT_AMAP_WEB_KEY`. The real value belongs
  only in an ignored local env file or a production secret manager; it must not
  appear in Compose YAML, example files, browser bundles, logs or Artifacts.
- Explicit provider allowlist: `ROUTEPILOT_PROVIDER_ALLOWLIST` (defaults to
  `amap`; the single AMap adapter advertises all five approved capabilities).
- Bounded AMap socket timeout: `ROUTEPILOT_AMAP_HTTP_TIMEOUT_SECONDS` (defaults
  to 3 seconds, accepted range 0.1–15 seconds).
- `ProviderSettings` is the single typed configuration surface and stores the
  key as a redacting secret type.
- Deprecated key aliases are intentionally not read. Browser bundles and metadata
  endpoints never receive the key.
- The adapter can reach only fixed HTTPS paths on `restapi.amap.com`, disables
  redirects, reuses one bounded `httpx.AsyncClient`, validates HTTP/content
  type/upstream status/schema and discards raw provider errors.
- Retry is bounded, jittered and only applied to safe read calls. The gateway
  also enforces per-tenant/provider rate windows, circuit breaking, bulkheads,
  absolute deadlines and cancellation.
- Stale-if-error is bounded and explicit: POI 1 h, geocode 7 d, opening status
  5 min and weather 10 min beyond the fresh TTL. Route matrices never use a
  stale fallback. Any fallback is returned with `freshness_status=stale`.
- `CacheScope.TENANT` includes the authenticated tenant in the cache key;
  private queries can never be reused across tenants. Use `DISABLED` for data
  that terms or privacy policy forbid caching. `PUBLIC` must only be selected
  by trusted server policy, never by model input.
- Without the AMap key, one unconfigured AMap descriptor covers all five
  capabilities and fails explicitly. No mock or stale RAG fact is presented
  as live data.

Only authenticated metadata is exposed over HTTP:

- `GET /api/v1/providers/capabilities`
- `GET /api/v1/providers/health`

These endpoints expose IDs, API family/version, capabilities,
configured/allowlisted flags and circuit state. They do not make upstream
probes and never include endpoints, environment values, raw errors or keys.

Adding a provider or a new live-fact port must follow the
[Provider Gateway extension guide](../../../docs/development/provider-extension.md).
