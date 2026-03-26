'use client';

import React from 'react';
import { Card } from 'antd';
import type { DayPlanCard, ItineraryConflict } from '@/utils/travelPlan';
import { ConflictCardContent } from './ConflictCardContent';

interface DayConflictCardProps {
  conflicts: ItineraryConflict[];
  day: DayPlanCard;
  dayIndex: number;
  dayKey: string;
  messageId: string;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
}

export const DayConflictCard: React.FC<DayConflictCardProps> = ({
  conflicts,
  day,
  dayIndex,
  dayKey,
  messageId,
  onOneClickFix,
}) => (
  <Card key={`${messageId}-conflict-${dayKey}`} size="small" title={day.dayLabel}>
    <ConflictCardContent conflicts={conflicts} day={day} dayIndex={dayIndex} dayKey={dayKey} onOneClickFix={onOneClickFix} />
  </Card>
);
