# Agent Benchmark Trend Report

- generated_at: 2026-03-08T06:41:32.814843+00:00
- current_report: docs/benchmarks/agent_benchmark_latest.json
- baseline_report: docs/benchmarks/agent_benchmark_baseline.json
- baseline_missing: true

## Aggregate Diff

| metric | current | baseline | delta | direction |
|---|---:|---:|---:|---|
| avg_success_rate | 0.6834 | 0.6834 | 0.0000 | higher |
| avg_tool_hit_rate | 0.6834 | 0.6834 | 0.0000 | higher |
| avg_elapsed_ms | 26.0000 | 26.0000 | 0.0000 | lower |
| fallback_steps_total | 2.0000 | 2.0000 | 0.0000 | lower |
| hallucination_rate | 0.0000 | 0.0000 | 0.0000 | lower |

## Scenario Diff

| scenario | current_success | baseline_success | delta_success | current_elapsed_ms | baseline_elapsed_ms | delta_elapsed_ms | current_fallback | baseline_fallback | delta_fallback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| attractions-city | 0.6667 | 0.6667 | 0.0000 | 25 | 25 | 0.0000 | 0 | 0 | 0.0000 |
| budget-city | 0.6667 | 0.6667 | 0.0000 | 25 | 25 | 0.0000 | 1 | 1 | 0.0000 |
| itinerary-city | 0.7500 | 0.7500 | 0.0000 | 26 | 26 | 0.0000 | 1 | 1 | 0.0000 |
| recommend-city | 0.6667 | 0.6667 | 0.0000 | 29 | 29 | 0.0000 | 0 | 0 | 0.0000 |
| tips-city | 0.6667 | 0.6667 | 0.0000 | 26 | 26 | 0.0000 | 0 | 0 | 0.0000 |
