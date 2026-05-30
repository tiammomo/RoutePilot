import fs from 'fs/promises';
import path from 'path';

function shouldRefreshScaffoldFile(filePath: string, existing: string): boolean {
  const normalizedPath = filePath.replaceAll(path.sep, '/');
  const trimmed = existing.trim();

  if (normalizedPath.endsWith('/app/page.tsx')) {
    const hasQuantDataBinding =
      existing.includes('dashboard-data.json') ||
      existing.includes('data_file/final') ||
      existing.includes('/api/market/');
    const hasStandardQuantDashboard =
      existing.includes('data-source-file={DATA_FILE}') &&
      existing.includes('function getBars(') &&
      existing.includes('TrendChart') &&
      existing.includes('K 线与量价结构');
    const hasLegacySvgTitleHydrationRisk =
      hasStandardQuantDashboard &&
      (
        existing.includes('<title>{String(bar.date') ||
        existing.includes('<title>{String(bar.date ??')
      );
    const isDefaultNextPage =
      existing.includes('Get started by editing') ||
      existing.includes('src/app/page.tsx') ||
      existing.includes('app/page.tsx') ||
      existing.includes('next/font/google') ||
      existing.includes('https://vercel.com/templates');
    const hasUnstableQuantDashboard =
      hasQuantDataBinding &&
      (
        existing.includes('0 条样本') ||
        (existing.includes('最新价</span>') && !hasStandardQuantDashboard) ||
        (existing.includes('QuantPilot 看板') && !hasStandardQuantDashboard) ||
        existing.includes('SAMPLE_DATA') ||
        existing.includes('MOCK_DATA') ||
        existing.includes('STATIC_QUOTES')
      );

    return (isDefaultNextPage && !hasQuantDataBinding) || hasUnstableQuantDashboard || hasLegacySvgTitleHydrationRisk;
  }

  if (normalizedPath.endsWith('/app/globals.css')) {
    const hasQuantDashboardStyles =
      existing.includes('.dashboard-shell') ||
      existing.includes('.quant-dashboard') ||
      existing.includes('.chart-card');

    return !hasQuantDashboardStyles && trimmed.length < 600;
  }

  if (normalizedPath.endsWith('/app/api/market/[...path]/route.ts')) {
    const targetsQuantBackend =
      existing.includes('127.0.0.1:8000/api/v1') ||
      existing.includes('QUANTPILOT_MARKET_API') ||
      existing.includes('/api/v1/');

    return !targetsQuantBackend && trimmed.length < 1_200;
  }

  if (normalizedPath.endsWith('/scripts/run-dev.js')) {
    return (
      existing.includes('--webpack') ||
      existing.includes('hasBundlerFlag') ||
      existing.includes("NEXT_RSPACK: process.env.NEXT_RSPACK || 'true'") ||
      existing.includes('const useRspack = process.env.NEXT_RSPACK ===') ||
      existing.includes('Rspack dev mode enabled') ||
      existing.includes('const devEnv =') ||
      /'next',\s*'dev'/.test(existing) ||
      !existing.includes("commandArgs.push('--turbo')") ||
      !existing.includes('QUANTPILOT_WORKSPACE_ROOT') ||
      !existing.includes('delete runtimeEnv.NEXT_RSPACK') ||
      !existing.includes("fs.existsSync(path.join(projectRoot, '.next', 'BUILD_ID'))")
    );
  }

  if (normalizedPath.endsWith('/scripts/run-build.js')) {
    return (
      !existing.includes("NODE_ENV: 'production'") ||
      !existing.includes('QUANTPILOT_WORKSPACE_ROOT') ||
      !existing.includes('NEXT_PRIVATE_BUILD_WORKER') ||
      !existing.includes('delete buildEnv.NEXT_RSPACK') ||
      !existing.includes("['next', 'build'")
    );
  }

  return false;
}

type PackageJsonShape = {
  scripts: Record<string, string>;
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
};

export function generatedBuildScriptContents(): string {
  return `#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const isWindows = process.platform === 'win32';
const workspaceRoot =
  process.env.QUANTPILOT_WORKSPACE_ROOT || path.resolve(projectRoot, '../../..');

const buildEnv = {
  ...process.env,
  NODE_ENV: 'production',
  QUANTPILOT_WORKSPACE_ROOT: workspaceRoot,
  NEXT_PRIVATE_BUILD_WORKER: '1',
  NEXT_TELEMETRY_DISABLED: '1',
};

delete buildEnv.NEXT_RSPACK;
delete buildEnv.TURBOPACK;

const child = spawn(
  'npx',
  ['next', 'build', ...process.argv.slice(2)],
  {
    cwd: projectRoot,
    stdio: 'inherit',
    shell: isWindows,
    env: buildEnv,
  }
);

child.on('exit', (code, signal) => {
  if (code === 0) {
    return;
  }

  console.error(
    \`Next.js build failed with code \${code ?? 'null'}, signal \${signal ?? 'none'}\`
  );
  process.exit(typeof code === 'number' ? code : 1);
});

child.on('error', (error) => {
  console.error('Failed to start Next.js build');
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
`;
}

async function mergePackageJson(filePath: string, defaults: PackageJsonShape & Record<string, unknown>) {
  let packageJson = defaults;

  try {
    packageJson = JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    // 文件缺失或 JSON 异常时，回写默认配置。
  }

  packageJson.scripts = {
    ...defaults.scripts,
    ...(packageJson.scripts ?? {}),
    build: defaults.scripts.build,
  };
  if (packageJson.scripts.build === 'next build' || packageJson.scripts.build === 'next build --webpack') {
    packageJson.scripts.build = defaults.scripts.build;
  }

  packageJson.dependencies = {
    ...(packageJson.dependencies ?? {}),
    next: packageJson.dependencies?.next ?? defaults.dependencies.next,
    react: packageJson.dependencies?.react ?? defaults.dependencies.react,
    'react-dom':
      packageJson.dependencies?.['react-dom'] ?? defaults.dependencies['react-dom'],
  };
  delete packageJson.dependencies['next-rspack'];

  const existingDevDependencies =
    packageJson.devDependencies &&
    typeof packageJson.devDependencies === 'object' &&
    !Array.isArray(packageJson.devDependencies)
      ? packageJson.devDependencies
      : {};

  packageJson.devDependencies = {
    ...(packageJson.devDependencies ?? {}),
    typescript:
      existingDevDependencies.typescript ?? defaults.devDependencies.typescript,
    '@types/react':
      existingDevDependencies['@types/react'] ?? defaults.devDependencies['@types/react'],
    '@types/node':
      existingDevDependencies['@types/node'] ?? defaults.devDependencies['@types/node'],
    eslint: existingDevDependencies.eslint ?? defaults.devDependencies.eslint,
    'eslint-config-next':
      existingDevDependencies['eslint-config-next'] ?? defaults.devDependencies['eslint-config-next'],
  };
  delete packageJson.devDependencies['next-rspack'];

  await fs.writeFile(
    filePath,
    `${JSON.stringify(packageJson, null, 2)}\n`,
    'utf8'
  );
}

async function ensureNextConfig(filePath: string) {
  const fallback = `/** @type {import('next').NextConfig} */
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = process.env.QUANTPILOT_WORKSPACE_ROOT
  ? path.resolve(process.env.QUANTPILOT_WORKSPACE_ROOT)
  : path.resolve(projectRoot, '../../..');

const nextConfig = {
  allowedDevOrigins: ['localhost', '127.0.0.1'],
  typedRoutes: true,
  outputFileTracingRoot: workspaceRoot,
  turbopack: {
    root: workspaceRoot,
  },
};

module.exports = nextConfig;
`;

  let content: string;
  try {
    content = await fs.readFile(filePath, 'utf8');
  } catch {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, fallback, 'utf8');
    return;
  }

  let nextContent = content.replace(
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
      /\/\*\* @type \{import\('next'\)\.NextConfig\} \*\/\n/,
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
    await fs.writeFile(filePath, nextContent, 'utf8');
  }
}

