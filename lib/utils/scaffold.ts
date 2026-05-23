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
    const isDefaultNextPage =
      existing.includes('Get started by editing') ||
      existing.includes('src/app/page.tsx') ||
      existing.includes('app/page.tsx') ||
      existing.includes('next/font/google') ||
      existing.includes('https://vercel.com/templates');

    return isDefaultNextPage && !hasQuantDataBinding;
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

  return false;
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

function getFundamentalSummary(data: JsonRecord | null): JsonRecord | null {
  return asRecord(asRecord(data?.fundamentalIndicators)?.summary);
}

function getBacktest(data: JsonRecord | null): JsonRecord | null {
  return asRecord(data?.backtest);
}

function getReports(data: JsonRecord | null): JsonRecord[] {
  const financials = asRecord(data?.financials) ?? asRecord(data?.fundamentals);
  return asArray(financials?.reports).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
}

function getAnnouncements(data: JsonRecord | null): JsonRecord[] {
  const announcements = asRecord(data?.announcements) ?? asRecord(data?.events);
  return asArray(announcements?.announcements).map(asRecord).filter((item): item is JsonRecord => Boolean(item));
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

function formatDate(value: unknown): string {
  if (typeof value !== 'string' || !value) {
    return '-';
  }
  return value.slice(0, 10);
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
      const x = (index / Math.max(values.length - 1, 1)) * 100;
      const y = 86 - ((value - min) / range) * 70;
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

      <div className="metric-grid backtest-metrics">
        <article><span>策略收益</span><strong>{formatPercent(summary?.total_return_pct)}</strong></article>
        <article><span>标的收益</span><strong>{formatPercent(summary?.benchmark_return_pct)}</strong></article>
        <article><span>最大回撤</span><strong>{formatPercent(summary?.max_drawdown_pct)}</strong></article>
        <article><span>胜率</span><strong>{formatPercent(summary?.win_rate_pct)}</strong></article>
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
          <svg className="trend-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="回测净值曲线">
            <line x1="0" y1="86" x2="100" y2="86" className="axis" />
            <line x1="0" y1="16" x2="100" y2="16" className="axis muted" />
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
        <div><span>最新营收</span><strong>{formatMoney(summary?.latest_revenue)}</strong></div>
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

export default async function Home() {
  const data = await readDashboardData();
  const quote = asRecord(data?.quote);
  const bars = getBars(data);
  const summary = getIndicatorSummary(data);
  const fundamentalSummary = getFundamentalSummary(data);
  const reports = getReports(data);
  const announcements = getAnnouncements(data);
  const backtest = getBacktest(data);
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

      <BacktestPanel backtest={backtest} />

      <section className="metric-grid financial-metrics">
        <article>
          <span>最新营收</span>
          <strong>{formatMoney(fundamentalSummary?.latest_revenue)}</strong>
        </article>
        <article>
          <span>归母净利润</span>
          <strong>{formatMoney(fundamentalSummary?.latest_parent_net_profit)}</strong>
        </article>
        <article>
          <span>平均毛利率</span>
          <strong>{formatPercent(fundamentalSummary?.avg_gross_margin)}</strong>
        </article>
        <article>
          <span>平均净利率</span>
          <strong>{formatPercent(fundamentalSummary?.avg_net_margin)}</strong>
        </article>
      </section>

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

      <section className="detail-grid wide">
        <FinancialPanel reports={reports} summary={fundamentalSummary} />
        <AnnouncementPanel announcements={announcements} />
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

.backtest-section {
  margin-top: 16px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.backtest-section .metric-grid {
  margin-top: 0;
}

.backtest-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
  gap: 16px;
  margin-top: 16px;
}

.chart-panel.embedded {
  margin-top: 0;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.panel-heading.compact {
  align-items: flex-start;
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

.equity-line {
  fill: none;
  stroke: var(--gold);
  stroke-width: 2.4;
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

.detail-grid.wide {
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.8fr);
}

.data-panel {
  padding: 20px;
}

.mini-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 18px;
}

.mini-metric-grid div {
  min-height: 76px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcff;
}

.mini-metric-grid span {
  display: block;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
}

.mini-metric-grid strong {
  font-size: 18px;
}

.financial-bars {
  display: grid;
  grid-template-columns: repeat(6, minmax(34px, 1fr));
  gap: 10px;
  align-items: end;
  height: 180px;
  margin: 8px 0 18px;
  padding: 12px 8px 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcff;
}

.financial-bar-group {
  display: grid;
  gap: 8px;
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

.bar.revenue {
  background: var(--blue);
}

.bar.profit {
  background: var(--gold);
}

.financial-bar-group small {
  overflow: hidden;
  color: var(--muted);
  font-size: 11px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.announcement-list {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.announcement-list li {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcff;
}

.announcement-list span,
.announcement-list em {
  color: var(--muted);
  font-size: 12px;
  font-style: normal;
}

.announcement-list strong {
  line-height: 1.45;
}

.empty-state {
  margin: 10px 0 0;
  padding: 14px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  color: var(--muted);
  background: #fbfcff;
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
  .detail-grid,
  .detail-grid.wide,
  .backtest-grid {
    grid-template-columns: 1fr;
  }

  .metric-grid,
  .mini-metric-grid {
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

  .mini-metric-grid {
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
