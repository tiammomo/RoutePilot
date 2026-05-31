# 故障排查

## 先分层

遇到问题时先判断是哪一层，不要一上来就重启所有服务。QuantPilot 的问题大多可以落在这几层：

| 层 | 典型现象 | 第一入口 |
| --- | --- | --- |
| 环境层 | 端口打不开、CLI 找不到、数据库不可达 | `npm run doctor`、`/ops-platform` 基础环境 |
| 数据层 | K 线为空、成交额缺失、补数很慢 | 策略平台补数弹窗、market-data 日志 |
| 生成层 | Agent 报错、达到最大轮数、页面没生成完 | 项目聊天页、生成链路观测 |
| 契约层 | 产物缺失、验证失败、证据不完整 | 工作空间健康、`.quantpilot/*.json` |
| 视觉层 | 页面能打开但难看、溢出、图表空白 | Playwright 截图、视觉检查报告 |
| 评测层 | CI 或评测平台失败 | 评测报告、运行队列、失败修复 |

如果判断不出来，按“环境、数据、契约、页面、skill”的顺序排查。这个顺序通常比直接改页面更省时间。

## 一键诊断

优先运行：

```bash
npm run doctor
```

它会快速检查：

- Node、npm、uv 版本。
- Claude / MiniMax 环境变量。
- Claude Code 和 Codex CLI。
- 前端 `3000` 和后端 `8000` 可达性。
- PostgreSQL / TimescaleDB、Loki 可观测性和降级配置。
- workspace 目录。
- Skills 注册表、lock 和压缩包一致性。
- 生成产物策略。
- 验证修复契约。
- benchmark 覆盖。
- eval 定时器。
- 最近评测报告。

提交前或排查复杂问题时运行完整诊断：

```bash
npm run doctor:full
```

完整诊断会额外运行 `lint`、`type-check`、后端 `ruff` 和后端 `pytest`。

如果本机没有启动部分组件，可通过 `.env` 控制降级：

```bash
QUANTPILOT_DEGRADATION_MODE=offline npm run doctor
```

`offline` 会跳过市场数据后端、Loki/Grafana/Alloy 和 Redis 等可选外部探测；`auto` 适合本地开发；`strict` 适合 CI 或生产巡检。

## 3000 端口被占用

```bash
lsof -i :3000
```

释放端口后重新执行：

```bash
npm run dev
```

主前端应优先使用：

```text
http://localhost:3000
```

## 8000 后端不可用

```bash
curl http://127.0.0.1:8000/health
```

如果没有响应：

```bash
cd services/market-data
uv run quantpilot-market-api
```

如果只是浏览平台页面而不需要实时行情，可临时关闭市场数据后端探测：

```bash
QUANTPILOT_MARKET_API_ENABLED=0 npm run doctor
```

## Loki / Grafana 不可用

启动本地可观测性组件：

```bash
npm run obs:up
```

默认入口：

```text
Loki: http://127.0.0.1:3100
Grafana: http://localhost:3001
Alloy: http://localhost:12345
```

如果不需要集中日志，可保持 Loki 停止。运维平台会降级读取本地日志文件；`npm run doctor` 在 `auto` 模式下只给 warning，不会失败。

## Claude Code 找不到 MiniMax 配置

确认 `.env`、`.env.local` 或 `~/.claude/settings.json` 中包含：

- `ANTHROPIC_BASE_URL`
- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_MODEL`

然后重启：

```bash
npm run dev
```

可以用脚本写入本机 Claude Code 配置：

```bash
bash claude_code_minimax_env.sh
```

## Codex CLI 没有调用 GPT-5.5

确认：

- `codex --version` 可执行。
- `CODEX_OPENAI_BASE_URL` 已配置。
- `CODEX_OPENAI_API_KEY` 已配置在本地环境或 `~/.codex/auth.json`。
- 前端模型选择为 `Codex CLI / GPT-5.5`。

## 生成页面没有真实行情

先确认后端可用：

```bash
curl "http://127.0.0.1:8000/api/v1/quotes/realtime/600519"
```

再检查生成项目中是否存在：

```text
.claude/skills/
.quantpilot/run_plan.json
.quantpilot/generation-state.json
.quantpilot/generation-queue.json
data_file/final/dashboard-data.json
evidence/sources.json
evidence/data_quality.json
```

如果这些文件都存在，但页面仍然没有真实行情，再看 `data_file/final/dashboard-data.json` 里是否真的有目标标的和足够样本。很多“页面问题”其实是 final data 只写了一天数据，或者字段名和页面绑定字段不一致。

## 可视化页面只有静态文案

通常说明取数、final 数据文件或 `quant-visualization-html` 没有完整执行。优先查看：

- 聊天页执行过程。
- `/ops-platform` 工作空间健康。
- `/ops-platform` 链路观测。
- `.quantpilot/events.jsonl`。
- `.quantpilot/validation.json`。
- `.quantpilot/validation-repair-plan.json`。
- `.quantpilot/artifact-contracts.json`。
- `.quantpilot/visual-validation.json`。

## 生成链路卡在运行中

检查：

```text
.quantpilot/generation-state.json
.quantpilot/generation-queue.json
```

如果用户已取消请求但队列仍显示 running，优先查看：

- `POST /api/chat/<project_id>/pause`
- `/ops-platform` 中的 active request。
- `.quantpilot/events.jsonl` 中最近的 queue 事件。

## 自动验证失败后没有修复

检查：

- `.quantpilot/validation.json` 是否存在。
- `.quantpilot/validation-repair-plan.json` 是否生成。
- `.quantpilot/generation-state.json` 中 `repairAttemptCount` 是否增加。
- Agent runtime 是否已被取消。
- `npm run check:validation-repair` 是否通过。

## Playwright 检查时页面可见但点击无效

优先使用：

```text
http://localhost:3000
```

项目已在 `next.config.js` 中允许 `127.0.0.1` 作为本地 dev origin，但日常浏览和截图仍推荐使用 `localhost`。

## Skills 发布后生成项目仍使用旧版本

检查：

```bash
npm run check:skills
npm run package:skills
```

确认这些文件有同步更新：

```text
.claude/skills.registry.json
.claude/skills.lock.json
.claude/skills.changelog.json
.claude/skill-packages/<skill-id>.tgz
```

如果需要临时安装 legacy alias：

```bash
QUANTPILOT_INSTALL_LEGACY_SKILLS=1 npm run dev
```

## 策略补数看起来卡住

先确认它是“卡住”还是“正在低频推进”。补数任务会因为外部源限速、请求延迟和本地 preflight 跳过而显得慢。

优先看：

- 策略平台补数弹窗里的心跳、当前标的、完成批次和预计完成时间。
- market-data 后端日志中是否持续出现 ingestion job 更新。
- `quant.market_data_ingestion_jobs` 里 parent job 的 `status`、`completed_symbols`、`rows_upserted` 和 `metadata.last_heartbeat_at`。

如果本地已有完整数据，后端会返回 `skipped`，`skip_reason=local_coverage_ready`。这代表本地覆盖已满足目标，不需要再拉外部接口。

## 日志太多不知道看哪条

先缩时间范围，再搜关键词。常用关键词：

```text
error
failed
validation
artifact
ingestion
timeout
Reached maximum
```

Loki 可用时优先在运维平台日志页查集中日志；Loki 不可用时查看本地文件日志。Next dev 的编译成功日志很多，通常可以先忽略，重点看红色错误、API 失败、SSE 断连和 Agent runtime 返回的错误。
