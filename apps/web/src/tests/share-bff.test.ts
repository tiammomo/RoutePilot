import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("server-only", () => ({}));

const ORIGINAL_ENV = { ...process.env };

function configure(): void {
  process.env.ROUTEPILOT_DEPLOYMENT_ENV = "local";
  process.env.ROUTEPILOT_API_ORIGIN = "http://api.internal:38083";
  process.env.ROUTEPILOT_PUBLIC_ORIGIN = "http://127.0.0.1:33003";
  process.env.ROUTEPILOT_BFF_DEV_AUTH = "1";
  process.env.ROUTEPILOT_BFF_DEV_TENANT = "tenant";
  process.env.ROUTEPILOT_BFF_DEV_USER = "user";
  process.env.ROUTEPILOT_V1_DEV_BFF_SECRET = "d".repeat(32);
}

describe("capability share BFF", () => {
  beforeEach(() => {
    vi.resetModules();
    process.env = { ...ORIGINAL_ENV };
    configure();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    process.env = { ...ORIGINAL_ENV };
  });

  it("exchanges a fragment secret only in a bounded POST and stores an HttpOnly session", async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(Response.json({
      session_token: "s".repeat(43),
      expires_at: "2026-07-12T15:00:00Z",
    }));
    vi.stubGlobal("fetch", upstream);
    const { POST } = await import("@/app/api/share/[publicId]/exchange/route");
    const response = await POST(new NextRequest("http://127.0.0.1:33003/api/share/public_123/exchange", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: "http://127.0.0.1:33003",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": "csrf-share-test-token",
        Cookie: "routepilot_csrf_dev=csrf-share-test-token",
      },
      body: JSON.stringify({ secret: "c".repeat(43) }),
    }), { params: Promise.resolve({ publicId: "public_123" }) });

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(response.headers.get("set-cookie")).toContain("SameSite=strict");
    const [target, init] = upstream.mock.calls[0] as [URL, RequestInit];
    expect(String(target)).toBe("http://api.internal:38083/api/v1/public/shares/public_123/exchange");
    expect(String(target)).not.toContain("c".repeat(43));
    expect(init.body).toBe(JSON.stringify({ secret: "c".repeat(43) }));
  });

  it("uses only the HttpOnly share session to fetch the public projection", async () => {
    const upstream = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ public_id: "public_123", snapshot: {} }));
    vi.stubGlobal("fetch", upstream);
    const { GET } = await import("@/app/api/share/[publicId]/snapshot/route");
    const response = await GET(new NextRequest("http://127.0.0.1:33003/api/share/public_123/snapshot", {
      headers: { Cookie: `routepilot_share_session_dev=${"s".repeat(43)}` },
    }), { params: Promise.resolve({ publicId: "public_123" }) });

    expect(response.status).toBe(200);
    const [, init] = upstream.mock.calls[0] as [URL, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get("X-RoutePilot-Share-Session")).toBe("s".repeat(43));
    expect(headers.has("Cookie")).toBe(false);
  });
});
