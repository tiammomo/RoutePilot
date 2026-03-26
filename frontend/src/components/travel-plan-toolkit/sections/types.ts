'use client';

import type { DayPlanCard } from '@/utils/travelPlan';

export interface CardEntry {
  day: DayPlanCard;
  dayIndex: number;
  dayKey: string;
}
