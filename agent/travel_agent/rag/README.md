# RoutePilot RAG V1

本目录实现 RFC-0003 的知识入库与 Research Agent 检索边界。检索结果是
`RetrievalResult`，它是生成正式 `EvidenceBundle@1` 的 citation-ready 输入，
不会冒充最终 Artifact。

## 安全与租户边界

- `AuthorizedKnowledgeContext` 只能由 API/OIDC 或 Orchestrator 构造；
  `ResearchQuery` 没有 `tenant_id` 字段。
- 检索在排序前只保留公共数据和当前租户数据，PostgreSQL lexical/vector 两路
  使用同一个 server-derived tenant predicate。
- `tenant_admin` 只能管理本租户知识；只有 `admin` 可以发布公共知识。
- 管理 API 接收已提供的文本，不会抓取 `canonical_source_uri`。未来 connector
  仍须单独实现 DNS/IP 重检、域名 allowlist、重定向和响应大小限制。
- HTML active content 会移除，疑似 prompt injection 会保留并标记；所有 chunk
  固定为 `untrusted_evidence`，只能出现在 prompt 的 tainted evidence 区域，不能
  修改工具、租户、权限或系统指令。

## 检索能力与降级

Alembic `20260712_0006` 首先建立 PostgreSQL FTS/GIN 基线，然后尝试：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

只有 pgvector `0.8+` 可用时，迁移才建立 384 维 vector side table 和按
public/tenant 分开的 HNSW 索引。扩展未安装或托管数据库无安装权限时，迁移仍
会完成，side table 不存在就是运行时 capability flag。

返回 trace 永远明确说明实际能力：

- `retrieval_mode=hybrid, vector_status=used`：真实 semantic provider 和
  pgvector 均成功；
- `retrieval_mode=lexical, vector_status=disabled`：未配置 provider；
- `retrieval_mode=lexical, vector_status=unavailable`：扩展、索引或查询不可用；
- `retrieval_mode=lexical, vector_status=provider_not_semantic`：provider 明确
  不是语义模型。

`DeterministicHashEmbeddingProvider` 必须显式传入 `testing_only=True`，并始终
声明 `semantic_capable=False`。它只用于维度、持久化和可重复测试，绝不能作为
生产语义召回或评测依据。

## 组合方式

- 数据库：`ROUTEPILOT_RAG_DATABASE_URL`，未设置时回退读取
  `ROUTEPILOT_V1_DATABASE_URL`；运行时不会 `create_all`。
- 生产 embedding provider 由 composition root 从
  `ROUTEPILOT_EMBEDDING_ENDPOINT`、`ROUTEPILOT_EMBEDDING_API_KEY`、
  `ROUTEPILOT_EMBEDDING_MODEL` 注入；接口采用 OpenAI-compatible
  `/embeddings` 响应，V1 PostgreSQL 索引固定要求 384 维。未配置时会在
  retrieval trace 中明确标记 lexical-only，不伪装为语义召回。
- API：`POST /api/v1/knowledge/documents:ingest` 与
  `POST /api/v1/knowledge/search`。
- Agent：调用 `KnowledgeService.bind_research(context)` 获得 tenant-bound port，
  Research Agent 只看到 `search(query)`，无法选择租户。

每个入库请求需要 `Idempotency-Key`，请求 hash 与 content hash 分别处理重试和
内容去重。文档、chunk、检索结果都保留 source version、corpus revision、
freshness、license、trust tier 和 visibility provenance。

管理员实际摄取、检索验证、版本更新和当前删除限制见
[RAG 知识摄取 Runbook](../../../docs/operations/rag-ingestion.md)。
