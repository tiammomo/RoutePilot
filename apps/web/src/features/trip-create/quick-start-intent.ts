const STORAGE_PREFIX = "routepilot.quick-start.v1.";
const MAX_PROMPT_LENGTH = 2_000;
const MAX_DESTINATION_LENGTH = 100;

const KNOWN_DESTINATIONS = [
  "新加坡", "吉隆坡", "洛杉矶", "旧金山", "香港", "澳门", "台北", "北京", "上海", "广州", "深圳",
  "杭州", "南京", "苏州", "成都", "重庆", "西安", "厦门", "大理", "丽江", "三亚", "东京", "京都",
  "大阪", "首尔", "曼谷", "清迈", "巴黎", "伦敦", "罗马", "悉尼",
] as const;

interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface QuickStartIntent {
  prompt: string;
  destination?: string;
}

function storageKey(tripId: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(tripId)}`;
}

function browserSessionStorage(): StorageLike | undefined {
  return typeof window === "undefined" ? undefined : window.sessionStorage;
}

export function detectExplicitDestination(prompt: string): string | undefined {
  const normalized = prompt.trim();
  return KNOWN_DESTINATIONS.find((destination) => normalized.includes(destination));
}

export function deriveTripTitle(prompt: string): string {
  const normalized = prompt
    .replace(/[\r\n\t]+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim()
    .replace(/[？?！!。．]+$/g, "")
    .trim();
  if (!normalized) return "新的旅行计划";
  return normalized.length <= 34 ? normalized : `${normalized.slice(0, 33).trimEnd()}…`;
}

export function saveQuickStartIntent(
  tripId: string,
  prompt: string,
  target: StorageLike | undefined = browserSessionStorage(),
): void {
  if (!target) return;
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt || cleanPrompt.length > MAX_PROMPT_LENGTH) return;
  const destination = detectExplicitDestination(cleanPrompt);
  try {
    target.setItem(storageKey(tripId), JSON.stringify({
      version: 1,
      prompt: cleanPrompt,
      ...(destination ? { destination } : {}),
    }));
  } catch {
    // A blocked session store only removes prefill convenience; creation still succeeds.
  }
}

export function consumeQuickStartIntent(
  tripId: string,
  target: StorageLike | undefined = browserSessionStorage(),
): QuickStartIntent | null {
  if (!target) return null;
  const key = storageKey(tripId);
  try {
    const raw = target.getItem(key);
    target.removeItem(key);
    if (!raw || raw.length > 4_500) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (parsed.version !== 1 || typeof parsed.prompt !== "string") return null;
    const prompt = parsed.prompt.trim();
    if (!prompt || prompt.length > MAX_PROMPT_LENGTH) return null;
    const destination = typeof parsed.destination === "string" &&
      parsed.destination.length <= MAX_DESTINATION_LENGTH &&
      detectExplicitDestination(prompt) === parsed.destination
      ? parsed.destination
      : undefined;
    return { prompt, ...(destination ? { destination } : {}) };
  } catch {
    try { target.removeItem(key); } catch { /* Storage may be blocked. */ }
    return null;
  }
}
