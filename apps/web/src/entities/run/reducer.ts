import type { PublicRunEvent } from "@/shared/api/public-event";
import type { RunLifecycle, RunPendingInput, RunView } from "@/shared/api/types";

export type StreamConnection =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "offline"
  | "closed"
  | "error";

export interface ArtifactPointer {
  artifactId: string;
  version: number;
  artifactType?: string;
  status: "candidate" | "published";
}

export interface ActivityItem {
  id: string;
  label: string;
  status: string;
  at: string;
}

export interface RunUiState {
  runId: string | null;
  tripId: string | null;
  lifecycle: RunLifecycle | "idle";
  phase: string;
  phaseLabel: string;
  progress: number;
  controlVersion: number;
  lastSeq: number;
  connection: StreamConnection;
  candidate: ArtifactPointer | null;
  published: ArtifactPointer | null;
  activities: ActivityItem[];
  risks: Array<{ id: string; severity: string; message: string }>;
  needsInput: boolean;
  pendingInput: RunPendingInput | null;
  needsApproval: boolean;
  publicError: { code: string; message: string; retryable: boolean } | null;
}

export const emptyRunState: RunUiState = {
  runId: null,
  tripId: null,
  lifecycle: "idle",
  phase: "",
  phaseLabel: "",
  progress: 0,
  controlVersion: 0,
  lastSeq: 0,
  connection: "idle",
  candidate: null,
  published: null,
  activities: [],
  risks: [],
  needsInput: false,
  pendingInput: null,
  needsApproval: false,
  publicError: null,
};

export type RunAction =
  | { type: "snapshot"; run: RunView; lastSeq?: number }
  | { type: "event"; event: PublicRunEvent }
  | { type: "connection"; connection: StreamConnection }
  | { type: "reset" };

