import type {
  EvidenceBundle,
  ItineraryPlan,
  TripBrief,
  TripSnapshot,
  ValidationReport,
} from "@routepilot/contracts-generated";

import type { ArtifactRecord } from "@/shared/api/types";

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function artifactType(value: unknown, expected: string): boolean {
  return record(value) && value.artifact_type === expected && value.schema_version === 1;
}

export interface ArtifactPresentation {
  record: ArtifactRecord | null;
  brief: TripBrief | null;
  itinerary: ItineraryPlan | null;
  evidence: EvidenceBundle | null;
  validation: ValidationReport | null;
}

export function selectPrimaryArtifact(
  artifacts: ArtifactRecord[],
  currentArtifactId: string | null,
  currentVersion: number | null,
): ArtifactRecord | null {
  const official = artifacts.find(
    (item) => item.artifact_id === currentArtifactId && item.version === currentVersion,
  );
  if (official) return official;
  const displayRank = (item: ArtifactRecord) =>
    ({ TripSnapshot: 4, ItineraryPlan: 3, TripBrief: 1 } as Record<string, number>)[item.artifact_type] ?? 0;
  return [...artifacts].sort((a, b) => {
    const publishedDelta = Number(b.status === "published") - Number(a.status === "published");
    return publishedDelta || displayRank(b) - displayRank(a) || b.created_at.localeCompare(a.created_at);
  })[0] ?? null;
}

export function presentArtifact(selected: ArtifactRecord | null, all: ArtifactRecord[]): ArtifactPresentation {
  const result: ArtifactPresentation = {
    record: selected,
    brief: null,
    itinerary: null,
    evidence: null,
    validation: null,
  };

  const inspect = (item: ArtifactRecord) => {
    const content: unknown = item.content;
    if (artifactType(content, "TripSnapshot")) {
      const snapshot = content as unknown as TripSnapshot;
      result.brief = snapshot.brief;
      result.itinerary = snapshot.itinerary;
      result.validation = snapshot.validation;
    } else if (artifactType(content, "TripBrief")) {
      result.brief = content as unknown as TripBrief;
    } else if (artifactType(content, "ItineraryPlan")) {
      result.itinerary = content as unknown as ItineraryPlan;
    } else if (artifactType(content, "EvidenceBundle")) {
      result.evidence = content as unknown as EvidenceBundle;
    } else if (artifactType(content, "ValidationReport")) {
      result.validation = content as unknown as ValidationReport;
    }
  };

  if (selected) inspect(selected);
  for (const item of all) {
    if (item !== selected) inspect(item);
  }
  return result;
}

export function isOfficialArtifact(
  artifact: ArtifactRecord | null,
  currentArtifactId: string | null,
  currentVersion: number | null,
): boolean {
  return !!artifact &&
    artifact.status === "published" &&
    artifact.artifact_id === currentArtifactId &&
    artifact.version === currentVersion;
}
