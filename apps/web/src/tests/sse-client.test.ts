import { describe, expect, it, vi } from "vitest";

import { streamRunEventsOnce } from "@/shared/api/sse";

describe("resumable SSE client", () => {
  it("uses GET with both cursor forms and parses fragmented events", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode("id: 8\nevent: run.phase_changed\ndata: {\"event_id\":\"evt-8\",\"schema_version\":1,\"seq\":8,"));
        controller.enqueue(encoder.encode("\"type\":\"run.phase_changed\",\"occurred_at\":\"2026-07-12T10:00:00Z\",\"trip_id\":\"trip-1\",\"run_id\":\"run-1\",\"trace_id\":\"trace-1\",\"audience\":\"trip_members\",\"data\":{\"phase\":\"planning\",\"progress\":62}}\n\n"));
        controller.close();
      },
    });
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    const received: number[] = [];

    await streamRunEventsOnce({
      runId: "run-1",
      afterSeq: 7,
      signal: new AbortController().signal,
      onEvent: (event) => received.push(event.seq),
      fetchImpl,
    });

    expect(received).toEqual([8]);
    const [path, request] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/runs/run-1/events?after_seq=7");
    expect(new Headers(request.headers).get("Last-Event-ID")).toBe("7");
    expect(request.method).toBe("GET");
  });

  it("treats transport heartbeats separately from domain events", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: heartbeat\ndata: {\"type\":\"heartbeat\"}\n\n"));
        controller.close();
      },
    });
    const onHeartbeat = vi.fn();
    const onEvent = vi.fn();
    await streamRunEventsOnce({
      runId: "run-1",
      afterSeq: 0,
      signal: new AbortController().signal,
      onEvent,
      onHeartbeat,
      fetchImpl: vi.fn<typeof fetch>().mockResolvedValue(new Response(body, { status: 200 })),
    });
    expect(onHeartbeat).toHaveBeenCalledOnce();
    expect(onEvent).not.toHaveBeenCalled();
  });
});
