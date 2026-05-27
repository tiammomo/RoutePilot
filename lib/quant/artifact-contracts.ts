import fs from 'fs/promises';
import path from 'path';
import { z } from 'zod';
import { QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH } from '@/lib/quant/artifacts';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace } from '@/lib/quant/workspace';

export type QuantArtifactContractStatus = 'passed' | 'failed' | 'warning';

export interface QuantArtifactContractCheck {
  id: string;
  label: string;
  path: string;
  required: boolean;
  status: QuantArtifactContractStatus;
  summary: string;
  details?: string;
}

export interface QuantArtifactContractReport {
  schemaVersion: 1;
  projectId: string;
  requestId?: string | null;
  status: QuantArtifactContractStatus;
  passed: boolean;
  reportPath: string;
  checks: QuantArtifactContractCheck[];
  createdAt: string;
  updatedAt: string;
}

type JsonRecord = Record<string, unknown>;

type ContractDefinition = {
  id: string;
  label: string;
  relativePath: string;
  required: boolean;
  schema: z.ZodType<unknown>;
  extraValidate?: (value: unknown) => string[];
};

const optionalString = z.string().nullable().optional();
const nonEmptyString = z.string().trim().min(1);
const statusString = z.string().trim().min(1);

const runPlanSchema = z.object({
  schemaVersion: z.literal(1),
  runId: nonEmptyString,
  status: z.enum(['pending', 'planned', 'needs_clarification']),
  capabilityId: nonEmptyString,
  question: nonEmptyString,
  symbols: z.array(z.string()),
  timeRange: optionalString,
  dataRequirements: z.array(z.string()),
  analysisSteps: z.array(z.string()),
  visualization: z.object({
    required: z.boolean(),
    templateId: z.string().optional(),
    panels: z.array(z.string()),
  }).passthrough(),
  expectedArtifacts: z.array(z.string()),
  validationRules: z.array(z.string()),
  createdAt: nonEmptyString,
  updatedAt: nonEmptyString,
}).passthrough();

const generationStateSchema = z.object({
  schemaVersion: z.literal(1),
  projectId: nonEmptyString,
  requestId: nonEmptyString,
  status: z.enum(['pending', 'running', 'needs_clarification', 'repairing', 'completed', 'failed', 'cancelled']),
  activeStep: nonEmptyString,
  createdAt: nonEmptyString,
  updatedAt: nonEmptyString,
  completedAt: optionalString,
  originalInstruction: z.string(),
  cliPreference: optionalString,
  selectedModel: optionalString,
  repairAttemptCount: z.number().int().min(0),
  maxRepairAttempts: z.number().int().min(0),
  steps: z.array(z.object({
    id: nonEmptyString,
    label: nonEmptyString,
    status: z.enum(['pending', 'running', 'success', 'warning', 'failed', 'skipped']),
    startedAt: optionalString,
    completedAt: optionalString,
    summary: z.string(),
    metadata: z.record(z.string(), z.unknown()).optional(),
  }).passthrough()).min(1),
  error: z.object({
    step: nonEmptyString,
    message: nonEmptyString,
  }).nullable(),
}).passthrough();

const validationSchema = z.object({
  schemaVersion: z.literal(1),
  status: z.enum(['passed', 'failed']),
  passed: z.boolean(),
  projectId: nonEmptyString,
  reportPath: nonEmptyString,
  checks: z.array(z.object({
    id: nonEmptyString,
    name: nonEmptyString,
    status: z.enum(['passed', 'failed', 'warning']),
    summary: z.string(),
  }).passthrough()),
  createdAt: nonEmptyString,
  updatedAt: nonEmptyString,
}).passthrough();

const queueSchema = z.object({
  schemaVersion: z.literal(1),
  projectId: nonEmptyString,
  activeRequestId: optionalString,
  updatedAt: nonEmptyString,
  items: z.array(z.object({
    id: nonEmptyString,
    projectId: nonEmptyString,
    requestId: nonEmptyString,
    status: z.enum(['queued', 'running', 'completed', 'failed', 'cancelled']),
    cliPreference: optionalString,
    selectedModel: optionalString,
    instructionPreview: z.string(),
    queuedAt: nonEmptyString,
    startedAt: optionalString,
    completedAt: optionalString,
    errorMessage: optionalString,
  }).passthrough()),
}).passthrough();

