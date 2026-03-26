'use client';

import type { ReminderItem } from '@/utils/travelPlan';

export function reminderPhaseMeta(phase: ReminderItem['phase']): { color: string; subtitle: string } {
  if (phase === 'T-1') return { color: 'volcano', subtitle: '出发前一天' };
  if (phase === 'T-3') return { color: 'cyan', subtitle: '出发前三天' };
  return { color: 'blue', subtitle: '出发前一周' };
}
