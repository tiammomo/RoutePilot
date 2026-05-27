import fs from 'fs/promises';
import path from 'path';
import { prisma } from '@/lib/db/client';
import { readQuantRunPlan, type QuantWorkspaceEvent } from '@/lib/quant/workspace';
import {
  readQuantValidationRepairPlan,
  readQuantValidationReport,
  type QuantValidationRepairPlan,
  type QuantValidationReport,
} from '@/lib/quant/validation';
import {
  QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
  QUANT_GENERATION_QUEUE_RELATIVE_PATH,
  QUANT_GENERATION_STATE_RELATIVE_PATH,
  QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
} from '@/lib/quant/artifacts';
import { readQuantArtifactContractReport, type QuantArtifactContractReport } from '@/lib/quant/artifact-contracts';
import { readQuantGenerationQueue, type QuantGenerationQueueState } from '@/lib/quant/generation-queue';
import { readQuantGenerationState, type QuantGenerationState } from '@/lib/quant/generation-state';
import { readQuantVisualValidationReport, type QuantVisualValidationReport } from '@/lib/quant/visual-validation';

type JsonRecord = Record<string, unknown>;

type ProjectWithTraceSources = Awaited<ReturnType<typeof loadProjectsWithTraceSources>>[number];

export type GenerationStageId =
  | 'request'
  | 'planning'
  | 'data'
  | 'tooling'
  | 'artifact'
  | 'validation'
  | 'repair'
  | 'completion'
  | 'system';

export type GenerationTraceStatus = 'success' | 'warning' | 'error' | 'pending' | 'unknown';

export interface GenerationTimelineEvent {
  id: string;
  projectId: string;
  source: 'user_request' | 'message' | 'tool_usage' | 'workspace_event' | 'run_plan' | 'validation' | 'repair_plan';
  stage: GenerationStageId;
  status: GenerationTraceStatus;
  title: string;
  summary: string;
  timestamp: string;
  requestId: string | null;
  artifactPath: string | null;
  metadata: JsonRecord;
}

export interface GenerationTraceStage {
  id: GenerationStageId;
  label: string;
  status: GenerationTraceStatus;
  eventCount: number;
  lastEventAt: string | null;
}

export interface GenerationTraceProject {
  id: string;
  name: string;
  description: string | null;
  status: string;
  repoPath: string;
  preferredCli: string | null;
  selectedModel: string | null;
  previewUrl: string | null;
  createdAt: string;
  updatedAt: string;
  lastActiveAt: string | null;
  trace: {
    status: GenerationTraceStatus;
    summary: string;
    activeStage: GenerationStageId;
    lastEventAt: string | null;
    eventCount: number;
    errorCount: number;
    warningCount: number;
    pendingCount: number;
    requestCount: number;
    toolCallCount: number;
    validationPassed: boolean | null;
    repairStepCount: number;
  };
  runPlan: {
    status: string | null;
    capabilityId: string | null;
    requestedCapabilityId: string | null;
    executionCapabilityId: string | null;
    symbols: string[];
    expectedArtifacts: string[];
    updatedAt: string | null;
  };
  stages: GenerationTraceStage[];
  timeline: GenerationTimelineEvent[];
  generationState: {
    status: string | null;
    activeStep: string | null;
    repairAttemptCount: number;
    maxRepairAttempts: number;
    updatedAt: string | null;
    path: string;
    steps: Array<{
      id: string;
      label: string;
      status: string;
      startedAt: string | null;
      completedAt: string | null;
      summary: string;
    }>;
    error: {
      step: string;
      message: string;
    } | null;
  } | null;
  generationQueue: {
    activeRequestId: string | null;
    running: number;
    queued: number;
    failed: number;
    updatedAt: string | null;
    path: string;
    items: Array<{
      requestId: string;
      status: string;
      cliPreference: string | null;
      selectedModel: string | null;
      instructionPreview: string;
      queuedAt: string;
      startedAt: string | null;
      completedAt: string | null;
      errorMessage: string | null;
    }>;
  };
  artifactContracts: {
    status: GenerationTraceStatus;
    passed: boolean | null;
    failedChecks: number;
    warningChecks: number;
    updatedAt: string | null;
    path: string;
    checks: Array<{
      id: string;
      label: string;
      path: string;
      required: boolean;
      status: string;
      summary: string;
      details?: string;
    }>;
  };
  visualValidation: {
    status: GenerationTraceStatus;
    passed: boolean | null;
    failedChecks: number;
    warningChecks: number;
    updatedAt: string | null;
    path: string;
    screenshots: string[];
    previewUrl: string | null;
    viewports: Array<{
      id: string;
      width: number;
      height: number;
      screenshotPath: string;
      status: string;
      failures: string[];
      warnings: string[];
    }>;
    failures: string[];
    warnings: string[];
  };
  latestRequest: {
    id: string;
    status: string;
    instruction: string;
    createdAt: string;
    completedAt: string | null;
    errorMessage: string | null;
  } | null;
  validation: {
    status: GenerationTraceStatus;
    passed: boolean | null;
    updatedAt: string | null;
    failedChecks: number;
    warningChecks: number;
  };
  repairPlan: {
    needed: boolean;
    stepCount: number;
    path: string | null;
    createdAt: string | null;
  };
  topTools: Array<{
    name: string;
    count: number;
    errorCount: number;
    averageDurationMs: number | null;
  }>;
  nextActions: string[];
}

