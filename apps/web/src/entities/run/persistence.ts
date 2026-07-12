import type { RunUiState } from "./reducer";

const PREFIX = "routepilot.active-run.v1.";

export interface PersistedRunCursor {
  runId: string;
  tripId: string;
  lastSeq: number;
  savedAt: string;
}

function storage(): Storage | undefined {
  return typeof window === "undefined" ? undefined : window.localStorage;
}

export function saveRunCursor(state: RunUiState): void {
  if (!state.runId || !state.tripId) return;
  const value: PersistedRunCursor = {
    runId: state.runId,
    tripId: state.tripId,
    lastSeq: state.lastSeq,
    savedAt: new Date().toISOString(),
  };
  storage()?.setItem(`${PREFIX}${state.tripId}`, JSON.stringify(value));
}

export function loadRunCursor(tripId: string): PersistedRunCursor | null {
  const raw = storage()?.getItem(`${PREFIX}${tripId}`);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PersistedRunCursor>;
    return value.tripId === tripId &&
      typeof value.runId === "string" &&
      Number.isInteger(value.lastSeq) &&
      typeof value.savedAt === "string"
      ? (value as PersistedRunCursor)
      : null;
  } catch {
    return null;
  }
}