async function writeFileIfMissing(filePath: string, contents: string) {
  try {
    const existing = await fs.readFile(filePath, 'utf8');
    if (!shouldRefreshScaffoldFile(filePath, existing)) {
      return;
    }
  } catch {
    // continue
  }
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(filePath, contents, 'utf8');
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

async function ensureSharedNodeModules(projectPath: string) {
  const projectNodeModules = path.join(projectPath, 'node_modules');
  const sharedNodeModules = path.join(process.cwd(), 'node_modules');

  if (path.resolve(projectNodeModules) === path.resolve(sharedNodeModules)) {
    return;
  }

  if (!(await fileExists(path.join(sharedNodeModules, 'next', 'package.json')))) {
    return;
  }

  try {
    const existing = await fs.lstat(projectNodeModules);
    if (existing.isSymbolicLink()) {
      const target = await fs.readlink(projectNodeModules);
      const resolvedTarget = path.resolve(projectPath, target);
      if (resolvedTarget === path.resolve(sharedNodeModules)) {
        return;
      }
      await fs.rm(projectNodeModules, { recursive: true, force: true });
    } else if (await directoryExists(path.join(projectNodeModules, 'next'))) {
      return;
    } else {
      return;
    }
  } catch {
    // node_modules 不存在时创建共享依赖桥接。
  }

  const relativeTarget = path.relative(projectPath, sharedNodeModules);
  await fs.symlink(relativeTarget || sharedNodeModules, projectNodeModules, 'dir');
}

async function readJsonRecord(filePath: string): Promise<Record<string, unknown> | null> {
  try {
    const parsed = JSON.parse(await fs.readFile(filePath, 'utf8'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

async function upsertGeneratedCssBlock(cssPath: string, marker: string, block: string) {
  const start = `/* quantpilot-${marker}:start */`;
  const end = `/* quantpilot-${marker}:end */`;
  const raw = await fs.readFile(cssPath, 'utf8').catch(() => '');
  const normalizedBlock = `${start}\n${block.trim()}\n${end}`;
  const blockWithNewline = `${normalizedBlock}\n`;

  if (raw.includes(start) && raw.includes(end)) {
    const pattern = new RegExp(`${start.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}[\\s\\S]*?${end.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`);
    const next = raw.replace(pattern, normalizedBlock);
    if (next !== raw) {
      await fs.writeFile(cssPath, next.endsWith('\n') ? next : `${next}\n`, 'utf8');
    }
    return;
  }

  await fs.writeFile(cssPath, `${raw.trimEnd()}\n${blockWithNewline}`, 'utf8');
}

function comparisonPageTemplate() {
  return `import fs from 'fs/promises';
import path from 'path';

type JsonRecord = Record<string, unknown>;

const DATA_FILE = 'data_file/final/dashboard-data.json';
const SOURCES_FILE = 'evidence/sources.json';

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as JsonRecord;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: unknown, digits = 2): string {
  const number = numeric(value);
  if (number === null) return '-';
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(number);
}

function formatPercent(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}

function formatMoney(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  if (Math.abs(number) >= 100000000) return formatNumber(number / 100000000, 2) + ' 亿';
  if (Math.abs(number) >= 10000) return formatNumber(number / 10000, 2) + ' 万';
  return formatNumber(number);
}

function sourceDisplayName(source: unknown, datasetType?: unknown): string {
  const normalized = String(source ?? '').toLowerCase();
  const type = String(datasetType ?? '').toLowerCase();
  if (normalized.includes('eastmoney')) {
    if (/kline|history|历史/.test(type)) return '东方财富历史 K 线接口';
    if (/financial|fundamental|财务/.test(type)) return '东方财富财务数据接口';
    if (/announcement|event|公告/.test(type)) return '东方财富公告事件接口';
    return '东方财富实时行情接口';
  }
  if (normalized.includes('uploaded_image')) return '用户上传截图';
  if (normalized.includes('market_prefetch')) return 'QuantPilot 后端预取';
  if (normalized.includes('tencent')) return '腾讯证券行情接口';
  if (normalized.includes('sina')) return '新浪财经行情接口';
  if (normalized.includes('akshare')) return 'AKShare 免费数据接口';
  if (normalized.includes('local')) return '本地计算结果';
  return String(source ?? '未知信源');
}

async function readDashboardData(): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(path.join(process.cwd(), DATA_FILE), 'utf8');
    return asRecord(JSON.parse(content));
  } catch {
    return null;
  }
}

function getAssets(data: JsonRecord | null): JsonRecord[] {
  return asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getComparisonRows(data: JsonRecord | null): JsonRecord[] {
  const comparison = asRecord(data?.comparison);
  const rows = asArray(comparison?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (rows.length > 0) return rows;
  return getAssets(data).map((asset) => {
    const quote = asRecord(asset.quote);
    const metrics = asRecord(asset.computedMetrics);
    return {
      symbol: asset.symbol ?? quote?.symbol,
      name: asset.name ?? quote?.name ?? asset.symbol,
      price: quote?.price,
      change_percent: quote?.change_percent,
      period_return: metrics?.periodReturn,
      max_drawdown: metrics?.maxDrawdown,
      volatility20d: metrics?.volatility20d,
      avg_volume_20d: metrics?.avgVolume20d,
      amount: quote?.amount,
      as_of: asset.as_of ?? quote?.quote_time ?? quote?.fetched_at,
      source: asset.source ?? quote?.source,
    };
  });
}

function getLeaders(data: JsonRecord | null): JsonRecord | null {
  return asRecord(asRecord(data?.comparison)?.leaders);
}

function getCorrelationPairs(data: JsonRecord | null): JsonRecord[] {
  const correlation = asRecord(data?.correlation);
  return asArray(correlation?.top_pairs).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getValuationRows(data: JsonRecord | null): JsonRecord[] {
  const valuation = asRecord(data?.valuation);
  const rows = asArray(valuation?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (rows.length > 0) {
    return rows;
  }
  const scenarios = asArray(valuation?.scenarios).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (scenarios.length === 0) {
    return [];
  }
  return [{
    symbol: data?.symbol,
    name: data?.name,
    base_metrics: valuation?.base_metrics ?? valuation?.baseMetrics,
    scenarios,
    warnings: valuation?.warnings,
  }];
}

function getTrendTemplateRows(data: JsonRecord | null): JsonRecord[] {
  const trendTemplate = asRecord(data?.trendTemplate) ?? asRecord(data?.trend_template);
  return asArray(trendTemplate?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getVisualization(data: JsonRecord | null): JsonRecord | null {
  return asRecord(data?.visualization);
}

function getVisualizationRows(visualization: JsonRecord | null): JsonRecord[] {
  const required = asArray(visualization?.required_components).map(String);
  const rendered = new Set(asArray(visualization?.rendered_components).map(String));
  const missing = new Set(asArray(visualization?.missing_components).map(String));
  return required.map((name) => ({
    name,
    status: missing.has(name) ? '待补充' : rendered.has(name) ? '已渲染' : '按模板渲染',
  }));
}

function getLiquidityRows(data: JsonRecord | null): JsonRecord[] {
  const liquidity = asRecord(data?.liquidity);
  return asArray(liquidity?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function tone(value: unknown): 'up' | 'down' | 'neutral' {
  const number = numeric(value);
  if (number === null || number === 0) return 'neutral';
  return number > 0 ? 'up' : 'down';
}

function BarChart({ rows, field, title, subtitle, inverse = false }: {
  rows: JsonRecord[];
  field: string;
  title: string;
  subtitle: string;
  inverse?: boolean;
}) {
  const values = rows.map((row) => numeric(row[field]) ?? 0);
  const maxAbs = Math.max(0.01, ...values.map((value) => Math.abs(value)));

  return (
    <section className="comparison-panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      <svg className="comparison-bars" viewBox="0 0 100 56" preserveAspectRatio="none" role="img" aria-label={title}>
        <line x1="0" y1="44" x2="100" y2="44" className="axis" />
        {rows.map((row, index) => {
          const value = numeric(row[field]) ?? 0;
          const height = Math.max(2, (Math.abs(value) / maxAbs) * 38);
          const x = 8 + index * (84 / Math.max(rows.length, 1));
          const width = Math.min(16, 66 / Math.max(rows.length, 1));
          const y = 44 - height;
          const isPositive = inverse ? value <= 0 : value >= 0;
          return (
            <g key={String(row.symbol ?? index)} className={isPositive ? 'bar-up' : 'bar-down'}>
              <rect x={x.toFixed(2)} y={y.toFixed(2)} width={width.toFixed(2)} height={height.toFixed(2)} rx="1" />
            </g>
          );
        })}
      </svg>
      <div className="chart-value-row">
        {rows.map((row, index) => (
          <span key={String(row.symbol ?? index)}>
            {String(row.symbol ?? '-')} {formatPercent(row[field])}
          </span>
        ))}
      </div>
    </section>
  );
}

function CorrelationPanel({ pairs }: { pairs: JsonRecord[] }) {
  return (
    <section className="comparison-matrix">
      <div className="panel-heading">
        <div>
          <h2>相关性结构</h2>
          <p>基于对齐日期后的日收益率计算 Pearson 相关性，帮助识别联动和分散效果。</p>
        </div>
        <span>{pairs.length} 组</span>
      </div>
      <div className="correlation-list">
        {pairs.length > 0 ? pairs.slice(0, 6).map((pair, index) => {
          const correlation = numeric(pair.correlation);
          const width = Math.max(4, Math.abs(correlation ?? 0) * 100);
          return (
            <div className="correlation-row" key={String(pair.left ?? index) + String(pair.right ?? '')}>
              <div>
                <strong>{String(pair.left ?? '-')} / {String(pair.right ?? '-')}</strong>
                <small>重合样本 {formatNumber(pair.overlap, 0)} 个交易日</small>
              </div>
              <div className="correlation-meter">
                <span style={{ width: width + '%' }} className={(correlation ?? 0) >= 0 ? 'corr-positive' : 'corr-negative'} />
              </div>
              <em>{formatNumber(correlation, 4)}</em>
            </div>
          );
        }) : <p className="empty-state">当前数据不足以计算多标的相关性。</p>}
      </div>
    </section>
  );
}

function LiquidityPanel({ rows }: { rows: JsonRecord[] }) {
  return (
    <section className="comparison-matrix">
      <div className="panel-heading">
        <div>
          <h2>流动性与可交易性</h2>
          <p>展示 20 日成交额、换手代理和 Amihud 非流动性，辅助判断样本可交易性。</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>流动性等级</th>
              <th>20 日均额</th>
              <th>20 日均量</th>
              <th>换手代理</th>
              <th>Amihud x1e9</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.symbol ?? index)}>
                <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                <td>{String(row.liquidity_score ?? '-')}</td>
                <td>{formatMoney(row.avg_amount_20d)}</td>
                <td>{formatNumber(row.avg_volume_20d, 0)}</td>
                <td>{formatPercent(row.turnover_proxy_pct)}</td>
                <td>{formatNumber(row.amihud_illiquidity_x1e9, 6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ValuationPanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="comparison-matrix">
      <div className="panel-heading">
        <div>
          <h2>估值情景</h2>
          <p>基于 PE/EPS 的防守、中性、进攻三档情景；仅用于研究，不构成收益承诺。</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>当前价</th>
              <th>PE</th>
              <th>EPS</th>
              <th>中性情景价</th>
              <th>中性空间</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const metrics = asRecord(row.base_metrics) ?? asRecord(row.baseMetrics) ?? {};
              const scenarios = asArray(row.scenarios).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
              const baseScenario = scenarios.find((item) => item.case === 'base') ?? scenarios[1] ?? scenarios[0];
              return (
                <tr key={String(row.symbol ?? index)}>
                  <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                  <td>{formatNumber(metrics.price)}</td>
                  <td>{formatNumber(metrics.pe_ttm ?? metrics.pe)}</td>
                  <td>{formatNumber(metrics.eps, 4)}</td>
                  <td>{formatNumber(baseScenario?.implied_price)}</td>
                  <td className={tone(baseScenario?.upside_pct)}>{formatPercent(baseScenario?.upside_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TrendTemplatePanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="comparison-matrix">
      <div className="panel-heading">
        <div>
          <h2>趋势模板</h2>
          <p>MA20/MA60、阶段回撤和量能比，辅助生成确认、减仓和观察条件。</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>状态</th>
              <th>分数</th>
              <th>MA20</th>
              <th>MA60</th>
              <th>20 日收益</th>
              <th>120 日回撤</th>
              <th>量能比</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const metrics = asRecord(row.metrics) ?? {};
              return (
                <tr key={String(row.symbol ?? index)}>
                  <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                  <td>{String(row.state ?? '-')}</td>
                  <td>{formatNumber(row.score, 0)}</td>
                  <td>{formatNumber(metrics.ma20)}</td>
                  <td>{formatNumber(metrics.ma60)}</td>
                  <td className={tone(metrics.return_20d_pct)}>{formatPercent(metrics.return_20d_pct)}</td>
                  <td className="down">{formatPercent(metrics.max_drawdown_120d_pct)}</td>
                  <td>{formatNumber(metrics.volume_ratio_20d, 2)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VisualizationPlanPanel({ visualization }: { visualization: JsonRecord | null }) {
  const rows = getVisualizationRows(visualization);
  if (!visualization || rows.length === 0) {
    return null;
  }

  return (
    <section className="comparison-matrix">
      <div className="panel-heading">
        <div>
          <h2>场景模板</h2>
          <p>{String(visualization.name ?? visualization.template_id ?? 'QuantPilot 场景化看板')}</p>
        </div>
        <span>{String(visualization.template_id ?? '-')}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>必备组件</th><th>状态</th></tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((row, index) => (
              <tr key={String(row.name ?? index)}>
                <td>{String(row.name ?? '-')}</td>
                <td>{String(row.status ?? '-')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function Home() {
  const data = await readDashboardData();
  const rows = getComparisonRows(data);
  const assets = getAssets(data);
  const leaders = getLeaders(data);
  const correlationPairs = getCorrelationPairs(data);
  const liquidityRows = getLiquidityRows(data);
  const valuationRows = getValuationRows(data);
  const trendTemplateRows = getTrendTemplateRows(data);
  const visualization = getVisualization(data);
  const requestedSymbols = asArray(data?.requestedSymbols ?? data?.symbols).map(String);
  const bestReturn = asRecord(leaders?.best_return);
  const lowestDrawdown = asRecord(leaders?.lowest_drawdown);
  const lowestVolatility = asRecord(leaders?.lowest_volatility);

  return (
    <main className="comparison-shell" data-market-proxy="/api/market" data-source-file={DATA_FILE}>
      <section className="comparison-hero">
        <div>
          <p className="eyebrow">QuantPilot 多标的对比</p>
          <h1>多标的相对强弱看板</h1>
          <p>覆盖 {requestedSymbols.length || rows.length} 个标的：{requestedSymbols.join('、') || rows.map((row) => String(row.symbol)).join('、')}</p>
        </div>
        <div className="hero-meta">
          <span>样本：最近 60 个交易日</span>
          <span>信源：{sourceDisplayName(data?.source ?? 'eastmoney')}</span>
          <span>证据：{SOURCES_FILE}</span>
        </div>
      </section>

      <section className="leader-grid">
        <article className="leader-card up">
          <span>收益领先</span>
          <strong>{String(bestReturn?.name ?? '-')}</strong>
          <em>{formatPercent(bestReturn?.value)}</em>
        </article>
        <article className="leader-card neutral">
          <span>回撤较小</span>
          <strong>{String(lowestDrawdown?.name ?? '-')}</strong>
          <em>{formatPercent(lowestDrawdown?.value)}</em>
        </article>
        <article className="leader-card neutral">
          <span>波动较低</span>
          <strong>{String(lowestVolatility?.name ?? '-')}</strong>
          <em>{formatPercent(lowestVolatility?.value)}</em>
        </article>
      </section>

      <section className="comparison-matrix">
        <div className="panel-heading">
          <div>
            <h2>指标矩阵</h2>
            <p>最新行情、区间收益、波动、回撤和成交额横向比较</p>
          </div>
          <span>{rows.length} 项</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>区间收益</th>
                <th>最大回撤</th>
                <th>波动率</th>
                <th>成交额</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={String(row.symbol ?? index)}>
                  <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                  <td>{formatNumber(row.price)}</td>
                  <td className={tone(row.change_percent)}>{formatPercent(row.change_percent)}</td>
                  <td className={tone(row.period_return)}>{formatPercent(row.period_return)}</td>
                  <td className="down">{formatPercent(row.max_drawdown)}</td>
                  <td>{formatPercent(row.volatility20d)}</td>
                  <td>{formatMoney(row.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="chart-grid">
        <BarChart rows={rows} field="period_return" title="收益对比" subtitle="同一窗口下的区间收益率" />
        <BarChart rows={rows} field="volatility20d" title="波动率对比" subtitle="20 日收益波动年化口径" />
        <BarChart rows={rows} field="max_drawdown" title="最大回撤对比" subtitle="从区间高点到低点的最大跌幅" inverse />
      </section>

      <section className="comparison-two-column">
        <CorrelationPanel pairs={correlationPairs} />
        <LiquidityPanel rows={liquidityRows} />
      </section>

      <section className="comparison-two-column">
        <ValuationPanel rows={valuationRows} />
        <TrendTemplatePanel rows={trendTemplateRows} />
      </section>

      <VisualizationPlanPanel visualization={visualization} />

      <section className="comparison-matrix">
        <div className="panel-heading">
          <div>
            <h2>数据信源渠道与质量</h2>
            <p>逐只标的展示行情、K 线、财务等渠道和样本覆盖；公开行情接口可能存在延迟。</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th>信源渠道</th>
                <th>行情时间</th>
                <th>K 线样本</th>
                <th>质量提示</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((asset, index) => {
                const quote = asRecord(asset.quote);
                const kline = asRecord(asset.kline);
                const quality = asRecord(quote?.data_quality) ?? asRecord(kline?.data_quality);
                return (
                  <tr key={String(asset.symbol ?? index)}>
                    <td><strong>{String(asset.name ?? quote?.name ?? asset.symbol)}</strong><small>{String(asset.symbol ?? quote?.symbol ?? '-')}</small></td>
                    <td>{sourceDisplayName(asset.source ?? quote?.source ?? 'eastmoney')}</td>
                    <td>{String(asset.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? '-')}</td>
                    <td>{asArray(kline?.bars).length}</td>
                    <td>{String(quality?.status ?? 'ok')}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
`;
}

function stockSelectionPageTemplate() {
  return `import fs from 'fs/promises';
import path from 'path';

type JsonRecord = Record<string, unknown>;

const DATA_FILE = 'data_file/final/dashboard-data.json';
const SOURCES_FILE = 'evidence/sources.json';

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as JsonRecord;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: unknown, digits = 2): string {
  const number = numeric(value);
  if (number === null) return '-';
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(number);
}

function formatPercent(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}

function formatMoney(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  if (Math.abs(number) >= 100000000) return formatNumber(number / 100000000, 2) + ' 亿';
  if (Math.abs(number) >= 10000) return formatNumber(number / 10000, 2) + ' 万';
  return formatNumber(number);
}

function sourceDisplayName(source: unknown, datasetType?: unknown): string {
  const normalized = String(source ?? '').toLowerCase();
  const type = String(datasetType ?? '').toLowerCase();
  if (normalized.includes('eastmoney')) {
    if (/kline|history|历史/.test(type)) return '东方财富历史 K 线接口';
    if (/financial|fundamental|财务/.test(type)) return '东方财富财务数据接口';
    if (/announcement|event|公告/.test(type)) return '东方财富公告事件接口';
    return '东方财富实时行情接口';
  }
  if (normalized.includes('uploaded_image')) return '用户上传截图';
  if (normalized.includes('market_prefetch')) return 'QuantPilot 后端预取';
  if (normalized.includes('tencent')) return '腾讯证券行情接口';
  if (normalized.includes('sina')) return '新浪财经行情接口';
  if (normalized.includes('akshare')) return 'AKShare 免费数据接口';
  if (normalized.includes('local')) return '本地计算结果';
  return String(source ?? '未知信源');
}

function tone(value: unknown): 'up' | 'down' | 'neutral' {
  const number = numeric(value);
  if (number === null || number === 0) return 'neutral';
  return number > 0 ? 'up' : 'down';
}

async function readDashboardData(): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(path.join(process.cwd(), DATA_FILE), 'utf8');
    return asRecord(JSON.parse(content));
  } catch {
    return null;
  }
}

function getAssets(data: JsonRecord | null): JsonRecord[] {
  return asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getComparisonRows(data: JsonRecord | null): JsonRecord[] {
  const comparison = asRecord(data?.comparison);
  const rows = asArray(comparison?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (rows.length > 0) return rows;
  return getAssets(data).map((asset) => {
    const quote = asRecord(asset.quote);
    const metrics = asRecord(asset.computedMetrics);
    const technical = asRecord(asRecord(asset.technicalIndicators)?.summary);
    const financialQuality = asRecord(asset.financialQuality);
    return {
      symbol: asset.symbol ?? quote?.symbol,
      name: asset.name ?? quote?.name ?? asset.symbol,
      price: quote?.price,
      change_percent: quote?.change_percent,
      return_120d_pct: technical?.return_120d_pct ?? metrics?.return120d ?? metrics?.periodReturn,
      max_drawdown: technical?.max_drawdown_pct ?? metrics?.maxDrawdown,
      volatility20d: technical?.volatility_20d_annualized_pct ?? metrics?.volatility20d,
      amount: quote?.amount,
      composite_score: financialQuality?.quality_score,
      selection_view: financialQuality?.quality_label,
      financial_quality_label: financialQuality?.quality_label,
    };
  });
}

function getRowsFrom(data: JsonRecord | null, key: string): JsonRecord[] {
  const record = asRecord(data?.[key]);
  return asArray(record?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getConclusion(data: JsonRecord | null): string[] {
  const conclusion = asRecord(data?.conclusion);
  return asArray(conclusion?.summary).map(String).filter(Boolean);
}

function pickMetric(row: JsonRecord, fields: string[]): number | null {
  for (const field of fields) {
    const value = numeric(row[field]);
    if (value !== null) return value;
  }
  return null;
}

function RankingPanel({ rows }: { rows: JsonRecord[] }) {
  return (
    <section className="selection-panel ranking-panel">
      <div className="panel-heading">
        <div>
          <h2>相对强弱与排名依据</h2>
          <p>综合收益、回撤、波动、流动性和财务质量后的研究优先级</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="ranking-list">
        {rows.map((row, index) => (
          <article key={String(row.symbol ?? index)} className="ranking-row">
            <span className="rank-badge">{String(row.rank ?? index + 1)}</span>
            <div>
              <strong>{String(row.name ?? row.symbol ?? '-')}</strong>
              <small>{String(row.symbol ?? '-')} · {String(row.view ?? row.selection_view ?? '观察候选')}</small>
            </div>
            <em>{formatNumber(row.score ?? row.composite_score, 0)}</em>
            <p>{String(row.reason ?? row.ranking_reason ?? row.exclusion_reason ?? '等待更多指标确认。')}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ComparisonTable({ rows }: { rows: JsonRecord[] }) {
  return (
    <section className="selection-panel">
      <div className="panel-heading">
        <div>
          <h2>多标的指标矩阵</h2>
          <p>统一窗口下的行情、收益、风险、流动性和质量对比</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>最新价</th>
              <th>涨跌幅</th>
              <th>120 日收益</th>
              <th>最大回撤</th>
              <th>波动率</th>
              <th>成交额</th>
              <th>综合分</th>
              <th>候选视图</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.symbol ?? index)}>
                <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                <td>{formatNumber(row.price)}</td>
                <td className={tone(row.change_percent)}>{formatPercent(row.change_percent)}</td>
                <td className={tone(row.return_120d_pct ?? row.period_return)}>{formatPercent(row.return_120d_pct ?? row.period_return)}</td>
                <td className="down">{formatPercent(row.max_drawdown)}</td>
                <td>{formatPercent(row.volatility20d)}</td>
                <td>{formatMoney(row.amount ?? row.avg_amount_20d)}</td>
                <td>{formatNumber(row.composite_score, 0)}</td>
                <td>{String(row.selection_view ?? row.relative_strength ?? '-')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BarCompare({ rows, fields, title, subtitle, inverse = false }: {
  rows: JsonRecord[];
  fields: string[];
  title: string;
  subtitle: string;
  inverse?: boolean;
}) {
  const chartRows = rows.slice(0, 8);
  const values = chartRows.map((row) => pickMetric(row, fields) ?? 0);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const range = Math.max(max - min, 0.000001);
  const zeroX = 250 + ((0 - min) / range) * 390;

  return (
    <section className="selection-panel chart-card core-chart-card">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      <svg className="selection-main-chart" viewBox="0 0 720 320" preserveAspectRatio="none" role="img" aria-label={title + '，含坐标轴、标的标签和数值标签'}>
        <rect x="0" y="0" width="720" height="320" className="chart-bg" />
        <line x1="250" y1="44" x2="640" y2="44" className="axis grid" />
        <line x1="250" y1="274" x2="640" y2="274" className="axis" />
        <line x1={zeroX.toFixed(2)} y1="34" x2={zeroX.toFixed(2)} y2="286" className="axis zero-axis" />
        <text x="250" y="304" className="chart-label chart-date">{formatPercent(min)}</text>
        <text x={zeroX.toFixed(2)} y="304" className="chart-label chart-date">0%</text>
        <text x="640" y="304" className="chart-label chart-date">{formatPercent(max)}</text>
        {chartRows.map((row, index) => {
          const value = pickMetric(row, fields) ?? 0;
          const valueX = 250 + ((value - min) / range) * 390;
          const x = Math.min(zeroX, valueX);
          const width = Math.max(3, Math.abs(valueX - zeroX));
          const y = 58 + index * 27;
          const favorable = inverse ? value <= 0 : value >= 0;
          return (
            <g key={String(row.symbol ?? index)}>
              <text x="22" y={(y + 10).toFixed(1)} className="chart-label chart-stock-label">{String(row.name ?? row.symbol ?? '-')}</text>
              <rect
                x={x.toFixed(2)}
                y={y.toFixed(1)}
                width={width.toFixed(2)}
                height="16"
                rx="3"
                className={favorable ? 'bar-up-rect' : 'bar-down-rect'}
              />
              <text x={(valueX + (value >= 0 ? 8 : -8)).toFixed(2)} y={(y + 11).toFixed(1)} className={'chart-label chart-value-label ' + (value >= 0 ? 'value-positive' : 'value-negative')}>
                {formatPercent(value)}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="chart-note">主图按统一横轴缩放，避免只用迷你趋势图造成不可读。</p>
    </section>
  );
}

function Sparkline({ asset }: { asset: JsonRecord }) {
  const bars = asArray(asRecord(asset.kline)?.bars).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  const visible = bars.slice(-50);
  const closes = visible.map((bar) => numeric(bar.close)).filter((value): value is number => value !== null);
  const min = closes.length ? Math.min(...closes) : 0;
  const max = closes.length ? Math.max(...closes) : 1;
  const range = Math.max(max - min, 0.000001);
  const points = closes.map((value, index) => {
    const x = (index / Math.max(closes.length - 1, 1)) * 100;
    const y = 34 - ((value - min) / range) * 28;
    return x.toFixed(2) + ',' + y.toFixed(2);
  }).join(' ');
  return (
    <svg className="sparkline" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label={String(asset.name ?? asset.symbol ?? 'K 线迷你趋势')}>
      <line x1="0" y1="34" x2="100" y2="34" className="axis" />
      {points ? <polyline points={points} fill="none" /> : null}
    </svg>
  );
}

function AssetCards({ assets }: { assets: JsonRecord[] }) {
  return (
    <section className="asset-grid">
      {assets.map((asset, index) => {
        const quote = asRecord(asset.quote);
        const technical = asRecord(asRecord(asset.technicalIndicators)?.summary);
        const quality = asRecord(asset.financialQuality);
        return (
          <article className="asset-card" key={String(asset.symbol ?? index)}>
            <div>
              <strong>{String(asset.name ?? quote?.name ?? asset.symbol)}</strong>
              <small>{String(asset.symbol ?? quote?.symbol ?? '-')} · {String(quality?.quality_label ?? '质量待确认')}</small>
            </div>
            <Sparkline asset={asset} />
            <dl>
              <div><dt>最新价</dt><dd>{formatNumber(quote?.price)}</dd></div>
              <div><dt>120 日</dt><dd className={tone(technical?.return_120d_pct)}>{formatPercent(technical?.return_120d_pct)}</dd></div>
              <div><dt>MA20</dt><dd>{formatNumber(technical?.ma20)}</dd></div>
              <div><dt>质量分</dt><dd>{formatNumber(quality?.quality_score, 0)}</dd></div>
            </dl>
          </article>
        );
      })}
    </section>
  );
}

function FinancialQualityPanel({ rows }: { rows: JsonRecord[] }) {
  return (
    <section className="selection-panel">
      <div className="panel-heading">
        <div>
          <h2>财务质量</h2>
          <p>最近报告期的 ROE、利润率、同比增长和质量标签</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>标的</th><th>ROE</th><th>毛利率</th><th>净利率</th><th>收入同比</th><th>利润同比</th><th>质量分</th><th>标签</th></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.symbol ?? index)}>
                <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                <td>{formatPercent(row.roe_pct)}</td>
                <td>{formatPercent(row.gross_margin_pct)}</td>
                <td>{formatPercent(row.net_margin_pct)}</td>
                <td className={tone(row.revenue_yoy_pct)}>{formatPercent(row.revenue_yoy_pct)}</td>
                <td className={tone(row.net_profit_yoy_pct)}>{formatPercent(row.net_profit_yoy_pct)}</td>
                <td>{formatNumber(row.quality_score, 0)}</td>
                <td>{String(row.quality_label ?? '-')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DataQualityPanel({ data, assets }: { data: JsonRecord | null; assets: JsonRecord[] }) {
  const visualization = asRecord(data?.visualization);
  const components = asArray(visualization?.required_components).map(String);
  return (
    <section className="selection-panel">
      <div className="panel-heading">
        <div>
          <h2>数据信源渠道逐项追踪</h2>
          <p>逐只标的展示实际使用的行情、K 线、财务渠道和样本覆盖。</p>
        </div>
        <span>{String(visualization?.template_id ?? 'stock-selection')}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>标的</th><th>信源渠道</th><th>行情时间</th><th>K 线样本</th><th>报告期</th></tr></thead>
          <tbody>
            {assets.map((asset, index) => {
              const quote = asRecord(asset.quote);
              const kline = asRecord(asset.kline);
              const quality = asRecord(asset.financialQuality);
              return (
                <tr key={String(asset.symbol ?? index)}>
                  <td><strong>{String(asset.name ?? quote?.name ?? asset.symbol)}</strong><small>{String(asset.symbol ?? quote?.symbol ?? '-')}</small></td>
                  <td>{sourceDisplayName(asset.source ?? quote?.source ?? 'eastmoney')}</td>
                  <td>{String(asset.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? '-')}</td>
                  <td>{asArray(kline?.bars).length}</td>
                  <td>{String(quality?.latest_report_date ?? '-').slice(0, 10)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="component-line">模板组件：{components.join(' / ') || '按 stock-selection 标准模板渲染'} · 技术证据：{DATA_FILE}</p>
    </section>
  );
}

export default async function Home() {
  const data = await readDashboardData();
  const assets = getAssets(data);
  const rows = getComparisonRows(data);
  const rankingRows = getRowsFrom(data, 'selectionRanking');
  const financialRows = getRowsFrom(data, 'financialQuality');
  const conclusion = getConclusion(data);
  const leaders = asRecord(asRecord(data?.comparison)?.leaders);
  const requestedSymbols = asArray(data?.requestedSymbols ?? data?.symbols).map(String);
  const topRanking = rankingRows[0] ?? rows.slice().sort((left, right) => (numeric(right.composite_score) ?? -1) - (numeric(left.composite_score) ?? -1))[0];

  return (
    <main className="selection-shell" data-market-proxy="/api/market" data-source-file={DATA_FILE} data-template="stock-selection">
      <section className="selection-hero">
        <div>
          <p className="eyebrow">QuantPilot 选股分析</p>
          <h1>{topRanking ? String(topRanking.name ?? topRanking.symbol) + ' 暂列研究优先级第一' : '多标的选股看板'}</h1>
          <p>覆盖 {requestedSymbols.length || rows.length} 个候选：{requestedSymbols.join('、') || rows.map((row) => String(row.symbol)).join('、')}。以下排序仅用于研究，不构成交易指令。</p>
        </div>
        <aside>
          <span>模板</span>
          <strong>stock-selection</strong>
          <em>读取最终数据并关联信源证据</em>
        </aside>
      </section>

      <section className="summary-grid">
        <article><span>收益领先</span><strong>{String(asRecord(leaders?.best_return)?.name ?? '-')}</strong><em>{formatPercent(asRecord(leaders?.best_return)?.value)}</em></article>
        <article><span>回撤较小</span><strong>{String(asRecord(leaders?.lowest_drawdown)?.name ?? '-')}</strong><em>{formatPercent(asRecord(leaders?.lowest_drawdown)?.value)}</em></article>
        <article><span>波动较低</span><strong>{String(asRecord(leaders?.lowest_volatility)?.name ?? '-')}</strong><em>{formatPercent(asRecord(leaders?.lowest_volatility)?.value)}</em></article>
        <article><span>候选数量</span><strong>{rows.length}</strong><em>{assets.length} 只已绑定数据</em></article>
      </section>

      <ComparisonTable rows={rows} />

      <section className="chart-grid core-chart-grid">
        <BarCompare rows={rows} fields={['return_120d_pct', 'period_return', 'return_120d', 'period_return_pct']} title="收益对比主图" subtitle="统一样本窗口下的阶段收益" />
        <BarCompare rows={rows} fields={['max_drawdown', 'max_drawdown_pct']} title="回撤对比主图" subtitle="回撤越小越稳健" inverse />
        <BarCompare rows={rows} fields={['volatility20d', 'volatility_20d_annualized_pct', 'volatility20d_pct']} title="波动对比主图" subtitle="20 日年化波动率口径" inverse />
      </section>

      <section className="main-grid">
        <RankingPanel rows={rankingRows.length ? rankingRows : rows} />
        <section className="selection-panel conclusion-panel">
          <div className="panel-heading">
            <div>
              <h2>结论摘要</h2>
              <p>事实、计算和限制分层呈现</p>
            </div>
          </div>
          <ul>
            {(conclusion.length ? conclusion : ['真实数据已绑定，等待 Agent 补充更详细的研究解释。']).map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </section>
      </section>

      <AssetCards assets={assets} />

      <FinancialQualityPanel rows={financialRows} />
      <DataQualityPanel data={data} assets={assets} />
    </main>
  );
}
`;
}

function comparisonCss() {
  return `

.comparison-shell {
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  padding: 28px;
}

.comparison-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  padding: 24px 28px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.comparison-hero h1 {
  margin: 4px 0 6px;
  font-size: clamp(26px, 2.8vw, 40px);
  letter-spacing: 0;
}

.comparison-hero p,
.hero-meta {
  color: var(--muted);
}

.eyebrow {
  margin: 0;
  color: var(--red);
  font-weight: 700;
  font-size: 14px;
}

.hero-meta {
  display: grid;
  gap: 6px;
  text-align: right;
  font-size: 14px;
}

.leader-grid,
.chart-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.leader-card,
.comparison-panel,
.comparison-matrix {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.leader-card {
  padding: 20px;
}

.leader-card span {
  display: block;
  color: var(--muted);
  margin-bottom: 8px;
  font-size: 14px;
}

.leader-card strong {
  display: block;
  font-size: 24px;
  white-space: nowrap;
}

.leader-card em {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  font-style: normal;
  font-weight: 800;
  white-space: nowrap;
}

.comparison-matrix,
.comparison-panel {
  margin-top: 14px;
  padding: 20px;
}

.comparison-two-column {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 14px;
}

.correlation-list {
  display: grid;
  gap: 10px;
}

.correlation-row {
  display: grid;
  grid-template-columns: minmax(160px, 0.9fr) minmax(120px, 1fr) 64px;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-1);
}

.correlation-row strong,
.correlation-row small,
.correlation-row em {
  display: block;
}

.correlation-row small {
  margin-top: 2px;
  color: var(--muted);
  font-size: 13px;
}

.correlation-row em {
  color: var(--ink);
  font-style: normal;
  font-weight: 800;
  text-align: right;
}

.correlation-meter {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef2f7;
}

.correlation-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.corr-positive {
  background: var(--red);
}

.corr-negative {
  background: var(--green);
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.panel-heading h2 {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
}

.panel-heading p {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 14px;
}

.panel-heading span {
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
}

.compact-list {
  display: grid;
  gap: 10px;
}

.compact-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.9fr) minmax(100px, 1fr) 64px;
  gap: 8px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-1);
}

.comparison-bars {
  width: 100%;
  height: 220px;
}

.axis {
  stroke: var(--line);
  stroke-width: 0.5;
}

.bar-up rect {
  fill: var(--red);
}

.bar-down rect {
  fill: var(--green);
}

.chart-value-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 14px;
  color: var(--muted);
}

.up {
  color: var(--red);
}

.down {
  color: var(--green);
}

.neutral {
  color: var(--ink);
}

@media (max-width: 900px) {
  .comparison-shell {
    padding: 16px;
  }

  .comparison-hero,
  .panel-heading {
    display: block;
  }

  .hero-meta {
    margin-top: 14px;
    text-align: left;
  }

  .leader-grid,
  .chart-grid,
  .comparison-two-column {
    grid-template-columns: 1fr;
  }

  .leader-grid > *,
  .chart-grid > *,
  .comparison-two-column > * {
    min-width: 0;
  }
}
`;
}

function stockSelectionCss() {
  return `

.selection-shell {
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  padding: 28px;
}

.selection-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 24px;
  align-items: stretch;
  padding: 24px 28px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.selection-hero h1 {
  margin: 6px 0;
  font-size: clamp(26px, 2.8vw, 42px);
  line-height: 1.1;
  letter-spacing: 0;
}

.selection-hero p,
.selection-hero em {
  color: var(--muted);
}

.selection-hero aside,
.selection-panel,
.asset-card,
.summary-grid article {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.selection-hero aside {
  display: grid;
  align-content: center;
  gap: 8px;
  padding: 22px;
}

.selection-hero aside span,
.summary-grid span {
  color: var(--muted);
}

.selection-hero aside strong {
  color: var(--red);
  font-size: 28px;
}

.summary-grid,
.asset-grid,
.chart-grid,
.main-grid {
  display: grid;
  gap: 14px;
  margin-top: 14px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.asset-grid,
.chart-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.core-chart-grid {
  align-items: stretch;
}

.main-grid {
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
}

.summary-grid article,
.asset-card,
.selection-panel {
  padding: 20px;
}

.summary-grid strong,
.summary-grid em,
.asset-card strong,
.asset-card dd,
.ranking-row strong,
.ranking-row em {
  display: block;
}

.summary-grid strong {
  margin-top: 8px;
  font-size: 24px;
  white-space: nowrap;
}

.summary-grid em {
  margin-top: 6px;
  font-style: normal;
  font-weight: 800;
}

.asset-card {
  display: grid;
  gap: 14px;
}

.asset-card dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.asset-card dt {
  color: var(--muted);
  font-size: 13px;
  white-space: nowrap;
}

.asset-card dd {
  margin: 2px 0 0;
  font-weight: 800;
  white-space: nowrap;
}

.sparkline {
  width: 100%;
  height: 68px;
}

.sparkline polyline {
  stroke: var(--blue);
  stroke-width: 2.4;
}

.selection-panel {
  margin-top: 14px;
}

.main-grid .selection-panel {
  margin-top: 0;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.panel-heading h2 {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
}

.panel-heading p {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 14px;
}

.panel-heading span {
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
}

.ranking-list {
  display: grid;
  gap: 10px;
}

.ranking-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 64px;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-1);
}

.ranking-row p {
  grid-column: 2 / -1;
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.rank-badge {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--ink);
  color: #fff;
  font-weight: 800;
  font-size: 15px;
}

.conclusion-panel ul {
  margin: 0;
  padding-left: 20px;
}

.conclusion-panel li + li {
  margin-top: 10px;
}

.core-chart-card {
  min-height: 390px;
}

.selection-main-chart {
  display: block;
  width: 100%;
  height: 290px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-1);
}

.chart-bg {
  fill: var(--surface-1);
}

.chart-label {
  fill: var(--muted);
  font-size: 13px;
  paint-order: stroke;
  stroke: var(--surface-1);
  stroke-width: 3;
  vector-effect: non-scaling-stroke;
}

.chart-stock-label {
  text-anchor: start;
  dominant-baseline: central;
  font-size: 13px;
  font-weight: 700;
}

.chart-date {
  text-anchor: middle;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.chart-value-label {
  dominant-baseline: central;
  font-weight: 800;
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.value-positive {
  text-anchor: start;
}

.value-negative {
  text-anchor: end;
}

.bar-up-rect {
  fill: var(--red);
}

.bar-down-rect {
  fill: var(--green);
}

.axis {
  stroke: var(--line);
  stroke-width: 0.7;
}

.axis.grid {
  opacity: 0.45;
  stroke-dasharray: 3 4;
}

.zero-axis {
  stroke: var(--ink);
  opacity: 0.32;
}

.chart-note {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.component-line {
  margin: 14px 0 0;
  color: var(--muted);
  font-size: 14px;
}

td small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
}

.up {
  color: var(--red);
}

.down {
  color: var(--green);
}

.neutral {
  color: var(--ink);
}

@media (max-width: 980px) {
  .selection-shell {
    padding: 10px;
  }

  .selection-hero {
    display: block;
    padding: 14px;
  }

  .selection-hero h1 {
    margin: 4px 0;
    font-size: 22px;
    line-height: 1.15;
  }

  .selection-hero p {
    margin: 0;
    font-size: 13px;
    line-height: 1.55;
  }

  .selection-hero aside {
    display: none;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 8px;
  }

  .summary-grid article {
    padding: 10px;
  }

  .summary-grid strong {
    margin-top: 4px;
    font-size: 17px;
  }

  .summary-grid em {
    margin-top: 3px;
    font-size: 12px;
  }

  .selection-panel {
    margin-top: 10px;
    padding: 12px;
  }

  .panel-heading {
    margin-bottom: 8px;
  }

  .panel-heading h2 {
    font-size: 15px;
  }

  .panel-heading p {
    font-size: 12px;
  }

  .panel-heading span {
    padding: 2px 7px;
    font-size: 11px;
  }

  .asset-grid,
  .chart-grid,
  .main-grid {
    grid-template-columns: 1fr;
  }

  .summary-grid > *,
  .asset-grid > *,
  .chart-grid > *,
  .main-grid > * {
    min-width: 0;
  }

  .selection-main-chart {
    height: 250px;
  }

  table {
    font-size: 12px;
  }

  th,
  td {
    padding: 7px 8px;
  }
}
`;
}

function holdingAnalysisPageTemplate() {
  return `import fs from 'fs/promises';
import path from 'path';

type JsonRecord = Record<string, unknown>;

const DATA_FILE = 'data_file/final/dashboard-data.json';
const SOURCES_FILE = 'evidence/sources.json';

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as JsonRecord;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: unknown, digits = 2): string {
  const number = numeric(value);
  if (number === null) return '-';
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(number);
}

function formatPercent(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}

function formatMoney(value: unknown): string {
  const number = numeric(value);
  if (number === null) return '-';
  if (Math.abs(number) >= 100000000) return formatNumber(number / 100000000, 2) + ' 亿';
  if (Math.abs(number) >= 10000) return formatNumber(number / 10000, 2) + ' 万';
  return formatNumber(number);
}

function sourceDisplayName(source: unknown, datasetType?: unknown): string {
  const normalized = String(source ?? '').toLowerCase();
  const type = String(datasetType ?? '').toLowerCase();
  if (normalized.includes('eastmoney')) {
    if (/kline|history|历史/.test(type)) return '东方财富历史 K 线接口';
    if (/financial|fundamental|财务/.test(type)) return '东方财富财务数据接口';
    if (/announcement|event|公告/.test(type)) return '东方财富公告事件接口';
    return '东方财富实时行情接口';
  }
  if (normalized.includes('uploaded_image')) return '用户上传截图';
  if (normalized.includes('market_prefetch')) return 'QuantPilot 后端预取';
  if (normalized.includes('tencent')) return '腾讯证券行情接口';
  if (normalized.includes('sina')) return '新浪财经行情接口';
  if (normalized.includes('akshare')) return 'AKShare 免费数据接口';
  if (normalized.includes('local')) return '本地计算结果';
  return String(source ?? '未知信源');
}

function tone(value: unknown): 'up' | 'down' | 'neutral' {
  const number = numeric(value);
  if (number === null || number === 0) return 'neutral';
  return number > 0 ? 'up' : 'down';
}

async function readDashboardData(): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(path.join(process.cwd(), DATA_FILE), 'utf8');
    return asRecord(JSON.parse(content));
  } catch {
    return null;
  }
}

function getAssets(data: JsonRecord | null): JsonRecord[] {
  return asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getHoldings(data: JsonRecord | null): JsonRecord[] {
  const raw = asArray(data?.holdings).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (raw.length > 0) {
    return raw.map((h) => ({
      symbol: h.symbol,
      name: h.name,
      weight: h.weight ?? h.position_pct,
      quantity: h.quantity ?? h.shares,
      cost: h.cost ?? h.cost_price,
      current_price: h.current_price ?? h.price,
      market_value: h.market_value ?? h.marketValue,
      pnl: h.pnl ?? h.profit_loss,
      pnl_pct: h.pnl_pct ?? h.profit_loss_pct,
      as_of: h.as_of ?? h.quote_time ?? h.fetched_at,
      source: h.source,
    }));
  }
  return getAssets(data).map((asset) => {
    const quote = asRecord(asset.quote);
    const position = asRecord(asset.position);
    return {
      symbol: asset.symbol ?? quote?.symbol ?? position?.symbol,
      name: asset.name ?? quote?.name ?? position?.name ?? asset.symbol,
      weight: position?.weight ?? asset.weight,
      quantity: position?.quantity ?? position?.shares ?? asset.quantity ?? asset.shares,
      cost: position?.cost ?? position?.cost_price ?? asset.cost ?? asset.cost_price,
      current_price: quote?.price ?? position?.current_price,
      market_value: position?.market_value ?? asset.market_value,
      pnl: position?.pnl ?? asset.pnl,
      pnl_pct: position?.pnl_pct ?? asset.pnl_pct,
      as_of: asset.as_of ?? quote?.quote_time ?? quote?.fetched_at,
      source: asset.source ?? quote?.source,
    };
  });
}

function getPortfolio(data: JsonRecord | null): JsonRecord | null {
  const portfolio = asRecord(data?.portfolio);
  if (portfolio && (numeric(portfolio.total_value) !== null || numeric(portfolio.total_asset) !== null || numeric(portfolio.market_value) !== null)) {
    return portfolio;
  }
  const holdings = getHoldings(data);
  if (holdings.length === 0) return null;
  const totalMarketValue = holdings.reduce((sum, h) => sum + (numeric(h.market_value) ?? 0), 0);
  const totalCost = holdings.reduce((sum, h) => sum + (numeric(h.cost) ?? 0) * (numeric(h.quantity) ?? 0), 0);
  const hasCostData = holdings.some((h) => numeric(h.cost) !== null && numeric(h.quantity) !== null);
  const totalPnl = hasCostData ? totalMarketValue - totalCost : null;
  return {
    total_value: totalMarketValue,
    cost_basis: hasCostData ? totalCost : null,
    total_pnl: totalPnl,
    total_pnl_pct: hasCostData && totalCost > 0 ? (totalPnl! / totalCost) * 100 : null,
    holdings_count: holdings.length,
    as_of: holdings[0]?.as_of ?? data?.as_of,
  };
}

function getRiskMetrics(data: JsonRecord | null): JsonRecord | null {
  return asRecord(data?.risk) ?? asRecord(data?.risk_metrics);
}

function getComparisonRows(data: JsonRecord | null): JsonRecord[] {
  const comparison = asRecord(data?.comparison);
  const rows = asArray(comparison?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (rows.length > 0) return rows;
  return getAssets(data).map((asset) => {
    const quote = asRecord(asset.quote);
    const metrics = asRecord(asset.computedMetrics);
    const technical = asRecord(asRecord(asset.technicalIndicators)?.summary);
    return {
      symbol: asset.symbol ?? quote?.symbol,
      name: asset.name ?? quote?.name ?? asset.symbol,
      price: quote?.price,
      change_percent: quote?.change_percent,
      period_return: technical?.return_120d_pct ?? metrics?.periodReturn,
      max_drawdown: technical?.max_drawdown_pct ?? metrics?.maxDrawdown,
      volatility20d: technical?.volatility_20d_annualized_pct ?? metrics?.volatility20d,
      avg_volume_20d: metrics?.avgVolume20d,
      amount: quote?.amount,
      as_of: asset.as_of ?? quote?.quote_time ?? quote?.fetched_at,
    };
  });
}

function getSparklineBars(asset: JsonRecord): JsonRecord[] {
  return asArray(asRecord(asset.kline)?.bars).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function weightBarWidth(weight: unknown, maxWeight: number): number {
  return Math.max(4, Math.min(100, ((numeric(weight) ?? 0) / Math.max(maxWeight, 0.01)) * 100));
}

function Sparkline({ asset }: { asset: JsonRecord }) {
  const bars = getSparklineBars(asset).slice(-50);
  const closes = bars.map((bar) => numeric(bar.close)).filter((value): value is number => value !== null);
  const min = closes.length ? Math.min(...closes) : 0;
  const max = closes.length ? Math.max(...closes) : 1;
  const range = Math.max(max - min, 0.000001);
  const points = closes.map((value, index) => {
    const x = (index / Math.max(closes.length - 1, 1)) * 100;
    const y = 34 - ((value - min) / range) * 28;
    return x.toFixed(2) + ',' + y.toFixed(2);
  }).join(' ');
  return (
    <svg className="sparkline" viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label={String(asset.name ?? asset.symbol ?? 'K 线迷你趋势')}>
      <line x1="0" y1="34" x2="100" y2="34" className="axis" />
      {points ? <polyline points={points} fill="none" /> : null}
    </svg>
  );
}

function HoldingCards({ holdings, assets }: { holdings: JsonRecord[]; assets: JsonRecord[] }) {
  return (
    <section className="holding-grid">
      {holdings.map((holding, index) => {
        const asset = assets.find((a) => (a.symbol ?? asRecord(a.quote)?.symbol) === holding.symbol) ?? {};
        const weight = numeric(holding.weight);
        const pnl = numeric(holding.pnl);
        const pnlPct = numeric(holding.pnl_pct);
        return (
          <article className="holding-card" key={String(holding.symbol ?? index)}>
            <div className="holding-card-top">
              <div>
                <strong>{String(holding.name ?? holding.symbol)}</strong>
                <small>{String(holding.symbol ?? '-')} · 权重 {formatPercent(weight)}</small>
              </div>
              <Sparkline asset={asset} />
            </div>
            <dl>
              <div><dt>持有数量</dt><dd>{formatNumber(holding.quantity, 0)} 股</dd></div>
              <div><dt>成本价</dt><dd>{formatNumber(holding.cost)}</dd></div>
              <div><dt>现价</dt><dd>{formatNumber(holding.current_price)}</dd></div>
              <div><dt>市值</dt><dd>{formatMoney(holding.market_value)}</dd></div>
              <div><dt>浮动盈亏</dt><dd className={tone(pnl)}>{formatMoney(pnl)}</dd></div>
              <div><dt>盈亏幅度</dt><dd className={tone(pnlPct)}>{formatPercent(pnlPct)}</dd></div>
            </dl>
          </article>
        );
      })}
    </section>
  );
}

function ConcentrationPanel({ holdings }: { holdings: JsonRecord[] }) {
  const maxWeight = Math.max(0.01, ...holdings.map((h) => numeric(h.weight) ?? 0));
  return (
    <section className="holding-panel">
      <div className="panel-heading">
        <div>
          <h2>仓位集中度</h2>
          <p>按持仓权重从高到低排列；集中度过高可能放大单只标的风险。</p>
        </div>
        <span>{holdings.length} 只</span>
      </div>
      <div className="concentration-list">
        {holdings.map((holding, index) => {
          const weight = numeric(holding.weight) ?? 0;
          const pnlPct = numeric(holding.pnl_pct);
          return (
            <div key={String(holding.symbol ?? index)} className="concentration-row">
              <span className="concentration-label">{String(holding.name ?? holding.symbol ?? '-')}</span>
              <div className="concentration-bar-track">
                <i className={weight >= 20 ? 'bar-heavy' : weight >= 10 ? 'bar-moderate' : 'bar-light'} style={{ width: weightBarWidth(weight, maxWeight) + '%' }} />
              </div>
              <strong className="concentration-pct">{formatPercent(weight)}</strong>
              <em className={tone(pnlPct)}>{formatPercent(pnlPct)}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function HoldingsTable({ holdings }: { holdings: JsonRecord[] }) {
  return (
    <section className="holding-panel">
      <div className="panel-heading">
        <div>
          <h2>持仓明细</h2>
          <p>逐只展示持仓数量、成本、现价、市值和浮动盈亏</p>
        </div>
        <span>{holdings.length} 只</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>数量</th>
              <th>成本价</th>
              <th>现价</th>
              <th>市值</th>
              <th>浮动盈亏</th>
              <th>盈亏%</th>
              <th>权重</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding, index) => {
              const pnl = numeric(holding.pnl);
              const pnlPct = numeric(holding.pnl_pct);
              return (
                <tr key={String(holding.symbol ?? index)}>
                  <td><strong>{String(holding.name ?? holding.symbol)}</strong><small>{String(holding.symbol ?? '-')}</small></td>
                  <td>{formatNumber(holding.quantity, 0)}</td>
                  <td>{formatNumber(holding.cost)}</td>
                  <td>{formatNumber(holding.current_price)}</td>
                  <td>{formatMoney(holding.market_value)}</td>
                  <td className={tone(pnl)}>{formatMoney(pnl)}</td>
                  <td className={tone(pnlPct)}>{formatPercent(pnlPct)}</td>
                  <td>{formatPercent(holding.weight)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ComparisonMetricsPanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length < 2) return null;
  return (
    <section className="holding-panel">
      <div className="panel-heading">
        <div>
          <h2>多标的指标对比</h2>
          <p>统一窗口下的行情、收益、波动和回撤横向比较</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标的</th>
              <th>最新价</th>
              <th>涨跌幅</th>
              <th>区间收益</th>
              <th>最大回撤</th>
              <th>波动率</th>
              <th>20 日均额</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.symbol ?? index)}>
                <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                <td>{formatNumber(row.price)}</td>
                <td className={tone(row.change_percent)}>{formatPercent(row.change_percent)}</td>
                <td className={tone(row.period_return)}>{formatPercent(row.period_return)}</td>
                <td className="down">{formatPercent(row.max_drawdown)}</td>
                <td>{formatPercent(row.volatility20d)}</td>
                <td>{formatMoney(row.avg_volume_20d ?? row.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RiskPanel({ risk }: { risk: JsonRecord | null }) {
  if (!risk) return null;
  const var95 = numeric(risk?.var_95_pct ?? risk?.VaR_95);
  const var99 = numeric(risk?.var_99_pct ?? risk?.VaR_99);
  const expectedShortfall = numeric(risk?.expected_shortfall ?? risk?.cvar_95);
  const correlation = asArray(risk?.correlation_top_pairs).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  return (
    <section className="holding-panel">
      <div className="panel-heading">
        <div>
          <h2>组合风险估算</h2>
          <p>基于历史收益的 VaR、CVaR 和相关性评估；未建模极端事件和流动性冲击。</p>
        </div>
        <span>仅供参考</span>
      </div>
      <div className="risk-grid">
        <article><span>VaR 95%</span><strong>{formatPercent(var95)}</strong></article>
        <article><span>VaR 99%</span><strong>{formatPercent(var99)}</strong></article>
        <article><span>Expected Shortfall</span><strong>{formatPercent(expectedShortfall)}</strong></article>
        <article><span>计算区间</span><strong>{String(risk?.window ?? risk?.sample_window ?? '-')}</strong></article>
      </div>
      {correlation.length > 0 && (
        <div className="correlation-list" style={{ marginTop: 14 }}>
          {correlation.slice(0, 4).map((pair, index) => {
            const corr = numeric(pair.correlation);
            return (
              <div className="correlation-row" key={String(pair.left ?? index) + String(pair.right ?? '')}>
                <div><strong>{String(pair.left ?? '-')} / {String(pair.right ?? '-')}</strong></div>
                <div className="correlation-meter"><span style={{ width: Math.max(4, Math.abs(corr ?? 0) * 100) + '%' }} className={(corr ?? 0) >= 0 ? 'corr-positive' : 'corr-negative'} /></div>
                <em>{formatNumber(corr, 4)}</em>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function DataSourcePanel({ assets }: { assets: JsonRecord[] }) {
  return (
    <section className="holding-panel">
      <div className="panel-heading">
        <div>
          <h2>数据信源渠道</h2>
          <p>逐只标的展示实际数据来源、行情时间和 K 线覆盖。</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>标的</th><th>信源渠道</th><th>行情时间</th><th>K 线样本</th></tr>
          </thead>
          <tbody>
            {assets.map((asset, index) => {
              const quote = asRecord(asset.quote);
              const kline = asRecord(asset.kline);
              return (
                <tr key={String(asset.symbol ?? index)}>
                  <td><strong>{String(asset.name ?? quote?.name ?? asset.symbol)}</strong><small>{String(asset.symbol ?? quote?.symbol ?? '-')}</small></td>
                  <td>{sourceDisplayName(asset.source ?? quote?.source ?? 'eastmoney')}</td>
                  <td>{String(asset.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? '-')}</td>
                  <td>{asArray(kline?.bars).length}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function Home() {
  const data = await readDashboardData();
  const portfolio = getPortfolio(data);
  const holdings = getHoldings(data);
  const assets = getAssets(data);
  const comparisonRows = getComparisonRows(data);
  const risk = getRiskMetrics(data);
  const requestedSymbols = asArray(data?.requestedSymbols ?? data?.symbols).map(String);
  const totalPnl = numeric(portfolio?.total_pnl);
  const totalPnlPct = numeric(portfolio?.total_pnl_pct);

  return (
    <main className="holding-shell" data-market-proxy="/api/market" data-source-file={DATA_FILE} data-template="holding-analysis">
      <section className="holding-hero">
        <div>
          <p className="eyebrow">QuantPilot 持仓分析</p>
          <h1>组合持仓风险看板</h1>
          <p>覆盖 {holdings.length} 只持仓：{holdings.map((h) => String(h.name ?? h.symbol)).join('、')}。以下分析仅用于研究，不构成交易指令。</p>
        </div>
        <div className="hero-summary">
          <article><span>组合市值</span><strong>{formatMoney(portfolio?.total_value)}</strong></article>
          <article><span>持仓成本</span><strong>{formatMoney(portfolio?.cost_basis)}</strong></article>
          <article><span>浮动盈亏</span><strong className={tone(totalPnl)}>{formatMoney(totalPnl)}</strong></article>
          <article><span>盈亏幅度</span><strong className={tone(totalPnlPct)}>{formatPercent(totalPnlPct)}</strong></article>
        </div>
        <div className="hero-meta">
          <span>持仓 {String(portfolio?.holdings_count ?? holdings.length)} 只</span>
          <span>覆盖 {requestedSymbols.length || assets.length} 个标的</span>
          <span>数据时间 {String(portfolio?.as_of ?? holdings[0]?.as_of ?? '-')}</span>
        </div>
      </section>

      <HoldingCards holdings={holdings} assets={assets} />

      <section className="holding-main-grid">
        <HoldingsTable holdings={holdings} />
        <ConcentrationPanel holdings={holdings} />
      </section>

      <ComparisonMetricsPanel rows={comparisonRows} />

      <RiskPanel risk={risk} />

      <DataSourcePanel assets={assets} />
    </main>
  );
}
`;
}

function holdingAnalysisCss() {
  return `

.holding-shell {
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  padding: 28px;
}

.holding-hero {
  display: grid;
  gap: 20px;
  padding: 24px 28px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.holding-hero h1 {
  margin: 4px 0 6px;
  font-size: clamp(26px, 2.8vw, 40px);
  letter-spacing: 0;
}

.holding-hero p {
  color: var(--muted);
}

.hero-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.hero-summary article {
  padding: 16px;
  border: 1px solid var(--line);
  background: var(--surface-1);
  border-radius: 8px;
}

.hero-summary span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 14px;
}

.hero-summary strong {
  display: block;
  font-size: 24px;
  white-space: nowrap;
}

.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  color: var(--muted);
  font-size: 14px;
}

.holding-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.holding-card {
  padding: 18px;
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.holding-card-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 114px;
  gap: 14px;
  align-items: center;
  margin-bottom: 14px;
}

.holding-card-top strong {
  display: block;
  font-size: 17px;
}

.holding-card-top small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 13px;
}

.holding-card dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.holding-card dt {
  color: var(--muted);
  font-size: 13px;
}

.holding-card dd {
  margin: 2px 0 0;
  font-weight: 800;
}

.holding-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
  gap: 14px;
  margin-top: 14px;
}

.holding-panel,
.risk-grid article {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.holding-panel {
  margin-top: 14px;
  padding: 20px;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.panel-heading h2 {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
}

.panel-heading p {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 14px;
}

.panel-heading span {
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
}

.concentration-list {
  display: grid;
  gap: 10px;
}

.concentration-row {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) 60px 64px;
  gap: 12px;
  align-items: center;
}

.concentration-label {
  font-weight: 600;
}

.concentration-bar-track {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef2f7;
}

.concentration-bar-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.bar-heavy { background: var(--red); }
.bar-moderate { background: #e6a817; }
.bar-light { background: #8b9cb8; }

.concentration-pct {
  font-weight: 800;
  text-align: right;
}

.risk-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.risk-grid article {
  padding: 16px;
}

.risk-grid span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 14px;
}

.risk-grid strong {
  display: block;
  font-size: 22px;
  white-space: nowrap;
}

.correlation-list {
  display: grid;
  gap: 10px;
}

.correlation-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.9fr) minmax(100px, 1fr) 56px;
  gap: 12px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-1);
}

.correlation-row strong {
  font-size: 15px;
}

.correlation-row em {
  font-style: normal;
  font-weight: 800;
  text-align: right;
}

.correlation-meter {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef2f7;
}

.correlation-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.corr-positive { background: var(--red); }
.corr-negative { background: var(--green); }

.sparkline {
  width: 100%;
  height: 56px;
}

.sparkline polyline {
  stroke: var(--blue);
  stroke-width: 2.4;
}

.axis {
  stroke: var(--line);
  stroke-width: 0.7;
}

td small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
}

.up { color: var(--red); }
.down { color: var(--green); }
.neutral { color: var(--ink); }

@media (max-width: 980px) {
  .holding-shell {
    padding: 16px;
  }

  .hero-summary,
  .holding-grid,
  .holding-main-grid,
  .risk-grid {
    grid-template-columns: 1fr;
  }

  .hero-summary > *,
  .holding-grid > *,
  .holding-main-grid > *,
  .risk-grid > * {
    min-width: 0;
  }

  .concentration-row {
    grid-template-columns: 80px minmax(0, 1fr) 48px 52px;
    gap: 8px;
  }
}
`;
}

async function ensureComparisonDashboardTemplate(projectPath: string) {
  const finalData = await readJsonRecord(path.join(projectPath, 'data_file', 'final', 'dashboard-data.json'));
  const runPlan = await readJsonRecord(path.join(projectPath, '.quantpilot', 'run_plan.json'));
  const runPlanVisualization = readRecord(runPlan?.visualization);
  const plannedTemplateId =
    typeof runPlanVisualization?.templateId === 'string'
      ? runPlanVisualization.templateId
      : typeof runPlanVisualization?.template_id === 'string'
        ? runPlanVisualization.template_id
        : null;
  const dashboardKind = typeof finalData?.dashboardKind === 'string' ? finalData.dashboardKind : null;
  const visualization = readRecord(finalData?.visualization);
  const templateId =
    typeof visualization?.template_id === 'string'
      ? visualization.template_id
      : typeof visualization?.templateId === 'string'
        ? visualization.templateId
        : null;
  const effectiveTemplateId = plannedTemplateId ?? templateId;

  const isHolding = dashboardKind === 'portfolio_rebalance' || dashboardKind === 'portfolio_risk' || effectiveTemplateId === 'holding-analysis';
  if (isHolding) {
    const assets = Array.isArray(finalData?.assets) ? finalData.assets : [];
    if (assets.length < 2) {
      return;
    }
    const pagePath = path.join(projectPath, 'app', 'page.tsx');
    const page = await fs.readFile(pagePath, 'utf8').catch(() => '');
    if (/data-template="holding-analysis"|持仓明细|仓位集中度|组合风险估算|浮动盈亏/.test(page)) {
      return;
    }
    await fs.writeFile(pagePath, holdingAnalysisPageTemplate(), 'utf8');
    const cssPath = path.join(projectPath, 'app', 'globals.css');
    const css = await fs.readFile(cssPath, 'utf8').catch(() => '');
    if (!css.includes('.holding-shell')) {
      await fs.writeFile(cssPath, `${css.trimEnd()}\n${holdingAnalysisCss()}`, 'utf8');
    }
    return;
  }

  if (effectiveTemplateId && effectiveTemplateId !== 'stock-selection' && effectiveTemplateId !== 'sector-rotation') {
    return;
  }
  const assets = Array.isArray(finalData?.assets) ? finalData.assets : [];
  if (assets.length < 2) {
    return;
  }

  const pagePath = path.join(projectPath, 'app', 'page.tsx');
  const page = await fs.readFile(pagePath, 'utf8').catch(() => '');
  const hasReadableSelectionPage =
    /data-template="stock-selection"/.test(page) &&
    /多标的指标矩阵|指标矩阵|ComparisonTable|comparison\.rows/.test(page) &&
    /收益对比主图|回撤对比主图|波动对比主图|selection-main-chart|chart-label|主图/.test(page);
  if (effectiveTemplateId === 'stock-selection' && hasReadableSelectionPage) {
    const cssPath = path.join(projectPath, 'app', 'globals.css');
    await upsertGeneratedCssBlock(cssPath, 'comparison-dashboard', comparisonCss());
    await upsertGeneratedCssBlock(cssPath, 'stock-selection-dashboard', stockSelectionCss());
    return;
  }
  if (
    effectiveTemplateId !== 'stock-selection' &&
    /多标的相对强弱看板|指标矩阵|收益对比|回撤对比|波动率对比|流动性与可交易性/.test(page) &&
    /comparison-bars|chart-label|主图|矩阵/.test(page)
  ) {
    const cssPath = path.join(projectPath, 'app', 'globals.css');
    await upsertGeneratedCssBlock(cssPath, 'comparison-dashboard', comparisonCss());
    return;
  }

  await fs.writeFile(
    pagePath,
    effectiveTemplateId === 'stock-selection' ? stockSelectionPageTemplate() : comparisonPageTemplate(),
    'utf8'
  );

  const cssPath = path.join(projectPath, 'app', 'globals.css');
  await upsertGeneratedCssBlock(cssPath, 'comparison-dashboard', comparisonCss());
  if (effectiveTemplateId === 'stock-selection') {
    await upsertGeneratedCssBlock(cssPath, 'stock-selection-dashboard', stockSelectionCss());
  }
}

export async function ensureQuantDashboardTemplate(projectPath: string) {
  await ensureComparisonDashboardTemplate(projectPath);
}

export async function scaffoldBasicNextApp(
  projectPath: string,
  projectId: string
) {
  await fs.mkdir(projectPath, { recursive: true });

  const packageJson = {
    name: projectId,
    private: true,
    version: '0.1.0',
    scripts: {
      dev: 'node scripts/run-dev.js',
      build: 'node scripts/run-build.js',
      start: 'next start',
      lint: 'next lint',
    },
    dependencies: {
      next: '^16.2.6',
      react: '^19.2.6',
      'react-dom': '^19.2.6',
    },
    devDependencies: {
      typescript: '^6.0.3',
      '@types/react': '^19.2.15',
      '@types/node': '^22.19.19',
      eslint: '^9.17.0',
      'eslint-config-next': '^16.2.6',
    },
  };

  await mergePackageJson(
    path.join(projectPath, 'package.json'),
    packageJson
  );
  await ensureSharedNodeModules(projectPath);

  await ensureNextConfig(
    path.join(projectPath, 'next.config.js')
  );

  await writeFileIfMissing(
    path.join(projectPath, 'postcss.config.js'),
    `module.exports = {
  plugins: [],
};
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'tsconfig.json'),
    `{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'next-env.d.ts'),
    `/// <reference types="next" />
/// <reference types="next/navigation-types/navigation" />
/// <reference types="next/image-types/global" />

// 注意：此文件由 Next.js 自动维护，通常不需要手动编辑。
// see https://nextjs.org/docs/basic-features/typescript for more information.
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'app/layout.tsx'),
    `import type { ReactNode } from 'react';
import './globals.css';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'app/api/market/[...path]/route.ts'),
    `import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  const { path } = await context.params;
  const target = new URL('http://127.0.0.1:8000/api/v1/' + path.join('/'));
  const source = new URL(request.url);
  source.searchParams.forEach((value, key) => target.searchParams.set(key, value));

  const response = await fetch(target, {
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });
  const body = await response.text();

  return new NextResponse(body, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('Content-Type') ?? 'application/json',
    },
  });
}

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'app/page.tsx'),
    `import fs from 'fs/promises';
import path from 'path';

type JsonRecord = Record<string, unknown>;

const DATA_FILE = 'data_file/final/dashboard-data.json';
const SOURCES_FILE = 'evidence/sources.json';

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as JsonRecord;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
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

function formatNumber(value: unknown, digits = 2): string {
  const number = numeric(value);
  if (number === null) {
    return '-';
  }
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: digits,
  }).format(number);
}

function hasNumber(value: unknown): boolean {
  return numeric(value) !== null;
}

function displayNumber(value: unknown, digits = 2, empty = '待接入'): string {
  const number = numeric(value);
  if (number === null) {
    return empty;
  }
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: digits,
  }).format(number);
}

function formatPercent(value: unknown): string {
  const number = numeric(value);
  if (number === null) {
    return '-';
  }
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}

function displayPercent(value: unknown, empty = '待接入'): string {
  const number = numeric(value);
  if (number === null) {
    return empty;
  }
  return (number > 0 ? '+' : '') + number.toFixed(2) + '%';
}

async function readDashboardData(): Promise<JsonRecord | null> {
  try {
    const content = await fs.readFile(path.join(process.cwd(), DATA_FILE), 'utf8');
    const parsed = JSON.parse(content);
    return asRecord(parsed);
  } catch {
    return null;
  }
}

async function readSourcesEvidence(): Promise<JsonRecord[]> {
  try {
    const content = await fs.readFile(path.join(process.cwd(), SOURCES_FILE), 'utf8');
    const parsed = asRecord(JSON.parse(content));
    return asArray(parsed?.sources)
      .map(asRecord)
      .filter((item): item is JsonRecord => Boolean(item));
  } catch {
    return [];
  }
}

function getBars(data: JsonRecord | null): JsonRecord[] {
  const kline = asRecord(data?.kline) ?? asRecord(data?.history);
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    const primaryAsset = assets.find((asset) => asArray(asRecord(asset.kline)?.bars).length > 0) ?? assets[0];
    return getBars(primaryAsset);
  }
  const candidates = [
    kline?.bars,
    kline?.data,
    kline?.items,
    data?.bars,
    data?.klines,
    data?.candles,
    Array.isArray(data?.history) ? data?.history : null,
  ];
  for (const candidate of candidates) {
    const bars = asArray(candidate).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
    if (bars.length > 0) {
      return bars;
    }
  }
  return [];
}

function getIndicatorSummary(data: JsonRecord | null): JsonRecord | null {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getIndicatorSummary(assets[0]);
  }
  const technical = asRecord(data?.technicalIndicators) ?? asRecord(data?.indicators) ?? asRecord(data?.technical);
  return asRecord(technical?.summary) ?? asRecord(data?.summary);
}