export interface GenerationObservabilityDashboard {
  generatedAt: string;
  projectsDir: string;
  summary: {
    total: number;
    healthy: number;
    warning: number;
    failed: number;
    running: number;
    unknown: number;
    eventsLast24h: number;
    toolCalls: number;
    requests: number;
  };
  projects: GenerationTraceProject[];
}

const ROOT = process.cwd();
const PROJECTS_DIR = process.env.PROJECTS_DIR || './data/projects';
const PROJECTS_DIR_ABSOLUTE = path.isAbsolute(PROJECTS_DIR)
  ? PROJECTS_DIR
  : path.resolve(ROOT, PROJECTS_DIR);
const MAX_TIMELINE_EVENTS = 220;
const MAX_WORKSPACE_EVENTS = 160;
const FALLBACK_EVENT_TIMESTAMP = '1970-01-01T00:00:00.000Z';

const STAGES: Array<{ id: GenerationStageId; label: string }> = [
  { id: 'request', label: '请求' },
  { id: 'planning', label: '规划' },
  { id: 'data', label: '数据' },
  { id: 'tooling', label: '工具' },
  { id: 'artifact', label: '产物' },
  { id: 'validation', label: '验证' },
  { id: 'repair', label: '修复' },
  { id: 'completion', label: '完成' },
];

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function parseJsonRecord(value?: string | null): JsonRecord {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return isRecord(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function compact(value: string, max = 180): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1)}…`;
}

function dateToIso(value: Date | string | null | undefined): string | null {
  if (!value) return null;
  if (value instanceof Date) return value.toISOString();
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function timestampFromWorkspaceEvent(event: QuantWorkspaceEvent & JsonRecord): string {
  return (
    dateToIso(stringValue(event.created_at)) ||
    dateToIso(stringValue(event.ts)) ||
    dateToIso(stringValue(event.timestamp)) ||
    FALLBACK_EVENT_TIMESTAMP
  );
}

function statusRank(status: GenerationTraceStatus) {
  return { success: 0, unknown: 1, pending: 2, warning: 3, error: 4 }[status];
}

function normalizeStatus(value: unknown): GenerationTraceStatus {
  const normalized = String(value ?? '').toLowerCase();
  if (['success', 'succeeded', 'passed', 'completed', 'complete', 'done', 'healthy', 'ok'].includes(normalized)) {
    return 'success';
  }
  if (['warning', 'warn', 'needs_clarification', 'stale', 'risk'].includes(normalized)) {
    return 'warning';
  }
  if (['error', 'failed', 'failure', 'blocked', 'fatal'].includes(normalized)) {
    return 'error';
  }
  if (['pending', 'processing', 'running', 'starting', 'in_progress', 'planned'].includes(normalized)) {
    return 'pending';
  }
  return 'unknown';
}

function normalizeRequestStatus(status: string): GenerationTraceStatus {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'pending' || status === 'processing') return 'pending';
  return normalizeStatus(status);
}

function stageFromWorkspaceEvent(event: QuantWorkspaceEvent & JsonRecord): GenerationStageId {
  const raw = `${stringValue(event.stage)} ${stringValue(event.event_type)}`.toLowerCase();
  if (/queue/.test(raw)) return 'request';
  if (/intent|request|clarification/.test(raw)) return raw.includes('intent') ? 'planning' : 'request';
  if (/plan|planning|run_plan/.test(raw)) return 'planning';
  if (/data|quality|source|market|symbol|image|evidence/.test(raw)) return 'data';
  if (/validation|validate/.test(raw)) return 'validation';
  if (/repair|fix/.test(raw)) return 'repair';
  if (/complete|completed|finish|done/.test(raw)) return 'completion';
  if (/execution|artifact|visualization|page|dashboard/.test(raw)) return 'artifact';
  return 'system';
}

function stageFromMessage(messageType: string, role: string, metadata: JsonRecord): GenerationStageId {
  const text = `${messageType} ${role} ${stringValue(metadata.toolName)} ${stringValue(metadata.tool_name)} ${stringValue(metadata.action)}`.toLowerCase();
  if (messageType === 'error') return 'system';
  if (/tool|bash|read|write|edit|apply_patch/.test(text)) return 'tooling';
  if (role === 'user') return 'request';
  if (/plan|thinking/.test(text)) return 'planning';
  if (role === 'assistant') return 'completion';
  return 'system';
}

function messageTitle(messageType: string, role: string, metadata: JsonRecord) {
  const toolName = stringValue(metadata.toolName) || stringValue(metadata.tool_name);
  if (toolName) return messageType === 'tool_result' ? `工具结果：${toolName}` : `工具调用：${toolName}`;
  if (messageType === 'thinking') return 'Agent 思考';
  if (messageType === 'error') return 'Agent 错误';
  if (role === 'user') return '用户消息';
  if (role === 'assistant') return 'Agent 回复';
  return '系统消息';
}

function messageStatus(messageType: string, metadata: JsonRecord): GenerationTraceStatus {
  if (messageType === 'error') return 'error';
  const status = normalizeStatus(metadata.status);
  if (status !== 'unknown') return status;
  if (metadata.error || metadata.isError) return 'error';
  return 'success';
}

function toolSummary(toolInput: string, toolOutput: string | null, error: string | null, durationMs: number | null) {
  if (error) return compact(error, 200);
  const duration = durationMs ? `，耗时 ${durationMs}ms` : '';
  const output = toolOutput ? compact(toolOutput, 120) : '';
  if (output) return `执行完成${duration}：${output}`;
  return `执行完成${duration || '。'}`;
}

function workspaceEventTitle(event: QuantWorkspaceEvent & JsonRecord) {
  const eventType = stringValue(event.event_type);
  if (eventType === 'run_planned') return '生成计划';
  if (eventType === 'intent_clarification_required') return '意图需要澄清';
  if (eventType === 'data_prefetch_started') return '数据预取开始';
  if (eventType === 'data_prefetched') return '数据预取完成';
  if (eventType === 'data_quality_checked') return '数据质量检查';
  if (eventType === 'image_attachment_evidence_created') return '图片证据建立';
  if (eventType === 'agent_auto_completed') return 'Agent 自动完成';
  if (eventType === 'validation_started') return '验证开始';
  if (eventType === 'validation_completed') return '验证完成';
  return eventType || stringValue(event.stage) || '工作空间事件';
}

async function readWorkspaceEvents(projectPath: string): Promise<Array<QuantWorkspaceEvent & JsonRecord>> {
  const filePath = path.join(projectPath, '.quantpilot', 'events.jsonl');
  const content = await fs.readFile(filePath, 'utf8').catch(() => '');
  return content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-MAX_WORKSPACE_EVENTS)
    .map((line) => {
      try {
        const parsed = JSON.parse(line);
        return isRecord(parsed) ? (parsed as QuantWorkspaceEvent & JsonRecord) : null;
      } catch {
        return null;
      }
    })
    .filter((event): event is QuantWorkspaceEvent & JsonRecord => Boolean(event));
}

function resolveProjectPath(project: Pick<ProjectWithTraceSources, 'id' | 'repoPath'>) {
  if (project.repoPath) {
    return path.isAbsolute(project.repoPath) ? project.repoPath : path.resolve(ROOT, project.repoPath);
  }
  return path.join(PROJECTS_DIR_ABSOLUTE, project.id);
}

async function loadProjectsWithTraceSources() {
  return prisma.project.findMany({
    orderBy: { lastActiveAt: 'desc' },
    include: {
      userRequests: {
        orderBy: { createdAt: 'desc' },
        take: 40,
      },
      messages: {
        orderBy: { createdAt: 'desc' },
        take: 180,
      },
      toolUsages: {
        orderBy: { createdAt: 'desc' },
        take: 140,
      },
    },
  });
}

function buildUserRequestEvents(project: ProjectWithTraceSources): GenerationTimelineEvent[] {
  return [...project.userRequests].reverse().map((request) => ({
    id: `request:${request.id}`,
    projectId: project.id,
    source: 'user_request',
    stage: 'request',
    status: normalizeRequestStatus(request.status),
    title: '用户请求',
    summary: compact(request.instruction),
    timestamp: request.createdAt.toISOString(),
    requestId: request.id,
    artifactPath: null,
    metadata: {
      cliPreference: request.cliPreference,
      completedAt: dateToIso(request.completedAt),
      errorMessage: request.errorMessage,
    },
  }));
}

function shouldKeepMessage(messageType: string, role: string, metadata: JsonRecord): boolean {
  if (messageType !== 'chat') return true;
  if (role === 'user') return true;
  return Boolean(metadata.toolName || metadata.tool_name || metadata.status || metadata.action || metadata.error);
}

function buildMessageEvents(project: ProjectWithTraceSources): GenerationTimelineEvent[] {
  return [...project.messages]
    .reverse()
    .filter((message) => shouldKeepMessage(message.messageType, message.role, parseJsonRecord(message.metadataJson)))
    .map((message) => {
      const metadata = parseJsonRecord(message.metadataJson);
      const artifactPath =
        stringValue(metadata.path) ||
        stringValue(metadata.file_path) ||
        stringValue(metadata.filePath) ||
        null;
      return {
        id: `message:${message.id}`,
        projectId: project.id,
        source: 'message',
        stage: stageFromMessage(message.messageType, message.role, metadata),
        status: messageStatus(message.messageType, metadata),
        title: messageTitle(message.messageType, message.role, metadata),
        summary: compact(message.content || messageTitle(message.messageType, message.role, metadata), 170),
        timestamp: message.createdAt.toISOString(),
        requestId: message.requestId,
        artifactPath,
        metadata: {
          role: message.role,
          messageType: message.messageType,
          cliSource: message.cliSource,
          durationMs: message.durationMs,
          tokenCount: message.tokenCount,
          costUsd: message.costUsd,
          ...metadata,
        },
      };
    });
}

function buildToolEvents(project: ProjectWithTraceSources): GenerationTimelineEvent[] {
  return [...project.toolUsages].reverse().map((tool) => {
    const metadata = parseJsonRecord(tool.toolInput);
    const artifactPath =
      stringValue(metadata.path) ||
      stringValue(metadata.file_path) ||
      stringValue(metadata.filePath) ||
      null;
    return {
      id: `tool:${tool.id}`,
      projectId: project.id,
      source: 'tool_usage',
      stage: 'tooling',
      status: tool.error ? 'error' : 'success',
      title: `工具调用：${tool.toolName}`,
      summary: toolSummary(tool.toolInput, tool.toolOutput, tool.error, tool.durationMs),
      timestamp: tool.createdAt.toISOString(),
      requestId: null,
      artifactPath,
      metadata: {
        toolName: tool.toolName,
        durationMs: tool.durationMs,
        messageId: tool.messageId,
        input: metadata,
      },
    };
  });
}

function buildWorkspaceEvents(projectId: string, events: Array<QuantWorkspaceEvent & JsonRecord>): GenerationTimelineEvent[] {
  return events.map((event, index) => ({
    id: `workspace:${projectId}:${index}:${timestampFromWorkspaceEvent(event)}`,
    projectId,
    source: 'workspace_event',
    stage: stageFromWorkspaceEvent(event),
    status: normalizeStatus(event.status),
    title: workspaceEventTitle(event),
    summary: compact(stringValue(event.summary) || stringValue(event.stage) || '工作空间事件'),
    timestamp: timestampFromWorkspaceEvent(event),
    requestId: stringValue(event.run_id) || null,
    artifactPath: stringValue(event.artifact_path) || null,
    metadata: {
      eventType: stringValue(event.event_type),
      rawStage: stringValue(event.stage),
    },
  }));
}

function buildRunPlanEvent(projectId: string, runPlan: Awaited<ReturnType<typeof readQuantRunPlan>>): GenerationTimelineEvent[] {
  if (!runPlan) return [];
  return [
    {
      id: `run-plan:${projectId}:${runPlan.runId ?? runPlan.updatedAt}`,
      projectId,
      source: 'run_plan',
      stage: 'planning',
      status: runPlan.status === 'needs_clarification' ? 'warning' : normalizeStatus(runPlan.status),
      title: '当前执行计划',
      summary: compact(runPlan.question || `${runPlan.capabilityId} · ${runPlan.symbols.join('、')}` || '已生成执行计划'),
      timestamp: runPlan.updatedAt ?? runPlan.createdAt,
      requestId: runPlan.runId ?? null,
      artifactPath: '.quantpilot/run_plan.json',
      metadata: {
        capabilityId: runPlan.capabilityId,
        requestedCapabilityId: runPlan.requestedCapabilityId,
        executionCapabilityId: runPlan.executionCapabilityId,
        symbols: runPlan.symbols,
        expectedArtifacts: runPlan.expectedArtifacts,
      },
    },
  ];
}

function buildValidationEvent(projectId: string, report: QuantValidationReport | null): GenerationTimelineEvent[] {
  if (!report) return [];
  const failed = report.checks.filter((check) => check.status === 'failed').length;
  const warnings = report.checks.filter((check) => check.status === 'warning').length;
  return [
    {
      id: `validation-report:${projectId}:${report.updatedAt}`,
      projectId,
      source: 'validation',
      stage: 'validation',
      status: report.passed ? 'success' : 'error',
      title: '最新验证报告',
      summary: report.passed
        ? `验证通过，${report.checks.length} 项检查完成。`
        : `验证未通过：${failed} 项失败，${warnings} 项警告。`,
      timestamp: report.updatedAt ?? report.createdAt,
      requestId: report.runId ?? null,
      artifactPath: report.reportPath,
      metadata: {
        failedChecks: failed,
        warningChecks: warnings,
        checkCount: report.checks.length,
      },
    },
  ];
}

function buildRepairEvent(projectId: string, repairPlan: QuantValidationRepairPlan | null): GenerationTimelineEvent[] {
  if (!repairPlan?.steps.length) return [];
  return [
    {
      id: `repair-plan:${projectId}:${repairPlan.createdAt}`,
      projectId,
      source: 'repair_plan',
      stage: 'repair',
      status: 'warning',
      title: '验证修复计划',
      summary: `需要处理 ${repairPlan.steps.length} 个修复步骤：${compact(repairPlan.steps.map((step) => step.checkName).join('、'), 130)}`,
      timestamp: repairPlan.createdAt,
      requestId: null,
      artifactPath: repairPlan.repairPlanPath,
      metadata: {
        steps: repairPlan.steps.map((step) => ({
          checkId: step.checkId,
          checkName: step.checkName,
          summary: step.summary,
        })),
      },
    },
  ];
}

function stateStepStatus(status: string): GenerationTraceStatus {
  if (status === 'success' || status === 'skipped') return 'success';
  if (status === 'warning') return 'warning';
  if (status === 'failed') return 'error';
  if (status === 'running' || status === 'pending') return 'pending';
  return 'unknown';
}

function buildGenerationStateEvents(projectId: string, state: QuantGenerationState | null): GenerationTimelineEvent[] {
  if (!state) return [];
  return state.steps
    .filter((step) => step.startedAt || step.completedAt || step.summary)
    .map((step) => ({
      id: `generation-state:${projectId}:${state.requestId}:${step.id}`,
      projectId,
      source: 'workspace_event',
      stage: step.id === 'request_received'
        ? 'request'
        : step.id === 'planning'
          ? 'planning'
          : step.id === 'data_prefetch'
            ? 'data'
            : step.id === 'agent_execution'
              ? 'artifact'
              : step.id === 'validation' || step.id === 'final_validation'
                ? 'validation'
                : step.id === 'repair'
                  ? 'repair'
                  : 'completion',
      status: stateStepStatus(step.status),
      title: `状态机：${step.label}`,
      summary: compact(step.summary || step.status),
      timestamp: step.completedAt ?? step.startedAt ?? state.updatedAt,
      requestId: state.requestId,
      artifactPath: QUANT_GENERATION_STATE_RELATIVE_PATH,
      metadata: {
        runStatus: state.status,
        stepStatus: step.status,
        activeStep: state.activeStep,
        repairAttemptCount: state.repairAttemptCount,
        ...(step.metadata ?? {}),
      },
    }));
}

function queueStatusToTrace(status: string): GenerationTraceStatus {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'error';
  if (status === 'cancelled') return 'warning';
  if (status === 'queued' || status === 'running') return 'pending';
  return 'unknown';
}

function buildGenerationQueueEvents(projectId: string, queue: QuantGenerationQueueState | null): GenerationTimelineEvent[] {
  if (!queue) return [];
  return queue.items.slice(0, 20).flatMap((item) => {
    const events: GenerationTimelineEvent[] = [
      {
        id: `generation-queue:${projectId}:${item.requestId}:queued`,
        projectId,
        source: 'workspace_event',
        stage: 'request',
        status: item.status === 'queued' ? 'pending' : 'success',
        title: '队列：已入队',
        summary: compact(item.instructionPreview || '生成任务已进入队列'),
        timestamp: item.queuedAt,
        requestId: item.requestId,
        artifactPath: QUANT_GENERATION_QUEUE_RELATIVE_PATH,
        metadata: {
          queueStatus: item.status,
          cliPreference: item.cliPreference,
          selectedModel: item.selectedModel,
        },
      },
    ];
    if (item.startedAt) {
      events.push({
        id: `generation-queue:${projectId}:${item.requestId}:started`,
        projectId,
        source: 'workspace_event',
        stage: 'tooling',
        status: item.status === 'running' ? 'pending' : 'success',
        title: '队列：开始执行',
        summary: '生成任务从队列取出并开始执行。',
        timestamp: item.startedAt,
        requestId: item.requestId,
        artifactPath: QUANT_GENERATION_QUEUE_RELATIVE_PATH,
        metadata: {
          queueStatus: item.status,
        },
      });
    }
    if (item.completedAt) {
      events.push({
        id: `generation-queue:${projectId}:${item.requestId}:finished`,
        projectId,
        source: 'workspace_event',
        stage: item.status === 'completed' ? 'completion' : 'system',
        status: queueStatusToTrace(item.status),
        title: '队列：执行结束',
        summary: item.errorMessage ? compact(item.errorMessage) : `生成任务状态：${item.status}`,
        timestamp: item.completedAt,
        requestId: item.requestId,
        artifactPath: QUANT_GENERATION_QUEUE_RELATIVE_PATH,
        metadata: {
          queueStatus: item.status,
        },
      });
    }
    return events;
  });
}

function buildArtifactContractEvents(projectId: string, report: QuantArtifactContractReport | null): GenerationTimelineEvent[] {
  if (!report) return [];
  return [
    {
      id: `artifact-contracts:${projectId}:${report.updatedAt}`,
      projectId,
      source: 'validation',
      stage: 'validation',
      status: report.status === 'passed' ? 'success' : report.status === 'warning' ? 'warning' : 'error',
      title: '产物 Schema 契约',
      summary: report.passed
        ? `契约检查通过，${report.checks.length} 项结构检查完成。`
        : `契约检查未通过：${report.checks.filter((check) => check.status === 'failed').length} 项失败。`,
      timestamp: report.updatedAt,
      requestId: report.requestId ?? null,
      artifactPath: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
      metadata: {
        failed: report.checks.filter((check) => check.status === 'failed').map((check) => check.id),
        warnings: report.checks.filter((check) => check.status === 'warning').map((check) => check.id),
      },
    },
  ];
}

function buildVisualValidationEvents(projectId: string, report: QuantVisualValidationReport | null): GenerationTimelineEvent[] {
  if (!report) return [];
  return [
    {
      id: `visual-validation:${projectId}:${report.updatedAt}`,
      projectId,
      source: 'validation',
      stage: 'validation',
      status: report.status === 'passed' ? 'success' : report.status === 'warning' ? 'warning' : 'error',
      title: '视觉验收',
      summary: report.passed
        ? `视觉验收通过，覆盖 ${report.viewports.length} 个视口。`
        : `视觉验收未通过：${report.failures.length} 个阻断项。`,
      timestamp: report.updatedAt,
      requestId: report.requestId ?? null,
      artifactPath: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
      metadata: {
        screenshots: report.viewports.map((viewport) => viewport.screenshotPath),
        failures: report.failures,
        warnings: report.warnings,
      },
    },
  ];
}

function dedupeTimeline(events: GenerationTimelineEvent[]) {
  const seen = new Set<string>();
  return events
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime() || a.id.localeCompare(b.id))
    .filter((event) => {
      const key = [event.source, event.stage, event.title, event.summary, event.timestamp, event.artifactPath].join('|');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(-MAX_TIMELINE_EVENTS);
}

function buildStages(timeline: GenerationTimelineEvent[]): GenerationTraceStage[] {
  return STAGES.map((stage) => {
    const events = timeline.filter((event) => event.stage === stage.id);
    const latestStatus = events.at(-1)?.status ?? 'unknown';
    return {
      id: stage.id,
      label: stage.label,
      status: events.length ? latestStatus : 'unknown',
      eventCount: events.length,
      lastEventAt: events.at(-1)?.timestamp ?? null,
    };
  });
}

function isSuccessCheckpoint(event: GenerationTimelineEvent) {
  return event.status === 'success' && (event.stage === 'validation' || event.stage === 'completion');
}

function getCurrentIssueWindow(timeline: GenerationTimelineEvent[]) {
  const checkpointIndex = timeline.findLastIndex(isSuccessCheckpoint);
  return checkpointIndex >= 0 ? timeline.slice(checkpointIndex + 1) : timeline;
}

function isRepairPlanCurrent(repairPlan: QuantValidationRepairPlan | null, validationReport: QuantValidationReport | null) {
  if (!repairPlan?.steps.length) return false;
  if (!validationReport?.passed) return true;
  const repairCreatedAt = new Date(repairPlan.createdAt).getTime();
  const validationUpdatedAt = new Date(validationReport.updatedAt ?? validationReport.createdAt).getTime();
  return Number.isFinite(repairCreatedAt) && Number.isFinite(validationUpdatedAt) && repairCreatedAt > validationUpdatedAt;
}

function buildTopTools(project: ProjectWithTraceSources): GenerationTraceProject['topTools'] {
  const grouped = new Map<string, { count: number; errorCount: number; durationTotal: number; durationCount: number }>();
  for (const tool of project.toolUsages) {
    const item = grouped.get(tool.toolName) ?? { count: 0, errorCount: 0, durationTotal: 0, durationCount: 0 };
    item.count += 1;
    if (tool.error) item.errorCount += 1;
    if (tool.durationMs !== null) {
      item.durationTotal += tool.durationMs;
      item.durationCount += 1;
    }
    grouped.set(tool.toolName, item);
  }
  return [...grouped.entries()]
    .map(([name, item]) => ({
      name,
      count: item.count,
      errorCount: item.errorCount,
      averageDurationMs: item.durationCount ? Math.round(item.durationTotal / item.durationCount) : null,
    }))
    .sort((a, b) => b.count - a.count || b.errorCount - a.errorCount)
    .slice(0, 8);
}

function buildTraceSummary(params: {
  status: GenerationTraceStatus;
  errorCount: number;
  warningCount: number;
  pendingCount: number;
  latestEvent: GenerationTimelineEvent | null;
  validationPassed: boolean | null;
  repairStepCount: number;
}) {
  if (params.status === 'error') return `${params.errorCount || 1} 个当前错误事件阻断生成链路。`;
  if (params.repairStepCount) return `验证修复计划待处理：${params.repairStepCount} 步。`;
  if (params.status === 'warning') return `${params.warningCount || 1} 个当前风险事件需要关注。`;
  if (params.pendingCount) return '链路中仍有 pending 阶段，建议确认 Agent 是否仍在执行。';
  if (params.validationPassed === true) return '生成、产物和验证链路已闭环。';
  if (params.latestEvent) return `最近停在「${params.latestEvent.title}」。`;
  return '暂无可观测事件，需要先触发一次生成或验证。';
}

function buildNextActions(params: {
  timeline: GenerationTimelineEvent[];
  currentTimeline: GenerationTimelineEvent[];
  validation: GenerationTraceProject['validation'];
  repairPlan: GenerationTraceProject['repairPlan'];
  runPlanStatus: string | null;
}) {
  const actions: string[] = [];
  const latestError = [...params.currentTimeline].reverse().find((event) => event.status === 'error');
  const pending = [...params.currentTimeline].reverse().find((event) => event.status === 'pending');

  if (latestError) {
    actions.push(`优先处理 ${latestError.title}：${latestError.summary}`);
  }
  if (params.repairPlan.needed) {
    actions.push(`执行 ${params.repairPlan.path ?? '.quantpilot/validation-repair-plan.json'} 中的 ${params.repairPlan.stepCount} 个修复步骤。`);
  }
  if (params.validation.passed === false) {
    actions.push('修复后重新运行自动验证，确认 validation.json 变为通过。');
  } else if (params.validation.passed === null) {
    actions.push('补一次自动验证，把生成结果纳入平台质量门禁。');
  }
  if (params.runPlanStatus === 'needs_clarification') {
    actions.push('先补齐用户意图澄清问题，再继续执行生成链路。');
  }
  if (pending && !latestError) {
    actions.push(`确认 pending 阶段是否仍在运行：${pending.title}。`);
  }
  if (!actions.length) {
    actions.push('链路状态正常，后续变更后继续观察验证和修复事件。');
  }
  return actions.slice(0, 4);
}

async function inspectProjectTrace(project: ProjectWithTraceSources): Promise<GenerationTraceProject> {
  const projectPath = resolveProjectPath(project);
  const [workspaceEvents, runPlan, validationReport, repairPlan, generationState, generationQueue, artifactContracts, visualValidation] = await Promise.all([
    readWorkspaceEvents(projectPath),
    readQuantRunPlan(projectPath),
    readQuantValidationReport(projectPath),
    readQuantValidationRepairPlan(projectPath),
    readQuantGenerationState(projectPath),
    readQuantGenerationQueue(projectPath, project.id),
    readQuantArtifactContractReport(projectPath),
    readQuantVisualValidationReport(projectPath),
  ]);
  const timeline = dedupeTimeline([
    ...buildUserRequestEvents(project),
    ...buildMessageEvents(project),
    ...buildToolEvents(project),
    ...buildWorkspaceEvents(project.id, workspaceEvents),
    ...buildRunPlanEvent(project.id, runPlan),
    ...buildValidationEvent(project.id, validationReport),
    ...buildRepairEvent(project.id, repairPlan),
    ...buildGenerationStateEvents(project.id, generationState),
    ...buildGenerationQueueEvents(project.id, generationQueue),
    ...buildArtifactContractEvents(project.id, artifactContracts),
    ...buildVisualValidationEvents(project.id, visualValidation),
  ]);
  const latestEvent = timeline.at(-1) ?? null;
  const validation = {
    status: validationReport ? (validationReport.passed ? 'success' : 'error') : 'unknown',
    passed: validationReport?.passed ?? null,
    updatedAt: validationReport?.updatedAt ?? validationReport?.createdAt ?? null,
    failedChecks: validationReport?.checks.filter((check) => check.status === 'failed').length ?? 0,
    warningChecks: validationReport?.checks.filter((check) => check.status === 'warning').length ?? 0,
  } satisfies GenerationTraceProject['validation'];
  const currentTimeline = getCurrentIssueWindow(timeline);
  const historicalErrorCount = timeline.filter((event) => event.status === 'error').length;
  const historicalWarningCount = timeline.filter((event) => event.status === 'warning').length;
  const historicalPendingCount = timeline.filter((event) => event.status === 'pending').length;
  const currentErrorCount = currentTimeline.filter((event) => event.status === 'error').length;
  const currentWarningCount = currentTimeline.filter((event) => event.status === 'warning').length;
  const currentPendingCount = currentTimeline.filter((event) => event.status === 'pending').length;
  const repairPlanNeeded = isRepairPlanCurrent(repairPlan, validationReport);
  const repair = {
    needed: repairPlanNeeded,
    stepCount: repairPlan?.steps.length ?? 0,
    path: repairPlan?.repairPlanPath ?? null,
    createdAt: repairPlan?.createdAt ?? null,
  };
  const queueSummary = {
    activeRequestId: generationQueue.activeRequestId,
    running: generationQueue.items.filter((item) => item.status === 'running').length,
    queued: generationQueue.items.filter((item) => item.status === 'queued').length,
    failed: generationQueue.items.filter((item) => item.status === 'failed').length,
    updatedAt: generationQueue.updatedAt ?? null,
    path: QUANT_GENERATION_QUEUE_RELATIVE_PATH,
    items: generationQueue.items.slice(0, 12).map((item) => ({
      requestId: item.requestId,
      status: item.status,
      cliPreference: item.cliPreference,
      selectedModel: item.selectedModel,
      instructionPreview: item.instructionPreview,
      queuedAt: item.queuedAt,
      startedAt: item.startedAt,
      completedAt: item.completedAt,
      errorMessage: item.errorMessage,
    })),
  };
  const contractsSummary = {
    status: artifactContracts
      ? artifactContracts.status === 'passed'
        ? 'success'
        : artifactContracts.status === 'warning'
          ? 'warning'
          : 'error'
      : 'unknown',
    passed: artifactContracts?.passed ?? null,
    failedChecks: artifactContracts?.checks.filter((check) => check.status === 'failed').length ?? 0,
    warningChecks: artifactContracts?.checks.filter((check) => check.status === 'warning').length ?? 0,
    updatedAt: artifactContracts?.updatedAt ?? null,
    path: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
    checks: artifactContracts?.checks.map((check) => ({
      id: check.id,
      label: check.label,
      path: check.path,
      required: check.required,
      status: check.status,
      summary: check.summary,
      details: check.details,
    })) ?? [],
  } satisfies GenerationTraceProject['artifactContracts'];
  const visualSummary = {
    status: visualValidation
      ? visualValidation.status === 'passed'
        ? 'success'
        : visualValidation.status === 'warning'
          ? 'warning'
          : 'error'
      : 'unknown',
    passed: visualValidation?.passed ?? null,
    failedChecks: visualValidation?.failures.length ?? 0,
    warningChecks: visualValidation?.warnings.length ?? 0,
    updatedAt: visualValidation?.updatedAt ?? null,
    path: QUANT_VISUAL_VALIDATION_RELATIVE_PATH,
    screenshots: visualValidation?.viewports.map((viewport) => viewport.screenshotPath) ?? [],
    previewUrl: visualValidation?.previewUrl ?? null,
    viewports: visualValidation?.viewports.map((viewport) => ({
      id: viewport.id,
      width: viewport.width,
      height: viewport.height,
      screenshotPath: viewport.screenshotPath,
      status: viewport.status,
      failures: viewport.failures,
      warnings: viewport.warnings,
    })) ?? [],
    failures: visualValidation?.failures ?? [],
    warnings: visualValidation?.warnings ?? [],
  } satisfies GenerationTraceProject['visualValidation'];
  const traceStatus: GenerationTraceStatus =
    validation.passed === false || currentErrorCount || contractsSummary.status === 'error' || visualSummary.status === 'error'
      ? 'error'
      : repair.needed || currentWarningCount || contractsSummary.status === 'warning' || visualSummary.status === 'warning'
        ? 'warning'
        : currentPendingCount || project.status === 'running' || queueSummary.running + queueSummary.queued > 0
          ? 'pending'
          : timeline.length
            ? 'success'
            : 'unknown';
  const activeStage =
    [...currentTimeline].reverse().find((event) => event.status === 'error' || event.status === 'warning' || event.status === 'pending')?.stage ??
    latestEvent?.stage ??
    'system';
  const latestRequestRaw = project.userRequests[0] ?? null;
  const requestCount = project.userRequests.length;
  const toolCallCount = project.toolUsages.length;
  const projectTrace: GenerationTraceProject = {
    id: project.id,
    name: project.name,
    description: project.description ?? null,
    status: project.status,
    repoPath: path.relative(ROOT, projectPath),
    preferredCli: project.preferredCli ?? null,
    selectedModel: project.selectedModel ?? null,
    previewUrl: project.previewUrl ?? null,
    createdAt: project.createdAt.toISOString(),
    updatedAt: project.updatedAt.toISOString(),
    lastActiveAt: project.lastActiveAt?.toISOString() ?? null,
    trace: {
      status: traceStatus,
      summary: buildTraceSummary({
        status: traceStatus,
        errorCount: currentErrorCount,
        warningCount: currentWarningCount,
        pendingCount: currentPendingCount,
        latestEvent,
        validationPassed: validation.passed,
        repairStepCount: repair.needed ? repair.stepCount : 0,
      }),
      activeStage,
      lastEventAt: latestEvent?.timestamp ?? null,
      eventCount: timeline.length,
      errorCount: historicalErrorCount,
      warningCount: historicalWarningCount,
      pendingCount: historicalPendingCount,
      requestCount,
      toolCallCount,
      validationPassed: validation.passed,
      repairStepCount: repair.needed ? repair.stepCount : 0,
    },
    runPlan: {
      status: runPlan?.status ?? null,
      capabilityId: runPlan?.capabilityId ?? null,
      requestedCapabilityId: runPlan?.requestedCapabilityId ?? null,
      executionCapabilityId: runPlan?.executionCapabilityId ?? null,
      symbols: runPlan?.symbols ?? [],
      expectedArtifacts: runPlan?.expectedArtifacts ?? [],
      updatedAt: runPlan?.updatedAt ?? null,
    },
    stages: buildStages(timeline),
    timeline,
    generationState: generationState
      ? {
          status: generationState.status,
          activeStep: generationState.activeStep,
          repairAttemptCount: generationState.repairAttemptCount,
          maxRepairAttempts: generationState.maxRepairAttempts,
          updatedAt: generationState.updatedAt,
          path: QUANT_GENERATION_STATE_RELATIVE_PATH,
          steps: generationState.steps.map((step) => ({
            id: step.id,
            label: step.label,
            status: step.status,
            startedAt: step.startedAt,
            completedAt: step.completedAt,
            summary: step.summary,
          })),
          error: generationState.error,
        }
      : null,
    generationQueue: queueSummary,
    artifactContracts: contractsSummary,
    visualValidation: visualSummary,
    latestRequest: latestRequestRaw
      ? {
          id: latestRequestRaw.id,
          status: latestRequestRaw.status,
          instruction: latestRequestRaw.instruction,
          createdAt: latestRequestRaw.createdAt.toISOString(),
          completedAt: latestRequestRaw.completedAt?.toISOString() ?? null,
          errorMessage: latestRequestRaw.errorMessage,
        }
      : null,
    validation,
    repairPlan: repair,
    topTools: buildTopTools(project),
    nextActions: buildNextActions({
      timeline,
      currentTimeline,
      validation,
      repairPlan: repair,
      runPlanStatus: runPlan?.status ?? null,
    }),
  };

  return projectTrace;
}

export async function getGenerationObservabilityDashboard(): Promise<GenerationObservabilityDashboard> {
  const projects = await loadProjectsWithTraceSources();
  const items = await Promise.all(projects.map((project) => inspectProjectTrace(project)));
  const dayAgo = Date.now() - 24 * 60 * 60 * 1_000;
  const summary = items.reduce(
    (acc, project) => {
      acc.total += 1;
      if (project.trace.status === 'success') acc.healthy += 1;
      if (project.trace.status === 'warning') acc.warning += 1;
      if (project.trace.status === 'error') acc.failed += 1;
      if (project.trace.status === 'pending') acc.running += 1;
      if (project.trace.status === 'unknown') acc.unknown += 1;
      acc.toolCalls += project.trace.toolCallCount;
      acc.requests += project.trace.requestCount;
      acc.eventsLast24h += project.timeline.filter((event) => new Date(event.timestamp).getTime() >= dayAgo).length;
      return acc;
    },
    { total: 0, healthy: 0, warning: 0, failed: 0, running: 0, unknown: 0, eventsLast24h: 0, toolCalls: 0, requests: 0 }
  );

  return {
    generatedAt: new Date().toISOString(),
    projectsDir: path.relative(ROOT, PROJECTS_DIR_ABSOLUTE),
    summary,
    projects: items.sort((a, b) => {
      const statusDiff = statusRank(b.trace.status) - statusRank(a.trace.status);
      if (statusDiff) return statusDiff;
      return (b.trace.lastEventAt ?? b.updatedAt).localeCompare(a.trace.lastEventAt ?? a.updatedAt);
    }),
  };
}
