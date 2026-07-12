# Provider Gateway 扩展指南

Provider Gateway 是所有实时旅行事实的唯一出口。新增 Provider 不等于在 Agent 中增加一次 HTTP 请求；它需要固定域名、结构化端口、标准化 provenance、租户限流和安全降级。

## 当前端口

- `PlaceSearchPort`
- `GeocodePort`
- `RouteMatrixPort`
- `OpeningHoursPort`
- `WeatherPort`

当前 allowlist 只有 `amap`。酒店、航班、火车、门票库存、价格和预订尚无正式端口。

## 接入步骤

1. 在 `agent/travel_agent/providers/models.py` 定义有界请求、结果和 provenance。
2. 在 `ports.py` 增加或实现 Protocol，不向 Agent 暴露 SDK/raw HTTP。
3. 在独立 adapter 中固定 HTTPS host/path，禁用重定向，验证 content type、状态和 schema。
4. 在 `ProviderSettings` 增加 canonical server-only 环境变量和 redacting secret。
5. 将 provider ID 加入静态已知集合和部署 allowlist，默认保持 fail closed。
6. 通过 Gateway 应用 deadline、重试、bulkhead、rate limit、circuit breaker 和 cache scope。
7. 为 capability/health metadata 增加脱敏描述，不返回 endpoint、key 或 raw error。
8. 增加 success、timeout、限流、畸形响应、取消、缓存隔离和 secret redaction 测试。
9. 更新 Provider README、平台配置示例和运维告警阈值。

## 数据与缓存策略

- 每个结果必须携带 `observed_at`、`valid_until`、freshness、provider ID/version。
- 路线、库存和价格不得在超出业务有效期后伪装为 fresh。
- `CacheScope.TENANT` 的 key 必须包含服务端 tenant；`PUBLIC` 只能由审核策略选择。
- Provider 条款禁止缓存时使用 `DISABLED`。
- stale-if-error 必须按能力单独审批并显式标记 `stale`。

## 网络安全

- 不接受模型或用户提供的目标 URL；
- 不跟随重定向；
- 域名、端口和路径固定 allowlist；
- DNS/IP 需要防止解析到 loopback、link-local 和私网；
- 限制响应体、解压后大小、content type 和解析深度；
- 不在日志记录 query 中的私人文本或 credential；
- 取消 Product Run/A2A Task 时取消 in-flight 请求。

## 交付门禁

```bash
python -m pytest -q tests/providers
python -m mypy agent/travel_agent/providers --config-file pyproject.toml
python scripts/v1_quality_gate.py --only a2a --only runtime --only security
```

接入交易或预订类 Provider 前，还需要单独设计支付、库存锁定、价格确认、退款、用户授权和合规边界；不得复用只读事实端口假装完成预订。
