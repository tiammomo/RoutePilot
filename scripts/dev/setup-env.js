#!/usr/bin/env node

/**
 * 开发环境初始化脚本。
 * - 确保 .env 和 .env.local 存在
 * - 主应用默认优先使用 33003 端口
 * - 同步 NEXT_PUBLIC_APP_URL、PORT、WEB_PORT 等本地配置
 */

const fs = require('fs');
const path = require('path');
const net = require('net');
const crypto = require('crypto');

const rootDir = path.join(__dirname, '..', '..');
const envFile = path.join(rootDir, '.env');
const envLocalFile = path.join(rootDir, '.env.local');
const rootDataDir = path.join(rootDir, 'data');
const projectsDir = path.join(rootDataDir, 'projects');

const MAX_PORT = 65_535;
// Preview servers (per-project) dynamic pool
const FALLBACK_PORT_START = 4_100;
const FALLBACK_PORT_END = 4_999;
const DEFAULT_RANGE_SPAN = FALLBACK_PORT_END - FALLBACK_PORT_START;
// 北京旅游 Agent 主应用默认端口，扫描范围避开生成项目预览端口池
const DEFAULT_WEB_PORT = 33_003;
const DEFAULT_WEB_SCAN_SPAN = 99; // scan up to 33102 at most
const DEFAULT_WEB_MAX = DEFAULT_WEB_PORT + DEFAULT_WEB_SCAN_SPAN;

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function readFileSafe(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch {
    return '';
  }
}

function writeFileSafe(filePath, contents) {
  if (!contents.endsWith('\n')) {
    contents += '\n';
  }
  fs.writeFileSync(filePath, contents, 'utf8');
}

function upsertEnvValue(contents, key, value) {
  const pattern = new RegExp(`^${escapeRegExp(key)}=.*$`, 'm');
  if (pattern.test(contents)) {
    return contents.replace(pattern, `${key}=${value}`);
  }

  if (contents.length && !contents.endsWith('\n')) {
    contents += '\n';
  }

  return contents + `${key}=${value}\n`;
}

function hasEnvKey(contents, key) {
  if (!contents) return false;
  const pattern = new RegExp(`^${escapeRegExp(key)}=`, 'm');
  return pattern.test(contents);
}

function readEnvRawValue(contents, key) {
  if (!contents) return '';
  const pattern = new RegExp(`^${escapeRegExp(key)}=["']?([^"'\\n]+)["']?$`, 'm');
  const match = contents.match(pattern);
  return match ? match[1] : '';
}

function shouldSetPostgresDatabaseUrl(contents) {
  const current = readEnvRawValue(contents, 'DATABASE_URL');
  if (!current) return true;
  return !current.startsWith('postgresql://') && !current.startsWith('postgres://');
}

function randomLocalPassword() {
  return crypto.randomBytes(18).toString('base64url');
}

function ensureDirectory(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function extractPort(contents, keys) {
  for (const key of keys) {
    const pattern = new RegExp(
      `^${escapeRegExp(key)}=["']?([0-9]{2,5})["']?$`,
      'm'
    );
    const match = contents.match(pattern);
    if (match) {
      const port = Number.parseInt(match[1], 10);
      if (!Number.isNaN(port) && port > 0 && port <= MAX_PORT) {
        return port;
      }
    }
  }
  return null;
}

function parsePortValue(value) {
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }
  const numeric = Number.parseInt(value, 10);
  if (Number.isNaN(numeric) || numeric <= 0 || numeric > MAX_PORT) {
    return null;
  }
  return numeric;
}

function checkPort(host, port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const cleanup = (available) => {
      socket.removeAllListeners();
      try {
        socket.end();
        socket.destroy();
      } catch (_) {
        // no-op
      }
      resolve(available);
    };

    socket.once('connect', () => cleanup(false));
    socket.once('error', () => cleanup(true));
    socket.setTimeout(500, () => cleanup(true));
  });
}

