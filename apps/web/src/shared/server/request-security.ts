import "server-only";

import { timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";

import { csrfCookieName } from "./config";

function equalSecret(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

export function assertMutationRequest(request: NextRequest): void {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && !new Set(["same-origin", "none"]).has(fetchSite)) {
    throw new Response("Cross-site request rejected", { status: 403 });
  }

  const origin = request.headers.get("origin");
  let originUrl: URL;
  try {
    originUrl = new URL(origin || "invalid:");
  } catch {
    throw new Response("Origin check failed", { status: 403 });
  }
  const configuredOrigin = process.env.ROUTEPILOT_PUBLIC_ORIGIN?.trim();
  let expectedHost: string;
  let expectedProtocol: string | undefined;
  if (configuredOrigin) {
    let configuredUrl: URL;
    try {
      configuredUrl = new URL(configuredOrigin);
    } catch {
      throw new Error("ROUTEPILOT_PUBLIC_ORIGIN is invalid");
    }
    expectedHost = configuredUrl.host;
    expectedProtocol = configuredUrl.protocol;
  } else {
    expectedHost = request.headers.get("host")?.trim().toLowerCase() ?? "";
    const forwardedProtocol = request.headers.get("x-forwarded-proto")?.split(",", 1)[0]?.trim();
    expectedProtocol = forwardedProtocol ? `${forwardedProtocol}:` : undefined;
  }
  if (
    !expectedHost ||
    originUrl.host.toLowerCase() !== expectedHost ||
    (expectedProtocol && originUrl.protocol !== expectedProtocol)
  ) {
    throw new Response("Origin check failed", { status: 403 });
  }

  const cookieToken = request.cookies.get(csrfCookieName())?.value ?? "";
  const headerToken = request.headers.get("x-csrf-token") ?? "";
  if (!cookieToken || !headerToken || !equalSecret(cookieToken, headerToken)) {
    throw new Response("CSRF token required", { status: 403 });
  }
}
