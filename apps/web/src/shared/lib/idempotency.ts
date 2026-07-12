import type { ArtifactCommandType } from "@/shared/api/types";

const PENDING_PREFIX = "routepilot.pending-run.v1.";
const PENDING_ARTIFACT_PREFIX = "routepilot.pending-artifact-command.v1.";

interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface PendingRunSubmission {
  tripId: string;
  fingerprint: string;
  idempotencyKey: string;
  createdAt: string;
}

export interface PendingArtifactCommand {
  artifactId: string;
  command: ArtifactCommandType;
  baseVersion: number;
  idempotencyKey: string;
  createdAt: string;
}

function storage(override?: KeyValueStorage): KeyValueStorage | undefined {
  if (override) return override;
  try {
    return typeof window === "undefined" ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

function read(storageKey: string, override?: KeyValueStorage): string | null {
  try {
    return storage(override)?.getItem(storageKey) ?? null;
  } catch {
    return null;
  }
}

function write(storageKey: string, value: string, override?: KeyValueStorage): void {
  try {
    storage(override)?.setItem(storageKey, value);
  } catch {
    // Storage can be disabled; the in-memory command still receives a safe key.
  }
}

function remove(storageKey: string, override?: KeyValueStorage): void {
  try {
    storage(override)?.removeItem(storageKey);
  } catch {
    // A completed operation must not fail merely because browser storage is unavailable.
  }
}

export function newIdempotencyKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

export function commandFingerprint(
  message: string,
  baseVersion: number | null,
  payload?: unknown,
): string {
  return JSON.stringify({ message: message.trim(), baseVersion, payload });
}

export function reserveRunSubmission(
  tripId: string,
  fingerprint: string,
  override?: KeyValueStorage,
): PendingRunSubmission {
  const existing = readRunSubmission(tripId, override);
  if (existing?.fingerprint === fingerprint) return existing;
  const pending = {
    tripId,
    fingerprint,
    idempotencyKey: newIdempotencyKey("run"),
    createdAt: new Date().toISOString(),
  };
  write(`${PENDING_PREFIX}${tripId}`, JSON.stringify(pending), override);
  return pending;
}

export function readRunSubmission(
  tripId: string,
  override?: KeyValueStorage,
): PendingRunSubmission | null {
  const raw = read(`${PENDING_PREFIX}${tripId}`, override);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingRunSubmission>;
    return parsed.tripId === tripId &&
      typeof parsed.fingerprint === "string" &&
      typeof parsed.idempotencyKey === "string" &&
      typeof parsed.createdAt === "string"
      ? (parsed as PendingRunSubmission)
      : null;
  } catch {
    return null;
  }
}

export function clearRunSubmission(
  tripId: string,
  key: string,
  override?: KeyValueStorage,
): void {
  const current = readRunSubmission(tripId, override);
  if (current?.idempotencyKey === key) remove(`${PENDING_PREFIX}${tripId}`, override);
}

function artifactStorageKey(artifactId: string): string {
  return `${PENDING_ARTIFACT_PREFIX}${artifactId}`;
}

export function readArtifactCommand(
  artifactId: string,
  override?: KeyValueStorage,
): PendingArtifactCommand | null {
  const raw = read(artifactStorageKey(artifactId), override);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<PendingArtifactCommand>;
    const validCommand = parsed.command === "artifact.select" ||
      parsed.command === "artifact.publish" ||
      parsed.command === "artifact.revoke";
    return parsed.artifactId === artifactId &&
      validCommand &&
      Number.isInteger(parsed.baseVersion) &&
      Number(parsed.baseVersion) >= 1 &&
      typeof parsed.idempotencyKey === "string" &&
      parsed.idempotencyKey.length >= 8 &&
      parsed.idempotencyKey.length <= 200 &&
      typeof parsed.createdAt === "string"
      ? (parsed as PendingArtifactCommand)
      : null;
  } catch {
    return null;
  }
}

export function reserveArtifactCommand(
  artifactId: string,
  command: ArtifactCommandType,
  baseVersion: number,
  override?: KeyValueStorage,
): PendingArtifactCommand {
  const existing = readArtifactCommand(artifactId, override);
  if (existing?.command === command && existing.baseVersion === baseVersion) return existing;
  const pending: PendingArtifactCommand = {
    artifactId,
    command,
    baseVersion,
    idempotencyKey: newIdempotencyKey(command.replace("artifact.", "artifact-")),
    createdAt: new Date().toISOString(),
  };
  write(artifactStorageKey(artifactId), JSON.stringify(pending), override);
  return pending;
}

export function clearArtifactCommand(
  artifactId: string,
  key: string,
  override?: KeyValueStorage,
): void {
  const current = readArtifactCommand(artifactId, override);
  if (current?.idempotencyKey === key) remove(artifactStorageKey(artifactId), override);
}
