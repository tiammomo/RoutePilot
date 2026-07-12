import type {
  ArtifactCommandInput,
  ArtifactListResponse,
  ArtifactRecord,
  RunCreateInput,
  RunResumeInput,
  RunView,
  ShareListResponse,
  ShareMutationResponse,
  TripListResponse,
  TripView,
} from "./types";

const API_PREFIX = "/api/v1/";
let csrfPromise: Promise<string> | undefined;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
    readonly retryable: boolean,
    readonly traceId?: string,
    readonly currentVersion?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function assertSameOriginPath(path: string): void {
  if (!path.startsWith(API_PREFIX) || path.startsWith("//") || path.includes("://")) {
    throw new Error("API client accepts only same-origin /api/v1 paths");
  }
}

async function csrfToken(fetchImpl: typeof fetch): Promise<string> {
  csrfPromise ??= fetchImpl("/api/auth/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
  })
    .then(async (response) => {
      if (!response.ok) throw new Error("Unable to initialize request protection");
      const payload = (await response.json()) as { token?: unknown };
      if (typeof payload.token !== "string" || payload.token.length < 20) {
        throw new Error("Invalid request protection response");
      }
      return payload.token;
    })
    .catch((error) => {
      csrfPromise = undefined;
      throw error;
    });
  return csrfPromise;
}

interface JsonRequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  headers?: Record<string, string>;
  fetchImpl?: typeof fetch;
}

export async function requestJson<T>(path: string, options: JsonRequestOptions = {}): Promise<T> {
  assertSameOriginPath(path);
  const fetchImpl = options.fetchImpl ?? fetch;
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json", ...options.headers });
  if (method !== "GET") {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRF-Token", await csrfToken(fetchImpl));
  }

  let response: Response;
  try {
    response = await fetchImpl(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError("网络连接中断，请恢复网络后重试", "NETWORK_ERROR", 0, true);
  }

  if (!response.ok) {
    let detail: Record<string, unknown> = {};
    try {
      const payload = (await response.json()) as { detail?: unknown };
      detail =
        payload.detail && typeof payload.detail === "object"
          ? (payload.detail as Record<string, unknown>)
          : {};
    } catch {
      // Public errors are intentionally normalized; upstream response text is not displayed.
    }
    throw new ApiError(
      typeof detail.message === "string" ? detail.message : "请求未能完成",
      typeof detail.code === "string" ? detail.code : `HTTP_${response.status}`,
      response.status,
      detail.retryable === true,
      typeof detail.trace_id === "string" ? detail.trace_id : undefined,
      typeof detail.current_version === "number" &&
        Number.isInteger(detail.current_version) &&
        detail.current_version >= 1
        ? detail.current_version
        : undefined,
    );
  }
  return (await response.json()) as T;
}

export const tripApi = {
  list: (fetchImpl?: typeof fetch) =>
    requestJson<TripListResponse>("/api/v1/trips", { fetchImpl }),
  get: (tripId: string, fetchImpl?: typeof fetch) =>
    requestJson<TripView>(`/api/v1/trips/${encodeURIComponent(tripId)}`, { fetchImpl }),
  create: (
    input: { title: string; locale?: string; timezone?: string },
    fetchImpl?: typeof fetch,
  ) => requestJson<TripView>("/api/v1/trips", { method: "POST", body: input, fetchImpl }),
  archive: (tripId: string, fetchImpl?: typeof fetch) =>
    requestJson<TripView>(`/api/v1/trips/${encodeURIComponent(tripId)}/archive`, {
      method: "POST",
      body: {},
      fetchImpl,
    }),
  restore: (tripId: string, fetchImpl?: typeof fetch) =>
    requestJson<TripView>(`/api/v1/trips/${encodeURIComponent(tripId)}/restore`, {
      method: "POST",
      body: {},
      fetchImpl,
    }),
  artifacts: (tripId: string, fetchImpl?: typeof fetch) =>
    requestJson<ArtifactListResponse>(
      `/api/v1/trips/${encodeURIComponent(tripId)}/artifacts`,
      { fetchImpl },
    ),
};

export const runApi = {
  get: (runId: string, fetchImpl?: typeof fetch) =>
    requestJson<RunView>(`/api/v1/runs/${encodeURIComponent(runId)}`, { fetchImpl }),
  create: (
    tripId: string,
    input: RunCreateInput,
    idempotencyKey: string,
    fetchImpl?: typeof fetch,
  ) =>
    requestJson<RunView>(`/api/v1/trips/${encodeURIComponent(tripId)}/runs`, {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
      fetchImpl,
    }),
  cancel: (
    runId: string,
    expectedControlVersion: number,
    idempotencyKey: string,
    fetchImpl?: typeof fetch,
  ) =>
    requestJson<RunView>(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      body: { expected_control_version: expectedControlVersion, input: {} },
      headers: { "Idempotency-Key": idempotencyKey },
      fetchImpl,
    }),
  resume: (
    runId: string,
    input: RunResumeInput,
    idempotencyKey: string,
    fetchImpl?: typeof fetch,
  ) =>
    requestJson<RunView>(`/api/v1/runs/${encodeURIComponent(runId)}/resume`, {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
      fetchImpl,
    }),
};

export const shareApi = {
  list: (tripId: string, fetchImpl?: typeof fetch) =>
    requestJson<ShareListResponse>(`/api/v1/trips/${encodeURIComponent(tripId)}/shares`, {
      fetchImpl,
    }),
  create: (
    tripId: string,
    artifactId: string,
    artifactVersion: number,
    idempotencyKey: string,
    fetchImpl?: typeof fetch,
  ) => requestJson<ShareMutationResponse>(`/api/v1/trips/${encodeURIComponent(tripId)}/shares`, {
    method: "POST",
    body: { artifact_id: artifactId, artifact_version: artifactVersion },
    headers: { "Idempotency-Key": idempotencyKey },
    fetchImpl,
  }),
  rotate: (shareId: string, version: number, idempotencyKey: string, fetchImpl?: typeof fetch) =>
    requestJson<ShareMutationResponse>(`/api/v1/shares/${encodeURIComponent(shareId)}/rotate`, {
      method: "POST",
      body: {},
      headers: { "Idempotency-Key": idempotencyKey, "If-Match": String(version) },
      fetchImpl,
    }),
  revoke: (shareId: string, version: number, idempotencyKey: string, fetchImpl?: typeof fetch) =>
    requestJson<ShareMutationResponse>(`/api/v1/shares/${encodeURIComponent(shareId)}/revoke`, {
      method: "POST",
      body: {},
      headers: { "Idempotency-Key": idempotencyKey, "If-Match": String(version) },
      fetchImpl,
    }),
};

export const artifactApi = {
  command: (
    artifactId: string,
    input: ArtifactCommandInput,
    idempotencyKey: string,
    fetchImpl?: typeof fetch,
  ) =>
    requestJson<ArtifactRecord>(
      `/api/v1/artifacts/${encodeURIComponent(artifactId)}/commands`,
      {
        method: "POST",
        body: input,
        headers: { "Idempotency-Key": idempotencyKey },
        fetchImpl,
      },
    ),
};

export function resetApiClientForTests(): void {
  csrfPromise = undefined;
}
