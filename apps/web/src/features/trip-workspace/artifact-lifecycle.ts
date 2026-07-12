import type {
  ArtifactCommandType,
  ArtifactRecord,
  TripStatus,
} from "@/shared/api/types";

export interface ArtifactLifecycleAction {
  type: ArtifactCommandType;
  label: string;
  confirmation?: string;
}

interface ArtifactLifecycleContext {
  tripStatus: TripStatus;
  busy: boolean;
  currentArtifactId: string | null;
  currentArtifactVersion: number | null;
}

function hasMatchingEnvelope(artifact: ArtifactRecord, expectedType: string): boolean {
  const content: unknown = artifact.content;
  return !!content &&
    typeof content === "object" &&
    !Array.isArray(content) &&
    (content as Record<string, unknown>).artifact_type === expectedType &&
    (content as Record<string, unknown>).artifact_id === artifact.artifact_id &&
    (content as Record<string, unknown>).schema_version === artifact.schema_version &&
    (content as Record<string, unknown>).version === artifact.version;
}

export function latestArtifactVersion(
  artifact: ArtifactRecord | null,
  artifacts: readonly ArtifactRecord[],
): number | null {
  if (!artifact) return null;
  const versions = artifacts
    .filter((item) => item.artifact_id === artifact.artifact_id)
    .map((item) => item.version);
  return versions.length ? Math.max(...versions) : artifact.version;
}

/**
 * Keep lifecycle policy next to the UI boundary. In particular, only a complete
 * TripSnapshot can be published; validated supporting artifacts remain read-only.
 */
export function availableArtifactAction(
  artifact: ArtifactRecord | null,
  artifacts: readonly ArtifactRecord[],
  context: ArtifactLifecycleContext,
): ArtifactLifecycleAction | null {
  if (!artifact || context.busy || context.tripStatus !== "active") return null;
  if (artifact.version !== latestArtifactVersion(artifact, artifacts)) return null;

  if (
    artifact.artifact_type === "ItineraryPlan" &&
    artifact.status === "candidate" &&
    hasMatchingEnvelope(artifact, "ItineraryPlan")
  ) {
    return { type: "artifact.select", label: "选择这个候选" };
  }

  if (
    artifact.artifact_type === "TripSnapshot" &&
    artifact.status === "validated" &&
    hasMatchingEnvelope(artifact, "TripSnapshot")
  ) {
    return {
      type: "artifact.publish",
      label: "发布为正式方案",
      confirmation: "确认将这个已验证整案设为当前正式方案？旧正式版本会保留，但状态会变为已替代。",
    };
  }

  const official = artifact.artifact_id === context.currentArtifactId &&
    artifact.version === context.currentArtifactVersion;
  if (
    artifact.artifact_type === "TripSnapshot" &&
    artifact.status === "published" &&
    official &&
    hasMatchingEnvelope(artifact, "TripSnapshot")
  ) {
    return {
      type: "artifact.revoke",
      label: "撤销正式方案",
      confirmation: "确认撤销当前正式方案？历史版本仍会保留。",
    };
  }

  return null;
}
