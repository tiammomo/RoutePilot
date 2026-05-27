import fs from 'fs/promises';
import path from 'path';
import { getAllProjects } from '@/lib/services/project';
import { readQuantRunPlan, type QuantWorkspaceEvent } from '@/lib/quant/workspace';
import {
  readQuantValidationRepairPlan,
  readQuantValidationReport,
  type QuantValidationReport,
} from '@/lib/quant/validation';
import {
  QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
  QUANT_GENERATION_QUEUE_RELATIVE_PATH,
  QUANT_GENERATION_STATE_RELATIVE_PATH,
  QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
} from '@/lib/quant/artifacts';
import { readQuantArtifactContractReport } from '@/lib/quant/artifact-contracts';
import { readQuantGenerationQueue } from '@/lib/quant/generation-queue';
import { readQuantVisualValidationReport } from '@/lib/quant/visual-validation';
import type { Project } from '@/types/backend';

type JsonRecord = Record<string, unknown>;

export type WorkspaceHealthStatus = 'healthy' | 'warning' | 'failed' | 'unknown';

export interface WorkspaceHealthArtifact {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  status: WorkspaceHealthStatus;
  updatedAt: string | null;
  summary: string;
}

export interface WorkspaceHealthItem {
  id: string;
  name: string;
  description: string | null;
  status: string;
  repoPath: string;
  preferredCli: string | null;
  selectedModel: string | null;
  quantCapabilityId: string | null;
  previewUrl: string | null;
  createdAt: string;
  updatedAt: string;
  lastActiveAt: string | null;
  health: {
    status: WorkspaceHealthStatus;
    score: number;
    summary: string;
    blockers: number;
    warnings: number;
  };
  validation: {
    status: WorkspaceHealthStatus;
    passed: boolean | null;
    updatedAt: string | null;
    failedChecks: number;
    warningChecks: number;
  };
  dataQuality: {
    status: WorkspaceHealthStatus;
    datasetCount: number;
    warningCount: number;
    sourceCount: number;
    updatedAt: string | null;
  };
  runPlan: {
    status: string | null;
    capabilityId: string | null;
    symbols: string[];
    updatedAt: string | null;
  };
  generationQueue: {
    activeRequestId: string | null;
    running: number;
    queued: number;
    failed: number;
    updatedAt: string | null;
  };
  artifactContracts: {
    status: WorkspaceHealthStatus;
    passed: boolean | null;
    failedChecks: number;
    warningChecks: number;
    updatedAt: string | null;
    path: string;
  };
  visualValidation: {
    status: WorkspaceHealthStatus;
    passed: boolean | null;
    failedChecks: number;
    warningChecks: number;
    updatedAt: string | null;
    path: string;
  };
  artifacts: WorkspaceHealthArtifact[];
  events: QuantWorkspaceEvent[];
  repairPlan: {
    needed: boolean;
    stepCount: number;
    path: string | null;
  };
  nextActions: string[];
}

export interface WorkspaceHealthDashboard {
  generatedAt: string;
  projectsDir: string;
  summary: {
    total: number;
    healthy: number;
    warning: number;
    failed: number;
    unknown: number;
    averageScore: number;
  };
  projects: WorkspaceHealthItem[];
}

const ROOT = process.cwd();
const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(ROOT, PROJECTS_DIR);

const REQUIRED_ARTIFACTS = [
  { id: 'run_plan', label: 'Run Plan', path: '.quantpilot/run_plan.json' },
  { id: 'generation_state', label: '生成状态', path: QUANT_GENERATION_STATE_RELATIVE_PATH },
  { id: 'generation_queue', label: '生成队列', path: QUANT_GENERATION_QUEUE_RELATIVE_PATH },
  { id: 'events', label: '事件日志', path: '.quantpilot/events.jsonl' },
  { id: 'final_data', label: '最终数据', path: 'data_file/final/dashboard-data.json' },
  { id: 'sources', label: '数据来源', path: 'evidence/sources.json' },
  { id: 'data_quality', label: '数据质量', path: 'evidence/data_quality.json' },
  { id: 'artifact_contracts', label: '产物契约', path: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH },
  { id: 'visual_validation', label: '视觉验收', path: QUANT_VISUAL_VALIDATION_RELATIVE_PATH },
  { id: 'validation', label: '验证报告', path: '.quantpilot/validation.json' },
  { id: 'page', label: '页面入口', path: 'app/page.tsx' },
];

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function readSettingsCapabilityId(settings?: string | null) {
  if (!settings) return null;
  try {
    const parsed = JSON.parse(settings);
    if (!isRecord(parsed) || !isRecord(parsed.quant)) return null;
    return stringValue(parsed.quant.capabilityId) || null;
  } catch {
    return null;
  }
}

