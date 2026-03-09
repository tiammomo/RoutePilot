import type { MessageDiagnostics } from '@/types';

export interface DayPlanCard {
  dayLabel: string;
  morning: string;
  afternoon: string;
  evening: string;
  tips: string[];
  baseBudget: number;
  spots: string[];
}

export interface PlanVariant {
  id: string;
  title: string;
  content: string;
}

export interface BudgetProjection {
  totalBudget: number;
  perDayBudget: number;
  hotelShare: number;
  foodShare: number;
  trafficShare: number;
}

export interface RoutePoint {
  name: string;
  lat: number;
  lng: number;
}

export interface ChecklistItem {
  id: string;
  label: string;
}

export interface ReminderItem {
  id: string;
  phase: 'T-7' | 'T-3' | 'T-1';
  title: string;
  detail: string;
}

export interface ConfidenceSummary {
  score: number;
  level: '高' | '中' | '低';
  risks: string[];
}

const PERIOD_PATTERNS: Record<'morning' | 'afternoon' | 'evening', RegExp> = {
  morning: /(上午|早上|晨间|morning)/i,
  afternoon: /(下午|午后|afternoon)/i,
  evening: /(晚上|夜间|傍晚|evening|night)/i,
};

const DAY_HEADING_REGEX = /^(#{1,6}\s*)?(Day\s*\d+|D\d+|第[一二三四五六七八九十百0-9]+天)/i;

function normalizeLine(line: string): string {
  return line.replace(/^\s*[-*+\d.、]+\s*/, '').trim();
}

function stripMarkdownNoise(input: string): string {
  return input
    .replace(/[*_`~#>\[\]\(\)]/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/https?:\/\/\S+/gi, ' ')
    .replace(/[|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function cleanForDisplay(input: string): string {
  return stripMarkdownNoise(input)
    .replace(/[;；]{2,}/g, '；')
    .replace(/[，,]{2,}/g, '，')
    .replace(/^[:：\-\s]+/, '')
    .trim();
}

function extractMoneyCandidates(content: string): number[] {
  const values = new Set<number>();
  const regex = /(￥|¥|RMB|预算|人均|总计|约)\s*([0-9]{2,6})/gi;
  let match = regex.exec(content);
  while (match) {
    const value = Number(match[2]);
    if (Number.isFinite(value) && value > 0) values.add(value);
    match = regex.exec(content);
  }
  return Array.from(values.values());
}

function dedupeStrings(items: string[]): string[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.trim();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function splitDayBlocks(content: string): string[] {
  const normalizedContent = content.replace(
    /([；;。]\s*)(#{1,6}\s*)?(Day\s*\d+|D\d+|第[一二三四五六七八九十百0-9]+天)/gi,
    (_match, p1, _p2, p3) => `${p1}\n${p3}`
  );
  const lines = normalizedContent.split('\n');
  const blocks: string[][] = [];
  let currentBlock: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    if (DAY_HEADING_REGEX.test(line) && currentBlock.length > 0) {
      blocks.push(currentBlock);
      currentBlock = [line];
      continue;
    }
    currentBlock.push(line);
  }

  if (currentBlock.length > 0) blocks.push(currentBlock);
  return blocks.map((block) => block.join('\n'));
}

function pickDayLabel(block: string, fallbackIndex: number): string {
  const firstLine = block.split('\n')[0] || '';
  if (DAY_HEADING_REGEX.test(firstLine)) return cleanForDisplay(firstLine.replace(/^#{1,6}\s*/, ''));
  return `Day ${fallbackIndex + 1}`;
}

function collectTips(lines: string[]): string[] {
  const tips = lines
    .filter((line) => /(小贴士|tips|提示|注意|建议)/i.test(line))
    .map((line) =>
      cleanForDisplay(normalizeLine(line).replace(/^(小贴士|Tips?|提示|注意|建议)[:：]?\s*/i, ''))
    )
    .filter((line) => line.length >= 4)
    .filter((line) => !/^(第[一二三四五六七八九十百0-9]+天|day\s*\d+)/i.test(line))
    .filter((line) => !/^(住宿建议|旅行小贴士|注意事项)$/i.test(line));
  return dedupeStrings(tips).slice(0, 6);
}

function collectSpots(lines: string[]): string[] {
  const spots: string[] = [];
  for (const line of lines) {
    const normalized = cleanForDisplay(normalizeLine(line));
    if (!normalized) continue;
    if (/(预算|费用|门票|交通|住宿|餐饮|建议|小贴士|tips)/i.test(normalized)) continue;
    const splitByPunctuation = normalized.split(/[，。；：,;>→]/).map((item) => item.trim());
    for (const token of splitByPunctuation) {
      if (token.length >= 2 && token.length <= 24 && !/\d{2,}/.test(token)) spots.push(token);
    }
  }
  return dedupeStrings(spots).slice(0, 8);
}

function parsePeriodText(blockLines: string[], period: 'morning' | 'afternoon' | 'evening'): string {
  const directLine = blockLines.find((line) => PERIOD_PATTERNS[period].test(line));
  if (!directLine) return '';

  const directIndex = blockLines.indexOf(directLine);
  const capture: string[] = [normalizeLine(directLine)];
  for (let i = directIndex + 1; i < blockLines.length; i += 1) {
    const line = blockLines[i];
    if (
      PERIOD_PATTERNS.morning.test(line) ||
      PERIOD_PATTERNS.afternoon.test(line) ||
      PERIOD_PATTERNS.evening.test(line)
    ) {
      break;
    }
    capture.push(normalizeLine(line));
  }

  return cleanForDisplay(
    capture
    .filter(Boolean)
    .join('；')
    .replace(/^(上午|早上|晨间|morning|下午|午后|afternoon|晚上|夜间|傍晚|evening|night)[:：]?\s*/i, '')
  );
}

export function parseDayPlanCards(content: string): DayPlanCard[] {
  if (!content.trim()) return [];
  const blocks = splitDayBlocks(content);
  const candidateBlocks = blocks.length > 0 ? blocks : [content];
  const baseNumbers = extractMoneyCandidates(content);
  const fallbackBudget = baseNumbers[0] || 1200;

  return candidateBlocks.slice(0, 7).map((block, index) => {
    const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
    const tips = collectTips(lines);
    const spots = collectSpots(lines);
    const blockMoney = extractMoneyCandidates(block);
    const morning = parsePeriodText(lines, 'morning');
    const afternoon = parsePeriodText(lines, 'afternoon');
    const evening = parsePeriodText(lines, 'evening');

    return {
      dayLabel: pickDayLabel(block, index),
      morning: morning || '自由安排或按兴趣补充景点',
      afternoon: afternoon || '建议安排核心景点与午餐',
      evening: evening || '轻松散步、夜景或特色餐厅',
      tips: tips.length > 0 ? tips : ['尽量提前预约热门景点和餐厅'],
      baseBudget: blockMoney[0] || fallbackBudget,
      spots,
    };
  });
}

export function parsePlanVariants(content: string): PlanVariant[] {
  const markers = content.match(/(方案\s*[A-C]|省钱版|均衡版|舒适版|轻松版)/gi);
  if (!markers || markers.length < 2) return [];

  const lines = content.split('\n');
  const variants: PlanVariant[] = [];
  let currentTitle = '';
  let currentLines: string[] = [];

  for (const line of lines) {
    const marker = line.match(/(方案\s*[A-C]|省钱版|均衡版|舒适版|轻松版)/i)?.[0] || '';
    if (marker) {
      if (currentTitle && currentLines.length > 0) {
        variants.push({
          id: `${variants.length + 1}`,
          title: currentTitle,
          content: currentLines.join('\n').trim(),
        });
      }
      currentTitle = marker;
      currentLines = [line];
      continue;
    }
    if (currentTitle) currentLines.push(line);
  }

  if (currentTitle && currentLines.length > 0) {
    variants.push({
      id: `${variants.length + 1}`,
      title: currentTitle,
      content: currentLines.join('\n').trim(),
    });
  }

  return variants.slice(0, 3);
}

export function getBudgetProjection(baseDailyBudget: number, days: number, sliderValue: number): BudgetProjection {
  const normalized = Math.max(0, Math.min(100, sliderValue));
  const factor = normalized <= 33 ? 0.82 : normalized >= 67 ? 1.26 : 1;
  const hotelShare = normalized <= 33 ? 0.31 : normalized >= 67 ? 0.46 : 0.39;
  const foodShare = normalized <= 33 ? 0.27 : normalized >= 67 ? 0.24 : 0.25;
  const trafficShare = 1 - hotelShare - foodShare;

  const perDayBudget = Math.round(baseDailyBudget * factor);
  const totalBudget = perDayBudget * Math.max(days, 1);

  return {
    totalBudget,
    perDayBudget,
    hotelShare,
    foodShare,
    trafficShare,
  };
}

function hashToCoordinate(input: string, min: number, max: number): number {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) hash = (hash << 5) - hash + input.charCodeAt(i);
  const normalized = ((hash % 10000) + 10000) % 10000;
  const ratio = normalized / 10000;
  return Number((min + (max - min) * ratio).toFixed(4));
}

export function buildRoutePoints(spots: string[]): RoutePoint[] {
  return dedupeStrings(spots).map((spot) => ({
    name: spot,
    lat: hashToCoordinate(spot, 22.5, 41.0),
    lng: hashToCoordinate(`${spot}-lng`, 102.0, 123.0),
  }));
}

function distance(a: RoutePoint, b: RoutePoint): number {
  const dx = a.lat - b.lat;
  const dy = a.lng - b.lng;
  return Math.sqrt(dx * dx + dy * dy);
}

export function reorderByDistance(points: RoutePoint[]): RoutePoint[] {
  if (points.length <= 2) return points;
  const result: RoutePoint[] = [points[0]];
  const remaining = points.slice(1);

  while (remaining.length > 0) {
    const last = result[result.length - 1];
    let bestIndex = 0;
    let bestDistance = Infinity;

    for (let i = 0; i < remaining.length; i += 1) {
      const candidateDistance = distance(last, remaining[i]);
      if (candidateDistance < bestDistance) {
        bestDistance = candidateDistance;
        bestIndex = i;
      }
    }

    const [next] = remaining.splice(bestIndex, 1);
    result.push(next);
  }

  return result;
}

export function buildChecklist(content: string): ChecklistItem[] {
  const candidates: string[] = [
    '预订往返交通（机票/高铁）',
    '确认酒店与入住时间',
    '准备证件（身份证/护照）',
    '规划市内交通与导航',
    '检查目的地天气与穿搭',
    '整理常用药品与充电设备',
  ];

  if (/签证|visa/i.test(content)) candidates.push('核对签证/入境材料');
  if (/亲子|儿童/i.test(content)) candidates.push('准备儿童用品与应急物品');
  if (/老人|长辈/i.test(content)) candidates.push('准备慢行路线与休息点');

  return dedupeStrings(candidates).map((label, index) => ({
    id: `todo-${index + 1}`,
    label,
  }));
}

export function buildReminders(): ReminderItem[] {
  return [
    {
      id: 't7',
      phase: 'T-7',
      title: '确认核心预订',
      detail: '锁定机票/酒店，检查退改规则和证件有效期。',
    },
    {
      id: 't3',
      phase: 'T-3',
      title: '整理行李与路线',
      detail: '按天气准备衣物，确认每日集合点与交通衔接。',
    },
    {
      id: 't1',
      phase: 'T-1',
      title: '最终核对',
      detail: '检查车票、酒店订单、支付方式和出发时间提醒。',
    },
  ];
}

export function buildConfidenceSummary(diagnostics?: MessageDiagnostics): ConfidenceSummary {
  if (!diagnostics) {
    return {
      score: 55,
      level: '中',
      risks: ['暂无后端验证元数据，建议对关键价格与营业时间再确认一次。'],
    };
  }

  let score = 70;
  const risks: string[] = [];

  if (diagnostics.verificationPassed === true) score += 18;
  if (diagnostics.verificationPassed === false) {
    score -= 18;
    risks.push('结果校验未通过，存在信息偏差风险。');
  }

  const staleCount = Number(diagnostics.staleResultCount || 0);
  if (staleCount > 0) {
    score -= Math.min(20, staleCount * 6);
    risks.push(`检测到 ${staleCount} 条可能过期信息，建议复核营业时间/票价。`);
  }

  const fallback = Number(diagnostics.fallbackSteps || 0);
  if (fallback > 0) {
    score -= Math.min(12, fallback * 3);
    risks.push(`发生 ${fallback} 次备源切换，部分细节可能来自降级结果。`);
  }

  score = Math.max(20, Math.min(98, score));
  const level: '高' | '中' | '低' = score >= 80 ? '高' : score >= 60 ? '中' : '低';

  if (risks.length === 0) risks.push('风险较低，仍建议对实时票务和天气做出发前复核。');
  return { score, level, risks };
}
