# RoutePilot Web V1

The single, artifact-first RoutePilot product UI. It talks only to its same-origin
`/api/v1` BFF; the FastAPI origin and development identity are read exclusively by
server modules.

```bash
cp .env.example .env.local
npm ci --ignore-scripts
npm run dev
```

Local identity forwarding is opt-in and refuses to run in production. Do not add an
API origin, access token, map key, or development identity under a `NEXT_PUBLIC_`
environment variable.

Staging and production use the OIDC Authorization Code flow implemented inside this
`apps/web` BFF. It uses PKCE, state and nonce, verifies ID-token signatures against
an explicitly configured JWKS URL, keeps the access JWT in a short-lived HttpOnly
cookie, and AES-GCM encrypts rotating refresh tokens in a separate HttpOnly cookie.
Authorization, token, JWKS and end-session endpoints are explicit server settings;
the BFF neither performs discovery nor accepts browser-provided return URLs. See
`../../docs/operations/v1-platform.md` for the complete pre-production variables.

The workspace submits every planning command with an explicitly confirmed
`trip_request` (destination, dates, travelers, budget, preferences, and
accessibility needs). Draft constraints are allowlist-serialized per Trip in browser
`localStorage`; credentials and server configuration are never part of that record.

The end-user flow is documented in the [RoutePilot user guide](../../docs/product/user-guide.md).
API mutation, CSRF, idempotency, and SSE rules are documented in the
[API guide](../../docs/development/api-guide.md).
