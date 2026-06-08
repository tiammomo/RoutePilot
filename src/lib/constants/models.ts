// ── Model definitions (merged from individual CLI model files) ───────────────

// ── Claude ──────────────────────────────────────────────────────────────────
export type ClaudeModelId = string;

export interface ClaudeModelDefinition {
  id: ClaudeModelId;
  name: string;
  description?: string;
  supportsImages?: boolean;
  provider?: "anthropic" | "minimax" | "external";
  runtime?: "anthropic-compatible";
  external?: boolean;
  aliases: string[];
}

export const CLAUDE_MODEL_DEFINITIONS: ClaudeModelDefinition[] = [
  { id: "MiniMax-M2.7", name: "MiniMax M2.7", description: "MiniMax model served through the Anthropic-compatible Claude Code runtime", supportsImages: false, provider: "minimax", runtime: "anthropic-compatible", external: true, aliases: ["MiniMax-M2.7", "minimax-m2.7", "minimax-m2-7", "m2.7", "m2-7"] },
];
export const CLAUDE_DEFAULT_MODEL: ClaudeModelId = "MiniMax-M2.7";

const CLAUDE_MODEL_ALIAS_MAP: Record<string, ClaudeModelId> = CLAUDE_MODEL_DEFINITIONS.reduce((map, def) => {
  def.aliases.forEach((a) => { map[a.trim().toLowerCase().replace(/[\s_]+/g, "-")] = def.id; });
  map[def.id.toLowerCase()] = def.id;
  return map;
}, {} as Record<string, ClaudeModelId>);

export function normalizeClaudeModelId(model?: string | null): ClaudeModelId {
  if (!model) return CLAUDE_DEFAULT_MODEL;
  const trimmed = model.trim();
  if (!trimmed) return CLAUDE_DEFAULT_MODEL;
  return CLAUDE_MODEL_ALIAS_MAP[trimmed.toLowerCase().replace(/[\s_]+/g, "-")] ?? CLAUDE_DEFAULT_MODEL;
}
export function getClaudeModelDefinition(id: string): ClaudeModelDefinition | undefined {
  return CLAUDE_MODEL_DEFINITIONS.find((d) => d.id === id) ?? CLAUDE_MODEL_DEFINITIONS.find((d) => d.aliases.some((a) => a.toLowerCase() === id.toLowerCase()));
}
export function getClaudeModelDisplayName(id: string): string {
  return getClaudeModelDefinition(id)?.name ?? id;
}

// ── Codex ───────────────────────────────────────────────────────────────────
export interface CodexModelDefinition {
  id: string; name: string; description?: string; supportsImages?: boolean;
  provider?: string; runtime?: string; external?: boolean;
}
export const CODEX_DEFAULT_MODEL = "gpt-5.5";
export const CODEX_MODEL_DEFINITIONS: CodexModelDefinition[] = [
  { id: "gpt-5.5", name: "GPT-5.5", description: "Third-party OpenAI-compatible GPT model for Codex CLI", supportsImages: true, provider: "OpenAI Compatible", runtime: "Codex CLI", external: true },
];

const CODEX_ALIAS_MAP: Record<string, string> = {
  gpt55: "gpt-5.5", gpt_5_5: "gpt-5.5", "gpt-5-5": "gpt-5.5", "gpt5.5": "gpt-5.5",
  gpt5: CODEX_DEFAULT_MODEL, gpt_5: CODEX_DEFAULT_MODEL, "gpt-5": CODEX_DEFAULT_MODEL, "gpt-5.0": CODEX_DEFAULT_MODEL,
  "gpt-4o": CODEX_DEFAULT_MODEL, gpt4o: CODEX_DEFAULT_MODEL, "gpt-4o-mini": CODEX_DEFAULT_MODEL,
  "gpt-4o-mini-high": CODEX_DEFAULT_MODEL, "gpt-4o-mini-low": CODEX_DEFAULT_MODEL,
  "o1-preview": CODEX_DEFAULT_MODEL, "o1-mini": CODEX_DEFAULT_MODEL,
  "claude-3.5-sonnet": CODEX_DEFAULT_MODEL, "claude-sonnet-3.5": CODEX_DEFAULT_MODEL,
  "claude35-sonnet": CODEX_DEFAULT_MODEL, "claude-3-haiku": CODEX_DEFAULT_MODEL,
};
const CODEX_KNOWN_IDS = new Set(CODEX_MODEL_DEFINITIONS.map((m) => m.id));

export function normalizeCodexModelId(model?: string | null): string {
  if (!model || typeof model !== "string") return CODEX_DEFAULT_MODEL;
  const trimmed = model.trim();
  if (!trimmed) return CODEX_DEFAULT_MODEL;
  const lower = trimmed.toLowerCase();
  if (CODEX_ALIAS_MAP[lower]) return CODEX_ALIAS_MAP[lower];
  if (CODEX_KNOWN_IDS.has(lower)) return lower;
  if (CODEX_KNOWN_IDS.has(trimmed)) return trimmed;
  return CODEX_DEFAULT_MODEL;
}
export function getCodexModelDisplayName(id?: string | null): string {
  if (!id) return CODEX_MODEL_DEFINITIONS.find((m) => m.id === CODEX_DEFAULT_MODEL)?.name ?? CODEX_DEFAULT_MODEL;
  const n = normalizeCodexModelId(id);
  return CODEX_MODEL_DEFINITIONS.find((m) => m.id === n)?.name ?? n;
}

