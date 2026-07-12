import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("server-only", () => ({}));

const ORIGINAL_ENV = { ...process.env };

function configureBase(): void {
  process.env.ROUTEPILOT_API_ORIGIN = "http://api.internal:38083";
  process.env.ROUTEPILOT_PUBLIC_ORIGIN = "https://travel.example.com";
  process.env.ROUTEPILOT_ACCESS_TOKEN_COOKIE_NAME = "__Host-routepilot_access_token";
  process.env.ROUTEPILOT_OIDC_ISSUER = "https://identity.example.com/";
  process.env.ROUTEPILOT_OIDC_AUTHORIZATION_URL = "https://identity.example.com/authorize";
  process.env.ROUTEPILOT_OIDC_TOKEN_URL = "https://identity.example.com/token";
  process.env.ROUTEPILOT_OIDC_END_SESSION_URL = "https://identity.example.com/logout";
  process.env.ROUTEPILOT_OIDC_JWKS_URL = "https://identity.example.com/jwks";
  process.env.ROUTEPILOT_OIDC_CLIENT_ID = "routepilot-web";
  process.env.ROUTEPILOT_OIDC_CLIENT_SECRET = "test-client-secret";
  process.env.ROUTEPILOT_OIDC_COOKIE_KEY = Buffer.alloc(32, 7).toString("base64url");
}

