import type { RunEvent } from "@routepilot/contracts-generated";

export type PublicRunEventType = RunEvent["type"];

export interface PublicRunEvent {
  event_id: string;
  schema_version: 1;
  seq: number;
  type: PublicRunEventType;
  occurred_at: string;
  trip_id: string;
  run_id: string;
  trace_id: string;
  audience: "trip_members";
  data: Record<string, unknown>;
}

const DATA_ALLOWLIST: Record<PublicRunEventType, ReadonlySet<string>> = {
  "run.accepted": new Set(["lifecycle_state", "phase", "control_version"]),
  "run.lifecycle_changed": new Set([
    "previous_state",
    "lifecycle_state",
    "control_version",
    "reason_code",
    "reason",
  ]),
  "run.phase_changed": new Set([
    "previous_phase",
    "phase",
    "progress_percent",
    "progress",
    "label",
    "control_version",
  ]),
  "agent.activity": new Set(["agent", "activity", "status", "duration_ms", "sources", "control_version"]),
  "artifact.candidate_updated": new Set([
    "artifact_ref",
    "artifact_id",
    "artifact_version",
    "artifact_type",
    "status",
    "control_version",
  ]),
  "artifact.published": new Set([
    "artifact_ref",
    "artifact_id",
    "artifact_version",
    "artifact_type",
    "status",
    "control_version",
  ]),
  "citation.added": new Set(["citation", "artifact_ref", "control_version"]),
  "risk.detected": new Set(["risk_id", "severity", "message", "artifact_ref", "control_version"]),
  "input.required": new Set(["request_id", "prompt", "kind", "fields", "expires_at", "control_version"]),
  "approval.required": new Set([
    "approval_id",
    "prompt",
    "kind",
    "summary",
    "artifact_ref",
    "expires_at",
    "control_version",
  ]),
  "run.completed": new Set([
    "lifecycle_state",
    "snapshot_ref",
    "artifact_id",
    "artifact_version",
    "duration_ms",
    "control_version",
  ]),
  "run.failed": new Set([
    "lifecycle_state",
    "failed_phase",
    "error",
    "error_code",
    "control_version",
  ]),
  "run.canceled": new Set(["lifecycle_state", "canceled_by", "reason", "control_version"]),
  heartbeat: new Set(["server_time"]),
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function pick(value: unknown, keys: readonly string[]): Record<string, unknown> | undefined {
  if (!isRecord(value)) return undefined;
  return Object.fromEntries(keys.flatMap((key) => key in value ? [[key, value[key]]] : []));
}

function cleanArtifactRef(value: unknown): Record<string, unknown> | undefined {
  return pick(value, ["artifact_type", "artifact_id", "schema_version", "version"]);
}

function cleanSource(value: unknown): Record<string, unknown> | undefined {
  return pick(value, ["source_id", "kind", "name", "version", "uri", "retrieved_at", "publisher", "license"]);
}

function cleanCitation(value: unknown): Record<string, unknown> | undefined {
  const citation = pick(value, ["citation_id", "evidence_id", "title", "locator"]);
  if (!citation || !isRecord(value)) return citation;
  const source = cleanSource(value.source);
  return source ? { ...citation, source } : citation;
}

function cleanData(type: PublicRunEventType, value: unknown): Record<string, unknown> {
  if (!isRecord(value)) return {};
  const allowed = DATA_ALLOWLIST[type];
  const clean = Object.fromEntries(Object.entries(value).filter(([key]) => allowed.has(key)));
  if ("artifact_ref" in clean) clean.artifact_ref = cleanArtifactRef(clean.artifact_ref);
  if ("snapshot_ref" in clean) clean.snapshot_ref = cleanArtifactRef(clean.snapshot_ref);
  if (type === "agent.activity" && Array.isArray(clean.sources)) {
    clean.sources = clean.sources
      .map((source) => pick(source, ["kind", "name", "version"]))
      .filter(Boolean);
  }
  if (type === "citation.added") clean.citation = cleanCitation(clean.citation);
  if (type === "input.required" && Array.isArray(clean.fields)) {
    clean.fields = clean.fields.map((field) => {
      const safe = pick(field, ["field_id", "label", "input_type", "required"]);
      if (!safe || !isRecord(field)) return safe;
      if (Array.isArray(field.options)) {
        safe.options = field.options.filter((option): option is string => typeof option === "string");
      }
      return safe;
    }).filter(Boolean);
  }
  if (type === "run.failed" && "error" in clean) {
    clean.error = pick(clean.error, ["code", "message", "retryable"]);
  }
  return clean;
}

export function isPublicRunEventType(value: unknown): value is PublicRunEventType {
  return typeof value === "string" && value in DATA_ALLOWLIST;
}

/**
 * Browser-side final projection. Unknown envelope fields and unapproved data keys
 * are discarded, so a future backend regression cannot make private reasoning a
 * renderable UI field.
 */
export function parsePublicRunEvent(value: unknown): PublicRunEvent | null {
  if (!isRecord(value) || !isPublicRunEventType(value.type)) return null;
  if (
    value.schema_version !== 1 ||
    !Number.isInteger(value.seq) ||
    Number(value.seq) < 1 ||
    typeof value.event_id !== "string" ||
    typeof value.occurred_at !== "string" ||
    typeof value.trip_id !== "string" ||
    typeof value.run_id !== "string" ||
    typeof value.trace_id !== "string" ||
    value.audience !== "trip_members"
  ) {
    return null;
  }
  return {
    event_id: value.event_id,
    schema_version: 1,
    seq: Number(value.seq),
    type: value.type,
    occurred_at: value.occurred_at,
    trip_id: value.trip_id,
    run_id: value.run_id,
    trace_id: value.trace_id,
    audience: "trip_members",
    data: cleanData(value.type, value.data),
  };
}