const visualValidationSchema = z.object({
  schemaVersion: z.literal(1),
  projectId: nonEmptyString,
  requestId: optionalString,
  status: z.enum(['passed', 'failed', 'warning']),
  passed: z.boolean(),
  previewUrl: nonEmptyString,
  reportPath: nonEmptyString,
  screenshotDir: nonEmptyString,
  viewports: z.array(z.object({
    id: z.enum(['desktop', 'mobile']),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    screenshotPath: nonEmptyString,
    status: z.enum(['passed', 'failed', 'warning']),
    failures: z.array(z.string()),
    warnings: z.array(z.string()),
    metrics: z.record(z.string(), z.unknown()),
  }).passthrough()).min(1),
  failures: z.array(z.string()),
  warnings: z.array(z.string()),
  createdAt: nonEmptyString,
  updatedAt: nonEmptyString,
}).passthrough();

const sourcesSchema = z.object({
  sources: z.array(z.object({
    source: statusString,
    endpoint: statusString,
    artifact_path: statusString,
  }).passthrough()).min(1),
}).passthrough();

const dataQualitySchema = z.object({
  status: z.enum(['ok', 'warning', 'error']),
}).passthrough();

const dashboardDataSchema = z.record(z.string(), z.unknown());

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function asRecord(value: unknown): JsonRecord | null {
  return isRecord(value) ? value : null;
}

function hasPresentValue(record: JsonRecord | null, keys: string[]) {
  return Boolean(
    record &&
      keys.some((key) => {
        const value = record[key];
        if (value === null || value === undefined) return false;
        return typeof value !== 'string' || value.trim().length > 0;
      })
  );
}

function hasArrayValue(record: JsonRecord | null, keys: string[]) {
  return Boolean(record && keys.some((key) => Array.isArray(record[key]) && (record[key] as unknown[]).length > 0));
}

function inspectDashboardData(value: unknown): string[] {
  const record = asRecord(value);
  const errors: string[] = [];
  if (!record || Object.keys(record).length === 0) {
    return ['dashboard-data.json 必须是非空对象。'];
  }

  const assets = Array.isArray(record.assets)
    ? record.assets.map(asRecord).filter((asset): asset is JsonRecord => Boolean(asset))
    : [];
  const targetRecords = assets.length ? assets : [record];
  const hasMarketPayload = targetRecords.some((item) => {
    const quote = asRecord(item.quote);
    const kline = asRecord(item.kline) ?? asRecord(item.history);
    return (
      hasPresentValue(item, ['symbol', 'name']) &&
      (hasPresentValue(quote, ['price', 'latest', 'latest_price', 'close']) ||
        hasArrayValue(kline, ['bars', 'data', 'items']) ||
        hasArrayValue(item, ['bars', 'history', 'klines', 'candles']))
    );
  });

  if (!hasMarketPayload) {
    errors.push('dashboard-data.json 至少需要包含标的和 quote.price 或 kline.bars/history 样本。');
  }

  const visualization = asRecord(record.visualization);
  if (visualization && !hasPresentValue(visualization, ['template_id', 'templateId'])) {
    errors.push('visualization 存在时必须声明 template_id/templateId。');
  }

  return errors;
}

function inspectRunPlan(value: unknown) {
  const record = asRecord(value);
  const expectedArtifacts = Array.isArray(record?.expectedArtifacts) ? record.expectedArtifacts : [];
  const errors: string[] = [];
  [
    '.quantpilot/run_plan.json',
    '.quantpilot/generation-state.json',
    '.quantpilot/generation-queue.json',
    '.quantpilot/events.jsonl',
    '.quantpilot/artifact-contracts.json',
    '.quantpilot/visual-validation.json',
    '.quantpilot/validation.json',
    'evidence/sources.json',
    'evidence/data_quality.json',
    'data_file/final/dashboard-data.json',
    'app/page.tsx',
  ].forEach((artifact) => {
    if (!expectedArtifacts.includes(artifact)) {
      errors.push(`expectedArtifacts 缺少 ${artifact}。`);
    }
  });
  return errors;
}

