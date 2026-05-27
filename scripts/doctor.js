#!/usr/bin/env node

const fs = require('fs');
const http = require('http');
const path = require('path');
const { spawnSync } = require('child_process');

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

function commandOutput(command, args = [], options = {}) {
  const result = run(command, args, options);
  if (result.status !== 0 || result.error) return null;
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

function hasCodexApiKey() {
  if (readEnvValue('CODEX_OPENAI_API_KEY') || readEnvValue('OPENAI_API_KEY')) return true;
  const auth = readJson(path.join(process.env.HOME || '', '.codex', 'auth.json'));
  return typeof auth?.OPENAI_API_KEY === 'string' && auth.OPENAI_API_KEY.length > 0;
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

function requestJson(url, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => {
        body += chunk;
      });
      response.on('end', () => {
        try {
          resolve({
            ok: response.statusCode >= 200 && response.statusCode < 400,
            statusCode: response.statusCode,
            data: JSON.parse(body),
          });
        } catch (error) {
          resolve({ ok: false, statusCode: response.statusCode, error: error.message });
        }
      });
    });
    request.on('timeout', () => {
      request.destroy();
      resolve({ ok: false, statusCode: null, error: 'timeout' });
    });
    request.on('error', (error) => resolve({ ok: false, statusCode: null, error: error.message }));
  });
}

function summarizeCommandFailure(result) {
  return (result.stderr || result.stdout || result.error?.message || 'command failed')
    .split('\n')
    .filter(Boolean)
    .slice(-6);
}

function latestBenchmarkReport() {
  const reportsDir = path.join(ROOT, 'tmp', 'quantpilot-benchmark-reports');
  if (!fs.existsSync(reportsDir)) return null;
  const files = fs
    .readdirSync(reportsDir)
    .filter((fileName) => /^report-\d+\.json$/.test(fileName))
    .map((fileName) => {
      const filePath = path.join(reportsDir, fileName);
      return { filePath, mtimeMs: fs.statSync(filePath).mtimeMs };
    })
    .sort((a, b) => b.mtimeMs - a.mtimeMs);
  if (!files[0]) return null;
  const report = readJson(files[0].filePath);
  return report ? { filePath: files[0].filePath, report } : null;
}

function checkCommand(name, command, args, options = {}) {
  const result = run(command, args, options);
  if (result.status === 0) {
    addCheck(name, 'ok', options.successSummary ?? '通过。', options.successDetails ? options.successDetails(result) : []);
    return true;
  }
  addCheck(name, options.warnOnly ? 'warn' : 'fail', options.failureSummary ?? '未通过。', summarizeCommandFailure(result));
  return false;
}