function getFundamentalSummary(data: JsonRecord | null): JsonRecord | null {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getFundamentalSummary(assets[0]);
  }
  const fundamental = asRecord(data?.fundamentalIndicators) ?? asRecord(data?.fundamentals) ?? asRecord(data?.financials);
  return asRecord(fundamental?.summary);
}

function getBacktest(data: JsonRecord | null): JsonRecord | null {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getBacktest(assets[0]);
  }
  return asRecord(data?.backtest);
}

function getReports(data: JsonRecord | null): JsonRecord[] {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getReports(assets[0]);
  }
  const financials = asRecord(data?.financials) ?? asRecord(data?.fundamentals);
  return asArray(financials?.reports ?? data?.reports).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getAnnouncements(data: JsonRecord | null): JsonRecord[] {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getAnnouncements(assets[0]);
  }
  const announcements = asRecord(data?.announcements) ?? asRecord(data?.events);
  return asArray(announcements?.announcements ?? announcements?.items ?? data?.announcement_events).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function formatMoney(value: unknown): string {
  const number = numeric(value);
  if (number === null) {
    return '-';
  }
  if (Math.abs(number) >= 100000000) {
    return formatNumber(number / 100000000, 2) + ' 亿';
  }
  if (Math.abs(number) >= 10000) {
    return formatNumber(number / 10000, 2) + ' 万';
  }
  return formatNumber(number);
}

