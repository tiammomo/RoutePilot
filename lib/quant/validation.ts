import { spawn } from 'child_process';
import fs from 'fs/promises';
import path from 'path';
import { serializeMessage } from '@/lib/serializers/chat';
import { createMessage } from '@/lib/services/message';
import { previewManager } from '@/lib/services/preview';
import { streamManager } from '@/lib/services/stream';
import { ensureBaselineEvidenceFiles } from '@/lib/quant/evidence';
import { prefetchQuantDataForRunPlan } from '@/lib/quant/data-prefetch';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace } from '@/lib/quant/workspace';
import type { QuantRunPlan } from '@/lib/quant/workspace';
import { validateQuantArtifactContracts } from '@/lib/quant/artifact-contracts';
import { validateQuantVisualPresentation } from '@/lib/quant/visual-validation';
import { generatedBuildScriptContents, scaffoldBasicNextApp } from '@/lib/utils/scaffold';
import {
  markActiveUserRequestsAsCompleted,
  markUserRequestAsCompleted,
} from '@/lib/services/user-requests';

export type QuantValidationCheckStatus = 'passed' | 'failed' | 'warning';
export type QuantValidationStatus = 'passed' | 'failed';

export interface QuantValidationCheck {
  id: string;
  name: string;
  status: QuantValidationCheckStatus;
  summary: string;
  details?: string;
  durationMs?: number;
  metadata?: Record<string, unknown>;
}

export interface QuantValidationReport {
  schemaVersion: 1;
  runId?: string;
  status: QuantValidationStatus;
  passed: boolean;
  projectId: string;
  reportPath: string;
  checks: QuantValidationCheck[];
  createdAt: string;
  updatedAt: string;
}

export interface QuantValidationRepairStep {
  checkId: string;
  checkName: string;
  summary: string;
  actions: string[];
  details?: string;
}

export interface QuantValidationRepairPlan {
  schemaVersion: 1;
  status: 'needed';
  projectId: string;
  reportPath: string;
  repairPlanPath: string;
  steps: QuantValidationRepairStep[];
  createdAt: string;
}

interface ValidateQuantProjectParams {
  projectId: string;
  projectPath: string;
  requestId?: string | null;
  conversationId?: string | null;
  cliSource?: string | null;
}

interface CommandResult {
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  timedOut: boolean;
  output: string;
}

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const VALIDATION_REPORT_RELATIVE_PATH = '.quantpilot/validation.json';
const VALIDATION_REPAIR_PLAN_RELATIVE_PATH = '.quantpilot/validation-repair-plan.json';
const VALIDATION_STALE_ARTIFACT_PATHS = [
  '.quantpilot/run_plan.json',
  'app/page.tsx',
  'app/globals.css',
  'app/layout.tsx',
  'app/api/market/[...path]/route.ts',
  'data_file/final/dashboard-data.json',
  'evidence/sources.json',
  'evidence/data_quality.json',
  'evidence/image_extraction.json',
  'package.json',
];
const BUILD_TIMEOUT_MS = Number.parseInt(process.env.QUANTPILOT_VALIDATION_BUILD_TIMEOUT_MS ?? '', 10) || 180_000;
const PREVIEW_HTTP_TIMEOUT_MS = Number.parseInt(process.env.QUANTPILOT_VALIDATION_HTTP_TIMEOUT_MS ?? '', 10) || 45_000;
const FETCH_TIMEOUT_MS = 5_000;
const OUTPUT_TAIL_LIMIT = 12_000;
const SENSITIVE_EVIDENCE_PATTERN =
  /(?:sk-(?:proj|ant|cp|live|test)-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,}|(?:authorization|api[_-]?key|auth[_-]?token|cookie|set-cookie)\s*[:=]\s*["']?[a-z0-9._~+/=-]{12,})/i;
const ARTIFACT_POLICY_MAX_FILE_BYTES = 300_000;
const ARTIFACT_POLICY_ROOT_DIRS = ['app', 'components', 'lib', 'src', 'styles'];
const ARTIFACT_POLICY_ROOT_FILES = [
  'package.json',
  'next.config.js',
  'next.config.mjs',
  'postcss.config.js',
  'tailwind.config.js',
  'tailwind.config.ts',
];
const ARTIFACT_POLICY_SKIP_DIRS = new Set([
  '.git',
  '.next',
  '.turbo',
  '.vercel',
  'build',
  'coverage',
  'dist',
  'node_modules',
]);
const ARTIFACT_POLICY_SOURCE_EXTENSIONS = new Set([
  '.css',
  '.html',
  '.js',
  '.jsx',
  '.json',
  '.mjs',
  '.ts',
  '.tsx',
]);
const REMOTE_URL_PATTERN = /\bhttps?:\/\/[a-z0-9.-]+(?::\d+)?[^\s'"`<>){}]*/gi;
const REMOTE_USAGE_PATTERNS: Array<{ label: string; pattern: RegExp }> = [
  { label: '远程脚本', pattern: /<script[^>]+src=["']https?:\/\/[^"']+["']/gi },
  { label: '远程样式', pattern: /<link[^>]+href=["']https?:\/\/[^"']+["']/gi },
  { label: 'CSS 远程资源', pattern: /(?:@import\s+(?:url\()?["']?https?:\/\/|url\(\s*["']?https?:\/\/)[^'")\s]+/gi },
  { label: '远程模块导入', pattern: /(?:\bfrom\s+["']https?:\/\/[^"']+["']|\bimport\s*\(\s*["']https?:\/\/[^"']+["']\s*\))/gi },
  { label: '浏览器直连外部接口', pattern: /\b(?:fetch|new\s+EventSource|new\s+WebSocket)\s*\(\s*["']https?:\/\/[^"']+["']/gi },
  { label: '远程媒体资源', pattern: /<(?:img|source|iframe)[^>]+(?:src|srcSet)=["']https?:\/\/[^"']+["']/gi },
];
const SENSITIVE_ARTIFACT_PATTERNS: Array<{ label: string; pattern: RegExp }> = [
  { label: '明文 API key', pattern: /\b(?:sk|sk-proj|sk-ant|sk-cp)-[a-z0-9_-]{16,}\b/i },
  { label: 'Bearer token', pattern: /\bbearer\s+[a-z0-9._-]{16,}\b/i },
  {
    label: '环境变量密钥字面量',
    pattern: /\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|MINIMAX_API_KEY|CODEX_OPENAI_API_KEY)\s*[:=]\s*["'][^"'\n]{8,}["']/i,
  },
  { label: 'AWS access key', pattern: /\bAKIA[0-9A-Z]{16}\b/ },
];
const MOCK_ARTIFACT_PATTERNS: Array<{ label: string; pattern: RegExp }> = [
  {
    label: 'mock/sample 静态数据变量',
    pattern:
      /\b(?:MOCK|SAMPLE|DEMO|PLACEHOLDER|STATIC)_(?:DATA|QUOTE|QUOTES|KLINE|KLINES|HISTORY|FINANCIALS|REPORTS|ANNOUNCEMENTS|DASHBOARD_DATA)\b/i,
  },
  {
    label: 'mock/sample 静态数据命名',
    pattern:
      /\b(?:mockData|sampleData|demoData|placeholderData|staticQuotes|staticKlines|staticFinancials|staticDashboardData)\b/,
  },
  { label: '示例或模拟数据标记', pattern: /lorem ipsum|假数据|模拟数据|示例数据|样例数据|占位数据/i },
];
const DISCOURAGED_VISUALIZATION_DEPENDENCIES = new Set([
  '@visx/visx',
  'chart.js',
  'd3',
  'echarts',
  'plotly.js',
  'recharts',
]);
const validationQueues = new Map<string, Promise<void>>();

function validationReportPath(projectPath: string) {
  return path.join(projectPath, VALIDATION_REPORT_RELATIVE_PATH);
}

function validationRepairPlanPath(projectPath: string) {
  return path.join(projectPath, VALIDATION_REPAIR_PLAN_RELATIVE_PATH);
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile();
  } catch {
    return false;
  }
}

async function directoryExists(dirPath: string): Promise<boolean> {
  try {
    const stat = await fs.stat(dirPath);
    return stat.isDirectory();
  } catch {
    return false;
  }
}

async function readTextFile(filePath: string): Promise<string | null> {
  try {
    return await fs.readFile(filePath, 'utf8');
  } catch {
    return null;
  }
}

function trimOutput(output: string): string {
  if (output.length <= OUTPUT_TAIL_LIMIT) {
    return output.trim();
  }
  return `...输出已截断，仅保留最后 ${OUTPUT_TAIL_LIMIT} 字符...\n${output.slice(-OUTPUT_TAIL_LIMIT)}`.trim();
}

function pathContains(parentPath: string, childPath: string): boolean {
  const relativePath = path.relative(parentPath, childPath);
  return relativePath === '' || (!relativePath.startsWith('..') && !path.isAbsolute(relativePath));
}

function buildGeneratedProjectEnv(projectPath: string): NodeJS.ProcessEnv {
  const allowedKeys = [
    'PATH',
    'HOME',
    'USER',
    'SHELL',
    'TMPDIR',
    'TEMP',
    'TMP',
    'SystemRoot',
    'ComSpec',
    'PATHEXT',
  ];
  const platformRoot = process.cwd();
  const workspaceRoot = pathContains(platformRoot, projectPath) ? platformRoot : projectPath;
  const env: NodeJS.ProcessEnv = {
    CI: '1',
    NODE_ENV: 'production',
    QUANTPILOT_WORKSPACE_ROOT: workspaceRoot,
    NEXT_PRIVATE_BUILD_WORKER: '1',
    NEXT_TELEMETRY_DISABLED: '1',
  };

  for (const key of allowedKeys) {
    const value = process.env[key];
    if (value) {
      env[key] = value;
    }
  }

  return env;
}

function formatDuration(ms?: number): string {
  if (!ms) return '';
  if (ms < 1_000) return `${ms}ms`;
  return `${(ms / 1_000).toFixed(1)}s`;
}

function isNonEmptyJsonValue(value: unknown): boolean {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return value !== null && value !== undefined && value !== '';
}

function normalizeRelativePath(projectPath: string, filePath: string): string {
  return path.relative(projectPath, filePath).replaceAll(path.sep, '/');
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function validationArtifactSignature(projectPath: string): Promise<string> {
  const signatures = await Promise.all(
    VALIDATION_STALE_ARTIFACT_PATHS.map(async (relativePath) => {
      const absolutePath = path.join(projectPath, relativePath);
      const stat = await fs.stat(absolutePath).catch(() => null);
      if (!stat?.isFile()) {
        return `${relativePath}:missing`;
      }
      return `${relativePath}:${stat.size}:${Math.floor(stat.mtimeMs)}`;
    })
  );
  return signatures.join('|');
}

async function waitForValidationArtifactsToSettle(projectPath: string) {
  const timeoutMs = Number.parseInt(process.env.QUANTPILOT_VALIDATION_SETTLE_TIMEOUT_MS ?? '', 10) || 4_000;
  const intervalMs = 500;
  const startedAt = Date.now();
  let lastSignature = '';
  let stableCount = 0;

  while (Date.now() - startedAt < timeoutMs) {
    const signature = await validationArtifactSignature(projectPath);
    if (signature === lastSignature) {
      stableCount += 1;
      if (stableCount >= 2) {
        return;
      }
    } else {
      lastSignature = signature;
      stableCount = 0;
    }
    await sleep(intervalMs);
  }
}

async function runCommand(
  command: string,
  args: string[],
  cwd: string,
  timeoutMs: number
): Promise<CommandResult> {
  return new Promise((resolve) => {
    let output = '';
    let timedOut = false;
    let settled = false;
    let killTimer: ReturnType<typeof setTimeout> | null = null;

    const child = spawn(command, args, {
      cwd,
      shell: process.platform === 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
      env: buildGeneratedProjectEnv(cwd),
    });

    const append = (chunk: Buffer | string) => {
      output += chunk.toString();
      if (output.length > OUTPUT_TAIL_LIMIT * 2) {
        output = output.slice(-OUTPUT_TAIL_LIMIT);
      }
    };

    const settle = (result: Omit<CommandResult, 'output'>) => {
      if (settled) return;
      settled = true;
      if (killTimer) clearTimeout(killTimer);
      resolve({ ...result, output: trimOutput(output) });
    };

    const timeout = setTimeout(() => {
      timedOut = true;
      append(`\n[QuantPilot validation] 命令超过 ${timeoutMs}ms，正在终止。\n`);
      child.kill('SIGTERM');
      killTimer = setTimeout(() => child.kill('SIGKILL'), 5_000);
    }, timeoutMs);

    child.stdout?.on('data', append);
    child.stderr?.on('data', append);

    child.on('error', (error) => {
      clearTimeout(timeout);
      append(`\n${error instanceof Error ? error.message : String(error)}\n`);
      settle({ exitCode: -1, signal: null, timedOut });
    });

    child.on('close', (exitCode, signal) => {
      clearTimeout(timeout);
      settle({ exitCode, signal, timedOut });
    });
  });
}

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
      cache: 'no-store',
    });
  } finally {
    clearTimeout(timer);
  }
}

async function waitForHttpOk(url: string, timeoutMs: number): Promise<{ status: number; text: string }> {
  const startedAt = Date.now();
  let lastStatus = 0;
  let lastText = '';

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetchWithTimeout(url, { method: 'GET' });
      lastStatus = response.status;
      lastText = await response.text().catch(() => '');
      if (response.ok) {
        return { status: response.status, text: lastText };
      }
    } catch (error) {
      lastText = error instanceof Error ? error.message : String(error);
    }

    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }

  throw new Error(
    lastStatus
      ? `预览地址未返回 2xx，最后状态码：${lastStatus}，响应：${lastText.slice(0, 500)}`
      : `预览地址未在 ${timeoutMs}ms 内返回 HTTP 200：${lastText}`
  );
}

