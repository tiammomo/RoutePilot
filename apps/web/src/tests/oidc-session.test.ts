import {
  constants,
  createHash,
  generateKeyPairSync,
  sign,
  type KeyObject,
} from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("server-only", () => ({}));

const ORIGINAL_ENV = { ...process.env };
const ISSUER = "https://identity.example.com/";
const PUBLIC_ORIGIN = "https://travel.example.com";
const CLIENT_ID = "routepilot-web";
const CLIENT_SECRET = "oidc-client-secret";
const KID = "routepilot-test-key";
let privateKey: KeyObject;
let publicJwk: Record<string, unknown>;

function configureOidc(): void {
  process.env.ROUTEPILOT_API_ORIGIN = "http://api.internal:38083";
  process.env.ROUTEPILOT_PUBLIC_ORIGIN = PUBLIC_ORIGIN;
  process.env.ROUTEPILOT_DEPLOYMENT_ENV = "staging";
  process.env.ROUTEPILOT_BFF_DEV_AUTH = "0";
  process.env.ROUTEPILOT_ACCESS_TOKEN_COOKIE_NAME = "__Host-routepilot_access_token";
  process.env.ROUTEPILOT_OIDC_ISSUER = ISSUER;
  process.env.ROUTEPILOT_OIDC_AUTHORIZATION_URL = `${ISSUER}authorize`;
  process.env.ROUTEPILOT_OIDC_TOKEN_URL = `${ISSUER}token`;
  process.env.ROUTEPILOT_OIDC_END_SESSION_URL = `${ISSUER}logout`;
  process.env.ROUTEPILOT_OIDC_JWKS_URL = `${ISSUER}jwks`;
  process.env.ROUTEPILOT_OIDC_CLIENT_ID = CLIENT_ID;
  process.env.ROUTEPILOT_OIDC_CLIENT_SECRET = CLIENT_SECRET;
  process.env.ROUTEPILOT_OIDC_COOKIE_KEY = Buffer.alloc(32, 19).toString("base64url");
  process.env.ROUTEPILOT_OIDC_ALGORITHMS = "RS256";
}

function encodeJson(value: object): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function signedJwt(payload: Record<string, unknown>): string {
  const header = encodeJson({ alg: "RS256", typ: "JWT", kid: KID });
  const encodedPayload = encodeJson(payload);
  const signature = sign(
    "RSA-SHA256",
    Buffer.from(`${header}.${encodedPayload}`, "ascii"),
    { key: privateKey, padding: constants.RSA_PKCS1_PADDING },
  ).toString("base64url");
  return `${header}.${encodedPayload}.${signature}`;
}

function accessJwt(subject = "user-1"): string {
  const now = Math.floor(Date.now() / 1_000);
  return signedJwt({ sub: subject, exp: now + 600, iat: now, aud: "routepilot-api", iss: ISSUER });
}