function displayMoney(value: unknown, empty = '待接入'): string {
  const number = numeric(value);
  if (number === null) {
    return empty;
  }
  return formatMoney(number);
}

function formatDate(value: unknown): string {
  if (typeof value !== 'string' || !value) {
    return '-';
  }
  return value.slice(0, 10);
}

function formatDateTime(value: unknown): string {
  if (typeof value !== 'string' || !value) {
    return '-';
  }
  const normalized = value.replace('T', ' ').replace('Z', '');
  return normalized.slice(0, 19);
}

function displayDateTime(value: unknown): string {
  const formatted = formatDateTime(value);
  return formatted === '-' ? '等待数据接入' : formatted;
}

function qualityTone(status: unknown): 'quality-ok' | 'quality-warning' | 'quality-error' | 'quality-muted' {
  const normalized = String(status ?? '').toLowerCase();
  if (normalized === 'ok' || normalized.includes('pass')) return 'quality-ok';
  if (normalized === 'warning' || normalized.includes('warn')) return 'quality-warning';
  if (normalized === 'error' || normalized.includes('fail')) return 'quality-error';
  return 'quality-muted';
}

function getComputedMetrics(data: JsonRecord | null): JsonRecord | null {
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (assets.length > 0) {
    return getComputedMetrics(assets[0]);
  }
  return asRecord(data?.computedMetrics);
}