async function readJson(filePath: string): Promise<unknown> {
  const content = await fs.readFile(filePath, 'utf8');
  return JSON.parse(content);
}

async function readJsonRecord(filePath: string): Promise<JsonRecord | null> {
  const parsed = await readJson(filePath).catch(() => null);
  return isRecord(parsed) ? parsed : null;
}

async function statFile(filePath: string) {
  const stat = await fs.stat(filePath).catch(() => null);
  return stat?.isFile() ? stat : null;
}

function statusRank(status: WorkspaceHealthStatus) {
  return { healthy: 0, warning: 1, unknown: 2, failed: 3 }[status];
}

function normalizeArtifactStatus(exists: boolean, id: string, validation: QuantValidationReport | null, dataQuality: JsonRecord | null): WorkspaceHealthStatus {
  if (!exists) {
    if (id === 'generation_state') return 'unknown';
    if (id === 'generation_queue') return 'unknown';
    if (id === 'artifact_contracts') return 'unknown';
    if (id === 'visual_validation') return 'unknown';
    if (id === 'validation') return 'unknown';
    if (id === 'events') return 'warning';
    return 'failed';
  }
  if (id === 'validation') {
    if (!validation) return 'unknown';
    return validation.passed ? 'healthy' : 'failed';
  }
  if (id === 'data_quality') {
    const status = stringValue(dataQuality?.status);
    if (status === 'ok' || status === 'passed') return 'healthy';
    if (status === 'warning') return 'warning';
  }
  return 'healthy';
}

function countValidationChecks(report: QuantValidationReport | null, status: 'failed' | 'warning') {
  return report?.checks.filter((check) => check.status === status).length ?? 0;
}

function readArrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function buildDataQualitySummary(dataQuality: JsonRecord | null, sources: JsonRecord | null): WorkspaceHealthItem['dataQuality'] {
  const datasets = Array.isArray(dataQuality?.datasets) ? dataQuality.datasets : [];
  const checks = Array.isArray(dataQuality?.checks) ? dataQuality.checks : [];
  const warnings = readArrayLength(dataQuality?.warnings) + checks.filter((check) => isRecord(check) && stringValue(check.status) === 'warning').length;
  const sourceCount =
    readArrayLength(sources?.sources) ||
    readArrayLength(sources?.datasets) ||
    readArrayLength(sources?.items) ||
    datasets.filter((dataset) => isRecord(dataset) && stringValue(dataset.source)).length;
  const statusText = stringValue(dataQuality?.status);
  const status =
    statusText === 'ok' || statusText === 'passed'
      ? 'healthy'
      : statusText === 'warning'
        ? 'warning'
        : dataQuality
          ? 'unknown'
          : 'failed';

  return {
    status,
    datasetCount: datasets.length,
    warningCount: warnings,
    sourceCount,
    updatedAt: stringValue(dataQuality?.created_at) || stringValue(dataQuality?.updatedAt) || null,
  };
}

async function readEvents(projectPath: string): Promise<QuantWorkspaceEvent[]> {
  const filePath = path.join(projectPath, '.quantpilot', 'events.jsonl');
  const content = await fs.readFile(filePath, 'utf8').catch(() => '');
  return content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-20)
    .map((line) => {
      try {
        const parsed = JSON.parse(line);
        return isRecord(parsed) ? (parsed as unknown as QuantWorkspaceEvent) : null;
      } catch {
        return null;
      }
    })
    .filter((event): event is QuantWorkspaceEvent => Boolean(event));
}

