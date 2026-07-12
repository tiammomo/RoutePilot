# RAG 知识摄取与检索 Runbook

本文说明如何把已经取得、审核并允许索引的文本加入 RoutePilot。V1 摄取 API 不抓取 URL；调用者必须先在受控流程中获取文本、确认许可并完成内容审核。

## 权限与边界

- `tenant_admin` 可以管理当前 tenant 的知识；
- `admin` 可以管理当前 tenant，并发布 `public` 知识；
- 普通 owner/editor/viewer 不能摄取文档；
- tenant 来自已验证的 Principal，请求体不能选择 tenant；
- 文档内容始终标记为 `untrusted_evidence`，不能改变系统指令或触发工具。

默认本地 Web 身份是 `owner`，不具备摄取权限。知识管理应使用受信运维客户端和具备相应角色的 OIDC access token，不能临时扩大浏览器角色。

## 摄取前检查

1. 确认来源 URI、发布者和 source version；
2. 确认许可允许索引，并记录 retention；
3. 删除凭据、Cookie、支付信息和不必要的个人信息；
4. 确认文本不超过 262,144 字符；
5. 选择稳定 `corpus_revision`，例如 `cn-travel-2026-07`；
6. 为该请求生成并保存 idempotency key。

## 摄取示例

```bash
export ROUTEPILOT_API=http://127.0.0.1:38083/api/v1
export ROUTEPILOT_ACCESS_TOKEN='受限运维会话中的 access token'
export INGESTION_KEY="knowledge-$(openssl rand -hex 16)"
```

请求：

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ROUTEPILOT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $INGESTION_KEY" \
  -d '{
    "canonical_source_uri": "https://example.org/travel/beijing-accessibility",
    "source_type": "official_guide",
    "source_version": "2026-07-01",
    "title": "北京主要景点无障碍出行说明",
    "content": "这里放置已经审核的纯文本内容。",
    "visibility_scope": "tenant",
    "language": "zh-CN",
    "geo_entities": ["北京"],
    "tags": ["无障碍", "公共交通"],
    "published_at": "2026-07-01T00:00:00+08:00",
    "observed_at": "2026-07-13T00:00:00+08:00",
    "valid_from": "2026-07-01T00:00:00+08:00",
    "valid_until": "2026-12-31T23:59:59+08:00",
    "corpus_revision": "cn-travel-2026-07",
    "trust_tier": "official",
    "license": {
      "license_id": "operator-reviewed-use",
      "license_url": "https://example.org/legal/content-policy",
      "usage_policy": "May index and cite with attribution inside this tenant.",
      "indexing_allowed": true,
      "retention_days": 365
    },
    "metadata": {"publisher": "示例机构"}
  }' \
  "$ROUTEPILOT_API/knowledge/documents:ingest"
```

成功响应需要审核：

- `status=published`；
- `chunk_count > 0`；
- `idempotent_replay` 是否符合预期；
- `vector_status` 是 `indexed`、`disabled`、`unavailable` 或 `provider_not_semantic`。

相同 key 与完全相同请求可以安全重放。相同 key 与不同请求会返回 `409`，不要换 key 掩盖内容冲突。

## 检索验证

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ROUTEPILOT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "带老人参观北京景点有哪些无障碍注意事项",
    "claim_scope": "travel.accessibility",
    "corpus_revision": "cn-travel-2026-07",
    "filters": {
      "languages": ["zh-CN"],
      "source_types": ["official_guide"],
      "trust_tiers": ["official"],
      "geo_entities": ["北京"],
      "tags": ["无障碍"],
      "valid_at": "2026-07-13T00:00:00+08:00",
      "include_stale": false
    },
    "top_k": 5,
    "score_threshold": 0.05
  }' \
  "$ROUTEPILOT_API/knowledge/search"
```

验证 `items` 的 source/version/license/freshness/trust，并检查 `trace`：

- `hybrid + used` 才表示真实向量召回生效；
- `lexical + disabled` 表示未配置 embedding；
- `lexical + unavailable` 表示 pgvector、索引或查询不可用；
- `provider_not_semantic` 不能当成语义召回。

## 更新、过期与删除

更新来源时使用新的 `source_version`、合适的 `corpus_revision` 和新的 idempotency key，不要覆盖旧 provenance。

当前 V1 HTTP API 尚未提供文档 tombstone、批量删除、connector 抓取或全库重新嵌入端点。因此：

- 不得用应用数据库角色直接删除知识表；
- 需要紧急下线内容时，停止相关知识的使用并由管理员通过审核过的 migration/维护变更处理；
- retention 执行、批量重建和 connector 生命周期属于后续运维能力，不能在文档中假装已经自动完成。

## 质量与安全抽查

- 每个 corpus revision 保留摄取清单、来源 checksum 和许可审批；
- 抽查典型查询、无结果查询、跨 tenant 查询和 prompt injection 文本；
- 不以确定性 hash embedding 的测试结果作为生产语义质量；
- RAG 不作为天气、营业、路线、库存和价格的实时权威；
- 发现来源失效或许可变化时，记录时间、source ID、document ID 和处理决定。
