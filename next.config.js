/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  output: 'standalone',
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
  },
  // 生成项目、数据快照和本地缓存不属于主应用运行时，避免 standalone tracing 误扫。
  outputFileTracingExcludes: {
    '*': [
      './data/projects/**/.next/**',
      './data/projects/**/node_modules/**',
      './data/projects/**/data_file/**',
      './data/projects/**/evidence/**',
      './backend/market_data/.venv/**',
      './tmp/**',
    ],
  },
  // 注入项目根路径，供前端读取当前工作区信息。避免在配置里调用 process.cwd()，
  // 防止 Turbopack 输出追踪误判为需要扫描整个仓库。
  env: {
    NEXT_PUBLIC_PROJECT_ROOT: process.env.NEXT_PUBLIC_PROJECT_ROOT || '',
  },
};

module.exports = nextConfig;