function buildNextActions(params: {
  artifacts: WorkspaceHealthArtifact[];
  validation: WorkspaceHealthItem['validation'];
  dataQuality: WorkspaceHealthItem['dataQuality'];
  repairPlanNeeded: boolean;
  contracts: WorkspaceHealthItem['artifactContracts'];
  visual: WorkspaceHealthItem['visualValidation'];
  queue: WorkspaceHealthItem['generationQueue'];
}) {
  const actions: string[] = [];
  const missing = params.artifacts.filter((artifact) => !artifact.exists);
  if (missing.length) {
    actions.push(`补齐缺失产物：${missing.slice(0, 3).map((artifact) => artifact.label).join('、')}。`);
  }
  if (params.validation.status === 'failed') {
    actions.push('重新运行自动验证，并按失败 check 生成修复指令。');
  } else if (params.validation.status === 'unknown') {
    actions.push('运行一次自动验证，生成 .quantpilot/validation.json。');
  }
  if (params.dataQuality.status === 'warning') {
    actions.push('检查 evidence/data_quality.json 中的数据缺口，并在页面结论中说明限制。');
  }
  if (params.repairPlanNeeded) {
    actions.push('处理 validation-repair-plan.json 中的修复步骤。');
  }
  if (params.contracts.status === 'failed') {
    actions.push(`修复 ${params.contracts.path} 中的 ${params.contracts.failedChecks} 个失败契约。`);
  }
  if (params.visual.status === 'failed') {
    actions.push(`查看 ${params.visual.path} 和截图，修复 ${params.visual.failedChecks} 个视觉阻断项。`);
  }
  if (params.queue.queued > 0 || params.queue.running > 0) {
    actions.push(`生成队列中仍有 ${params.queue.running} 个运行中、${params.queue.queued} 个排队任务。`);
  }
  if (!actions.length) {
    actions.push('保持当前 workspace，后续变更后重新验证。');
  }
  return actions;
}

function summarizeHealth(status: WorkspaceHealthStatus, blockers: number, warnings: number) {
  if (status === 'healthy') return '工作空间关键产物和验证状态正常。';
  if (status === 'failed') return `${blockers} 个阻断项需要处理。`;
  if (status === 'warning') return `${warnings} 个风险项需要关注。`;
  return '工作空间状态不完整，需要先补充验证报告。';
}

