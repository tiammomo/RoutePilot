/**
 * Project Service - Project management logic
 */

import { prisma } from '@/lib/db/client';
import type { Project, CreateProjectInput, UpdateProjectInput } from '@/types/backend';
import fs from 'fs/promises';
import path from 'path';
import { normalizeModelId, getDefaultModelForCli } from '@/lib/constants/cliModels';
import { ensureClaudeSkillsForProject } from '@/lib/services/claude-skills';
import { buildQuantProjectSettings, getQuantCapability } from '@/lib/quant/capabilities';
import { serializeQuantVisualizationTemplate } from '@/lib/quant/visualization-templates';

const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(/*turbopackIgnore: true*/ process.cwd(), PROJECTS_DIR);

function mergeProjectSettings(existing: string | null | undefined, quantCapabilityId?: string | null): string {
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
    quant: buildQuantProjectSettings(quantCapabilityId),
  });
}

async function writeQuantPilotManifest(params: {
  projectPath: string;
  projectId: string;
  projectName: string;
  preferredCli: string;
  selectedModel: string;
  quantCapabilityId?: string | null;
}) {
  const capability = getQuantCapability(params.quantCapabilityId);
  const visualizationTemplate = serializeQuantVisualizationTemplate(capability.id);
  const quantPilotDir = path.join(params.projectPath, '.quantpilot');
  await fs.mkdir(quantPilotDir, { recursive: true });
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
    platform: 'QuantPilot',
    createdAt: new Date().toISOString(),
    runtime: {
      cli: params.preferredCli,
      model: params.selectedModel,
    },
    quant: buildQuantProjectSettings(capability.id),
  };

  await fs.writeFile(
    path.join(quantPilotDir, 'manifest.json'),
    `${JSON.stringify(manifest, null, 2)}\n`,
    'utf8'
  );
  await fs.writeFile(
    path.join(quantPilotDir, 'run_plan.json'),
    `${JSON.stringify(
      {
        schemaVersion: 1,
        runId: null,
        status: 'pending',
        capabilityId: capability.id,
        question: '',
        symbols: [],
        timeRange: null,
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
    path.join(quantPilotDir, 'events.jsonl'),
    '',
    { encoding: 'utf8', flag: 'a' }
  );
}

/**
 * Retrieve all projects
 */
export async function getAllProjects(): Promise<Project[]> {
  const projects = await prisma.project.findMany({
    orderBy: {
      lastActiveAt: 'desc',
    },
  });
  return projects.map(project => ({
    ...project,
    selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
  })) as Project[];
}

/**
 * Retrieve project by ID
 */
export async function getProjectById(id: string): Promise<Project | null> {
  const project = await prisma.project.findUnique({
    where: { id },
  });
  if (!project) return null;
  return {
    ...project,
    selectedModel: normalizeModelId(project.preferredCli ?? 'claude', project.selectedModel ?? undefined),
  } as Project;
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
  const quantCapability = getQuantCapability(input.quantCapabilityId);
  await writeQuantPilotManifest({
    projectPath,
    projectId: input.project_id,
    projectName: input.name,
    preferredCli,
    selectedModel,
    quantCapabilityId: quantCapability.id,
  });

  // Create project in database
  const project = await prisma.project.create({
    data: {
      id: input.project_id,
      name: input.name,
      description: input.description,
      initialPrompt: input.initialPrompt,
      repoPath: projectPath,
      preferredCli,
      selectedModel,
      settings: mergeProjectSettings(undefined, quantCapability.id),
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
  if (project?.repoPath) {
    try {
      await fs.rm(project.repoPath, { recursive: true, force: true });
    } catch (error) {
      console.warn(`[ProjectService] Failed to delete project directory:`, error);
    }
  }

  // Delete project from database (related data automatically deleted via Cascade)
  await prisma.project.delete({
    where: { id },
  });

  console.log(`[ProjectService] Deleted project: ${id}`);
}

/**
 * Update project activity time
 */
export async function updateProjectActivity(id: string): Promise<void> {
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
