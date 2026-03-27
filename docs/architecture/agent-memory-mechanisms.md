# Agent Memory Mechanisms

本文档说明 memory 相关机制在 `agent/travel_agent/graph/memory_integration.py`、`agent/travel_agent/memory/persistence.py`、`agent/travel_agent/memory/conflict_resolution.py` 之间的当前分工，以及后续维护时的改动约束。

## 0.1 当前模块分工

- `graph/memory_integration.py`
  - 保留 session memory 编排、profile 写入、上下文注入、诊断聚合与持久化装配
- `memory/persistence.py`
  - 保留主备快照恢复、原子写入与磁盘持久化
- `memory/conflict_resolution.py`
  - 保留偏好冲突检测、澄清提示排序、同轮 retry 去重、显式覆盖闭环、resolved 审计日志与 persisted conflict schema 归一化

## 0. 改动约束（团队约定）

当 memory 相关逻辑发生任何变更时，必须同时满足：

1. 代码层：为新增关键分支补充解释“为什么这样做”的注释
2. 文档层：同步更新 `docs/architecture/agent-memory-mechanisms.md` 与相关索引文档
3. 测试层：至少新增或更新 1 个可回归用例，覆盖改动行为

## 1. 原子持久化与恢复

### 1.1 写入策略

- 主文件：`data/agent_memory.json`
- 备份文件：`data/agent_memory.json.bak`
- 写入方式：`temp file -> flush/fsync -> os.replace`

关键点：

1. 先写临时文件，确保 JSON 完整落盘后再替换目标文件。
2. 使用 `os.replace` 保证替换动作原子化，避免“写一半”状态。
3. 每次保存主文件后同步保存 `.bak`，提供热备恢复入口。

### 1.2 启动恢复策略

加载顺序：

1. 优先读取主文件
2. 主文件损坏时自动尝试 `.bak`
3. 若从 `.bak` 恢复成功，回写修复主文件

这套策略的目标是：进程异常中断后，尽量确保 memory 至少可恢复到最近一次完整快照。

## 2. Top-K 槽位注入

### 2.1 背景

完整 profile 注入 prompt 容易导致：

- token 膨胀
- 无关历史偏好干扰当前任务
- 成本与响应稳定性下降

### 2.2 当前实现

注入时不再传完整画像，而是仅注入“压缩画像”：

- `core_slots`：按 query 相关度 + 衰减置信度 + source 优先级计算，保留 Top-K
- `interests`：标签 Top-K
- `avoid_preferences`：规避偏好 Top-K

默认参数：

- `PROFILE_SLOT_TOP_K = 6`
- `PROFILE_TAG_TOP_K = 4`

### 2.3 维护建议

1. 新增 profile 字段时，先评估是否应进入 `core_slots` 候选。
2. 若字段高噪声，不建议进入 prompt 注入层。
3. Top-K 调整需配合 benchmark 观察 token 与回答质量变化。

### 2.4 Token 预算控制器（P1）

在 Top-K 之上，memory 注入新增预算护栏，避免长对话 prompt 持续膨胀：

- 总预算：`MEMORY_PROMPT_TOKEN_BUDGET`
- 分项预算：
  - `MEMORY_SUMMARY_TOKEN_BUDGET`
  - `MEMORY_PROFILE_TOKEN_BUDGET`
  - `MEMORY_CLARIFICATION_TOKEN_BUDGET`
  - `MEMORY_MESSAGE_TOKEN_BUDGET`
- 每条历史消息上限：`MEMORY_PER_MESSAGE_TOKEN_BUDGET`

预算策略：

1. 先放摘要，再放 compact profile，再放冲突澄清，再放历史消息。
2. 若 profile 超预算，自动缩小 `slot_top_k/tag_top_k`。
3. 历史消息在预算内按“最新优先”保留，且至少保留最小条数保证连续性。

### 2.5 写入去重与同义归并（P2）

profile 更新阶段已加入“写入前归一化”：

1. 属性值归一化
- `budget_hint` 统一成 `xxxx元`
- `days_hint/people_hint` 统一成整数
- `season_hint` 统一季节别名（如“春季”归并到“春”）

2. 偏好词归并
- `interests` 与 `avoid_preferences` 使用同义词表抽取 canonical term
- 列表按“去重 + 限长”写入，避免长期对话中标签膨胀

3. 目标
- 降低“同义词导致重复存储”的噪音
- 避免值形态不同引发伪冲突（如 `5000人民币` vs `5000元`）

### 2.6 跨会话偏好候选注入（P2）

在当前会话画像稀疏时，新增“跨会话稳定偏好候选”注入机制：

1. 候选来源
- 仅来自其他 session 的高质量属性与偏好词
- 按 source 优先级、衰减置信度、时间新鲜度与 query 相关度综合排序

2. 注入原则
- 仅补当前会话缺失的槽位，不覆盖当前会话已有值
- 以“候选提示”形式注入，不直接写回当前会话 profile
- 同时纳入 token 预算护栏，避免额外 prompt 膨胀

3. 关键参数
- `CROSS_SESSION_MIN_DECAY_CONFIDENCE`
- `CROSS_SESSION_MIN_SOURCE_PRIORITY`
- `CROSS_SESSION_LOOKBACK_HOURS`
- `CROSS_SESSION_ATTR_TOP_K`
- `CROSS_SESSION_TERM_TOP_K`
- `MEMORY_CROSS_SESSION_TOKEN_BUDGET`

