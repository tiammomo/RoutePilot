# 知识库建设与维护手册

RoutePilot 的知识体系分为三层，不能互相替代：

1. **内置稳定知识**：旅行决策方法、行程节奏、预算框架和证据使用规则，由仓库版本控制；
2. **目的地知识包**：已取得索引许可并经过人工审核的地点、政策和设施资料，按来源版本定期刷新；
3. **Provider 实时事实**：营业时间、票价、班次、天气、库存、道路状态和临时公告，查询时实时获取。

静态 RAG 负责“知道什么、为什么这样判断”；Provider Gateway 负责“此刻是否仍成立”。模型只组织已经获得的证据，不能补写缺失事实。

## 已内置的基础知识

仓库包含 `routepilot-travel-zh@2026.07.2`，位置是 [`agent/travel_agent/rag/curated/routepilot-travel-basics-zh/`](../../agent/travel_agent/rag/curated/routepilot-travel-basics-zh/README.md)。它包含：

- 旅行问答的决策优先框架；
- 行程节奏与空间组织；
- 预算范围与不确定性；
- 住宿区域选择；
- 老人、儿童与无障碍规划；
- 证据时效、许可、冲突和下线边界。
- 北京、上海、广东、浙江、江苏、四川、云南、福建、海南、陕西、广西、湖南的区域拆分、联游取舍与实时核验边界。

18 篇内容均由 RoutePilot 编写，使用仓库 MIT 许可，具备固定来源 URI、source version、SHA-256、人工复核记录和下一次复核时间。12 篇地区指南额外记录 24 个官方上游来源，并按 90 天周期复核。36 个固定查询覆盖所有文档；质量门禁会验证词法降级模式下仍能召回预期来源。

内置包不会在应用启动时自动写数据库。生产知识发布需要受限管理员身份、幂等键和可审计结果；这避免镜像启动绕过权限、许可审核或内容生命周期。

## 知识包结构

每个知识包包含一个 `manifest.json` 和若干本地正文：

```text
curated/<bundle-id>/
├── README.md
├── manifest.json
└── documents/
    ├── document-a.md
    └── document-b.md
```

manifest 必须记录：

- 稳定的 `bundle_id`、`corpus_revision` 和 `document_key`；
- 规范来源 URI、标题、来源类型和 `source_version`；
- 地区指南使用的 `upstream_sources`：官方 URI、publisher、source version、observed time 和 reference-only 说明；
- language、geo entities、tags 和 trust tier；
- license、indexing policy 和 retention；
- published/observed/valid 时间；
- 正文 SHA-256；
- reviewer、reviewed time、next review time 和审核说明；
- 每篇文档至少一个固定检索问题。

加载器会拒绝路径逃逸、符号链接、重复 key/URI、无查询覆盖、地区指南缺少上游来源、时区不明确、许可不允许索引，以及正文哈希漂移。正文改变后只更新 checksum 而不重新审核，虽然格式上可以做到，但不符合本手册和代码评审要求。

## 首次部署

先验证和查看不包含正文的发布计划：

```bash
.venv/bin/python -m scripts.v1_knowledge_base validate
.venv/bin/python -m scripts.v1_knowledge_base plan
```

使用受限运维会话中的 OIDC access token。token 只能通过环境变量提供，不能写入命令参数、仓库或日志：

```bash
export ROUTEPILOT_KNOWLEDGE_API_URL=http://127.0.0.1:38083/api/v1
export ROUTEPILOT_ACCESS_TOKEN='受限运维会话中的 access token'
```

发布为当前 tenant 私有知识只需要 `tenant_admin`：

```bash
.venv/bin/python -m scripts.v1_knowledge_base apply --visibility tenant
.venv/bin/python -m scripts.v1_knowledge_base verify --visibility tenant
```

发布为所有 tenant 可见的公共知识必须使用全局 `admin`，并显式确认影响范围：

```bash
.venv/bin/python -m scripts.v1_knowledge_base apply --allow-public
.venv/bin/python -m scripts.v1_knowledge_base verify
```

`apply` 在发出任何请求前完成整包校验，每篇文档使用由 bundle、revision、document key 和内容哈希推导的稳定幂等键。输出只包含 document ID、状态、chunk 数量和 vector 状态，不打印正文或 token。任何文档未进入 `published` 或没有 chunk 时整次命令失败并要求人工处理；已成功的前序文档可用相同命令安全重放。

`verify` 对明确的 corpus revision 运行全部固定查询。它既接受 `lexical`，也接受真实配置后的 `hybrid`，但每个查询都必须召回预期 source URI。命令通过后才能把该 revision 切给 Agent。

