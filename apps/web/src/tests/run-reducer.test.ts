import { describe, expect, it } from "vitest";

import { emptyRunState, runEventReducer } from "@/entities/run/reducer";
import { parsePublicRunEvent, type PublicRunEventType } from "@/shared/api/public-event";

function event(seq: number, type: PublicRunEventType, data: Record<string, unknown>) {
  const parsed = parsePublicRunEvent({
    event_id: `evt-${seq}`,
    schema_version: 1,
    seq,
    type,
    occurred_at: "2026-07-12T10:00:00Z",
    tenant_id: "must-not-be-rendered",
    trip_id: "trip-1",
    run_id: "run-1",
    trace_id: "trace-1",
    audience: "trip_members",
    data,
  });
  if (!parsed) throw new Error("test event is invalid");
  return parsed;
}

describe("runEventReducer", () => {
  it("rejects events addressed to any audience other than authorized trip members", () => {
    expect(parsePublicRunEvent({
      event_id: "evt-public",
      schema_version: 1,
      seq: 1,
      type: "run.accepted",
      occurred_at: "2026-07-12T10:00:00Z",
      trip_id: "trip-1",
      run_id: "run-1",
      trace_id: "trace-1",
      audience: "public",
      data: { lifecycle_state: "queued", phase: "accepted", control_version: 1 },
    })).toBeNull();
  });

  it("deduplicates replayed and out-of-order sequence numbers", () => {
    const accepted = event(1, "run.accepted", {
      lifecycle_state: "queued",
      phase: "accepted",
      control_version: 1,
    });
    const progress = event(2, "run.phase_changed", {
      phase: "research",
      label: "正在查找可靠信息",
      progress: 36,
      control_version: 2,
    });
    let state = runEventReducer(emptyRunState, { type: "event", event: accepted });
    state = runEventReducer(state, { type: "event", event: progress });
    state = runEventReducer(state, { type: "event", event: accepted });

    expect(state.lastSeq).toBe(2);
    expect(state.phase).toBe("research");
    expect(state.progress).toBe(36);
    expect(state.controlVersion).toBe(2);
  });

  it("keeps candidate and published artifact states distinct", () => {
    let state = runEventReducer(emptyRunState, {
      type: "event",
      event: event(3, "artifact.candidate_updated", {
        artifact_ref: {
          artifact_id: "plan-1",
          artifact_type: "ItineraryPlan",
          schema_version: 1,
          version: 2,
        },
        status: "candidate",
      }),
    });
    state = runEventReducer(state, {
      type: "event",
      event: event(4, "artifact.published", {
        artifact_id: "plan-1",
        artifact_version: 3,
        artifact_type: "ItineraryPlan",
        status: "published",
      }),
    });

    expect(state.candidate).toMatchObject({ artifactId: "plan-1", version: 2, status: "candidate" });
    expect(state.published).toMatchObject({ artifactId: "plan-1", version: 3, status: "published" });
  });

  it("projects out private reasoning and raw tool data before reduction", () => {
    const projected = event(5, "agent.activity", {
      agent: "research",
      activity: "已核对 4 个来源",
      status: "completed",
      sources: [{ kind: "rag", name: "城市知识库", version: "1", api_key: "nested-secret" }],
      reasoning: "private chain of thought",
      tool_result: { api_key: "secret" },
    });

    expect(projected.data).toEqual({
      agent: "research",
      activity: "已核对 4 个来源",
      status: "completed",
      sources: [{ kind: "rag", name: "城市知识库", version: "1" }],
    });
    expect(JSON.stringify(projected)).not.toContain("secret");
    expect(JSON.stringify(projected)).not.toContain("chain of thought");
  });
});
