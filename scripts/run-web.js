#!/usr/bin/env node

/**
 * Next.js development server launcher with automatic port management.
 * Expects scripts/setup-env.js to have been executed beforehand.
 */

const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs/promises');
const dotenv = require('dotenv');
const { ensureEnvironment } = require('./setup-env');
const { PrismaClient } = require('@prisma/client');
const { buildStableCss } = require('./build-stable-css');

const rootDir = path.join(__dirname, '..');
const isWindows = os.platform() === 'win32';
const nextDevLockFile = path.join(rootDir, '.next', 'dev', 'lock');

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

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

function runPrismaDbPush() {
  return new Promise((resolve, reject) => {
    console.log('🗃️  Synchronizing Prisma schema (prisma db push)...');
    const child = spawn('npx', ['prisma', 'db', 'push'], {
      cwd: rootDir,
      stdio: 'inherit',
      shell: isWindows,
      detached: !isWindows,
      env: {
        ...process.env,
        PRISMA_HIDE_UPDATE_MESSAGE: '1',
      },
    });

    child.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(
          new Error(`prisma db push exited with code ${code ?? 'unknown'}`)
        );
      }
    });

    child.on('error', (error) => {
      reject(error);
    });
  });
}

async function ensureDatabaseSynced() {
  if (process.env.SKIP_DB_SYNC === '1') {
    return;
  }

  let prisma;
  try {
    prisma = new PrismaClient();
  } catch (error) {
    console.warn(
      '⚠️  Failed to initialize Prisma Client, attempting to sync automatically:',
      error instanceof Error ? error.message : error
    );
    await runPrismaDbPush();
    return;
  }

  try {
    const tables = await prisma.$queryRaw`SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'projects'`;
    if (!Array.isArray(tables) || tables.length === 0) {
      await runPrismaDbPush();
    }
  } catch (error) {
    console.warn(
      '⚠️  Prisma schema check failed, attempting to sync automatically:',
      error instanceof Error ? error.message : error
    );
    await runPrismaDbPush();
  } finally {
    if (prisma) {
      await prisma.$disconnect().catch(() => {});
    }
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function probeUrl(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
    });
    return response.ok || response.status < 500;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function stopChild(child) {
  if (!child?.pid) {
    return;
  }

  try {
    if (!isWindows) {
      process.kill(-child.pid, 'SIGTERM');
    } else {
      child.kill('SIGTERM');
    }
  } catch {
    try {
      child.kill('SIGTERM');
    } catch {
      // 进程可能已经退出。
    }
  }
}

async function clearStaleNextDevLock() {
  try {
    const raw = await fs.readFile(nextDevLockFile, 'utf8');
    const parsed = JSON.parse(raw);
    const pid = Number.parseInt(String(parsed?.pid ?? ''), 10);
    if (Number.isInteger(pid) && pid > 0) {
      try {
        process.kill(pid, 0);
        return;
      } catch {
        // PID 不存在，锁文件是过期的。
      }
    }
  } catch {
    // 没有锁文件或内容不可解析都可以直接清理。
  }

  await fs.rm(nextDevLockFile, { force: true });
}

async function clearRspackCaches() {
  await Promise.all([
    fs.rm(path.join(rootDir, '.next', 'dev', 'cache', 'rspack'), { recursive: true, force: true }),
    fs.rm(path.join(rootDir, '.next', 'cache'), { recursive: true, force: true }),
    clearStaleNextDevLock(),
  ]);
}

async function startWebDevServer({
  preferredPort,
  passthrough = [],
  stdio = 'inherit',
  onOutput,
  bundler = 'rspack',
} = {}) {
  const { port, url } = await ensureEnvironment({
    preferredPort,
  });

  await buildStableCss();
  await ensureDatabaseSynced();

  const resolvedPort = port;
  const resolvedUrl = url;

  process.env.PORT = resolvedPort.toString();
  process.env.WEB_PORT = resolvedPort.toString();
  process.env.NEXT_PUBLIC_APP_URL = resolvedUrl;

  console.log(`🚀 Starting Next.js dev server on ${resolvedUrl}`);

  const useRspack = bundler === 'rspack';
  const bundlerEnv = {
    ...process.env,
    QUANTPILOT_DISABLE_RSPACK: useRspack ? '0' : '1',
  };
  if (useRspack) {
    bundlerEnv.TURBOPACK = process.env.TURBOPACK || 'auto';
    delete bundlerEnv.NEXT_RSPACK;
  } else {
    bundlerEnv.TURBOPACK = '1';
    delete bundlerEnv.NEXT_RSPACK;
  }

  const devArgs = ['next', 'dev', '--port', resolvedPort.toString(), ...passthrough];
  if (!useRspack && !devArgs.includes('--turbo') && !devArgs.includes('--turbopack')) {
    devArgs.push('--turbo');
  }

  const child = spawn(
    'npx',
    devArgs,
    {
      cwd: rootDir,
      stdio: onOutput ? ['inherit', 'pipe', 'pipe'] : stdio,
      shell: isWindows,
      env: {
        ...bundlerEnv,
        PORT: resolvedPort.toString(),
        WEB_PORT: resolvedPort.toString(),
        NEXT_PUBLIC_APP_URL: resolvedUrl,
        BROWSER: process.env.BROWSER || 'none',
        NEXT_TELEMETRY_DISABLED: '1',
      },
    }
  );

  if (onOutput) {
    child.stdout?.on('data', (chunk) => onOutput(chunk));
    child.stderr?.on('data', (chunk) => onOutput(chunk));
  }

  await new Promise((resolve, reject) => {
    const handleError = (error) => {
      reject(error instanceof Error ? error : new Error(String(error)));
    };
    child.once('error', handleError);
    child.once('spawn', () => {
      child.removeListener('error', handleError);
      resolve();
    });
  });

  return { child, port: resolvedPort, url: resolvedUrl };
}

async function runFromCli() {
  const argv = process.argv.slice(2);
  const { preferredPort, passthrough } = parseCliArgs(argv);
  let restartedAfterRspackPanic = false;
  let recentOutput = '';
  let activeChild = null;
  let activeBundler = process.env.QUANTPILOT_BUNDLER === 'turbo' ? 'turbo' : 'rspack';

  const hasRspackPanicOutput = () =>
    /rspack/i.test(recentOutput) &&
    (/Panic occurred at runtime/i.test(recentOutput) || /should mgm exist/i.test(recentOutput));

  const launch = async () => {
    const { child, port, url } = await startWebDevServer({
      preferredPort,
      passthrough,
      stdio: 'inherit',
      bundler: activeBundler,
      onOutput(chunk) {
        const text = chunk.toString();
        recentOutput = `${recentOutput}${text}`.slice(-16_000);
        process.stdout.write(text);
      },
    });
    activeChild = child;

    setTimeout(async () => {
      if (restartedAfterRspackPanic || !hasRspackPanicOutput()) {
        return;
      }

      const healthy = await probeUrl(url);
      if (healthy) {
        return;
      }

      restartedAfterRspackPanic = true;
      activeBundler = 'turbo';
      console.warn('\n⚠️  检测到 Rspack 缓存死锁，正在切换到 Next Turbopack 稳定模式...');
      stopChild(activeChild);
      await delay(1200);
      await clearRspackCaches();
      recentOutput = '';
      process.env.PORT = String(port);
      process.env.WEB_PORT = String(port);
      await launch();
    }, 5_000);

    child.on('error', (error) => {
      console.error('\n❌ Failed to start Next.js dev server');
      console.error(error instanceof Error ? error.message : error);
      process.exit(1);
    });

    child.on('exit', async (code) => {
      const rspackCachePanic =
        /rspack/i.test(recentOutput) &&
        (/Panic occurred at runtime/i.test(recentOutput) || /should mgm exist/i.test(recentOutput));

      if (!restartedAfterRspackPanic && rspackCachePanic) {
        restartedAfterRspackPanic = true;
        activeBundler = 'turbo';
        console.warn('\n⚠️  检测到 Rspack 开发缓存异常，正在切换到 Next Turbopack 稳定模式...');
        await clearRspackCaches();
        recentOutput = '';
        process.env.PORT = String(port);
        process.env.WEB_PORT = String(port);
        await launch();
        return;
      }

      if (typeof code !== 'number' || code === 0) {
        return;
      }

      console.error(`\n❌ Next.js dev server exited with code ${code}`);
      process.exit(code);
    });
  };

  await launch();
}

if (require.main === module) {
  runFromCli().catch((error) => {
    console.error('\n❌ Failed to launch dev server');
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}

module.exports = {
  parseCliArgs,
  startWebDevServer,
};
