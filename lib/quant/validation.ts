import { spawn } from 'child_process';
import fs from 'fs/promises';
import path from 'path';
import { serializeMessage } from '@/lib/serializers/chat';
import { createMessage } from '@/lib/services/message';
import { previewManager } from '@/lib/services/preview';
import { streamManager } from '@/lib/services/stream';
import { ensureBaselineEvidenceFiles } from '@/lib/quant/evidence';
import { appendQuantWorkspaceEvent, ensureQuantWorkspace } from '@/lib/quant/workspace';
import { scaffoldBasicNextApp } from '@/lib/utils/scaffold';

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
const BUILD_TIMEOUT_MS = Number.parseInt(process.env.QUANTPILOT_VALIDATION_BUILD_TIMEOUT_MS ?? '', 10) || 180_000;
const PREVIEW_HTTP_TIMEOUT_MS = Number.parseInt(process.env.QUANTPILOT_VALIDATION_HTTP_TIMEOUT_MS ?? '', 10) || 45_000;
const FETCH_TIMEOUT_MS = 5_000;
const OUTPUT_TAIL_LIMIT = 12_000;
const SENSITIVE_EVIDENCE_PATTERN =
  /sk-[a-z0-9_-]{12,}|authorization|bearer\s+[a-z0-9._-]{12,}|api[_-]?key|auth[_-]?token|cookie|set-cookie/i;