async function safeRunCheck(
  id: string,
  name: string,
  checker: () => Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>>
): Promise<QuantValidationCheck> {
  const startedAt = Date.now();
  const elapsed = () => Math.max(0, Date.now() - startedAt);
  try {
    const result = await checker();
    return {
      id,
      name,
      durationMs: elapsed(),
      ...result,
    };
  } catch (error) {
    return {
      id,
      name,
      status: 'failed',
      summary: `${name}检查异常。`,
      details: error instanceof Error ? error.message : String(error),
      durationMs: elapsed(),
    };
  }
}

async function checkBuild(projectPath: string): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  await normalizeGeneratedProjectForValidation(projectPath);

  const packageJsonPath = path.join(projectPath, 'package.json');
  const packageJsonRaw = await readTextFile(packageJsonPath);
  if (!packageJsonRaw) {
    return {
      status: 'failed',
      summary: '未找到 package.json，无法执行 Next.js build。',
    };
  }

  let packageJson: { scripts?: Record<string, string> };
  try {
    packageJson = JSON.parse(packageJsonRaw) as { scripts?: Record<string, string> };
  } catch (error) {
    return {
      status: 'failed',
      summary: 'package.json 不是有效 JSON。',
      details: error instanceof Error ? error.message : String(error),
    };
  }

  if (!packageJson.scripts?.build) {
    return {
      status: 'failed',
      summary: 'package.json 缺少 build 脚本。',
    };
  }

  const result = await runCommand(npmCommand, ['run', 'build'], projectPath, BUILD_TIMEOUT_MS);
  if (result.exitCode === 0 && !result.timedOut) {
    return {
      status: 'passed',
      summary: 'Next.js build 通过。',
      details: result.output,
    };
  }

  return {
    status: 'failed',
    summary: result.timedOut
      ? `Next.js build 超过 ${formatDuration(BUILD_TIMEOUT_MS)} 未完成。`
      : `Next.js build 失败，退出码：${result.exitCode ?? 'null'}，信号：${result.signal ?? 'none'}。`,
    details: result.output,
  };
}

async function normalizeGeneratedProjectForValidation(projectPath: string) {
  await normalizePostCssConfig(projectPath);
  await normalizeBuildScript(projectPath);
  await normalizeNextConfig(projectPath);
}

async function normalizePostCssConfig(projectPath: string) {
  const postCssPath = path.join(projectPath, 'postcss.config.js');
  const content = await readTextFile(postCssPath);
  if (content === null) {
    return;
  }

  const compact = content.replace(/\s+/g, '');
  const hasPluginsKey = /\bplugins\s*:/.test(content) || compact.includes('"plugins":') || compact.includes("'plugins':");
  const isEmptyExport = /module\.exports\s*=\s*\{\s*\}\s*;?/.test(content) || /export\s+default\s+\{\s*\}\s*;?/.test(content);

  if (hasPluginsKey && !isEmptyExport) {
    return;
  }

  await fs.writeFile(
    postCssPath,
    `module.exports = {
  plugins: [],
};
`,
    'utf8'
  );
}