function idJwt(nonce: string, accessToken: string): string {
  const now = Math.floor(Date.now() / 1_000);
  const atHash = createHash("sha256").update(accessToken, "ascii").digest().subarray(0, 16).toString("base64url");
  return signedJwt({
    sub: "user-1",
    exp: now + 600,
    iat: now,
    aud: CLIENT_ID,
    iss: ISSUER,
    nonce,
    at_hash: atHash,
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function beginLogin(): Promise<{
  state: string;
  nonce: string;
  flowCookie: string;
  response: Response;
}> {
  const { GET } = await import("@/app/api/auth/login/route");
  const response = GET(new NextRequest(`${PUBLIC_ORIGIN}/api/auth/login?returnTo=https://evil.example/`));
  const location = new URL(response.headers.get("location") ?? "invalid:");
  const flowCookie = response.cookies.get("__Host-routepilot_oidc_flow")?.value ?? "";
  return {
    state: location.searchParams.get("state") ?? "",
    nonce: location.searchParams.get("nonce") ?? "",
    flowCookie,
    response,
  };
}

beforeEach(async () => {
  vi.resetModules();
  process.env = { ...ORIGINAL_ENV };
  configureOidc();
  const pair = generateKeyPairSync("rsa", { modulusLength: 2048 });
  privateKey = pair.privateKey;
  publicJwk = { ...pair.publicKey.export({ format: "jwk" }), kid: KID, alg: "RS256", use: "sig" };
});

afterEach(() => {
  vi.unstubAllGlobals();
  process.env = { ...ORIGINAL_ENV };
});

describe("built-in OIDC Authorization Code + PKCE session", () => {
  it("creates a fixed PKCE authorization request and hardened transient cookie", async () => {
    const login = await beginLogin();
    const location = new URL(login.response.headers.get("location") ?? "invalid:");

    expect(location.origin + location.pathname).toBe(`${ISSUER.slice(0, -1)}/authorize`);
    expect(location.searchParams.get("client_id")).toBe(CLIENT_ID);
    expect(location.searchParams.get("redirect_uri")).toBe(`${PUBLIC_ORIGIN}/api/auth/callback`);
    expect(location.searchParams.get("response_type")).toBe("code");
    expect(location.searchParams.get("code_challenge_method")).toBe("S256");
    expect(location.searchParams.get("code_challenge")).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(login.state).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(login.nonce).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(location.toString()).not.toContain(CLIENT_SECRET);
    expect(location.toString()).not.toContain("evil.example");
    const cookie = login.response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("__Host-routepilot_oidc_flow=");
    expect(cookie).toMatch(/HttpOnly/i);
    expect(cookie).toMatch(/Secure/i);
    expect(cookie).toMatch(/SameSite=lax/i);
    expect(cookie).toMatch(/Max-Age=300/i);
  });

  it("fails closed when secure OIDC configuration is missing or uses HTTP", async () => {
    delete process.env.ROUTEPILOT_OIDC_TOKEN_URL;
    const { GET } = await import("@/app/api/auth/login/route");
    expect(() => GET(new NextRequest(`${PUBLIC_ORIGIN}/api/auth/login`))).toThrow(
      /ROUTEPILOT_OIDC_TOKEN_URL/,
    );

    vi.resetModules();
    configureOidc();
    process.env.ROUTEPILOT_OIDC_TOKEN_URL = "http://identity.example.com/token";
    const insecure = await import("@/app/api/auth/login/route");
    expect(() => insecure.GET(new NextRequest(`${PUBLIC_ORIGIN}/api/auth/login`))).toThrow(
      /must use https/,
    );
  });

  it("rejects state tampering before token exchange", async () => {
    const login = await beginLogin();
    const tokenFetch = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", tokenFetch);
    const { GET } = await import("@/app/api/auth/callback/route");
    const request = new NextRequest(
      `${PUBLIC_ORIGIN}/api/auth/callback?code=code-1&state=${"x".repeat(43)}`,
      { headers: { Cookie: `__Host-routepilot_oidc_flow=${login.flowCookie}` } },
    );

    const response = await GET(request);

    expect(response.headers.get("location")).toBe(`${PUBLIC_ORIGIN}/auth/error`);
    expect(tokenFetch).not.toHaveBeenCalled();
  });

  it("exchanges once, validates nonce/signature, and rejects replay", async () => {
    const login = await beginLogin();
    const accessToken = accessJwt();
    const tokenFetch = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === `${ISSUER}token`) {
        const headers = new Headers(init?.headers);
        expect(headers.get("Authorization")).toBe(
          `Basic ${Buffer.from(`${CLIENT_ID}:${CLIENT_SECRET}`).toString("base64")}`,
        );
        const body = init?.body as URLSearchParams;
        expect(body.get("grant_type")).toBe("authorization_code");
        expect(body.get("redirect_uri")).toBe(`${PUBLIC_ORIGIN}/api/auth/callback`);
        expect(body.get("code_verifier")).toMatch(/^[A-Za-z0-9_-]{64}$/);
        return jsonResponse({
          token_type: "Bearer",
          access_token: accessToken,
          refresh_token: "initial-refresh-token",
          id_token: idJwt(login.nonce, accessToken),
          expires_in: 600,
        });
      }
      if (url === `${ISSUER}jwks`) return jsonResponse({ keys: [publicJwk] });
      throw new Error("unexpected URL");
    });
    vi.stubGlobal("fetch", tokenFetch);
    const { GET } = await import("@/app/api/auth/callback/route");
    const callbackRequest = () => new NextRequest(
      `${PUBLIC_ORIGIN}/api/auth/callback?code=code-1&state=${login.state}`,
      { headers: { Cookie: `__Host-routepilot_oidc_flow=${login.flowCookie}` } },
    );

    const success = await GET(callbackRequest());
    const replay = await GET(callbackRequest());

    expect(success.headers.get("location")).toBe(`${PUBLIC_ORIGIN}/trips`);
    expect(success.cookies.get("__Host-routepilot_access_token")?.value).toBe(accessToken);
    const encryptedRefresh = success.cookies.get("__Host-routepilot_refresh")?.value ?? "";
    expect(encryptedRefresh).toMatch(/^v1\./);
    expect(encryptedRefresh).not.toContain("initial-refresh-token");
    const allCookies = success.headers.get("set-cookie") ?? "";
    expect(allCookies).toMatch(/HttpOnly/i);
    expect(allCookies).toMatch(/Secure/i);
    expect(allCookies).toMatch(/SameSite=strict/i);
    expect(replay.headers.get("location")).toBe(`${PUBLIC_ORIGIN}/auth/error`);
    expect(tokenFetch).toHaveBeenCalledTimes(2); // token + JWKS; replay performs no fetch.
  });

  it("never forwards return targets and normalizes provider/token errors", async () => {
    const login = await beginLogin();
    const tokenFetch = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(null, { status: 302, headers: { Location: "https://evil.example/token" } }),
    );
    vi.stubGlobal("fetch", tokenFetch);
    const { GET } = await import("@/app/api/auth/callback/route");
    const response = await GET(new NextRequest(
      `${PUBLIC_ORIGIN}/api/auth/callback?code=bad&state=${login.state}&returnTo=${encodeURIComponent("https://evil.example/")}`,
      { headers: { Cookie: `__Host-routepilot_oidc_flow=${login.flowCookie}` } },
    ));

    expect(response.headers.get("location")).toBe(`${PUBLIC_ORIGIN}/auth/error`);
    expect(response.headers.get("location")).not.toContain("evil.example");
    expect(await response.text()).not.toContain("token");
  });

  it("rotates refresh tokens server-side, retries once, and never exposes them", async () => {
    const login = await beginLogin();
    const firstAccess = accessJwt("first");
    const initialFetch = vi.fn<typeof fetch>(async (input) => {
      if (String(input) === `${ISSUER}token`) return jsonResponse({
        token_type: "Bearer",
        access_token: firstAccess,
        refresh_token: "refresh-token-one",
        id_token: idJwt(login.nonce, firstAccess),
        expires_in: 600,
      });
      if (String(input) === `${ISSUER}jwks`) return jsonResponse({ keys: [publicJwk] });
      throw new Error("unexpected URL");
    });
    vi.stubGlobal("fetch", initialFetch);
    const { GET } = await import("@/app/api/auth/callback/route");
    const callback = await GET(new NextRequest(
      `${PUBLIC_ORIGIN}/api/auth/callback?code=code-1&state=${login.state}`,
      { headers: { Cookie: `__Host-routepilot_oidc_flow=${login.flowCookie}` } },
    ));
    const refreshCookie = callback.cookies.get("__Host-routepilot_refresh")?.value ?? "";
    const rotatedAccess = accessJwt("rotated");
    let apiCalls = 0;
    const refreshFetch = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input) === "http://api.internal:38083/api/v1/trips") {
        apiCalls += 1;
        const authorization = new Headers(init?.headers).get("Authorization");
        if (apiCalls === 1) expect(authorization).toBe(`Bearer ${firstAccess}`);
        if (apiCalls === 2) expect(authorization).toBe(`Bearer ${rotatedAccess}`);
        return apiCalls === 1 ? jsonResponse({ detail: {} }, 401) : jsonResponse({ items: [] });
      }
      if (String(input) === `${ISSUER}token`) {
        const body = init?.body as URLSearchParams;
        expect(body.get("grant_type")).toBe("refresh_token");
        expect(body.get("refresh_token")).toBe("refresh-token-one");
        return jsonResponse({
          token_type: "Bearer",
          access_token: rotatedAccess,
          refresh_token: "refresh-token-two",
          expires_in: 600,
        });
      }
      throw new Error(`unexpected URL ${String(input)}`);
    });
    vi.stubGlobal("fetch", refreshFetch);
    const { proxyV1Request } = await import("@/shared/server/proxy");
    const request = new NextRequest(`${PUBLIC_ORIGIN}/api/v1/trips`, {
      headers: {
        Cookie: `__Host-routepilot_access_token=${firstAccess}; __Host-routepilot_refresh=${refreshCookie}`,
      },
    });

    const response = await proxyV1Request(request, ["trips"]);

    expect(response.status).toBe(200);
    expect(apiCalls).toBe(2);
    expect(response.headers.get("set-cookie")).not.toContain("refresh-token-two");
    expect(response.headers.get("set-cookie")).toContain("__Host-routepilot_refresh=v1.");
  });

  it("logs out with CSRF, clears cookies, and ignores an open-redirect input", async () => {
    const { POST } = await import("@/app/api/auth/logout/route");
    const response = POST(new NextRequest(
      `${PUBLIC_ORIGIN}/api/auth/logout?returnTo=${encodeURIComponent("https://evil.example/")}`,
      {
        method: "POST",
        headers: {
          Origin: PUBLIC_ORIGIN,
          "Sec-Fetch-Site": "same-origin",
          "X-CSRF-Token": "csrf-token-with-enough-entropy",
          Cookie: "__Host-routepilot_csrf=csrf-token-with-enough-entropy",
        },
      },
    ));
    const payload = await response.json() as { logout_url: string };
    const logout = new URL(payload.logout_url);

    expect(response.status).toBe(200);
    expect(logout.origin + logout.pathname).toBe(`${ISSUER.slice(0, -1)}/logout`);
    expect(logout.searchParams.get("client_id")).toBe(CLIENT_ID);
    expect(logout.searchParams.get("post_logout_redirect_uri")).toBe(`${PUBLIC_ORIGIN}/`);
    expect(payload.logout_url).not.toContain("evil.example");
    expect(response.headers.get("set-cookie")).toMatch(/Max-Age=0/i);
  });

  it("returns token-free session status with private no-store headers", async () => {
    const token = accessJwt();
    const { GET } = await import("@/app/api/auth/session/route");
    const response = await GET(new NextRequest(`${PUBLIC_ORIGIN}/api/auth/session`, {
      headers: { Cookie: `__Host-routepilot_access_token=${token}` },
    }));
    const payload = await response.json() as Record<string, unknown>;

    expect(payload).toMatchObject({ authenticated: true, mode: "oidc" });
    expect(JSON.stringify(payload)).not.toContain(token);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });
});
