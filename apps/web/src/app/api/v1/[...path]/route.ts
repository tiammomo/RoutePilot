import type { NextRequest } from "next/server";

import { proxyV1Request } from "@/shared/server/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface Context {
  params: Promise<{ path: string[] }>;
}

async function handler(request: NextRequest, context: Context): Promise<Response> {
  const { path } = await context.params;
  return proxyV1Request(request, path);
}

export { handler as DELETE, handler as GET, handler as PATCH, handler as POST, handler as PUT };
