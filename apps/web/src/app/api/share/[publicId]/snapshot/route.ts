import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getServerConfig, isSecureDeployment } from "@/shared/server/config";
import { shareSessionCookieName } from "@/shared/server/share-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest, context: { params: Promise<{ publicId: string }> }): Promise<Response> {
  const { publicId } = await context.params;
  if (!/^[A-Za-z0-9_-]{3,128}$/.test(publicId)) return new Response(null, { status: 404 });
  const token = request.cookies.get(shareSessionCookieName())?.value;
  if (!token) return Response.json({ detail: { code: "SHARE_SESSION_REQUIRED", message: "分享访问已过期" } }, { status: 401 });
  try {
    const target = new URL(`/api/v1/public/shares/${encodeURIComponent(publicId)}/snapshot`, getServerConfig().apiOrigin);
    const upstream = await fetch(target, {
      headers: { Accept: "application/json", "X-RoutePilot-Share-Session": token },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(10_000),
    });
    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff" },
    });
    if (!upstream.ok) response.cookies.set(shareSessionCookieName(), "", { httpOnly: true, secure: isSecureDeployment(), sameSite: "strict", path: "/", maxAge: 0 });
    return response;
  } catch {
    return Response.json({ detail: { code: "SHARE_UPSTREAM_UNAVAILABLE", message: "分享服务暂时不可用" } }, { status: 502, headers: { "Cache-Control": "no-store" } });
  }
}