function getTechnicalPoints(data: JsonRecord | null): JsonRecord[] {
  const technical = asRecord(data?.technicalIndicators);
  return asArray(technical?.points).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getLiquidityRows(data: JsonRecord | null): JsonRecord[] {
  const liquidity = asRecord(data?.liquidity);
  return asArray(liquidity?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getCorrelationPairs(data: JsonRecord | null): JsonRecord[] {
  const correlation = asRecord(data?.correlation);
  return asArray(correlation?.top_pairs).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getValuationRows(data: JsonRecord | null): JsonRecord[] {
  const valuation = asRecord(data?.valuation);
  const rows = asArray(valuation?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (rows.length > 0) {
    return rows;
  }
  const scenarios = asArray(valuation?.scenarios).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  if (scenarios.length === 0) {
    return [];
  }
  return [{
    symbol: data?.symbol,
    name: data?.name,
    base_metrics: valuation?.base_metrics ?? valuation?.baseMetrics,
    scenarios,
    warnings: valuation?.warnings,
  }];
}

function getTrendTemplateRows(data: JsonRecord | null): JsonRecord[] {
  const trendTemplate = asRecord(data?.trendTemplate) ?? asRecord(data?.trend_template);
  return asArray(trendTemplate?.rows).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getVisualization(data: JsonRecord | null): JsonRecord | null {
  return asRecord(data?.visualization);
}

function getVisualizationRows(visualization: JsonRecord | null): JsonRecord[] {
  const required = asArray(visualization?.required_components).map(String);
  const rendered = new Set(asArray(visualization?.rendered_components).map(String));
  const missing = new Set(asArray(visualization?.missing_components).map(String));
  return required.map((name) => ({
    name,
    status: missing.has(name) ? '待补充' : rendered.has(name) ? '已渲染' : '按模板渲染',
  }));
}

function sourceDisplayName(source: unknown, datasetType?: unknown): string {
  const normalized = String(source ?? '').toLowerCase();
  const type = String(datasetType ?? '').toLowerCase();
  if (normalized.includes('eastmoney')) {
    if (/kline|history|历史/.test(type)) return '东方财富历史 K 线接口';
    if (/financial|fundamental|财务/.test(type)) return '东方财富财务数据接口';
    if (/announcement|event|公告/.test(type)) return '东方财富公告事件接口';
    return '东方财富实时行情接口';
  }
  if (normalized.includes('uploaded_image')) return '用户上传持仓截图';
  if (normalized.includes('market_prefetch')) return 'QuantPilot 后端行情预取';
  if (normalized.includes('tencent')) return '腾讯证券行情接口';
  if (normalized.includes('sina')) return '新浪财经行情接口';
  if (normalized.includes('akshare')) return 'AKShare 免费数据接口';
  if (normalized.includes('local')) return '本地计算结果';
  return String(source ?? '未知信源');
}

function endpointLabel(endpoint: unknown): string {
  const value = String(endpoint ?? '');
  if (!value) return '-';
  if (value.includes('/quotes/realtime')) return '实时行情';
  if (value.includes('/quotes/history')) return '历史 K 线';
  if (value.includes('/fundamentals/financials')) return '财务报表';
  if (value.includes('/announcements')) return '公告事件';
  if (value.includes('/indicators')) return '指标计算';
  if (value.includes('/symbols/resolve')) return '标的解析';
  return value.replace(/^https?:\\/\\/127\\.0\\.0\\.1:8000\\/api\\/v1\\//, '/api/market/');
}

function inferSourceChannels(data: JsonRecord | null, sourceEvidence: JsonRecord[]): JsonRecord[] {
  if (sourceEvidence.length > 0) {
    const unique = new Map<string, JsonRecord>();
    for (const source of sourceEvidence) {
      const datasetType = source.dataset_type ?? source.type ?? source.dataset ?? source.name;
      const channel = sourceDisplayName(source.source, datasetType);
      const endpoint = endpointLabel(source.endpoint ?? source.url ?? source.route);
      const key = [channel, endpoint, String(source.symbol ?? source.name ?? '')].join('|');
      if (!unique.has(key)) {
        unique.set(key, {
          channel,
          dataset: String(datasetType ?? '数据集'),
          endpoint,
          as_of: source.as_of ?? source.quote_time ?? source.fetched_at ?? source.updated_at,
          sample_count: source.sample_count ?? source.rows ?? source.count ?? source.records,
          limitation: source.limitation ?? source.note ?? source.warning,
        });
      }
    }
    return Array.from(unique.values()).slice(0, 8);
  }

  const channels: JsonRecord[] = [];
  const rootSource = data?.source ?? asRecord(data?.quote)?.source ?? 'eastmoney';
  if (asRecord(data?.quote)) {
    const quote = asRecord(data?.quote);
    channels.push({
      channel: sourceDisplayName(rootSource, 'realtime'),
      dataset: '实时行情',
      endpoint: '/api/market/quotes/realtime',
      as_of: quote?.quote_time ?? quote?.fetched_at ?? data?.as_of,
    });
  }
  if (asArray(asRecord(data?.kline)?.bars).length > 0 || getBars(data).length > 0) {
    channels.push({
      channel: sourceDisplayName(rootSource, 'history'),
      dataset: '历史 K 线',
      endpoint: '/api/market/quotes/history',
      as_of: data?.as_of,
      sample_count: getBars(data).length,
    });
  }
  if (asRecord(data?.financials) || asRecord(data?.fundamentalIndicators)) {
    channels.push({
      channel: sourceDisplayName(rootSource, 'financials'),
      dataset: '财务与基本面',
      endpoint: '/api/market/fundamentals/financials',
      as_of: asRecord(data?.financials)?.as_of ?? data?.as_of,
    });
  }
  if (asRecord(data?.announcements)) {
    channels.push({
      channel: sourceDisplayName(rootSource, 'announcements'),
      dataset: '公告事件',
      endpoint: '/api/market/announcements',
      as_of: asRecord(data?.announcements)?.as_of ?? data?.as_of,
    });
  }
  if (asRecord(data?.imageExtraction)) {
    channels.push({
      channel: sourceDisplayName('uploaded_image', 'portfolio'),
      dataset: '截图识别',
      endpoint: '上传附件',
      as_of: asRecord(data?.imageExtraction)?.extracted_at ?? data?.as_of,
    });
  }
  return channels;
}

function movingAverage(values: Array<number | null>, windowSize: number, index: number): number | null {
  if (index + 1 < windowSize) {
    return null;
  }
  const windowValues = values.slice(index + 1 - windowSize, index + 1).filter((value): value is number => value !== null);
  if (windowValues.length < windowSize) {
    return null;
  }
  return windowValues.reduce((sum, value) => sum + value, 0) / windowValues.length;
}

function scaleY(value: number, min: number, max: number): number {
  const range = Math.max(max - min, 0.000001);
  return 350 - ((value - min) / range) * 320;
}

function buildLinePath(values: Array<number | null>, min: number, max: number): string {
  const validCount = values.filter((value): value is number => value !== null).length;
  if (validCount < 2) {
    return '';
  }
  let started = false;
  return values
    .map((value, index) => {
      if (value === null) {
        return '';
      }
      const x = 60 + (index / Math.max(values.length - 1, 1)) * 720;
      const y = scaleY(value, min, max);
      const segment = (started ? 'L ' : 'M ') + x.toFixed(2) + ' ' + y.toFixed(2);
      started = true;
      return segment;
    })
    .filter(Boolean)
    .join(' ');
}

function TrendChart({ bars }: { bars: JsonRecord[] }) {
  const visibleBars = bars.slice(-60);
  const hasBars = visibleBars.length > 0;
  const closes = visibleBars.map((bar) => numeric(bar.close));
  const highs = visibleBars.map((bar) => numeric(bar.high) ?? numeric(bar.close)).filter((value): value is number => value !== null);
  const lows = visibleBars.map((bar) => numeric(bar.low) ?? numeric(bar.close)).filter((value): value is number => value !== null);
  const volumes = visibleBars.map((bar) => numeric(bar.volume) ?? 0);
  const minPrice = lows.length ? Math.min(...lows) : 0;
  const maxPrice = highs.length ? Math.max(...highs) : 1;
  const maxVolume = Math.max(1, ...volumes);
  const ma5 = closes.map((_, index) => movingAverage(closes, 5, index));
  const ma10 = closes.map((_, index) => movingAverage(closes, 10, index));
  const ma20 = closes.map((_, index) => movingAverage(closes, 20, index));
  const priceTicks = [maxPrice, maxPrice - (maxPrice - minPrice) * 0.25, maxPrice - (maxPrice - minPrice) * 0.5, maxPrice - (maxPrice - minPrice) * 0.75, minPrice];
  const dateLabels = visibleBars.length > 0
    ? [
        String(visibleBars[0]?.date ?? '').slice(5) || '-',
        String(visibleBars[Math.floor(visibleBars.length * 0.25)]?.date ?? '').slice(5) || '-',
        String(visibleBars[Math.floor(visibleBars.length * 0.5)]?.date ?? '').slice(5) || '-',
        String(visibleBars[Math.floor(visibleBars.length * 0.75)]?.date ?? '').slice(5) || '-',
        String(visibleBars[visibleBars.length - 1]?.date ?? '').slice(5) || '-',
      ]
    : ['-', '-', '-', '-', '-'];

  return (
    <div className="chart-panel">
      <div className="panel-heading">
        <div>
          <h2>K 线与量价结构</h2>
          <p>OHLC 蜡烛图、MA5/MA10/MA20、成交量和阶段走势</p>
        </div>
        <span>{bars.length} 条样本</span>
      </div>
      <div className="chart-legend">
        <span className="legend-price">K 线</span>
        <span className="legend-ma5">MA5</span>
        <span className="legend-ma10">MA10</span>
        <span className="legend-ma20">MA20</span>
      </div>
      {!hasBars ? (
        <div className="chart-empty-state">
          <strong>等待 K 线数据接入</strong>
          <span>生成器已预留 OHLC、均线和成交量区域；数据文件写入后会自动渲染真实走势。</span>
        </div>
      ) : null}
      <svg className="trend-chart" viewBox="0 0 800 400" preserveAspectRatio="none" role="img" aria-label="K 线 OHLC 趋势图">
        <rect x="0" y="0" width="800" height="400" className="chart-bg" />
        <line x1="60" y1="350" x2="780" y2="350" className="axis" />
        <line x1="60" y1="30" x2="780" y2="30" className="axis muted" />
        <line x1="60" y1="110" x2="780" y2="110" className="axis grid" />
        <line x1="60" y1="190" x2="780" y2="190" className="axis grid" />
        <line x1="60" y1="270" x2="780" y2="270" className="axis grid" />
        <line x1="204" y1="30" x2="204" y2="350" className="axis grid" />
        <line x1="348" y1="30" x2="348" y2="350" className="axis grid" />
        <line x1="492" y1="30" x2="492" y2="350" className="axis grid" />
        <line x1="636" y1="30" x2="636" y2="350" className="axis grid" />
        {priceTicks.map((tick, index) => (
          <text key={index} x="56" y={['25', '105', '185', '275', '355'][index] || '185'} className="chart-label chart-price">
            {formatNumber(tick)}
          </text>
        ))}
        {dateLabels.map((label, index) => (
          <text key={index} x={(60 + index * 180).toFixed(0)} y="385" className="chart-label chart-date">
            {label}
          </text>
        ))}
        {visibleBars.map((bar, index) => {
          const open = numeric(bar.open) ?? numeric(bar.close);
          const close = numeric(bar.close) ?? open;
          const high = numeric(bar.high) ?? Math.max(open ?? 0, close ?? 0);
          const low = numeric(bar.low) ?? Math.min(open ?? 0, close ?? 0);
          if (open === null || close === null) {
            return null;
          }
          const x = 60 + (index / Math.max(visibleBars.length - 1, 1)) * 720;
          const yHigh = scaleY(high, minPrice, maxPrice);
          const yLow = scaleY(low, minPrice, maxPrice);
          const yOpen = scaleY(open, minPrice, maxPrice);
          const yClose = scaleY(close, minPrice, maxPrice);
          const candleTop = Math.min(yOpen, yClose);
          const candleHeight = Math.max(Math.abs(yClose - yOpen), 1.5);
          const candleWidth = 6;
          const up = close >= open;
          const candleLabel = \`\${String(bar.date ?? '-')} 开 \${formatNumber(open)} 高 \${formatNumber(high)} 低 \${formatNumber(low)} 收 \${formatNumber(close)}\`;
          return (
            <g
              key={String(bar.date ?? index)}
              className={up ? 'candle-up' : 'candle-down'}
              aria-label={candleLabel}
              data-tooltip={candleLabel}
            >
              <line x1={x.toFixed(1)} x2={x.toFixed(1)} y1={yHigh.toFixed(1)} y2={yLow.toFixed(1)} />
              <rect x={(x - candleWidth / 2).toFixed(1)} y={candleTop.toFixed(1)} width={candleWidth} height={candleHeight.toFixed(1)} rx="1" />
            </g>
          );
        })}
        <path d={buildLinePath(ma5, minPrice, maxPrice)} className="ma-line ma5" />
        <path d={buildLinePath(ma10, minPrice, maxPrice)} className="ma-line ma10" />
        <path d={buildLinePath(ma20, minPrice, maxPrice)} className="ma-line ma20" />
      </svg>

      <svg className="volume-chart" viewBox="0 0 800 120" preserveAspectRatio="none" role="img" aria-label="成交量柱状图">
        <rect x="0" y="0" width="800" height="120" className="chart-bg" />
        <line x1="60" y1="100" x2="780" y2="100" className="axis" />
        <line x1="60" y1="30" x2="780" y2="30" className="axis muted" />
        <line x1="60" y1="65" x2="780" y2="65" className="axis grid" />
        <line x1="204" y1="0" x2="204" y2="100" className="axis grid" />
        <line x1="348" y1="0" x2="348" y2="100" className="axis grid" />
        <line x1="492" y1="0" x2="492" y2="100" className="axis grid" />
        <line x1="636" y1="0" x2="636" y2="100" className="axis grid" />
        {visibleBars.map((bar, index) => {
          const open = numeric(bar.open) ?? numeric(bar.close) ?? 0;
          const close = numeric(bar.close) ?? open;
          const volume = numeric(bar.volume) ?? 0;
          const barHeight = Math.max(2, (volume / Math.max(maxVolume, 1)) * 80);
          const x = 60 + (index / Math.max(visibleBars.length - 1, 1)) * 720;
          const volumeLabel = \`\${String(bar.date ?? '-')} 成交量 \${formatNumber(volume, 0)}\`;
          return (
            <rect
              key={String(bar.date ?? index)}
              x={(x - 4).toFixed(1)}
              y={(100 - barHeight).toFixed(1)}
              width="8"
              height={barHeight.toFixed(1)}
              rx="1"
              className={close >= open ? 'volume-up' : 'volume-down'}
              aria-label={volumeLabel}
              data-tooltip={volumeLabel}
            />
          );
        })}
      </svg>
    </div>
  );
}

function buildEquityPath(points: JsonRecord[]): string {
  const values = points.map((point) => numeric(point.equity)).filter((value): value is number => value !== null);
  if (values.length < 2) {
    return '';
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.000001);
  return values
    .map((value, index) => {
      const x = 60 + (index / Math.max(values.length - 1, 1)) * 720;
      const y = 85 - ((value - min) / range) * 70;
      return (index === 0 ? 'M ' : 'L ') + x.toFixed(2) + ' ' + y.toFixed(2);
    })
    .join(' ');
}

function BacktestPanel({ backtest }: { backtest: JsonRecord | null }) {
  const summary = asRecord(backtest?.summary);
  const points = asArray(backtest?.equity_curve).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  const trades = asArray(backtest?.trades).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  const equityPath = buildEquityPath(points);

  if (!backtest) {
    return null;
  }

  return (
    <section className="backtest-section">
      <div className="panel-heading">
        <div>
          <h2>回测复盘</h2>
          <p>
            {String(backtest.strategy_name ?? '均线突破')} · MA{String(backtest.fast_window ?? '-')} / MA{String(backtest.slow_window ?? '-')} · 费用 {formatNumber(backtest.fee_bps)} bps
          </p>
        </div>
        <span>{points.length} 个交易日</span>
      </div>

      <div className="metric-strip four-col backtest-metrics">
        <div className="metric-cell"><span className="metric-label">策略收益</span><span className={'metric-value ' + ((numeric(summary?.total_return_pct) ?? 0) >= 0 ? 'red' : 'green')}>{formatPercent(summary?.total_return_pct)}</span></div>
        <div className="metric-cell"><span className="metric-label">标的收益</span><span className={'metric-value ' + ((numeric(summary?.benchmark_return_pct) ?? 0) >= 0 ? 'red' : 'green')}>{formatPercent(summary?.benchmark_return_pct)}</span></div>
        <div className="metric-cell"><span className="metric-label">最大回撤</span><span className="metric-value green">{formatPercent(summary?.max_drawdown_pct)}</span></div>
        <div className="metric-cell"><span className="metric-label">胜率</span><span className="metric-value">{formatPercent(summary?.win_rate_pct)}</span></div>
      </div>

      <div className="backtest-grid">
        <div className="chart-panel embedded">
          <div className="panel-heading compact">
            <div>
              <h2>策略净值</h2>
              <p>全仓/空仓规则下的净值曲线</p>
            </div>
            <span>净值 {formatNumber(summary?.final_equity, 4)}</span>
          </div>
          <svg className="trend-chart" viewBox="0 0 800 100" preserveAspectRatio="none" role="img" aria-label="回测净值曲线">
            <rect x="0" y="0" width="800" height="100" className="chart-bg" />
            <line x1="60" y1="85" x2="780" y2="85" className="axis" />
            <line x1="60" y1="15" x2="780" y2="15" className="axis muted" />
            <line x1="60" y1="50" x2="780" y2="50" className="axis grid" />
            {equityPath ? <path d={equityPath} className="equity-line" /> : null}
          </svg>
        </div>

        <article className="data-panel">
          <h2>交易明细</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>买入</th><th>卖出</th><th>收益</th><th>天数</th></tr>
              </thead>
              <tbody>
                {trades.slice(-8).reverse().map((trade, index) => (
                  <tr key={String(trade.entry_date ?? index)}>
                    <td>{String(trade.entry_date ?? '-')}</td>
                    <td>{String(trade.exit_date ?? trade.status ?? '-')}</td>
                    <td className={(numeric(trade.return_pct) ?? 0) >= 0 ? 'red' : 'green'}>{formatPercent(trade.return_pct)}</td>
                    <td>{formatNumber(trade.holding_days, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="empty-state">当前回测暂未建模滑点、停牌、分红再投资和冲击成本，结果用于策略研究参考。</p>
        </article>
      </div>
    </section>
  );
}

function FinancialPanel({
  reports,
  summary,
}: {
  reports: JsonRecord[];
  summary: JsonRecord | null;
}) {
  const recentReports = reports.slice(0, 6);
  const chartReports = recentReports.slice().reverse();
  const maxRevenue = Math.max(
    1,
    ...chartReports.map((report) => numeric(report.revenue) ?? 0)
  );

  return (
    <article className="data-panel financial-panel">
      <div className="panel-heading compact">
        <div>
          <h2>财务趋势</h2>
          <p>营收、归母净利润、ROE、毛利率和净利率</p>
        </div>
        <span>{reports.length} 期</span>
      </div>

      <div className="mini-metric-grid">
        <div className="mini-metric"><span>最新营收</span><strong>{formatMoney(summary?.latest_revenue)}</strong></div>
        <div><span>归母净利</span><strong>{formatMoney(summary?.latest_parent_net_profit)}</strong></div>
        <div><span>平均 ROE</span><strong>{formatPercent(summary?.avg_roe)}</strong></div>
        <div><span>净利率</span><strong>{formatPercent(summary?.latest_net_margin)}</strong></div>
      </div>

      {chartReports.length > 0 ? (
        <div className="financial-bars" aria-label="财务柱状趋势图">
          {chartReports.map((report, index) => {
            const revenue = numeric(report.revenue) ?? 0;
            const profit = numeric(report.parent_net_profit) ?? 0;
            const revenueHeight = Math.max(8, (revenue / maxRevenue) * 100);
            const profitHeight = Math.max(6, Math.min(100, (profit / maxRevenue) * 100));
            return (
              <div className="financial-bar-group" key={String(report.report_date ?? index)}>
                <div className="bar-stack">
                  <span className="bar revenue" style={{ height: revenueHeight + '%' }} />
                  <span className="bar profit" style={{ height: profitHeight + '%' }} />
                </div>
                <small>{formatDate(report.report_date)}</small>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="empty-state">暂无财务摘要。指数或 ETF 标的通常不提供个股财务报表。</p>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>报告期</th><th>营收</th><th>净利润</th><th>ROE</th><th>毛利率</th></tr>
          </thead>
          <tbody>
            {recentReports.map((report, index) => (
              <tr key={String(report.report_date ?? index)}>
                <td>{formatDate(report.report_date)}</td>
                <td>{formatMoney(report.revenue)}</td>
                <td>{formatMoney(report.parent_net_profit)}</td>
                <td>{formatPercent(report.weighted_roe)}</td>
                <td>{formatPercent(report.gross_margin)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function AnnouncementPanel({ announcements }: { announcements: JsonRecord[] }) {
  const recent = announcements.slice(0, 6);

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>公告事件</h2>
          <p>近期公告标题、日期和事件线索</p>
        </div>
        <span>{announcements.length} 条</span>
      </div>
      {recent.length > 0 ? (
        <ul className="announcement-list">
          {recent.map((item, index) => (
            <li key={String(item.art_code ?? index)}>
              <span>{formatDate(item.notice_date ?? item.display_time)}</span>
              <strong>{String(item.title ?? '未命名公告')}</strong>
              <em>{asArray(item.columns).map(String).join(' / ') || '公告'}</em>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">暂无公告事件。指数或 ETF 标的通常不提供个股公告列表。</p>
      )}
    </article>
  );
}

function LiquidityPanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>流动性摘要</h2>
          <p>20 日成交额、成交量、换手代理和 Amihud 非流动性</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>标的</th><th>等级</th><th>20 日均额</th><th>换手代理</th><th>Amihud x1e9</th></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={String(row.symbol ?? index)}>
                <td><strong>{String(row.name ?? row.symbol)}</strong><small>{String(row.symbol ?? '-')}</small></td>
                <td>{String(row.liquidity_score ?? '-')}</td>
                <td>{formatMoney(row.avg_amount_20d)}</td>
                <td>{formatPercent(row.turnover_proxy_pct)}</td>
                <td>{formatNumber(row.amihud_illiquidity_x1e9, 6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function CorrelationPanel({ pairs }: { pairs: JsonRecord[] }) {
  if (pairs.length === 0) {
    return null;
  }

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>相关性结构</h2>
          <p>基于对齐日期后的日收益率，展示联动最高的标的组合</p>
        </div>
        <span>{pairs.length} 组</span>
      </div>
      <div className="correlation-list compact-list">
        {pairs.slice(0, 6).map((pair, index) => {
          const correlation = numeric(pair.correlation);
          const width = Math.max(4, Math.abs(correlation ?? 0) * 100);
          return (
            <div className="correlation-row compact-row" key={String(pair.left ?? index) + String(pair.right ?? '')}>
              <div>
                <strong>{String(pair.left ?? '-')} / {String(pair.right ?? '-')}</strong>
                <small>重合样本 {formatNumber(pair.overlap, 0)} 个交易日</small>
              </div>
              <div className="correlation-meter">
                <span style={{ width: width + '%' }} className={(correlation ?? 0) >= 0 ? 'corr-positive' : 'corr-negative'} />
              </div>
              <em>{formatNumber(correlation, 4)}</em>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function ValuationPanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>估值情景</h2>
          <p>防守、中性、进攻三档假设；用于研究，不构成收益承诺</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>标的</th><th>当前价</th><th>PE</th><th>EPS</th><th>中性情景价</th><th>中性空间</th></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const metrics = asRecord(row.base_metrics) ?? asRecord(row.baseMetrics) ?? {};
              const scenarios = asArray(row.scenarios).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
              const baseScenario = scenarios.find((item) => item.case === 'base') ?? scenarios[1] ?? scenarios[0];
              return (
                <tr key={String(row.symbol ?? index)}>
                  <td><strong>{String(row.name ?? row.symbol ?? '-')}</strong><small>{String(row.symbol ?? '-')}</small></td>
                  <td>{formatNumber(metrics.price)}</td>
                  <td>{formatNumber(metrics.pe_ttm ?? metrics.pe)}</td>
                  <td>{formatNumber(metrics.eps, 4)}</td>
                  <td>{formatNumber(baseScenario?.implied_price)}</td>
                  <td className={(numeric(baseScenario?.upside_pct) ?? 0) >= 0 ? 'red' : 'green'}>{formatPercent(baseScenario?.upside_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function TrendTemplatePanel({ rows }: { rows: JsonRecord[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>趋势模板</h2>
          <p>MA20/MA60、阶段回撤、量能比和样本长度</p>
        </div>
        <span>{rows.length} 项</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>标的</th><th>状态</th><th>分数</th><th>MA20</th><th>MA60</th><th>20 日收益</th><th>120 日回撤</th></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const metrics = asRecord(row.metrics) ?? {};
              return (
                <tr key={String(row.symbol ?? index)}>
                  <td><strong>{String(row.name ?? row.symbol ?? '-')}</strong><small>{String(row.symbol ?? '-')}</small></td>
                  <td>{String(row.state ?? '-')}</td>
                  <td>{formatNumber(row.score, 0)}</td>
                  <td>{formatNumber(metrics.ma20)}</td>
                  <td>{formatNumber(metrics.ma60)}</td>
                  <td className={(numeric(metrics.return_20d_pct) ?? 0) >= 0 ? 'red' : 'green'}>{formatPercent(metrics.return_20d_pct)}</td>
                  <td className="green">{formatPercent(metrics.max_drawdown_120d_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function VisualizationPlanPanel({ visualization }: { visualization: JsonRecord | null }) {
  const rows = getVisualizationRows(visualization);
  if (!visualization || rows.length === 0) {
    return null;
  }

  return (
    <article className="data-panel">
      <div className="panel-heading compact">
        <div>
          <h2>场景模板</h2>
          <p>{String(visualization.name ?? visualization.template_id ?? 'QuantPilot 场景化看板')}</p>
        </div>
        <span>{String(visualization.template_id ?? '-')}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>必备组件</th><th>状态</th></tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((row, index) => (
              <tr key={String(row.name ?? index)}>
                <td>{String(row.name ?? '-')}</td>
                <td>{String(row.status ?? '-')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function SignalPanel({
  quote,
  latestBar,
  summary,
  computedMetrics,
  data,
}: {
  quote: JsonRecord | null;
  latestBar?: JsonRecord;
  summary: JsonRecord | null;
  computedMetrics: JsonRecord | null;
  data: JsonRecord | null;
}) {
  const latestPrice = numeric(quote?.price ?? latestBar?.close);
  const ma5 = numeric(summary?.ma5 ?? computedMetrics?.ma5);
  const ma20 = numeric(summary?.ma20 ?? computedMetrics?.ma20);
  const volume = numeric(latestBar?.volume);
  const avgVolume = numeric(computedMetrics?.avgVolume20d);
  const aboveMa20 = latestPrice !== null && ma20 !== null ? latestPrice >= ma20 : null;
  const maTrend = ma5 !== null && ma20 !== null ? ma5 >= ma20 : null;
  const volumeSignal = volume !== null && avgVolume !== null ? volume / Math.max(avgVolume, 1) : null;
  const dataQuality = asRecord(data?.data_quality) ?? asRecord(asRecord(data?.kline)?.data_quality);
  const dataQualityStatus = String(dataQuality?.status ?? 'ok');
  const warnings = asArray(dataQuality?.warnings).map(String);

  return (
    <article className="data-panel signal-panel">
      <div className="panel-heading compact">
        <div>
          <h2>量化信号摘要</h2>
          <p>价格位置、均线结构、量能和数据质量</p>
        </div>
        <span className={'quality-pill ' + qualityTone(dataQualityStatus)}>{dataQualityStatus}</span>
      </div>
      <div className="signal-list">
        <div className={'signal-item ' + (aboveMa20 === null ? '' : aboveMa20 ? 'signal-up' : 'signal-down')}>
          <span className="signal-label">价格位置</span>
          <span className={'signal-value ' + (aboveMa20 === null ? '' : aboveMa20 ? 'red' : 'green')}>
            {aboveMa20 === null ? '待确认' : (aboveMa20 ? '站上 MA20' : '低于 MA20')}
            {latestPrice != null && ma20 != null ? <span className="signal-detail"> · {formatNumber(latestPrice)} / {formatNumber(ma20)}</span> : null}
          </span>
        </div>
        <div className={'signal-item ' + (maTrend === null ? '' : maTrend ? 'signal-up' : 'signal-down')}>
          <span className="signal-label">均线结构</span>
          <span className={'signal-value ' + (maTrend === null ? '' : maTrend ? 'red' : 'green')}>
            {maTrend === null ? '待确认' : (maTrend ? '短多排列' : '短线偏弱')}
            {ma5 != null && ma20 != null ? <span className="signal-detail"> · MA5 {formatNumber(ma5)} / MA20 {formatNumber(ma20)}</span> : null}
          </span>
        </div>
        <div className={'signal-item ' + (volumeSignal === null ? '' : volumeSignal >= 1.2 ? 'signal-up' : volumeSignal <= 0.8 ? 'signal-down' : '')}>
          <span className="signal-label">量能状态</span>
          <span className="signal-value">
            {volumeSignal === null ? '待确认' : volumeSignal >= 1.2 ? '放量' : volumeSignal <= 0.8 ? '缩量' : '常态'}
            {volumeSignal != null ? <span className="signal-detail"> · {volumeSignal.toFixed(2)}x</span> : null}
          </span>
        </div>
      </div>
      {warnings.length > 0 ? (
        <ul className="warning-list">
          {warnings.slice(0, 3).map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-state">未检测到阻断性数据质量警告。</p>
      )}
    </article>
  );
}

export default async function Home() {
  const data = await readDashboardData();
  const sourceEvidence = await readSourcesEvidence();
  const assets = asArray(data?.assets).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
  const primaryAsset = assets[0] ?? data;
  const quote = asRecord(primaryAsset?.quote) ?? asRecord(data?.quote);
  const bars = getBars(data);
  const summary = getIndicatorSummary(data);
  const computedMetrics = getComputedMetrics(data);
  const fundamentalSummary = getFundamentalSummary(data);
  const reports = getReports(data);
  const announcements = getAnnouncements(data);
  const backtest = getBacktest(data);
  const liquidityRows = getLiquidityRows(data);
  const correlationPairs = getCorrelationPairs(data);
  const valuationRows = getValuationRows(data);
  const trendTemplateRows = getTrendTemplateRows(data);
  const visualization = getVisualization(data);
  const sourceChannels = inferSourceChannels(data, sourceEvidence);
  const latestBar = bars.at(-1);
  const name = String(primaryAsset?.name ?? quote?.name ?? primaryAsset?.symbol ?? data?.name ?? 'QuantPilot');
  const symbol = String(primaryAsset?.symbol ?? quote?.symbol ?? data?.symbol ?? '-');
  const change = numeric(quote?.change_percent ?? latestBar?.change_percent);
  const isUp = (change ?? 0) >= 0;
  const latestPrice = quote?.price ?? latestBar?.close;
  const previousClose = quote?.previous_close ?? latestBar?.previous_close;
  const todayOpen = quote?.open ?? latestBar?.open;
  const todayHigh = quote?.high ?? latestBar?.high;
  const todayLow = quote?.low ?? latestBar?.low;
  const todayVolume = quote?.volume ?? latestBar?.volume;
  const todayAmount = quote?.amount ?? latestBar?.amount;
  const todayTurnover = quote?.turnover ?? latestBar?.turnover ?? computedMetrics?.turnoverRate;
  const todayAmplitude = quote?.amplitude ?? latestBar?.amplitude;
  const conclusion = asRecord(data?.conclusion);
  const conclusionItems = asArray(conclusion?.summary).map(String).filter(Boolean);
  const hasQuoteData = [
    latestPrice,
    change,
    previousClose,
    todayOpen,
    todayHigh,
    todayLow,
    todayAmount,
    todayTurnover,
  ].some(hasNumber);

  return (
    <main className="dashboard-shell" data-market-proxy="/api/market" data-source-file={DATA_FILE}>
      <section className="hero-panel">
        <div className="top-bar">
          <span className="source-pill">{String(data?.source ?? quote?.source ?? 'eastmoney')}</span>
          <span className="freshness">数据更新于 {displayDateTime(quote?.quote_time ?? data?.as_of)}</span>
        </div>

        <div className="price-header">
          <div className="id-area">
            <span className="eyebrow">A 股实时诊断</span>
            <span className="name">{name}</span>
            <span className="symbol">{symbol} · {String(quote?.market ?? data?.market ?? '待识别市场')}</span>
          </div>
          <div className="quote-area">
            <span className={'price ' + (hasNumber(latestPrice) ? '' : 'is-missing')}>{displayNumber(latestPrice)}</span>
            <span className={'change ' + (hasNumber(change) ? (isUp ? 'up' : 'down') : 'neutral')}>{displayPercent(change)}</span>
            <span className="quote-note">{hasQuoteData ? '涨跌额 ' + formatNumber(quote?.change_amount ?? latestBar?.change_amount) : '等待行情、K 线或财务数据写入'}</span>
          </div>
        </div>

        <div className="meta-row">
          <div className="meta-item"><span className="meta-label">昨收</span><span className="meta-value">{displayNumber(previousClose)}</span></div>
          <div className="meta-item"><span className="meta-label">今开</span><span className="meta-value">{displayNumber(todayOpen)}</span></div>
          <div className="meta-item"><span className="meta-label">最高</span><span className="meta-value red">{displayNumber(todayHigh)}</span></div>
          <div className="meta-item"><span className="meta-label">最低</span><span className="meta-value green">{displayNumber(todayLow)}</span></div>
          <div className="meta-item"><span className="meta-label">振幅</span><span className="meta-value">{displayPercent(todayAmplitude)}</span></div>
          <div className="meta-item"><span className="meta-label">成交额</span><span className="meta-value">{displayMoney(todayAmount)}</span></div>
          <span className="meta-source">行情源：{String(quote?.source ?? data?.source ?? 'eastmoney')}</span>
        </div>

        <div className="insight-strip">
          <article>
            <span>趋势判断</span>
            <strong>{String(summary?.trend_state ?? '等待更多行情确认')}</strong>
          </article>
          <article>
            <span>量能与换手</span>
            <strong>成交量 {displayNumber(todayVolume, 0)} · 换手 {displayPercent(todayTurnover)}</strong>
          </article>
          <article>
            <span>研究结论</span>
            <strong>{String(conclusion?.primary_view ?? conclusionItems[0] ?? '仅作研究展示，不构成交易指令。')}</strong>
          </article>
        </div>
      </section>

      <div className="metric-strip">
        <div className="metric-cell">
          <span className="metric-label">最新价</span>
          <span className="metric-value">{displayNumber(latestPrice)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">涨跌幅</span>
          <span className={'metric-value ' + (hasNumber(change) ? (isUp ? 'red' : 'green') : '')}>{displayPercent(change)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">PE-TTM</span>
          <span className="metric-value">{displayNumber(quote?.pe_ttm ?? quote?.pe ?? summary?.pe_ttm)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">总市值</span>
          <span className="metric-value">{displayMoney(quote?.total_market_cap ?? quote?.market_cap ?? summary?.market_cap)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">换手率</span>
          <span className="metric-value">{displayPercent(todayTurnover)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">MA20</span>
          <span className="metric-value">{displayNumber(summary?.ma20 ?? computedMetrics?.ma20)}</span>
        </div>
      </div>

      <section className="chart-zone">
        <TrendChart bars={bars} />
        <SignalPanel
          quote={quote}
          latestBar={latestBar}
          summary={summary}
          computedMetrics={computedMetrics}
          data={data}
        />
      </section>

      <BacktestPanel backtest={backtest} />

      <div className="metric-strip four-col">
        <div className="metric-cell">
          <span className="metric-label">最新营收</span>
          <span className="metric-value">{formatMoney(fundamentalSummary?.latest_revenue)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">归母净利润</span>
          <span className="metric-value">{formatMoney(fundamentalSummary?.latest_parent_net_profit)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">平均毛利率</span>
          <span className="metric-value">{formatPercent(fundamentalSummary?.avg_gross_margin)}</span>
        </div>
        <div className="metric-cell">
          <span className="metric-label">平均净利率</span>
          <span className="metric-value">{formatPercent(fundamentalSummary?.avg_net_margin)}</span>
        </div>
      </div>

      <section className="content-grid">
        <article className="data-panel">
          <div className="panel-heading compact">
            <div>
              <h2>数据信源渠道</h2>
              <p>展示本次看板实际使用的外部或本地数据渠道。</p>
            </div>
          </div>
          {sourceChannels.length > 0 ? (
            <div className="source-channel-list">
              {sourceChannels.map((source, index) => (
                <div key={index} className="source-channel">
                  <strong>{String(source.channel)}</strong>
                  <span>{String(source.dataset ?? '数据集')}</span>
                  <small>{String(source.endpoint ?? '-')}</small>
                  <em>时间：{formatDate(source.as_of)}{source.sample_count ? ' · 样本 ' + String(source.sample_count) : ''}</em>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-state">暂无可展示的信源渠道，需检查 evidence/sources.json。</p>
          )}
          <p className="evidence-note">技术证据：{SOURCES_FILE} · {DATA_FILE}</p>
        </article>
        <article className="data-panel">
          <h2>最近 K 线</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>日期</th><th>开盘</th><th>最高</th><th>最低</th><th>收盘</th><th>涨跌幅</th><th>成交额</th><th>成交量</th></tr>
              </thead>
              <tbody>
                {bars.slice(-10).reverse().map((bar, index) => (
                  <tr key={String(bar.date ?? index)}>
                    <td>{String(bar.date ?? '-')}</td>
                    <td>{formatNumber(bar.open)}</td>
                    <td>{formatNumber(bar.high)}</td>
                    <td>{formatNumber(bar.low)}</td>
                    <td>{formatNumber(bar.close)}</td>
                    <td className={(numeric(bar.change_percent) ?? 0) >= 0 ? 'red' : 'green'}>{formatPercent(bar.change_percent)}</td>
                    <td>{formatMoney(bar.amount)}</td>
                    <td>{formatNumber(bar.volume, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="content-grid wide">
        <FinancialPanel reports={reports} summary={fundamentalSummary} />
        <AnnouncementPanel announcements={announcements} />
      </section>

      <section className="content-grid wide">
        <LiquidityPanel rows={liquidityRows} />
        <CorrelationPanel pairs={correlationPairs} />
      </section>

      <section className="content-grid wide">
        <ValuationPanel rows={valuationRows} />
        <TrendTemplatePanel rows={trendTemplateRows} />
      </section>

      <section className="content-grid wide">
        <VisualizationPlanPanel visualization={visualization} />
      </section>
    </main>
  );
}
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'app/globals.css'),
    `:root {
  color-scheme: light;
  --bg: #f2f3f7;
  --ink: #1a1e2b;
  --muted: #5f6b7f;
  --line: #d8dce6;
  --line-light: #e9ecf2;
  --panel: #ffffff;
  --red: #d9363e;
  --green: #0e9d5d;
  --blue: #2b6de5;
  --gold: #b88719;
  --purple: #7c3aed;
  --amber-bg: #fff8e5;
  --red-bg: #fef2f2;
  --green-bg: #f0fdf4;
  --blue-bg: #eef4ff;
  --surface-1: #f7f8fb;
  --surface-2: #fafbfd;
  --shadow-sm: 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md: 0 4px 12px rgba(15,23,42,0.06);
  --red-fill: #fef0ef;
  --green-fill: #edf9f2;
  --volume-up-fill: #f2c4c0;
  --volume-down-fill: #b0e0c6;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  overflow-x: hidden;
  background:
    linear-gradient(180deg, #eef4ff 0, #f7f9fd 260px, var(--bg) 100%);
  color: var(--ink);
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI",
    "PingFang SC", "Microsoft YaHei",
    "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  font-variant-numeric: tabular-nums;
}

button,
input,
select,
textarea {
  font: inherit;
}

/* ==================== SHELL ==================== */

.dashboard-shell {
  width: min(1360px, calc(100vw - 40px));
  margin: 0 auto;
  padding: 24px 0 56px;
}

.hero-panel {
  margin-bottom: 16px;
  padding: 20px;
  border: 1px solid rgba(43, 109, 229, 0.16);
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(247, 250, 255, 0.98)),
    var(--panel);
  box-shadow: var(--shadow-md);
}

.eyebrow {
  display: inline-flex;
  width: fit-content;
  margin: 0 0 4px;
  padding: 4px 9px;
  border: 1px solid rgba(43, 109, 229, 0.18);
  border-radius: 999px;
  color: var(--blue);
  background: rgba(43, 109, 229, 0.08);
  font-size: 13px;
  font-weight: 700;
}

/* ==================== TOP BAR ==================== */

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--muted);
}

.source-pill {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid rgba(184, 135, 25, 0.24);
  border-radius: 999px;
  color: #805600;
  background: #fff9e8;
  font-weight: 700;
}

.source-pill::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--gold);
}

.top-bar .freshness {
  display: flex;
  align-items: center;
  gap: 6px;
}

.top-bar .freshness::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
}

/* ==================== PRICE HEADER ==================== */

.price-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 4px;
}

.price-header .id-area {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.price-header .id-area .name {
  font-size: clamp(34px, 4vw, 52px);
  font-weight: 900;
  line-height: 1;
  word-break: break-word;
}

.price-header .id-area .symbol {
  font-size: 15px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.price-header .quote-area {
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px 10px;
  flex-shrink: 0;
  text-align: right;
  max-width: 520px;
}

.price-header .quote-area .price {
  font-size: clamp(36px, 4.2vw, 58px);
  font-weight: 900;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0;
  line-height: 1;
  white-space: nowrap;
}

.price-header .quote-area .price.is-missing {
  font-size: clamp(22px, 2.2vw, 30px);
  color: var(--muted);
  font-family: inherit;
}

.price-header .quote-area .change {
  font-size: 16px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 4px;
  color: #fff;
}

.price-header .quote-area .change.up {
  background: var(--red);
}

.price-header .quote-area .change.down {
  background: var(--green);
}

.price-header .quote-area .change.neutral {
  color: var(--muted);
  background: var(--surface-1);
  border: 1px solid var(--line);
}

.quote-note {
  width: 100%;
  color: var(--muted);
  font-size: 13px;
}

/* ==================== META ROW ==================== */

.meta-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(110px, 1fr)) auto;
  align-items: stretch;
  gap: 10px;
  margin: 16px 0 0;
}

.meta-row .meta-item {
  display: grid;
  gap: 7px;
  min-height: 70px;
  padding: 12px;
  border: 1px solid rgba(216, 220, 230, 0.9);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.74);
  font-size: 14px;
}

.meta-row .meta-item .meta-label {
  color: var(--muted);
}

.meta-row .meta-item .meta-value {
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 18px;
  overflow-wrap: anywhere;
}

.meta-row .meta-source {
  align-self: center;
  justify-self: end;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.insight-strip {
  display: grid;
  grid-template-columns: 1.15fr 0.9fr 1.35fr;
  gap: 12px;
  margin-top: 14px;
}

.insight-strip article {
  min-height: 88px;
  padding: 14px;
  border: 1px solid rgba(43, 109, 229, 0.12);
  border-radius: 8px;
  background: #f8fbff;
}

.insight-strip span {
  display: block;
  margin-bottom: 8px;
  color: var(--blue);
  font-size: 13px;
  font-weight: 800;
}

.insight-strip strong {
  display: block;
  color: #1f2937;
  font-size: 15px;
  line-height: 1.65;
}

/* ==================== METRIC STRIP ==================== */

.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  margin-bottom: 24px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}

.metric-strip .metric-cell {
  padding: 14px 16px;
  background: var(--panel);
}

.metric-strip .metric-cell .metric-label {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 500;
}

.metric-strip .metric-cell .metric-value {
  font-size: 20px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}

.metric-strip.four-col {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

/* ==================== SECTION DIVIDER ==================== */

.section-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 28px 0 14px;
}

.section-divider:first-of-type {
  margin-top: 0;
}

.section-divider h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  flex-shrink: 0;
}

.section-divider .section-meta {
  font-size: 13px;
  color: var(--muted);
}

.section-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--line);
}

/* ==================== CHART ZONE ==================== */

.chart-zone {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.75fr);
  gap: 16px;
  margin-bottom: 24px;
}

.chart-zone > *,
.content-grid > *,
.content-grid.wide > *,
.backtest-grid > *,
.main-grid > *,
.detail-grid > * {
  min-width: 0;
}

.chart-panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  padding: 16px;
  box-shadow: var(--shadow-sm);
}