## Corpus 切换与回滚

Agent 只检索 `ROUTEPILOT_RAG_CORPUS_REVISION` 指定的版本。推荐使用蓝绿切换：

1. 用新 revision 构建完整知识发布，不覆盖旧 revision；
2. 对新 revision 执行 `validate`、`apply` 和 `verify`；
3. 在被忽略的 Compose env 或 secret manager 中更新 `ROUTEPILOT_RAG_CORPUS_REVISION`；
4. 重新创建 API 和 Run Worker；
5. 观察零结果率、检索模式、引用准确率和回答拒绝率；
6. 经过回滚窗口后再处理旧 revision。

```bash
docker compose \
  --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml \
  up --detach --force-recreate api run-worker
```

回滚只需把环境变量恢复为上一个已验证 revision 并重新创建服务。回滚窗口内不要 tombstone 旧 revision。当前 `v1_knowledge_publications` 只是预留数据结构，运行时切换仍以受控环境变量为准，不要假装数据库 publication 已经自动接管流量。

## 日常更新流程

### 1. 来源登记

为新来源记录 publisher、canonical URI、取得时间、版本标识、许可证明、允许的使用方式和负责人。当前地区指南采用 `reference_only`：维护人员阅读官方来源后编写原创摘要，只把来源目录写入 ingestion metadata，不抓取或复制官方正文。公开可访问不等于允许复制索引；许可不清楚时只保存链接目录，不摄取正文。

### 2. 内容分类

| 内容类型 | 建议复核周期 | 存储位置 |
| --- | --- | --- |
| RoutePilot 方法论 | 180 天 | 内置知识包 |
| 目的地稳定介绍 | 90 天 | 目的地知识包 |
| 预约、无障碍、交通政策 | 30 天或来源变更时 | 目的地知识包，并保留有效期 |
| 营业、票价、班次、天气、库存 | 不静态担保 | Provider Gateway |
| 安全、医疗、签证等高风险事实 | 按官方更新并提高审核等级 | 官方来源 + Provider，不做无依据推断 |

周期是维护基线，不表示内容在周期内必然正确。来源发布变更、许可撤回或用户报告错误时应立即复核。

### 3. 修改和版本化

修改正文后：

1. 提升该文档 `source_version`；
2. 计算并更新精确文件哈希：`sha256sum documents/<file>.md`；
3. 更新 `reviewer`、`reviewed_at`、`next_review_at` 和审核说明；
4. 新增或调整能覆盖变化内容的 smoke query；
5. 形成新发布时提升 `corpus_revision`；
6. 保留旧 manifest 或 Git tag，确保可回滚和审计。

### 4. 质量门禁

```bash
.venv/bin/python -m pytest -q tests/rag/test_curated_knowledge_bundle.py
.venv/bin/python -m pytest -q tests/rag
.venv/bin/python -m ruff check agent/travel_agent/rag scripts/v1_knowledge_base.py
.venv/bin/python -m mypy agent/travel_agent/rag scripts/v1_knowledge_base.py --config-file pyproject.toml
```

固定查询不是唯一评估。目的地包还应维护：正常问题、同义表达、无结果问题、过期过滤、相互冲突来源、跨 tenant 隔离和提示注入样本。大版本发布前记录 recall@k、citation precision@1、零结果率和错误引用案例。

## 下线和安全事件

以下情况应立即 `quarantined` 或 `tombstoned`：

- 来源许可撤回或保留期限到期；
- 内容包含隐私、凭据或不应公开的数据；
- 发现严重事实错误或来源被接管；
- 提示注入检测、解析或内容边界异常；
- 新版本已经稳定接管且旧版本超过回滚窗口。

状态变更必须继续使用 `Idempotency-Key + expected_version`，具体命令见 [RAG 摄取 Runbook](rag-ingestion.md)。紧急下线后要执行固定查询，确认被下线 URI 不再出现，并检查已经生成的 Artifact 是否需要发出用户可见更正；不能直接使用应用数据库角色删除表记录。

## 维护责任

每个知识包至少指定四类责任：

- **Knowledge owner**：决定覆盖范围和发布节奏；
- **Source steward**：跟踪来源版本、许可和失效；
- **Reviewer**：验证内容、风险与固定查询；
- **Operator**：以受限身份执行发布、切换、回滚和下线。

同一人可以在小团队中承担多项职责，但生产公共知识的内容变更与发布操作应保留独立复核记录。数据库、知识文档和检索审计都属于备份范围；备份与恢复后要重新运行 bundle verify。
