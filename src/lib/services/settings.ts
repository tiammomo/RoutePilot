import fs from 'fs/promises';
import path from 'path';
import { Prisma } from '@prisma/client';
import { prisma } from '@/lib/db/client';
import { getDefaultModelForCli, normalizeModelId } from '@/lib/constants/cliModels';

const DATA_DIR = process.env.SETTINGS_DIR || path.join(process.cwd(), 'data');
const SETTINGS_FILE = path.join(DATA_DIR, 'global-settings.json');
const GLOBAL_SETTINGS_KEY = 'global';

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
  },
};

function migrateStoredModelDefaults(settings: GlobalSettings): GlobalSettings {
  return {
    ...settings,
    default_cli: 'claude',
    cli_settings: {
      claude: {
        ...(settings.cli_settings?.claude ?? {}),
        model: normalizeModelId('claude', settings.cli_settings?.claude?.model as string | undefined),
      },
    },
  };
}

function applyEnvironmentModelDefaults(settings: GlobalSettings): GlobalSettings {
  const anthropicModel = process.env.ANTHROPIC_MODEL?.trim();
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

  return nextSettings;
}

function applyEnvironmentRuntimeDefaults(settings: GlobalSettings): GlobalSettings {
  return settings;
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
  try {
    await prisma.platformSetting.upsert({
      where: { key: GLOBAL_SETTINGS_KEY },
      update: { value: settings as unknown as Prisma.InputJsonValue },
      create: { key: GLOBAL_SETTINGS_KEY, value: settings as unknown as Prisma.InputJsonValue },
    });
  } catch (error) {
    if (process.env.SKIP_DB_SYNC === '1') {
      await ensureDataDir();
      await fs.writeFile(SETTINGS_FILE, JSON.stringify(settings, null, 2), 'utf8');
      return;
    }
    throw error;
  }
}

function coerceSettings(value: unknown): GlobalSettings | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const parsed = value as Partial<GlobalSettings>;
  const cliSettings =
    parsed.cli_settings && typeof parsed.cli_settings === 'object'
      ? parsed.cli_settings
      : {};

  return {
    default_cli: typeof parsed.default_cli === 'string' ? parsed.default_cli : DEFAULT_SETTINGS.default_cli,
    cli_settings: {
      ...DEFAULT_SETTINGS.cli_settings,
      ...cliSettings,
    },
  };
}

async function readSettingsFromDatabase(): Promise<GlobalSettings | null> {
  try {
    const record = await prisma.platformSetting.findUnique({
      where: { key: GLOBAL_SETTINGS_KEY },
    });
    return coerceSettings(record?.value);
  } catch {
    return null;
  }
}

async function migrateSettingsFileToDatabase(settings: GlobalSettings): Promise<void> {
  try {
    await writeSettings(settings);
  } catch {
    await ensureDataDir();
    await fs.writeFile(SETTINGS_FILE, JSON.stringify(settings, null, 2), 'utf8');
  }
}

export async function loadGlobalSettings(): Promise<GlobalSettings> {
  const stored = await readSettingsFromDatabase();
  if (stored) {
    return applyEnvironmentRuntimeDefaults(applyEnvironmentModelDefaults(migrateStoredModelDefaults(stored)));
  }

  const existing = await readSettingsFile();
  if (existing) {
    const merged: GlobalSettings = {
      default_cli: existing.default_cli ?? DEFAULT_SETTINGS.default_cli,
      cli_settings: {
        ...DEFAULT_SETTINGS.cli_settings,
        ...(existing.cli_settings ?? {}),
      },
    };
    const normalized = applyEnvironmentRuntimeDefaults(applyEnvironmentModelDefaults(migrateStoredModelDefaults(merged)));
    await migrateSettingsFileToDatabase(normalized);
    return normalized;
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
