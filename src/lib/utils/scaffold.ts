import fs from 'fs/promises';
import path from 'path';

type PackageJsonShape = {
  scripts: Record<string, string>;
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
};

async function writeFileIfMissing(filePath: string, contents: string) {
  try {
    await fs.access(filePath);
  } catch {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    await fs.writeFile(filePath, contents, 'utf8');
  }
}

async function upsertTextFile(filePath: string, contents: string) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, contents, 'utf8');
}

async function mergePackageJson(filePath: string, defaults: PackageJsonShape & Record<string, unknown>) {
  let packageJson = defaults;

  try {
    packageJson = JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    // Missing or invalid generated package.json: rewrite with safe defaults.
  }

  packageJson.scripts = {
    ...defaults.scripts,
    ...(packageJson.scripts ?? {}),
    build: defaults.scripts.build,
    dev: defaults.scripts.dev,
  };

  packageJson.dependencies = {
    ...(packageJson.dependencies ?? {}),
    next: packageJson.dependencies?.next ?? defaults.dependencies.next,
    react: packageJson.dependencies?.react ?? defaults.dependencies.react,
    'react-dom': packageJson.dependencies?.['react-dom'] ?? defaults.dependencies['react-dom'],
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
    typescript: existingDevDependencies.typescript ?? defaults.devDependencies.typescript,
    '@types/react': existingDevDependencies['@types/react'] ?? defaults.devDependencies['@types/react'],
    '@types/node': existingDevDependencies['@types/node'] ?? defaults.devDependencies['@types/node'],
    eslint: existingDevDependencies.eslint ?? defaults.devDependencies.eslint,
    'eslint-config-next':
      existingDevDependencies['eslint-config-next'] ?? defaults.devDependencies['eslint-config-next'],
  };
  delete packageJson.devDependencies['next-rspack'];

  await fs.writeFile(filePath, `${JSON.stringify(packageJson, null, 2)}\n`, 'utf8');
}

export function generatedBuildScriptContents(): string {
  return `#!/usr/bin/env node

const { spawn } = require('child_process');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const isWindows = process.platform === 'win32';
const workspaceRoot =
  process.env.TRAVELPILOT_WORKSPACE_ROOT || path.resolve(projectRoot, '../../..');

const buildEnv = {
  ...process.env,
  NODE_ENV: 'production',
  TRAVELPILOT_WORKSPACE_ROOT: workspaceRoot,
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
  if (code === 0) return;
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

function generatedDevScriptContents(): string {
  return `#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const isWindows = process.platform === 'win32';

function parsePort(argv) {
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if ((arg === '--port' || arg === '-p') && argv[i + 1]) {
      const parsed = Number.parseInt(argv[i + 1], 10);
      if (!Number.isNaN(parsed)) return parsed;
    }
    if (arg.startsWith('--port=')) {
      const parsed = Number.parseInt(arg.slice('--port='.length), 10);
      if (!Number.isNaN(parsed)) return parsed;
    }
  }
  return Number.parseInt(process.env.PORT || process.env.WEB_PORT || '4100', 10);
}

const passthrough = process.argv.slice(2).filter((arg, index, args) => {
  if (arg === '--port' || arg === '-p') return false;
  if ((args[index - 1] === '--port' || args[index - 1] === '-p')) return false;
  return !arg.startsWith('--port=');
});
const port = parsePort(process.argv.slice(2));
const url = process.env.NEXT_PUBLIC_APP_URL || \`http://localhost:\${port}\`;

process.env.PORT = String(port);
process.env.WEB_PORT = String(port);
process.env.NEXT_PUBLIC_APP_URL = url;

console.log(\`Starting Next.js preview on \${url}\`);

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
  TRAVELPILOT_WORKSPACE_ROOT:
    process.env.TRAVELPILOT_WORKSPACE_ROOT || path.resolve(projectRoot, '../../..'),
  NEXT_TELEMETRY_DISABLED: '1',
};

delete runtimeEnv.NEXT_RSPACK;
delete runtimeEnv.TURBOPACK;

const child = spawn('npx', commandArgs, {
  cwd: projectRoot,
  stdio: 'inherit',
  shell: isWindows,
  env: runtimeEnv,
});

child.on('exit', (code) => {
  if (typeof code === 'number' && code !== 0) {
    console.error(\`Next.js preview exited with code \${code}\`);
    process.exit(code);
  }
});

child.on('error', (error) => {
  console.error('Failed to start Next.js preview');
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
`;
}

