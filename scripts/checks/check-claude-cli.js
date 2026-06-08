#!/usr/bin/env node
/**
 * Claude Code CLI 与 MiniMax 环境检查脚本
 *
 * 运行：npm run check-cli
 */

const { execSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function readEnvFile(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf8');
  } catch {
    return '';
  }
}

function readEnvValue(key) {
  if (process.env[key]) {
    return process.env[key];
  }

  for (const file of ['.env.local', '.env']) {
    const contents = readEnvFile(path.join(process.cwd(), file));
    const match = contents.match(new RegExp(`^${key}=["']?([^"'\\n]+)["']?$`, 'm'));
    if (match) {
      return match[1];
    }
  }
  return '';
}

function resolveCodexExecutable() {
  const explicit = readEnvValue('CODEX_EXECUTABLE');
  if (explicit) {
    return explicit;
  }
  const nodeBin = path.dirname(process.execPath);
  const candidate = path.join(nodeBin, process.platform === 'win32' ? 'codex.cmd' : 'codex');
  return fs.existsSync(candidate) ? candidate : 'codex';
}

function hasCodexApiKey() {
  if (readEnvValue('CODEX_OPENAI_API_KEY') || readEnvValue('OPENAI_API_KEY')) {
    return true;
  }
  try {
    const auth = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.codex', 'auth.json'), 'utf8'));
    return typeof auth.OPENAI_API_KEY === 'string' && auth.OPENAI_API_KEY.length > 0;
  } catch {
    return false;
  }
}

console.log('\n🔍 Claude Code CLI 与 MiniMax 配置检查\n');

console.log('1️⃣  检查 Claude Code CLI 是否已安装...');
try {
  const version = execSync('claude --version', { encoding: 'utf-8', stdio: 'pipe' }).trim();
  console.log(`   ✅ 已安装：${version}\n`);
} catch (error) {
  console.log('   ❌ 未安装 Claude Code CLI。\n');
  console.log('   安装命令：');
  console.log('   $ npm install -g @anthropic-ai/claude-code\n');
  process.exit(1);
}

console.log('2️⃣  检查 CLI 是否可运行...');
try {
  execSync('claude --help', { encoding: 'utf-8', stdio: 'pipe' });
  console.log('   ✅ CLI 可正常运行。\n');
} catch (error) {
  console.log('   ⚠️  CLI 运行时出现异常。\n');
}

console.log('3️⃣  检查 MiniMax 相关环境变量');
const requiredEnv = ['ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_MODEL'];
for (const key of requiredEnv) {
  const value = readEnvValue(key);
  if (!value) {
    console.log(`   ⚠️  ${key} 未在当前 shell 环境中设置。`);
  } else if (key === 'ANTHROPIC_AUTH_TOKEN') {
    console.log(`   ✅ ${key}=已设置`);
  } else {
    console.log(`   ✅ ${key}=${value}`);
  }
}

console.log('\n4️⃣  检查 Codex CLI 与第三方 OpenAI-compatible GPT 配置');
try {
  const codexExecutable = resolveCodexExecutable();
  const version = execSync(`"${codexExecutable}" --version`, { encoding: 'utf-8', stdio: 'pipe' }).trim();
  console.log(`   ✅ Codex 已安装：${version}`);
  console.log(`   ✅ Codex 可执行文件：${codexExecutable}`);
} catch (error) {
  console.log('   ⚠️  Codex CLI 不可运行。');
  console.log('   安装命令：npm install -g @openai/codex@latest');
}

const codexModel = readEnvValue('CODEX_MODEL') || 'gpt-5.5';
const codexBaseUrl = readEnvValue('CODEX_OPENAI_BASE_URL') || readEnvValue('OPENAI_BASE_URL') || 'https://w.ciykj.cn';
const codexReasoningEffort = readEnvValue('CODEX_MODEL_REASONING_EFFORT') || 'low';
console.log(`   ✅ Codex 模型：${codexModel}`);
console.log(`   ✅ Codex Base URL：${codexBaseUrl}`);
console.log(`   ✅ Codex reasoning effort：${codexReasoningEffort}`);
console.log(hasCodexApiKey() ? '   ✅ Codex API Key=已设置' : '   ⚠️  Codex API Key 未设置');

console.log('\n✨ 北京旅游 Agent 已准备好使用 Claude Code 运行时。\n');
console.log('   下一步：');
console.log('   1. 确认 .env/.env.local 或 ~/.claude/settings.json 中已配置 MiniMax Token');
console.log('   2. 如需使用 Codex，确认 .env.local 或 ~/.codex/auth.json 中已配置 OpenAI-compatible API Key');
console.log('   3. npm run dev - 启动开发服务');
console.log('   4. 访问 http://localhost:3000\n');

console.log('────────────────────────────────────────────────────────────');
console.log('💡 提示：当前默认使用 Claude Code + MiniMax；Codex CLI 可通过 OpenAI-compatible Base URL 接入第三方 GPT。');
console.log('────────────────────────────────────────────────────────────\n');
