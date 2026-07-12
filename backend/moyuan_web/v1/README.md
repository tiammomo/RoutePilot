# RoutePilot V1 API control plane

This package owns authenticated `/api/v1` Trip, Run, Artifact, A2A, RAG,
Provider metadata, membership, and share control-plane routes. PostgreSQL is
the system of record; Redis is only the external execution delivery layer.

Key modules:

- `routes.py`: Trip/Run/Artifact and resumable SSE adapters;
- `postgres_store.py`: tenant-scoped persistence, CAS, leases, and outbox writes;
- `runtime.py`: Product Run coordination and public event projection;
- `worker.py` and `outbox.py`: Redis delivery with database execution fencing;
- `a2a_routes.py`, `rag_routes.py`, `provider_routes.py`: trusted subsystem adapters;
- `share_service.py`: immutable minimized share projections and capability fencing.

Do not add browser authentication logic, provider HTTP calls, schema creation,
or legacy compatibility to this package. See the [API guide](../../../docs/development/api-guide.md),
[platform manual](../../../docs/operations/v1-platform.md), and
[Artifact contract guide](../../../docs/development/artifact-contracts.md).
