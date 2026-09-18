# RoutePilot Web

[Project overview](../../README.en.md) · [中文首页](../../README.md) · [Documentation](../../docs/README.md)

The Next.js 16 / React 19 travel workspace: ask a question, turn the answer into a plan, inspect evidence, revise a published itinerary and share it. This package also owns the same-origin `/api/v1` BFF and browser authentication.

## Start the complete product

Use the root [quick start](../../README.en.md#quick-start) to launch PostgreSQL, Redis, migrations, API, workers and Web together. The default workspace is <http://127.0.0.1:33003>.

Starting this package alone does not start the API or execution workers. New databases also require explicit [knowledge publication](../../docs/operations/knowledge-base-maintenance.md) for the included corpus to be searchable.

## Develop the Web app locally

Use Node.js 24 and npm. All commands below run from the **repository root**. Keep the API and worker services running using the root Compose setup.

```bash
npm ci --prefix apps/web --ignore-scripts
cp apps/web/.env.example apps/web/.env.local
```

Edit the ignored `apps/web/.env.local` file:

| Server-only setting | Local development value |
| --- | --- |
| `ROUTEPILOT_API_ORIGIN` | `http://127.0.0.1:38083` with the default Compose API port |
| `ROUTEPILOT_DEPLOYMENT_ENV` | `local` |
| `ROUTEPILOT_BFF_DEV_AUTH` | `1` to opt into local development identity |
| `ROUTEPILOT_BFF_DEV_TENANT` | Match `ROUTEPILOT_DEV_TENANT` in the Compose env |
| `ROUTEPILOT_BFF_DEV_USER` | Match `ROUTEPILOT_DEV_USER` in the Compose env |
| `ROUTEPILOT_BFF_DEV_ROLES` | Keep the example's local `owner` role |
| `ROUTEPILOT_V1_DEV_BFF_SECRET` | Copy the same locally generated value used by the Compose API |

The example disables development authentication by default. The API must also enable `ROUTEPILOT_V1_DEV_AUTH`; local Compose already does so. OIDC is an alternative to development identity, not a requirement for this local flow.

Both Compose Web and the development server use port 33003. Stop only the Compose Web service before starting Next.js:

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml stop web
npm --prefix apps/web run dev
```

This leaves the API, workers and state services running. When finished, stop the development server and restore Compose Web:

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml up --detach web
```

## Verify changes

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run build
```

Run the repository-wide gate for changes that cross contracts or backend boundaries; see the [development guide](../../docs/development/local-development.md).

## Runtime and authentication boundaries

Browser code talks only to the same-origin BFF. The upstream API origin, provider keys and identity configuration are read by server modules. Never put them in `NEXT_PUBLIC_*` variables.

Staging and production use OIDC Authorization Code with PKCE, state and nonce. The BFF verifies ID-token signatures using an explicitly configured JWKS URL, keeps the access JWT in a short-lived HttpOnly cookie, and AES-GCM encrypts rotating refresh tokens in a separate HttpOnly cookie. The API independently validates access JWTs.

Authorization, token, JWKS and end-session endpoints are explicit server settings. The BFF does not perform discovery or accept browser-provided return URLs. Development identity is rejected in production. See the [platform manual](../../docs/operations/v1-platform.md) for the production configuration.

## Product and contract boundaries

Direct questions do not require a full planning form. A planning command uses an explicitly confirmed `trip_request` with destination, dates, travelers, budget, preferences and accessibility needs. Draft constraints are serialized using an allowlist into per-Trip browser `localStorage`; credentials and server configuration are excluded.

The workspace consumes versioned Artifacts and public event projections. Keep Python, JSON Schema and generated TypeScript contracts aligned when those boundaries change.

- [User guide](../../docs/product/user-guide.md): answering, planning, revision, sharing and archives.
- [API and events](../../docs/development/api-guide.md): mutations, CSRF, idempotency and SSE recovery.
- [Contract extension guide](../../docs/development/artifact-contracts.md): coordinated contract changes.
