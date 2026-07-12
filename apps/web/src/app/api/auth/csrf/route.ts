import { randomBytes } from "node:crypto";
import { NextResponse } from "next/server";

import { csrfCookieName, isSecureDeployment } from "@/shared/server/config";

export const dynamic = "force-dynamic";

export function GET(): NextResponse {
  const token = randomBytes(32).toString("base64url");
  const response = NextResponse.json({ token });
  response.headers.set("Cache-Control", "no-store");
  response.cookies.set(csrfCookieName(), token, {
    httpOnly: true,
    secure: isSecureDeployment(),
    sameSite: "strict",
    path: "/",
  });
  return response;
}
