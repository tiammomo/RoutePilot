#!/usr/bin/env node

const fs = require('fs');
const http = require('http');
const path = require('path');
const { spawnSync } = require('child_process');
const { PrismaClient } = require('@prisma/client');

const ROOT = process.cwd();
const FULL_CHECKS = process.argv.includes('--full');
const checks = [];

function addCheck(name, status, summary, details = []) {
  checks.push({ name, status, summary, details: details.filter(Boolean) });
}

function run(command, args = [], options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? ROOT,
    encoding: 'utf8',
    shell: false,
    env: { ...process.env, ...(options.env ?? {}) },
  });
  return {
    status: result.status ?? 1,
    stdout: (result.stdout ?? '').trim(),
    stderr: (result.stderr ?? '').trim(),
    error: result.error,
  };
}

function commandOutput(command, args = []) {
  const result = run(command, args);
  if (result.status !== 0 || result.error) return '';
  return result.stdout.split('\n').find(Boolean)?.trim() ?? '';
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function readEnvFile(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch {
    return '';
  }
}

function readEnvValue(key) {
  if (process.env[key]) return process.env[key];
  for (const file of ['.env.local', '.env']) {
    const content = readEnvFile(path.join(ROOT, file));
    const match = content.match(new RegExp(`^${key}=["']?([^"'\\n]+)["']?$`, 'm'));
    if (match) return match[1];
  }
  return '';
}

function requestHead(url, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const request = http.request(url, { method: 'HEAD', timeout: timeoutMs }, (response) => {
      response.resume();
      resolve({ ok: response.statusCode >= 200 && response.statusCode < 400, statusCode: response.statusCode });
    });
    request.on('timeout', () => {
      request.destroy();
      resolve({ ok: false, statusCode: null, error: 'timeout' });
    });
    request.on('error', (error) => resolve({ ok: false, statusCode: null, error: error.message }));
    request.end();
  });
}

function summarizeCommandFailure(result) {
  return (result.stderr || result.stdout || result.error?.message || 'command failed')
    .split('\n')
    .filter(Boolean)
    .slice(-6);
}

function checkCommand(name, command, args, options = {}) {
  const result = run(command, args, options);
  if (result.status === 0) {
    addCheck(name, 'ok', options.successSummary ?? '通过。');
    return true;
  }
  addCheck(name, options.warnOnly ? 'warn' : 'fail', options.failureSummary ?? '未通过。', summarizeCommandFailure(result));
  return false;
}

async function checkDatabase() {
  const databaseUrl = readEnvValue('DATABASE_URL');
  if (!databaseUrl) {
    addCheck('数据库', 'warn', 'DATABASE_URL 未配置。');
    return;
  }

  if (!databaseUrl.startsWith('postgresql://') && !databaseUrl.startsWith('postgres://')) {
    addCheck('数据库', 'fail', 'DATABASE_URL 不是 PostgreSQL 连接串。');
    return;
  }

  const prisma = new PrismaClient();
  try {
    await prisma.$queryRaw`SELECT 1`;
    addCheck('数据库', 'ok', 'PostgreSQL 可连接。');
  } catch (error) {
    addCheck('数据库', 'fail', 'PostgreSQL 连接失败。', [
      error instanceof Error ? error.message : String(error),
      '可运行 npm run db:up && npm run db:init 初始化旅游数据表。',
    ]);
  } finally {
    await prisma.$disconnect().catch(() => {});
  }
}

async function main() {
  console.log(`\nBeijing Travel Agent Doctor ${FULL_CHECKS ? '(full)' : '(quick)'}\n`);

  const packageJson = readJson(path.join(ROOT, 'package.json'));
  addCheck(
    '项目配置',
    packageJson?.name === 'beijing-travel-agent' ? 'ok' : 'warn',
    packageJson ? `${packageJson.name}@${packageJson.version}` : '无法读取 package.json。'
  );

  const nodeVersion = commandOutput('node', ['--version']);
  const npmVersion = commandOutput('npm', ['--version']);
  addCheck(
    '工具版本',
    nodeVersion && npmVersion ? 'ok' : 'fail',
    `node=${nodeVersion || '-'} npm=${npmVersion || '-'}`,
    [nodeVersion ? null : 'Node.js 不可用。', npmVersion ? null : 'npm 不可用。']
  );

  const modelEnv = ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_MODEL'];
  const missingModelEnv = modelEnv.filter((key) => !readEnvValue(key));
  addCheck(
    '模型环境',
    missingModelEnv.length ? 'warn' : 'ok',
    missingModelEnv.length ? `缺少 ${missingModelEnv.join(', ')}` : '模型环境变量已配置。',
    missingModelEnv.map((key) => `${key} 未设置。`)
  );

  const amapKey = readEnvValue('AMAP_API_KEY') || readEnvValue('AMAP_KEY');
  addCheck('高德 API', amapKey ? 'ok' : 'warn', amapKey ? 'AMap key 已配置。' : '未检测到 AMap key。');

  await checkDatabase();

  const frontend = await requestHead('http://localhost:3000/');
  addCheck(
    '前端服务 :3000',
    frontend.ok ? 'ok' : 'warn',
    frontend.ok ? `HTTP ${frontend.statusCode}` : '未连接；如需本地预览可运行 npm run dev。'
  );

  checkCommand('旅游数据库诊断', 'npm', ['run', 'travel:db:doctor'], {
    warnOnly: true,
    successSummary: '旅游数据表检查通过。',
  });

  if (FULL_CHECKS) {
    checkCommand('ESLint', 'npm', ['run', 'lint'], { successSummary: 'lint 通过。' });
    checkCommand('TypeScript', 'npm', ['run', 'type-check'], { successSummary: 'type-check 通过。' });
    checkCommand('通勤数据检查', 'npm', ['run', 'check:travel-commute'], { successSummary: '通勤数据检查通过。' });
  } else {
    addCheck('Full checks', 'warn', '已跳过 lint/type-check/通勤检查。', ['使用 npm run doctor:full 运行完整诊断。']);
  }

  const statusIcon = { ok: '✓', warn: '!', fail: '✗' };
  for (const check of checks) {
    console.log(`${statusIcon[check.status]} ${check.name}: ${check.summary}`);
    for (const detail of check.details) {
      console.log(`  - ${detail}`);
    }
  }

  const counts = checks.reduce(
    (acc, check) => {
      acc[check.status] += 1;
      return acc;
    },
    { ok: 0, warn: 0, fail: 0 }
  );
  console.log(`\nSummary: ${counts.ok} ok, ${counts.warn} warn, ${counts.fail} fail\n`);
  if (counts.fail > 0) process.exitCode = 1;
}

main().catch((error) => {
  console.error('[doctor] failed:', error);
  process.exit(1);
});
