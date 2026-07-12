import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { clearSessionCookies, sessionStatus, setSessionCookies } from "@/shared/server/oidc";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const result = await sessionStatus(request);
  const response = NextResponse.json(result.session);
  response.headers.set("Cache-Control", "no-store, private");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("X-Content-Type-Options", "nosniff");
  if (result.rotated) setSessionCookies(response, result.rotated);
  if (result.clear) clearSessionCookies(response);
  return response;
}
