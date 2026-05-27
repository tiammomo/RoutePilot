import fs from 'fs/promises';
import path from 'path';
import { QUANT_GENERATION_STATE_RELATIVE_PATH } from '@/lib/quant/artifacts';
import { appendQuantWorkspaceEvent } from '@/lib/quant/workspace';

export type QuantGenerationStepId =
  | 'request_received'
  | 'planning'
  | 'data_prefetch'
  | 'agent_execution'
  | 'validation'
  | 'repair'
  | 'final_validation'
  | 'completed';

export type QuantGenerationStepStatus = 'pending' | 'running' | 'success' | 'warning' | 'failed' | 'skipped';

export type QuantGenerationRunStatus =
  | 'pending'
  | 'running'
  | 'needs_clarification'
  | 'repairing'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface QuantGenerationStep {
  id: QuantGenerationStepId;
  label: string;
  status: QuantGenerationStepStatus;
  startedAt: string | null;
  completedAt: string | null;
  summary: string;
  metadata?: Record<string, unknown>;
}

export interface QuantGenerationState {
  schemaVersion: 1;
  projectId: string;
  requestId: string;
  status: QuantGenerationRunStatus;
  activeStep: QuantGenerationStepId;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  originalInstruction: string;
  cliPreference: string | null;
  selectedModel: string | null;
  repairAttemptCount: number;
  maxRepairAttempts: number;
  steps: QuantGenerationStep[];
  error: {
    step: QuantGenerationStepId;
    message: string;
  } | null;
}

const DEFAULT_MAX_REPAIR_ATTEMPTS =
  Number.parseInt(process.env.QUANTPILOT_MAX_VALIDATION_REPAIR_ATTEMPTS ?? '', 10) || 1;

const STEP_LABELS: Record<QuantGenerationStepId, string> = {
  request_received: '接收请求',
  planning: '生成计划',
  data_prefetch: '数据预取',
  agent_execution: 'Agent 执行',
  validation: '自动验证',
  repair: '自动修复',
  final_validation: '修复后验证',
  completed: '完成',
};

function nowIso() {
  return new Date().toISOString();
}

function statePath(projectPath: string) {
  return path.join(projectPath, QUANT_GENERATION_STATE_RELATIVE_PATH);
}

function initialSteps(): QuantGenerationStep[] {
  return (Object.keys(STEP_LABELS) as QuantGenerationStepId[]).map((id) => ({
    id,
    label: STEP_LABELS[id],
    status: id === 'request_received' ? 'running' : 'pending',
    startedAt: id === 'request_received' ? nowIso() : null,
    completedAt: null,
    summary: '',
  }));
}

async function readState(projectPath: string): Promise<QuantGenerationState | null> {
  const content = await fs.readFile(statePath(projectPath), 'utf8').catch(() => null);
  if (!content) return null;
  try {
    const parsed = JSON.parse(content) as QuantGenerationState;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

async function writeState(projectPath: string, state: QuantGenerationState) {
  const filePath = statePath(projectPath);
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
}

function mergeStep(
  state: QuantGenerationState,
  stepId: QuantGenerationStepId,
  status: QuantGenerationStepStatus,
  summary: string,
  metadata?: Record<string, unknown>
) {
  const timestamp = nowIso();
  let found = false;
  const steps = state.steps.map((step) => {
    if (step.id !== stepId) return step;
    found = true;
    return {
      ...step,
      status,
      startedAt: step.startedAt ?? timestamp,
      completedAt: ['success', 'warning', 'failed', 'skipped'].includes(status) ? timestamp : step.completedAt,
      summary,
      ...(metadata ? { metadata: { ...(step.metadata ?? {}), ...metadata } } : {}),
    };
  });

  if (!found) {
    steps.push({
      id: stepId,
      label: STEP_LABELS[stepId],
      status,
      startedAt: timestamp,
      completedAt: ['success', 'warning', 'failed', 'skipped'].includes(status) ? timestamp : null,
      summary,
      ...(metadata ? { metadata } : {}),
    });
  }

  return steps;
}

function deriveRunStatus(params: {
  previous: QuantGenerationRunStatus;
  stepId: QuantGenerationStepId;
  stepStatus: QuantGenerationStepStatus;
  runStatus?: QuantGenerationRunStatus;
}) {
  if (params.runStatus) return params.runStatus;
  if (params.stepStatus === 'failed') return 'failed';
  if (params.stepId === 'repair' && params.stepStatus === 'running') return 'repairing';
  if (params.stepId === 'completed' && params.stepStatus === 'success') return 'completed';
  if (params.previous === 'needs_clarification') return params.previous;
  return 'running';
}

export async function startQuantGenerationRun(params: {
  projectPath: string;
  projectId: string;
  requestId: string;
  instruction: string;
  cliPreference?: string | null;
  selectedModel?: string | null;
  maxRepairAttempts?: number;
}) {
  const timestamp = nowIso();
  const state: QuantGenerationState = {
    schemaVersion: 1,
    projectId: params.projectId,
    requestId: params.requestId,
    status: 'running',
    activeStep: 'request_received',
    createdAt: timestamp,
    updatedAt: timestamp,
    completedAt: null,
    originalInstruction: params.instruction,
    cliPreference: params.cliPreference ?? null,
    selectedModel: params.selectedModel ?? null,
    repairAttemptCount: 0,
    maxRepairAttempts: params.maxRepairAttempts ?? DEFAULT_MAX_REPAIR_ATTEMPTS,
    steps: initialSteps(),
    error: null,
  };
  await writeState(params.projectPath, state);
  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'generation_state_started',
    stage: 'state_machine',
    status: 'pending',
    run_id: params.requestId,
    artifact_path: QUANT_GENERATION_STATE_RELATIVE_PATH,
    summary: '生成状态机已启动。',
    created_at: timestamp,
  });
  return state;
}

