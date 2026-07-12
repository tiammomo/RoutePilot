import type { Artifact, PlanStatus, ShareSnapshot } from "@routepilot/contracts-generated";

export type TripStatus = "active" | "archived";

export interface TripView {
  trip_id: string;
  tenant_id: string;
  owner_id: string;
  title: string;
  locale: string;
  timezone: string;
  status: TripStatus;
  version: number;
  current_artifact_id: string | null;
  current_artifact_version: number | null;
  created_at: string;
  updated_at: string;
}

export interface TripListResponse {
  items: TripView[];
  next_cursor: string | null;
}

export type RunLifecycle =
  | "queued"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "canceled";

export interface RunCommand {
  type: "trip.plan" | "trip.replan" | "artifact.select" | "artifact.publish" | "artifact.revoke";
  message: string;
  payload?: Record<string, unknown>;
}

/** Explicit workbench constraints consumed by the V2 trip-intake boundary. */
export interface TripRequestInput {
  destination: string;
  start_date: string;
  end_date: string;
  adults: number;
  seniors: number;
  budget_min: string;
  budget_max: string;
  currency: string;
  preferences: string[];
  accessibility_needs: string[];
}

export interface RunCreateInput {
  command: RunCommand;
  base_artifact_id: string | null;
  base_artifact_version: number | null;
}

export interface RunInputField {
  field_id: string;
  label: string;
  input_type: "text" | "date" | "number" | "single_select" | "multi_select" | "confirmation";
  required: boolean;
  options: string[];
}

export interface RunPendingInput {
  request_id: string;
  prompt: string;
  fields: RunInputField[];
  expires_at: string;
}

export interface RunResumeInput {
  expected_control_version: number;
  request_id: string;
  values: Record<string, string | number | boolean | string[]>;
}

export interface RunView {
  run_id: string;
  trip_id: string;
  tenant_id: string;
  actor_id: string;
  trace_id: string;
  lifecycle_state: RunLifecycle;
  phase: string;
  control_version: number;
  command: RunCommand;
  base_artifact_id: string | null;
  base_artifact_version: number | null;
  pending_input: RunPendingInput | null;
  result_artifact_id: string | null;
  result_artifact_version: number | null;
  public_error_code: string | null;
  created_at: string;
  updated_at: string;
}

export type ShareStatus = "active" | "revoked";

export interface ShareView {
  share_id: string;
  public_id: string;
  trip_id: string;
  source_artifact_id: string;
  source_artifact_version: number;
  status: ShareStatus;
  version: number;
  capability_epoch: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
}

export interface ShareMutationResponse {
  share: ShareView;
  capability_secret: string | null;
  replayed: boolean;
}

export interface ShareListResponse {
  items: ShareView[];
}

export interface PublicShareSnapshotResponse {
  public_id: string;
  snapshot: ShareSnapshot;
}

export interface ArtifactRecord {
  artifact_id: string;
  version: number;
  trip_id: string;
  tenant_id: string;
  artifact_type: string;
  schema_version: number;
  status: PlanStatus | "validated" | "published" | "superseded" | "revoked";
  content: Artifact | Record<string, unknown>;
  created_by: string;
  created_at: string;
  parent_version: number | null;
}

export interface ArtifactListResponse {
  items: ArtifactRecord[];
}

export type ArtifactCommandType =
  | "artifact.select"
  | "artifact.publish"
  | "artifact.revoke";

export interface ArtifactCommandInput {
  type: ArtifactCommandType;
  base_version: number;
}

export interface ProblemDetail {
  code: string;
  message: string;
  retryable: boolean;
  trace_id?: string;
  current_version?: number;
}
