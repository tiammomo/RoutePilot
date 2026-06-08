/**
 * Claude Agent SDK Service - Claude Agent SDK Integration
 *
 * Interacts with projects using the Claude Agent SDK.
 */

import { query, type PermissionResult, type SDKMessage, type SDKUserMessage } from '@anthropic-ai/claude-agent-sdk';
import type { ClaudeSession, ClaudeResponse } from '@/types/backend';
import { streamManager } from '../stream';
import { serializeMessage, createRealtimeMessage } from '@/lib/serializers/chat';
import { updateProject, getProjectById } from '../project';
import { createMessage } from '../message';
import { CLAUDE_DEFAULT_MODEL, normalizeClaudeModelId, getClaudeModelDefinition, getClaudeModelDisplayName } from '@/lib/constants/cliModels';
import path from 'path';
import fs from 'fs/promises';
import { randomUUID } from 'crypto';
import {
  buildQuantPilotSystemPrompt,
  buildQuantPilotTaskPrompt,
  ensureClaudeSkillsForProject,
  readQuantPilotManifest,
} from '@/lib/services/claude-skills';
import {
  markUserRequestAsRunning,
  markUserRequestAsCompleted,
  markUserRequestAsFailed,
} from '@/lib/services/user-requests';

type ToolAction = 'Edited' | 'Created' | 'Read' | 'Deleted' | 'Generated' | 'Searched' | 'Executed';

type ClaudeImageAttachment = {
  name: string;
  path: string;
  url?: string;
  publicUrl?: string;
  mimeType?: string;
  size?: number;
};

const TOOL_NAME_ACTION_MAP: Record<string, ToolAction> = {
  read: 'Read',
  read_file: 'Read',
  'read-file': 'Read',
  write: 'Created',
  write_file: 'Created',
  'write-file': 'Created',
  create_file: 'Created',
  edit: 'Edited',
  edit_file: 'Edited',
  'edit-file': 'Edited',
  update_file: 'Edited',
  apply_patch: 'Edited',
  patch_file: 'Edited',
  remove_file: 'Deleted',
  delete_file: 'Deleted',
  delete: 'Deleted',
  remove: 'Deleted',
  list_files: 'Searched',
  list: 'Searched',
  ls: 'Searched',
  glob: 'Searched',
  glob_files: 'Searched',
  search_files: 'Searched',
  grep: 'Searched',
  bash: 'Executed',
  run: 'Executed',
  run_bash: 'Executed',
  shell: 'Executed',
  todo_write: 'Generated',
  todo: 'Generated',
  plan_write: 'Generated',
};

function readPositiveMsEnv(name: string, fallback: number): number {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

type TravelDashboardArtifactSnapshot = {
  complete: boolean;
  signature: string;
  summary: string;
};

async function statFileOrNull(filePath: string): Promise<{ size: number; mtimeMs: number } | null> {
  try {
    const stat = await fs.stat(filePath);
    if (!stat.isFile()) return null;
    return { size: stat.size, mtimeMs: stat.mtimeMs };
  } catch {
    return null;
  }
}

function hasMeaningfulJsonPayload(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }

  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }

  return false;
}

async function parseJsonFileOrNull(filePath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    return null;
  }
}

async function inspectTravelDashboardArtifacts(projectPath: string): Promise<TravelDashboardArtifactSnapshot> {
  const requiredFiles = [
    '.travelpilot/run_plan.json',
    'data_file/final/itinerary-data.json',
    'evidence/sources.json',
    'evidence/data_quality.json',
    'app/page.tsx',
  ];

  const stats = await Promise.all(
    requiredFiles.map(async (relativePath) => ({
      relativePath,
      stat: await statFileOrNull(path.join(projectPath, relativePath)),
    }))
  );
  const missing = stats.filter((entry) => !entry.stat).map((entry) => entry.relativePath);

  if (missing.length > 0) {
    return {
      complete: false,
      signature: '',
      summary: `缺少关键产物：${missing.join(', ')}`,
    };
  }

  const [runPlan, itineraryData, sources, dataQuality, pageSource] = await Promise.all([
    parseJsonFileOrNull(path.join(projectPath, '.travelpilot/run_plan.json')),
    parseJsonFileOrNull(path.join(projectPath, 'data_file/final/itinerary-data.json')),
    parseJsonFileOrNull(path.join(projectPath, 'evidence/sources.json')),
    parseJsonFileOrNull(path.join(projectPath, 'evidence/data_quality.json')),
    fs.readFile(path.join(projectPath, 'app/page.tsx'), 'utf8').catch(() => ''),
  ]);

  if (!hasMeaningfulJsonPayload(runPlan)) {
    return { complete: false, signature: '', summary: '.travelpilot/run_plan.json 不是有效执行计划' };
  }

  if (!hasMeaningfulJsonPayload(itineraryData)) {
    return { complete: false, signature: '', summary: 'itinerary-data.json 没有有效路线数据' };
  }

  if (!hasMeaningfulJsonPayload(sources) || !hasMeaningfulJsonPayload(dataQuality)) {
    return { complete: false, signature: '', summary: '数据来源或质量证据不完整' };
  }

  const hasTravelDashboard =
    pageSource.length > 1500 &&
    !/Create Next App|Get started by editing|next\/image/i.test(pageSource) &&
    /(itinerary-data|data_file\/final|路线|行程|POI|UGC|预算|时长|步行|排队|风险|proposal|timeline|evidence|svg|canvas|recharts)/i.test(pageSource);

  if (!hasTravelDashboard) {
    return { complete: false, signature: '', summary: 'app/page.tsx 尚未形成有效旅行路线看板' };
  }

  return {
    complete: true,
    signature: stats
      .map(({ relativePath, stat }) => `${relativePath}:${stat?.size ?? 0}:${Math.round(stat?.mtimeMs ?? 0)}`)
      .join('|'),
    summary: 'run_plan、itinerary 数据、证据文件和路线看板页面已完成',
  };
}

async function appendTravelExecutionEvent(projectPath: string, payload: Record<string, unknown>): Promise<void> {
  const eventPath = path.join(projectPath, '.travelpilot/events.jsonl');
  const event = {
    created_at: new Date().toISOString(),
    ...payload,
  };

  try {
    await fs.mkdir(path.dirname(eventPath), { recursive: true });
    await fs.appendFile(eventPath, `${JSON.stringify(event)}\n`, 'utf8');
  } catch (error) {
    console.warn('[ClaudeService] Failed to append travel execution event:', error);
  }
}

