# Agent Optimization Roadmap (LangChain/LangGraph 1.x Baseline)

## Scope
- Runtime baseline: `langchain>=1.0.0`, `langgraph>=1.0.0`
- Focus modules: `agent/src/graph`, `agent/src/llm`, `web/src/services/chat_service.py`

## Phase 1 (Stability Hardening, 1-2 weeks)
- Standardize streaming payload handling for all chat model chunk shapes.
- Make event stream version configurable with safe fallback (`v1` default).
- Add intent structured-output method fallback chain (`json_schema -> function_calling -> json_mode`).
- Acceptance:
  - Local streaming smoke tests pass.
  - Unit tests for chunk normalization and fallback chain pass.
  - No regression in `/api/chat/stream` contract.

## Phase 2 (Execution Quality, 2-3 weeks)
- Add tool-level concurrency budget by intent and by provider health.
- Add plan-step retry policy profile (tool-specific retries/backoff caps).
- Add execution observability fields: `run_id`, step-level retry histogram, timeout percentile.
- Acceptance:
  - P95 tool timeout rate reduced.
  - Mean plan completion latency reduced.
  - Error-code distribution visible in logs/metrics.

## Phase 3 (Answer Quality + Guardrails, 2-3 weeks)
- Add explicit citation contract from tool outputs into final answer template.
- Add stale-data handling strategy (auto-refresh gate for critical tools).
- Add stronger unsafe-input classification (pattern + lightweight rule score).
- Acceptance:
  - Factuality audit score improved on sampled dialogs.
  - Unsafe input false-negative rate reduced.

## Phase 4 (Scale + Maintainability, 3-4 weeks)
- Split planner/executor as independent runnables for easier A/B testing.
- Introduce scenario-driven benchmark suite (recommendation, itinerary, budget, fallback).
- Add configuration registry for all tunables (timeouts, retries, stream mode, structured method).
- Acceptance:
  - Benchmark pass-rate target reached.
  - Config changes can be rolled out without code edits.

## Current Status (2026-03-07)
- Done: streaming chunk normalization and stream event version fallback.
- Done: run-level tracing (`run_id`) through SSE and graph streaming paths.
- Done: tool/circuit diagnostics endpoint and health payload.
- Done: centralized runtime config registry for key agent tunables.
- Done: synthetic benchmark harness script with JSON/Markdown report output.
- Done: execution summary enriched with retry histogram, error-code distribution, latency percentiles.
- In progress: replay tooling and scenario quality benchmark expansion.

## Engineering Backlog (Next 10 Tasks)
1. Add tool metadata schema validator in CI.
2. Add integration test for `AGENT_STREAM_EVENTS_VERSION=v2`.
3. Add failure replay utility using persisted checkpoints.
4. Add plan-preview quality assertions (step dependency sanity).
5. Add prompt+tool contract tests per intent class.
6. Add benchmark scenario for dual-provider failure and fallback quality.
7. Add per-intent execution summary aggregation endpoint.
8. Add timeout SLO alert thresholds into diagnostics payload.
9. Add stale-data auto-refresh benchmark scenario.
10. Add benchmark trend report (compare latest vs previous baseline).

## Next 4-Week Execution Plan
1. Week 1
   - Expand benchmark harness scenarios (`budget`, `dual-failure fallback`).
   - Persist baseline report artifacts under `docs/benchmarks/`.
2. Week 2
   - Add per-intent latency and tool-failure dashboards from diagnostics payload.
   - Add benchmark trend report generator against baseline.
3. Week 3
   - Implement stale-data auto-refresh gate for critical tools (`weather`, `hotels`).
   - Add deterministic fallback templates for provider dual-failure cases.
4. Week 4
   - Add prompt+tool contract tests per intent class.
   - Run benchmark comparison against Week 1 baseline and publish delta report.
