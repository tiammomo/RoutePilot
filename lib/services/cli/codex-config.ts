import fs from 'fs';
import path from 'path';

export const DEFAULT_CODEX_OPENAI_BASE_URL = 'https://w.ciykj.cn';
export const DEFAULT_CODEX_REASONING_EFFORT = 'low';

export interface CodexRuntimeConfig {
  executable: string;
  openAIBaseUrl?: string;
  apiKey?: string;
  reasoningEffort?: string;
  maxTurns: number;
  maxThinkingTokens: number;
  disablePlugins: boolean;
}

function readPositiveInteger(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function firstExistingPath(paths: string[]): string | null {
  for (const candidate of paths) {
    if (!candidate) {
      continue;
    }
    try {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    } catch {
      // ignore inaccessible path candidates
    }
  }
  return null;
}

function readCodexAuthApiKey(): string | undefined {
  const codexHome = process.env.CODEX_HOME?.trim() || path.join(process.env.HOME ?? '', '.codex');
  const authPath = path.join(codexHome, 'auth.json');
  try {
    const parsed = JSON.parse(fs.readFileSync(authPath, 'utf8')) as Record<string, unknown>;
    const key = parsed.OPENAI_API_KEY;
    return typeof key === 'string' && key.trim().length > 0 ? key.trim() : undefined;
  } catch {
    return undefined;
  }
}

export function getCodexExecutable(): string {
  const explicit = process.env.CODEX_EXECUTABLE?.trim();
  if (explicit) {
    return explicit;
  }

  const executableName = process.platform === 'win32' ? 'codex.cmd' : 'codex';
  const nodeBinDir = path.dirname(process.execPath);
  const candidates = [
    path.join(nodeBinDir, executableName),
    path.join(process.env.HOME ?? '', '.local', 'bin', executableName),
    path.join(process.env.HOME ?? '', '.npm-global', 'bin', executableName),
  ];

  return firstExistingPath(candidates) ?? executableName;
}

export function getCodexRuntimeConfig(): CodexRuntimeConfig {
  const openAIBaseUrl =
    process.env.CODEX_OPENAI_BASE_URL?.trim() ||
    process.env.OPENAI_BASE_URL?.trim() ||
    DEFAULT_CODEX_OPENAI_BASE_URL;

  const apiKey =
    process.env.CODEX_OPENAI_API_KEY?.trim() ||
    process.env.OPENAI_API_KEY?.trim() ||
    readCodexAuthApiKey() ||
    undefined;

  const reasoningEffort =
    process.env.CODEX_MODEL_REASONING_EFFORT?.trim() ||
    process.env.MODEL_REASONING_EFFORT?.trim() ||
    DEFAULT_CODEX_REASONING_EFFORT;

  return {
    executable: getCodexExecutable(),
    openAIBaseUrl,
    apiKey,
    reasoningEffort,
    maxTurns: readPositiveInteger(process.env.CODEX_MAX_TURNS, 20),
    maxThinkingTokens: readPositiveInteger(process.env.CODEX_MAX_THINKING_TOKENS, 4096),
    disablePlugins: process.env.CODEX_ENABLE_PLUGINS !== '1',
  };
}

export function buildCodexEnvironment(baseEnv: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const config = getCodexRuntimeConfig();
  const env: NodeJS.ProcessEnv = { ...baseEnv };
  const additionalPaths: string[] = [];

  const executableDir = path.dirname(config.executable);
  if (path.isAbsolute(config.executable) && executableDir) {
    additionalPaths.push(executableDir);
  }

  const npmGlobal = process.env.NPM_GLOBAL_PATH;
  if (npmGlobal) {
    additionalPaths.push(npmGlobal);
  }

  if (process.platform === 'win32') {
    const appData = process.env.APPDATA;
    const localApp = process.env.LOCALAPPDATA;
    if (appData) {
      additionalPaths.push(path.join(appData, 'npm'));
    }
    if (localApp) {
      additionalPaths.push(path.join(localApp, 'Programs', 'nodejs'));
    }
  }

  const existingPath = env.PATH || env.Path || '';
  env.PATH = [...additionalPaths, existingPath].filter(Boolean).join(path.delimiter);

  if (config.apiKey) {
    env.OPENAI_API_KEY = config.apiKey;
  }
  if (config.openAIBaseUrl) {
    env.OPENAI_BASE_URL = config.openAIBaseUrl;
  }
  env.CODEX_DISABLE_NONESSENTIAL_TRAFFIC = env.CODEX_DISABLE_NONESSENTIAL_TRAFFIC || '1';

  return env;
}

export function buildCodexFeatureArgs(): string[] {
  const config = getCodexRuntimeConfig();
  if (!config.disablePlugins) {
    return [];
  }

  return [
    '--disable',
    'plugins',
    '--disable',
    'plugin_sharing',
    '--disable',
    'plugin_hooks',
    '--disable',
    'remote_plugin',
  ];
}

export function buildCodexConfigArgs(): string[] {
  const config = getCodexRuntimeConfig();
  const args = [
    '-c',
    'include_apply_patch_tool=true',
    '-c',
    'include_plan_tool=true',
    '-c',
    'tools.web_search_request=true',
    '-c',
    'use_experimental_streamable_shell_tool=true',
    '-c',
    'sandbox_mode="danger-full-access"',
    '-c',
    `max_turns=${config.maxTurns}`,
    '-c',
    `max_thinking_tokens=${config.maxThinkingTokens}`,
  ];

  if (config.openAIBaseUrl) {
    args.push('-c', `openai_base_url=${JSON.stringify(config.openAIBaseUrl)}`);
  }
  if (config.reasoningEffort) {
    args.push('-c', `model_reasoning_effort=${JSON.stringify(config.reasoningEffort)}`);
  }

  return args;
}
