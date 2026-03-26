'use client';

import React from 'react';
import type { RoutePreviewResponse } from '@/types';
import type {
  BudgetProjection,
  ConfidenceSummary,
  DayPlanCard,
  ItineraryConflict,
  SpotDecisionInfo,
} from '@/utils/travelPlan';
import type { BudgetMode, QuickRefineAction } from '../shared';
import type { CardEntry } from './types';
import { ItineraryBudgetPanel } from './itinerary/ItineraryBudgetPanel';
import { ItineraryDayCard } from './itinerary/ItineraryDayCard';

interface ToolkitItineraryTabProps {
  messageId: string;
  exportRef: React.RefObject<HTMLDivElement | null>;
  budgetMode: BudgetMode;
  budgetProjection: BudgetProjection;
  familyBudget: number;
  childFriendlyBudget: number;
  confidence: ConfidenceSummary;
  cardEntries: CardEntry[];
  conflictMap: Map<string, ItineraryConflict[]>;
  favoriteSpots: Record<string, SpotDecisionInfo>;
  expandedPeriods: Record<string, boolean>;
  expandedTips: Record<string, boolean>;
  quickRefineActions: QuickRefineAction[];
  routeByDay: Record<string, RoutePreviewResponse | undefined>;
  routeLoadingDay: string | null;
  onBudgetModeChange: (mode: BudgetMode) => void;
  onExportImage: () => void;
  onFetchRoute: (dayKey: string, day: DayPlanCard) => void;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
  onQuickRefine: (action: QuickRefineAction) => void;
  onReorderByDistance: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
  onShare: () => void;
  onToggleFavoriteSpot: (spot: SpotDecisionInfo) => void;
  onTogglePeriod: (periodKey: string) => void;
  onToggleTips: (dayKey: string) => void;
}

export const ToolkitItineraryTab: React.FC<ToolkitItineraryTabProps> = ({
  messageId: _messageId,
  exportRef,
  budgetMode,
  budgetProjection,
  familyBudget,
  childFriendlyBudget,
  confidence,
  cardEntries,
  conflictMap,
  favoriteSpots,
  expandedPeriods,
  expandedTips,
  quickRefineActions,
  routeByDay,
  routeLoadingDay,
  onBudgetModeChange,
  onExportImage,
  onFetchRoute,
  onOneClickFix,
  onQuickRefine,
  onReorderByDistance,
  onShare,
  onToggleFavoriteSpot,
  onTogglePeriod,
  onToggleTips,
}) => (
  <div ref={exportRef} style={{ display: 'grid', gap: 12 }}>
    <ItineraryBudgetPanel
      budgetMode={budgetMode}
      budgetProjection={budgetProjection}
      childFriendlyBudget={childFriendlyBudget}
      confidence={confidence}
      familyBudget={familyBudget}
      onBudgetModeChange={onBudgetModeChange}
      onExportImage={onExportImage}
      onQuickRefine={onQuickRefine}
      onShare={onShare}
      quickRefineActions={quickRefineActions}
    />

    {cardEntries.map(({ day, dayIndex, dayKey }) => (
      <ItineraryDayCard
        key={dayKey}
        conflicts={conflictMap.get(dayKey) || []}
        day={day}
        dayIndex={dayIndex}
        dayKey={dayKey}
        expandedPeriods={expandedPeriods}
        expandedTips={expandedTips}
        favoriteSpots={favoriteSpots}
        onFetchRoute={onFetchRoute}
        onOneClickFix={onOneClickFix}
        onReorderByDistance={onReorderByDistance}
        onToggleFavoriteSpot={onToggleFavoriteSpot}
        onTogglePeriod={onTogglePeriod}
        onToggleTips={onToggleTips}
        route={routeByDay[dayKey]}
        routeLoadingDay={routeLoadingDay}
      />
    ))}
  </div>
);
