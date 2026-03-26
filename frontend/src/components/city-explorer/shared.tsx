'use client';

import type { CityDetail, CitySummary } from '@/types';

export type QuickFilterKey = 'weekend' | 'budget' | 'family' | 'easywalk' | 'rainy' | 'food';

export interface QuickFilterOption {
  key: QuickFilterKey;
  label: string;
}

export interface CuratedPromptOption {
  label: string;
  hint: string;
  prompt: string;
  borderColor: string;
  background: string;
}

export interface DerivedCityProfile {
  budgetLevel: 'low' | 'medium' | 'high';
  tripDuration: string;
  walkIntensity: 'low' | 'medium' | 'high';
  rainFriendly: boolean;
  familyFriendly: boolean;
  foodFriendly: boolean;
  styleLabel: string;
  recommendation: string;
}

export interface CompareTableRow {
  key: string;
  metric: string;
  values: Record<string, string>;
}

export const QUICK_FILTERS: QuickFilterOption[] = [
  { key: 'weekend', label: '周末可去' },
  { key: 'budget', label: '预算友好' },
  { key: 'family', label: '亲子友好' },
  { key: 'easywalk', label: '少走路' },
  { key: 'rainy', label: '雨天也能玩' },
  { key: 'food', label: '美食优先' },
];

export const CURATED_PROMPTS: CuratedPromptOption[] = [
  {
    label: '周末快闪',
    hint: '低预算，出行轻松。',
    prompt: '请推荐适合周末两天出发、预算 1500 元内、地铁友好的真实旅行城市，并给出选择理由。',
    borderColor: '#bfdbfe',
    background: 'linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%)',
  },
  {
    label: '亲子省心',
    hint: '少走路，雨天也稳。',
    prompt: '请推荐亲子友好、少走路、下雨也不容易废行程的真实旅行城市，并说明为什么适合。',
    borderColor: '#c7d2fe',
    background: 'linear-gradient(180deg, #fbfbff 0%, #f3f4ff 100%)',
  },
  {
    label: '预算吃好',
    hint: '好吃不贵，节奏轻松。',
    prompt: '请推荐预算友好、以美食为主、景点不需要太密集的城市，并做简短对比。',
    borderColor: '#bae6fd',
    background: 'linear-gradient(180deg, #f8feff 0%, #edf9ff 100%)',
  },
];

const QUICK_FILTER_LABEL_MAP = Object.fromEntries(QUICK_FILTERS.map((item) => [item.key, item.label])) as Record<
  QuickFilterKey,
  string
>;

function includesAny(source: string[], patterns: string[]): boolean {
  const text = source.join(' ').toLowerCase();
  return patterns.some((pattern) => text.includes(pattern.toLowerCase()));
}

export function getQuickFilterLabel(filterKey: QuickFilterKey): string {
  return QUICK_FILTER_LABEL_MAP[filterKey];
}

export function buildCityProfile(city: CitySummary | CityDetail): DerivedCityProfile {
  const budgetValue = city.avg_budget_per_day || 0;
  const tags = city.tags || [];
  const budgetLevel: DerivedCityProfile['budgetLevel'] =
    budgetValue <= 500 ? 'low' : budgetValue <= 900 ? 'medium' : 'high';

  return {
    budgetLevel,
    tripDuration: city.trip_duration || '2-3天',
    walkIntensity: city.walk_intensity || 'medium',
    rainFriendly: city.rain_friendly ?? includesAny(tags, ['博物馆', '室内', '文化']),
    familyFriendly: city.family_friendly ?? includesAny(tags, ['亲子', '家庭', '乐园']),
    foodFriendly: city.food_friendly ?? includesAny(tags, ['美食', '小吃', '夜市']),
    styleLabel: city.style_label || '综合体验',
    recommendation: city.editorial_note?.trim() || city.description?.trim() || `${city.name}适合做轻量旅行。`,
  };
}

export function budgetLabel(level: DerivedCityProfile['budgetLevel']): string {
  if (level === 'low') return '预算友好';
  if (level === 'high') return '预算偏高';
  return '预算均衡';
}

export function walkLabel(level: DerivedCityProfile['walkIntensity']): string {
  if (level === 'low') return '少走路';
  if (level === 'high') return '步行偏多';
  return '步行适中';
}

export function boolLabel(value: boolean): string {
  return value ? '友好' : '一般';
}

export function foodLabel(value: boolean): string {
  return value ? '高' : '中';
}

export function seasonLabel(seasons: string[]): string {
  return seasons.slice(0, 2).join(' / ') || '四季皆可';
}

export function buildPlanPrompt(cityName: string): string {
  return `请为我规划${cityName} 3 天旅行计划，包含每日时间轴、预算估算、住宿建议、拍照点位、下雨天备选和适合第一次去的顺序安排。`;
}

export function buildComparePrompt(cityNames: string[]): string {
  return `请比较这些城市作为下一次旅行目的地的差异：${cityNames.join('、')}。请从预算、适合天数、步行强度、亲子友好度、雨天可玩度、核心景点真实性和整体旅行氛围做并排对比，并给出推荐结论。`;
}
