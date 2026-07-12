# RoutePilot Runtime V2

Runtime V2 coordinates grounded question answering and the artifact-first
Research → Planner → Validation → Semantic Verifier planning chain. It uses the
same durable A2A `TaskService` as the HTTP protocol adapter and never bypasses
Task idempotency, leases, cancellation, or event replay.

The orchestrator exchanges only validated versioned Artifact inputs/outputs.
Deterministic calculations remain local domain services. Product Run state is
owned by the backend coordinator; A2A Task completion alone cannot publish an
Artifact or complete a Product Run.

Start with the [Agent extension guide](../../../docs/development/agent-extension.md)
and [Artifact contract guide](../../../docs/development/artifact-contracts.md)
before changing stages or executor outputs.
