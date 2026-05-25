#!/usr/bin/env node

/**
 * 安全的 Next.js 生产构建入口。
 *
 * dev server 和 next build 都会写入 .next。两者同时运行时容易互相影响，
 * 所以构建前先停止根项目的 3000 开发服务。
 */

const { execFile, spawn } = require('child_process');
const path = require('path');
const os = require('os');
const { promisify } = require('util');
const { buildStableCss } = require('./build-stable-css');

const execFileAsync = promisify(execFile);
const rootDir = path.join(__dirname, '..');
const isWindows = os.platform() === 'win32';
const rootPort = Number.parseInt(process.env.WEB_PORT || process.env.PORT || '3000', 10) || 3000;

function extractPidsFromSs(output) {
  const pids = new Set();
  for (const match of output.matchAll(/pid=(\d+)/g)) {
    const pid = Number.parseInt(match[1], 10);
    if (Number.isInteger(pid) && pid > 0) {
      pids.add(pid);
    }
  }
  return Array.from(pids);
}

async function findListeningPids(port) {
  if (isWindows) {
    return [];
  }
  try {
    const { stdout } = await execFileAsync('ss', ['-ltnpH', `sport = :${port}`]);
    return extractPidsFromSs(stdout);
  } catch {
    return [];
  }
}

async function isPidWithinRoot(pid) {
  if (isWindows) {
    return false;
  }
  try {
    const cwd = await require('fs/promises').readlink(`/proc/${pid}/cwd`);
    const normalizedCwd = path.resolve(cwd);
    return normalizedCwd === rootDir || normalizedCwd.startsWith(`${rootDir}${path.sep}`);
  } catch {
    return false;
  }
}

async function stopRootDevServer() {
  const pids = await findListeningPids(rootPort);
  if (pids.length === 0) {
    return;
  }

  const rootPids = (
    await Promise.all(pids.map(async (pid) => ((await isPidWithinRoot(pid)) ? pid : null)))
  ).filter((pid) => pid !== null);

  if (rootPids.length === 0) {
    return;
  }

  console.log(`[build] Stopping root dev server on port ${rootPort}: ${rootPids.join(', ')}`);
  for (const pid of rootPids) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {
      // 进程可能已经退出。
    }
  }

  await new Promise((resolve) => setTimeout(resolve, 2_000));

  for (const pid of rootPids) {
    try {
      process.kill(pid, 0);
      process.kill(pid, 'SIGKILL');
    } catch {
      // 已经退出。
    }
  }
}

function parseBuildArgs(argv) {
  const args = [];
  let standalone = process.env.QUANTPILOT_STANDALONE_BUILD === '1';

  for (const arg of argv) {
    if (arg === '--standalone') {
      standalone = true;
      continue;
    }
    args.push(arg);
  }

  return { args, standalone };
}

async function runNextBuild(args, { standalone } = {}) {
  await new Promise((resolve, reject) => {
    const child = spawn(
      path.join(rootDir, 'node_modules', '.bin', isWindows ? 'next.cmd' : 'next'),
      ['build', ...args],
      {
        cwd: rootDir,
        stdio: 'inherit',
        shell: isWindows,
        env: {
          ...process.env,
          TURBOPACK: process.env.TURBOPACK || 'auto',
          QUANTPILOT_STANDALONE_BUILD: standalone ? '1' : '0',
          QUANTPILOT_SKIP_ROUTE_TRACING:
            process.env.QUANTPILOT_SKIP_ROUTE_TRACING || (standalone ? '0' : '1'),
          NEXT_TELEMETRY_DISABLED: '1',
          NEXT_PUBLIC_PROJECT_ROOT: process.env.NEXT_PUBLIC_PROJECT_ROOT || rootDir,
        },
      }
    );

    child.on('error', reject);
    child.on('exit', (code, signal) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`next build exited with code ${code ?? 'null'}, signal ${signal ?? 'null'}`));
    });
  });
}

async function main() {
  const { args, standalone } = parseBuildArgs(process.argv.slice(2));
  await stopRootDevServer();
  await buildStableCss();
  await runNextBuild(args, { standalone });
}

main().catch((error) => {
  console.error('[build] Failed:', error instanceof Error ? error.message : error);
  process.exit(1);
});
