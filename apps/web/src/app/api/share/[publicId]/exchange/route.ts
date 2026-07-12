import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getServerConfig, isSecureDeployment } from "@/shared/server/config";
import { assertMutationRequest } from "@/shared/server/request-security";
import { SHARE_SESSION_MAX_AGE_SECONDS, shareSessionCookieName } from "@/shared/server/share-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: NextRequest, context: { params: Promise<{ publicId: string }> }): Promise<Response> {
  try {
    assertMutationRequest(request);
    const { publicId } = await context.params;
    if (!/^[A-Za-z0-9_-]{3,128}$/.test(publicId)) return new Response(null, { status: 404 });
    const body = await request.json() as { secret?: unknown };
    if (typeof body.secret !== "string" || !/^[A-Za-z0-9_-]{32,128}$/.test(body.secret)) {
      return Response.json({ detail: { code: "SHARE_ACCESS_INVALID", message: "分享访问无效或已过期" } }, { status: 401 });
    }
    const target = new URL(`/api/v1/public/shares/${encodeURIComponent(publicId)}/exchange`, getServerConfig().apiOrigin);
    const upstream = await fetch(target, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ secret: body.secret }),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(10_000),
    });
    if (!upstream.ok) {
      return Response.json(
        { detail: { code: upstream.status === 429 ? "SHARE_EXCHANGE_RATE_LIMITED" : "SHARE_ACCESS_INVALID", message: upstream.status === 429 ? "访问尝试过多，请稍后重试" : "分享访问无效或已过期" } },
        { status: upstream.status === 429 ? 429 : 401, headers: { "Cache-Control": "no-store" } },
      );
    }
    const result = await upstream.json() as { session_token?: unknown };
    if (typeof result.session_token !== "string") throw new Error("invalid share exchange response");
    const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
    response.cookies.set(shareSessionCookieName(), result.session_token, {
      httpOnly: true,
      secure: isSecureDeployment(),
      sameSite: "strict",
      path: "/",
      maxAge: SHARE_SESSION_MAX_AGE_SECONDS,
    });
    return response;
  } catch (error) {
    if (error instanceof Response) return error;
    return Response.json({ detail: { code: "SHARE_UPSTREAM_UNAVAILABLE", message: "分享服务暂时不可用" } }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}
