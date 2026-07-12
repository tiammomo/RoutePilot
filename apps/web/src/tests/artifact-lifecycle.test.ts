import { describe, expect, it } from "vitest";

import { isOfficialArtifact } from "@/entities/artifact/presentation";
import {
  availableArtifactAction,
  latestArtifactVersion,
} from "@/features/trip-workspace/artifact-lifecycle";
import type { ArtifactRecord } from "@/shared/api/types";
import {
  clearArtifactCommand,
  readArtifactCommand,
  reserveArtifactCommand,
} from "@/shared/lib/idempotency";

class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

function artifact(
  artifactType: string,
  status: ArtifactRecord["status"],
  version = 1,
  artifactId = `artifact-${artifactType}`,
): ArtifactRecord {
  return {
    artifact_id: artifactId,
    version,
    trip_id: "trip-1",
    tenant_id: "tenant-1",
    artifact_type: artifactType,
    schema_version: 1,
    status,
    content: {
      artifact_type: artifactType,
      artifact_id: artifactId,
      schema_version: 1,
      version,
    },
    created_by: "user-1",
    created_at: `2026-07-12T10:00:0${version}Z`,
    parent_version: version > 1 ? version - 1 : null,
  };
}

const activeContext = {
  tripStatus: "active" as const,
  busy: false,
  currentArtifactId: null,
  currentArtifactVersion: null,
};

describe("Artifact lifecycle policy", () => {
  it("never offers publish for validated supporting artifacts", () => {
    for (const artifactType of [
      "TripBrief",
      "EvidenceBundle",
      "CandidateSet",
      "ItineraryPlan",
      "ConstraintReport",
      "SemanticRiskReport",
      "ValidationReport",
    ]) {
      const supporting = artifact(artifactType, "validated");
      expect(availableArtifactAction(supporting, [supporting], activeContext)).toBeNull();
    }

    const snapshot = artifact("TripSnapshot", "validated");
    expect(availableArtifactAction(snapshot, [snapshot], activeContext)).toMatchObject({
      type: "artifact.publish",
      label: "发布为正式方案",
    });
  });

  it("allows only the expected transition on a valid latest envelope", () => {
    const candidate = artifact("ItineraryPlan", "candidate");
    expect(availableArtifactAction(candidate, [candidate], activeContext)?.type)
      .toBe("artifact.select");

    const published = artifact("TripSnapshot", "published");
    expect(availableArtifactAction(published, [published], {
      ...activeContext,
      currentArtifactId: published.artifact_id,
      currentArtifactVersion: published.version,
    })?.type).toBe("artifact.revoke");
    expect(availableArtifactAction(published, [published], activeContext)).toBeNull();

    const malformed = {
      ...artifact("TripSnapshot", "validated"),
      content: { artifact_type: "EvidenceBundle", schema_version: 1 },
    };
    expect(availableArtifactAction(malformed, [malformed], activeContext)).toBeNull();
  });

  it("keeps historical, archived, and in-flight versions read-only", () => {
    const oldVersion = artifact("ItineraryPlan", "candidate", 1, "plan-1");
    const latestVersion = artifact("ItineraryPlan", "candidate", 2, "plan-1");

    expect(latestArtifactVersion(oldVersion, [oldVersion, latestVersion])).toBe(2);
    expect(availableArtifactAction(oldVersion, [oldVersion, latestVersion], activeContext))
      .toBeNull();
    expect(availableArtifactAction(latestVersion, [oldVersion, latestVersion], {
      ...activeContext,
      tripStatus: "archived",
    })).toBeNull();
    expect(availableArtifactAction(latestVersion, [oldVersion, latestVersion], {
      ...activeContext,
      busy: true,
    })).toBeNull();
  });

  it("does not call a revoked pointer official while Trip refresh is pending", () => {
    const revoked = artifact("TripSnapshot", "revoked");
    expect(isOfficialArtifact(revoked, revoked.artifact_id, revoked.version)).toBe(false);
  });
});

describe("Artifact command idempotency reservation", () => {
  it("reuses one key for an ambiguous retry and rotates it when the command changes", () => {
    const storage = new MemoryStorage();
    const first = reserveArtifactCommand("artifact-1", "artifact.publish", 3, storage);
    const retry = reserveArtifactCommand("artifact-1", "artifact.publish", 3, storage);
    const nextVersion = reserveArtifactCommand("artifact-1", "artifact.publish", 4, storage);

    expect(retry.idempotencyKey).toBe(first.idempotencyKey);
    expect(nextVersion.idempotencyKey).not.toBe(first.idempotencyKey);
    expect(readArtifactCommand("artifact-1", storage)).toEqual(nextVersion);

    clearArtifactCommand("artifact-1", first.idempotencyKey, storage);
    expect(readArtifactCommand("artifact-1", storage)).toEqual(nextVersion);
    clearArtifactCommand("artifact-1", nextVersion.idempotencyKey, storage);
    expect(readArtifactCommand("artifact-1", storage)).toBeNull();
  });
});
