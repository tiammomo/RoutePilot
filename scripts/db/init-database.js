#!/usr/bin/env node

const fs = require('fs/promises');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const dotenv = require('dotenv');

const rootDir = path.join(__dirname, '..', '..');
const sqlDir = path.join(rootDir, 'sqls');
const isWindows = os.platform() === 'win32';

dotenv.config({ path: path.join(rootDir, '.env') });
dotenv.config({ path: path.join(rootDir, '.env.local') });

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd ?? rootDir,
      stdio: options.stdio ?? 'inherit',
      shell: isWindows,
      env: {
        ...process.env,
        ...(options.env ?? {}),
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

async function listSqlFiles() {
  const entries = await fs.readdir(sqlDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && /^0(0[89]|10)-travel-.+\.sql$/.test(entry.name))
    .map((entry) => path.join(sqlDir, entry.name))
    .sort((a, b) => path.basename(a).localeCompare(path.basename(b)));
}

async function applySqlFile(filePath) {
  await fs.access(filePath);
  console.log(`[db:init] applying ${path.relative(rootDir, filePath)}`);
  await run('npx', ['prisma', 'db', 'execute', '--file', filePath, '--schema', path.join(rootDir, 'prisma', 'schema.prisma')], {
    stdio: 'inherit',
    env: {
      PRISMA_HIDE_UPDATE_MESSAGE: '1',
    },
  });
}

async function applyBootstrapSql() {
  const databaseUrl = process.env.DATABASE_URL;
  if (!databaseUrl) {
    throw new Error('DATABASE_URL is not configured. Run npm run ensure:env first.');
  }
  if (!databaseUrl.startsWith('postgresql://') && !databaseUrl.startsWith('postgres://')) {
    throw new Error('DATABASE_URL must use PostgreSQL.');
  }

  const sqlFiles = await listSqlFiles();
  if (!sqlFiles.length) {
    throw new Error(`No bootstrap SQL files found in ${path.relative(rootDir, sqlDir)}.`);
  }

  for (const filePath of sqlFiles) {
    await applySqlFile(filePath);
  }
}

async function main() {
  await applyBootstrapSql();
  console.log('[db:init] syncing Prisma schema');
  await run('npx', ['prisma', 'db', 'push'], {
    env: {
      PRISMA_HIDE_UPDATE_MESSAGE: '1',
    },
  });
  console.log('[db:init] done');
}

main().catch((error) => {
  console.error('[db:init] failed:', error instanceof Error ? error.message : error);
  process.exit(1);
});
