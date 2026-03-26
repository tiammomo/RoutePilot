'use client';

import type { DayPlanCard } from '@/utils/travelPlan';

export function looksLikeItineraryContent(content: string, cards: DayPlanCard[]): boolean {
  if (cards.length >= 2) return true;
  if (/(上午|下午|晚上|预算|小贴士|tips|day\s*\d+|第.{1,4}天|方案|路线|景点)/i.test(content)) return true;
  return false;
}