.data-panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  padding: 16px;
  box-shadow: var(--shadow-sm);
  min-width: 0;
  overflow: hidden;
}

/* ==================== TREND CHART ==================== */

.trend-chart {
  width: 100%;
  height: 380px;
  overflow: hidden;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.volume-chart {
  width: 100%;
  height: 100px;
  margin-top: 10px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--muted);
}

.chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.chart-legend span::before {
  content: "";
  width: 16px;
  height: 3px;
  border-radius: 999px;
  background: currentColor;
}

.chart-empty-state {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px dashed rgba(43, 109, 229, 0.28);
  border-radius: 6px;
  color: var(--muted);
  background: #f8fbff;
}

.chart-empty-state strong {
  color: var(--ink);
  font-size: 15px;
}

.chart-empty-state span {
  font-size: 13px;
  line-height: 1.6;
}

.legend-price { color: var(--ink); }
.legend-ma5 { color: var(--blue); }
.legend-ma10 { color: var(--gold); }
.legend-ma20 { color: var(--purple); }

.chart-bg { fill: var(--surface-1); }

.chart-label {
  fill: var(--muted);
  font-size: 12px;
  paint-order: stroke;
  stroke: var(--surface-1);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.chart-price {
  text-anchor: end;
  dominant-baseline: central;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.chart-date { text-anchor: middle; }

.axis {
  stroke: var(--line);
  stroke-width: 1.2;
}

.axis.muted { opacity: 0.5; }

.axis.grid {
  opacity: 0.4;
  stroke-dasharray: 2 3;
}

.equity-line {
  fill: none;
  stroke: var(--gold);
  stroke-width: 2.4;
  vector-effect: non-scaling-stroke;
}

.candle-up line,
.candle-up rect {
  fill: var(--red-fill);
  stroke: var(--red);
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.candle-down line,
.candle-down rect {
  fill: var(--green-fill);
  stroke: var(--green);
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.ma-line {
  fill: none;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.ma5 { stroke: var(--blue); }
.ma10 { stroke: var(--gold); }
.ma20 { stroke: var(--purple); }

.volume-up {
  fill: var(--volume-up-fill);
  stroke: var(--red);
  stroke-width: 0.5;
  vector-effect: non-scaling-stroke;
}

.volume-down {
  fill: var(--volume-down-fill);
  stroke: var(--green);
  stroke-width: 0.5;
  vector-effect: non-scaling-stroke;
}

/* ==================== PANEL HEADING ==================== */

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.panel-heading.compact {
  align-items: flex-start;
}

.panel-heading h2 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 700;
}

.panel-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}

.panel-heading .pill {
  flex-shrink: 0;
  padding: 3px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

/* ==================== SIGNAL LIST ==================== */

.signal-list {
  display: grid;
  gap: 8px;
}

.signal-list .signal-item {
  padding: 12px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.signal-list .signal-item.signal-up {
  border-color: color-mix(in srgb, var(--red) 28%, var(--line));
  background: var(--red-bg);
}

.signal-list .signal-item.signal-down {
  border-color: color-mix(in srgb, var(--green) 28%, var(--line));
  background: var(--green-bg);
}

.signal-list .signal-item .signal-label {
  display: block;
  margin-bottom: 4px;
  color: var(--muted);
  font-size: 13px;
}

.signal-list .signal-item .signal-value {
  font-size: 18px;
  font-weight: 700;
  white-space: nowrap;
}

.signal-list .signal-item .signal-detail {
  display: block;
  margin-top: 2px;
  font-weight: 400;
  font-size: 13px;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* ==================== WARNING LIST ==================== */

.warning-list {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.warning-list li {
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--gold) 38%, white);
  border-radius: 6px;
  color: #805600;
  background: var(--amber-bg);
  font-size: 13px;
}

/* ==================== QUALITY PILL ==================== */

.quality-pill {
  font-weight: 700;
}

.quality-ok {
  border-color: color-mix(in srgb, var(--green) 28%, var(--line)) !important;
  color: var(--green) !important;
  background: var(--green-bg);
}

.quality-warning {
  border-color: color-mix(in srgb, var(--gold) 34%, var(--line)) !important;
  color: #805600 !important;
  background: var(--amber-bg);
}

.quality-error {
  border-color: color-mix(in srgb, var(--red) 32%, var(--line)) !important;
  color: var(--red) !important;
  background: var(--red-bg);
}

.quality-muted {
  color: var(--muted) !important;
  background: #f8fafc;
}

/* ==================== BACKTEST ==================== */

.backtest-section {
  margin-bottom: 24px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
}

.backtest-section .metric-strip {
  margin-bottom: 14px;
}

.backtest-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
  gap: 14px;
  margin-top: 14px;
}

.chart-panel.embedded {
  margin-top: 0;
}

/* ==================== CONTENT GRID ==================== */

.content-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.4fr);
  gap: 16px;
  margin-bottom: 16px;
}

.content-grid.wide {
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.8fr);
}

/* ==================== SOURCE CHANNELS ==================== */

.source-channel-list {
  display: grid;
  gap: 8px;
}

.source-channel {
  padding: 10px 12px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
  min-width: 0;
}

.source-channel strong {
  display: block;
  margin-bottom: 2px;
  color: var(--ink);
  font-size: 15px;
}

.source-channel span {
  color: var(--muted);
  font-size: 13px;
}

.source-channel small {
  display: block;
  overflow: hidden;
  color: var(--blue);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.source-channel em {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
  overflow-wrap: anywhere;
}

.evidence-note {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 12px;
}

/* ==================== MINI METRICS ==================== */

.mini-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0 16px;
}

.mini-metric-grid .mini-metric {
  padding: 10px 12px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.mini-metric-grid .mini-metric span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 13px;
}

.mini-metric-grid .mini-metric strong {
  font-size: 18px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: nowrap;
}

/* ==================== FINANCIAL BARS ==================== */

.financial-bars {
  display: grid;
  grid-template-columns: repeat(6, minmax(34px, 1fr));
  gap: 8px;
  align-items: end;
  height: 180px;
  margin: 8px 0 16px;
  padding: 12px 8px 0;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.financial-bar-group {
  display: grid;
  gap: 6px;
  align-items: end;
  min-width: 0;
  height: 100%;
}

.bar-stack {
  position: relative;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 3px;
  height: 130px;
}

.bar {
  width: 10px;
  min-height: 4px;
  border-radius: 999px 999px 2px 2px;
}

.bar.revenue { background: var(--blue); }
.bar.profit { background: var(--gold); }

.financial-bar-group small {
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ==================== ANNOUNCEMENTS ==================== */

.announcement-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.announcement-list li {
  padding: 10px 12px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.announcement-list span,
.announcement-list em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.announcement-list strong {
  display: block;
  margin: 4px 0;
  font-size: 15px;
  line-height: 1.45;
}

/* ==================== CORRELATION ==================== */

.correlation-list {
  display: grid;
  gap: 10px;
}

.correlation-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.9fr) minmax(100px, 1fr) 56px;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--line-light);
  border-radius: 6px;
  background: var(--surface-1);
}

.correlation-row strong {
  display: block;
  font-size: 14px;
}

.correlation-row small {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
}

.correlation-row .corr-value {
  color: var(--ink);
  font-weight: 700;
  font-size: 15px;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.correlation-meter {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef2f7;
}

.correlation-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.corr-positive { background: var(--red); }
.corr-negative { background: var(--green); }

/* ==================== EMPTY STATE ==================== */

.empty-state {
  margin: 8px 0 0;
  padding: 12px;
  border: 1px dashed var(--line);
  border-radius: 6px;
  color: var(--muted);
  background: var(--surface-1);
  font-size: 14px;
}

/* ==================== DL ==================== */

dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

dl div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 10px;
}

dt {
  color: var(--muted);
  font-size: 14px;
}

dd {
  margin: 0;
  word-break: break-word;
  font-size: 14px;
}

/* ==================== TABLES ==================== */

.table-wrap {
  overflow-x: auto;
  overflow-y: hidden;
  width: 100%;
  max-width: 100%;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line-light);
  text-align: left;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

th {
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
  position: sticky;
  top: 0;
  z-index: 1;
  color: var(--muted);
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--panel);
}

