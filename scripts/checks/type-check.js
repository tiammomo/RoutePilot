#!/usr/bin/env node

const { spawn } = require('child_process');
const os = require('os');
const path = require('path');
const { withNextArtifactLock } = require('../shared/next-artifact-lock');

const rootDir = path.join(__dirname, '..', '..');
const isWindows = os.platform() === 'win32';

function run(command, args, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: rootDir,
      stdio: 'inherit',
      shell: isWindows,
      env: {
        ...process.env,
        ...env,
      },
    });

    child.on('error', reject);
    child.on('exit', (code, signal) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} ${args.join(' ')} exited with code ${code ?? 'null'}, signal ${signal ?? 'null'}`));
    });
  });
}

async function main() {
  await withNextArtifactLock(rootDir, 'type-check', async () => {
    await run('npx', ['next', 'typegen'], { TURBOPACK: 'auto' });
    await run('npx', ['tsc', '--noEmit']);
  });
}

main().catch((error) => {
  console.error('[type-check] Failed:', error instanceof Error ? error.message : error);
  process.exit(1);
});
