import { execFile } from 'child_process';
import fs from 'fs/promises';
import path from 'path';
import { promisify } from 'util';
import { getCapabilityCenterData } from '@/lib/quant/capability-center';
import { getStrategyDashboardData } from '@/lib/quant/strategies';
import { getWorkspaceHealthDashboard, type WorkspaceHealthDashboard } from '@/lib/quant/workspace-health';
import { getInfrastructureHealth, type InfrastructureHealth } from '@/lib/ops/infrastructure-health';

const execFileAsync = promisify(execFile);

export type OpsCheckStatus = 'ok' | 'warning' | 'failed' | 'unknown';

export interface OpsCheck {
  id: string;
  label: string;
  status: OpsCheckStatus;
  summary: string;
  detail?: string;
  actions?: string[];
}

export interface OpsLogSource {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  sizeBytes: number;
  modifiedAt: string | null;
  lineCount: number;
  lines: string[];
  entries: OpsLogEntry[];
  error?: string;
}

export interface OpsLogEntry {
  id: string;
  lineNumber: number;
  timestamp: string | null;
  timestampSource: 'line' | 'source-modified' | null;
  level: string | null;
  message: string;
  raw: string;
}

export interface OpsHealthFactor {
  id: string;
  label: string;
  score: number;
  weight: number;
  status: OpsCheckStatus;
  summary: string;
}

export interface OpsHealthProfile {
  id: 'project' | 'runtime' | 'strategy';
  label: string;
  score: number;
  status: OpsCheckStatus;
  summary: string;
  factors: OpsHealthFactor[];
}

export interface OpsPlatformDashboard {
  generatedAt: string;
  summary: {
    status: OpsCheckStatus;
    score: number;
    ok: number;
    warning: number;
    failed: number;
    unknown: number;
    logSources: number;
  };
  infrastructure: InfrastructureHealth;
  infrastructureError: string | null;
  healthProfiles: OpsHealthProfile[];
  systemChecks: OpsCheck[];
  capabilityChecks: OpsCheck[];
  logSources: OpsLogSource[];
}

const ROOT = process.cwd();
const MARKET_API_BASE_URL =
  process.env.QUANTPILOT_MARKET_API_URL ||
  process.env.QUANTPILOT_MARKET_API_BASE_URL ||
  'http://127.0.0.1:8000';

function relativePath(filePath: string): string {
  return path.relative(ROOT, filePath) || '.';
}

function isVersionAtLeast(version: string, minimum: string): boolean {
  const current = version.split('.').map((part) => Number.parseInt(part, 10) || 0);
  const required = minimum.split('.').map((part) => Number.parseInt(part, 10) || 0);
  for (let i = 0; i < Math.max(current.length, required.length); i += 1) {
    const left = current[i] ?? 0;
    const right = required[i] ?? 0;
    if (left > right) return true;
    if (left < right) return false;
  }
  return true;
}

async function commandOutput(command: string, args: string[], timeout = 1800): Promise<string | null> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, { cwd: ROOT, timeout });
    const output = `${stdout}${stderr}`.trim();
    return output.split('\n')[0]?.trim() || null;
  } catch {
    return null;
  }
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function countDirectoryItems(dirPath: string, prefix?: string): Promise<number> {
  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    return entries.filter((entry) => entry.isDirectory() && (!prefix || entry.name.startsWith(prefix))).length;
  } catch {
    return 0;
  }
}