tbody tr:nth-child(even) {
  background: #f8fafc;
}

tbody tr:hover {
  background: #f1f5f9;
}

/* ==================== SEMANTIC COLORS ==================== */

.red { color: var(--red); }
.green { color: var(--green); }

/* ==================== RESPONSIVE ==================== */

@media (max-width: 800px) {
  .dashboard-shell {
    width: min(100vw - 24px, 720px);
    padding-top: 12px;
  }

  .hero-panel {
    padding: 16px;
  }

  .top-bar {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .price-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .price-header .quote-area {
    text-align: left;
    justify-content: flex-start;
    align-items: center;
    max-width: 100%;
  }

  .price-header .quote-area .price {
    font-size: 28px;
  }

  .price-header .quote-area .price.is-missing {
    font-size: 20px;
  }

  .price-header .quote-area .change {
    font-size: 14px;
  }

  .metric-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric-strip.four-col {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .meta-row,
  .insight-strip {
    grid-template-columns: 1fr;
  }

  .meta-row .meta-source {
    justify-self: start;
  }

  .chart-zone,
  .backtest-grid {
    grid-template-columns: 1fr;
  }

  .chart-zone > *,
  .backtest-grid > * {
    min-width: 0;
  }

  .content-grid,
  .content-grid.wide {
    grid-template-columns: 1fr;
  }

  .content-grid > *,
  .content-grid.wide > * {
    min-width: 0;
  }

  .trend-chart {
    height: 260px;
  }

  .panel-heading {
    flex-direction: column;
    gap: 8px;
  }
}

@media (max-width: 520px) {
  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric-strip.four-col {
    grid-template-columns: 1fr;
  }

  .mini-metric-grid {
    grid-template-columns: 1fr;
  }

  .mini-metric-grid > * {
    min-width: 0;
  }

  .chart-panel,
  .data-panel {
    padding: 12px;
  }

  .price-header .quote-area .price {
    font-size: 24px;
  }

  .financial-bars {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .correlation-row {
    grid-template-columns: minmax(0, 1fr) 56px;
    overflow-x: auto;
  }

  .table-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'scripts/run-build.js'),
    generatedBuildScriptContents()
  );

  await writeFileIfMissing(
    path.join(projectPath, 'scripts/run-dev.js'),
    `#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const isWindows = process.platform === 'win32';

function parseCliArgs(argv) {
  const passthrough = [];
  let preferredPort;

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === '--port' || arg === '-p') {
      const value = argv[i + 1];
      if (value && !value.startsWith('-')) {
        const parsed = Number.parseInt(value, 10);
        if (!Number.isNaN(parsed)) {
          preferredPort = parsed;
        }
        i += 1;
        continue;
      }
    } else if (arg.startsWith('--port=')) {
      const value = arg.slice('--port='.length);
      const parsed = Number.parseInt(value, 10);
      if (!Number.isNaN(parsed)) {
        preferredPort = parsed;
      }
      continue;
    } else if (arg.startsWith('-p=')) {
      const value = arg.slice('-p='.length);
      const parsed = Number.parseInt(value, 10);
      if (!Number.isNaN(parsed)) {
        preferredPort = parsed;
      }
      continue;
    }

    passthrough.push(arg);
  }

  return { preferredPort, passthrough };
}

function resolvePort(preferredPort) {
  const candidates = [
    preferredPort,
    process.env.PORT,
    process.env.WEB_PORT,
    process.env.PREVIEW_PORT_START,
    3100,
  ];

  for (const candidate of candidates) {
    if (candidate === undefined || candidate === null) {
      continue;
    }

    const numeric =
      typeof candidate === 'number'
        ? candidate
        : Number.parseInt(String(candidate), 10);

    if (!Number.isNaN(numeric) && numeric > 0 && numeric <= 65535) {
      return numeric;
    }
  }

  return 3100;
}

(async () => {
  const argv = process.argv.slice(2);
  const { preferredPort, passthrough } = parseCliArgs(argv);
  const port = resolvePort(preferredPort);
  const url =
    process.env.NEXT_PUBLIC_APP_URL || \`http://localhost:\${port}\`;

  process.env.PORT = String(port);
  process.env.WEB_PORT = String(port);
  process.env.NEXT_PUBLIC_APP_URL = url;

  console.log(\`🚀 Starting Next.js dev server on \${url}\`);

  const hasProductionBuild = fs.existsSync(path.join(projectRoot, '.next', 'BUILD_ID'));
  const commandArgs = hasProductionBuild
    ? ['next', 'start', '--port', String(port), ...passthrough]
    : ['next', 'dev', '--port', String(port), ...passthrough];
  if (!hasProductionBuild && !commandArgs.includes('--turbo') && !commandArgs.includes('--turbopack')) {
    commandArgs.push('--turbo');
  }
  const runtimeEnv = {
    ...process.env,
    PORT: String(port),
    WEB_PORT: String(port),
    NEXT_PUBLIC_APP_URL: url,
    QUANTPILOT_WORKSPACE_ROOT:
      process.env.QUANTPILOT_WORKSPACE_ROOT || path.resolve(projectRoot, '../../..'),
    NEXT_TELEMETRY_DISABLED: '1',
  };
  delete runtimeEnv.NEXT_RSPACK;
  delete runtimeEnv.TURBOPACK;

  const child = spawn(
    'npx',
    commandArgs,
    {
      cwd: projectRoot,
      stdio: 'inherit',
      shell: isWindows,
      env: runtimeEnv,
    }
  );

  child.on('exit', (code) => {
    if (typeof code === 'number' && code !== 0) {
      console.error(\`❌ Next.js dev server exited with code \${code}\`);
      process.exit(code);
    }
  });

  child.on('error', (error) => {
    console.error('❌ Failed to start Next.js dev server');
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
})();
`
  );

  await ensureComparisonDashboardTemplate(projectPath);
}
