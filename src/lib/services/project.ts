/**
 * Project Service - Project management logic
 */

import { prisma } from '@/lib/db/client';
import type { Project, CreateProjectInput, UpdateProjectInput } from '@/types/backend';
import fs from 'fs/promises';
import path from 'path';
import { normalizeModelId, getDefaultModelForCli } from '@/lib/constants/cliModels';
import { ensureClaudeSkillsForProject } from '@/lib/services/claude-skills';
import { buildTravelProjectSettings, getTravelCapability } from '@/lib/travel/capabilities';
import { serializeTravelVisualizationTemplate } from '@/lib/travel/visualization-templates';

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(/*turbopackIgnore: true*/ process.cwd(), PROJECTS_DIR);

function mergeProjectSettings(existing: string | null | undefined, travelCapabilityId?: string | null): string {
  let parsed: Record<string, unknown> = {};

  if (existing) {
    try {
      const value = JSON.parse(existing);
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        parsed = value as Record<string, unknown>;
      }
    } catch {
      parsed = {};
    }
  }

  return JSON.stringify({
    ...parsed,
    travel: buildTravelProjectSettings(travelCapabilityId),
  });
}

async function writeTravelPilotManifest(params: {
  projectPath: string;
  projectId: string;
  projectName: string;
  preferredCli: string;
  selectedModel: string;
  travelCapabilityId?: string | null;
}) {
  const capability = getTravelCapability(params.travelCapabilityId);
  const visualizationTemplate = serializeTravelVisualizationTemplate(capability.id);
  const travelPilotDir = path.join(params.projectPath, '.travelpilot');
  await fs.mkdir(travelPilotDir, { recursive: true });
  await Promise.all([
    fs.mkdir(path.join(params.projectPath, 'data_file', 'raw'), { recursive: true }),
    fs.mkdir(path.join(params.projectPath, 'data_file', 'intermediate'), { recursive: true }),
    fs.mkdir(path.join(params.projectPath, 'data_file', 'final'), { recursive: true }),
    fs.mkdir(path.join(params.projectPath, 'evidence'), { recursive: true }),
    fs.mkdir(path.join(params.projectPath, 'scripts'), { recursive: true }),
    fs.mkdir(path.join(params.projectPath, 'dashboard'), { recursive: true }),
  ]);

  const manifest = {
    schemaVersion: 1,
    projectId: params.projectId,
    projectName: params.projectName,
    platform: '北京旅游规划',
    createdAt: new Date().toISOString(),
    runtime: {
      cli: params.preferredCli,
      model: params.selectedModel,
    },
    travel: buildTravelProjectSettings(capability.id),
  };

  await fs.writeFile(
    path.join(travelPilotDir, 'manifest.json'),
    `${JSON.stringify(manifest, null, 2)}\n`,
    'utf8'
  );
  await fs.writeFile(
    path.join(travelPilotDir, 'run_plan.json'),
    `${JSON.stringify(
      {
        schemaVersion: 1,
        runId: null,
        status: 'pending',
        capabilityId: capability.id,
        question: '',
        cityId: 'beijing',
        routeMode: capability.id === 'culture_route' || capability.id === 'efficient_route' ? 'culture' : 'mixed',
        area: null,
        constraints: {},
        dataRequirements: capability.dataEndpoints,
        analysisSteps: [],
        visualization: {
          required: false,
          templateId: visualizationTemplate.templateId,
          name: visualizationTemplate.name,
          scenario: visualizationTemplate.scenario,
          panels: visualizationTemplate.requiredComponents,
          painPoints: visualizationTemplate.painPoints,
          optionalPanels: visualizationTemplate.optionalComponents,
          dataSignals: visualizationTemplate.dataSignals,
          finalDataContract: visualizationTemplate.finalDataContract,
        },
        expectedArtifacts: capability.expectedArtifacts,
        validationRules: capability.validationRules,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      null,
      2
    )}\n`,
    'utf8'
  );
  await fs.writeFile(
    path.join(travelPilotDir, 'events.jsonl'),
    '',
    { encoding: 'utf8', flag: 'a' }
  );
}