async function normalizeBuildScript(projectPath: string) {
  const packageJsonPath = path.join(projectPath, 'package.json');
  const raw = await readTextFile(packageJsonPath);
  if (!raw) {
    return;
  }

  let packageJson: Record<string, unknown>;
  try {
    packageJson = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return;
  }

  let changed = false;
  const scripts = packageJson.scripts;
  if (!scripts || typeof scripts !== 'object' || Array.isArray(scripts)) {
    packageJson.scripts = {};
    changed = true;
  }

  const scriptMap = packageJson.scripts as Record<string, unknown>;
  if (
    scriptMap.build !== 'node scripts/run-build.js' &&
    (typeof scriptMap.build !== 'string' || /^next\s+build(?:\s|$)/.test(scriptMap.build))
  ) {
    scriptMap.build = 'node scripts/run-build.js';
    changed = true;
  }
  if (!scriptMap.build) {
    scriptMap.build = 'node scripts/run-build.js';
    changed = true;
  }

  const buildScriptPath = path.join(projectPath, 'scripts', 'run-build.js');
  const buildScript = generatedBuildScriptContents();
  if ((await readTextFile(buildScriptPath)) !== buildScript) {
    await fs.mkdir(path.dirname(buildScriptPath), { recursive: true });
    await fs.writeFile(buildScriptPath, buildScript, 'utf8');
  }

  if (
    !packageJson.dependencies ||
    typeof packageJson.dependencies !== 'object' ||
    Array.isArray(packageJson.dependencies)
  ) {
    packageJson.dependencies = {};
    changed = true;
  }

  const dependencies = packageJson.dependencies as Record<string, unknown>;
  if (dependencies['next-rspack']) {
    delete dependencies['next-rspack'];
    changed = true;
  }

  const devDependencies = packageJson.devDependencies;
  if (
    devDependencies &&
    typeof devDependencies === 'object' &&
    !Array.isArray(devDependencies) &&
    (devDependencies as Record<string, unknown>)['next-rspack']
  ) {
    delete (devDependencies as Record<string, unknown>)['next-rspack'];
    changed = true;
  }

  if (changed) {
    await fs.writeFile(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`, 'utf8');
  }
}

async function normalizeNextConfig(projectPath: string) {
  const configPath = path.join(projectPath, 'next.config.js');
  const content = await readTextFile(configPath);
  const defaultConfig = `/** @type {import('next').NextConfig} */
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = process.env.QUANTPILOT_WORKSPACE_ROOT
  ? path.resolve(process.env.QUANTPILOT_WORKSPACE_ROOT)
  : path.resolve(projectRoot, '../../..');

const nextConfig = {
  turbopack: {
    root: workspaceRoot,
  },
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  typedRoutes: true,
  outputFileTracingRoot: workspaceRoot,
};

module.exports = nextConfig;
`;

  if (content === null || content.trim().length === 0) {
    await fs.writeFile(configPath, defaultConfig, 'utf8');
    return;
  }

  let nextContent = content;
  nextContent = nextContent.replace(
    /(?:const|var|let)\s+withRspack\s*=\s*require\(['"]next-rspack['"]\);\n?/g,
    ''
  );
  nextContent = nextContent.replace(
    /const\s+shouldUseRspack\s*=.*?;\n?/g,
    ''
  );
  nextContent = nextContent.replace(
    /module\.exports\s*=\s*shouldUseRspack\s*\?\s*withRspack\(nextConfig\)\s*:\s*nextConfig\s*;?/g,
    'module.exports = nextConfig;'
  );
  nextContent = nextContent.replace(
    /module\.exports\s*=\s*withRspack\(nextConfig\)\s*;?/g,
    'module.exports = nextConfig;'
  );
  if (!nextContent.includes('const projectRoot = __dirname;')) {
    nextContent = nextContent.replace(
      /\/\*\* @type \{import\(['"]next['"]\)\.NextConfig\} \*\/\n/,
      "/** @type {import('next').NextConfig} */\nconst projectRoot = __dirname;\n"
    );
  }
  if (!nextContent.includes("const path = require('path');")) {
    nextContent = nextContent.replace(
      /\/\*\* @type \{import\(['"]next['"]\)\.NextConfig\} \*\/\n/,
      "/** @type {import('next').NextConfig} */\nconst path = require('path');\n\n"
    );
  }
  if (!nextContent.includes('const workspaceRoot =')) {
    nextContent = nextContent.replace(
      /const projectRoot = __dirname;\n/,
      `const projectRoot = __dirname;
const workspaceRoot = process.env.QUANTPILOT_WORKSPACE_ROOT
  ? path.resolve(process.env.QUANTPILOT_WORKSPACE_ROOT)
  : path.resolve(projectRoot, '../../..');
`
    );
  }
  nextContent = nextContent.replace(/outputFileTracingRoot:\s*projectRoot/g, 'outputFileTracingRoot: workspaceRoot');
  nextContent = nextContent.replace(/root:\s*projectRoot/g, 'root: workspaceRoot');
  if (!nextContent.includes('turbopack:')) {
    nextContent = nextContent.replace(
      /const nextConfig = \{\n/,
      `const nextConfig = {
  turbopack: {
    root: workspaceRoot,
  },
`
    );
  }
  if (!nextContent.includes('allowedDevOrigins')) {
    nextContent = nextContent.replace(
      /const nextConfig = \{\n/,
      `const nextConfig = {
  allowedDevOrigins: ['localhost', '127.0.0.1'],
`
    );
  }

  if (nextContent !== content) {
    await fs.writeFile(configPath, nextContent, 'utf8');
  }
}

async function checkPreviewHttp(
  projectId: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const preview = await previewManager.start(projectId);
  if (!preview.url) {
    return {
      status: 'failed',
      summary: '预览服务未返回可访问 URL。',
      metadata: { preview },
    };
  }

  const response = await waitForHttpOk(preview.url, PREVIEW_HTTP_TIMEOUT_MS);
  return {
    status: 'passed',
    summary: `预览首页 HTTP ${response.status}。`,
    metadata: {
      url: preview.url,
      port: preview.port,
      responsePreview: response.text.slice(0, 400),
    },
  };
}

async function checkVisualPresentation(
  projectPath: string,
  projectId: string,
  requestId?: string | null
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const preview = await previewManager.start(projectId);
  if (!preview.url) {
    return {
      status: 'failed',
      summary: '无法执行视觉验收，因为预览 URL 不存在。',
    };
  }
  const report = await validateQuantVisualPresentation({
    projectPath,
    projectId,
    previewUrl: preview.url,
    requestId,
  });
  if (!report.passed) {
    return {
      status: 'failed',
      summary: `视觉验收未通过：${report.failures.length} 个阻断项。`,
      details: [
        ...report.failures,
        report.viewports.length
          ? `截图：${report.viewports.map((viewport) => `${viewport.id}=${viewport.screenshotPath}`).join('；')}`
          : null,
      ].filter(Boolean).join('\n'),
      metadata: {
        reportPath: report.reportPath,
        screenshotDir: report.screenshotDir,
        viewports: report.viewports.map((viewport) => ({
          id: viewport.id,
          screenshotPath: viewport.screenshotPath,
          metrics: viewport.metrics,
        })),
      },
    };
  }
  return {
    status: report.status === 'warning' ? 'warning' : 'passed',
    summary: report.status === 'warning' ? `视觉验收通过但有 ${report.warnings.length} 个警告。` : '桌面和移动端视觉验收通过。',
    details: report.warnings.length ? report.warnings.join('\n') : undefined,
    metadata: {
      reportPath: report.reportPath,
      screenshotDir: report.screenshotDir,
      viewports: report.viewports.map((viewport) => ({
        id: viewport.id,
        screenshotPath: viewport.screenshotPath,
        metrics: viewport.metrics,
      })),
    },
  };
}

async function checkFinalDataFile(
  projectPath: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const finalDir = path.join(projectPath, 'data_file', 'final');
  if (!(await directoryExists(finalDir))) {
    return {
      status: 'failed',
      summary: '未找到 data_file/final 目录。',
    };
  }

  const preferredPath = path.join(finalDir, 'dashboard-data.json');
  const entries = await fs.readdir(finalDir, { withFileTypes: true }).catch(() => []);
  const jsonFiles = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => path.join(finalDir, entry.name));

  const candidates = [
    ...(await fileExists(preferredPath) ? [preferredPath] : []),
    ...jsonFiles.filter((filePath) => filePath !== preferredPath),
  ];

  if (candidates.length === 0) {
    return {
      status: 'failed',
      summary: 'data_file/final 下没有 JSON 数据文件，预期至少生成 dashboard-data.json。',
    };
  }

  const errors: string[] = [];
  for (const filePath of candidates) {
    const raw = await readTextFile(filePath);
    if (!raw || raw.trim().length <= 2) {
      errors.push(`${normalizeRelativePath(projectPath, filePath)} 为空。`);
      continue;
    }

    try {
      const parsed = JSON.parse(raw) as unknown;
      const runPlan = await readRunPlan(projectPath);
      const plannedSymbols = extractPlannedSymbols(runPlan);
      const fetchedSymbols = extractFetchedSymbols(parsed);
      const comparisonSymbols = extractComparisonSymbols(parsed);
      const missingSymbols = plannedSymbols.filter((symbol) => !fetchedSymbols.includes(symbol));
      const serialized = JSON.stringify(parsed);
      const hasDataShape =
        /quote|quotes|price|symbol|symbols|assets|comparison|secid|history|kline|financial|reports|announcement|source|fetched_at|quote_time|close|open|volume|amount|backtest|equity_curve|trades|strategy|drawdown|win_rate|营收|净利润|毛利率|roe|回测|净值|回撤|胜率/i.test(
          serialized
        );
      const hasPlaceholderSmell = /mock|demo|example|placeholder|lorem|示例|样例|模拟|假数据/i.test(serialized);

      if (!isNonEmptyJsonValue(parsed)) {
        errors.push(`${normalizeRelativePath(projectPath, filePath)} 没有可用数据。`);
        continue;
      }

      if (!hasDataShape) {
        errors.push(`${normalizeRelativePath(projectPath, filePath)} 未检测到行情、K 线、财务或来源字段。`);
        continue;
      }

      if (hasPlaceholderSmell) {
        errors.push(`${normalizeRelativePath(projectPath, filePath)} 疑似包含示例或模拟数据标记。`);
        continue;
      }

      const payloadInspection = inspectDashboardDataPayload(parsed);
      if (!payloadInspection.hasUsableMarketData) {
        errors.push(`${normalizeRelativePath(projectPath, filePath)} 未提取到可用实时行情或 K 线样本。`);
        continue;
      }

      if (missingSymbols.length > 0) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 未覆盖 run_plan 中的全部标的，缺少：${missingSymbols.join('、')}。`
        );
        continue;
      }

      if (plannedSymbols.length > 1) {
        const comparisonMissingSymbols = plannedSymbols.filter((symbol) => !comparisonSymbols.includes(symbol));
        if (comparisonMissingSymbols.length > 0) {
          errors.push(
            `${normalizeRelativePath(projectPath, filePath)} 的 comparison.rows 未覆盖全部对比标的，缺少：${comparisonMissingSymbols.join('、')}。`
          );
          continue;
        }
      }

      const runPlanVisualization = asRecord(runPlan?.visualization);
      const plannedTemplateId = pickString(runPlanVisualization?.templateId);
      const expectedTemplateId = inferExpectedTemplateFromTask(runPlan);
      const visualization = asRecord(asRecord(parsed)?.visualization);
      const finalTemplateId = pickString(visualization?.template_id ?? visualization?.templateId);
      const requiredComponents = Array.isArray(visualization?.required_components)
        ? visualization.required_components
        : Array.isArray(runPlanVisualization?.panels)
          ? runPlanVisualization.panels
          : [];

      if (expectedTemplateId && plannedTemplateId !== expectedTemplateId) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 的任务语义需要 ${expectedTemplateId} 模板，但 run_plan.visualization.templateId=${plannedTemplateId ?? '未设置'}。`
        );
        continue;
      }

      if (expectedTemplateId && finalTemplateId && finalTemplateId !== expectedTemplateId) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 的任务语义需要 ${expectedTemplateId} 模板，但 visualization.template_id=${finalTemplateId}。`
        );
        continue;
      }

      if (plannedTemplateId && !finalTemplateId) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 缺少 visualization.template_id，无法验证场景化看板模板。`
        );
        continue;
      }

      if (plannedTemplateId && finalTemplateId && plannedTemplateId !== finalTemplateId) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 的 visualization.template_id=${finalTemplateId} 与 run_plan=${plannedTemplateId} 不一致。`
        );
        continue;
      }

      if (plannedTemplateId && requiredComponents.length === 0) {
        errors.push(
          `${normalizeRelativePath(projectPath, filePath)} 缺少 visualization.required_components，无法确认页面是否覆盖场景痛点。`
        );
        continue;
      }

      if (plannedTemplateId === 'stock-selection') {
        const record = asRecord(parsed);
        const selectionRanking = asRecord(record?.selectionRanking);
        const financialQuality = asRecord(record?.financialQuality);
        const rankingRows = Array.isArray(selectionRanking?.rows) ? selectionRanking.rows : [];
        const qualityRows = Array.isArray(financialQuality?.rows) ? financialQuality.rows : [];
        const comparisonRows = Array.isArray(asRecord(record?.comparison)?.rows)
          ? asRecord(record?.comparison)?.rows as unknown[]
          : [];
        const missingSelectionData = [
          rankingRows.length === 0 ? 'selectionRanking.rows' : null,
          qualityRows.length === 0 ? 'financialQuality.rows' : null,
          comparisonRows.some((row) => {
            const item = asRecord(row);
            return !item || numeric(item.composite_score) === null || !pickString(item.selection_view);
          }) ? 'comparison.rows[].composite_score/selection_view' : null,
        ].filter((item): item is string => Boolean(item));

        if (missingSelectionData.length > 0) {
          errors.push(
            `${normalizeRelativePath(projectPath, filePath)} 缺少选股模板数据字段：${missingSelectionData.join('、')}。`
          );
          continue;
        }
      }

      if (plannedTemplateId === 'holding-analysis') {
        const record = asRecord(parsed);
        const holdings = Array.isArray(record?.holdings) ? record.holdings : [];
        const assets = Array.isArray(record?.assets) ? record.assets : [];
        const comparisonRows = Array.isArray(asRecord(record?.comparison)?.rows)
          ? asRecord(record?.comparison)?.rows as unknown[]
          : [];
        const missingHoldingData = [
          !asRecord(record?.portfolio) ? 'portfolio' : null,
          holdings.length === 0 ? 'holdings[]' : null,
          assets.length === 0 ? 'assets[]' : null,
          comparisonRows.length === 0 ? 'comparison.rows' : null,
        ].filter((item): item is string => Boolean(item));

        if (missingHoldingData.length > 0) {
          errors.push(
            `${normalizeRelativePath(projectPath, filePath)} 缺少持仓分析模板数据字段：${missingHoldingData.join('、')}。`
          );
          continue;
        }
      }

      return {
        status: 'passed',
        summary: `已找到可用最终数据文件：${normalizeRelativePath(projectPath, filePath)}。`,
        metadata: {
          file: normalizeRelativePath(projectPath, filePath),
          bytes: Buffer.byteLength(raw),
          plannedSymbols,
          fetchedSymbols,
          comparisonSymbols,
          barCount: payloadInspection.barCount,
          hasQuote: payloadInspection.hasQuote,
          visualizationTemplateId: finalTemplateId,
        },
      };
    } catch (error) {
      errors.push(`${normalizeRelativePath(projectPath, filePath)} JSON 解析失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return {
    status: 'failed',
    summary: '最终数据文件存在，但没有通过真实数据形态检查。',
    details: errors.join('\n'),
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function hasAnyKeyDeep(value: unknown, keys: string[]): boolean {
  if (Array.isArray(value)) {
    return value.some((entry) => hasAnyKeyDeep(entry, keys));
  }
  const record = asRecord(value);
  if (!record) {
    return false;
  }
  return Object.entries(record).some(([key, nestedValue]) => keys.includes(key) || hasAnyKeyDeep(nestedValue, keys));
}

function pickString(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function truncatePolicySnippet(value: string, limit = 180): string {
  const compact = value.replace(/\s+/g, ' ').trim();
  if (compact.length <= limit) {
    return compact;
  }
  return `${compact.slice(0, limit)}...`;
}

function isAllowedBackendProxyUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname;
    const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
    return (host === '127.0.0.1' || host === 'localhost') && port === '8000' && parsed.pathname.startsWith('/api/v1/');
  } catch {
    return false;
  }
}

async function collectArtifactPolicyFiles(projectPath: string): Promise<string[]> {
  const files: string[] = [];

  const visit = async (currentPath: string) => {
    const entries = await fs.readdir(currentPath, { withFileTypes: true }).catch(() => []);
    for (const entry of entries) {
      const absolutePath = path.join(currentPath, entry.name);
      if (entry.isDirectory()) {
        if (!ARTIFACT_POLICY_SKIP_DIRS.has(entry.name)) {
          await visit(absolutePath);
        }
        continue;
      }

      if (!entry.isFile()) {
        continue;
      }

      const ext = path.extname(entry.name);
      if (!ARTIFACT_POLICY_SOURCE_EXTENSIONS.has(ext)) {
        continue;
      }

      const stat = await fs.stat(absolutePath).catch(() => null);
      if (!stat || stat.size > ARTIFACT_POLICY_MAX_FILE_BYTES) {
        continue;
      }

      files.push(absolutePath);
    }
  };

  for (const rootDir of ARTIFACT_POLICY_ROOT_DIRS) {
    const absoluteRoot = path.join(projectPath, rootDir);
    if (await directoryExists(absoluteRoot)) {
      await visit(absoluteRoot);
    }
  }

  for (const rootFile of ARTIFACT_POLICY_ROOT_FILES) {
    const absoluteFile = path.join(projectPath, rootFile);
    if (await fileExists(absoluteFile)) {
      files.push(absoluteFile);
    }
  }

  return Array.from(new Set(files));
}

function findRemotePolicyViolations(projectPath: string, filePath: string, content: string): string[] {
  const relativePath = normalizeRelativePath(projectPath, filePath);
  const isMarketProxyRoute =
    relativePath === 'app/api/market/route.ts' ||
    /^app\/api\/market\/.*\/route\.ts$/.test(relativePath);
  const violations: string[] = [];

  for (const usage of REMOTE_USAGE_PATTERNS) {
    usage.pattern.lastIndex = 0;
    const matches = Array.from(content.matchAll(usage.pattern)).slice(0, 3);
    for (const match of matches) {
      const snippet = match[0] ?? '';
      const urls = Array.from(snippet.matchAll(REMOTE_URL_PATTERN)).map((urlMatch) => urlMatch[0]);
      const disallowedUrls = urls.filter((url) => !(isMarketProxyRoute && isAllowedBackendProxyUrl(url)));
      if (disallowedUrls.length > 0) {
        violations.push(`${relativePath} 存在${usage.label}：${truncatePolicySnippet(snippet)}`);
      }
    }
  }

  REMOTE_URL_PATTERN.lastIndex = 0;
  const remoteUrls = Array.from(content.matchAll(REMOTE_URL_PATTERN)).map((match) => match[0]);
  for (const remoteUrl of remoteUrls.slice(0, 8)) {
    if (isMarketProxyRoute && isAllowedBackendProxyUrl(remoteUrl)) {
      continue;
    }

    if (/nextjs\.org|react\.dev|vercel\.com/i.test(remoteUrl) && /package\.json$|next\.config\./.test(relativePath)) {
      continue;
    }

    if (relativePath === 'package.json') {
      continue;
    }

    violations.push(`${relativePath} 存在外部 URL：${remoteUrl}`);
  }

  return Array.from(new Set(violations));
}

function findPatternPolicyViolations(
  projectPath: string,
  filePath: string,
  content: string,
  patterns: Array<{ label: string; pattern: RegExp }>
): string[] {
  const relativePath = normalizeRelativePath(projectPath, filePath);
  const violations: string[] = [];

  for (const { label, pattern } of patterns) {
    pattern.lastIndex = 0;
    const match = pattern.exec(content);
    if (match?.[0]) {
      violations.push(`${relativePath} 存在${label}：${truncatePolicySnippet(match[0])}`);
    }
  }

  return violations;
}

function collectVisualizationDependencyWarnings(projectPath: string, packageRaw: string | null): string[] {
  if (!packageRaw) {
    return [];
  }

  try {
    const parsed = JSON.parse(packageRaw) as Record<string, unknown>;
    const dependencyNames = [
      ...Object.keys(asRecord(parsed.dependencies) ?? {}),
      ...Object.keys(asRecord(parsed.devDependencies) ?? {}),
    ];
    return dependencyNames
      .filter((dependency) => DISCOURAGED_VISUALIZATION_DEPENDENCIES.has(dependency))
      .map(
        (dependency) =>
          `${normalizeRelativePath(projectPath, path.join(projectPath, 'package.json'))} 引入 ${dependency}，生成看板优先使用平台内置 SVG/CSS 图表，避免额外依赖拖慢 build。`
      );
  } catch {
    return [];
  }
}

async function checkArtifactPolicy(
  projectPath: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const requiredArtifacts = [
    '.quantpilot/run_plan.json',
    'app/page.tsx',
    'data_file/final/dashboard-data.json',
    'evidence/sources.json',
    'evidence/data_quality.json',
  ];
  const missingArtifacts: string[] = [];
  for (const relativePath of requiredArtifacts) {
    if (!(await fileExists(path.join(projectPath, relativePath)))) {
      missingArtifacts.push(relativePath);
    }
  }

  const files = await collectArtifactPolicyFiles(projectPath);
  const violations: string[] = [];
  const warnings: string[] = [];

  if (missingArtifacts.length > 0) {
    violations.push(`缺少标准产物：${missingArtifacts.join('、')}。`);
  }

  for (const filePath of files) {
    const relativePath = normalizeRelativePath(projectPath, filePath);
    const content = await readTextFile(filePath);
    if (!content) {
      continue;
    }

    violations.push(...findRemotePolicyViolations(projectPath, filePath, content));
    violations.push(...findPatternPolicyViolations(projectPath, filePath, content, SENSITIVE_ARTIFACT_PATTERNS));

    if (/^(?:app|components|src)\//.test(relativePath)) {
      violations.push(...findPatternPolicyViolations(projectPath, filePath, content, MOCK_ARTIFACT_PATTERNS));
    }
  }

  const pagePath = path.join(projectPath, 'app', 'page.tsx');
  const page = await readTextFile(pagePath);
  if (page && !/data_file\/final\/dashboard-data\.json|data_file\\final\\dashboard-data\.json|\/api\/market/.test(page)) {
    violations.push('app/page.tsx 没有使用标准 final 数据文件或 /api/market 同源接口。');
  }

  const packageRaw = await readTextFile(path.join(projectPath, 'package.json'));
  warnings.push(...collectVisualizationDependencyWarnings(projectPath, packageRaw));

  if (violations.length > 0) {
    return {
      status: 'failed',
      summary: '生成产物未满足 QuantPilot 硬约束。',
      details: violations.slice(0, 20).join('\n'),
      metadata: {
        checkedFiles: files.length,
        violationCount: violations.length,
        warningCount: warnings.length,
      },
    };
  }

  if (warnings.length > 0) {
    return {
      status: 'warning',
      summary: '生成产物满足硬约束，但存在可优化依赖。',
      details: warnings.slice(0, 10).join('\n'),
      metadata: {
        checkedFiles: files.length,
        warningCount: warnings.length,
      },
    };
  }

  return {
    status: 'passed',
    summary: '生成产物满足本地化、真实数据绑定和安全策略。',
    metadata: {
      checkedFiles: files.length,
    },
  };
}

export async function checkQuantArtifactPolicy(projectPath: string): Promise<QuantValidationCheck> {
  return safeRunCheck('artifact_policy', '生成产物策略', () => checkArtifactPolicy(path.resolve(projectPath)));
}

function normalizeTextForIntent(value: unknown): string {
  if (typeof value === 'string') {
    return value.replace(/\s+/g, '');
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeTextForIntent(item)).join('');
  }
  const record = asRecord(value);
  if (record) {
    return Object.values(record).map((item) => normalizeTextForIntent(item)).join('');
  }
  return '';
}

function inferExpectedTemplateFromTask(runPlan: Record<string, unknown> | null): string | null {
  if (!runPlan) {
    return null;
  }

  const capabilityId = pickString(runPlan.capabilityId ?? runPlan.capability_id);
  if (capabilityId === 'portfolio_risk') {
    return 'holding-analysis';
  }

  const taskText = normalizeTextForIntent([
    runPlan.question,
    runPlan.task,
    runPlan.instruction,
    runPlan.clarification,
  ]);
  if (/持仓|仓位|组合|调仓|盈亏|成本|账户|总资产|可用资金|浮动盈亏|持仓截图/.test(taskText)) {
    return 'holding-analysis';
  }

  return null;
}

function pickSymbolCode(value: unknown): string | null {
  if (typeof value === 'string' && /^(?:6|0|3|5)\d{5}$/.test(value.trim())) {
    return value.trim();
  }

  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const candidates = [
    record.symbol,
    record.code,
    record.security_code,
    record.securityCode,
    record.ticker,
    typeof record.secid === 'string' ? record.secid.split('.').at(-1) : null,
  ];

  for (const candidate of candidates) {
    const symbol = pickString(candidate);
    if (symbol && /^(?:6|0|3|5)\d{5}$/.test(symbol)) {
      return symbol;
    }
  }

  return null;
}

async function readRunPlan(projectPath: string): Promise<Record<string, unknown> | null> {
  const raw = await readTextFile(path.join(projectPath, '.quantpilot', 'run_plan.json'));
  if (!raw) {
    return null;
  }
  try {
    return asRecord(JSON.parse(raw));
  } catch {
    return null;
  }
}

function extractPlannedSymbols(runPlan: Record<string, unknown> | null): string[] {
  const symbols = Array.isArray(runPlan?.symbols) ? runPlan.symbols : [];
  return Array.from(
    new Set(
      symbols
        .map((symbol) => pickSymbolCode(symbol))
        .filter((symbol): symbol is string => Boolean(symbol && /^(?:6|0|3|5)\d{5}$/.test(symbol)))
    )
  );
}

function extractFetchedSymbols(data: unknown): string[] {
  const record = asRecord(data);
  if (!record) {
    return [];
  }

  const assets = Array.isArray(record.assets)
    ? record.assets.map(asRecord).filter((asset): asset is Record<string, unknown> => Boolean(asset))
    : [];
  const candidates = assets.length > 0
    ? assets.map((asset) => pickSymbolCode(asset) ?? pickSymbolCode(asRecord(asset.quote)?.symbol))
    : [
        pickSymbolCode(record),
        pickSymbolCode(asRecord(record.quote)),
        ...(Array.isArray(record.symbols) ? record.symbols.map((symbol) => pickSymbolCode(symbol)) : []),
      ];

  return Array.from(
    new Set(candidates.filter((symbol): symbol is string => Boolean(symbol && /^(?:6|0|3|5)\d{5}$/.test(symbol))))
  );
}

function extractComparisonSymbols(data: unknown): string[] {
  const record = asRecord(data);
  if (!record) {
    return [];
  }

  const comparison = asRecord(record.comparison);
  const rows = Array.isArray(comparison?.rows)
    ? comparison.rows
    : Array.isArray(record.comparison)
      ? record.comparison
      : [];

  return Array.from(
    new Set(
      rows
        .map((row) => pickSymbolCode(row))
        .filter((symbol): symbol is string => Boolean(symbol && /^(?:6|0|3|5)\d{5}$/.test(symbol)))
    )
  );
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
}

function extractBarsFromDashboardData(data: unknown): Record<string, unknown>[] {
  const record = asRecord(data);
  if (!record) {
    return [];
  }

  const assets = arrayOfRecords(record.assets);
  if (assets.length > 0) {
    return assets.flatMap((asset) => extractBarsFromDashboardData(asset));
  }

  const kline = asRecord(record.kline) ?? asRecord(record.history) ?? asRecord(record.ohlc);
  const candidates = [
    kline?.bars,
    kline?.data,
    kline?.items,
    record.bars,
    record.klines,
    record.candles,
    record.history,
  ];

  for (const candidate of candidates) {
    const bars = arrayOfRecords(candidate);
    if (bars.length > 0) {
      return bars;
    }
  }

  return [];
}

function hasUsableQuote(data: unknown): boolean {
  const record = asRecord(data);
  if (!record) {
    return false;
  }

  const assets = arrayOfRecords(record.assets);
  if (assets.length > 0) {
    return assets.some(hasUsableQuote);
  }

  const quote = asRecord(record.quote);
  return [
    quote?.price,
    quote?.latest,
    quote?.latest_price,
    quote?.close,
    record.price,
    record.latest,
    record.latest_price,
  ].some((value) => numeric(value) !== null);
}

function inspectDashboardDataPayload(data: unknown) {
  const bars = extractBarsFromDashboardData(data);
  const hasQuote = hasUsableQuote(data);
  const fetchedSymbols = extractFetchedSymbols(data);

  return {
    hasQuote,
    barCount: bars.length,
    fetchedSymbols,
    hasUsableMarketData: hasQuote || bars.length > 0,
  };
}

async function ensurePrefetchedFinalData(projectPath: string) {
  const runPlan = await readRunPlan(projectPath);
  if (!runPlan) {
    return;
  }

  const raw = await readTextFile(path.join(projectPath, 'data_file', 'final', 'dashboard-data.json'));
  let parsed: unknown = null;
  try {
    parsed = raw ? JSON.parse(raw) : null;
  } catch {
    parsed = null;
  }

  const inspection = inspectDashboardDataPayload(parsed);
  const plannedSymbols = extractPlannedSymbols(runPlan);
  const missingSymbols = plannedSymbols.filter((symbol) => !inspection.fetchedSymbols.includes(symbol));
  if (raw && inspection.hasUsableMarketData && missingSymbols.length === 0) {
    return;
  }

  try {
    await prefetchQuantDataForRunPlan({
      projectPath,
      plan: runPlan as unknown as QuantRunPlan,
    });
  } catch (error) {
    console.warn(
      '[QuantValidation] Failed to prefetch final dashboard data before validation:',
      error
    );
  }
}

type EvidenceJsonResult =
  | { ok: true; parsed: unknown; raw: string; absolutePath: string }
  | { ok: false; error: string; absolutePath: string };

async function readEvidenceJson(
  projectPath: string,
  relativePath: string
): Promise<EvidenceJsonResult> {
  const absolutePath = path.join(projectPath, relativePath);
  const raw = await readTextFile(absolutePath);
  if (!raw) {
    return { ok: false, error: `未找到或为空：${relativePath}`, absolutePath };
  }
  try {
    return { ok: true, parsed: JSON.parse(raw), raw, absolutePath };
  } catch (error) {
    return {
      ok: false,
      error: `${relativePath} JSON 解析失败：${error instanceof Error ? error.message : String(error)}`,
      absolutePath,
    };
  }
}

async function checkEvidenceFiles(
  projectPath: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const baseline = await ensureBaselineEvidenceFiles(projectPath);
  const sources = await readEvidenceJson(projectPath, path.join('evidence', 'sources.json'));
  const quality = await readEvidenceJson(projectPath, path.join('evidence', 'data_quality.json'));
  const errors: string[] = [];

  if (!sources.ok || !quality.ok) {
    const fileErrors = [
      sources.ok ? null : sources.error,
      quality.ok ? null : quality.error,
    ].filter((error): error is string => Boolean(error));
    return {
      status: 'failed',
      summary: '缺少数据信源渠道或数据质量证据文件。',
      details: fileErrors.join('\n'),
    };
  }

  const sourcesRaw = sources.raw;
  const qualityRaw = quality.raw;
  const combined = `${sourcesRaw}\n${qualityRaw}`;
  if (SENSITIVE_EVIDENCE_PATTERN.test(combined)) {
    return {
      status: 'failed',
      summary: 'evidence 文件疑似包含敏感信息。',
      details: '请移除任何鉴权凭据、会话凭据或密钥值，仅保留数据信源渠道、端点、时间戳和质量摘要。',
    };
  }

  const sourceEntries = asRecord(sources.parsed)?.sources;
  if (!Array.isArray(sourceEntries) || sourceEntries.length === 0) {
    errors.push('evidence/sources.json 必须包含非空 sources 数组。');
  }

  const serializedSources = JSON.stringify(sources.parsed);
  if (!/source|eastmoney|tencent|endpoint|fetched_at|as_of|quote_time|artifact_path/i.test(serializedSources)) {
    errors.push('evidence/sources.json 未检测到 source、endpoint、fetched_at/as_of 或 artifact_path 等来源字段。');
  }

  const qualityRecord = asRecord(quality.parsed);
  const qualityStatus = typeof qualityRecord?.status === 'string' ? qualityRecord.status : null;
  if (!qualityStatus || !['ok', 'warning', 'error'].includes(qualityStatus)) {
    errors.push('evidence/data_quality.json 必须包含 status，取值为 ok、warning 或 error。');
  }

  const hasQualitySignals =
    hasAnyKeyDeep(quality.parsed, ['datasets', 'checks', 'missing_fields', 'warnings', 'limitations', 'row_count', 'fetched_at']) ||
    /row_count|missing_fields|warnings|limitations|fetched_at|样本|缺失|限制/i.test(JSON.stringify(quality.parsed));
  if (!hasQualitySignals) {
    errors.push('evidence/data_quality.json 未检测到数据集、检查项、缺失字段、警告或限制说明。');
  }

  if (errors.length > 0) {
    return {
      status: 'failed',
      summary: '数据信源渠道或质量证据不完整。',
      details: errors.join('\n'),
    };
  }

  const warningSummary = qualityStatus === 'warning' ? '数据质量存在警告，页面应展示限制说明。' : undefined;
  return {
    status: qualityStatus === 'error' ? 'failed' : qualityStatus === 'warning' ? 'warning' : 'passed',
    summary: baseline.created
      ? `已根据最终数据自动生成数据信源渠道和质量证据文件，状态：${qualityStatus}。`
      : warningSummary ?? '已找到数据信源渠道和质量证据文件。',
    metadata: {
      sources: 'evidence/sources.json',
      dataQuality: 'evidence/data_quality.json',
      qualityStatus,
      sourceCount: Array.isArray(sourceEntries) ? sourceEntries.length : 0,
      baselineCreated: baseline.created,
      baselineReason: baseline.reason,
    },
  };
}

async function checkDashboardBinding(
  projectPath: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const pagePath = path.join(projectPath, 'app', 'page.tsx');
  const page = await readTextFile(pagePath);
  if (!page) {
    return {
      status: 'failed',
      summary: '未找到 app/page.tsx。',
    };
  }

  const defaultPageSignals = [
    'Get started by editing',
    'Learn →',
    'Examples →',
    'Next.js →',
  ];
  if (defaultPageSignals.some((signal) => page.includes(signal))) {
    return {
      status: 'failed',
      summary: 'app/page.tsx 仍包含 Next.js 默认页内容。',
    };
  }

  const bindingSignals = [
    '/api/market',
    'dashboard-data.json',
    'data_file/final',
    'data_file\\final',
    'fetch(',
  ];
  const hasBindingSignal = bindingSignals.some((signal) => page.includes(signal));
  const hardcodedDataSignals = [
    /const\s+DASHBOARD_DATA\s*[:=]\s*\{/,
    /const\s+(?:STATIC_|MOCK_|SAMPLE_)?(?:QUOTE|QUOTES|HISTORY|KLINE|KLINES|FINANCIALS|REPORTS|ANNOUNCEMENTS|DASHBOARD_DATA)\s*[:=]\s*(?:\[|\{)/,
    /(?:bars|reports|announcements)\s*:\s*\[\s*\{[\s\S]{0,80}(?:open|close|report_date|notice_date|title)\s*:/,
  ];
  const hasStaticSmell =
    hardcodedDataSignals.some((signal) => signal.test(page)) ||
    (page.match(/(?:trade_date|report_date|notice_date|change_percent)\s*:/g)?.length ?? 0) > 30;
  const runPlan = await readRunPlan(projectPath);
  const plannedSymbols = extractPlannedSymbols(runPlan);
  const finalDataRaw = await readTextFile(path.join(projectPath, 'data_file', 'final', 'dashboard-data.json'));
  let finalData: unknown = null;
  try {
    finalData = finalDataRaw ? JSON.parse(finalDataRaw) : null;
  } catch {
    finalData = null;
  }
  const finalDataRecord = asRecord(finalData);
  const assetRows = Array.isArray(finalDataRecord?.assets) ? finalDataRecord.assets : [];
  const fetchedSymbols = extractFetchedSymbols(finalData);
  const payloadInspection = inspectDashboardDataPayload(finalData);
  const isMultiSymbolTask = plannedSymbols.length > 1 || assetRows.length > 1;
  const runPlanVisualization = asRecord(runPlan?.visualization);
  const plannedTemplateId = pickString(runPlanVisualization?.templateId);
  const expectedTemplateId = inferExpectedTemplateFromTask(runPlan);
  const requiredPanels = Array.isArray(runPlanVisualization?.panels)
    ? runPlanVisualization.panels.map((panel) => pickString(panel)).filter((panel): panel is string => Boolean(panel))
    : [];

  if (!hasBindingSignal) {
    return {
      status: 'failed',
      summary: '页面未检测到数据文件或同源行情 API 绑定。',
      details: 'app/page.tsx 应读取 data_file/final/dashboard-data.json，或通过 /api/market/** 获取真实数据。',
    };
  }

  if (hasStaticSmell) {
    return {
      status: 'failed',
      summary: '页面疑似直接硬编码大段行情/财务数据，未形成可复用的数据绑定。',
      details: '请让 app/page.tsx 读取 data_file/final/dashboard-data.json，或通过 /api/market/** 获取数据；不要把完整数据对象内联到页面代码。',
    };
  }

  if (!payloadInspection.hasUsableMarketData) {
    return {
      status: 'failed',
      summary: '页面数据入口存在，但最终数据无法映射出实时行情或 K 线样本。',
      details: '请先生成可用 data_file/final/dashboard-data.json；其中至少应包含 quote.price 或 kline.bars/history.bars 等字段。',
      metadata: payloadInspection,
    };
  }

  const hasStandardBinding =
    /function\s+getBars\(|extractBarsFromDashboardData|data-source-file=\{DATA_FILE\}|data_file\/final\/dashboard-data\.json/.test(page);
  if (!hasStandardBinding) {
    return {
      status: 'failed',
      summary: '页面未使用 QuantPilot 标准看板数据绑定结构。',
      details: '请使用平台标准模板读取 dashboard-data.json，并通过统一解析层渲染最新价、K 线样本、指标、财务和公告。',
    };
  }

  if (expectedTemplateId && plannedTemplateId !== expectedTemplateId) {
    return {
      status: 'failed',
      summary: `执行计划模板与任务语义不一致，应使用 ${expectedTemplateId}。`,
      details: `当前 run_plan.visualization.templateId=${plannedTemplateId ?? '未设置'}。持仓、调仓、截图账户类任务必须走持仓分析模板，不能复用个股诊断模板。`,
      metadata: {
        expectedTemplateId,
        plannedTemplateId,
      },
    };
  }

  const finalTemplateId = pickString(asRecord(finalDataRecord?.visualization)?.template_id ?? asRecord(finalDataRecord?.visualization)?.templateId);
  if (expectedTemplateId && finalTemplateId && finalTemplateId !== expectedTemplateId) {
    return {
      status: 'failed',
      summary: `最终数据模板与任务语义不一致，应使用 ${expectedTemplateId}。`,
      details: `当前 data_file/final/dashboard-data.json visualization.template_id=${finalTemplateId}。`,
      metadata: {
        expectedTemplateId,
        finalTemplateId,
      },
    };
  }

  if (isMultiSymbolTask) {
    const dataDrivenCoverage =
      /requestedSymbols|assets|comparison/.test(page) &&
      plannedSymbols.every((symbol) => fetchedSymbols.includes(symbol));
    const missingPageSymbols = dataDrivenCoverage
      ? []
      : plannedSymbols.filter((symbol) => !page.includes(symbol));
    const hasComparisonBinding = /assets|comparison|requestedSymbols|assetCount|对比|相对强弱|多标的|收益对比|回撤对比|波动/.test(page);
    if (missingPageSymbols.length > 0 || !hasComparisonBinding) {
      return {
        status: 'failed',
        summary: '页面未完整绑定多标的对比数据。',
        details: [
          missingPageSymbols.length > 0 ? `页面未显式覆盖标的：${missingPageSymbols.join('、')}。` : null,
          !hasComparisonBinding ? '页面未检测到 assets[]、comparison 或多标的对比展示逻辑。' : null,
        ].filter(Boolean).join('\n'),
        metadata: {
          plannedSymbols,
          fetchedSymbols,
          assetCount: assetRows.length,
        },
      };
    }
  }

	  if (plannedTemplateId) {
	    const serializedPage = page.toLowerCase();
	    const serializedFinal = JSON.stringify(finalData ?? {}).toLowerCase();
	    const templateChecks: Record<string, { label: string; patterns: RegExp[] }> = {
      'holding-analysis': {
        label: '持仓分析模板',
        patterns: [/持仓|holding|portfolio|仓位|集中度/, /调仓|风险|相关性|流动性|回撤/],
      },
	      'stock-selection': {
	        label: '选股分析模板',
	        patterns: [
	          /stock-selection|选股|候选|多标的|comparison|assets/,
	          /selectionranking|financialquality|排名|相对强弱|研究优先级/,
	          /收益对比|波动对比|回撤对比|财务质量|(?:数据来源|数据信源|信源渠道)逐项追踪/,
	        ],
	      },
      'single-stock-diagnosis': {
        label: '个股诊断模板',
        patterns: [/个股|行情|最新价|quote|k\s*线|k线/, /财务|公告|(?:数据来源|数据信源|信源渠道)|质量/],
      },
      'technical-timing': {
        label: '技术择时模板',
        patterns: [/k\s*线|k线|均线|ma20|ma60|成交量/, /触发|失效|趋势|回撤|波动/],
      },
      'fundamental-research': {
        label: '基本面研究模板',
        patterns: [/财务|基本面|营收|净利润|roe|毛利率/, /报告期|现金流|公告|估值/],
      },
      'backtest-review': {
        label: '回测复盘模板',
        patterns: [/回测|净值|策略|胜率|交易/, /参数|回撤|样本|限制/],
      },
      'sector-rotation': {
        label: '板块轮动模板',
        patterns: [/板块|行业|指数|etf|轮动|相对强弱/, /收益|回撤|流动性|排名/],
      },
    };
    const templateCheck = templateChecks[plannedTemplateId];
    const missingSignals = templateCheck?.patterns
      .filter((pattern) => !pattern.test(page) && !pattern.test(serializedPage) && !pattern.test(serializedFinal))
      .map((pattern) => pattern.source) ?? [];

	    if (templateCheck && missingSignals.length > 0) {
	      return {
	        status: 'failed',
        summary: `页面未体现 ${templateCheck.label} 的关键组件。`,
        details: [
          `run_plan.visualization.templateId=${plannedTemplateId}`,
          requiredPanels.length ? `必备组件：${requiredPanels.join('、')}` : null,
          `缺少信号：${missingSignals.join('；')}`,
        ].filter(Boolean).join('\n'),
	      };
	    }

	    if (plannedTemplateId === 'holding-analysis') {
	      const oversizedHeroSignals = [
	        /hero-band/,
	        /risk-card/,
	        /holding-analysis\s*持仓分析模板/i,
	        /持仓问题快速诊断/,
	      ];
	      if (oversizedHeroSignals.some((signal) => signal.test(page))) {
	        return {
	          status: 'failed',
	          summary: '持仓分析页面仍使用过重的顶部 hero 结构。',
	          details: '持仓、调仓和截图账户类看板应直接从账户摘要、持仓矩阵或核心风险指标开始；VaR、样本口径和声明应放入指标卡、风险面板或底部说明，不要占据首屏顶部。',
	        };
	      }
	    }

	    if (plannedTemplateId === 'stock-selection') {
	      const holdingOnlySignals = [
	        /持仓矩阵/,
	        /仓位与集中度/,
	        /调仓优先级/,
	        /portfolio[_-]?risk/i,
	        /holding-analysis/i,
	      ];
	      if (holdingOnlySignals.some((signal) => signal.test(page))) {
	        return {
	          status: 'failed',
	          summary: '页面仍残留持仓分析模板，不符合选股/多股对比任务。',
	          details: 'stock-selection 页面应展示候选覆盖、排名依据、财务质量、收益/波动/回撤对比和数据信源渠道逐项追踪。',
	        };
	      }
	    }
	  }

  return {
    status: 'passed',
    summary: '页面已检测到真实数据绑定入口。',
    metadata: {
      signals: bindingSignals.filter((signal) => page.includes(signal)),
    },
  };
}

async function checkChartPresence(
  projectPath: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const pagePath = path.join(projectPath, 'app', 'page.tsx');
  const page = await readTextFile(pagePath);
  if (!page) {
    return {
      status: 'failed',
      summary: '未找到 app/page.tsx，无法检查图表。',
    };
  }

  const styleFiles = await Promise.all([
    readTextFile(path.join(projectPath, 'app', 'globals.css')),
    readTextFile(path.join(projectPath, 'styles', 'globals.css')),
    readTextFile(path.join(projectPath, 'src', 'app', 'globals.css')),
  ]);
  const visualSource = [page, ...styleFiles.filter(Boolean)].join('\n');
  const hasGraphicElement = /<svg|<canvas|<polyline|<rect|<path|Chart|chart|candlestick|ohlc|K线|K 线|折线|柱状|趋势图/i.test(page);
  const hasFinanceOrMarketLanguage = /成交量|成交额|均线|MA5|MA10|MA20|K线|K 线|营收|净利润|ROE|毛利率|回撤|波动率|quote|history|financial/i.test(page);
  const hasSemanticColoring = /red|green|up|down|gain|loss|risk-(?:high|mid|low)|dot\s+(?:red|green|amber)|candle-up|candle-down|volume-up|volume-down|bar-up|bar-down|quality-(?:ok|warning|error)|signal-(?:up|down)|#d9363e|#15945b|#dc2626|#16a34a/i.test(visualSource);
  const hasChartReadingAid = /<title>|<desc>|aria-label|chart-label|axis|grid|legend|tooltip|刻度|图例|坐标|日期/i.test(page);
  const runPlan = await readRunPlan(projectPath);
  const plannedSymbols = extractPlannedSymbols(runPlan);
  const finalDataRaw = await readTextFile(path.join(projectPath, 'data_file', 'final', 'dashboard-data.json'));
  const hasMultiFinalData = Boolean(finalDataRaw && /"assets"\s*:|"comparison"\s*:/.test(finalDataRaw));
  const isMultiSymbolTask = plannedSymbols.length > 1 || hasMultiFinalData;
  const plannedTemplateId = pickString(asRecord(runPlan?.visualization)?.templateId);

  if (!hasGraphicElement || !hasFinanceOrMarketLanguage) {
    return {
      status: 'failed',
      summary: '未检测到有效金融图表实现。',
      details: '页面至少应包含 SVG/canvas/图表组件，并展示 K 线、成交量、均线、财务趋势或风险指标。',
    };
  }

  if (!hasSemanticColoring || !hasChartReadingAid) {
    return {
      status: 'failed',
      summary: '金融图表缺少语义染色或读图辅助。',
      details: '页面需要为涨跌、风险、质量状态提供明确颜色，并给 SVG/canvas 图表提供坐标/图例/tooltip/title 等读图辅助。',
      metadata: {
        hasSemanticColoring,
        hasChartReadingAid,
      },
    };
  }

  if (isMultiSymbolTask && !/对比|相对强弱|多标的|矩阵|收益|波动|回撤|comparison|assets/i.test(page)) {
    return {
      status: 'failed',
      summary: '多标的任务未检测到对比图表或对比指标展示。',
      details: '页面需要展示多标的指标矩阵、收益对比、波动/回撤对比或相对强弱摘要。',
      metadata: {
        plannedSymbols,
      },
    };
  }

  if (
    plannedTemplateId === 'stock-selection' &&
    !/selectionRanking|financialQuality|stock-selection|相对强弱与排名依据|财务质量|收益对比图|波动对比图|回撤对比图/.test(page)
  ) {
    return {
      status: 'failed',
      summary: '选股任务未检测到场景化选股图表组件。',
      details: '页面需要展示相对强弱/排名依据、财务质量、收益对比图、波动对比图或回撤对比图。',
      metadata: {
        plannedSymbols,
        plannedTemplateId,
      },
    };
  }

  return {
    status: 'passed',
    summary: '已检测到金融图表相关实现。',
  };
}

async function checkMarketProxy(
  projectPath: string,
  projectId: string
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const marketDir = path.join(projectPath, 'app', 'api', 'market');
  const marketEntries = await fs.readdir(marketDir).catch(() => []);
  const escapedRouteEntry = marketEntries.find((entry) => entry.includes('\\[') || entry.includes('\\]'));
  if (escapedRouteEntry) {
    return {
      status: 'failed',
      summary: '/api/market 动态路由目录名称不正确。',
      details: `检测到目录 ${path.posix.join('app/api/market', escapedRouteEntry)}。请使用 app/api/market/[...path]/route.ts，不要在目录名中写入反斜杠。`,
    };
  }

  const routeCandidates = [
    path.join(projectPath, 'app', 'api', 'market', '[...path]', 'route.ts'),
    path.join(projectPath, 'app', 'api', 'market', '[[...path]]', 'route.ts'),
    path.join(projectPath, 'app', 'api', 'market', 'route.ts'),
  ];
  const routePath = await routeCandidates.reduce<Promise<string | null>>(async (previous, candidate) => {
    const found = await previous;
    if (found) return found;
    return (await fileExists(candidate)) ? candidate : null;
  }, Promise.resolve(null));

  if (!routePath) {
    return {
      status: 'failed',
      summary: '未找到 /api/market 同源代理 route。',
      details: '请在生成项目中创建 app/api/market/[...path]/route.ts，并转发到 http://127.0.0.1:8000/api/v1/**。',
    };
  }

  const preview = await previewManager.start(projectId);
  if (!preview.url) {
    return {
      status: 'failed',
      summary: '无法检查 /api/market 代理，因为预览 URL 不存在。',
      metadata: { route: normalizeRelativePath(projectPath, routePath) },
    };
  }

  const probeUrl = new URL('/api/market/quotes/realtime/600519', preview.url).toString();
  const response = await fetchWithTimeout(probeUrl, { method: 'GET' }, 8_000);
  const responseText = await response.text().catch(() => '');
  if (!response.ok) {
    return {
      status: 'failed',
      summary: `/api/market 代理未返回 2xx，状态码：${response.status}。`,
      details: responseText.slice(0, 1_000),
      metadata: {
        route: normalizeRelativePath(projectPath, routePath),
        probeUrl,
      },
    };
  }

  let parsed: unknown = null;
  try {
    parsed = JSON.parse(responseText);
  } catch {
    // 非 JSON 响应也会在下面的数据形态检查失败。
  }

  const serialized = parsed ? JSON.stringify(parsed) : responseText;
  if (!/600519|贵州茅台|price|symbol|quote|latest|fetched_at|source/i.test(serialized)) {
    return {
      status: 'failed',
      summary: '/api/market 代理返回了 2xx，但响应不像真实行情数据。',
      details: responseText.slice(0, 1_000),
      metadata: {
        route: normalizeRelativePath(projectPath, routePath),
        probeUrl,
      },
    };
  }

  return {
    status: 'passed',
    summary: '/api/market 同源代理可用，实时行情探测通过。',
    metadata: {
      route: normalizeRelativePath(projectPath, routePath),
      probeUrl,
    },
  };
}

async function checkArtifactContracts(
  projectPath: string,
  projectId: string,
  requestId?: string | null
): Promise<Omit<QuantValidationCheck, 'id' | 'name' | 'durationMs'>> {
  const report = await validateQuantArtifactContracts({
    projectPath,
    projectId,
    requestId,
  });
  const failed = report.checks.filter((check) => check.status === 'failed');
  const warnings = report.checks.filter((check) => check.status === 'warning');
  if (failed.length > 0) {
    return {
      status: 'failed',
      summary: `产物契约未通过：${failed.length} 个结构性问题。`,
      details: failed.map((check) => `${check.label}：${check.summary}${check.details ? `\n${check.details}` : ''}`).join('\n\n'),
      metadata: {
        reportPath: report.reportPath,
        failed: failed.map((check) => check.id),
      },
    };
  }
  return {
    status: warnings.length > 0 ? 'warning' : 'passed',
    summary: warnings.length > 0 ? `产物契约通过但有 ${warnings.length} 个警告。` : '关键 JSON 产物契约通过。',
    metadata: {
      reportPath: report.reportPath,
      warningCount: warnings.length,
    },
  };
}

async function writeValidationReport(projectPath: string, report: QuantValidationReport) {
  await ensureQuantWorkspace(projectPath);
  await fs.writeFile(validationReportPath(projectPath), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
}

function actionsForFailedCheck(check: QuantValidationCheck): string[] {
  const common = [
    '只修改当前生成项目目录内的文件。',
    '保留已经获取到的真实数据，不要改成 mock 或静态样例。',
  ];

  switch (check.id) {
    case 'next_build':
      return [
        ...common,
        '运行或根据报告修复 TypeScript、Next.js、CSS 或依赖错误。',
        '动态 JSON 字段必须使用 JsonRecord、asRecord、asArray、numeric 等守卫函数处理。',
        '不要通过新增大型图表依赖绕开类型问题。',
      ];
    case 'preview_http_200':
      return [
        ...common,
        '确认 app/page.tsx、app/layout.tsx、app/globals.css 和 package.json 能让 Next.js 预览启动。',
        '修复运行时异常、端口预览错误或页面加载时抛出的异常。',
      ];
    case 'visual_presentation':
      return [
        ...common,
        '查看 .quantpilot/visual-validation.json 和 tmp/visual-checks 下的截图。',
        '修复桌面/移动端布局：首屏不能空白，不能横向溢出，文本不能互相遮挡。',
        '补齐真实金融语义和图表元素：K 线、成交量、财务趋势、持仓/风险或回测图表必须按任务展示。',
        '页面需要显示数据信源、更新时间或 dashboard-data.json 绑定说明。',
      ];
    case 'final_data_file':
      return [
        ...common,
        '生成或修复 data_file/final/dashboard-data.json。',
        '确保 final 数据包含 quote.price 或 kline.bars/history.bars 等真实行情字段。',
        '多标的任务必须覆盖 run_plan.symbols 中的全部代码，并写入 assets[] 与 comparison.rows[]。',
      ];
    case 'evidence_files':
      return [
        ...common,
        '生成 evidence/sources.json，记录 source、endpoint、fetched_at/as_of、样本量和 artifact_path。',
        '生成 evidence/data_quality.json，记录 status、datasets/checks、缺失字段、警告和限制。',
        '不要把鉴权凭据、会话凭据或密钥值写入 evidence。',
      ];
    case 'artifact_contracts':
      return [
        ...common,
        '查看 .quantpilot/artifact-contracts.json 中失败的契约项。',
        '修复 .quantpilot/run_plan.json、.quantpilot/generation-state.json、evidence/*.json 或 data_file/final/dashboard-data.json 的结构字段。',
        '不要只让页面 build 通过；关键 JSON 产物必须满足平台契约，后续健康检查和链路观测依赖这些字段。',
      ];
    case 'artifact_policy':
      return [
        ...common,
        '移除外部 CDN、远程脚本、远程样式、远程字体、远程媒体和浏览器直连外部 API。',
        '页面资源必须本地化；浏览器取数只能读取 data_file/final/dashboard-data.json 或同源 /api/market/**。',
        '移除 MOCK_DATA、SAMPLE_DATA、STATIC_QUOTES、示例数据、模拟数据、占位数据和明文密钥。',
      ];
    case 'dashboard_data_binding':
      return [
        ...common,
        '让 app/page.tsx 使用 QuantPilot 标准数据绑定结构读取 data_file/final/dashboard-data.json。',
        '保留 DATA_FILE、readDashboardData()、getBars() 或 data-source-file={DATA_FILE} 等标准入口。',
        '不要把完整行情、K 线、财务或公告对象内联到页面代码。',
      ];
    case 'chart_presence':
      return [
        ...common,
        '补齐真实金融图表：K 线/OHLC、成交量、均线、财务趋势、收益/回撤/波动或风险指标。',
        '图表必须有语义染色、坐标/图例/tooltip/title 等读图辅助。',
        '多标的任务必须展示对比矩阵、收益对比、波动/回撤或相对强弱摘要。',
      ];
    case 'market_proxy':
      return [
        ...common,
        '创建 app/api/market/[...path]/route.ts。',
        '将 /api/market/** 转发到 http://127.0.0.1:8000/api/v1/** 并保留 query 参数。',
        '前端刷新行情时调用 /api/market/**，不要从浏览器直连 8000 或外部接口。',
      ];
    default:
      return [
        ...common,
        '根据失败详情修复对应产物，并重新确保 build、HTTP、数据、evidence、图表和代理检查通过。',
      ];
  }
}

export function buildQuantValidationRepairPlan(report: QuantValidationReport): QuantValidationRepairPlan {
  const failedChecks = report.checks.filter((check) => check.status === 'failed');
  return {
    schemaVersion: 1,
    status: 'needed',
    projectId: report.projectId,
    reportPath: report.reportPath,
    repairPlanPath: VALIDATION_REPAIR_PLAN_RELATIVE_PATH,
    steps: failedChecks.map((check) => ({
      checkId: check.id,
      checkName: check.name,
      summary: check.summary,
      actions: actionsForFailedCheck(check),
      ...(check.details ? { details: truncateForPrompt(check.details, 1_000) } : {}),
    })),
    createdAt: new Date().toISOString(),
  };
}

async function writeValidationRepairPlan(projectPath: string, report: QuantValidationReport) {
  const repairPlanPath = validationRepairPlanPath(projectPath);
  if (report.passed) {
    await fs.rm(repairPlanPath, { force: true }).catch(() => undefined);
    return;
  }

  await ensureQuantWorkspace(projectPath);
  const plan = buildQuantValidationRepairPlan(report);
  await fs.writeFile(repairPlanPath, `${JSON.stringify(plan, null, 2)}\n`, 'utf8');
}

function buildValidationSummary(report: QuantValidationReport): string {
  const passedCount = report.checks.filter((check) => check.status === 'passed').length;
  const failedChecks = report.checks.filter((check) => check.status === 'failed');
  const warningChecks = report.checks.filter((check) => check.status === 'warning');
  const headline = report.passed
    ? `自动验证通过：${passedCount}/${report.checks.length} 项检查通过。`
    : `自动验证未通过：${passedCount}/${report.checks.length} 项检查通过，${failedChecks.length} 项失败。`;

  const lines = [
    headline,
    '',
    ...report.checks.map((check) => {
      const mark = check.status === 'passed' ? '通过' : check.status === 'warning' ? '警告' : '失败';
      const duration = check.durationMs ? `（${formatDuration(check.durationMs)}）` : '';
      return `- ${mark}：${check.name}${duration} - ${check.summary}`;
    }),
    '',
    `验证报告：${report.reportPath}`,
  ];

  if (!report.passed) {
    lines.push(`修复计划：${VALIDATION_REPAIR_PLAN_RELATIVE_PATH}`);
  }

  if (warningChecks.length > 0) {
    lines.push(`警告项：${warningChecks.map((check) => check.name).join('、')}`);
  }

  return lines.join('\n');
}

function truncateForPrompt(value: string, limit = 1_500): string {
  const trimmed = value.trim();
  if (trimmed.length <= limit) {
    return trimmed;
  }
  return `${trimmed.slice(0, limit)}\n...内容已截断...`;
}

export function buildQuantValidationRepairInstruction(
  report: QuantValidationReport,
  options: { originalInstruction?: string } = {}
): string {
  const failedChecks = report.checks.filter((check) => check.status === 'failed');
  const repairPlan = buildQuantValidationRepairPlan(report);
  const failedSummary = failedChecks
    .map((check, index) => {
      const details = check.details ? `\n   细节：${truncateForPrompt(check.details)}` : '';
      return `${index + 1}. ${check.name}（${check.id}）：${check.summary}${details}`;
    })
    .join('\n');
  const repairSteps = repairPlan.steps
    .map((step, index) => {
      const actions = step.actions.map((action, actionIndex) => `   ${actionIndex + 1}. ${action}`).join('\n');
      return `${index + 1}. ${step.checkName}（${step.checkId}）\n${actions}`;
    })
    .join('\n');

  const original = options.originalInstruction
    ? `\n原始用户需求：\n${truncateForPrompt(options.originalInstruction, 1_000)}\n`
    : '';

  return `QuantPilot 自动验证未通过，请修复失败项并保持已有真实数据与分析内容。${original}

失败项：
${failedSummary || '无失败项，但验证报告状态为失败，请重新检查产物。'}

结构化修复计划已写入：
${VALIDATION_REPAIR_PLAN_RELATIVE_PATH}

请按下面步骤逐项修复：
${repairSteps || '请重新检查验证报告并补齐缺失产物。'}

修复要求：
1. 只修改当前生成项目目录内的文件，不要修改父级 QuantPilot 平台工程。
2. 不要只回复说明，必须实际修改文件并让页面可访问。
3. 不允许把取到的行情、K 线、财务、公告数据整段硬编码到 app/page.tsx；即使是真实数据，整段内联到页面代码也视为失败。
4. 最终数据必须保留在 data_file/final/dashboard-data.json，页面必须读取该数据文件，或通过同源 /api/market/** 获取/刷新数据。
5. 必须写入 evidence/sources.json 和 evidence/data_quality.json，记录来源、端点、时间戳、样本长度、缺失字段、警告和限制。
6. 必须创建 app/api/market/[...path]/route.ts，将 /api/market/** 转发到 http://127.0.0.1:8000/api/v1/**，并保留 query 参数。
7. 不得引用外部 CDN、远程脚本、远程样式或浏览器直连外部接口；页面资源必须本地化，浏览器取数只能走 final 数据文件或同源 /api/market/**。
8. 不得留下 MOCK_DATA、SAMPLE_DATA、STATIC_QUOTES、示例数据、模拟数据等 mock/static 产物，也不得写入任何鉴权凭据、会话凭据或密钥值。
9. 保留或增强金融图表：K 线/量价/均线/财务趋势/公告事件至少覆盖当前用户问题所需内容。
10. 如果 final 数据包含 assets[] 或 comparison，必须生成多标的对比页面：展示全部标的、指标矩阵、收益对比、波动/回撤对比和相对强弱摘要，不能只展示主标的。
11. 如果失败细节提示 run_plan 或 visualization.template_id 与任务语义不一致，必须同步修复 .quantpilot/run_plan.json、data_file/final/dashboard-data.json 的 visualization.template_id 和 app/page.tsx 的页面结构。
12. 修复后确保 npm run build、预览 HTTP 200、数据文件、evidence、产物策略、页面数据绑定、图表存在性和 /api/market 代理都能通过平台验证。
13. 不要启动开发服务器，QuantPilot 会统一管理预览。`;
}

async function publishValidationSummary(
  params: ValidateQuantProjectParams,
  report: QuantValidationReport
) {
  const content = buildValidationSummary(report);

  try {
    const savedMessage = await createMessage({
      projectId: params.projectId,
      role: 'assistant',
      messageType: 'chat',
      content,
      conversationId: params.conversationId ?? null,
      cliSource: params.cliSource ?? 'validator',
      requestId: params.requestId ?? undefined,
      metadata: {
        toolName: 'QuantPilot 自动验证',
        validationStatus: report.status,
        reportPath: report.reportPath,
        checks: report.checks.map((check) => ({
          id: check.id,
          name: check.name,
          status: check.status,
          summary: check.summary,
        })),
      },
    });

    streamManager.publish(params.projectId, {
      type: 'message',
      data: serializeMessage(savedMessage, {
        requestId: params.requestId ?? undefined,
        isFinal: true,
      }),
    });
  } catch (error) {
    console.error('[QuantValidation] Failed to persist validation summary:', error);
  }
}

export async function validateQuantProject(params: ValidateQuantProjectParams): Promise<QuantValidationReport> {
  return withProjectValidationLock(params.projectId, () => validateQuantProjectUnlocked(params));
}

async function withProjectValidationLock<T>(
  projectId: string,
  task: () => Promise<T>
): Promise<T> {
  const previous = validationQueues.get(projectId) ?? Promise.resolve();
  let release!: () => void;
  const current = new Promise<void>((resolve) => {
    release = resolve;
  });
  const queued = previous.then(() => current, () => current);
  validationQueues.set(projectId, queued);

  await previous.catch(() => undefined);
  try {
    return await task();
  } finally {
    release();
    if (validationQueues.get(projectId) === queued) {
      validationQueues.delete(projectId);
    }
  }
}

async function validateQuantProjectUnlocked(params: ValidateQuantProjectParams): Promise<QuantValidationReport> {
  const projectPath = path.resolve(params.projectPath);
  const now = new Date().toISOString();

  await ensureQuantWorkspace(projectPath);
  await waitForValidationArtifactsToSettle(projectPath);
  await ensurePrefetchedFinalData(projectPath);
  await scaffoldBasicNextApp(projectPath, params.projectId);
  await waitForValidationArtifactsToSettle(projectPath);
  await previewManager.stop(params.projectId).catch((error) => {
    console.warn(
      '[QuantValidation] Failed to stop preview before validation build:',
      error
    );
  });
  await appendQuantWorkspaceEvent(projectPath, {
    event_type: 'validation_started',
    stage: 'validation',
    status: 'pending',
    run_id: params.requestId ?? undefined,
    summary: '开始自动验证：build、HTTP 200、最终数据文件、evidence、产物策略、图表和 /api/market 代理。',
    created_at: now,
  });

  streamManager.publish(params.projectId, {
    type: 'status',
    data: {
      status: 'validation_running',
      message: '正在执行自动验证：build、HTTP 200、数据文件、evidence、产物策略、图表和 /api/market 代理。',
      requestId: params.requestId ?? undefined,
    },
  });

  const checks: QuantValidationCheck[] = [];
  try {
    checks.push(await safeRunCheck('next_build', 'Next.js build', () => checkBuild(projectPath)));
    checks.push(await safeRunCheck('preview_http_200', '预览 HTTP 200', () => checkPreviewHttp(params.projectId)));
    checks.push(await safeRunCheck('visual_presentation', '视觉验收', () => checkVisualPresentation(projectPath, params.projectId, params.requestId)));
    checks.push(await safeRunCheck('final_data_file', '最终数据文件', () => checkFinalDataFile(projectPath)));
    checks.push(await safeRunCheck('evidence_files', '数据证据文件', () => checkEvidenceFiles(projectPath)));
    checks.push(await safeRunCheck('artifact_contracts', '产物 Schema 契约', () => checkArtifactContracts(projectPath, params.projectId, params.requestId)));
    checks.push(await safeRunCheck('artifact_policy', '生成产物策略', () => checkArtifactPolicy(projectPath)));
    checks.push(await safeRunCheck('dashboard_data_binding', '页面数据绑定', () => checkDashboardBinding(projectPath)));
    checks.push(await safeRunCheck('chart_presence', '金融图表存在性', () => checkChartPresence(projectPath)));
    checks.push(await safeRunCheck('market_proxy', '/api/market 代理', () => checkMarketProxy(projectPath, params.projectId)));
  } finally {
    await previewManager.stop(params.projectId).catch((error) => {
      console.warn(
        '[QuantValidation] Failed to stop temporary preview after validation:',
        error
      );
    });
  }

  const passed = checks.every((check) => check.status !== 'failed');
  const updatedAt = new Date().toISOString();
  const report: QuantValidationReport = {
    schemaVersion: 1,
    runId: params.requestId ?? undefined,
    status: passed ? 'passed' : 'failed',
    passed,
    projectId: params.projectId,
    reportPath: VALIDATION_REPORT_RELATIVE_PATH,
    checks,
    createdAt: now,
    updatedAt,
  };

  await writeValidationReport(projectPath, report);
  await writeValidationRepairPlan(projectPath, report);
  await appendQuantWorkspaceEvent(projectPath, {
    event_type: 'validation_completed',
    stage: 'validation',
    status: passed ? 'success' : 'error',
    run_id: params.requestId ?? undefined,
    artifact_path: VALIDATION_REPORT_RELATIVE_PATH,
    summary: passed ? '自动验证通过。' : `自动验证未通过：${checks.filter((check) => check.status === 'failed').length} 项失败。`,
    created_at: updatedAt,
  });

  streamManager.publish(params.projectId, {
    type: 'status',
    data: {
      status: passed ? 'validation_passed' : 'validation_failed',
      message: passed ? '自动验证通过，可手动打开预览或发布后查看。' : '自动验证未通过，请查看验证摘要。',
      requestId: params.requestId ?? undefined,
      metadata: {
        reportPath: VALIDATION_REPORT_RELATIVE_PATH,
        checks: checks.map((check) => ({
          id: check.id,
          status: check.status,
          summary: check.summary,
        })),
      },
    },
  });

  await publishValidationSummary(params, report);

  if (passed) {
    try {
      if (params.requestId) {
        await markUserRequestAsCompleted(params.requestId);
      } else {
        await markActiveUserRequestsAsCompleted(params.projectId);
      }
    } catch (error) {
      console.warn('[QuantValidation] Failed to mark request as completed after validation:', error);
    }
  }

  return report;
}

export async function readQuantValidationReport(projectPath: string): Promise<QuantValidationReport | null> {
  const resolvedProjectPath = path.resolve(projectPath);
  const reportPath = validationReportPath(resolvedProjectPath);
  const report = await readTextFile(reportPath);
  if (!report) {
    return null;
  }

  try {
    const parsed = JSON.parse(report) as QuantValidationReport;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    if (parsed.passed === false || parsed.status === 'failed') {
      const reportStat = await fs.stat(reportPath).catch(() => null);
      const artifactStats = await Promise.all(
        VALIDATION_STALE_ARTIFACT_PATHS.map((relativePath) =>
          fs.stat(path.join(resolvedProjectPath, relativePath)).catch(() => null)
        )
      );
      const newestArtifactMtime = Math.max(
        0,
        ...artifactStats
          .filter((stat): stat is NonNullable<typeof stat> => Boolean(stat?.isFile()))
          .map((stat) => stat.mtimeMs)
      );
      if (reportStat && newestArtifactMtime > reportStat.mtimeMs + 1_000) {
        return {
          ...parsed,
          checks: [
            ...parsed.checks,
            {
              id: 'validation_report_stale',
              name: '验证报告已过期',
              status: 'warning',
              summary: '生成产物在上次验证后发生变化，需要重新运行自动验证。',
              metadata: {
                reportUpdatedAt: reportStat.mtime.toISOString(),
                newestArtifactUpdatedAt: new Date(newestArtifactMtime).toISOString(),
              },
            },
          ],
        };
      }
    }
    return parsed;
  } catch {
    return null;
  }
}

export async function readQuantValidationRepairPlan(projectPath: string): Promise<QuantValidationRepairPlan | null> {
  const report = await readTextFile(validationRepairPlanPath(path.resolve(projectPath)));
  if (!report) {
    return null;
  }

  try {
    const parsed = JSON.parse(report) as QuantValidationRepairPlan;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}