function inspectGenerationState(value: unknown) {
  const record = asRecord(value);
  const steps = Array.isArray(record?.steps) ? record.steps.map(asRecord).filter(Boolean) : [];
  const requiredSteps = ['request_received', 'planning', 'data_prefetch', 'agent_execution', 'validation', 'repair', 'final_validation', 'completed'];
  const present = new Set(steps.map((step) => typeof step?.id === 'string' ? step.id : ''));
  return requiredSteps.filter((step) => !present.has(step)).map((step) => `steps 缺少 ${step}。`);
}

function inspectSources(value: unknown) {
  const sources = Array.isArray(asRecord(value)?.sources) ? asRecord(value)?.sources as unknown[] : [];
  return sources.flatMap((source, index) => {
    const record = asRecord(source);
    const errors: string[] = [];
    if (!hasPresentValue(record, ['source'])) errors.push(`sources[${index}].source 缺失。`);
    if (!hasPresentValue(record, ['endpoint'])) errors.push(`sources[${index}].endpoint 缺失。`);
    if (!hasPresentValue(record, ['artifact_path'])) errors.push(`sources[${index}].artifact_path 缺失。`);
    if (!hasPresentValue(record, ['fetched_at', 'as_of', 'quote_time'])) errors.push(`sources[${index}] 缺少 fetched_at/as_of/quote_time。`);
    return errors;
  });
}

function inspectDataQuality(value: unknown) {
  const record = asRecord(value);
  const errors: string[] = [];
  if (!hasArrayValue(record, ['datasets']) && !hasArrayValue(record, ['checks'])) {
    errors.push('data_quality.json 需要包含 datasets 或 checks。');
  }
  if (!hasArrayValue(record, ['warnings']) && !hasArrayValue(record, ['limitations']) && !JSON.stringify(value).match(/row_count|missing_fields|fetched_at/i)) {
    errors.push('data_quality.json 需要记录样本数、缺失字段、警告或限制。');
  }
  return errors;
}

const CONTRACTS: ContractDefinition[] = [
  {
    id: 'run_plan_contract',
    label: '运行计划契约',
    relativePath: '.quantpilot/run_plan.json',
    required: true,
    schema: runPlanSchema,
    extraValidate: inspectRunPlan,
  },
  {
    id: 'generation_state_contract',
    label: '生成状态契约',
    relativePath: '.quantpilot/generation-state.json',
    required: true,
    schema: generationStateSchema,
    extraValidate: inspectGenerationState,
  },
  {
    id: 'validation_contract',
    label: '验证报告契约',
    relativePath: '.quantpilot/validation.json',
    required: false,
    schema: validationSchema,
  },
  {
    id: 'generation_queue_contract',
    label: '生成队列契约',
    relativePath: '.quantpilot/generation-queue.json',
    required: false,
    schema: queueSchema,
  },
  {
    id: 'visual_validation_contract',
    label: '视觉验收契约',
    relativePath: '.quantpilot/visual-validation.json',
    required: false,
    schema: visualValidationSchema,
  },
  {
    id: 'sources_contract',
    label: '数据信源契约',
    relativePath: 'evidence/sources.json',
    required: true,
    schema: sourcesSchema,
    extraValidate: inspectSources,
  },
  {
    id: 'data_quality_contract',
    label: '数据质量契约',
    relativePath: 'evidence/data_quality.json',
    required: true,
    schema: dataQualitySchema,
    extraValidate: inspectDataQuality,
  },
  {
    id: 'dashboard_data_contract',
    label: '最终数据契约',
    relativePath: 'data_file/final/dashboard-data.json',
    required: true,
    schema: dashboardDataSchema,
    extraValidate: inspectDashboardData,
  },
];

