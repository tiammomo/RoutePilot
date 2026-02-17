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
        destination: 'http://localhost:48081/api/:path*',
      },
    ];
  },
  compress: true,
  // 允许跨域开发请求
  allowedDevOrigins: ['http://localhost:43001', 'http://127.0.0.1:43001'],
};

export default nextConfig;
