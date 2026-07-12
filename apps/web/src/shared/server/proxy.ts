import "server-only";

import { type NextRequest, NextResponse } from "next/server";

import { getServerConfig } from "./config";
import {
  accessTokenFromRequest,
  clearSessionCookies,
  hasRefreshCookie,
  refreshSession,
  setSessionCookies,
  type SessionTokens,
} from "./oidc";
import { assertMutationRequest } from "./request-security";

const SAFE_ID = "[A-Za-z0-9_-]+";
const ROUTES: ReadonlyArray<{ method: string; pattern: RegExp }> = [
  { method: "GET", pattern: /^providers\/(?:capabilities|health)$/ },
  { method: "GET", pattern: /^trips$/ },
  { method: "POST", pattern: /^trips$/ },
  { method: "GET", pattern: new RegExp(`^trips/${SAFE_ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^trips/${SAFE_ID}$`) },
  { method: "POST", pattern: new RegExp(`^trips/${SAFE_ID}/(?:archive|restore)$`) },
  { method: "POST", pattern: new RegExp(`^trips/${SAFE_ID}/runs$`) },
  { method: "GET", pattern: new RegExp(`^trips/${SAFE_ID}/shares$`) },
  { method: "POST", pattern: new RegExp(`^trips/${SAFE_ID}/shares$`) },
  { method: "GET", pattern: new RegExp(`^trips/${SAFE_ID}/artifacts$`) },
  { method: "GET", pattern: new RegExp(`^artifacts/${SAFE_ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^artifacts/${SAFE_ID}$`) },
  { method: "POST", pattern: new RegExp(`^artifacts/${SAFE_ID}/commands$`) },
  { method: "GET", pattern: new RegExp(`^runs/${SAFE_ID}$`) },
  { method: "GET", pattern: new RegExp(`^runs/${SAFE_ID}/events$`) },
  { method: "POST", pattern: new RegExp(`^runs/${SAFE_ID}/cancel$`) },
  { method: "POST", pattern: new RegExp(`^runs/${SAFE_ID}/resume$`) },
  { method: "POST", pattern: new RegExp(`^shares/${SAFE_ID}/(?:rotate|revoke)$`) },
];

const MUTATION_METHODS = new Set(["POST", "PATCH", "PUT", "DELETE"]);
const MAX_BODY_BYTES = 64 * 1024;

function routeAllowed(method: string, path: string): boolean {
  return ROUTES.some((route) => route.method === method && route.pattern.test(path));
}

function filteredQuery(request: NextRequest, path: string): string {
  if (path.match(new RegExp(`^runs/${SAFE_ID}/events$`))) {
    const afterSeq = request.nextUrl.searchParams.get("after_seq");
    if (afterSeq === null) return "";
    if (!/^\d+$/.test(afterSeq)) throw new Response("Invalid event cursor", { status: 400 });
    return `?after_seq=${encodeURIComponent(afterSeq)}`;
  }
  if (request.method === "GET" && path.match(new RegExp(`^artifacts/${SAFE_ID}$`))) {
    const version = request.nextUrl.searchParams.get("version");
    if (version === null) return "";
    if (!/^[1-9]\d*$/.test(version)) throw new Response("Invalid artifact version", { status: 400 });
    return `?version=${encodeURIComponent(version)}`;
  }
  return "";
}

function authHeaders(request: NextRequest): HeadersInit {
  const config = getServerConfig();
  if (config.developmentIdentity) {
    return {
      "X-RoutePilot-Dev-Tenant": config.developmentIdentity.tenant,
      "X-RoutePilot-Dev-User": config.developmentIdentity.user,
      "X-RoutePilot-Dev-Roles": config.developmentIdentity.roles,
      "X-RoutePilot-Dev-BFF-Secret": config.developmentIdentity.sharedSecret,
    };
  }

  // The built-in OIDC session stores a bounded short-lived JWT in an HttpOnly
  // cookie. Browser Authorization and development identity headers are ignored.
  const token = accessTokenFromRequest(request);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestBody(request: NextRequest): Promise<ArrayBuffer | undefined> {
  if (!MUTATION_METHODS.has(request.method)) return undefined;
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    throw new Response("Only application/json is accepted", { status: 415 });
  }
  const declaredLength = Number(request.headers.get("content-length") || 0);
  if (declaredLength > MAX_BODY_BYTES) throw new Response("Request body too large", { status: 413 });
  const body = await request.arrayBuffer();
  if (body.byteLength > MAX_BODY_BYTES) throw new Response("Request body too large", { status: 413 });
  return body;
}

function responseHeaders(upstream: Response, isStream: boolean): Headers {
  const headers = new Headers({
    "Cache-Control": "no-store, no-transform",
    "X-Content-Type-Options": "nosniff",
  });
  for (const name of ["content-type", "etag", "retry-after", "x-request-id"]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (isStream) {
    headers.set("Content-Type", "text/event-stream; charset=utf-8");
    headers.set("X-Accel-Buffering", "no");
  }
  return headers;
}

export async function proxyV1Request(request: NextRequest, segments: string[]): Promise<Response> {
  const path = segments.join("/");
  if (!routeAllowed(request.method, path)) {
    return Response.json({ detail: { code: "BFF_ROUTE_DENIED", retryable: false } }, { status: 404 });
  }

  try {
    if (MUTATION_METHODS.has(request.method)) assertMutationRequest(request);
    const isStream = new RegExp(`^runs/${SAFE_ID}/events$`).test(path);
    const config = getServerConfig();
    const target = new URL(`/api/v1/${path}${filteredQuery(request, path)}`, config.apiOrigin);
    const headers = new Headers({
      Accept: isStream ? "text/event-stream" : "application/json",
      ...authHeaders(request),
    });
    const contentType = request.headers.get("content-type");
    if (contentType && MUTATION_METHODS.has(request.method)) headers.set("Content-Type", "application/json");
    for (const name of ["idempotency-key", "last-event-id", "if-match"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    if (
      (path.endsWith("/runs") || path.endsWith("/cancel") || path.endsWith("/resume") ||
        path.endsWith("/commands") || path.endsWith("/shares") || path.endsWith("/rotate") ||
        path.endsWith("/revoke")) &&
      !headers.has("idempotency-key")
    ) {
      return Response.json(
        { detail: { code: "IDEMPOTENCY_KEY_REQUIRED", retryable: false } },
        { status: 400 },
      );
    }

    const body = await requestBody(request);
    const upstreamSignal = isStream
      ? request.signal
      : AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]);
    const forward = () => fetch(target, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "manual",
        signal: upstreamSignal,
      });
    let upstream = await forward();
    let rotated: SessionTokens | undefined;
    let clearInvalidSession = false;
    if (
      upstream.status === 401 &&
      !config.developmentIdentity &&
      config.oidc &&
      hasRefreshCookie(request)
    ) {
      try {
        rotated = await refreshSession(request);
        await upstream.body?.cancel();
        headers.set("Authorization", `Bearer ${rotated.accessToken}`);
        upstream = await forward();
        if (upstream.status === 401) {
          rotated = undefined;
          clearInvalidSession = true;
        }
      } catch {
        clearInvalidSession = true;
      }
    }
    const response = new NextResponse(upstream.body, {
      status: upstream.status,
      headers: responseHeaders(upstream, isStream),
    });
    if (rotated) setSessionCookies(response, rotated);
    if (clearInvalidSession) clearSessionCookies(response);
    return response;
  } catch (error) {
    if (error instanceof Response) return error;
    return Response.json(
      { detail: { code: "UPSTREAM_UNAVAILABLE", message: "旅行服务暂时不可用", retryable: true } },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
