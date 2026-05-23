import fs from 'fs/promises';
import path from 'path';

async function writeFileIfMissing(filePath: string, contents: string) {
  try {
    await fs.access(filePath);
    return;
  } catch {
    // continue
  }
  const dir = path.dirname(filePath);
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(filePath, contents, 'utf8');
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
      build: 'next build --webpack',
      start: 'next start',
      lint: 'next lint',
    },
    dependencies: {
      next: '^16.2.6',
      react: '19.0.0',
      'react-dom': '19.0.0',
    },
    devDependencies: {
      typescript: '^5.7.2',
      '@types/react': '^19.0.0',
      '@types/node': '^22.10.0',
      eslint: '^9.17.0',
      'eslint-config-next': '^16.2.6',
    },
  };

  await writeFileIfMissing(
    path.join(projectPath, 'package.json'),
    `${JSON.stringify(packageJson, null, 2)}\n`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'next.config.js'),
    `/** @type {import('next').NextConfig} */
const projectRoot = __dirname;

const nextConfig = {
  typedRoutes: true,
  outputFileTracingRoot: projectRoot,
  turbopack: {
    root: projectRoot,
  },
};

module.exports = nextConfig;
`
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

function formatPercent(value: unknown): string {
  const number = numeric(value);
  if (number === null) {
    return '-';
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

function getBars(data: JsonRecord | null): JsonRecord[] {
  const kline = asRecord(data?.kline) ?? asRecord(data?.history);
  return asArray(kline?.bars).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getIndicatorSummary(data: JsonRecord | null): JsonRecord | null {
  return asRecord(asRecord(data?.technicalIndicators)?.summary);
}

function buildLinePath(bars: JsonRecord[]): string {
  const closes = bars.map((bar) => numeric(bar.close)).filter((value): value is number => value !== null);
  if (closes.length < 2) {
    return '';
  }
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = Math.max(max - min, 1);
  return closes
    .map((close, index) => {
      const x = (index / Math.max(closes.length - 1, 1)) * 100;
      const y = 86 - ((close - min) / range) * 70;
      return (index === 0 ? 'M ' : 'L ') + x.toFixed(2) + ' ' + y.toFixed(2);
    })
    .join(' ');
}

function TrendChart({ bars }: { bars: JsonRecord[] }) {
  const pathData = buildLinePath(bars);
  const latestBars = bars.slice(-24);

  return (
    <div className="chart-panel">
      <div className="panel-heading">
        <div>
          <h2>K 线趋势</h2>
          <p>收盘价、成交量、均线和阶段走势</p>
        </div>
        <span>{bars.length} 条样本</span>
      </div>
      <svg className="trend-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="K 线趋势图">
        <line x1="0" y1="86" x2="100" y2="86" className="axis" />
        <line x1="0" y1="16" x2="100" y2="16" className="axis muted" />
        {pathData ? <path d={pathData} className="price-line" /> : null}
        {latestBars.map((bar, index) => {
          const change = numeric(bar.change_percent) ?? 0;
          const height = Math.max(5, Math.min(28, Math.abs(change) * 3 + 5));
          const x = 3 + index * 4;
          const y = 91 - height;
          return (
            <rect
              key={String(bar.date ?? index)}
              x={x}
              y={y}
              width="2.4"
              height={height}
              className={change >= 0 ? 'volume-up' : 'volume-down'}
            />
          );
        })}
      </svg>
    </div>
  );
}

export default async function Home() {
  const data = await readDashboardData();
  const quote = asRecord(data?.quote);
  const bars = getBars(data);
  const summary = getIndicatorSummary(data);
  const latestBar = bars.at(-1);
  const name = String(data?.name ?? quote?.name ?? data?.symbol ?? 'QuantPilot');
  const symbol = String(data?.symbol ?? quote?.symbol ?? '-');
  const change = numeric(quote?.change_percent ?? latestBar?.change_percent);
  const isUp = (change ?? 0) >= 0;

  return (
    <main className="dashboard-shell" data-market-proxy="/api/market" data-source-file={DATA_FILE}>
      <section className="hero-band">
        <div>
          <p className="eyebrow">QuantPilot 看板</p>
          <h1>{name}</h1>
          <div className="meta-row">
            <span>{symbol}</span>
            <span>{String(data?.asset_type ?? quote?.asset_type ?? 'stock')}</span>
            <span>{String(data?.source ?? quote?.source ?? 'eastmoney')}</span>
          </div>
        </div>
        <div className={isUp ? 'quote-card up' : 'quote-card down'}>
          <span>最新价</span>
          <strong>{formatNumber(quote?.price ?? latestBar?.close)}</strong>
          <em>{formatPercent(change)}</em>
        </div>
      </section>

      <section className="metric-grid">
        <article>
          <span>区间收益</span>
          <strong>{formatPercent(summary?.period_return_pct)}</strong>
        </article>
        <article>
          <span>最大回撤</span>
          <strong>{formatPercent(summary?.max_drawdown_pct)}</strong>
        </article>
        <article>
          <span>年化波动率</span>
          <strong>{formatPercent(summary?.volatility_annualized_pct)}</strong>
        </article>
        <article>
          <span>MA20</span>
          <strong>{formatNumber(summary?.ma20)}</strong>
        </article>
      </section>

      <TrendChart bars={bars} />

      <section className="detail-grid">
        <article className="data-panel">
          <h2>数据来源</h2>
          <dl>
            <div><dt>时间</dt><dd>{String(data?.as_of ?? quote?.quote_time ?? quote?.fetched_at ?? '-')}</dd></div>
            <div><dt>缓存</dt><dd>{String(asRecord(quote?.fetch)?.cache_status ?? '-')}</dd></div>
            <div><dt>文件</dt><dd>{DATA_FILE}</dd></div>
          </dl>
        </article>
        <article className="data-panel">
          <h2>最近 K 线</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>日期</th><th>收盘</th><th>涨跌幅</th><th>成交量</th></tr>
              </thead>
              <tbody>
                {bars.slice(-6).reverse().map((bar, index) => (
                  <tr key={String(bar.date ?? index)}>
                    <td>{String(bar.date ?? '-')}</td>
                    <td>{formatNumber(bar.close)}</td>
                    <td className={(numeric(bar.change_percent) ?? 0) >= 0 ? 'red' : 'green'}>{formatPercent(bar.change_percent)}</td>
                    <td>{formatNumber(bar.volume, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
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
  --bg: #f7f8fb;
  --ink: #182033;
  --muted: #647087;
  --line: #dfe4ec;
  --panel: #ffffff;
  --red: #d9363e;
  --green: #15945b;
  --blue: #2f6fed;
  --gold: #b88719;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family:
    Arial,
    "Microsoft YaHei",
    sans-serif;
}

button,
input,
select,
textarea {
  font: inherit;
}

.dashboard-shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 32px 0 48px;
}

.hero-band {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 300px);
  gap: 20px;
  align-items: stretch;
  padding: 28px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--gold);
  font-size: 13px;
  font-weight: 700;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 14px;
  font-size: clamp(30px, 5vw, 56px);
  line-height: 1;
  letter-spacing: 0;
}

h2 {
  margin-bottom: 6px;
  font-size: 18px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-row span,
.panel-heading span {
  min-height: 28px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
}

.quote-card {
  display: grid;
  gap: 8px;
  align-content: center;
  min-height: 150px;
  padding: 20px;
  border-radius: 8px;
  color: #fff;
}

.quote-card.up {
  background: var(--red);
}

.quote-card.down {
  background: var(--green);
}

.quote-card span {
  font-size: 14px;
  opacity: 0.82;
}

.quote-card strong {
  font-size: 42px;
  line-height: 1;
}

.quote-card em {
  font-style: normal;
  font-weight: 700;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.metric-grid article,
.chart-panel,
.data-panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.metric-grid article {
  min-height: 92px;
  padding: 18px;
}

.metric-grid span {
  display: block;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 13px;
}

.metric-grid strong {
  font-size: 26px;
}

.chart-panel {
  margin-top: 16px;
  padding: 20px;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.panel-heading p {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 14px;
}

.trend-chart {
  width: 100%;
  height: 330px;
  overflow: visible;
}

.axis {
  stroke: var(--line);
  stroke-width: 0.6;
}

.axis.muted {
  opacity: 0.55;
}

.price-line {
  fill: none;
  stroke: var(--blue);
  stroke-width: 2.2;
  vector-effect: non-scaling-stroke;
}

.volume-up {
  fill: color-mix(in srgb, var(--red) 72%, white);
}

.volume-down {
  fill: color-mix(in srgb, var(--green) 72%, white);
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.9fr) minmax(0, 1.4fr);
  gap: 16px;
  margin-top: 16px;
}

.data-panel {
  padding: 20px;
}

dl {
  display: grid;
  gap: 12px;
  margin: 0;
}

dl div {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
}

dt {
  color: var(--muted);
}

dd {
  margin: 0;
  word-break: break-word;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

th,
td {
  padding: 10px 8px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--muted);
  font-weight: 600;
}

.red {
  color: var(--red);
}

.green {
  color: var(--green);
}

@media (max-width: 800px) {
  .dashboard-shell {
    width: min(100vw - 20px, 720px);
    padding-top: 16px;
  }

  .hero-band,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trend-chart {
    height: 240px;
  }
}

@media (max-width: 520px) {
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .hero-band,
  .chart-panel,
  .data-panel {
    padding: 16px;
  }
}
`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'scripts/run-dev.js'),
    `#!/usr/bin/env node

const { spawn } = require('child_process');
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

  const hasBundlerFlag = passthrough.some((arg) =>
    ['--webpack', '--turbopack'].includes(arg)
  );

  const child = spawn(
    'npx',
    [
      'next',
      'dev',
      '--port',
      String(port),
      ...(hasBundlerFlag ? [] : ['--webpack']),
      ...passthrough,
    ],
    {
      cwd: projectRoot,
      stdio: 'inherit',
      shell: isWindows,
      env: {
        ...process.env,
        PORT: String(port),
        WEB_PORT: String(port),
        NEXT_PUBLIC_APP_URL: url,
        NEXT_TELEMETRY_DISABLED: '1',
      },
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
}
