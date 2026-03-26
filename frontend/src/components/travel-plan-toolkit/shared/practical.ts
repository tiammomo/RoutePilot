'use client';

import type { PracticalInfoCard } from '@/utils/travelPlan';

export function practicalToneStyle(
  tone: PracticalInfoCard['tone']
): { background: string; border: string; color: string } {
  if (tone === 'good') return { background: '#ecfdf5', border: '#a7f3d0', color: '#065f46' };
  if (tone === 'warn') return { background: '#fff7ed', border: '#fed7aa', color: '#9a3412' };
  return { background: '#f8fafc', border: '#cbd5e1', color: '#334155' };
}

export function practicalToneLabel(tone: PracticalInfoCard['tone']): string {
  if (tone === 'good') return '建议';
  if (tone === 'warn') return '注意';
  return '常规';
}