async function isPortAvailable(port) {
  const results = await Promise.allSettled([
    checkPort('127.0.0.1', port),
    checkPort('::1', port),
  ]);

  // Treat IPv6 errors (e.g., not supported) as available
  return results.every((result) => {
    if (result.status === 'fulfilled') {
      return result.value;
    }
    return true;
  });
}

async function findAvailablePort(rangeStart, rangeEnd, preferredPort) {
  if (rangeStart > rangeEnd) {
    throw new Error(
      `Invalid port range: start ${rangeStart} is greater than end ${rangeEnd}.`
    );
  }

  const normalizedPreferred = Math.min(
    Math.max(preferredPort ?? rangeStart, rangeStart),
    rangeEnd
  );

  for (let port = normalizedPreferred; port <= rangeEnd; port += 1) {
    // eslint-disable-next-line no-await-in-loop
    const available = await isPortAvailable(port);
    if (available) {
      return port;
    }
  }

  for (let port = rangeStart; port < normalizedPreferred; port += 1) {
    // eslint-disable-next-line no-await-in-loop
    const available = await isPortAvailable(port);
    if (available) {
      return port;
    }
  }

  throw new Error(
    `Could not find an available port between ${rangeStart} and ${rangeEnd}.`
  );
}

async function ensureEnvironment(options = {}) {
  console.log('🔧 Setting up development environment...');

  const { preferredPort: preferredOverride } = options ?? {};

  let envContents = readFileSafe(envFile);
  const envLocalContentsRaw = readFileSafe(envLocalFile);

  // Ensure required directories/files exist
  ensureDirectory(rootDataDir);
  ensureDirectory(projectsDir);

  const envDefaults = {};
  const postgresPassword = readEnvRawValue(envContents, 'POSTGRES_PASSWORD') || randomLocalPassword();
  if (shouldSetPostgresDatabaseUrl(envContents)) {
    envDefaults.DATABASE_URL = `"postgresql://travelpilot:${postgresPassword}@127.0.0.1:5432/travelpilot?schema=public"`;
  }
  if (!hasEnvKey(envContents, 'POSTGRES_DB')) {
    envDefaults.POSTGRES_DB = '"travelpilot"';
  }
  if (!hasEnvKey(envContents, 'POSTGRES_USER')) {
    envDefaults.POSTGRES_USER = '"travelpilot"';
  }
  if (!hasEnvKey(envContents, 'POSTGRES_PASSWORD')) {
    envDefaults.POSTGRES_PASSWORD = `"${postgresPassword}"`;
  }
  if (!hasEnvKey(envContents, 'POSTGRES_PORT')) {
    envDefaults.POSTGRES_PORT = '5432';
  }
  if (!hasEnvKey(envContents, 'PROJECTS_DIR')) {
    envDefaults.PROJECTS_DIR = '"./data/projects"';
  }
  if (!hasEnvKey(envContents, 'TRAVELPILOT_DATA_ROOT')) {
    envDefaults.TRAVELPILOT_DATA_ROOT = '"./travel-data/processed"';
  }
  if (!hasEnvKey(envContents, 'TRAVELPILOT_WIKI_ROOT')) {
    envDefaults.TRAVELPILOT_WIKI_ROOT = '"./travel-data/wiki"';
  }
  if (!hasEnvKey(envContents, 'AMAP_API_KEY')) {
    envDefaults.AMAP_API_KEY = '"replace-with-your-amap-key"';
  }
  if (!hasEnvKey(envContents, 'ENCRYPTION_KEY')) {
    envDefaults.ENCRYPTION_KEY = `"${crypto.randomBytes(32).toString('hex')}"`;
  }

  const portStartCandidates = [
    parsePortValue(process.env.PREVIEW_PORT_START),
    extractPort(envContents, ['PREVIEW_PORT_START']),
  ];

  let portRangeStart =
    portStartCandidates.find((value) => value !== null) ?? FALLBACK_PORT_START;

  const portEndCandidates = [
    parsePortValue(process.env.PREVIEW_PORT_END),
    extractPort(envContents, ['PREVIEW_PORT_END']),
  ];

  let portRangeEnd =
    portEndCandidates.find((value) => value !== null) ?? FALLBACK_PORT_END;

  if (portRangeEnd < portRangeStart) {
    portRangeEnd = Math.min(
      MAX_PORT,
      portRangeStart + DEFAULT_RANGE_SPAN
    );
  }

  const overridePreferred =
    preferredOverride !== undefined && preferredOverride !== null
      ? parsePortValue(String(preferredOverride))
      : null;

  const sanitizeWebCandidate = (val) => {
    if (val === null || val === undefined) return null;
    if (val >= portRangeStart && val <= portRangeEnd) return null;
    if (val < DEFAULT_WEB_PORT || val > DEFAULT_WEB_MAX) {
      return DEFAULT_WEB_PORT;
    }
    return val;
  };

  const explicitPreferredPort = sanitizeWebCandidate(overridePreferred);
  const preferredPort = explicitPreferredPort ?? DEFAULT_WEB_PORT;

  // Compute scan window for WEB app: stay below preview range when possible
  let webRangeStart = preferredPort;
  let webRangeEnd = Math.min(
    preferredPort + DEFAULT_WEB_SCAN_SPAN,
    portRangeStart > preferredPort ? portRangeStart - 1 : preferredPort + DEFAULT_WEB_SCAN_SPAN
  );
  if (webRangeEnd < webRangeStart) {
    webRangeEnd = webRangeStart;
  }

  const port = await findAvailablePort(webRangeStart, webRangeEnd, preferredPort);
  const url = `http://localhost:${port}`;

  if (port !== preferredPort) {
    console.log(
      `⚠️  Port ${preferredPort} is busy. Switching to available port ${port} within ${webRangeStart}-${webRangeEnd}.`
    );
  } else {
    console.log(
      `✅ Using port ${port} (range ${webRangeStart}-${webRangeEnd}).`
    );
  }

  const envUpdates = {
    PORT: String(port),
    WEB_PORT: String(port),
    NEXT_PUBLIC_APP_URL: `"${url}"`,
    PREVIEW_PORT_START: String(portRangeStart),
    PREVIEW_PORT_END: String(portRangeEnd),
  };

  let updatedEnv = envContents || '# Auto-generated defaults - customize as needed\n';
  for (const [key, value] of Object.entries(envDefaults)) {
    updatedEnv = upsertEnvValue(updatedEnv, key, value);
  }
  for (const [key, value] of Object.entries(envUpdates)) {
    updatedEnv = upsertEnvValue(updatedEnv, key, value);
  }
  writeFileSafe(envFile, updatedEnv);
  console.log(`📝 Updated ${path.relative(rootDir, envFile)}`);

  let envLocalContents = envLocalContentsRaw;
  if (!envLocalContents.trim()) {
    envLocalContents = '# Auto-generated by scripts/dev/setup-env.js\n';
  }

  const envLocalUpdates = {
    NEXT_PUBLIC_APP_URL: url,
    PORT: String(port),
    WEB_PORT: String(port),
    PREVIEW_PORT_START: String(portRangeStart),
    PREVIEW_PORT_END: String(portRangeEnd),
  };

  for (const [key, value] of Object.entries(envLocalUpdates)) {
    envLocalContents = upsertEnvValue(envLocalContents, key, value);
  }
  writeFileSafe(envLocalFile, envLocalContents);
  console.log(`📝 Updated ${path.relative(rootDir, envLocalFile)}`);

  console.log('✅ Environment ready!');
  return { port, url };
}

if (require.main === module) {
  ensureEnvironment().catch((error) => {
    console.error('❌ Failed to set up environment.');
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}

module.exports = { ensureEnvironment };
