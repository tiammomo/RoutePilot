'use client';

import type { ItineraryConflict } from '@/utils/travelPlan';

export function formatDistance(distanceM: number | undefined): string {
  if (!distanceM || distanceM <= 0) return '-';
  return `${(distanceM / 1000).toFixed(1)} km`;
}

export function riskColor(severity: ItineraryConflict['severity']): string {
  if (severity === 'high') return '#dc2626';
  if (severity === 'medium') return '#d97706';
  return '#b45309';
}
