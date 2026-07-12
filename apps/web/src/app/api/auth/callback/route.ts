import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getServerConfig } from "@/shared/server/config";
import {
  clearFlowCookie,
  consumeAuthorizationFlow,
  exchangeAuthorizationCode,
  setSessionCookies,
} from "@/shared/server/oidc";

export const dynamic = "force-dynamic";

function fixedRedirect(path: "/trips" | "/auth/error"): URL {
  const origin = getServerConfig().publicOrigin;
  if (!origin) throw new Error("ROUTEPILOT_PUBLIC_ORIGIN is required for the OIDC callback");
  return new URL(path, origin);
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const codes = request.nextUrl.searchParams.getAll("code");
  const states = request.nextUrl.searchParams.getAll("state");
  const code = codes.length === 1 ? codes[0] : "";
  const state = states.length === 1 ? states[0] : "";
  const providerError = request.nextUrl.searchParams.has("error");
  try {
    const flow = consumeAuthorizationFlow(request, state);
    if (providerError || codes.length !== 1 || states.length !== 1) {
      throw new Error("OIDC provider rejected authorization");
    }
    const responseIssuer = request.nextUrl.searchParams.get("iss");
    if (responseIssuer !== null && responseIssuer !== getServerConfig().oidc?.issuer) {
      throw new Error("OIDC authorization issuer mismatch");
    }
    const tokens = await exchangeAuthorizationCode(code, flow);
    const response = NextResponse.redirect(fixedRedirect("/trips"), 303);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    clearFlowCookie(response);
    setSessionCookies(response, tokens);
    return response;
  } catch {
    // Provider errors and token response details are deliberately not reflected.
    const response = NextResponse.redirect(fixedRedirect("/auth/error"), 303);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Referrer-Policy", "no-referrer");
    clearFlowCookie(response);
    return response;
  }
}
