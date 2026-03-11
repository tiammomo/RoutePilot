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
  level: 'high' | 'medium' | 'low';
  risks: string[];
}

export interface SpotDecisionInfo {
  name: string;
  stayDuration: string;
  bestArrival: string;
  audience: string;
  costHint: string;
}

export interface PracticalInfoCard {
  id: string;
  title: string;
  value: string;
  tone: 'neutral' | 'warn' | 'good';
}

export interface ItineraryConflict {
  id: string;
  type: 'time_conflict' | 'long_distance' | 'closing_risk';
  severity: 'low' | 'medium' | 'high';
  title: string;
  description: string;
  suggestion: string;
}

interface TimeEntry {
  raw: string;
  timeMinutes: number | null;
  content: string;
}

// Heuristic keyword mapping for period extraction from free-form itinerary text.
const PERIOD_PATTERNS: Record<'morning' | 'afternoon' | 'evening', RegExp> = {
  morning: /(?:\u4e0a\u5348|\u65e9\u4e0a|morning)/i,
  afternoon: /(?:\u4e0b\u5348|afternoon)/i,
  evening: /(?:\u665a\u4e0a|\u591c\u95f4|evening|night)/i,
};

const DAY_HEADING_REGEX = /^(#{1,6}\s*)?(Day\s*\d+|D\d+|\u7b2c[\u4e00-\u9fff0-9]+\u5929)/i;

function normalizeLine(line: string): string {
  return line.replace(/^\s*[-*+\d.\u3001]+\s*/, '').trim();
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

function dedupeStrings(items: string[]): string[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = item.trim();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function extractMoneyCandidates(content: string): number[] {
  const values = new Set<number>();
  const regex = /(¥|￥|RMB|CNY|\u9884\u7b97|\u4eba\u5747|\u603b\u8ba1|\u7ea6)\s*([0-9]{2,6})/gi;
  let match = regex.exec(content);
  while (match) {
    const value = Number(match[2]);
    if (Number.isFinite(value) && value > 0) values.add(value);
    match = regex.exec(content);
  }
  return Array.from(values.values());
}

function splitDayBlocks(content: string): string[] {
  // Normalize compact "Day X" inline mentions into line starts so later parsing is stable.
  const normalizedContent = content.replace(
    /([；;。]\s*)(#{1,6}\s*)?(Day\s*\d+|D\d+|\u7b2c[\u4e00-\u9fff0-9]+\u5929)/gi,
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
    .filter((line) => /(?:\u5c0f\u8d34\u58eb|tips|\u63d0\u793a|\u6ce8\u610f|\u5efa\u8bae)/i.test(line))
    .map((line) =>
      cleanForDisplay(normalizeLine(line).replace(/^(?:\u5c0f\u8d34\u58eb|Tips?|\u63d0\u793a|\u6ce8\u610f|\u5efa\u8bae)[:：]?\s*/i, ''))
    )
    .filter((line) => line.length >= 4)
    .filter((line) => !/^(?:Day\s*\d+|\u7b2c[\u4e00-\u9fff0-9]+\u5929)$/i.test(line));
  return dedupeStrings(tips).slice(0, 6);
}

function collectSpots(lines: string[]): string[] {
  const spots: string[] = [];
  for (const line of lines) {
    const normalized = cleanForDisplay(normalizeLine(line));
    if (!normalized) continue;
    if (/(?:\u9884\u7b97|\u8d39\u7528|\u95e8\u7968|\u4ea4\u901a|\u4f4f\u5bbf|\u9910\u996e|\u5efa\u8bae|\u5c0f\u8d34\u58eb|tips)/i.test(normalized)) continue;
    const tokens = normalized.split(/[，。；：,;>→]/).map((item) => item.trim());
    for (const token of tokens) {
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
    if (PERIOD_PATTERNS.morning.test(line) || PERIOD_PATTERNS.afternoon.test(line) || PERIOD_PATTERNS.evening.test(line)) break;
    capture.push(normalizeLine(line));
  }

  return cleanForDisplay(
    capture
      .filter(Boolean)
      .join('；')
      .replace(/^(?:\u4e0a\u5348|\u65e9\u4e0a|morning|\u4e0b\u5348|afternoon|\u665a\u4e0a|\u591c\u95f4|evening|night)[:：]?\s*/i, '')
  );
}

// Parse raw assistant markdown/text into structured day cards for downstream toolkit modules.
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
      morning: morning || 'Free arrangement or one core attraction',
      afternoon: afternoon || 'Core attraction and meal window',
      evening: evening || 'Night view or relaxed dinner',
      tips: tips.length > 0 ? tips : ['Book popular attractions and restaurants early.'],
      baseBudget: blockMoney[0] || fallbackBudget,
      spots,
    };
  });
}

export function parsePlanVariants(content: string): PlanVariant[] {
  const markers = content.match(/(方案\s*[A-C]|省钱版|均衡版|舒适版|轻松版|Plan\s*[A-C])/gi);
  if (!markers || markers.length < 2) return [];

  const lines = content.split('\n');
  const variants: PlanVariant[] = [];
  let currentTitle = '';
  let currentLines: string[] = [];

  for (const line of lines) {
    const marker = line.match(/(方案\s*[A-C]|省钱版|均衡版|舒适版|轻松版|Plan\s*[A-C])/i)?.[0] || '';
    if (marker) {
      if (currentTitle && currentLines.length > 0) {
        variants.push({ id: `${variants.length + 1}`, title: currentTitle, content: currentLines.join('\n').trim() });
      }
      currentTitle = marker;
      currentLines = [line];
      continue;
    }
    if (currentTitle) currentLines.push(line);
  }

  if (currentTitle && currentLines.length > 0) {
    variants.push({ id: `${variants.length + 1}`, title: currentTitle, content: currentLines.join('\n').trim() });
  }

  return variants.slice(0, 3);
}

// Map budget slider to coarse profile factors instead of strict linear scaling,
// keeping projections easier to explain to end users.
export function getBudgetProjection(baseDailyBudget: number, days: number, sliderValue: number): BudgetProjection {
  const normalized = Math.max(0, Math.min(100, sliderValue));
  const factor = normalized <= 33 ? 0.82 : normalized >= 67 ? 1.26 : 1;
  const hotelShare = normalized <= 33 ? 0.31 : normalized >= 67 ? 0.46 : 0.39;
  const foodShare = normalized <= 33 ? 0.27 : normalized >= 67 ? 0.24 : 0.25;
  const trafficShare = 1 - hotelShare - foodShare;

  const perDayBudget = Math.round(baseDailyBudget * factor);
  const totalBudget = perDayBudget * Math.max(days, 1);

  return { totalBudget, perDayBudget, hotelShare, foodShare, trafficShare };
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
    'Book intercity transportation',
    'Confirm hotel and check-in policy',
    'Prepare required IDs/documents',
    'Plan city transport and navigation',
    'Check weather and packing list',
    'Prepare medicine and chargers',
  ];

  if (/visa/i.test(content)) candidates.push('Verify visa/entry requirements');
  if (/(?:亲子|儿童)/i.test(content)) candidates.push('Prepare child-friendly supplies');
  if (/(?:老人|长辈)/i.test(content)) candidates.push('Prepare low-walk fallback options');

  return dedupeStrings(candidates).map((label, index) => ({ id: `todo-${index + 1}`, label }));
}

export function buildReminders(): ReminderItem[] {
  return [
    { id: 't7', phase: 'T-7', title: 'Confirm bookings', detail: 'Lock transport/hotel and verify cancellation rules.' },
    { id: 't3', phase: 'T-3', title: 'Pack and verify route', detail: 'Pack by weather and verify each day transfer points.' },
    { id: 't1', phase: 'T-1', title: 'Final check', detail: 'Re-check tickets, orders, payment and departure time.' },
  ];
}

function inferSpotDuration(name: string): string {
  if (/(迪士尼|欢乐谷|环球|乐园|度假区)/i.test(name)) return '4-8h';
  if (/(博物馆|美术馆|展|纪念馆|科技馆|图书馆|museum|gallery)/i.test(name)) return '1.5-3h';
  if (/(古镇|街|步行街|里|坊|夜市|市集)/i.test(name)) return '1-2h';
  if (/(公园|湿地|湖|山|海滩|岛|植物园|动物园)/i.test(name)) return '2-4h';
  if (/(寺|庙|宫|塔|教堂|故居|古城|城墙|府)/i.test(name)) return '1-2h';
  return '1-2h';
}

function inferBestArrival(name: string): string {
  if (/(夜市|外滩|江边|灯光|夜景|酒吧|秀)/i.test(name)) return '17:30-20:00';
  if (/(博物馆|美术馆|纪念馆|展|museum|gallery)/i.test(name)) return '09:30-11:30';
  if (/(公园|海边|湖|山|古镇|步行街)/i.test(name)) return '08:30-10:30 / 16:00后';
  if (/(乐园|迪士尼|环球|动物园)/i.test(name)) return '开园前后';
  return '10:00-12:00';
}

function inferAudience(name: string): string {
  if (/(迪士尼|动物园|海洋馆|乐园|科技馆)/i.test(name)) return '亲子/第一次来';
  if (/(博物馆|美术馆|纪念馆|展)/i.test(name)) return '文化爱好者/雨天友好';
  if (/(步行街|古镇|夜市|外滩|江边|街区)/i.test(name)) return '情侣/轻松逛';
  if (/(公园|湖|海滩|湿地|植物园)/i.test(name)) return '少压力散步/拍照';
  return '大众友好';
}

function inferSpotCost(name: string): string {
  if (/(迪士尼|环球|乐园|演出|索道)/i.test(name)) return '较高';
  if (/(博物馆|公园|古镇|街区|步行街|外滩)/i.test(name)) return '低到中';
  return '中等';
}

export function buildSpotDecisionInfos(spots: string[]): SpotDecisionInfo[] {
  return dedupeStrings(spots)
    .slice(0, 6)
    .map((name) => ({
      name,
      stayDuration: inferSpotDuration(name),
      bestArrival: inferBestArrival(name),
      audience: inferAudience(name),
      costHint: inferSpotCost(name),
    }));
}

export function buildPracticalInfoCards(content: string): PracticalInfoCard[] {
  const cards: PracticalInfoCard[] = [
    {
      id: 'weather',
      title: '天气与穿衣',
      value: /冬|降温|风大/i.test(content) ? '建议分层穿搭，外层准备防风外套。' : '出发前一天再确认天气，优先准备轻便分层穿搭。',
      tone: 'neutral',
    },
    {
      id: 'transport',
      title: '交通建议',
      value: /无车|地铁|公交/i.test(content) ? '优先地铁+步行，跨区移动尽量集中到同一天。' : '热门时段建议地铁优先，晚间返程可预留打车预算。',
      tone: 'good',
    },
    {
      id: 'documents',
      title: '证件准备',
      value: '身份证、预订凭证、酒店订单截图建议提前整理到一个相册。',
      tone: 'neutral',
    },
    {
      id: 'queue',
      title: '排队高峰',
      value: /周末|节假日/i.test(content) ? '高峰时段更容易排队，热门景点尽量前置到上午。' : '午后到傍晚通常人流更高，热门点位建议错峰。',
      tone: 'warn',
    },
  ];

  if (/(亲子|儿童)/i.test(content)) {
    cards.push({
      id: 'family',
      title: '亲子补充',
      value: '给孩子预留午休和临时室内备选，不要把全天排得过满。',
      tone: 'good',
    });
  }

  if (/(老人|长辈|少走路)/i.test(content)) {
    cards.push({
      id: 'senior',
      title: '体力管理',
      value: '优先连片景点和可随时打车撤退的区域，控制连续步行时长。',
      tone: 'warn',
    });
  }

  return cards;
}

export function buildConfidenceSummary(diagnostics?: MessageDiagnostics): ConfidenceSummary {
  if (!diagnostics) {
    return {
      score: 55,
      level: 'medium',
      risks: ['No verification metadata available. Re-check key prices and opening times.'],
    };
  }

  let score = 70;
  const risks: string[] = [];

  if (diagnostics.verificationPassed === true) score += 18;
  if (diagnostics.verificationPassed === false) {
    score -= 18;
    risks.push('Verification failed. Some details may be inaccurate.');
  }

  const staleCount = Number(diagnostics.staleResultCount || 0);
  if (staleCount > 0) {
    score -= Math.min(20, staleCount * 6);
    risks.push(`Found ${staleCount} potentially stale items. Re-check schedule and pricing.`);
  }

  const fallback = Number(diagnostics.fallbackSteps || 0);
  if (fallback > 0) {
    score -= Math.min(12, fallback * 3);
    risks.push(`Fallback switched ${fallback} times. Some fields may be downgraded.`);
  }

  score = Math.max(20, Math.min(98, score));
  const level: 'high' | 'medium' | 'low' = score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low';
  if (risks.length === 0) risks.push('Low risk, but still re-check real-time weather and ticket inventory.');
  return { score, level, risks };
}

function parseTimeEntries(text: string): TimeEntry[] {
  return text
    .split(/[；;。]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((raw) => {
      const timeMatch = raw.match(/(\d{1,2})[:：](\d{2})/);
      if (!timeMatch) return { raw, timeMinutes: null, content: raw };
      const hour = Number(timeMatch[1]);
      const minute = Number(timeMatch[2]);
      const isValid = Number.isFinite(hour) && Number.isFinite(minute) && hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
      return {
        raw,
        timeMinutes: isValid ? hour * 60 + minute : null,
        content: raw.replace(timeMatch[0], '').replace(/^\s*[-:：]?\s*/, '').trim(),
      };
    });
}

function formatTime(totalMinutes: number): string {
  const h = Math.floor(totalMinutes / 60).toString().padStart(2, '0');
  const m = (totalMinutes % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
}

export function detectDayConflicts(day: DayPlanCard, distanceM?: number): ItineraryConflict[] {
  // Conflict detection is deliberately conservative: prefer surfacing "likely issues"
  // rather than proving strict impossibility.
  const conflicts: ItineraryConflict[] = [];
  const periods = [
    { key: 'morning', label: 'Morning', text: day.morning },
    { key: 'afternoon', label: 'Afternoon', text: day.afternoon },
    { key: 'evening', label: 'Evening', text: day.evening },
  ] as const;

  periods.forEach((period) => {
    const entries = parseTimeEntries(period.text).filter((item) => item.timeMinutes !== null);
    for (let index = 1; index < entries.length; index += 1) {
      const prev = entries[index - 1];
      const curr = entries[index];
      if ((curr.timeMinutes ?? 0) <= (prev.timeMinutes ?? 0)) {
        conflicts.push({
          id: `${period.key}-time-${index}`,
          type: 'time_conflict',
          severity: 'high',
          title: `${period.label} time conflict`,
          description: `Detected timeline overlap or reverse order (${prev.raw} -> ${curr.raw}).`,
          suggestion: 'Sort by time and leave at least 30 minutes buffer between items.',
        });
        break;
      }
    }
  });

  if (distanceM && distanceM > 30000) {
    conflicts.push({
      id: 'distance-long',
      type: 'long_distance',
      severity: distanceM > 50000 ? 'high' : 'medium',
      title: 'Route too long',
      description: `Daily route is about ${(distanceM / 1000).toFixed(1)} km.`,
      suggestion: 'Split into two days or remove 1-2 far points.',
    });
  }

  const eveningEntries = parseTimeEntries(day.evening);
  const closingKeywords = /(博物馆|美术馆|纪念馆|景区|公园|寺|塔|宫|图书馆|museum|park|gallery)/i;
  const closeRiskEntry = eveningEntries.find((entry) => (entry.timeMinutes ?? 0) >= 1110 && closingKeywords.test(entry.content));
  if (closeRiskEntry) {
    conflicts.push({
      id: 'closing-risk-evening',
      type: 'closing_risk',
      severity: 'medium',
      title: 'Potential closing-time risk',
      description: `Late visit may hit closing window: ${closeRiskEntry.raw}`,
      suggestion: 'Move this point to afternoon; keep evening for night-view or dining.',
    });
  }

  return conflicts;
}

export function applyConflictFixes(day: DayPlanCard, conflicts: ItineraryConflict[]): DayPlanCard {
  if (conflicts.length === 0) return day;

  function normalizePeriod(text: string): string {
    const entries = parseTimeEntries(text);
    const timed = entries
      .filter((entry) => entry.timeMinutes !== null)
      .sort((a, b) => (a.timeMinutes ?? 0) - (b.timeMinutes ?? 0));
    const untimed = entries.filter((entry) => entry.timeMinutes === null);

    let cursor = -1;
    const normalizedTimed = timed.map((entry) => {
      const nextValue = Math.max(entry.timeMinutes ?? 0, cursor + 30);
      cursor = nextValue;
      return `${formatTime(nextValue)} ${entry.content}`.trim();
    });

    return [...normalizedTimed, ...untimed.map((entry) => entry.content)].filter(Boolean).join('；');
  }

  let nextMorning = day.morning;
  let nextAfternoon = day.afternoon;
  let nextEvening = day.evening;
  const nextTips = [...day.tips];

  if (conflicts.some((item) => item.type === 'time_conflict')) {
    nextMorning = normalizePeriod(nextMorning);
    nextAfternoon = normalizePeriod(nextAfternoon);
    nextEvening = normalizePeriod(nextEvening);
    nextTips.unshift('Auto-fix: timeline sorted by time with safety buffers.');
  }

  if (conflicts.some((item) => item.type === 'long_distance')) {
    nextTips.unshift('Suggestion: reduce far points or split this day.');
  }

  if (conflicts.some((item) => item.type === 'closing_risk')) {
    nextTips.unshift('Suggestion: move closing-risk places to afternoon.');
  }

  return {
    ...day,
    morning: nextMorning,
    afternoon: nextAfternoon,
    evening: nextEvening,
    tips: dedupeStrings(nextTips).slice(0, 8),
  };
}