async function inspectWorkspace(project: Project): Promise<WorkspaceHealthItem> {
  const projectPath = project.repoPath
    ? path.isAbsolute(project.repoPath)
      ? project.repoPath
      : path.resolve(ROOT, project.repoPath)
    : path.join(PROJECTS_DIR_ABSOLUTE, project.id);
  const [validationReport, repairPlan, runPlan, events, dataQuality, sources, generationQueue, artifactContractReport, visualValidationReport] = await Promise.all([
    readQuantValidationReport(projectPath),
    readQuantValidationRepairPlan(projectPath),
    readQuantRunPlan(projectPath),
    readEvents(projectPath),
    readJsonRecord(path.join(projectPath, 'evidence', 'data_quality.json')),
    readJsonRecord(path.join(projectPath, 'evidence', 'sources.json')),
    readQuantGenerationQueue(projectPath, project.id),
    readQuantArtifactContractReport(projectPath),
    readQuantVisualValidationReport(projectPath),
  ]);

  const artifacts = await Promise.all(
    REQUIRED_ARTIFACTS.map(async (artifact): Promise<WorkspaceHealthArtifact> => {
      const absolutePath = path.join(projectPath, artifact.path);
      const stat = await statFile(absolutePath);
      const status = normalizeArtifactStatus(Boolean(stat), artifact.id, validationReport, dataQuality);
      return {
        ...artifact,
        exists: Boolean(stat),
        status,
        updatedAt: stat?.mtime.toISOString() ?? null,
        summary: stat ? '已生成' : '缺失',
      };
    })
  );
  const dataQualitySummary = buildDataQualitySummary(dataQuality, sources);
  const validationStatus: WorkspaceHealthItem['validation'] = {
    status: validationReport ? (validationReport.passed ? 'healthy' : 'failed') : 'unknown',
    passed: validationReport?.passed ?? null,
    updatedAt: validationReport?.updatedAt ?? validationReport?.createdAt ?? null,
    failedChecks: countValidationChecks(validationReport, 'failed'),
    warningChecks: countValidationChecks(validationReport, 'warning'),
  };
  const queueSummary: WorkspaceHealthItem['generationQueue'] = {
    activeRequestId: generationQueue.activeRequestId,
    running: generationQueue.items.filter((item) => item.status === 'running').length,
    queued: generationQueue.items.filter((item) => item.status === 'queued').length,
    failed: generationQueue.items.filter((item) => item.status === 'failed').length,
    updatedAt: generationQueue.updatedAt ?? null,
  };
  const artifactContracts: WorkspaceHealthItem['artifactContracts'] = {
    status: artifactContractReport
      ? artifactContractReport.status === 'passed'
        ? 'healthy'
        : artifactContractReport.status === 'warning'
          ? 'warning'
          : 'failed'
      : 'unknown',
    passed: artifactContractReport?.passed ?? null,
    failedChecks: artifactContractReport?.checks.filter((check) => check.status === 'failed').length ?? 0,
    warningChecks: artifactContractReport?.checks.filter((check) => check.status === 'warning').length ?? 0,
    updatedAt: artifactContractReport?.updatedAt ?? null,
    path: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
  };
  const visualValidation: WorkspaceHealthItem['visualValidation'] = {
    status: visualValidationReport
      ? visualValidationReport.status === 'passed'
        ? 'healthy'
        : visualValidationReport.status === 'warning'
          ? 'warning'
          : 'failed'
      : 'unknown',
    passed: visualValidationReport?.passed ?? null,
    failedChecks: visualValidationReport?.failures.length ?? 0,
    warningChecks: visualValidationReport?.warnings.length ?? 0,
    updatedAt: visualValidationReport?.updatedAt ?? null,
    path: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
  };
  const blockers =
    artifacts.filter((artifact) => artifact.status === 'failed').length +
    (validationStatus.status === 'failed' ? validationStatus.failedChecks || 1 : 0) +
    (artifactContracts.status === 'failed' ? artifactContracts.failedChecks || 1 : 0) +
    (visualValidation.status === 'failed' ? visualValidation.failedChecks || 1 : 0);
  const warnings =
    artifacts.filter((artifact) => artifact.status === 'warning' || artifact.status === 'unknown').length +
    validationStatus.warningChecks +
    dataQualitySummary.warningCount +
    artifactContracts.warningChecks +
    visualValidation.warningChecks +
    (queueSummary.running + queueSummary.queued > 0 ? 1 : 0);
  const worstStatus = [validationStatus.status, dataQualitySummary.status, artifactContracts.status, visualValidation.status, ...artifacts.map((artifact) => artifact.status)]
    .sort((a, b) => statusRank(b) - statusRank(a))[0] ?? 'unknown';
  const healthStatus: WorkspaceHealthStatus = blockers ? 'failed' : worstStatus === 'failed' ? 'failed' : warnings ? 'warning' : 'healthy';
  const score = Math.max(0, Math.min(100, 100 - blockers * 18 - warnings * 4));
  const repairPlanNeeded = Boolean(repairPlan?.steps?.length);

  return {
    id: project.id,
    name: project.name,
    description: project.description ?? null,
    status: project.status,
    repoPath: path.relative(ROOT, projectPath),
    preferredCli: project.preferredCli ?? null,
    selectedModel: project.selectedModel ?? null,
    quantCapabilityId: readSettingsCapabilityId(project.settings),
    previewUrl: project.previewUrl ?? null,
    createdAt: project.createdAt.toISOString(),
    updatedAt: project.updatedAt.toISOString(),
    lastActiveAt: project.lastActiveAt?.toISOString() ?? null,
    health: {
      status: healthStatus,
      score,
      summary: summarizeHealth(healthStatus, blockers, warnings),
      blockers,
      warnings,
    },
    validation: validationStatus,
    dataQuality: dataQualitySummary,
    runPlan: {
      status: runPlan?.status ?? null,
      capabilityId: runPlan?.capabilityId ?? null,
      symbols: runPlan?.symbols ?? [],
      updatedAt: runPlan?.updatedAt ?? null,
    },
    generationQueue: queueSummary,
    artifactContracts,
    visualValidation,
    artifacts,
    events,
    repairPlan: {
      needed: repairPlanNeeded,
      stepCount: repairPlan?.steps.length ?? 0,
      path: repairPlan?.repairPlanPath ?? null,
    },
    nextActions: buildNextActions({
      artifacts,
      validation: validationStatus,
      dataQuality: dataQualitySummary,
      repairPlanNeeded,
      contracts: artifactContracts,
      visual: visualValidation,
      queue: queueSummary,
    }),
  };
}

export async function getWorkspaceHealthDashboard(): Promise<WorkspaceHealthDashboard> {
  const projects = await getAllProjects();
  const items = await Promise.all(projects.map((project) => inspectWorkspace(project)));
  const summary = items.reduce(
    (acc, item) => {
      acc.total += 1;
      acc[item.health.status] += 1;
      acc.averageScore += item.health.score;
      return acc;
    },
    { total: 0, healthy: 0, warning: 0, failed: 0, unknown: 0, averageScore: 0 }
  );

  return {
    generatedAt: new Date().toISOString(),
    projectsDir: path.relative(ROOT, PROJECTS_DIR_ABSOLUTE),
    summary: {
      ...summary,
      averageScore: summary.total ? Math.round(summary.averageScore / summary.total) : 0,
    },
    projects: items.sort((a, b) => statusRank(b.health.status) - statusRank(a.health.status) || b.updatedAt.localeCompare(a.updatedAt)),
  };
}
