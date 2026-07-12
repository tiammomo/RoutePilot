# Artifact 与事件契约扩展

Artifact 是 RoutePilot 的业务事实边界。自然语言可以触发命令，但正式状态必须落在严格、版本化、跨语言一致的契约中。

## 单一变更链

一次 Artifact 变更必须同步完成：

```text
Pydantic contract
  -> JSON Schema
  -> generated TypeScript types
  -> backend validation/public projection
  -> Python + JSON Schema + TypeScript contract tests
  -> consumer UI/Agent tests
```

不能只修改前端 interface、只编辑生成的 JSON，或在运行时接受额外自由字段。

## 新增 Artifact

1. 在 `packages/python/routepilot_contracts/src/routepilot_contracts/` 定义继承 `ContractModel` 的严格模型。
2. 增加固定 `artifact_type` 和 `schema_version`。
3. 为 ID、列表、文本、金额、日期和嵌套结构设置明确上限。
4. 把模型加入 `ARTIFACT_MODELS` 和 validation adapter。
5. 在生成器 `SCHEMA_TARGETS` 中登记 JSON Schema 文件。
6. 更新 `ContractName`、A2A profile 输入输出 allowlist 和 Runtime consumer。
7. 生成 schema，并更新 TypeScript 生成包。
8. 在 `tests/contract/` 增加有效样本、无效边界和 parity 测试。

生成 JSON Schema：

```bash
PYTHONPATH=packages/python/routepilot_contracts/src \
  python -m routepilot_contracts.generate --output-root schemas
```

生成文件不得手工编辑。breaking change 使用新的 major contract，例如 `TripSnapshot@2`，不能静默改变 `@1` 的语义。

## Provenance 与隐私检查

证据型 Artifact 至少考虑 source、version、license、observed/retrieved time、validity、trust 和 retrieval trace。实时 Provider 数据必须说明 provider/version/freshness。

禁止进入 Artifact：

- prompt、chain-of-thought 或 reasoning；
- tool 原始响应和内部异常；
- access token、cookie、API key、数据库 DSN；
- 不必要的个人身份信息；
- 任意可执行指令或未经限制的 HTML。

分享不是复制原 Artifact，而是显式生成最小化 `ShareSnapshot` 投影。

## 修改 public event

1. 在 Python event contract 中增加封闭 event/data model；
2. 更新后端 `PUBLIC_EVENT_TYPES`；
3. 更新 `PUBLIC_EVENT_DATA_FIELDS` 和逐类型 projection；
4. 更新 JSON Schema 和生成的 TypeScript union；
5. 更新 Web reducer，只处理公开字段；
6. 增加未知字段被丢弃、禁止字段不泄露和 SSE replay 测试。

public event 只能表示用户可观察状态。Agent 私有消息、Provider raw error 和内部 diagnostics 不能为了调试方便进入事件。

## Artifact version 与状态

- 旧版本不可修改；编辑创建新候选版本；
- 发布使用 CAS，并在事务内 supersede 旧正式版本、更新 Trip 指针和写入事件/outbox；
- Product Run 和 A2A Task 的完成状态不能代替 Artifact 发布；
- 历史版本只读；撤销不会删除历史；
- 重规划必须固定当前正式 Artifact ID 与 version。

## 必跑门禁

```bash
python scripts/v1_quality_gate.py --only contracts --only backend --only a2a --only web
git diff --check
```

修改数据库字段时还必须增加 Alembic revision，并执行 `--only migration`。提交中应同时包含契约、生成物、消费者和测试，避免跨提交留下不可构建状态。