function pageTemplate(projectId: string) {
  return `import fs from 'fs';
import path from 'path';

type AnyRecord = Record<string, any>;

function readItinerary(): AnyRecord | null {
  const filePath = path.join(process.cwd(), 'data_file', 'final', 'itinerary-data.json');
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function planningOf(data: AnyRecord | null) {
  return data?.planning_response || data || {};
}

function statusText(value: unknown, ok = '满足', bad = '需取舍') {
  return value === false ? bad : ok;
}

export default function Home() {
  const data = readItinerary();
  const planning = planningOf(data);
  const proposals = Array.isArray(planning.proposals) ? planning.proposals.slice(0, 3) : [];
  const primary = proposals[0] || {};
  const checks = primary.constraint_report?.checks || {};
  const sla = planning.generation_metrics?.sla || {};
  const acceleration = planning.acceleration || {};
  const knowledgeGuidance = planning.knowledge_guidance || {};
  const patch = planning.replan_metadata?.adjustment_text || planning.replan_metadata?.route_patch_summary
    ? planning.route_patch_summary || planning.replan_metadata?.route_patch_summary
    : null;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Local intelligent route planner</p>
          <h1>{planning.resolved_area || '北京'}路线规划看板</h1>
        </div>
        <div className="status-pill">
          <span>Project</span>
          <strong>${projectId}</strong>
        </div>
      </header>

      {!data ? (
        <section className="empty">
          <h2>等待生成路线</h2>
          <p>完成一次旅行规划后，这里会读取 data_file/final/itinerary-data.json 并展示可执行路线、约束报告和多方案对比。</p>
        </section>
      ) : (
        <>
          <section className="summary-grid">
            <article>
              <span>10 秒响应</span>
              <strong>{sla.within_10s === false ? '超时' : '达标'}</strong>
              <p>{sla.elapsed_ms ?? planning.generation_metrics?.elapsed_ms ?? '-'} ms · {sla.fast_path || 'local_planner'}</p>
            </article>
            <article>
              <span>POI 串联</span>
              <strong>{checks.poi_count?.actual ?? primary.ordered_poi_names?.length ?? '-'}</strong>
              <p>至少 3 个 POI</p>
            </article>
            <article>
              <span>类型覆盖</span>
              <strong>{checks.category_coverage?.food_count ?? 0} + {checks.category_coverage?.culture_or_entertainment_count ?? 0}</strong>
              <p>餐饮 + 文化/娱乐</p>
            </article>
            <article>
              <span>可用性评分</span>
              <strong>{primary.quality_summary?.competition_readiness_score ? Math.round(primary.quality_summary.competition_readiness_score * 100) + '%' : '-'}</strong>
              <p>时间轴、证据、转场综合</p>
            </article>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <h2>加速与知识库</h2>
              <span>{knowledgeGuidance.enabled ? '知识库引导' : '快路径优先'}</span>
            </div>
            <div className="checks">
              <div><span>语义加速</span><b>{acceleration.layers?.common_semantic_fast_path ? '命中' : '未命中'}</b><small>{acceleration.parser || '-'}</small></div>
              <div><span>缓存层</span><b>{Array.isArray(acceleration.cache_layers_hit) ? acceleration.cache_layers_hit.length : 0} 层</b><small>{Array.isArray(acceleration.cache_layers_hit) ? acceleration.cache_layers_hit.join(' / ') : '-'}</small></div>
              <div><span>知识库</span><b>{knowledgeGuidance.enabled ? '启用' : '未阻塞'}</b><small>{knowledgeGuidance.knowledge_base?.hit_count ?? 0} 条命中</small></div>
            </div>
            <p className="resolution">{knowledgeGuidance.user_visible_summary || '加速层优先保障 10 秒内返回。'}</p>
          </section>

          {patch ? (
            <section className="panel">
              <div className="panel-heading">
                <h2>自然语言调整结果</h2>
                <span>{patch.changed ? '已更新' : '无变化'}</span>
              </div>
              <div className="patch-grid">
                <p><b>调整前</b>{Array.isArray(patch.before_route_names) ? patch.before_route_names.join(' -> ') : '-'}</p>
                <p><b>调整后</b>{Array.isArray(patch.after_route_names) ? patch.after_route_names.join(' -> ') : '-'}</p>
                <p><b>保留/删除/新增</b>{patch.preserved_poi_ids?.length ?? 0}/{patch.removed_poi_ids?.length ?? 0}/{patch.added_poi_ids?.length ?? 0}</p>
              </div>
            </section>
          ) : null}

          <section className="layout">
            <div className="panel">
              <div className="panel-heading">
                <h2>主推路线</h2>
                <span>{primary.display_title || primary.title || primary.strategy || '方案'}</span>
              </div>
              <ol className="timeline">
                {(primary.pois || []).map((poi: AnyRecord, index: number) => (
                  <li key={poi.poi_id || index}>
                    <div className="time">{poi.arrival_time || '--:--'}<small>{poi.departure_time || '--:--'}</small></div>
                    <div>
                      <h3>{poi.name}</h3>
                      <p>{poi.poi_type === 'food' ? '餐饮' : '文化/娱乐'} · 停留 {poi.stay_minutes ?? '-'} 分钟 · 预算 {poi.estimated_cost ?? 0} 元</p>
                      <p>{poi.recommendation_reason || '本地 POI 与 UGC 信号推荐'}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            <aside className="panel">
              <div className="panel-heading">
                <h2>约束报告</h2>
                <span>{primary.constraint_report?.overall_satisfied ? '全部满足' : '显式取舍'}</span>
              </div>
              <div className="checks">
                <div><span>预算</span><b>{statusText(checks.budget?.satisfied)}</b><small>{checks.budget?.estimated_budget ?? primary.total_budget_estimate ?? '-'} 元</small></div>
                <div><span>时长</span><b>{statusText(checks.duration?.satisfied)}</b><small>{checks.duration?.estimated_duration_min ?? primary.total_route_duration_min ?? '-'} 分钟</small></div>
                <div><span>少排队</span><b>{statusText(checks.queue?.satisfied)}</b><small>{checks.queue?.high_queue_stop_names?.length ?? 0} 个风险点</small></div>
                <div><span>少走路</span><b>{statusText(checks.distance?.satisfied)}</b><small>{checks.distance?.estimated_transfer_distance_m ?? primary.total_walking_distance_m ?? '-'} 米</small></div>
                <div><span>营业时间</span><b>{statusText(checks.opening_hours?.satisfied, '可执行', '需复核')}</b><small>{checks.opening_hours?.unknown_count ?? 0} 个未知</small></div>
              </div>
              <p className="resolution">{primary.constraint_resolution?.user_visible_summary || '路线已完成多约束校验。'}</p>
            </aside>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <h2>多方案对比</h2>
              <span>{proposals.length} 套方案</span>
            </div>
            <div className="proposal-grid">
              {proposals.map((proposal: AnyRecord, index: number) => {
                const report = proposal.constraint_report?.checks || {};
                return (
                  <article key={proposal.proposal_id || index}>
                    <h3>{proposal.display_title || proposal.title || '路线方案'}</h3>
                    <p>{Array.isArray(proposal.ordered_poi_names) ? proposal.ordered_poi_names.join(' -> ') : '-'}</p>
                    <dl>
                      <div><dt>时长</dt><dd>{proposal.total_route_duration_min ?? '-'} 分钟</dd></div>
                      <div><dt>预算</dt><dd>{proposal.total_budget_estimate ?? '-'} 元</dd></div>
                      <div><dt>覆盖</dt><dd>{report.category_coverage?.food_count ?? 0} 餐饮 / {report.category_coverage?.culture_or_entertainment_count ?? 0} 文化</dd></div>
                      <div><dt>冲突</dt><dd>{proposal.constraint_resolution?.relaxed_constraints?.length ?? 0} 项</dd></div>
                    </dl>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
`;
}
function cssTemplate() {
  return `:root {
  color-scheme: light;
  --bg: #f6f7f4;
  --ink: #18201c;
  --muted: #647067;
  --panel: #ffffff;
  --soft: #eef3ef;
  --line: #d8ded8;
  --accent: #2f7d68;
  --warn: #a15c21;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: Arial, Helvetica, sans-serif;
}

.shell {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 28px;
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 8px 0 20px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  font-size: 34px;
  line-height: 1.15;
}

h2 {
  margin-bottom: 0;
  font-size: 18px;
}

h3 {
  margin-bottom: 8px;
  font-size: 15px;
}

p {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.65;
}

.status-pill {
  display: grid;
  gap: 4px;
  min-width: 150px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.status-pill span,
.summary-grid span,
.panel-heading span,
.checks span,
dt {
  color: var(--muted);
  font-size: 12px;
}

.status-pill strong,
.summary-grid strong {
  font-size: 20px;
}

.empty,
.panel,
.summary-grid article,
.proposal-grid article {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}

.empty {
  padding: 32px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.summary-grid article {
  min-height: 112px;
  padding: 16px;
}

.summary-grid article > * {
  display: block;
}

.summary-grid p {
  margin: 8px 0 0;
  font-size: 13px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.8fr);
  gap: 12px;
  margin: 12px 0;
}

.panel {
  padding: 18px;
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-heading span {
  padding: 5px 8px;
  border-radius: 6px;
  background: var(--soft);
  color: var(--accent);
  font-weight: 700;
}

.timeline {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline li {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 14px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcfb;
}

.time {
  color: var(--accent);
  font-weight: 800;
}

.time small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-weight: 500;
}

.timeline p {
  margin-bottom: 4px;
}

.checks {
  display: grid;
  gap: 10px;
}

.checks div {
  display: grid;
  grid-template-columns: 74px 72px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 10px;
  border-radius: 8px;
  background: var(--soft);
}

.checks b {
  color: var(--accent);
  font-size: 14px;
}

.checks small {
  color: var(--muted);
  text-align: right;
}

.resolution {
  margin: 14px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.patch-grid {
  display: grid;
  gap: 8px;
}

.patch-grid p {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: var(--soft);
}

.patch-grid b {
  display: block;
  margin-bottom: 4px;
  color: var(--ink);
}

.proposal-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.proposal-grid article {
  padding: 14px;
}

.proposal-grid p {
  min-height: 68px;
  margin-bottom: 12px;
}

dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

dl div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--line);
  padding-top: 8px;
}

dd {
  margin: 0;
  text-align: right;
  font-weight: 700;
}

@media (max-width: 900px) {
  .topbar,
  .layout {
    grid-template-columns: 1fr;
  }

  .topbar {
    display: grid;
  }

  .summary-grid,
  .proposal-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .shell {
    padding: 18px;
  }

  h1 {
    font-size: 28px;
  }

  .summary-grid,
  .proposal-grid,
  .timeline li {
    grid-template-columns: 1fr;
  }

  .checks div {
    grid-template-columns: 1fr;
  }

  .checks small {
    text-align: left;
  }
}
`;
}
async function ensureNextConfig(filePath: string) {
  await writeFileIfMissing(
    filePath,
    `/** @type {import('next').NextConfig} */
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = process.env.TRAVELPILOT_WORKSPACE_ROOT
  ? path.resolve(process.env.TRAVELPILOT_WORKSPACE_ROOT)
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
`
  );
}

