'use client';

export type BudgetMode = 'saving' | 'balanced' | 'comfort';

export interface CompareRow {
  key: string;
  metric: string;
  values: Record<string, string>;
}

export interface QuickRefineAction {
  key: string;
  label: string;
  prompt: string;
}
