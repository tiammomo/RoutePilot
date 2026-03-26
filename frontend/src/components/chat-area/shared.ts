'use client';

export const ANSWER_CHARS_PER_TICK = 1;
export const REASONING_CHARS_PER_TICK = 2;
export const STREAM_FLUSH_INTERVAL_MS = 28;
export const MAX_EVENT_LOGS = 14;
export const MAX_STAGE_LOGS = 8;
export const MAX_SUBAGENT_EVENTS = 10;
export const PRESET_CONSTRAINTS = ['亲子', '老人', '无车', '雨天', '少走路'] as const;
export const QUICK_START_PROMPTS = [
  '帮我做一个上海周末 2 天轻松游，地铁可达，预算 1500 元以内',
  '请规划北京亲子 3 日游，包含室内备选和午休节奏',
  '做一个杭州 2 天游预算版，优先高性价比美食和免费景点',
];

export type ActiveView = 'chat' | 'city' | 'status';
export type ComparePlanCount = 2 | 3;

export interface RuntimeLog {
  id: string;
  label: string;
  detail?: string;
  time: string;
}

export function takeChars(source: string, count: number): [string, string] {
  if (!source) return ['', ''];
  const chars = Array.from(source);
  return [chars.slice(0, count).join(''), chars.slice(count).join('')];
}

export function nowLabel(): string {
  return new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function messageTimestamp(): string {
  return new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function normalizeStepLabel(step: Record<string, unknown>, index: number): string {
  const title = typeof step.title === 'string' ? step.title : '';
  const description = typeof step.description === 'string' ? step.description : '';
  const tool = typeof step.tool === 'string' ? step.tool : '';
  return title || description || tool || `步骤 ${index + 1}`;
}

export function subagentLabel(name: string | null | undefined): string {
  if (name === 'planning') return '规划';
  if (name === 'research') return '研究';
  if (name === 'verification') return '校验';
  return name || 'unknown';
}

export function buildEnhancedPrompt(
  rawInput: string,
  options: {
    selectedConstraints: string[];
    budgetUpperLimit: number | null;
    compareModeEnabled: boolean;
    comparePlanCount: ComparePlanCount;
  }
): string {
  const constraints = [...options.selectedConstraints];
  if (options.budgetUpperLimit && options.budgetUpperLimit > 0) {
    constraints.push(`预算上限 ${options.budgetUpperLimit} 元`);
  }
  const constraintLine = constraints.length > 0 ? `约束条件：${constraints.join('、')}` : '';
  const compareLine = options.compareModeEnabled
    ? `请同时生成 ${options.comparePlanCount} 套方案用于对比，至少覆盖省钱版、均衡版、舒适版中的任意组合。`
    : '';
  const formatLine =
    '请按“每日行程卡”输出：每一天包含上午 / 下午 / 晚上安排、当日预算、小贴士，并在每天给出景点点位列表。最后附上可执行清单与 T-7 / T-3 / T-1 提醒。';

  return [rawInput, constraintLine, compareLine, formatLine].filter(Boolean).join('\n\n');
}