function pickCommandFromToolInput(input: Record<string, unknown>): string | null {
  const keys = ['command', 'cmd', 'shellCommand', 'shell_command'];
  for (const key of keys) {
    const value = input[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return null;
}

function getBlockedBashReason(command: string): string | null {
  const compact = command.replace(/\s+/g, ' ').trim();
  const blockedPatterns: Array<{ pattern: RegExp; reason: string }> = [
    {
      pattern: /(^|[;&|]\s*|\bxargs\s+)kill\b|\bpkill\b|\bkillall\b|\bfuser\b[^;&|]*\s-k\b/i,
      reason: '不能杀进程或清理 dev server，这会影响 QuantPilot 平台自身。',
    },
    {
      pattern: /\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?dev\b|\bnpm\s+exec\s+next\s+dev\b|\bnext\s+dev\b/i,
      reason: '不能自行启动 Next.js dev server，预览由 QuantPilot 统一托管。',
    },
    {
      pattern: /\bscripts\/run-(?:web|dev)\.js\b|\bnode\s+scripts\/run-(?:web|dev)\.js\b/i,
      reason: '不能绕过平台启动脚本，预览端口由 QuantPilot 统一分配。',
    },
    {
      pattern: /\buvicorn\b|\bfastapi\s+dev\b|\bflask\s+run\b|\bpython(?:3)?\s+-m\s+http\.server\b|\bserve\b(?:\s|$)/i,
      reason: '不能在生成项目中启动长驻服务，HTTP 验证由平台自动执行。',
    },
    {
      pattern: /\b(?:cat|tee|echo|printf|python(?:3)?(?:\s+-c)?|node(?:\s+-e)?)\b[\s\S]*(?:>|>>|<<\s*['"]?\w+)|\btouch\s+.*\.(?:tsx?|jsx?|css|json|txt|md)\b/i,
      reason: '不能通过 Bash 重定向、heredoc、脚本或 touch 写入源码/数据文件，请使用 Write/Edit 工具修改文件。',
    },
  ];

  return blockedPatterns.find(({ pattern }) => pattern.test(compact))?.reason ?? null;
}

async function guardClaudeToolUse(toolName: string, input: Record<string, unknown>): Promise<PermissionResult> {
  const normalizedToolName = toolName.toLowerCase();
  const isShellTool = normalizedToolName.includes('bash') || normalizedToolName.includes('shell');

  if (isShellTool) {
    const command = pickCommandFromToolInput(input);
    if (command) {
      const blockedReason = getBlockedBashReason(command);
      if (blockedReason) {
        return {
          behavior: 'deny',
          message: `QuantPilot 已拦截该命令：${blockedReason} 请只修改生成项目文件并运行 npm run build；预览、HTTP 200 和端口管理由平台自动完成。`,
        };
      }
    }
  }

  return { behavior: 'allow', updatedInput: input };
}

const normalizeAction = (value: unknown): ToolAction | undefined => {
  if (typeof value !== 'string') return undefined;
  const candidate = value.trim().toLowerCase();
  if (!candidate) return undefined;
  if (candidate.includes('edit') || candidate.includes('modify') || candidate.includes('update') || candidate.includes('patch')) {
    return 'Edited';
  }
  if (candidate.includes('write') || candidate.includes('create') || candidate.includes('add') || candidate.includes('append')) {
    return 'Created';
  }
  if (candidate.includes('read') || candidate.includes('open') || candidate.includes('view')) {
    return 'Read';
  }
  if (candidate.includes('delete') || candidate.includes('remove')) {
    return 'Deleted';
  }
  if (
    candidate.includes('search') ||
    candidate.includes('find') ||
    candidate.includes('list') ||
    candidate.includes('glob') ||
    candidate.includes('ls') ||
    candidate.includes('grep')
  ) {
    return 'Searched';
  }
  if (candidate.includes('generate') || candidate.includes('todo') || candidate.includes('plan')) {
    return 'Generated';
  }
  if (
    candidate.includes('execute') ||
    candidate.includes('exec') ||
    candidate.includes('run') ||
    candidate.includes('bash') ||
    candidate.includes('shell') ||
    candidate.includes('command')
  ) {
    return 'Executed';
  }
  return undefined;
};

const inferActionFromToolName = (toolName: unknown): ToolAction | undefined => {
  if (typeof toolName !== 'string') return undefined;
  const normalized = toolName.trim().toLowerCase();
  if (!normalized) return undefined;
  if (TOOL_NAME_ACTION_MAP[normalized]) {
    return TOOL_NAME_ACTION_MAP[normalized];
  }
  const suffix = normalized.split(':').pop() ?? normalized;
  if (suffix && TOOL_NAME_ACTION_MAP[suffix]) {
    return TOOL_NAME_ACTION_MAP[suffix];
  }
  return normalizeAction(normalized);
};

const pickFirstString = (value: unknown): string | undefined => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : undefined;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      const candidate = pickFirstString(entry);
      if (candidate) return candidate;
    }
    return undefined;
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    const nestedKeys = ['path', 'filepath', 'filePath', 'file_path', 'target', 'value'];
    for (const key of nestedKeys) {
      if (key in obj) {
        const candidate = pickFirstString(obj[key]);
        if (candidate) return candidate;
      }
    }
  }
  return undefined;
};

const extractPathFromInput = (input: unknown, action?: ToolAction): string | undefined => {
  if (!input || typeof input !== 'object') return undefined;
  const record = input as Record<string, unknown>;
  const candidateKeys = [
    'filePath',
    'file_path',
    'filepath',
    'path',
    'targetPath',
    'target_path',
    'target',
    'targets',
    'fullPath',
    'full_path',
    'destination',
    'destinationPath',
    'outputPath',
    'output_path',
    'glob',
    'pattern',
    'directory',
    'dir',
    'filename',
    'name',
  ];

  for (const key of candidateKeys) {
    if (key in record) {
      const result = pickFirstString(record[key]);
      if (result) {
        return result;
      }
    }
  }

  if (Array.isArray(record.targets)) {
    for (const target of record.targets as unknown[]) {
      const candidate = pickFirstString(target);
      if (candidate) {
        return candidate;
      }
    }
  }

  if (!action || action === 'Executed') {
    const commandKeys = ['command', 'cmd', 'shellCommand', 'shell_command'];
    for (const key of commandKeys) {
      if (key in record) {
        const candidate = pickFirstString(record[key]);
        if (candidate) {
          return candidate;
        }
      }
    }
  }

  return undefined;
};

const extractPathFromToolText = (value: unknown): string | undefined => {
  const text = stringifyToolResultContent(value);
  if (!text) return undefined;

  const patterns = [
    /File created successfully at:\s*([^\n(]+)/i,
    /The file\s+(.+?)\s+has been updated successfully/i,
    /File (?:updated|written|created) successfully at:\s*([^\n(]+)/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    const candidate = match?.[1]?.trim();
    if (candidate) {
      return candidate;
    }
  }

  return undefined;
};

const describeCurlCommand = (command: string): string | undefined => {
  const lower = command.toLowerCase();
  if (!lower.includes('curl')) return undefined;
  if (lower.includes('/api/v1/travel/')) return '调用本地旅游接口获取路线、POI、餐厅或通勤数据。';
  return '调用本地接口获取任务数据。';
};

const describeFileTarget = (target: string, action?: ToolAction): string | undefined => {
  const normalized = target.replaceAll('\\', '/');
  if (!normalized) return undefined;
  if (normalized.endsWith('.travelpilot/run_plan.json')) return '记录本次旅游规划的区域、偏好、数据需求和验收项。';
  if (normalized.endsWith('.travelpilot/events.jsonl')) return '追加可见执行事件，便于复盘每个阶段。';
  if (normalized.endsWith('evidence/sources.json')) return '记录数据来源、接口、抓取时间和来源说明。';
  if (normalized.endsWith('evidence/data_quality.json')) return '记录数据质量、缺失字段、异常和限制。';
  if (normalized.endsWith('data_file/final/itinerary-data.json')) return '写入最终路线数据，页面将基于它渲染方案。';
  if (normalized.endsWith('app/page.tsx')) return action === 'Read' ? '读取页面代码，确认当前渲染结构。' : '生成或更新旅游路线可视化页面。';
  if (normalized.endsWith('app/globals.css')) return action === 'Read' ? '读取页面样式，确认布局基础。' : '更新页面样式，保证布局和响应式体验。';
  if (normalized.endsWith('next.config.js')) return '检查 Next.js 配置，确保预览和构建链路可用。';
  if (normalized.endsWith('package.json')) return '检查项目依赖和脚本，确保 build/dev 可执行。';
  return undefined;
};

const describeSkill = (toolName?: string): string | undefined => {
  if (!toolName || !toolName.toLowerCase().includes('travel')) return undefined;
  const lower = toolName.toLowerCase();
  if (lower.includes('run-planner')) return '建立旅游规划执行计划，明确区域、偏好、数据需求和验证规则。';
  if (lower.includes('poi')) return '检索景点、餐厅和区域候选数据。';
  if (lower.includes('route')) return '优化路线顺序、通勤和时间安排。';
  if (lower.includes('data-quality')) return '检查旅游数据覆盖率、缺失字段、来源和可用性。';
  if (lower.includes('visualization')) return '基于最终路线数据生成可视化页面。';
  return '执行旅游规划工具，推进当前阶段。';
};

const buildToolMetadata = (block: Record<string, unknown>): Record<string, unknown> => {
  const metadata: Record<string, unknown> = {};
  const toolName = pickFirstString(block.name) ?? (typeof block.name === 'string' ? block.name : undefined);
  const toolInput = block.input;
  const inputRecord = toolInput && typeof toolInput === 'object' ? (toolInput as Record<string, unknown>) : undefined;

  if (toolName) {
    metadata.toolName = toolName;
    metadata.tool_name = toolName;
  }

  if (toolInput !== undefined) {
    metadata.toolInput = toolInput;
  }

  let action =
    normalizeAction(block.action) ??
    normalizeAction(block.operation) ??
    (inputRecord ? normalizeAction(inputRecord.action) ?? normalizeAction(inputRecord.operation) : undefined) ??
    inferActionFromToolName(toolName);

  const directPath =
    pickFirstString(block.filePath) ??
    pickFirstString(block.file_path) ??
    pickFirstString(block.targetPath) ??
    pickFirstString(block.target_path) ??
    pickFirstString(block.path);

  let filePath = directPath ?? extractPathFromInput(toolInput, action);

  if (!filePath && inputRecord) {
    filePath =
      extractPathFromInput(inputRecord, action) ??
      pickFirstString(inputRecord.filePath) ??
      pickFirstString(inputRecord.file_path);
  }

  if (!filePath && inputRecord) {
    const command =
      pickFirstString(inputRecord.command) ??
      pickFirstString(inputRecord.cmd) ??
      pickFirstString(inputRecord.shellCommand) ??
      pickFirstString(inputRecord.shell_command);
    if (command) {
      metadata.command = command;
      filePath = command;
      if (!action) {
        action = 'Executed';
      }
    }
  }

  if (filePath) {
    metadata.filePath = filePath;
  }

  if (action) {
    metadata.action = action;
  }

  const summary =
    pickFirstString(block.summary) ??
    pickFirstString(block.description) ??
    pickFirstString(block.result) ??
    pickFirstString(block.resultSummary) ??
    pickFirstString(block.result_summary) ??
    (inputRecord ? pickFirstString(inputRecord.summary) ?? pickFirstString(inputRecord.description) : undefined) ??
    pickFirstString(block.diff) ??
    pickFirstString(block.diffInfo) ??
    pickFirstString(block.diff_info);

  if (summary) {
    metadata.summary = summary;
  }

  if (!metadata.summary) {
    const command = pickFirstString(metadata.command) ?? (filePath && filePath.includes('curl') ? filePath : undefined);
    metadata.summary =
      describeSkill(toolName) ??
      (command ? describeCurlCommand(command) : undefined) ??
      (filePath ? describeFileTarget(filePath, action) : undefined);
  }

  return metadata;
};

const stringifyToolResultContent = (value: unknown): string => {
  if (value === null || value === undefined) {
    return '';
  }

  if (typeof value === 'string') {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return value
      .map((entry) => {
        if (typeof entry === 'string') {
          return entry;
        }
        if (entry && typeof entry === 'object') {
          const record = entry as Record<string, unknown>;
          const text = pickFirstString(record.text) ?? pickFirstString(record.content) ?? pickFirstString(record.value);
          if (text) {
            return text;
          }
        }
        try {
          return JSON.stringify(entry);
        } catch {
          return String(entry);
        }
      })
      .filter((entry) => entry.trim().length > 0)
      .join('\n')
      .trim();
  }

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const text = pickFirstString(record.text) ?? pickFirstString(record.content) ?? pickFirstString(record.value);
    if (text) {
      return text;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  return String(value).trim();
};

const buildToolResultMetadata = (
  block: Record<string, unknown>,
  toolNameById: Map<string, string>
): Record<string, unknown> => {
  const toolUseId =
    pickFirstString(block.tool_use_id) ??
    pickFirstString(block.toolUseId) ??
    pickFirstString(block.toolCallId) ??
    pickFirstString(block.tool_call_id) ??
    pickFirstString(block.id);
  const rawToolName =
    pickFirstString(block.name) ??
    pickFirstString(block.tool_name) ??
    pickFirstString(block.toolName) ??
    (toolUseId ? toolNameById.get(toolUseId) : undefined);
  const skillName =
    block.content && typeof block.content === 'object'
      ? pickFirstString((block.content as Record<string, unknown>).skill)
      : undefined;
  const metadata: Record<string, unknown> = {};

  if (rawToolName || skillName) {
    metadata.toolName = rawToolName ?? skillName;
    metadata.tool_name = rawToolName ?? skillName;
    if (skillName) {
      metadata.skill = skillName;
      metadata.skillName = skillName;
    }
  }

  if (toolUseId) {
    metadata.toolUseId = toolUseId;
    metadata.tool_use_id = toolUseId;
    metadata.toolCallId = toolUseId;
    metadata.tool_call_id = toolUseId;
  }

  if (typeof block.is_error === 'boolean') {
    metadata.isError = block.is_error;
    metadata.is_error = block.is_error;
  }

  const resultText = stringifyToolResultContent(block.content ?? block.result ?? block.output ?? block.text ?? block.value);
  const resultPath = extractPathFromToolText(resultText);
  if (resultPath) {
    metadata.filePath = resultPath;
    metadata.file_path = resultPath;
  }
  if (!metadata.summary && resultText) {
    if (/error|failed|失败|报错/i.test(resultText)) {
      metadata.summary = '工具返回异常，需要根据错误信息调整后续步骤。';
    } else if (resultPath) {
      metadata.summary = describeFileTarget(resultPath, inferActionFromToolName(rawToolName));
    }
  }

  return metadata;
};

const dispatchToolResultBlock = async ({
  projectId,
  block,
  toolNameById,
  requestId,
  dedupeStore,
}: {
  projectId: string;
  block: Record<string, unknown>;
  toolNameById: Map<string, string>;
  requestId?: string;
  dedupeStore: Set<string>;
}): Promise<void> => {
  const metadata = buildToolResultMetadata(block, toolNameById);
  const resultValue = block.content ?? block.result ?? block.output ?? block.text ?? block.value;
  const resultText = stringifyToolResultContent(resultValue);

  if (!resultText) {
    return;
  }

  metadata.toolOutput = resultText;
  metadata.tool_output = resultText;
  metadata.output = resultText;

  await dispatchToolMessage({
    projectId,
    metadata,
    content: resultText,
    requestId,
    persist: true,
    isStreaming: false,
    messageType: 'tool_result',
    dedupeKey: computeToolMessageSignature(metadata, resultText, 'tool_result'),
    dedupeStore,
  });
};

interface ToolPlaceholderDetails {
  raw: string;
  toolName?: string;
  target?: string;
  summary?: string;
  action?: ToolAction;
  isResult: boolean;
}

const parseToolPlaceholderText = (text: string): ToolPlaceholderDetails | null => {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  let toolName: string | undefined;
  let target: string | undefined;
  let summary: string | undefined;
  let isResult = false;

  const bracketMatch = trimmed.match(/^\[Tool:\s*([^\]\n]+)\s*\](.*)$/i);
  if (bracketMatch) {
    toolName = bracketMatch[1]?.trim();
    const trailing = bracketMatch[2]?.trim();
    if (trailing) {
      target = trailing;
    }
  }

  const usingToolMatch = trimmed.match(/^Using tool:\s*([^\n]+?)(?:\s+on\s+(.+))?$/i);
  if (usingToolMatch) {
    toolName = toolName ?? usingToolMatch[1]?.trim();
    const maybeTarget = usingToolMatch[2]?.trim();
    if (maybeTarget) {
      target = maybeTarget;
    }
  }

  const toolResultMatch = trimmed.match(/^Tool result:\s*(.+)$/i);
  if (toolResultMatch) {
    summary = toolResultMatch[1]?.trim() || undefined;
    isResult = true;
  }

  if (!toolName && !target && !summary) {
    return null;
  }

  const action = inferActionFromToolName(toolName) ?? (isResult ? undefined : 'Executed');

  return {
    raw: trimmed,
    toolName,
    target,
    summary,
    action,
    isResult,
  };
};

const buildMetadataFromPlaceholder = (details: ToolPlaceholderDetails): Record<string, unknown> => {
  const metadata: Record<string, unknown> = {};

  if (details.toolName) {
    metadata.toolName = details.toolName;
    metadata.tool_name = details.toolName;
  }

  if (details.target) {
    metadata.filePath = details.target;
    metadata.file_path = details.target;
  }

  if (details.summary) {
    metadata.summary = details.summary;
  }

  const action = details.action ?? inferActionFromToolName(details.toolName);
  if (action) {
    metadata.action = action;
  }

  metadata.placeholderType = details.isResult ? 'result' : 'start';

  return metadata;
};

const mergeMetadata = (
  base: Record<string, unknown> | undefined,
  extension: Record<string, unknown>
): Record<string, unknown> => {
  const result: Record<string, unknown> = { ...(base ?? {}) };
  for (const [key, value] of Object.entries(extension)) {
    if (value !== undefined) {
      result[key] = value;
    }
  }
  return result;
};

const normalizeSignatureValue = (value?: string | null): string => {
  if (typeof value !== 'string') {
    return '';
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed.toLowerCase() : '';
};

const computeToolMessageSignature = (
  metadata: Record<string, unknown>,
  content: string,
  messageType: 'tool_use' | 'tool_result' = 'tool_use'
): string => {
  const meta = metadata ?? {};
  const toolName =
    pickFirstString(meta.toolName) ?? pickFirstString(meta.tool_name);
  const filePath =
    pickFirstString(meta.filePath) ??
    pickFirstString(meta.file_path) ??
    pickFirstString(meta.targetPath) ??
    pickFirstString(meta.target_path);
  const summary =
    pickFirstString(meta.summary) ??
    pickFirstString(meta.resultSummary) ??
    pickFirstString(meta.result_summary) ??
    pickFirstString(meta.description);
  const command = pickFirstString(meta.command);
  const action = pickFirstString(meta.action);

  return [
    normalizeSignatureValue(messageType),
    normalizeSignatureValue(toolName),
    normalizeSignatureValue(filePath),
    normalizeSignatureValue(summary),
    normalizeSignatureValue(command),
    normalizeSignatureValue(action),
    normalizeSignatureValue(content),
  ].join('|');
};

const createToolMessageContent = (details: ToolPlaceholderDetails): string => {
  if (details.isResult && details.summary) {
    return `Tool result: ${details.summary}`;
  }
  if (details.toolName) {
    const targetSegment = details.target ? ` on ${details.target}` : '';
    return `Using tool: ${details.toolName}${targetSegment}`;
  }
  return details.raw;
};

const dispatchToolMessage = async ({
  projectId,
  metadata,
  content,
  requestId,
  persist = true,
  isStreaming = false,
  messageType = 'tool_use',
  dedupeKey,
  dedupeStore,
}: {
  projectId: string;
  metadata: Record<string, unknown>;
  content: string;
  requestId?: string;
  persist?: boolean;
  isStreaming?: boolean;
  messageType?: 'tool_use' | 'tool_result';
  dedupeKey?: string;
  dedupeStore?: Set<string>;
}): Promise<void> => {
  const trimmedContent = content.trim();
  if (!trimmedContent) {
    return;
  }

  const enrichedMetadata = {
    ...(metadata ?? {}),
  };

  if (requestId && !enrichedMetadata.requestId) {
    enrichedMetadata.requestId = requestId;
  }

  if (persist && dedupeStore && dedupeKey) {
    const normalizedKey = dedupeKey.trim();
    if (normalizedKey.length > 0) {
      if (dedupeStore.has(normalizedKey)) {
        return;
      }
      dedupeStore.add(normalizedKey);
    }
  }

  if (!persist) {
    const transientMetadata = {
      ...enrichedMetadata,
      isTransientToolMessage: true,
    };
    streamManager.publish(projectId, {
      type: 'message',
      data: createRealtimeMessage({
        projectId,
        role: 'tool',
        content: trimmedContent,
        messageType,
        metadata: transientMetadata,
        requestId,
        isStreaming,
      }),
    });
    return;
  }

  try {
    const savedMessage = await createMessage({
      projectId,
      role: 'tool',
      messageType,
      content: trimmedContent,
      metadata: enrichedMetadata,
      cliSource: 'claude',
      requestId: requestId ?? null,
    });

    streamManager.publish(projectId, {
      type: 'message',
      data: serializeMessage(savedMessage, {
        requestId,
        isStreaming,
        isFinal: !isStreaming,
      }),
    });
  } catch (error) {
    console.error('[ClaudeService] Failed to persist tool message:', error);
  }
};

const handleToolPlaceholderMessage = async (
  projectId: string,
  placeholderText: string,
  requestId: string | undefined,
  baseMetadata?: Record<string, unknown>,
  options?: { dedupeStore?: Set<string> }
): Promise<boolean> => {
  const details = parseToolPlaceholderText(placeholderText);
  if (!details) {
    return false;
  }

  const metadata = mergeMetadata(baseMetadata, buildMetadataFromPlaceholder(details));
  const content = createToolMessageContent(details);
  const messageType: 'tool_use' | 'tool_result' = details.isResult ? 'tool_result' : 'tool_use';
  const signature = computeToolMessageSignature(metadata, content, messageType);

  await dispatchToolMessage({
    projectId,
    metadata,
    content,
    requestId,
    persist: true,
    isStreaming: false,
    messageType,
    dedupeKey: signature,
    dedupeStore: options?.dedupeStore,
  });

  return true;
};

function resolveModelId(model?: string | null): string {
  if (model && model.trim().length > 0) {
    return normalizeClaudeModelId(model);
  }
  const anthropicModelOverride = process.env.ANTHROPIC_MODEL?.trim();
  if (anthropicModelOverride) {
    return anthropicModelOverride;
  }
  return normalizeClaudeModelId(model);
}

function inferImageMediaType(image: ClaudeImageAttachment): 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp' | null {
  const source = `${image.mimeType ?? ''} ${image.name ?? ''} ${image.path ?? ''}`.toLowerCase();
  if (source.includes('png') || source.endsWith('.png')) return 'image/png';
  if (source.includes('jpeg') || source.includes('jpg') || source.endsWith('.jpeg') || source.endsWith('.jpg')) return 'image/jpeg';
  if (source.includes('gif') || source.endsWith('.gif')) return 'image/gif';
  if (source.includes('webp') || source.endsWith('.webp')) return 'image/webp';
  return null;
}

async function buildClaudePromptInput(
  promptText: string,
  model: string,
  images?: ClaudeImageAttachment[]
): Promise<string | AsyncIterable<SDKUserMessage>> {
  const validImages = (images ?? []).filter((image) => image.path && image.path.trim().length > 0);
  const modelSupportsImages = getClaudeModelDefinition(model)?.supportsImages === true;
  if (validImages.length === 0 || !modelSupportsImages) {
    return promptText;
  }

  const content: unknown[] = [{ type: 'text', text: promptText }];

  for (const image of validImages) {
    const mediaType = inferImageMediaType(image);
    if (!mediaType) {
      content.push({
        type: 'text',
        text: `图片 ${image.name} 的格式暂不支持直接视觉输入，请改为读取附件路径：${image.path}`,
      });
      continue;
    }

    try {
      const data = await fs.readFile(image.path, 'base64');
      content.push({
        type: 'image',
        source: {
          type: 'base64',
          media_type: mediaType,
          data,
        },
      });
    } catch (error) {
      content.push({
        type: 'text',
        text: `图片 ${image.name} 读取失败，请尝试通过附件路径检查：${image.path}。错误：${error instanceof Error ? error.message : String(error)}`,
      });
    }
  }

  async function* promptStream(): AsyncIterable<SDKUserMessage> {
    yield {
      type: 'user',
      parent_tool_use_id: null,
      message: {
        role: 'user',
        content: content as any,
      },
    };
  }

  return promptStream();
}

/**
 * Execute command using Claude Agent SDK
 *
 * @param projectId - Project ID
 * @param projectPath - Project directory path
 * @param instruction - Command to pass to AI
 * @param model - Claude model to use (default: claude-sonnet-4-6)
 * @param sessionId - Previous session ID (maintains conversation context)
 * @param requestId - (Optional) User request tracking ID
 */
export async function executeClaude(
  projectId: string,
  projectPath: string,
  instruction: string,
  model: string = CLAUDE_DEFAULT_MODEL,
  sessionId?: string,
  requestId?: string,
  images?: ClaudeImageAttachment[]
): Promise<void> {
  console.log(`\n========================================`);
  console.log(`[ClaudeService] 🚀 Starting Claude Agent SDK`);
  console.log(`[ClaudeService] Project: ${projectId}`);
  const resolvedModel = resolveModelId(model);
  const modelLabel = getClaudeModelDisplayName(resolvedModel);
  const aliasNote = resolvedModel !== model ? ` (alias for ${model})` : '';
  console.log(`[ClaudeService] Model: ${modelLabel} [${resolvedModel}]${aliasNote}`);
  console.log(`[ClaudeService] Session ID: ${sessionId || 'new session'}`);
  console.log(`[ClaudeService] Instruction: ${instruction.substring(0, 100)}...`);
  console.log(`========================================\n`);

  const configuredMaxTokens = Number(process.env.CLAUDE_CODE_MAX_OUTPUT_TOKENS);
  const maxOutputTokens = Number.isFinite(configuredMaxTokens) && configuredMaxTokens > 0
    ? configuredMaxTokens
    : 4000;
  const configuredMaxTurns = Number(process.env.CLAUDE_CODE_MAX_TURNS);
  const maxTurns = Number.isFinite(configuredMaxTurns) && configuredMaxTurns > 0
    ? configuredMaxTurns
    : 32;
  const idleTimeoutMs = readPositiveMsEnv('CLAUDE_CODE_IDLE_TIMEOUT_MS', 5 * 60 * 1000);
  const totalTimeoutMs = readPositiveMsEnv('CLAUDE_CODE_EXECUTION_TIMEOUT_MS', 20 * 60 * 1000);
  const abortController = new AbortController();
  let response: ReturnType<typeof query> | null = null;
  let idleTimer: NodeJS.Timeout | null = null;
  let totalTimer: NodeJS.Timeout | null = null;
  let abortReason: string | null = null;
  let gracefulAbortReason: string | null = null;

  let hasMarkedTerminalStatus = false;
  let emittedCompletedStatus = false;

  const safeMarkRunning = async () => {
    if (!requestId) return;
    try {
      await markUserRequestAsRunning(requestId);
    } catch (error) {
      console.error(`[ClaudeService] Failed to mark request ${requestId} as running:`, error);
    }
  };

  const safeMarkCompleted = async () => {
    if (!requestId || hasMarkedTerminalStatus) return;
    try {
      await markUserRequestAsCompleted(requestId);
    } catch (error) {
      console.error(`[ClaudeService] Failed to mark request ${requestId} as completed:`, error);
    } finally {
      hasMarkedTerminalStatus = true;
    }
  };

  const safeMarkFailed = async (message?: string) => {
    if (!requestId || hasMarkedTerminalStatus) return;
    try {
      await markUserRequestAsFailed(requestId, message);
    } catch (error) {
      console.error(`[ClaudeService] Failed to mark request ${requestId} as failed:`, error);
    } finally {
      hasMarkedTerminalStatus = true;
    }
  };

  const publishStatus = (status: string, message?: string) => {
    streamManager.publish(projectId, {
      type: 'status',
      data: {
        status,
        ...(message ? { message } : {}),
        ...(requestId ? { requestId } : {}),
      },
    });
  };

  const clearExecutionTimers = () => {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    if (totalTimer) {
      clearTimeout(totalTimer);
      totalTimer = null;
    }

  };

  const abortClaudeExecution = (message: string) => {
    if (abortReason) return;
    abortReason = message;
    console.warn(`[ClaudeService] ${message}`);
    publishStatus('agent_timeout', message);
    try {
      abortController.abort(new Error(message));
    } catch {
      abortController.abort();
    }
    response?.close();
  };

  const refreshIdleTimer = () => {
    if (idleTimeoutMs <= 0) return;
    if (idleTimer) {
      clearTimeout(idleTimer);
    }
    idleTimer = setTimeout(() => {
      abortClaudeExecution(`Claude Code 超过 ${Math.round(idleTimeoutMs / 1000)} 秒没有返回执行事件，已自动终止本次执行。`);
    }, idleTimeoutMs);
    idleTimer.unref?.();
  };

  // Send start notification via SSE
  publishStatus('starting', 'Initializing Claude Agent SDK...');

  await safeMarkRunning();

  // Collect stderr from SDK process for better diagnostics
  const stderrBuffer: string[] = [];
  const placeholderHistory = new Map<string, Set<string>>();
  const persistedToolMessageSignatures = new Set<string>();
  const toolNameById = new Map<string, string>();
  const markPlaceholderHandled = (sessionKey: string, placeholder: string): boolean => {
    const normalized = placeholder.trim();
    if (!normalized) {
      return false;
    }
    let entries = placeholderHistory.get(sessionKey);
    if (!entries) {
      entries = new Set<string>();
      placeholderHistory.set(sessionKey, entries);
    }
    if (entries.has(normalized)) {
      return false;
    }
    entries.add(normalized);
    return true;
  };

  try {
    // Verify project exists (prevents foreign key constraint errors)
    console.log(`[ClaudeService] 🔍 Verifying project exists...`);
    const project = await getProjectById(projectId);
    if (!project) {
      const errorMessage = `Project not found: ${projectId}. Cannot create messages for non-existent project.`;
      console.error(`[ClaudeService] ❌ ${errorMessage}`);

      streamManager.publish(projectId, {
        type: 'error',
        error: errorMessage,
        data: requestId ? { requestId } : undefined,
      });

      throw new Error(errorMessage);
    }

    console.log(`[ClaudeService] ✅ Project verified: ${project.name}`);

    // Validate and prepare project path
    console.log(`[ClaudeService] 🔒 Validating project path...`);

    // Convert to absolute path
    const absoluteProjectPath = path.isAbsolute(projectPath)
      ? path.resolve(projectPath)
      : path.resolve(process.cwd(), projectPath);

    // Security: Verify project path is within allowed directory
    const allowedBasePath = path.resolve(process.cwd(), process.env.PROJECTS_DIR || './data/projects');
    const relativeToBase = path.relative(allowedBasePath, absoluteProjectPath);
    const isWithinBase =
      !relativeToBase.startsWith('..') && !path.isAbsolute(relativeToBase);
    if (!isWithinBase) {
      const errorMessage = `Security violation: Project path must be within ${allowedBasePath}. Got: ${absoluteProjectPath}`;
      console.error(`[ClaudeService] ❌ ${errorMessage}`);

      streamManager.publish(projectId, {
        type: 'error',
        error: errorMessage,
        data: requestId ? { requestId } : undefined,
      });

      throw new Error(errorMessage);
    }

    // Check project directory exists and create if needed
    try {
      await fs.access(absoluteProjectPath);
      console.log(`[ClaudeService] ✅ Project directory exists: ${absoluteProjectPath}`);
    } catch {
      console.log(`[ClaudeService] 📁 Creating project directory: ${absoluteProjectPath}`);
      await fs.mkdir(absoluteProjectPath, { recursive: true });
    }

    // Send ready notification via SSE
    publishStatus('ready', 'Project verified. Starting AI...');

    const availableSkills = await ensureClaudeSkillsForProject(absoluteProjectPath);
    const quantManifest = await readQuantPilotManifest(absoluteProjectPath);

    // Start Claude Agent SDK query
    console.log(`[ClaudeService] 🤖 Querying Claude Agent SDK...`);
    console.log(`[ClaudeService] 📁 Working Directory: ${absoluteProjectPath}`);
    console.log(`[ClaudeService] 🧩 Skills: ${availableSkills.join(', ') || 'none'}`);
    if (totalTimeoutMs > 0) {
      totalTimer = setTimeout(() => {
        abortClaudeExecution(`Claude Code 执行超过 ${Math.round(totalTimeoutMs / 1000)} 秒，已自动终止本次执行。`);
      }, totalTimeoutMs);
      totalTimer.unref?.();
    }
    refreshIdleTimer();

    const taskPrompt = await buildQuantPilotTaskPrompt(
      instruction,
      absoluteProjectPath,
      quantManifest
    );
    const promptInput = await buildClaudePromptInput(taskPrompt, resolvedModel, images);

    response = query({
      prompt: promptInput,
      options: {
        abortController,
        cwd: absoluteProjectPath,
        additionalDirectories: [absoluteProjectPath],
        model: resolvedModel,
        resume: sessionId, // Resume previous session
        permissionMode: 'default',
        canUseTool: guardClaudeToolUse,
        settingSources: ['project'],
        skills: availableSkills,
        systemPrompt: buildQuantPilotSystemPrompt(),
        maxOutputTokens,
        maxTurns,
        // Capture SDK stderr so we can surface real errors instead of just exit code
        stderr: (data: string) => {
          const line = String(data).trimEnd();
          if (!line) return;
          // Keep only the last ~200 lines to avoid memory bloat
          if (stderrBuffer.length > 200) stderrBuffer.shift();
          stderrBuffer.push(line);
          // Also mirror to server logs for live debugging
          console.error(`[ClaudeSDK][stderr] ${line}`);
        },
      } as any,
    });

    let currentSessionId: string | undefined = sessionId;

    interface AssistantStreamState {
      messageId: string;
      content: string;
      hasSentUpdate: boolean;
      finalized: boolean;
    }

    const assistantStreamStates = new Map<string, AssistantStreamState>();
    const completedStreamSessions = new Set<string>();

    // Handle streaming response
    for await (const message of response) {
      refreshIdleTimer();
      console.log('[ClaudeService] Message type:', message.type);

      if (message.type === 'stream_event') {
        const event: any = (message as any).event ?? {};
        const sessionKey = (message.session_id ?? message.uuid ?? 'default').toString();
        console.log('[ClaudeService] Stream event type:', event.type);

        let streamState = assistantStreamStates.get(sessionKey);

        switch (event.type) {
          case 'message_start': {
            const newState: AssistantStreamState = {
              messageId: randomUUID(),
              content: '',
              hasSentUpdate: false,
              finalized: false,
            };
            assistantStreamStates.set(sessionKey, newState);
            break;
          }
          case 'content_block_start': {
            const contentBlock = event.content_block;
            if (contentBlock && typeof contentBlock === 'object' && contentBlock.type === 'tool_use') {
              const toolUseBlock = contentBlock as Record<string, unknown>;
              const metadata = buildToolMetadata(toolUseBlock);
              const toolUseId = pickFirstString(toolUseBlock.id);
              if (toolUseId) {
                metadata.toolCallId = toolUseId;
                metadata.tool_call_id = toolUseId;
                metadata.toolUseId = toolUseId;
                metadata.tool_use_id = toolUseId;
                const name = pickFirstString(toolUseBlock.name);
                if (name) {
                  toolNameById.set(toolUseId, name);
                }
              }
              await dispatchToolMessage({
                projectId,
                metadata,
                content: `Using tool: ${toolUseBlock.name ?? 'tool'}`,
                requestId,
                persist: false,
                isStreaming: true,
              });
            }
            if (contentBlock && typeof contentBlock === 'object' && contentBlock.type === 'tool_result') {
              await dispatchToolResultBlock({
                projectId,
                block: contentBlock as Record<string, unknown>,
                toolNameById,
                requestId,
                dedupeStore: persistedToolMessageSignatures,
              });
            }
            break;
          }
          case 'tool_result': {
            await dispatchToolResultBlock({
              projectId,
              block: event as Record<string, unknown>,
              toolNameById,
              requestId,
              dedupeStore: persistedToolMessageSignatures,
            });
            break;
          }
          case 'content_block_delta': {
            const delta = event.delta;
            let textChunk = '';

            if (typeof delta === 'string') {
              textChunk = delta;
            } else if (delta && typeof delta === 'object') {
              if (typeof delta.text === 'string') {
                textChunk = delta.text;
              } else if (typeof delta.delta === 'string') {
                textChunk = delta.delta;
              } else if (typeof delta.partial === 'string') {
                textChunk = delta.partial;
              }
            }

            if (typeof textChunk !== 'string' || textChunk.length === 0) {
              break;
            }

            if (!streamState || streamState.finalized) {
              streamState = {
                messageId: randomUUID(),
                content: '',
                hasSentUpdate: false,
                finalized: false,
              };
              assistantStreamStates.set(sessionKey, streamState);
            }

            streamState.content += textChunk;
            const trimmedContent = streamState.content.trim();
            const isPlaceholderLine =
              trimmedContent.length > 0 &&
              ((/^\[Tool:\s*.+\]$/i.test(trimmedContent) && !trimmedContent.includes('\n')) ||
                /^Using tool:/i.test(trimmedContent) ||
                /^Tool result:/i.test(trimmedContent));

            if (trimmedContent.length === 0) {
              streamState.content = '';
              streamState.hasSentUpdate = false;
              break;
            }

            if (isPlaceholderLine) {
              const shouldHandle = markPlaceholderHandled(sessionKey, trimmedContent);
              if (shouldHandle) {
                try {
                  await handleToolPlaceholderMessage(
                    projectId,
                    trimmedContent,
                    requestId,
                    undefined,
                    { dedupeStore: persistedToolMessageSignatures }
                  );
                } catch (error) {
                  console.error('[ClaudeService] Failed to handle streaming tool placeholder:', error);
                }
              }
              streamState.content = '';
              streamState.hasSentUpdate = false;
              break;
            }

            streamState.hasSentUpdate = true;

            streamManager.publish(projectId, {
              type: 'message',
              data: createRealtimeMessage({
                id: streamState.messageId,
                projectId,
                role: 'assistant',
                content: streamState.content,
                messageType: 'chat',
                requestId,
                isStreaming: true,
              }),
            });
            break;
          }
          case 'message_stop': {
            if (streamState && streamState.hasSentUpdate && !streamState.finalized) {
              const trimmedContent = streamState.content.trim();
              const isPlaceholderLine =
                trimmedContent.length > 0 &&
                ((/^\[Tool:\s*.+\]$/i.test(trimmedContent) && !trimmedContent.includes('\n')) ||
                  /^Using tool:/i.test(trimmedContent) ||
                  /^Tool result:/i.test(trimmedContent));

              if (isPlaceholderLine) {
                const shouldHandle = markPlaceholderHandled(sessionKey, trimmedContent);
                if (shouldHandle) {
                  try {
                    await handleToolPlaceholderMessage(
                      projectId,
                      trimmedContent,
                      requestId,
                      undefined,
                      { dedupeStore: persistedToolMessageSignatures }
                    );
                  } catch (error) {
                    console.error('[ClaudeService] Failed to handle tool placeholder on stop:', error);
                  }
                }
              }

              if (
                trimmedContent.length === 0 ||
                isPlaceholderLine
              ) {
                streamState.hasSentUpdate = false;
              }

              if (!streamState.hasSentUpdate) {
                streamState.content = '';
                assistantStreamStates.delete(sessionKey);
                break;
              }

              streamState.finalized = true;

              const savedMessage = await createMessage({
                id: streamState.messageId,
                projectId,
                role: 'assistant',
                messageType: 'chat',
                content: streamState.content,
                cliSource: 'claude',
                requestId: requestId ?? null,
              });

              streamManager.publish(projectId, {
                type: 'message',
                data: serializeMessage(savedMessage, {
                  isStreaming: false,
                  isFinal: true,
                  requestId,
                }),
              });

              completedStreamSessions.add(sessionKey);
            }

            assistantStreamStates.delete(sessionKey);
            break;
          }
          default:
            break;
        }

        continue;
      }

      // Handle by message type
      if (message.type === 'system' && message.subtype === 'init') {
        // Initialize session
        currentSessionId = message.session_id;
        console.log(`[ClaudeService] Session initialized: ${currentSessionId}`);

        // Save session ID to project
        if (currentSessionId) {
          await updateProject(projectId, {
            activeClaudeSessionId: currentSessionId,
          });
        }

        // Send connection notification via SSE
        streamManager.publish(projectId, {
          type: 'connected',
          data: {
            projectId,
            sessionId: currentSessionId,
            timestamp: new Date().toISOString(),
            connectionStage: 'assistant',
          },
        });
      } else if (message.type === 'assistant') {
        const sessionKey = (message.session_id ?? message.uuid ?? 'default').toString();
        if (completedStreamSessions.has(sessionKey)) {
          completedStreamSessions.delete(sessionKey);
          continue;
        }

        // Assistant message
        const assistantMessage = message.message;
        let content = '';

        // Extract content
        if (typeof assistantMessage.content === 'string') {
          content = assistantMessage.content;
        } else if (Array.isArray(assistantMessage.content)) {
          const parts: string[] = [];
          for (const block of assistantMessage.content as unknown[]) {
            if (!block || typeof block !== 'object') {
              continue;
            }

            const safeBlock = block as any;

            if (safeBlock.type === 'text') {
              const text = typeof safeBlock.text === 'string' ? safeBlock.text : '';
              const trimmed = text.trim();
              if (!trimmed) {
                continue;
              }

              const isPlaceholderLine =
                /^\[Tool:\s*/i.test(trimmed) ||
                /^Using tool:/i.test(trimmed) ||
                /^Tool result:/i.test(trimmed);

              if (isPlaceholderLine) {
                const shouldHandle = markPlaceholderHandled(sessionKey, trimmed);
                if (shouldHandle) {
                  try {
                    await handleToolPlaceholderMessage(
                      projectId,
                      trimmed,
                      requestId,
                      undefined,
                      { dedupeStore: persistedToolMessageSignatures }
                    );
                  } catch (error) {
                    console.error('[ClaudeService] Failed to handle assistant tool placeholder:', error);
                  }
                }
                continue;
              }

              parts.push(text);
              continue;
            }

            if (safeBlock.type === 'tool_use') {
              const metadata = buildToolMetadata(safeBlock as Record<string, unknown>);
              const toolUseId = pickFirstString(safeBlock.id);
              if (toolUseId) {
                metadata.toolCallId = toolUseId;
                metadata.tool_call_id = toolUseId;
                metadata.toolUseId = toolUseId;
                metadata.tool_use_id = toolUseId;
                const safeToolName = pickFirstString(safeBlock.name);
                if (safeToolName) {
                  toolNameById.set(toolUseId, safeToolName);
                }
              }
              const name = typeof safeBlock.name === 'string' ? safeBlock.name : pickFirstString(safeBlock.name);
              const toolContent = `Using tool: ${name ?? 'tool'}`;
              await dispatchToolMessage({
                projectId,
                metadata,
                content: toolContent,
                requestId,
                persist: true,
                isStreaming: false,
                messageType: 'tool_use',
                dedupeKey: computeToolMessageSignature(metadata, toolContent, 'tool_use'),
                dedupeStore: persistedToolMessageSignatures,
              });
              continue;
            }

            if (safeBlock.type === 'tool_result') {
              await dispatchToolResultBlock({
                projectId,
                block: safeBlock as Record<string, unknown>,
                toolNameById,
                requestId,
                dedupeStore: persistedToolMessageSignatures,
              });
              continue;
            }
          }

          content = parts.join('\n');
        }

        console.log('[ClaudeService] Assistant message:', content.substring(0, 100));

        // Save message to DB
        if (content) {
          const savedMessage = await createMessage({
            projectId,
            role: 'assistant',
            messageType: 'chat',
            content,
            // sessionId is Session table foreign key, so don't store Claude SDK session ID
            // Claude SDK session ID is stored in project.activeClaudeSessionId
            cliSource: 'claude',
            requestId: requestId ?? null,
          });

          // Send via SSE in real-time
          streamManager.publish(projectId, {
            type: 'message',
            data: serializeMessage(savedMessage, { requestId }),
          });
        }
      } else if (message.type === 'user') {
        const userMessage = (message as any).message;
        const contentBlocks = Array.isArray(userMessage?.content) ? userMessage.content : [];

        for (const block of contentBlocks) {
          if (!block || typeof block !== 'object') {
            continue;
          }
          const safeBlock = block as Record<string, unknown>;
          if (safeBlock.type === 'tool_result') {
            await dispatchToolResultBlock({
              projectId,
              block: safeBlock,
              toolNameById,
              requestId,
              dedupeStore: persistedToolMessageSignatures,
            });
          }
        }
      } else if (message.type === 'result') {
        // Final result
        console.log('[ClaudeService] Task completed:', message.subtype);

        publishStatus('completed');
        emittedCompletedStatus = true;
        await safeMarkCompleted();
      }
    }

    console.log('[ClaudeService] Streaming completed');
    if (abortReason) {
      if (gracefulAbortReason) {
        return;
      }
      throw new Error(abortReason);
    }
    await safeMarkCompleted();
    if (!emittedCompletedStatus) {
      publishStatus('completed');
      emittedCompletedStatus = true;
    }
  } catch (error) {
    if (gracefulAbortReason) {
      console.log(`[ClaudeService] Claude execution ended after artifact completion: ${gracefulAbortReason}`);
      return;
    }

    console.error(`[ClaudeService] Failed to execute Claude:`, error);

    let errorMessage = abortReason ?? 'Unknown error';

    if (!abortReason && error instanceof Error) {
      errorMessage = error.message;

      // Detect Claude Code CLI not installed
      if (errorMessage.includes('command not found') || errorMessage.includes('not found: claude')) {
        errorMessage = `Claude Code CLI is not installed.\n\nInstallation instructions:\n1. npm install -g @anthropic-ai/claude-code\n2. Configure MiniMax environment variables such as ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN`;
      }
      // Detect authentication failure
      else if (errorMessage.includes('not authenticated') || errorMessage.includes('authentication')) {
        errorMessage = `Claude Code MiniMax configuration required.\n\nPlease configure ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN in .env/.env.local or ~/.claude/settings.json.`;
      }
      // Permission error
      else if (errorMessage.includes('permission') || errorMessage.includes('EACCES')) {
        errorMessage = `No file access permission. Please check project directory permissions.`;
      }
      // Token limit exceeded
      else if (errorMessage.includes('max_tokens')) {
        errorMessage = `Generation length is too long. Please shorten the prompt or split the request into smaller parts.`;
      }
      // Generic process exit without details – attempt to surface last stderr lines
      else if (/process exited with code \d+/.test(errorMessage) && stderrBuffer.length > 0) {
        // Heuristics: extract likely actionable hints from stderr
        const tail = stderrBuffer.slice(-15).join('\n');
        // Common auth hints
        if (/auth\s+login|not\s+logged\s+in|sign\s+in/i.test(tail)) {
          errorMessage = `Claude Code MiniMax configuration required.\n\nPlease configure ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN.\n\nDetailed log:\n${tail}`;
        } else if (/network|ENOTFOUND|ECONN|timeout/i.test(tail)) {
          errorMessage = `Failed to run Claude Code due to network error. Please check your network connection and try again.\n\nDetailed log:\n${tail}`;
        } else if (/permission|EACCES|EPERM|denied/i.test(tail)) {
          errorMessage = `Execution interrupted due to file access permission error. Please check project directory permissions.\n\nDetailed log:\n${tail}`;
        } else if (/model|unsupported|invalid\s+model/i.test(tail)) {
          errorMessage = `There is a problem with the model settings. Please try changing the model.\n\nDetailed log:\n${tail}`;
        } else {
          errorMessage = `${errorMessage}\n\nDetailed log:\n${tail}`;
        }
      }
    }

    await safeMarkFailed(errorMessage);
    publishStatus('error', errorMessage);

    // Send error via SSE
    streamManager.publish(projectId, {
      type: 'error',
      error: errorMessage,
      data: requestId ? { requestId } : undefined,
    });

    throw new Error(errorMessage);
  } finally {
    clearExecutionTimers();
  }
}

/**
 * Initialize Next.js project with Claude Code
 *
 * @param projectId - Project ID
 * @param projectPath - Project directory path
 * @param initialPrompt - Initial prompt
 * @param model - Claude Code runtime model to use (default: MiniMax-M2.7)
 * @param requestId - (Optional) User request tracking ID
 */
export async function initializeNextJsProject(
  projectId: string,
  projectPath: string,
  initialPrompt: string,
  model: string = CLAUDE_DEFAULT_MODEL,
  requestId?: string
): Promise<void> {
  console.log(`[ClaudeService] Initializing Next.js project: ${projectId}`);

  // Next.js project creation command
  const fullPrompt = `
Create a new Next.js 16 application with the following requirements:
${initialPrompt}

Use App Router, TypeScript, and Tailwind CSS.
Set up the basic project structure and implement the requested features.
`.trim();

  await executeClaude(projectId, projectPath, fullPrompt, model, undefined, requestId);
}

/**
 * Apply changes to project
 *
 * @param projectId - Project ID
 * @param projectPath - Project directory path
 * @param instruction - Change request command
 * @param model - Claude Code runtime model to use (default: MiniMax-M2.7)
 * @param sessionId - Session ID
 * @param requestId - (Optional) User request tracking ID
 */
export async function applyChanges(
  projectId: string,
  projectPath: string,
  instruction: string,
  model: string = CLAUDE_DEFAULT_MODEL,
  sessionId?: string,
  requestId?: string,
  images?: ClaudeImageAttachment[]
): Promise<void> {
  console.log(`[ClaudeService] Applying changes to project: ${projectId}`);
  await executeClaude(projectId, projectPath, instruction, model, sessionId, requestId, images);
}
