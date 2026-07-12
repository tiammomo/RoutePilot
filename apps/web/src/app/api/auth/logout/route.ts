import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { clearSessionCookies, endSessionUrl } from "@/shared/server/oidc";
import { assertMutationRequest } from "@/shared/server/request-security";

export const dynamic = "force-dynamic";

export function POST(request: NextRequest): NextResponse {
  try {
    assertMutationRequest(request);
  } catch (error) {
    if (error instanceof Response) {
      return NextResponse.json(
        { detail: { code: "LOGOUT_REQUEST_REJECTED", retryable: false } },
        { status: error.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    throw error;
  }
  // logout_url is derived only from server configuration. Query parameters and
  // browser-supplied redirect targets are never forwarded.
  const response = NextResponse.json({ logout_url: endSessionUrl() });
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("X-Content-Type-Options", "nosniff");
  clearSessionCookies(response);
  return response;
}
