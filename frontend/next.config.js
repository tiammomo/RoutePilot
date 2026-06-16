import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: frontendRoot,
  async rewrites() {
    const internalApiBase = process.env.INTERNAL_API_BASE || 'http://localhost:38083';
    return [
      {
        source: '/api/:path*',
        destination: `${internalApiBase}/api/:path*`,
      },
    ];
  },
  compress: true,
  allowedDevOrigins: ['localhost:33003'],
};

export default nextConfig;