export async function updateQuantGenerationStep(params: {
  projectPath: string;
  projectId: string;
  requestId: string;
  stepId: QuantGenerationStepId;
  status: QuantGenerationStepStatus;
  summary: string;
  metadata?: Record<string, unknown>;
  runStatus?: QuantGenerationRunStatus;
  errorMessage?: string | null;
}) {
  const existing = await readState(params.projectPath);
  const timestamp = nowIso();
  const state: QuantGenerationState =
    existing?.requestId === params.requestId
      ? existing
      : {
          schemaVersion: 1,
          projectId: params.projectId,
          requestId: params.requestId,
          status: 'running',
          activeStep: params.stepId,
          createdAt: timestamp,
          updatedAt: timestamp,
          completedAt: null,
          originalInstruction: '',
          cliPreference: null,
          selectedModel: null,
          repairAttemptCount: 0,
          maxRepairAttempts: DEFAULT_MAX_REPAIR_ATTEMPTS,
          steps: initialSteps(),
          error: null,
        };

  const nextStatus = deriveRunStatus({
    previous: state.status,
    stepId: params.stepId,
    stepStatus: params.status,
    runStatus: params.runStatus,
  });
  const nextState: QuantGenerationState = {
    ...state,
    status: nextStatus,
    activeStep: params.stepId,
    updatedAt: timestamp,
    completedAt: ['completed', 'failed', 'cancelled'].includes(nextStatus) ? timestamp : null,
    steps: mergeStep(state, params.stepId, params.status, params.summary, params.metadata),
    error:
      params.errorMessage || params.status === 'failed'
        ? {
            step: params.stepId,
            message: params.errorMessage ?? params.summary,
          }
        : nextStatus === 'completed'
          ? null
          : state.error,
  };

  await writeState(params.projectPath, nextState);
  await appendQuantWorkspaceEvent(params.projectPath, {
    event_type: 'generation_state_updated',
    stage: params.stepId,
    status: params.status === 'failed' ? 'error' : params.status === 'warning' ? 'warning' : params.status === 'running' ? 'pending' : 'success',
    run_id: params.requestId,
    artifact_path: QUANT_GENERATION_STATE_RELATIVE_PATH,
    summary: `${STEP_LABELS[params.stepId]}：${params.summary}`,
    created_at: timestamp,
  });
  return nextState;
}

export async function incrementQuantGenerationRepairAttempt(params: {
  projectPath: string;
  projectId: string;
  requestId: string;
}) {
  const existing = await readState(params.projectPath);
  if (!existing || existing.requestId !== params.requestId) {
    await updateQuantGenerationStep({
      projectPath: params.projectPath,
      projectId: params.projectId,
      requestId: params.requestId,
      stepId: 'repair',
      status: 'running',
      summary: '开始自动修复。',
      runStatus: 'repairing',
    });
  }
  const state = (await readState(params.projectPath))!;
  const nextState = {
    ...state,
    repairAttemptCount: state.repairAttemptCount + 1,
    updatedAt: nowIso(),
  };
  await writeState(params.projectPath, nextState);
  return nextState.repairAttemptCount;
}

export async function readQuantGenerationState(projectPath: string) {
  return readState(projectPath);
}
