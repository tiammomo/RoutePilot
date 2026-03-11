# Testing Guide

## 测试分层

### 1. 后端 / 集成测试

目录：`tests/`

覆盖内容：

- FastAPI 路由
- Agent 执行链路
- guardrails
- stale / verification / fallback
- 工具结果聚合与健康统计

运行命令：

```bash
python -m pytest tests -q
```

### 2. 前端测试

目录：`frontend/`

运行命令：

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```

说明：

- `lint` 实际执行 `tsc --noEmit`
- `build` 可用于发现类型、SSR、编码和导入链路问题

### 3. Agent 质量脚本

常用脚本：

```bash
python scripts/agent_benchmark.py --output-dir docs/benchmarks
python scripts/agent_benchmark_trend.py --current docs/benchmarks/agent_benchmark_latest.json --baseline docs/benchmarks/agent_benchmark_baseline.json --output docs/benchmarks/agent_benchmark_trend_latest.md
python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0
python scripts/agent_quality_gate.py --golden-report docs/benchmarks/agent_golden_eval_latest.json --benchmark-report docs/benchmarks/agent_benchmark_latest.json --baseline-benchmark-report docs/benchmarks/agent_benchmark_baseline.json
```

这些脚本主要用于：

- benchmark 回归
- golden set 稳定性评估
- CI/CD 质量门禁

## 推荐的本地回归顺序

### 日常前端改动

```bash
cd frontend
npm run lint
npm run build
```

### 改 API / Agent 后

```bash
python -m pytest tests -q
python scripts/docstring_audit.py --strict
cd frontend
npm run lint
npm run build
```

### 发版前建议

```bash
python -m pytest tests -q
python scripts/docstring_audit.py --strict
cd frontend && npm run lint && npm run test:run && npm run build
cd ..
python scripts/agent_benchmark.py --output-dir docs/benchmarks
python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0
python scripts/agent_quality_gate.py --golden-report docs/benchmarks/agent_golden_eval_latest.json --benchmark-report docs/benchmarks/agent_benchmark_latest.json --baseline-benchmark-report docs/benchmarks/agent_benchmark_baseline.json
```

## 注释质量检查

项目提供 `scripts/docstring_audit.py` 用于审计 Python 注释覆盖率：

```bash
python scripts/docstring_audit.py
python scripts/docstring_audit.py --strict
```

说明：

1. 默认扫描 `agent/`、`web/`、`scripts/`。
2. `--strict` 模式下，只要存在缺失 docstring 会返回非零退出码，适合 CI 使用。

## Replay / 故障回放

用于复现某个 session 的执行路径并导出报告。

### 执行真实 replay

```bash
python scripts/agent_replay.py --session-id <session_id> --db data/langgraph_checkpoints.sqlite3
```

### 只导出 checkpoint 快照

```bash
python scripts/agent_replay.py --session-id <session_id> --db data/langgraph_checkpoints.sqlite3 --dry-run
```

默认输出目录：`docs/benchmarks/`

产物示例：

- `agent_replay_<session>_<timestamp>.json`
- `agent_replay_<session>_<timestamp>.md`

## CI 常见失败点

### 1. 编码问题

典型表现：

- `invalid utf-8 sequence`
- 构建时读取源码失败

建议：

- 统一用 UTF-8 保存
- 避免通过有编码污染的终端直接写中文源码
- 改动后至少跑一次 `npm run build`

### 2. SSE / 流式测试不稳定

优先检查：

- `/api/chat/stream` 是否正常返回 `text/event-stream`
- 模型配置是否可用
- 工具 provider 是否超时

### 3. Golden eval / 正则错误

优先检查：

- 新增文案是否影响断言
- 正则是否有未转义字符
- 聚合字段和测试预期是否一致

## 浏览器联调建议

如果需要做真实界面验证，建议至少覆盖：

- 首页是否正常打开
- 对话流是否能生成回答
- 城市探索是否能加载
- 导出图片和分享按钮是否能触发
- 路线预览与重排按钮是否工作