// ── Cursor ──────────────────────────────────────────────────────────────────
export interface CursorModelDefinition {
  id: string; name: string; description?: string; supportsImages?: boolean;
}
export const CURSOR_DEFAULT_MODEL = "gpt-5";
export const CURSOR_MODEL_DEFINITIONS: CursorModelDefinition[] = [
  { id: "gpt-5", name: "GPT-5", description: "Cursor Agent default multi-model router (auto-selects best model)" },
  { id: "sonnet-4", name: "Claude Sonnet 4", description: "Anthropic Claude Sonnet via Cursor Agent router" },
  { id: "sonnet-4-thinking", name: "Claude Sonnet 4 (Thinking)", description: "High-depth Claude Sonnet reasoning mode" },
];

const CURSOR_MODEL_ALIASES: Record<string, string> = {
  gpt5: "gpt-5", "gpt-5.0": "gpt-5", sonnet4: "sonnet-4", "sonnet-4.5": "sonnet-4", "sonnet-45": "sonnet-4",
  "claude-sonnet-4.5": "sonnet-4", "claude-sonnet-45": "sonnet-4", "claude-sonnet-4_5": "sonnet-4",
  "claude-sonnet-4": "sonnet-4", "sonnet-4.0-thinking": "sonnet-4-thinking", "claude-sonnet-4-thinking": "sonnet-4-thinking",
  "opus-4.6": "sonnet-4", "opus-4.1": "sonnet-4", "claude-opus-4.6": "sonnet-4", "claude-opus-4.1": "sonnet-4",
  "claude-opus-46": "sonnet-4", "claude-opus-41": "sonnet-4", "claude-opus-4_6": "sonnet-4", "claude-opus-4_1": "sonnet-4",
};
const KNOWN_CURSOR_MODEL_IDS = new Set(CURSOR_MODEL_DEFINITIONS.map((m) => m.id));
const CURSOR_CLI_MODEL_IDS: Record<string, string> = { "gpt-5": "gpt-5", "sonnet-4": "sonnet-4", "sonnet-4-thinking": "sonnet-4-thinking" };

export function normalizeCursorModelId(model?: string | null): string {
  if (!model || typeof model !== "string") return CURSOR_DEFAULT_MODEL;
  const trimmed = model.trim();
  if (!trimmed) return CURSOR_DEFAULT_MODEL;
  const lowered = trimmed.toLowerCase();
  if (CURSOR_MODEL_ALIASES[lowered]) return CURSOR_MODEL_ALIASES[lowered];
  if (KNOWN_CURSOR_MODEL_IDS.has(lowered)) return lowered;
  if (KNOWN_CURSOR_MODEL_IDS.has(trimmed)) return trimmed;
  return CURSOR_DEFAULT_MODEL;
}
export function getCursorModelDisplayName(id?: string | null): string {
  if (!id) return CURSOR_MODEL_DEFINITIONS.find((m) => m.id === CURSOR_DEFAULT_MODEL)?.name ?? CURSOR_DEFAULT_MODEL;
  const n = normalizeCursorModelId(id);
  return CURSOR_MODEL_DEFINITIONS.find((m) => m.id === n)?.name ?? n;
}
export function resolveCursorCliModelId(modelId?: string | null): string {
  const n = normalizeCursorModelId(modelId);
  return CURSOR_CLI_MODEL_IDS[n] ?? n;
}

// ── Qwen ────────────────────────────────────────────────────────────────────
export type QwenModelId = "qwen3-coder-plus" | "qwen3-coder-pro" | "qwen3-coder";

export interface QwenModelDefinition {
  id: QwenModelId; name: string; description?: string; supportsImages?: boolean; aliases: string[];
}
export const QWEN_MODEL_DEFINITIONS: QwenModelDefinition[] = [
  { id: "qwen3-coder-plus", name: "Qwen3 Coder Plus", description: "Balanced 32k context model optimised for coding tasks", aliases: ["qwen3-coder-plus", "qwen3-coder+", "qwen3-plus", "qwen3 coder plus", "qwen-coder-plus", "qwen-coder+", "qwen-plus", "qwen coder plus"] },
  { id: "qwen3-coder-pro", name: "Qwen3 Coder Pro", description: "Larger 128k context model with stronger reasoning", aliases: ["qwen3-coder-pro", "qwen3-pro", "qwen3 coder pro", "qwen-coder-pro", "qwen-pro", "qwen coder pro"] },
  { id: "qwen3-coder", name: "Qwen3 Coder", description: "Default quick model for fast iteration", aliases: ["qwen3-coder", "qwen3", "qwen coder", "qwen-coder", "qwen"] },
];
export const QWEN_DEFAULT_MODEL: QwenModelId = "qwen3-coder-plus";

