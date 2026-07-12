import { beforeEach, describe, expect, it, vi } from "vitest";

import { artifactApi, requestJson, resetApiClientForTests, runApi, tripApi } from "@/shared/api/client";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("same-origin API client", () => {
  beforeEach(() => resetApiClientForTests());

  it("refuses absolute or non-v1 targets before fetch", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    await expect(requestJson("https://attacker.example/api/v1/trips", { fetchImpl })).rejects.toThrow(
      "same-origin",
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("initializes CSRF and sends a caller-owned Idempotency-Key exactly once", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-token-with-sufficient-length-123" }))
      .mockResolvedValueOnce(jsonResponse({
        run_id: "run-1",
        trip_id: "trip-1",
        tenant_id: "tenant-1",
        actor_id: "user-1",
        trace_id: "trace-1",
        lifecycle_state: "queued",
        phase: "accepted",
        control_version: 1,
        command: { type: "trip.plan", message: "北京两天" },
        base_artifact_version: null,
        result_artifact_id: null,
        result_artifact_version: null,
        public_error_code: null,
        created_at: "2026-07-12T10:00:00Z",
        updated_at: "2026-07-12T10:00:00Z",
      }));

    await runApi.create(
      "trip-1",
      {
        command: { type: "trip.plan", message: "北京两天", payload: {} },
        base_artifact_id: null,
        base_artifact_version: null,
      },
      "run-fixed-idempotency-key",
      fetchImpl,
    );

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    const [path, request] = fetchImpl.mock.calls[1] as [string, RequestInit];
    const headers = new Headers(request.headers);
    expect(path).toBe("/api/v1/trips/trip-1/runs");
    expect(headers.get("Idempotency-Key")).toBe("run-fixed-idempotency-key");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-with-sufficient-length-123");
  });

  it("does not automatically repeat an ambiguous POST", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-token-with-sufficient-length-123" }))
      .mockRejectedValueOnce(new TypeError("network down"));

    await expect(
      runApi.create(
        "trip-1",
        { command: { type: "trip.plan", message: "杭州三天" }, base_artifact_id: null, base_artifact_version: null },
        "run-stable-key",
        fetchImpl,
      ),
    ).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("sends Artifact lifecycle commands through the same-origin CSRF boundary", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-token-with-sufficient-length-123" }))
      .mockResolvedValueOnce(jsonResponse({ artifact_id: "artifact/unsafe", version: 3 }));

    await artifactApi.command(
      "artifact/unsafe",
      { type: "artifact.publish", base_version: 3 },
      "artifact-stable-idempotency-key",
      fetchImpl,
    );

    const [path, request] = fetchImpl.mock.calls[1] as [string, RequestInit];
    const headers = new Headers(request.headers);
    expect(path).toBe("/api/v1/artifacts/artifact%2Funsafe/commands");
    expect(request.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toBe("artifact-stable-idempotency-key");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-with-sufficient-length-123");
    expect(JSON.parse(String(request.body))).toEqual({
      type: "artifact.publish",
      base_version: 3,
    });
  });

  it("renames a Trip with an encoded same-origin PATCH request", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-token-with-sufficient-length-123" }))
      .mockResolvedValueOnce(jsonResponse({ trip_id: "trip/unsafe", title: "京都慢旅行" }));

    await tripApi.update("trip/unsafe", { title: "京都慢旅行" }, fetchImpl);

    const [path, request] = fetchImpl.mock.calls[1] as [string, RequestInit];
    const headers = new Headers(request.headers);
    expect(path).toBe("/api/v1/trips/trip%2Funsafe");
    expect(request.method).toBe("PATCH");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-with-sufficient-length-123");
    expect(JSON.parse(String(request.body))).toEqual({ title: "京都慢旅行" });
  });

  it("preserves the server current version without retrying a conflicting command", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ token: "csrf-token-with-sufficient-length-123" }))
      .mockResolvedValueOnce(jsonResponse({
        detail: {
          code: "VERSION_CONFLICT",
          message: "The resource changed; refresh and retry.",
          retryable: true,
          current_version: 7,
        },
      }, { status: 409 }));

    await expect(artifactApi.command(
      "artifact-1",
      { type: "artifact.publish", base_version: 6 },
      "artifact-stable-conflict-key",
      fetchImpl,
    )).rejects.toMatchObject({
      code: "VERSION_CONFLICT",
      status: 409,
      currentVersion: 7,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});