function localProjectFromManifest(projectId: string, manifest: Record<string, any>, projectPath: string): Project {
  const preferredCli = String(manifest.runtime?.cli || 'claude');
  const selectedModel = normalizeModelId(preferredCli, manifest.runtime?.model || getDefaultModelForCli(preferredCli));
  const now = new Date();
  return {
    id: projectId,
    name: String(manifest.projectName || projectId),
    description: 'Local Beijing travel project',
    initialPrompt: '',
    repoPath: projectPath,
    preferredCli,
    selectedModel,
    settings: JSON.stringify({ travel: manifest.travel || buildTravelProjectSettings() }),
    status: 'idle',
    templateType: 'nextjs',
    createdAt: manifest.createdAt ? new Date(manifest.createdAt) : now,
    updatedAt: now,
    lastActiveAt: now,
    previewUrl: null,
    previewPort: null,
    activeClaudeSessionId: undefined,
    activeCursorSessionId: undefined,
    fallbackEnabled: true,
  } as Project;
}

async function readLocalProject(projectId: string): Promise<Project | null> {
  const projectPath = path.join(PROJECTS_DIR_ABSOLUTE, projectId);
  try {
    const raw = await fs.readFile(path.join(projectPath, '.travelpilot', 'manifest.json'), 'utf8');
    const manifest = JSON.parse(raw);
    return localProjectFromManifest(projectId, manifest, projectPath);
  } catch {
    return null;
  }
}

async function listLocalProjects(): Promise<Project[]> {
  try {
    const entries = await fs.readdir(PROJECTS_DIR_ABSOLUTE, { withFileTypes: true });
    const projects = await Promise.all(
      entries
        .filter((entry) => entry.isDirectory())
        .map((entry) => readLocalProject(entry.name))
    );
    return projects.filter(Boolean) as Project[];
  } catch {
    return [];
  }
}

/**
 * Retrieve all projects
 */
export async function getAllProjects(): Promise<Project[]> {
  try {
    const projects = await prisma.project.findMany({
      orderBy: {
        lastActiveAt: 'desc',
      },
    });
    return projects.map(project => ({
      ...project,
      selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
    })) as Project[];
  } catch (error) {
    if (process.env.SKIP_DB_SYNC === '1') {
      console.warn('[ProjectService] Database unavailable, using local project manifests.');
      return listLocalProjects();
    }
    throw error;
  }
}

/**
 * Retrieve project by ID
 */
export async function getProjectById(id: string): Promise<Project | null> {
  if (process.env.SKIP_DB_SYNC === '1') {
    return readLocalProject(id);
  }

  try {
    const project = await prisma.project.findUnique({
      where: { id },
    });
    if (!project) return null;
    return {
      ...project,
      selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
    } as Project;
  } catch (error) {
    if (process.env.SKIP_DB_SYNC === '1') {
      console.warn(`[ProjectService] Database unavailable, reading local project ${id}.`);
      return readLocalProject(id);
    }
    throw error;
  }
}

/**
 * Create new project
 */
export async function createProject(input: CreateProjectInput): Promise<Project> {
  // Create project directory
  const projectPath = path.join(PROJECTS_DIR_ABSOLUTE, input.project_id);
  await fs.mkdir(projectPath, { recursive: true });
  await ensureClaudeSkillsForProject(projectPath);
  const preferredCli = input.preferredCli || 'claude';
  const selectedModel = normalizeModelId(
    preferredCli,
    input.selectedModel ?? getDefaultModelForCli(preferredCli)
  );
  const travelCapability = getTravelCapability(input.travelCapabilityId);
  await writeTravelPilotManifest({
    projectPath,
    projectId: input.project_id,
    projectName: input.name,
    preferredCli,
    selectedModel,
    travelCapabilityId: travelCapability.id,
  });

  try {
    const project = await prisma.project.create({
      data: {
        id: input.project_id,
        name: input.name,
        description: input.description,
        initialPrompt: input.initialPrompt,
        repoPath: projectPath,
        preferredCli,
        selectedModel,
        settings: mergeProjectSettings(undefined, travelCapability.id),
        status: 'idle',
        templateType: 'nextjs',
        lastActiveAt: new Date(),
        previewUrl: null,
        previewPort: null,
      },
    });

    console.log(`[ProjectService] Created project: ${project.id}`);
    return {
      ...project,
      selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
    } as Project;
  } catch (error) {
    if (process.env.SKIP_DB_SYNC === '1') {
      console.warn(`[ProjectService] Database unavailable, created local project manifest only: ${input.project_id}`);
      const localProject = await readLocalProject(input.project_id);
      if (localProject) return localProject;
    }
    throw error;
  }
}

