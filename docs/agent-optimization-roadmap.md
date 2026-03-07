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
- In progress: scenario benchmark suite and replay tooling.

## Engineering Backlog (Next 10 Tasks)
1. Fix SSE frame formatting to true newline delimiters in web layer.
2. Add `run_id` propagation from web request into graph config metadata.
3. Add configurable default `max_parallelism` via env.
4. Add circuit-breaker status endpoint for diagnostics.
5. Add tool metadata schema validator in CI.
6. Add regression tests for content-block chunk streams.
7. Add integration test for `AGENT_STREAM_EVENTS_VERSION=v2`.
8. Add failure replay utility using persisted checkpoints.
9. Add plan-preview quality assertions (step dependency sanity).
10. Add prompt+tool contract tests per intent class.

## Next 4-Week Execution Plan
1. Week 1
   - Add scenario benchmark harness (`recommend`, `itinerary`, `budget`, `fallback`).
   - Generate baseline report artifacts under `docs/benchmarks/`.
2. Week 2
   - Add timeout/retry histogram metrics to execution summary.
   - Expose per-intent latency and tool-failure dashboards from diagnostics payload.
3. Week 3
   - Implement stale-data auto-refresh gate for critical tools (`weather`, `hotels`).
   - Add deterministic fallback templates for provider dual-failure cases.
4. Week 4
   - Add prompt+tool contract tests per intent class.
   - Run benchmark comparison against Week 1 baseline and publish delta report.
