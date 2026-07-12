import { type NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "@/shared/server/config";
import { beginAuthorization, setFlowCookie } from "@/shared/server/oidc";

export const dynamic = "force-dynamic";

export function GET(request: NextRequest): NextResponse {
  const config = getServerConfig();
  if (config.developmentIdentity) {
    const response = NextResponse.redirect(new URL("/trips", config.publicOrigin ?? request.nextUrl), 303);
    response.headers.set("Cache-Control", "no-store");
    return response;
  }
  const { authorizationUrl, flowCookie } = beginAuthorization();
  const response = NextResponse.redirect(authorizationUrl, 303);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  setFlowCookie(response, flowCookie);
  return response;
}
