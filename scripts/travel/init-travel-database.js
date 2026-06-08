#!/usr/bin/env node

const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const dotenv = require('dotenv');

const rootDir = path.join(__dirname, '..', '..');
const isWindows = os.platform() === 'win32';

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: rootDir,
      stdio: 'inherit',
      shell: isWindows,
      env: {
        ...process.env,
        PRISMA_HIDE_UPDATE_MESSAGE: '1',
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
  const travelSqlFiles = [
    path.join(rootDir, 'sqls', '008-travel-commute-data.sql'),
    path.join(rootDir, 'sqls', '009-travel-knowledge-base.sql'),
    path.join(rootDir, 'sqls', '010-travel-route-corpus.sql'),
  ];
  const schema = path.join(rootDir, 'prisma', 'schema.prisma');

  for (const travelSql of travelSqlFiles) {
    console.log(`[travel:db:init] applying ${path.relative(rootDir, travelSql)}`);
    await run('npx', ['prisma', 'db', 'execute', '--file', travelSql, '--schema', schema]);
  }

  console.log('[travel:db:init] done');
}

main().catch((error) => {
  console.error('[travel:db:init] failed:', error instanceof Error ? error.message : error);
  process.exit(1);
});
