# RoutePilot A2A v1

This package is the trusted A2A 1.0 boundary for professional travel agents. Wire objects,
ProtoJSON parsing, JSON-RPC method routing, SSE envelopes, and protocol errors come from the
official `a2a-sdk`; RoutePilot adds only the versioned travel profile and task-control policy.

The curated V1 interfaces are `answering`, `research`, `planner`, `validation`, and `semantic-verifier`.
Every domain request must declare A2A version `1.0`, the RoutePilot travel extension, an
authenticated tenant, a UUID `dispatch_id`, a Product `run_id`, and one bounded structured Part.
Browser clients do not call these endpoints directly.

## Persistence boundary

`AgentTaskPersistence` is the storage port. `InMemoryAgentTaskStore` is intentionally a local/test
reference adapter. `PostgresAgentTaskStore` is the production adapter selected from
`ROUTEPILOT_A2A_DATABASE_URL` (falling back to `ROUTEPILOT_V1_DATABASE_URL`). It preserves these
invariants:

1. Uniqueness is `(tenant_id, agent_interface_id, dispatch_id)` and duplicate dispatches return the
   original Task.
2. Dispatch inbox insert, Task creation, and any retained initial events are one transaction.
3. Every Task transition uses a monotonic version/CAS; late results cannot overwrite cancellation.
4. Task events remain replayable for `SendStreamingMessage` and `SubscribeToTask` reconciliation.
5. Tenant predicates are applied in every read and write, independently of the request `tenant`
   field.
6. Protobuf snapshots/events use deterministic bytes with hard bounds; invocation JSON is
   canonicalized and bounded before it is stored.
7. A submitted/working Task is executed only while a database-clock lease is owned. The
   monotonic execution attempt is also a write fence, so an expired process cannot commit a late
   result after another process recovers the Task.
8. A typed input supplement is retained with the working snapshot until settlement, allowing a
   restarted process to invoke the executor with the same validated input.

The PostgreSQL adapter writes a bounded `NOTIFY` after each successful transition and implements
the persistence port's wait operation with portable bounded polling, so SSE replay works across
API processes even when no dedicated PostgreSQL listener is configured. Production and staging
fail closed when neither A2A nor V1 PostgreSQL DSN is configured.

Product Run lifecycle remains owned by `RunCoordinator`. A2A Task state is linked through
`RunTaskRef` and must be translated into Run commands/events rather than written into Product Run
state directly. Local orchestration derives each dispatch UUID from tenant, Product Run, agent
interface, and stage, then recovers the persisted invocation instead of creating a second Task.
Product Run cancellation first persists `cancel_requested`, transitions every cancelable linked
A2A Task to `canceled`, and relies on the remote Task heartbeat to cancel the owning executor and
its in-flight provider coroutine. A failed propagation stays retryable and is not reported as a
fully canceled graph.
