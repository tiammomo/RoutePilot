/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // 禁用 Turbopack 使用传统 Webpack
  experimental: {
    turbo: false,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:38000/api/:path*',
      },
    ];
  },
  compress: true,
  // 允许跨域开发请求 - 使用 localhost 确保 WebSocket HMR 正常工作
  allowedDevOrigins: ['localhost:33001', 'localhost:33001'],
};

export default nextConfig;