function validationReportPath(projectPath: string) {
  return path.join(projectPath, VALIDATION_REPORT_RELATIVE_PATH);
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
      env: {
        ...process.env,
        CI: '1',
        NODE_ENV: 'production',
        NEXT_TELEMETRY_DISABLED: '1',
      },
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

  const scripts = packageJson.scripts;
  if (!scripts || typeof scripts !== 'object' || Array.isArray(scripts)) {
    return;
  }

  const scriptMap = scripts as Record<string, unknown>;
  if (scriptMap.build === 'next build') {
    scriptMap.build = 'next build --webpack';
    await fs.writeFile(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`, 'utf8');
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
      const serialized = JSON.stringify(parsed);
      const hasDataShape =
        /quote|price|symbol|secid|history|kline|financial|reports|announcement|source|fetched_at|quote_time|close|open|volume|amount|backtest|equity_curve|trades|strategy|drawdown|win_rate|营收|净利润|毛利率|roe|回测|净值|回撤|胜率/i.test(
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

      return {
        status: 'passed',
        summary: `已找到可用最终数据文件：${normalizeRelativePath(projectPath, filePath)}。`,
        metadata: {
          file: normalizeRelativePath(projectPath, filePath),
          bytes: Buffer.byteLength(raw),
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
      summary: '缺少数据来源或数据质量证据文件。',
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
      details: '请移除 token、cookie、authorization header、api key 等敏感内容，仅保留数据来源、端点、时间戳和质量摘要。',
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
      summary: '数据来源或质量证据不完整。',
      details: errors.join('\n'),
    };
  }

  const warningSummary = qualityStatus === 'warning' ? '数据质量存在警告，页面应展示限制说明。' : undefined;
  return {
    status: qualityStatus === 'error' ? 'failed' : qualityStatus === 'warning' ? 'warning' : 'passed',
    summary: baseline.created
      ? `已根据最终数据自动生成数据来源和质量证据文件，状态：${qualityStatus}。`
      : warningSummary ?? '已找到数据来源和质量证据文件。',
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

  const hasGraphicElement = /<svg|<canvas|<polyline|<rect|<path|Chart|chart|candlestick|ohlc|K线|K 线|折线|柱状|趋势图/i.test(page);
  const hasFinanceOrMarketLanguage = /成交量|成交额|均线|MA5|MA10|MA20|K线|K 线|营收|净利润|ROE|毛利率|回撤|波动率|quote|history|financial/i.test(page);

  if (!hasGraphicElement || !hasFinanceOrMarketLanguage) {
    return {
      status: 'failed',
      summary: '未检测到有效金融图表实现。',
      details: '页面至少应包含 SVG/canvas/图表组件，并展示 K 线、成交量、均线、财务趋势或风险指标。',
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

async function writeValidationReport(projectPath: string, report: QuantValidationReport) {
  await ensureQuantWorkspace(projectPath);
  await fs.writeFile(validationReportPath(projectPath), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
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
  const failedSummary = failedChecks
    .map((check, index) => {
      const details = check.details ? `\n   细节：${truncateForPrompt(check.details)}` : '';
      return `${index + 1}. ${check.name}（${check.id}）：${check.summary}${details}`;
    })
    .join('\n');

  const original = options.originalInstruction
    ? `\n原始用户需求：\n${truncateForPrompt(options.originalInstruction, 1_000)}\n`
    : '';

  return `QuantPilot 自动验证未通过，请修复失败项并保持已有真实数据与分析内容。${original}

失败项：
${failedSummary || '无失败项，但验证报告状态为失败，请重新检查产物。'}

修复要求：
1. 只修改当前生成项目目录内的文件，不要修改父级 QuantPilot 平台工程。
2. 不要只回复说明，必须实际修改文件并让页面可访问。
3. 不允许把取到的行情、K 线、财务、公告数据整段硬编码到 app/page.tsx；即使是真实数据，整段内联到页面代码也视为失败。
4. 最终数据必须保留在 data_file/final/dashboard-data.json，页面必须读取该数据文件，或通过同源 /api/market/** 获取/刷新数据。
5. 必须写入 evidence/sources.json 和 evidence/data_quality.json，记录来源、端点、时间戳、样本长度、缺失字段、警告和限制。
6. 必须创建 app/api/market/[...path]/route.ts，将 /api/market/** 转发到 http://127.0.0.1:8000/api/v1/**，并保留 query 参数。
7. 保留或增强金融图表：K 线/量价/均线/财务趋势/公告事件至少覆盖当前用户问题所需内容。
8. 修复后确保 npm run build、预览 HTTP 200、数据文件、evidence、页面数据绑定、图表存在性和 /api/market 代理都能通过平台验证。
9. 不要启动开发服务器，QuantPilot 会统一管理预览。`;
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
  const projectPath = path.resolve(params.projectPath);
  const now = new Date().toISOString();

  await ensureQuantWorkspace(projectPath);
  await scaffoldBasicNextApp(projectPath, params.projectId);
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
    summary: '开始自动验证：build、HTTP 200、最终数据文件、evidence、图表和 /api/market 代理。',
    created_at: now,
  });

  streamManager.publish(params.projectId, {
    type: 'status',
    data: {
      status: 'validation_running',
      message: '正在执行自动验证：build、HTTP 200、数据文件、evidence、图表和 /api/market 代理。',
      requestId: params.requestId ?? undefined,
    },
  });

  const checks: QuantValidationCheck[] = [];
  checks.push(await safeRunCheck('next_build', 'Next.js build', () => checkBuild(projectPath)));
  checks.push(await safeRunCheck('preview_http_200', '预览 HTTP 200', () => checkPreviewHttp(params.projectId)));
  checks.push(await safeRunCheck('final_data_file', '最终数据文件', () => checkFinalDataFile(projectPath)));
  checks.push(await safeRunCheck('evidence_files', '数据证据文件', () => checkEvidenceFiles(projectPath)));
  checks.push(await safeRunCheck('dashboard_data_binding', '页面数据绑定', () => checkDashboardBinding(projectPath)));
  checks.push(await safeRunCheck('chart_presence', '金融图表存在性', () => checkChartPresence(projectPath)));
  checks.push(await safeRunCheck('market_proxy', '/api/market 代理', () => checkMarketProxy(projectPath, params.projectId)));

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
      message: passed ? '自动验证通过。' : '自动验证未通过，请查看验证摘要。',
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

  return report;
}

export async function readQuantValidationReport(projectPath: string): Promise<QuantValidationReport | null> {
  const report = await readTextFile(validationReportPath(path.resolve(projectPath)));
  if (!report) {
    return null;
  }

  try {
    const parsed = JSON.parse(report) as QuantValidationReport;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}