function unsignedShapeJwt(expiresInSeconds = 600): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "RS256", typ: "JWT" })}.${encode({ exp: Math.floor(Date.now() / 1_000) + expiresInSeconds })}.c2lnbmF0dXJl`;
}

describe("server-only BFF authentication", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env = { ...ORIGINAL_ENV };
    configureBase();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    process.env = { ...ORIGINAL_ENV };
  });

  it("converts only the trusted HttpOnly access-token cookie to upstream Bearer", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "staging";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "0";
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ items: [] }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const trustedJwt = unsignedShapeJwt();
    const request = new NextRequest("https://travel.example.com/api/v1/trips", {
      headers: {
        Authorization: "Bearer browser-controlled-token",
        Cookie: `__Host-routepilot_access_token=${trustedJwt}`,
        "X-RoutePilot-Dev-User": "attacker",
      },
    });
    const { proxyV1Request } = await import("@/shared/server/proxy");

    await proxyV1Request(request, ["trips"]);

    const [, init] = upstreamFetch.mock.calls[0] as [URL, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe(`Bearer ${trustedJwt}`);
    expect(headers.has("Cookie")).toBe(false);
    expect(headers.has("X-RoutePilot-Dev-User")).toBe(false);
  });

  it("does not forward malformed cookie or client Authorization", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "staging";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "0";
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ items: [] }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new NextRequest("https://travel.example.com/api/v1/trips", {
      headers: {
        Authorization: "Bearer browser-controlled-token",
        Cookie: "__Host-routepilot_access_token=not-a-jwt",
      },
    });
    const { proxyV1Request } = await import("@/shared/server/proxy");

    await proxyV1Request(request, ["trips"]);

    const [, init] = upstreamFetch.mock.calls[0] as [URL, RequestInit];
    expect(new Headers(init.headers).has("Authorization")).toBe(false);
  });

  it("sends the shared dev proxy secret only in an explicit local deployment", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "local";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "1";
    process.env.ROUTEPILOT_BFF_DEV_TENANT = "local-tenant";
    process.env.ROUTEPILOT_BFF_DEV_USER = "local-user";
    process.env.ROUTEPILOT_BFF_DEV_ROLES = "owner";
    process.env.ROUTEPILOT_V1_DEV_BFF_SECRET = "a".repeat(32);
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ items: [] }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new NextRequest("http://127.0.0.1:33003/api/v1/trips");
    const { proxyV1Request } = await import("@/shared/server/proxy");

    await proxyV1Request(request, ["trips"]);

    const [, init] = upstreamFetch.mock.calls[0] as [URL, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("X-RoutePilot-Dev-User")).toBe("local-user");
    expect(headers.get("X-RoutePilot-Dev-BFF-Secret")).toBe("a".repeat(32));
    expect(headers.has("Authorization")).toBe(false);
  });

  it("allowlists read-only Provider metadata without forwarding a Provider key", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "local";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "1";
    process.env.ROUTEPILOT_BFF_DEV_TENANT = "local-tenant";
    process.env.ROUTEPILOT_BFF_DEV_USER = "local-user";
    process.env.ROUTEPILOT_BFF_DEV_ROLES = "owner";
    process.env.ROUTEPILOT_V1_DEV_BFF_SECRET = "a".repeat(32);
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ items: [{ provider_id: "amap", configured: false }] }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const { proxyV1Request } = await import("@/shared/server/proxy");

    const response = await proxyV1Request(
      new NextRequest("http://127.0.0.1:33003/api/v1/providers/capabilities"),
      ["providers", "capabilities"],
    );

    expect(response.status).toBe(200);
    expect(String(upstreamFetch.mock.calls[0]?.[0])).toBe(
      "http://api.internal:38083/api/v1/providers/capabilities",
    );
    const headers = new Headers(upstreamFetch.mock.calls[0]?.[1]?.headers);
    expect(headers.get("X-RoutePilot-Dev-BFF-Secret")).toBe("a".repeat(32));
    expect(headers.has("ROUTEPILOT_AMAP_WEB_KEY")).toBe(false);
  });

  it("allowlists versioned Artifact reads, edits, and idempotent commands", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "staging";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "0";
    const upstreamFetch = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json({ artifact_id: "artifact-1", version: 3 }),
    );
    vi.stubGlobal("fetch", upstreamFetch);
    const { proxyV1Request } = await import("@/shared/server/proxy");

    const readResponse = await proxyV1Request(
      new NextRequest("https://travel.example.com/api/v1/artifacts/artifact-1?version=3"),
      ["artifacts", "artifact-1"],
    );
    expect(readResponse.status).toBe(200);

    const mutationHeaders = {
      "Content-Type": "application/json",
      Origin: "https://travel.example.com",
      "Sec-Fetch-Site": "same-origin",
      "X-CSRF-Token": "csrf-test-token",
      Cookie: "__Host-routepilot_csrf=csrf-test-token",
    };
    const patchResponse = await proxyV1Request(
      new NextRequest("https://travel.example.com/api/v1/artifacts/artifact-1", {
        method: "PATCH",
        headers: mutationHeaders,
        body: JSON.stringify({ base_version: 3, content: {} }),
      }),
      ["artifacts", "artifact-1"],
    );
    expect(patchResponse.status).toBe(200);

    const commandResponse = await proxyV1Request(
      new NextRequest("https://travel.example.com/api/v1/artifacts/artifact-1/commands", {
        method: "POST",
        headers: { ...mutationHeaders, "Idempotency-Key": "artifact-command-1" },
        body: JSON.stringify({ command: "publish", expected_version: 3 }),
      }),
      ["artifacts", "artifact-1", "commands"],
    );
    expect(commandResponse.status).toBe(200);
    expect(upstreamFetch).toHaveBeenCalledTimes(3);
    expect(String(upstreamFetch.mock.calls[0]?.[0])).toBe(
      "http://api.internal:38083/api/v1/artifacts/artifact-1?version=3",
    );
    expect(new Headers(upstreamFetch.mock.calls[2]?.[1]?.headers).get("Idempotency-Key"))
      .toBe("artifact-command-1");
  });

  it("requires an Idempotency-Key before forwarding Artifact commands", async () => {
    process.env.ROUTEPILOT_DEPLOYMENT_ENV = "staging";
    process.env.ROUTEPILOT_BFF_DEV_AUTH = "0";
    const upstreamFetch = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", upstreamFetch);
    const request = new NextRequest(
      "https://travel.example.com/api/v1/artifacts/artifact-1/commands",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Origin: "https://travel.example.com",
          "Sec-Fetch-Site": "same-origin",
          "X-CSRF-Token": "csrf-test-token",
          Cookie: "__Host-routepilot_csrf=csrf-test-token",
        },
        body: JSON.stringify({ command: "publish", expected_version: 3 }),
      },
    );
    const { proxyV1Request } = await import("@/shared/server/proxy");

    const response = await proxyV1Request(request, ["artifacts", "artifact-1", "commands"]);

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toMatchObject({
      detail: { code: "IDEMPOTENCY_KEY_REQUIRED" },
    });
    expect(upstreamFetch).not.toHaveBeenCalled();
  });
});