export async function ensureTravelDashboardTemplate(projectPath: string) {
  await upsertTextFile(path.join(projectPath, 'app', 'page.tsx'), pageTemplate(path.basename(projectPath)));
  await upsertTextFile(path.join(projectPath, 'app', 'globals.css'), cssTemplate());
}

export async function scaffoldBasicNextApp(projectPath: string, projectId = path.basename(projectPath)) {
  await fs.mkdir(path.join(projectPath, 'app'), { recursive: true });
  await fs.mkdir(path.join(projectPath, 'scripts'), { recursive: true });

  await mergePackageJson(path.join(projectPath, 'package.json'), {
    name: projectId,
    version: '0.1.0',
    private: true,
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
      '@types/node': '^22.19.19',
      '@types/react': '^19.2.15',
      eslint: '^9.39.4',
      'eslint-config-next': '^16.2.6',
      typescript: '^6.0.3',
    },
  });

  await writeFileIfMissing(
    path.join(projectPath, 'tsconfig.json'),
    `${JSON.stringify(
      {
        compilerOptions: {
          target: 'ES2017',
          lib: ['dom', 'dom.iterable', 'esnext'],
          allowJs: true,
          skipLibCheck: true,
          strict: true,
          noEmit: true,
          esModuleInterop: true,
          module: 'esnext',
          moduleResolution: 'bundler',
          resolveJsonModule: true,
          isolatedModules: true,
          jsx: 'react-jsx',
          incremental: true,
          plugins: [{ name: 'next' }],
          paths: { '@/*': ['./*'] },
        },
        include: ['next-env.d.ts', '**/*.ts', '**/*.tsx', '.next/types/**/*.ts'],
        exclude: ['node_modules'],
      },
      null,
      2
    )}\n`
  );

  await writeFileIfMissing(
    path.join(projectPath, 'app', 'layout.tsx'),
    `import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Beijing Travel Agent Preview',
  description: 'Generated travel planning workspace',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
`
  );

  await ensureTravelDashboardTemplate(projectPath);
  await ensureNextConfig(path.join(projectPath, 'next.config.js'));
  await writeFileIfMissing(path.join(projectPath, 'scripts', 'run-build.js'), generatedBuildScriptContents());
  await writeFileIfMissing(path.join(projectPath, 'scripts', 'run-dev.js'), generatedDevScriptContents());
}
