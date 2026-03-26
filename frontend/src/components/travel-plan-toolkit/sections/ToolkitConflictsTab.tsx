'use client';

import React from 'react';
import type { DayPlanCard, ItineraryConflict } from '@/utils/travelPlan';
import type { CardEntry } from './types';
import { ConflictSummaryTag } from './conflicts-tab/ConflictSummaryTag';
import { DayConflictCard } from './conflicts-tab/DayConflictCard';

interface ToolkitConflictsTabProps {
  cardEntries: CardEntry[];
  conflictMap: Map<string, ItineraryConflict[]>;
  messageId: string;
  totalConflicts: number;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
}

export const ToolkitConflictsTab: React.FC<ToolkitConflictsTabProps> = ({
  cardEntries,
  conflictMap,
  messageId,
  totalConflicts,
  onOneClickFix,
}) => (
  <div style={{ display: 'grid', gap: 10 }}>
    <ConflictSummaryTag totalConflicts={totalConflicts} />
    {cardEntries.map(({ day, dayIndex, dayKey }) => (
      <DayConflictCard
        key={`${messageId}-conflict-${dayKey}`}
        conflicts={conflictMap.get(dayKey) || []}
        day={day}
        dayIndex={dayIndex}
        dayKey={dayKey}
        messageId={messageId}
        onOneClickFix={onOneClickFix}
      />
    ))}
  </div>
);