function number(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function string(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function lifecycle(value: unknown, fallback: RunUiState["lifecycle"]): RunUiState["lifecycle"] {
  return new Set([
    "queued",
    "running",
    "waiting_input",
    "waiting_approval",
    "cancel_requested",
    "completed",
    "failed",
    "canceled",
  ]).has(String(value))
    ? (value as RunLifecycle)
    : fallback;
}

function pointer(data: Record<string, unknown>, status: "candidate" | "published"): ArtifactPointer | null {
  const ref = data.artifact_ref;
  const contractRef = ref && typeof ref === "object" ? (ref as Record<string, unknown>) : undefined;
  const artifactId = string(contractRef?.artifact_id ?? data.artifact_id);
  const version = number(contractRef?.version ?? data.artifact_version, 0);
  if (!artifactId || version < 1) return null;
  return {
    artifactId,
    version,
    artifactType: string(contractRef?.artifact_type ?? data.artifact_type) || undefined,
    status,
  };
}

function pendingInput(data: Record<string, unknown>): RunPendingInput | null {
  const requestId = string(data.request_id);
  const prompt = string(data.prompt);
  const expiresAt = string(data.expires_at);
  if (!requestId || !prompt || !expiresAt || !Array.isArray(data.fields)) return null;
  const fields = data.fields.flatMap((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const field = value as Record<string, unknown>;
    const fieldId = string(field.field_id);
    const label = string(field.label);
    const inputType = string(field.input_type);
    if (!fieldId || !label || !new Set([
      "text", "date", "number", "single_select", "multi_select", "confirmation",
    ]).has(inputType)) return [];
    return [{
      field_id: fieldId,
      label,
      input_type: inputType as RunPendingInput["fields"][number]["input_type"],
      required: field.required !== false,
      options: Array.isArray(field.options)
        ? field.options.filter((option): option is string => typeof option === "string")
        : [],
    }];
  });
  return fields.length ? { request_id: requestId, prompt, expires_at: expiresAt, fields } : null;
}

function applyEvent(state: RunUiState, event: PublicRunEvent): RunUiState {
  if (state.runId && event.run_id !== state.runId) return state;
  if (event.seq <= state.lastSeq) return state;
  const data = event.data;
  let next: RunUiState = { ...state, runId: event.run_id, tripId: event.trip_id, lastSeq: event.seq };
  const eventControlVersion = number(data.control_version, next.controlVersion);
  next.controlVersion = Math.max(next.controlVersion, eventControlVersion);

  switch (event.type) {
    case "run.accepted":
      return {
        ...next,
        lifecycle: "queued",
        phase: string(data.phase, "accepted"),
        phaseLabel: "请求已进入处理队列",
      };
    case "run.lifecycle_changed":
      return { ...next, lifecycle: lifecycle(data.lifecycle_state, next.lifecycle) };
    case "run.phase_changed": {
      const progress = number(data.progress_percent ?? data.progress, next.progress);
      return {
        ...next,
        phase: string(data.phase, next.phase),
        phaseLabel: string(data.label, next.phaseLabel),
        progress: Math.max(0, Math.min(100, progress)),
      };
    }
    case "agent.activity": {
      const activity = string(data.activity, "专业 Agent 正在处理");
      return {
        ...next,
        activities: [
          ...next.activities,
          {
            id: event.event_id,
            label: activity,
            status: string(data.status, "progress"),
            at: event.occurred_at,
          },
        ].slice(-12),
      };
    }
    case "artifact.candidate_updated":
      return { ...next, candidate: pointer(data, "candidate") ?? next.candidate };
    case "artifact.published":
      return {
        ...next,
        published: pointer(data, "published") ?? next.published,
        progress: Math.max(95, next.progress),
      };
    case "risk.detected":
      return {
        ...next,
        risks: [
          ...next.risks,
          {
            id: string(data.risk_id, event.event_id),
            severity: string(data.severity, "medium"),
            message: string(data.message, "发现一项需要确认的风险"),
          },
        ].slice(-20),
      };
    case "input.required":
      return {
        ...next,
        lifecycle: "waiting_input",
        needsInput: true,
        pendingInput: pendingInput(data) ?? next.pendingInput,
      };
    case "approval.required":
      return { ...next, lifecycle: "waiting_approval", needsApproval: true };
    case "run.completed":
      return { ...next, lifecycle: "completed", phase: "finished", progress: 100, connection: "closed", needsInput: false, pendingInput: null };
    case "run.failed": {
      const publicError = data.error && typeof data.error === "object"
        ? (data.error as Record<string, unknown>)
        : {};
      return {
        ...next,
        lifecycle: "failed",
        connection: "closed",
        publicError: {
          code: string(publicError.code ?? data.error_code, "RUN_FAILED"),
          message: string(publicError.message, "本次处理未能完成，请稍后重试"),
          retryable: publicError.retryable === true,
        },
      };
    }
    case "run.canceled":
      return { ...next, lifecycle: "canceled", connection: "closed" };
    case "citation.added":
    case "heartbeat":
      return next;
  }
}

export function runEventReducer(state: RunUiState, action: RunAction): RunUiState {
  switch (action.type) {
    case "reset":
      return emptyRunState;
    case "connection":
      return { ...state, connection: action.connection };
    case "snapshot": {
      const sameRun = state.runId === action.run.run_id;
      return {
        ...emptyRunState,
        runId: action.run.run_id,
        tripId: action.run.trip_id,
        lifecycle: action.run.lifecycle_state,
        phase: action.run.phase,
        phaseLabel: action.run.phase,
        controlVersion: action.run.control_version,
        lastSeq: action.lastSeq ?? 0,
        connection: sameRun ? state.connection : "idle",
        candidate: sameRun ? state.candidate : null,
        activities: sameRun ? state.activities : [],
        risks: sameRun ? state.risks : [],
        progress: action.run.lifecycle_state === "completed" ? 100 : 0,
        published:
          action.run.result_artifact_id && action.run.result_artifact_version
            ? {
                artifactId: action.run.result_artifact_id,
                version: action.run.result_artifact_version,
                status: "published",
              }
            : sameRun ? state.published : null,
        needsInput: action.run.lifecycle_state === "waiting_input",
        pendingInput: action.run.pending_input,
      };
    }
    case "event":
      return applyEvent(state, action.event);
  }
}

export function isRunTerminal(state: RunUiState): boolean {
  return new Set(["completed", "failed", "canceled"]).has(state.lifecycle);
}