const QWEN_MODEL_ALIAS_MAP: Record<string, QwenModelId> = QWEN_MODEL_DEFINITIONS.reduce((map, def) => {
  def.aliases.forEach((a) => { map[a.trim().toLowerCase().replace(/[\s_]+/g, "-")] = def.id; });
  map[def.id.toLowerCase()] = def.id;
  return map;
}, {} as Record<string, QwenModelId>);

export function normalizeQwenModelId(model?: string | null): QwenModelId {
  if (!model) return QWEN_DEFAULT_MODEL;
  return QWEN_MODEL_ALIAS_MAP[model.trim().toLowerCase().replace(/[\s_]+/g, "-")] ?? QWEN_DEFAULT_MODEL;
}
export function getQwenModelDefinition(id: string): QwenModelDefinition | undefined {
  return QWEN_MODEL_DEFINITIONS.find((d) => d.id === id) ?? QWEN_MODEL_DEFINITIONS.find((d) => d.aliases.some((a) => a.toLowerCase() === id.toLowerCase()));
}
export function getQwenModelDisplayName(id?: string | null): string {
  if (!id) return getQwenModelDefinition(QWEN_DEFAULT_MODEL)?.name ?? QWEN_DEFAULT_MODEL;
  return getQwenModelDefinition(normalizeQwenModelId(id))?.name ?? normalizeQwenModelId(id);
}

// ── GLM ─────────────────────────────────────────────────────────────────────
export type GLMModelId = "glm-4.6";

export interface GLMModelDefinition {
  id: GLMModelId; name: string; description?: string; supportsImages?: boolean; aliases: string[];
}
export const GLM_MODEL_DEFINITIONS: GLMModelDefinition[] = [
  { id: "glm-4.6", name: "GLM 4.6", description: "Zhipu GLM 4.6 with Claude Code compatible agent runtime", supportsImages: false, aliases: ["glm46", "glm-46", "glm_46", "glm 4.6", "glm-4_6", "glm4.6", "glm4", "glm", "glm-latest"] },
];
export const GLM_DEFAULT_MODEL: GLMModelId = "glm-4.6";

const GLM_MODEL_ALIAS_MAP: Record<string, GLMModelId> = GLM_MODEL_DEFINITIONS.reduce((acc, def) => {
  acc[def.id.toLowerCase()] = def.id;
  for (const a of def.aliases) acc[a.toLowerCase()] = def.id;
  return acc;
}, {} as Record<string, GLMModelId>);

export function normalizeGLMModelId(model?: string | null): GLMModelId {
  if (!model) return GLM_DEFAULT_MODEL;
  const n = model.trim().toLowerCase();
  return n ? GLM_MODEL_ALIAS_MAP[n] ?? GLM_DEFAULT_MODEL : GLM_DEFAULT_MODEL;
}
export function getGLMModelDefinition(id: string): GLMModelDefinition | undefined {
  return GLM_MODEL_DEFINITIONS.find((d) => d.id === id) ?? GLM_MODEL_DEFINITIONS.find((d) => d.aliases.some((a) => a.toLowerCase() === id.toLowerCase()));
}
export function getGLMModelDisplayName(id?: string | null): string {
  if (!id) return getGLMModelDefinition(GLM_DEFAULT_MODEL)?.name ?? GLM_DEFAULT_MODEL;
  return getGLMModelDefinition(normalizeGLMModelId(id))?.name ?? normalizeGLMModelId(id);
}

// ── CLI aggregator ──────────────────────────────────────────────────────────
type CLIKey = "claude" | "codex" | "cursor" | "gemini" | "qwen" | "glm";

type ModelDefinition = {
  id: string; name: string; description?: string; supportsImages?: boolean;
  provider?: string; runtime?: string; external?: boolean;
};

const DEFAULT_MODELS: Record<CLIKey, string> = {
  claude: CLAUDE_DEFAULT_MODEL, codex: CODEX_DEFAULT_MODEL, cursor: CURSOR_DEFAULT_MODEL,
  gemini: "gemini-2.5-pro", qwen: QWEN_DEFAULT_MODEL, glm: GLM_DEFAULT_MODEL,
};

const MODEL_DEFINITIONS: Record<CLIKey, ModelDefinition[]> = {
  claude: CLAUDE_MODEL_DEFINITIONS, codex: CODEX_MODEL_DEFINITIONS, cursor: CURSOR_MODEL_DEFINITIONS,
  gemini: [{ id: "gemini-2.5-pro", name: "Gemini 2.5 Pro" }, { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash" }],
  qwen: QWEN_MODEL_DEFINITIONS, glm: GLM_MODEL_DEFINITIONS,
};

export function getDefaultModelForCli(cli: string | null | undefined): string {
  return CLAUDE_DEFAULT_MODEL;
}

export function normalizeModelId(cli: string | null | undefined, model?: string | null): string {
  return normalizeClaudeModelId(model);
}

export function getModelDisplayName(cli: string | null | undefined, modelId?: string | null): string {
  return getClaudeModelDisplayName(normalizeClaudeModelId(modelId));
}

export function getModelDefinitionsForCli(cli: string | null | undefined): ModelDefinition[] {
  return MODEL_DEFINITIONS.claude;
}