/**
 * Update project
 */
export async function updateProject(
  id: string,
  input: UpdateProjectInput
): Promise<Project> {
  const existing = await prisma.project.findUnique({
    where: { id },
    select: { preferredCli: true },
  });
  const targetCli = input.preferredCli ?? existing?.preferredCli ?? 'claude';
  const normalizedModel = input.selectedModel
    ? normalizeModelId(targetCli, input.selectedModel)
    : undefined;

  const project = await prisma.project.update({
    where: { id },
    data: {
      ...input,
      ...(input.selectedModel
        ? { selectedModel: normalizedModel }
        : {}),
      updatedAt: new Date(),
    },
  });

  console.log(`[ProjectService] Updated project: ${id}`);
  return {
    ...project,
    selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
  } as Project;
}

/**
 * Delete project
 */
export async function deleteProject(id: string): Promise<void> {
  // Delete project directory
  const project = await getProjectById(id);
  const projectPath = project?.repoPath || path.join(PROJECTS_DIR_ABSOLUTE, id);
  if (projectPath) {
    try {
      await fs.rm(projectPath, { recursive: true, force: true });
    } catch (error) {
      console.warn(`[ProjectService] Failed to delete project directory:`, error);
    }
  }

  if (process.env.SKIP_DB_SYNC === '1') {
    console.log(`[ProjectService] Deleted local project: ${id}`);
    return;
  }

  // Delete project from database (related data automatically deleted via Cascade)
  try {
    await prisma.project.delete({
      where: { id },
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes('Record to delete does not exist')) {
      console.warn(`[ProjectService] Project database record already absent: ${id}`);
      return;
    }
    throw error;
  }

  console.log(`[ProjectService] Deleted project: ${id}`);
}

/**
 * Update project activity time
 */
export async function updateProjectActivity(id: string): Promise<void> {
  if (process.env.SKIP_DB_SYNC === '1') {
    return;
  }

  await prisma.project.update({
    where: { id },
    data: {
      lastActiveAt: new Date(),
    },
  });
}

/**
 * Update project status
 */
export async function updateProjectStatus(
  id: string,
  status: 'idle' | 'running' | 'stopped' | 'error'
): Promise<void> {
  await prisma.project.update({
    where: { id },
    data: {
      status,
      updatedAt: new Date(),
    },
  });
  console.log(`[ProjectService] Updated project status: ${id} -> ${status}`);
}

export interface ProjectCliPreference {
  preferredCli: string;
  fallbackEnabled: boolean;
  selectedModel: string | null;
}

export async function getProjectCliPreference(projectId: string): Promise<ProjectCliPreference | null> {
  const project = await prisma.project.findUnique({
    where: { id: projectId },
    select: {
      preferredCli: true,
      fallbackEnabled: true,
      selectedModel: true,
    },
  });

  if (!project) {
    return null;
  }

  return {
    preferredCli: project.preferredCli ?? 'claude',
    fallbackEnabled: project.fallbackEnabled ?? false,
    selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
  };
}

export async function updateProjectCliPreference(
  projectId: string,
  input: Partial<ProjectCliPreference>
): Promise<ProjectCliPreference> {
  const existing = await prisma.project.findUnique({
    where: { id: projectId },
    select: { preferredCli: true },
  });
  const targetCli = input.preferredCli ?? existing?.preferredCli ?? 'claude';

  const result = await prisma.project.update({
    where: { id: projectId },
    data: {
      ...(input.preferredCli ? { preferredCli: input.preferredCli } : {}),
      ...(typeof input.fallbackEnabled === 'boolean'
        ? { fallbackEnabled: input.fallbackEnabled }
        : {}),
      ...(input.selectedModel
        ? { selectedModel: normalizeModelId(targetCli, input.selectedModel) }
        : input.selectedModel === null
        ? { selectedModel: null }
        : {}),
      updatedAt: new Date(),
    },
    select: {
      preferredCli: true,
      fallbackEnabled: true,
      selectedModel: true,
    },
  });

  return {
    preferredCli: result.preferredCli ?? 'claude',
    fallbackEnabled: result.fallbackEnabled ?? false,
    selectedModel: normalizeModelId(result.preferredCli ?? 'claude', result.selectedModel ?? undefined),
  };
}
