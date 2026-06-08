const fs = require('fs/promises');
const os = require('os');
const path = require('path');

const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_STALE_MS = 30 * 60 * 1000;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function isProcessAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function readLockInfo(lockFile) {
  try {
    const raw = await fs.readFile(lockFile, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function removeStaleLock(lockFile, staleMs) {
  const [stat, info] = await Promise.all([
    fs.stat(lockFile).catch(() => null),
    readLockInfo(lockFile),
  ]);
  if (!stat) {
    return false;
  }

  const pid = Number.parseInt(String(info?.pid ?? ''), 10);
  const hasLiveOwner = isProcessAlive(pid);
  const isStale = Date.now() - stat.mtimeMs > staleMs;
  if (hasLiveOwner && !isStale) {
    return false;
  }

  await fs.rm(lockFile, { force: true });
  return true;
}

async function acquireNextArtifactLock(rootDir, options = {}) {
  const timeoutMs = parsePositiveInteger(
    options.timeoutMs ?? process.env.NEXT_ARTIFACT_LOCK_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS
  );
  const staleMs = parsePositiveInteger(
    options.staleMs ?? process.env.NEXT_ARTIFACT_LOCK_STALE_MS,
    DEFAULT_STALE_MS
  );
  const label = options.label || 'next artifacts';
  const lockDir = path.join(rootDir, '.next');
  const lockFile = path.join(lockDir, 'travel-agent-next-artifact.lock');
  const startedAt = Date.now();
  let announcedWait = false;

  await fs.mkdir(lockDir, { recursive: true });

  while (true) {
    try {
      const handle = await fs.open(lockFile, 'wx');
      await handle.writeFile(`${JSON.stringify({
        pid: process.pid,
        label,
        hostname: os.hostname(),
        createdAt: new Date().toISOString(),
      })}\n`);
      await handle.close();
      let released = false;
      return async () => {
        if (released) {
          return;
        }
        released = true;
        await fs.rm(lockFile, { force: true }).catch(() => {});
      };
    } catch (error) {
      if (!error || error.code !== 'EEXIST') {
        throw error;
      }

      await removeStaleLock(lockFile, staleMs).catch(() => false);
      if (Date.now() - startedAt > timeoutMs) {
        throw new Error(`Timed out waiting for Next artifact lock: ${path.relative(rootDir, lockFile)}`);
      }
      if (!announcedWait) {
        console.log(`[next-artifacts] Waiting for another Next task before ${label}...`);
        announcedWait = true;
      }
      await delay(500);
    }
  }
}

async function withNextArtifactLock(rootDir, label, fn) {
  const release = await acquireNextArtifactLock(rootDir, { label });
  try {
    return await fn();
  } finally {
    await release();
  }
}

module.exports = {
  acquireNextArtifactLock,
  withNextArtifactLock,
};