async function readJson(projectPath: string, relativePath: string) {
  const absolutePath = path.join(projectPath, relativePath);
  const content = await fs.readFile(absolutePath, 'utf8').catch(() => null);
  if (!content) {
    return { ok: false as const, error: `缺少或为空：${relativePath}` };
  }
  try {
    return { ok: true as const, value: JSON.parse(content) as unknown };
  } catch (error) {
    return {
      ok: false as const,
      error: `JSON 解析失败：${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

function formatZodIssue(issue: z.core.$ZodIssue) {
  const pathLabel = issue.path.length ? issue.path.join('.') : '<root>';
  return `${pathLabel}: ${issue.message}`;
}

async function checkContract(projectPath: string, definition: ContractDefinition): Promise<QuantArtifactContractCheck> {
  const payload = await readJson(projectPath, definition.relativePath);
  if (!payload.ok) {
    return {
      id: definition.id,
      label: definition.label,
      path: definition.relativePath,
      required: definition.required,
      status: definition.required ? 'failed' : 'warning',
      summary: payload.error,
    };
  }

  const parsed = definition.schema.safeParse(payload.value);
  if (!parsed.success) {
    return {
      id: definition.id,
      label: definition.label,
      path: definition.relativePath,
      required: definition.required,
      status: 'failed',
      summary: `${definition.label}结构不符合契约。`,
      details: parsed.error.issues.slice(0, 12).map(formatZodIssue).join('\n'),
    };
  }

  const extraErrors = definition.extraValidate?.(payload.value) ?? [];
  if (extraErrors.length > 0) {
    return {
      id: definition.id,
      label: definition.label,
      path: definition.relativePath,
      required: definition.required,
      status: definition.required ? 'failed' : 'warning',
      summary: `${definition.label}缺少关键业务字段。`,
      details: extraErrors.slice(0, 16).join('\n'),
    };
  }

  return {
    id: definition.id,
    label: definition.label,
    path: definition.relativePath,
    required: definition.required,
    status: 'passed',
    summary: `${definition.label}通过。`,
  };
}

export async function validateQuantArtifactContracts(params: {
  projectPath: string;
  projectId: string;
  requestId?: string | null;
}): Promise<QuantArtifactContractReport> {
  const projectPath = path.resolve(params.projectPath);
  const now = new Date().toISOString();
  await ensureQuantWorkspace(projectPath);
  const checks = await Promise.all(CONTRACTS.map((definition) => checkContract(projectPath, definition)));
  const requiredFailures = checks.filter((check) => check.required && check.status === 'failed');
  const warnings = checks.filter((check) => check.status === 'warning');
  const status: QuantArtifactContractStatus = requiredFailures.length ? 'failed' : warnings.length ? 'warning' : 'passed';
  const report: QuantArtifactContractReport = {
    schemaVersion: 1,
    projectId: params.projectId,
    requestId: params.requestId ?? null,
    status,
    passed: status !== 'failed',
    reportPath: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
    checks,
    createdAt: now,
    updatedAt: now,
  };

  await fs.writeFile(
    path.join(projectPath, QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8'
  );
  await appendQuantWorkspaceEvent(projectPath, {
    event_type: 'artifact_contracts_checked',
    stage: 'validation',
    status: status === 'failed' ? 'error' : status === 'warning' ? 'warning' : 'success',
    run_id: params.requestId ?? undefined,
    artifact_path: QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH,
    summary: status === 'failed'
      ? `产物契约未通过：${requiredFailures.length} 个必需契约失败。`
      : status === 'warning'
        ? `产物契约通过但有 ${warnings.length} 个警告。`
        : '产物契约全部通过。',
    created_at: now,
  });
  return report;
}

export async function readQuantArtifactContractReport(projectPath: string): Promise<QuantArtifactContractReport | null> {
  const content = await fs.readFile(path.join(projectPath, QUANT_ARTIFACT_CONTRACTS_RELATIVE_PATH), 'utf8').catch(() => null);
  if (!content) return null;
  try {
    const parsed = JSON.parse(content);
    return parsed && typeof parsed === 'object' ? parsed as QuantArtifactContractReport : null;
  } catch {
    return null;
  }
}
