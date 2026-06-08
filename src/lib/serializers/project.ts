import type { Project as ProjectEntity } from '@/types/backend';
import type { Project } from '@/types';
import { getTravelCapability } from '@/lib/travel/capabilities';

function readTravelCapabilityId(settings?: string | null) {
  if (!settings) return null;
  try {
    const parsed = JSON.parse(settings) as { travel?: { capabilityId?: string } };
    return getTravelCapability(parsed.travel?.capabilityId).id;
  } catch {
    return null;
  }
}

export function serializeProject(project: ProjectEntity): Project {
  return {
    id: project.id,
    name: project.name,
    description: project.description ?? null,
    status: project.status,
    previewUrl: project.previewUrl ?? null,
    previewPort: project.previewPort ?? null,
    createdAt: project.createdAt.toISOString(),
    updatedAt: project.updatedAt.toISOString(),
    lastActiveAt: project.lastActiveAt ? project.lastActiveAt.toISOString() : null,
    initialPrompt: project.initialPrompt ?? null,
    preferredCli: (project.preferredCli ?? null) as Project['preferredCli'],
    selectedModel: project.selectedModel ?? null,
    fallbackEnabled: project.fallbackEnabled,
    travelCapabilityId: readTravelCapabilityId(project.settings),
  };
}

export function serializeProjects(projects: ProjectEntity[]): Project[] {
  return projects.map((project) => serializeProject(project));
}