async function main() {
  console.log(`\nQuantPilot Doctor ${FULL_CHECKS ? '(full)' : '(quick)'}\n`);

  const packageJson = readJson(path.join(ROOT, 'package.json'));
  addCheck('项目配置', packageJson?.name === 'quantpilot' ? 'ok' : 'fail', packageJson ? `${packageJson.name}@${packageJson.version}` : '无法读取 package.json。');

  const nodeVersion = commandOutput('node', ['--version']);
  const npmVersion = commandOutput('npm', ['--version']);
  const uvVersion = commandOutput('uv', ['--version'], { cwd: path.join(ROOT, 'backend', 'market_data') });
  addCheck(
    '工具版本',
    nodeVersion && npmVersion && uvVersion ? 'ok' : 'fail',
    `node=${nodeVersion || '-'} npm=${npmVersion || '-'} uv=${uvVersion || '-'}`,
    [
      nodeVersion ? null : 'Node.js 不可用。',
      npmVersion ? null : 'npm 不可用。',
      uvVersion ? null : 'uv 不可用。',
    ]
  );

  const envRequired = ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_MODEL'];
  const missingEnv = envRequired.filter((key) => !readEnvValue(key));
  addCheck(
    'Claude / MiniMax 环境',
    missingEnv.length ? 'warn' : 'ok',
    missingEnv.length ? `缺少 ${missingEnv.join(', ')}` : '必需环境变量已配置。',
    missingEnv.map((key) => `${key} 未设置。`)
  );

  const claudeVersion = commandOutput('claude', ['--version']);
  const codexExecutable = readEnvValue('CODEX_EXECUTABLE') || 'codex';
  const codexVersion = commandOutput(codexExecutable, ['--version']);
  addCheck(
    'Agent CLI',
    claudeVersion ? 'ok' : 'fail',
    `claude=${claudeVersion || '-'} codex=${codexVersion || 'optional-missing'}`,
    [
      claudeVersion ? null : 'Claude Code CLI 不可用。',
      codexVersion ? null : 'Codex CLI 不可用；如不使用 Codex 可忽略。',
      hasCodexApiKey() ? null : 'Codex API Key 未配置；如不使用 Codex 可忽略。',
    ]
  );

  const frontend = await requestHead('http://localhost:3000/');
  addCheck(
    '前端服务 :3000',
    frontend.ok ? 'ok' : 'warn',
    frontend.ok ? `HTTP ${frontend.statusCode}` : '未连接。',
    frontend.ok ? [] : ['运行 npm run dev 可启动主前端。']
  );

  const backend = await requestJson('http://127.0.0.1:8000/health');
  addCheck(
    '量化数据后端 :8000',
    backend.ok ? 'ok' : 'warn',
    backend.ok ? `HTTP ${backend.statusCode}` : '未连接。',
    backend.ok ? [] : ['进入 backend/market_data 后运行 uv run quantpilot-market-api。']
  );

  const projectsDir = readEnvValue('PROJECTS_DIR') || './data/projects';
  const projectRoot = path.resolve(ROOT, projectsDir);
  const projectCount = fs.existsSync(projectRoot)
    ? fs.readdirSync(projectRoot).filter((item) => item.startsWith('project-')).length
    : 0;
  addCheck('工作空间目录', fs.existsSync(projectRoot) ? 'ok' : 'warn', `${path.relative(ROOT, projectRoot)} (${projectCount} 个项目)`);

  checkCommand('Skills 注册表', 'node', ['scripts/check-skills-registry.js', '--check-lock'], {
    successSummary: 'registry / changelog / lock / package 一致。',
  });
  checkCommand('生成产物策略', 'node', ['scripts/check-generated-artifact-policy.js'], {
    successSummary: 'artifact policy smoke 通过。',
  });
  checkCommand('验证修复契约', 'node', ['scripts/check-validation-repair.js'], {
    successSummary: 'validation repair smoke 通过。',
  });
  checkCommand('验证过期检查', 'node', ['scripts/check-validation-stale-report.js'], {
    successSummary: 'stale validation smoke 通过。',
  });
  checkCommand('Benchmark 覆盖', 'node', ['scripts/check-quant-benchmark-coverage.js'], {
    successSummary: '固定评测覆盖达标。',
  });
  checkCommand('Eval 定时器', 'node', ['scripts/check-eval-schedule.js'], {
    successSummary: '定时评测检查通过。',
  });

  const report = latestBenchmarkReport();
  if (report) {
    const total = Number(report.report.total || 0);
    const passed = Number(report.report.passedCount || 0);
    const failed = Number(report.report.failedCount || 0);
    const passRate = Number(report.report.passRate ?? (total ? Math.round((passed / total) * 100) : 0));
    addCheck(
      '最近评测报告',
      failed ? 'warn' : 'ok',
      `${path.relative(ROOT, report.filePath)} · ${passed}/${total} · ${passRate}%`,
      failed ? [`失败用例：${failed}`] : []
    );
  } else {
    addCheck('最近评测报告', 'warn', '未找到 tmp/quantpilot-benchmark-reports/report-*.json。', ['运行 npm run benchmark:quant 可生成报告。']);
  }

  if (FULL_CHECKS) {
    checkCommand('ESLint', 'npm', ['run', 'lint'], { successSummary: 'lint 通过。' });
    checkCommand('TypeScript', 'npm', ['run', 'type-check'], { successSummary: 'type-check 通过。' });
    checkCommand('后端 Ruff', 'uv', ['run', 'ruff', 'check', '.'], {
      cwd: path.join(ROOT, 'backend', 'market_data'),
      successSummary: 'ruff 通过。',
    });
    checkCommand('后端 Pytest', 'uv', ['run', 'pytest'], {
      cwd: path.join(ROOT, 'backend', 'market_data'),
      successSummary: 'pytest 通过。',
    });
  } else {
    addCheck('Full checks', 'warn', '已跳过 lint/type-check/后端测试。', ['使用 npm run doctor:full 运行完整诊断。']);
  }

  const statusIcon = { ok: '✓', warn: '!', fail: '✕' };
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
  if (counts.fail > 0) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error('[doctor] failed:', error);
  process.exit(1);
});
