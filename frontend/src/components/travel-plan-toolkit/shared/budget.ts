'use client';

import type { BudgetMode } from './types';

export function sliderToMode(value: number): BudgetMode {
  if (value <= 33) return 'saving';
  if (value >= 67) return 'comfort';
  return 'balanced';
}

export function modeToSliderValue(mode: BudgetMode): number {
  if (mode === 'saving') return 10;
  if (mode === 'comfort') return 90;
  return 50;
}