## 3. 冲突自动澄清与闭环

### 3.1 自动澄清提示

当 `pending_clarifications` 非空时，系统会注入澄清提示，排序依据：

- 冲突严重度（high/medium/low）
- 与当前 query 的词项相关度
- 冲突条目新近度

默认最多注入 `CLARIFICATION_TOP_K = 2` 条。

自 `2026-03-27` 起，这条逻辑已经从 `graph/memory_integration.py` 下沉到 `agent/travel_agent/memory/conflict_resolution.py`，由 `MemoryConflictResolutionHelper` 统一维护；`AgentMemoryManager` 只保留委托出口和上下文装配。

### 3.2 澄清状态机（P1）

`pending_clarifications` 条目增加状态字段：

- `state`: `pending/resolved`
- `asked_at`: 最近一次澄清提问时间
- `retry_count`: 已提问次数
- `resolved_at`: 冲突被确认并收敛的时间
- `resolution_source`: 决策来源（如 `explicit_override` / `explicit_update`）

补充字段：

- `last_asked_fingerprint`: 同一用户轮次的去重标记，避免一次请求链路内重复消耗重试计数

### 3.3 重复追问抑制（P1）

当前默认 `CLARIFICATION_MAX_ASK_PER_ITEM = 1`：

1. 同一冲突最多追问 1 次。
2. 同一用户轮次内若重复构建上下文，不重复增加 `retry_count`。
3. 用户显式确认后，冲突条目从 pending 队列移除，并在 `conflict_log` 中写入 resolved 轨迹。

### 3.4 用户显式确认后的自动消歧

当用户消息包含“按这次/以最新/为准/就按”等显式决策短语时：

1. 对命中的冲突键执行强制覆盖（采用本轮显式值）
2. 清理该键的 `pending_clarifications`
3. 写入 `conflict_resolved` 日志，保留审计轨迹

这一步是“澄清闭环”的关键，避免同一冲突在后续轮次反复追问。

### 3.5 陈旧冲突降噪（P2）

针对长期未解决且已触达重试上限的冲突条目，引入自动降噪清理：

- 条件：`retry_count` 达上限且 `created_at` 超过过期窗口
- 行为：从 `pending_clarifications` 清理，避免旧冲突长期污染 prompt
- 说明：`conflict_log` 保留审计轨迹，不影响问题追溯

## 4. 低置信度属性清理（P2）

为保持 memory 紧凑度，新增低信号属性清理策略：

1. 对每个 attribute 计算 decayed confidence。
2. 当 decayed confidence 低于阈值且年龄超过窗口时，从 `attributes` 中移除。
3. 该清理在 profile 更新与 profile 归一化路径中都会触发。

默认关注参数：

- `ATTRIBUTE_GC_MIN_DECAY_CONFIDENCE`
- `ATTRIBUTE_GC_MIN_AGE_HOURS`

## 5. 关键代码入口

- 记忆注入：
  - `build_context_messages`
  - `build_context_messages_for_query`
  - `_build_budgeted_context_messages`
- 压缩画像：
  - `_build_compact_profile_for_prompt`
  - `_fit_compact_profile_to_budget`
- 跨会话候选：
  - `_build_cross_session_preference_hints`
  - `_fit_cross_session_hints_to_budget`
  - `_cross_session_recency_bonus`
- 归一化/去重：
  - `_normalize_profile_attr_value`
  - `_match_terms_by_synonyms`
  - `_merge_preference_terms`
  - `_cleanup_stale_profile_entries`
- 冲突澄清：
  - `_build_conflict_clarification_hint`
  - `_consume_conflict_clarification_hint`
  - `_extract_conflict_resolution_intent`
  - `_merge_profile_attr`
  - `memory/conflict_resolution.py` 中的 `MemoryConflictResolutionHelper`
- 可观测性：
  - `get_memory_diagnostics_sync`
  - `get_memory_diagnostics`
  - `_increment_profile_stat`
  - `_increment_session_stat`
- 持久化：
  - `_save_to_disk_locked`
  - `_load_from_disk`
  - `_atomic_write_json`

## 6. Memory 可观测指标（P2）

每个 session profile 内维护一组轻量统计字段 `stats`，用于持续评估 memory 质量：

- `clarification_asked`
- `conflict_resolved`
- `attr_pruned`
- `pending_pruned`
- `cross_session_hint_injected`

诊断接口：

1. `get_memory_diagnostics_sync(session_id=None)`
2. `get_memory_diagnostics(session_id=None)`

输出分两层：

- 单会话：消息数、属性数、待澄清数、最后消息时间、session 级 stats
- 全局：session 数、总消息数、平均属性数、全局澄清/清理/跨会话注入累计值

## 7. 回归测试

对应测试文件：`tests/test_agent_memory_unit.py`

关键用例：

1. 原子持久化 + `.bak` 恢复
2. Top-K 槽位注入裁剪
3. 冲突自动澄清提示注入
4. “按这次...为准”冲突闭环覆盖与 pending 清理
5. 澄清重试上限 + 同轮去重
6. memory context token 预算护栏
7. 同义词归并与伪冲突抑制
8. 低置信陈旧属性清理
9. 跨会话候选注入与当前会话槽位保护
10. 会话级与全局 memory 诊断指标

建议回归命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_memory_unit.py tests/test_session_memory_sync_unit.py -q
```
