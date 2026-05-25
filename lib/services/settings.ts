import fs from 'fs/promises';
import path from 'path';
import { getDefaultModelForCli, normalizeModelId } from '@/lib/constants/cliModels';

const DATA_DIR = process.env.SETTINGS_DIR || path.join(process.cwd(), 'data');
const SETTINGS_FILE = path.join(DATA_DIR, 'global-settings.json');

export type CLISettings = Record<string, Record<string, unknown>>;

export interface GlobalSettings {
  default_cli: string;
  cli_settings: CLISettings;
}

const DEFAULT_SETTINGS: GlobalSettings = {
  default_cli: 'claude',
  cli_settings: {
    claude: {
      model: getDefaultModelForCli('claude'),
    },
    codex: {
      model: getDefaultModelForCli('codex'),
    },
    cursor: {
      model: getDefaultModelForCli('cursor'),
    },
    qwen: {
      model: getDefaultModelForCli('qwen'),
    },
    glm: {
      model: getDefaultModelForCli('glm'),
    },
  },
};

function migrateStoredModelDefaults(settings: GlobalSettings): GlobalSettings {
  const codexSettings = settings.cli_settings?.codex ?? {};
  const normalizedCodexModel = normalizeModelId(
    'codex',
    typeof codexSettings.model === 'string' ? codexSettings.model : undefined
  );

  if (codexSettings.model === normalizedCodexModel) {
    return settings;
  }

  return {
    ...settings,
    cli_settings: {
      ...settings.cli_settings,
      codex: {
        ...codexSettings,
        model: normalizedCodexModel,
      },
    },
  };
}

function applyEnvironmentModelDefaults(settings: GlobalSettings): GlobalSettings {
  const anthropicModel = process.env.ANTHROPIC_MODEL?.trim();
  const codexModelRaw = process.env.CODEX_MODEL?.trim();
  const codexModel = codexModelRaw ? normalizeModelId('codex', codexModelRaw) : undefined;
  let nextSettings = settings;

  if (anthropicModel) {
    const claudeSettings = nextSettings.cli_settings?.claude ?? {};
    const currentModel =
      typeof claudeSettings.model === 'string' && claudeSettings.model.trim().length > 0
        ? claudeSettings.model.trim()
        : undefined;

    if (!currentModel || currentModel === DEFAULT_SETTINGS.cli_settings.claude.model) {
      nextSettings = {
        ...nextSettings,
        default_cli: nextSettings.default_cli || 'claude',
        cli_settings: {
          ...nextSettings.cli_settings,
          claude: {
            ...claudeSettings,
            model: anthropicModel,
          },
        },
      };
    }
  }

  if (codexModel) {
    const codexSettings = nextSettings.cli_settings?.codex ?? {};
    const currentModel =
      typeof codexSettings.model === 'string' && codexSettings.model.trim().length > 0
        ? codexSettings.model.trim()
        : undefined;

    if (!currentModel || currentModel === DEFAULT_SETTINGS.cli_settings.codex.model) {
      nextSettings = {
        ...nextSettings,
        cli_settings: {
          ...nextSettings.cli_settings,
          codex: {
            ...codexSettings,
            model: codexModel,
          },
        },
      };
    }
  }

  return nextSettings;
}

function applyEnvironmentRuntimeDefaults(settings: GlobalSettings): GlobalSettings {
  const codexBaseUrl = process.env.CODEX_OPENAI_BASE_URL?.trim() || process.env.OPENAI_BASE_URL?.trim();
  const codexReasoningEffort =
    process.env.CODEX_MODEL_REASONING_EFFORT?.trim() || process.env.MODEL_REASONING_EFFORT?.trim();

  if (!codexBaseUrl && !codexReasoningEffort) {
    return settings;
  }

  const codexSettings = settings.cli_settings?.codex ?? {};
  return {
    ...settings,
    cli_settings: {
      ...settings.cli_settings,
      codex: {
        ...codexSettings,
        ...(codexBaseUrl ? { openAIBaseUrl: codexBaseUrl } : {}),
        ...(codexReasoningEffort ? { reasoningEffort: codexReasoningEffort } : {}),
      },
    },
  };
}

async function ensureDataDir(): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
}

async function readSettingsFile(): Promise<GlobalSettings | null> {
  try {
    const raw = await fs.readFile(SETTINGS_FILE, 'utf8');
    const parsed = JSON.parse(raw) as GlobalSettings;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }

    const defaultCli = typeof parsed.default_cli === 'string'
      ? parsed.default_cli
      : DEFAULT_SETTINGS.default_cli;

    const cliSettings =
      typeof parsed.cli_settings === 'object' && parsed.cli_settings !== null
        ? parsed.cli_settings
        : {};

    return {
      default_cli: typeof parsed.default_cli === 'string' ? parsed.default_cli : DEFAULT_SETTINGS.default_cli,
      cli_settings: {
        ...DEFAULT_SETTINGS.cli_settings,
        ...cliSettings,
      },
    };
  } catch (error) {
    return null;
  }
}

async function writeSettings(settings: GlobalSettings): Promise<void> {
  await ensureDataDir();
  await fs.writeFile(SETTINGS_FILE, JSON.stringify(settings, null, 2), 'utf8');
}

export async function loadGlobalSettings(): Promise<GlobalSettings> {
  const existing = await readSettingsFile();
  if (existing) {
    const merged: GlobalSettings = {
      default_cli: existing.default_cli ?? DEFAULT_SETTINGS.default_cli,
      cli_settings: {
        ...DEFAULT_SETTINGS.cli_settings,
        ...(existing.cli_settings ?? {}),
      },
    };
    return applyEnvironmentRuntimeDefaults(applyEnvironmentModelDefaults(migrateStoredModelDefaults(merged)));
  }

  const defaults = applyEnvironmentRuntimeDefaults(applyEnvironmentModelDefaults(migrateStoredModelDefaults(DEFAULT_SETTINGS)));
  await writeSettings(defaults);
  return defaults;
}

export function normalizeCliSettings(settings: unknown): CLISettings | undefined {
  if (!settings || typeof settings !== 'object') {
    return undefined;
  }

  const normalized: CLISettings = {};
  for (const [cli, config] of Object.entries(settings)) {
    if (config && typeof config === 'object') {
      normalized[cli] = {
        ...(config as Record<string, unknown>),
      };
      const model = normalized[cli].model as string | undefined;
      if (model) {
        normalized[cli].model = normalizeModelId(cli, model);
      }
    }
  }
  return normalized;
}

export async function updateGlobalSettings(partial: Partial<GlobalSettings>): Promise<GlobalSettings> {
  const current = await loadGlobalSettings();

  const cliSettings = normalizeCliSettings(partial.cli_settings);

  const next: GlobalSettings = {
    default_cli: partial.default_cli ?? current.default_cli,
    cli_settings: { ...current.cli_settings },
  };

  if (cliSettings) {
    for (const [cli, config] of Object.entries(cliSettings)) {
      next.cli_settings[cli] = {
        ...(current.cli_settings[cli] ?? {}),
        ...config,
      };
    }
  }

  await writeSettings(next);
  return next;
}
