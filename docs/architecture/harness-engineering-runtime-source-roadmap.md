# Harness Engineering Runtime Source Roadmap (2026-03-28)

## 1. Background

By 2026-03-28, the previous next-cycle Harness Engineering roadmap had been fully closed:

- `Delivery Harness` already converged on a shared artifact delivery descriptor, HTML snapshot replay, and artifact-first share/export paths.
- `Skills Market Harness` already shipped governed metadata, onboarding docs, selection policy, and the `schema + tests + docs + eval` audit gate.
- `Eval / Release Harness` already shipped subagent scorecards, release scorecards, CI checks, and release-manifest wiring.
- `Runtime Decoupling` already introduced the explicit bridge seam, supervisor request/context contracts, supervisor event contracts, typed preview payloads, typed tool-health diagnostics, and the first `legacy_runtime` shim.

That roadmap is now retired. This document is the active roadmap for the next cycle.

## 2. Goals

The next cycle is no longer about splitting giant modules for the first time. The new focus is to make the typed runtime seam become the single source of truth for runtime evolution:

1. Keep `AgentRuntime` consuming only explicit supervisor/runtime contracts.
2. Make `legacy_runtime` a replaceable source layer instead of a long-lived compatibility dumping ground.
3. Contractize runtime/ops artifacts so replay, support, delivery, and release evidence all share stable payloads.
4. Keep governance executable through local scripts, CI gates, and release evidence.

## 3. Workstreams

### 3.1 Runtime Source Harness

Goal:
- Replace remaining legacy graph runtime sources behind the typed seam without letting `AgentRuntime` drift back to loose kwargs or direct graph imports.

Planned actions:
- [completed 2026-03-28] Add `scripts/runtime_contract_audit.py` and wire it into `python scripts/dev.py infra-check` plus CI to guard the typed runtime seam.
- Replace remaining `legacy_runtime` event assembly paths with contract-first emitters.
- Move memory-aware source-state assembly out of the legacy shim and into smaller runtime-source adapters.
- Keep `AgentRuntime -> legacy_bridge -> legacy_runtime` as the only allowed compatibility chain.

### 3.2 Ops Artifact Harness

Goal:
- Make runtime doctor, support bundle, release manifest, and diagnostics outputs share typed artifact/report contracts.

Planned actions:
- [completed 2026-03-28] Add a typed runtime-doctor report contract and snapshot.
- [completed 2026-03-28] Contractize support-bundle manifest sections around runtime health, release evidence, and delivery evidence.
- Make release evidence reuse the same typed report sources instead of rebuilding ad-hoc dict payloads.

### 3.3 Delivery Bundle Harness

Goal:
- Upgrade the delivery path from “HTML plus share metadata” to a full artifact/delivery bundle that can be replayed and audited.

Planned actions:
- Package `artifact + execution receipt + HTML content + share metadata` as one delivery bundle descriptor.
- Add replay/snapshot coverage for the persisted share route and delivery bundle payload.
- Keep frontend delivery views consuming bundle/descriptor contracts instead of raw assistant text.

### 3.4 Governance Closure

Goal:
- Ensure future runtime/source changes cannot bypass executable governance.

Planned actions:
- Extend infra checks with runtime-source specific governance gates.
- Roll release scorecards forward to include runtime contract health.
- Keep README, docs index, and maintainer docs pointing at the active roadmap only.

## 4. Execution Phases

### Phase A: Runtime Contract Guardrails

- [completed 2026-03-28] Land `runtime_contract_audit` and wire it into local + CI checks.
- Lock the typed seam around `AgentRuntime`, `legacy_bridge`, `legacy_runtime`, and supervisor contracts.

### Phase B: Runtime Source Replacement

- Replace remaining legacy source assembly with contract-native adapters.
- Move memory/state preparation closer to source adapters and out of wide compatibility functions.

### Phase C: Ops Artifact Contracts

- [completed 2026-03-28] Add typed runtime doctor outputs.
- [completed 2026-03-28] Add typed support-bundle/report payloads.
- Reuse the same report contracts in release evidence.

### Phase D: Delivery Bundle Closure

- Package delivery bundle contracts.
- Add replay + snapshot coverage for persisted share/delivery routes.
- Keep frontend delivery UI consuming bundle contracts only.

## 5. Exit Criteria

This roadmap is complete when:

- `AgentRuntime` only depends on explicit runtime contracts and the bridge seam.
- Runtime source replacement no longer relies on ad-hoc kwargs expansion or direct graph imports outside the seam.
- Runtime doctor, support bundle, release evidence, and delivery bundle all have stable typed contracts or snapshots.
- `runtime_contract_audit` remains green in local and CI checks, alongside existing docstring, complexity, governance, skills-market, and release gates.

## 6. Current First Priorities

1. [completed 2026-03-28] Add the runtime contract audit gate.
2. [completed 2026-03-28] Contractize runtime doctor and support bundle outputs.
3. Continue replacing legacy runtime source assembly behind the typed seam.
