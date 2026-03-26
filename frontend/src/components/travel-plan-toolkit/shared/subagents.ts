'use client';

export function subagentLabel(name: string): string {
  if (name === 'planning') return '规划';
  if (name === 'research') return '研究';
  if (name === 'budget') return '预算';
  if (name === 'verification') return '校验';
  return name;
}