async function probeUrl(url: string, timeout = 2500): Promise<{ ok: boolean; status: number | null; ms: number; error: string | null }> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const started = Date.now();
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
    return {
      ok: response.ok,
      status: response.status,
      ms: Date.now() - started,
      error: response.ok ? null : `HTTP ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      status: null,
      ms: Date.now() - started,
      error: error instanceof Error ? error.message : String(error),
    };
  } finally {
    clearTimeout(timer);
  }
}

async function findLatestLogFile(dirPath: string): Promise<string | null> {
  try {
    const entries = await fs.readdir(dirPath, { withFileTypes: true });
    const files = await Promise.all(
      entries
        .filter((entry) => entry.isFile() && entry.name.endsWith('.log'))
        .map(async (entry) => {
          const filePath = path.join(dirPath, entry.name);
          const stat = await fs.stat(filePath);
          return { filePath, mtime: stat.mtimeMs };
        })
    );
    return files.sort((a, b) => b.mtime - a.mtime)[0]?.filePath ?? null;
  } catch {
    return null;
  }
}

async function tailLogSource(id: string, label: string, filePath: string | null, maxLines = 180): Promise<OpsLogSource> {
  const emptyPath = filePath ?? path.join(ROOT, '<missing>');
  if (!filePath) {
    return {
      id,
      label,
      path: '<未发现日志文件>',
      exists: false,
      sizeBytes: 0,
      modifiedAt: null,
      lineCount: 0,
      lines: [],
      entries: [],
      error: '没有匹配的日志文件',
    };
  }

  try {
    const stat = await fs.stat(filePath);
    const maxBytes = 220_000;
    const start = Math.max(0, stat.size - maxBytes);
    const handle = await fs.open(filePath, 'r');
    try {
      const buffer = Buffer.alloc(stat.size - start);
      await handle.read(buffer, 0, buffer.length, start);
      const text = buffer.toString('utf8');
      const lines = text.split(/\r?\n/).filter((line, index, all) => line || index < all.length - 1);
      const visibleLines = lines.slice(-maxLines);
      return {
        id,
        label,
        path: relativePath(filePath),
        exists: true,
        sizeBytes: stat.size,
        modifiedAt: stat.mtime.toISOString(),
        lineCount: lines.length,
        lines: visibleLines,
        entries: visibleLines.map((line, index) => parseLogEntry(line, Math.max(1, lines.length - visibleLines.length + index + 1), stat.mtime.toISOString())),
      };
    } finally {
      await handle.close();
    }
  } catch (error) {
    return {
      id,
      label,
      path: relativePath(emptyPath),
      exists: false,
      sizeBytes: 0,
      modifiedAt: null,
      lineCount: 0,
      lines: [],
      entries: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function parseDateToken(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const timestamp = Date.parse(normalized);
  if (!Number.isFinite(timestamp)) return null;
  return new Date(timestamp).toISOString();
}

function parseLogEntry(raw: string, lineNumber: number, fallbackTimestamp: string | null): OpsLogEntry {
  const trimmed = raw.trim();
  let timestamp: string | null = null;
  let level: string | null = null;
  let message = trimmed || raw;

  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      timestamp = parseDateToken(parsed.timestamp) ?? parseDateToken(parsed.time) ?? parseDateToken(parsed.created_at);
      level = typeof parsed.level === 'string' ? parsed.level : typeof parsed.severity === 'string' ? parsed.severity : null;
      message =
        typeof parsed.message === 'string'
          ? parsed.message
          : typeof parsed.msg === 'string'
            ? parsed.msg
            : trimmed;
    }
  } catch {
    const isoMatch = trimmed.match(/\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b/);
    const bracketMatch = trimmed.match(/\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]/);
    timestamp = parseDateToken(isoMatch?.[0]) ?? parseDateToken(bracketMatch?.[1]);
    const levelMatch = trimmed.match(/\b(TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|LOG)\b/i);
    level = levelMatch?.[1]?.toUpperCase() ?? null;
  }

  const effectiveTimestamp = timestamp ?? fallbackTimestamp;
  return {
    id: `${lineNumber}-${Buffer.from(raw).subarray(0, 12).toString('hex')}`,
    lineNumber,
    timestamp: effectiveTimestamp,
    timestampSource: timestamp ? 'line' : effectiveTimestamp ? 'source-modified' : null,
    level,
    message,
    raw,
  };
}

async function collectLogSources(): Promise<OpsLogSource[]> {
  const latestEvalLog = await findLatestLogFile(path.join(ROOT, 'tmp', 'quantpilot-eval-queue', 'logs'));
  const sources: Array<{ id: string; label: string; filePath: string | null }> = [
    { id: 'next-dev', label: '前端 Next.js dev', filePath: path.join(ROOT, '.next', 'dev', 'logs', 'next-development.log') },
    { id: 'frontend-runtime', label: '前端启动脚本', filePath: path.join(ROOT, 'tmp', 'runtime', 'frontend.log') },
    { id: 'market-api', label: '量化数据后端', filePath: path.join(ROOT, 'tmp', 'runtime', 'market-api.log') },
    { id: 'eval-queue', label: '评测队列最新运行', filePath: latestEvalLog },
  ];
  return Promise.all(sources.map((source) => tailLogSource(source.id, source.label, source.filePath)));
}

function checkStatusFromCount(failed: number, warning: number): OpsCheckStatus {
  if (failed > 0) return 'failed';
  if (warning > 0) return 'warning';
  return 'ok';
}

function scoreStatus(score: number): OpsCheckStatus {
  if (score >= 85) return 'ok';
  if (score >= 70) return 'warning';
  return 'failed';
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function weightedScore(factors: OpsHealthFactor[]): number {
  const totalWeight = factors.reduce((sum, factor) => sum + factor.weight, 0) || 1;
  return clampScore(factors.reduce((sum, factor) => sum + factor.score * factor.weight, 0) / totalWeight);
}

function percent(numerator: number, denominator: number): number {
  if (denominator <= 0) return 0;
  return clampScore((numerator / denominator) * 100);
}

function daysSince(dateText?: string | null): number | null {
  if (!dateText) return null;
  const timestamp = Date.parse(dateText);
  if (!Number.isFinite(timestamp)) return null;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
}

function buildSummary(checks: OpsCheck[], logSources: OpsLogSource[]): OpsPlatformDashboard['summary'] {
  const failed = checks.filter((check) => check.status === 'failed').length;
  const warning = checks.filter((check) => check.status === 'warning').length;
  const unknown = checks.filter((check) => check.status === 'unknown').length;
  const ok = checks.filter((check) => check.status === 'ok').length;
  return {
    status: checkStatusFromCount(failed, warning),
    score: Math.max(0, 100 - failed * 18 - warning * 7 - unknown * 3),
    ok,
    warning,
    failed,
    unknown,
    logSources: logSources.filter((source) => source.exists).length,
  };
}

function buildRuntimeHealthProfile(params: {
  systemChecks: OpsCheck[];
  capabilityChecks: OpsCheck[];
  logSources: OpsLogSource[];
}): OpsHealthProfile {
  const checkById = new Map([...params.systemChecks, ...params.capabilityChecks].map((check) => [check.id, check]));
  const scoreGroup = (ids: string[], warningPenalty = 12, failedPenalty = 32) => {
    const checks = ids.map((id) => checkById.get(id)).filter((check): check is OpsCheck => Boolean(check));
    const warnings = checks.filter((check) => check.status === 'warning' || check.status === 'unknown').length;
    const failed = checks.filter((check) => check.status === 'failed').length;
    return clampScore(100 - warnings * warningPenalty - failed * failedPenalty);
  };
  const logScore = percent(params.logSources.filter((source) => source.exists).length, params.logSources.length);
  const factors: OpsHealthFactor[] = [
    {
      id: 'core-services',
      label: '核心服务',
      score: scoreGroup(['database', 'docker-timescaledb', 'market-api'], 12, 35),
      weight: 40,
      status: scoreStatus(scoreGroup(['database', 'docker-timescaledb', 'market-api'], 12, 35)),
      summary: '数据库、TimescaleDB、Docker 和量化数据后端可用性。',
    },
    {
      id: 'toolchain',
      label: '工具链',
      score: scoreGroup(['node-runtime', 'npm-cli', 'agent-cli'], 10, 25),
      weight: 20,
      status: scoreStatus(scoreGroup(['node-runtime', 'npm-cli', 'agent-cli'], 10, 25)),
      summary: 'Node.js、npm、Agent CLI 是否满足生成链路要求。',
    },
    {
      id: 'storage-schema',
      label: '存储与表结构',
      score: scoreGroup(['workspace-storage', 'repo-baseline', 'quant-schema'], 10, 30),
      weight: 25,
      status: scoreStatus(scoreGroup(['workspace-storage', 'repo-baseline', 'quant-schema'], 10, 30)),
      summary: '工作空间目录、基础文件和 quant schema 是否完整。',
    },
    {
      id: 'observability',
      label: '可观测性',
      score: logScore,
      weight: 15,
      status: scoreStatus(logScore),
      summary: `${params.logSources.filter((source) => source.exists).length}/${params.logSources.length} 个日志源可读。`,
    },
  ];
  const score = weightedScore(factors);
  return {
    id: 'runtime',
    label: '运行健康',
    score,
    status: scoreStatus(score),
    summary: '衡量基础服务、工具链、存储结构和日志可观测性。',
    factors,
  };
}

function buildProjectHealthProfile(workspace: WorkspaceHealthDashboard): OpsHealthProfile {
  const passedProjects = workspace.summary.healthy;
  const verifiedScore = percent(passedProjects, workspace.summary.total);
  const blockerScore = clampScore(100 - workspace.summary.failed * 18 - workspace.summary.warning * 7 - workspace.summary.unknown * 4);
  const factors: OpsHealthFactor[] = [
    {
      id: 'average-score',
      label: '平均交付分',
      score: workspace.summary.averageScore,
      weight: 45,
      status: scoreStatus(workspace.summary.averageScore),
      summary: `${workspace.summary.total} 个工作空间平均 ${workspace.summary.averageScore} 分。`,
    },
    {
      id: 'healthy-ratio',
      label: '健康占比',
      score: verifiedScore,
      weight: 30,
      status: scoreStatus(verifiedScore),
      summary: `${passedProjects}/${workspace.summary.total} 个工作空间处于健康状态。`,
    },
    {
      id: 'blocker-risk',
      label: '阻断风险',
      score: blockerScore,
      weight: 25,
      status: scoreStatus(blockerScore),
      summary: `${workspace.summary.failed} 个失败、${workspace.summary.warning} 个风险、${workspace.summary.unknown} 个待验证。`,
    },
  ];
  const score = weightedScore(factors);
  return {
    id: 'project',
    label: '项目健康',
    score,
    status: scoreStatus(score),
    summary: '衡量生成工作空间的产物完整性、验证结果和交付可靠性。',
    factors,
  };
}

function buildStrategyHealthProfile(strategy: Awaited<ReturnType<typeof getStrategyDashboardData>>): OpsHealthProfile {
  const templateScore = percent(strategy.summary.readyTemplates, strategy.summary.templates);
  const coverageScore = percent(strategy.summary.syncedSymbols, strategy.summary.trackedSymbols);
  const primaryUniverse =
    strategy.research.universes.find((universe) => universe.id === strategy.research.primaryUniverseId) ??
    strategy.research.universes[0] ??
    null;
  const latestAgeDays = daysSince(primaryUniverse?.latestTs);
  const freshnessScore = latestAgeDays === null
    ? 0
    : latestAgeDays <= 3
      ? 100
      : latestAgeDays <= 10
        ? 82
        : latestAgeDays <= 30
          ? 65
          : 40;
  const recentRuns = strategy.scanRuns.slice(0, 20);
  const runTotal = recentRuns.reduce((sum, run) => sum + Math.max(1, run.total), 0);
  const runSucceeded = recentRuns.reduce((sum, run) => sum + run.succeeded, 0);
  const activeJobs = strategy.scanJobs.filter((job) => job.status === 'queued' || job.status === 'running').length;
  const failedJobs = strategy.scanJobs.filter((job) => job.status === 'failed').length;
  const scanScore = recentRuns.length
    ? clampScore(percent(runSucceeded, runTotal) - failedJobs * 8 - activeJobs * 2)
    : strategy.summary.parameterScans > 0
      ? 72
      : 55;
  const sourceScore = strategy.research.source === 'market-api' && !strategy.research.error ? 100 : 65;
  const factors: OpsHealthFactor[] = [
    {
      id: 'template-readiness',
      label: '策略目录',
      score: templateScore,
      weight: 25,
      status: scoreStatus(templateScore),
      summary: `${strategy.summary.readyTemplates}/${strategy.summary.templates} 个策略模板 ready。`,
    },
    {
      id: 'universe-coverage',
      label: '股票池覆盖',
      score: coverageScore,
      weight: 30,
      status: scoreStatus(coverageScore),
      summary: `${strategy.summary.syncedSymbols}/${strategy.summary.trackedSymbols} 个标的已有行情覆盖，${strategy.summary.syncedBars.toLocaleString('zh-CN')} 根 K 线。`,
    },
    {
      id: 'freshness',
      label: '数据新鲜度',
      score: freshnessScore,
      weight: 20,
      status: scoreStatus(freshnessScore),
      summary: primaryUniverse?.latestTs ? `主股票池最新数据 ${primaryUniverse.latestTs}，距今 ${latestAgeDays ?? '-'} 天。` : '主股票池暂无最新数据时间。',
    },
    {
      id: 'scan-backtest',
      label: '回测准备度',
      score: scanScore,
      weight: 15,
      status: scoreStatus(scanScore),
      summary: recentRuns.length ? `最近 ${recentRuns.length} 次扫描成功 ${runSucceeded}/${runTotal} 组参数。` : `${strategy.summary.parameterScans} 个参数扫描已配置，等待真实扫描沉淀。`,
    },
    {
      id: 'research-source',
      label: '研究数据源',
      score: sourceScore,
      weight: 10,
      status: scoreStatus(sourceScore),
      summary: strategy.research.error ? `market-api 降级：${strategy.research.error}` : `研究数据来自 ${strategy.research.source}。`,
    },
  ];
  const score = weightedScore(factors);
  return {
    id: 'strategy',
    label: '策略健康',
    score,
    status: scoreStatus(score),
    summary: '衡量策略目录、股票池行情覆盖、数据新鲜度和回测扫描准备度。',
    factors,
  };
}

export async function getOpsPlatformDashboard(params: {
  workspaceHealth?: WorkspaceHealthDashboard | Promise<WorkspaceHealthDashboard>;
} = {}): Promise<OpsPlatformDashboard> {
  const [
    infrastructure,
    capabilityCenter,
    workspaceHealth,
    strategyHealth,
    npmVersion,
    claudeVersion,
    codexVersion,
    marketHealth,
    marketRegistry,
    logSources,
  ] = await Promise.all([
    getInfrastructureHealth(),
    getCapabilityCenterData(),
    params.workspaceHealth ?? getWorkspaceHealthDashboard(),
    getStrategyDashboardData(),
    commandOutput('npm', ['--version']),
    commandOutput('claude', ['--version']),
    commandOutput(process.env.CODEX_EXECUTABLE || 'codex', ['--version']),
    probeUrl(`${MARKET_API_BASE_URL}/health`),
    probeUrl(`${MARKET_API_BASE_URL}/api/v1/registry`),
    collectLogSources(),
  ]);

  const projectsDir = path.resolve(ROOT, process.env.PROJECTS_DIR || './data/projects');
  const projectCount = await countDirectoryItems(projectsDir, 'project-');
  const requiredFiles = await Promise.all([
    fileExists(path.join(ROOT, '.env')),
    fileExists(path.join(ROOT, '.env.example')),
    fileExists(path.join(ROOT, 'sqls')),
    fileExists(path.join(ROOT, 'services', 'market-data')),
  ]);
  const missingRequired = [
    requiredFiles[0] ? null : '.env',
    requiredFiles[1] ? null : '.env.example',
    requiredFiles[2] ? null : 'sqls',
    requiredFiles[3] ? null : 'services/market-data',
  ].filter((item): item is string => Boolean(item));

  const nodeVersion = process.versions.node;
  const systemChecks: OpsCheck[] = [
    {
      id: 'node-runtime',
      label: 'Node.js 运行时',
      status: isVersionAtLeast(nodeVersion, '20.19.0') ? 'ok' : 'failed',
      summary: `v${nodeVersion}`,
      detail: '项目要求 Node.js >= 20.19.0。',
      actions: isVersionAtLeast(nodeVersion, '20.19.0') ? [] : ['升级本地 Node.js 版本。'],
    },
    {
      id: 'npm-cli',
      label: 'npm 工具链',
      status: npmVersion ? 'ok' : 'failed',
      summary: npmVersion ? `npm ${npmVersion}` : 'npm 不可用',
      actions: npmVersion ? [] : ['确认 Node.js 安装包含 npm。'],
    },
    {
      id: 'agent-cli',
      label: 'Agent CLI',
      status: claudeVersion ? 'ok' : codexVersion ? 'warning' : 'failed',
      summary: `claude=${claudeVersion ?? '-'} · codex=${codexVersion ?? '-'}`,
      detail: '生成链路至少需要一个可用的 Agent CLI；Claude 是默认主链路，Codex 可作为补充。',
      actions: claudeVersion || codexVersion ? [] : ['安装并登录 Claude Code 或 Codex CLI。'],
    },
    {
      id: 'database',
      label: 'PostgreSQL / TimescaleDB',
      status: infrastructure.data.connected && infrastructure.data.timescale.enabled ? 'ok' : 'failed',
      summary: infrastructure.data.connected
        ? `已连接 ${infrastructure.data.provider}，TimescaleDB ${infrastructure.data.timescale.version ?? '未启用'}`
        : '数据库不可连接',
      detail: infrastructure.error ?? `${infrastructure.data.quantSchema.tables.length} 张 quant 表可用。`,
      actions: infrastructure.data.connected ? [] : ['运行 npm run db:up 和 npm run prisma:push。'],
    },
    {
      id: 'docker-timescaledb',
      label: 'Docker timescaledb 服务',
      status: infrastructure.data.docker.running ? 'ok' : infrastructure.data.docker.available ? 'warning' : 'failed',
      summary: infrastructure.data.docker.service?.status ?? 'compose 服务未运行',
      detail: infrastructure.data.docker.error,
      actions: infrastructure.data.docker.running ? [] : ['运行 npm run db:up。'],
    },
    {
      id: 'market-api',
      label: '量化数据后端',
      status: marketHealth.ok && marketRegistry.ok ? 'ok' : marketHealth.ok ? 'warning' : 'failed',
      summary: `${MARKET_API_BASE_URL} · health=${marketHealth.status ?? '-'} · registry=${marketRegistry.status ?? '-'}`,
      detail: marketHealth.ok && marketRegistry.ok
        ? `响应 ${Math.max(marketHealth.ms, marketRegistry.ms)}ms`
        : marketHealth.error ?? marketRegistry.error ?? undefined,
      actions: marketHealth.ok ? [] : ['进入 services/market-data 后运行 uv run quantpilot-market-api。'],
    },
    {
      id: 'workspace-storage',
      label: '工作空间目录',
      status: projectCount > 0 ? 'ok' : 'warning',
      summary: `${relativePath(projectsDir)} · ${projectCount} 个项目`,
      actions: projectCount > 0 ? [] : ['从首页创建一次任务，确认生成链路写入 data/projects。'],
    },
    {
      id: 'repo-baseline',
      label: '项目基础文件',
      status: missingRequired.length ? 'failed' : 'ok',
      summary: missingRequired.length ? `缺少 ${missingRequired.join('、')}` : '环境、SQL、后端服务目录齐全',
      actions: missingRequired.length ? ['补齐缺失的项目基础文件。'] : [],
    },
  ];

  const capabilityChecks: OpsCheck[] = [
    {
      id: 'capability-center',
      label: '能力中心',
      status: capabilityCenter.summary.blockedCapabilities > 0 ? 'failed' : capabilityCenter.summary.plannedCapabilities > 0 ? 'warning' : 'ok',
      summary: `${capabilityCenter.summary.readyCapabilities}/${capabilityCenter.summary.capabilities} 个能力 ready`,
      detail: `${capabilityCenter.summary.plannedCapabilities} 个规划中，${capabilityCenter.summary.blockedCapabilities} 个阻断。`,
    },
    {
      id: 'skills',
      label: 'Skills 健康',
      status: capabilityCenter.summary.skillErrors > 0 ? 'failed' : 'ok',
      summary: `${capabilityCenter.summary.skills} 个 skill，${capabilityCenter.summary.skillErrors} 个异常`,
      actions: capabilityCenter.summary.skillErrors ? ['进入 /skills 查看异常 skill 并重新同步。'] : [],
    },
    {
      id: 'data-providers',
      label: '数据源可用性',
      status: capabilityCenter.summary.availableProviders > 0
        ? capabilityCenter.summary.degradedProviders > 0 ? 'warning' : 'ok'
        : 'failed',
      summary: `${capabilityCenter.summary.availableProviders}/${capabilityCenter.summary.dataProviders} 个数据源可用`,
      detail: `${capabilityCenter.summary.degradedProviders} 个数据源降级；market API ${capabilityCenter.marketApi.status}。`,
      actions: capabilityCenter.summary.availableProviders ? [] : ['启动量化数据后端并检查数据源注册表。'],
    },
    {
      id: 'quant-schema',
      label: '量化数据表',
      status: infrastructure.data.quantSchema.tables.length >= 4 ? 'ok' : 'warning',
      summary: `${infrastructure.data.quantSchema.tables.length} 张 quant 表`,
      detail: infrastructure.data.quantSchema.tables.map((table) => `quant.${table}`).join('、') || '尚未初始化 quant schema。',
      actions: infrastructure.data.quantSchema.tables.length >= 4 ? [] : ['执行 sqls/README.md 中的初始化 SQL。'],
    },
    {
      id: 'logs',
      label: '系统日志入口',
      status: logSources.some((source) => source.exists) ? 'ok' : 'warning',
      summary: `${logSources.filter((source) => source.exists).length}/${logSources.length} 个日志源可读`,
      detail: logSources.filter((source) => !source.exists).map((source) => source.label).join('、') || undefined,
    },
  ];

  const allChecks = [...systemChecks, ...capabilityChecks];
  const healthProfiles = [
    buildProjectHealthProfile(workspaceHealth),
    buildRuntimeHealthProfile({ systemChecks, capabilityChecks, logSources }),
    buildStrategyHealthProfile(strategyHealth),
  ];
  return {
    generatedAt: new Date().toISOString(),
    summary: buildSummary(allChecks, logSources),
    infrastructure: infrastructure.data,
    infrastructureError: infrastructure.error ?? null,
    healthProfiles,
    systemChecks,
    capabilityChecks,
    logSources,
  };
}
