/**
 * Codex CLI model definitions and helpers
 */

export interface CodexModelDefinition {
  id: string;
  name: string;
  description?: string;
  supportsImages?: boolean;
  provider?: string;
  runtime?: string;
  external?: boolean;
}

export const CODEX_DEFAULT_MODEL = 'gpt-5.5';

export const CODEX_MODEL_DEFINITIONS: CodexModelDefinition[] = [
  {
    id: 'gpt-5.5',
    name: 'GPT-5.5',
    description: 'Third-party OpenAI-compatible GPT model for Codex CLI',
    supportsImages: true,
    provider: 'OpenAI Compatible',
    runtime: 'Codex CLI',
    external: true,
  },
];

const ALIAS_MAP: Record<string, string> = {
  'gpt55': 'gpt-5.5',
  'gpt_5_5': 'gpt-5.5',
  'gpt-5-5': 'gpt-5.5',
  'gpt5.5': 'gpt-5.5',
  'gpt5': CODEX_DEFAULT_MODEL,
  'gpt_5': CODEX_DEFAULT_MODEL,
  'gpt-5': CODEX_DEFAULT_MODEL,
  'gpt-5.0': CODEX_DEFAULT_MODEL,
  'gpt-4o': CODEX_DEFAULT_MODEL,
  'gpt4o': CODEX_DEFAULT_MODEL,
  'gpt-4o-mini': CODEX_DEFAULT_MODEL,
  'gpt-4o-mini-high': CODEX_DEFAULT_MODEL,
  'gpt-4o-mini-low': CODEX_DEFAULT_MODEL,
  'o1-preview': CODEX_DEFAULT_MODEL,
  'o1-mini': CODEX_DEFAULT_MODEL,
  'claude-3.5-sonnet': CODEX_DEFAULT_MODEL,
  'claude-sonnet-3.5': CODEX_DEFAULT_MODEL,
  'claude35-sonnet': CODEX_DEFAULT_MODEL,
  'claude-3-haiku': CODEX_DEFAULT_MODEL,
};

const KNOWN_IDS = new Set(CODEX_MODEL_DEFINITIONS.map((model) => model.id));

export function normalizeCodexModelId(model?: string | null): string {
  if (!model || typeof model !== 'string') {
    return CODEX_DEFAULT_MODEL;
  }

  const trimmed = model.trim();
  if (!trimmed) {
    return CODEX_DEFAULT_MODEL;
  }

  const lower = trimmed.toLowerCase();
  if (ALIAS_MAP[lower]) {
    return ALIAS_MAP[lower];
  }

  if (KNOWN_IDS.has(lower)) {
    return lower;
  }

  // If the exact casing exists, allow it
  if (KNOWN_IDS.has(trimmed)) {
    return trimmed;
  }

  return CODEX_DEFAULT_MODEL;
}

export function getCodexModelDisplayName(id?: string | null): string {
  if (!id) {
    return CODEX_MODEL_DEFINITIONS.find((model) => model.id === CODEX_DEFAULT_MODEL)?.name ?? CODEX_DEFAULT_MODEL;
  }

  const normalized = normalizeCodexModelId(id);
  const match = CODEX_MODEL_DEFINITIONS.find((model) => model.id === normalized);
  return match?.name ?? normalized;
}
