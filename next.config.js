const withRspack = require('next-rspack');

const isStandaloneBuild = process.env.QUANTPILOT_STANDALONE_BUILD === '1';
const skipRouteOutputTracing = process.env.QUANTPILOT_SKIP_ROUTE_TRACING !== '0' && !isStandaloneBuild;
const projectRoot = __dirname;
const tracingExcludes = [
  './.git/**',
  './.next/**',
  './.turbo/**',
  './.ruff_cache/**',
  './data/**',
  './tmp/**',
  './services/**/.venv/**',
  './services/**/.ruff_cache/**',
  './coverage/**',
  './dist/**',
  './build/**',
  './out/**',
  './node_modules/.cache/**',
];
const tracePluginIgnores = [
  '**/.git/**',
  '**/.next/**',
  '**/.turbo/**',
  '**/.ruff_cache/**',
  '**/data/**',
  '**/tmp/**',
  '**/services/**/.venv/**',
  '**/services/**/.ruff_cache/**',
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  devIndicators: false,
  allowedDevOrigins: ['127.0.0.1'],
  ...(isStandaloneBuild ? { output: 'standalone' } : {}),
  // Agent、数据库和本地进程管理只在 Node.js API Route 中运行，构建时保持外部依赖。
  serverExternalPackages: [
    '@anthropic-ai/claude-agent-sdk',
    '@prisma/client',
    'prisma',
    'ws',
  ],
  // 关闭 critters 的 CSS 优化，避免构建时缺少可选依赖。
  experimental: {
    optimizeCss: false,
    scrollRestoration: true,
    webpackMemoryOptimizations: true,
    webpackBuildWorker: true,
  },
  // Next 16 defaults dev mode to Turbopack and errors when a webpack() hook
  // exists without a turbopack key. next-rspack still uses TURBOPACK=auto as
  // its activation signal, so keep this empty config to satisfy that check.
  turbopack: {},
  outputFileTracingRoot: projectRoot,
  // 工作区数据、历史项目、本地缓存和 Git 元数据不属于构建产物，避免 trace 扫全仓库。
  outputFileTracingExcludes: {
    '*': tracingExcludes,
    '/api/**': tracingExcludes,
  },
  webpack(config, { isServer }) {
    if (isServer) {
      config.plugins = (config.plugins || []).filter((plugin) => {
        if (plugin?.constructor?.name !== 'TraceEntryPointsPlugin') {
          return true;
        }
        if (skipRouteOutputTracing) {
          return false;
        }
        if (plugin?.constructor?.name === 'TraceEntryPointsPlugin' && Array.isArray(plugin.traceIgnores)) {
          plugin.traceIgnores.push(...tracePluginIgnores);
        }
        return true;
      });
    }
    return config;
  },
  // 注入项目根路径，供前端读取当前工作区信息。避免在配置里调用 process.cwd()，
  // 防止输出追踪误判为需要扫描整个仓库。
  async redirects() { return [{ source: '/observability', destination: '/workspaces?view=trace', permanent: true }]; },
  env: {
    NEXT_PUBLIC_PROJECT_ROOT: process.env.NEXT_PUBLIC_PROJECT_ROOT || '',
  },
};

const shouldUseRspack =
  process.env.QUANTPILOT_DISABLE_RSPACK !== '1' &&
  process.env.TURBOPACK === 'auto';

module.exports = shouldUseRspack ? withRspack(nextConfig) : nextConfig;
