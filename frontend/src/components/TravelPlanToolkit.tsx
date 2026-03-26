'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { App, Card, Tabs } from 'antd';
import {
  CheckSquareOutlined,
  CompassOutlined,
  HeartOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  FundOutlined,
} from '@ant-design/icons';
import type { Message, SubagentEvent, TripPlanArtifact } from '@/types';
import { hasArtifactData } from '@/utils/agentArtifacts';
import {
  applyConflictFixes,
  buildChecklist,
  buildConfidenceSummary,
  buildPracticalInfoCards,
  buildReminders,
  detectDayConflicts,
  getBudgetProjection,
  parseDayPlanCards,
  parsePlanVariants,
} from '@/utils/travelPlan';
import type { DayPlanCard } from '@/utils/travelPlan';
import type { QuickRefineAction } from './travel-plan-toolkit/shared';
import {
  ToolkitChecklistTab,
  ToolkitCompareTab,
  ToolkitConflictsTab,
  ToolkitFavoritesTab,
  ToolkitItineraryTab,
  ToolkitOverviewPanel,
  ToolkitPracticalTab,
  ToolkitRemindersTab,
} from './travel-plan-toolkit/sections';
import { looksLikeItineraryContent, modeToSliderValue, type BudgetMode } from './travel-plan-toolkit/shared';
import { useTravelPlanToolkitActions } from './travel-plan-toolkit/useTravelPlanToolkitActions';

interface TravelPlanToolkitProps {
  messageId: string;
  content: string;
  diagnostics?: Message['diagnostics'];
  artifact?: TripPlanArtifact | null;
  subagentEvents?: SubagentEvent[];
  onContinuePrompt?: (prompt: string) => void;
}

const QUICK_REFINE_ACTIONS: QuickRefineAction[] = [
  { key: 'cheaper', label: '换成更省钱', prompt: '请基于当前方案改成更省钱版本，优先保留核心体验，减少高价项目，并重算预算。' },
  { key: 'easy', label: '少走路版', prompt: '请基于当前方案改成少走路版本，压缩跨区移动，增加打车衔接和休息点。' },
  { key: 'rainy', label: '下雨天重排', prompt: '请把当前方案改成下雨天可执行版本，优先室内点位，并替换不适合雨天的安排。' },
  { key: 'family', label: '加亲子备选', prompt: '请在当前方案基础上增加亲子友好备选点和午休/室内 fallback。' },
];

type ToolkitTabItem = NonNullable<React.ComponentProps<typeof Tabs>['items']>[number];

const TravelPlanToolkit: React.FC<TravelPlanToolkitProps> = ({
  messageId,
  content,
  diagnostics,
  artifact = null,
  subagentEvents = [],
  onContinuePrompt,
}) => {
  const { message } = App.useApp();
  const exportRef = useRef<HTMLDivElement | null>(null);

  const baseCards = useMemo(() => parseDayPlanCards(content), [content]);
  const variants = useMemo(() => parsePlanVariants(content), [content]);
  const checklist = useMemo(() => buildChecklist(content), [content]);
  const reminders = useMemo(() => buildReminders(), []);
  const confidence = useMemo(() => buildConfidenceSummary(diagnostics), [diagnostics]);
  const practicalInfo = useMemo(() => buildPracticalInfoCards(content), [content]);

  const [cards, setCards] = useState<DayPlanCard[]>(baseCards);
  const [budgetMode, setBudgetMode] = useState<BudgetMode>('balanced');
  const [completedChecklist, setCompletedChecklist] = useState<Record<string, boolean>>({});
  const [expandedPeriods, setExpandedPeriods] = useState<Record<string, boolean>>({});
  const [expandedTips, setExpandedTips] = useState<Record<string, boolean>>({});

  const artifactAvailable = hasArtifactData(artifact);

  useEffect(() => {
    setCards(baseCards);
    setExpandedPeriods({});
    setExpandedTips({});
  }, [baseCards]);

  const {
    favoriteSpots,
    favoriteSpotList,
    routeByDay,
    routeLoadingDay,
    runQuickRefine,
    handleBuildFromFavorites,
    handleChooseVariant,
    handleToggleFavoriteSpot,
    handleFetchRoute,
    handleReorderByDistance,
    handleExportImage,
    handleShare,
  } = useTravelPlanToolkitActions({
    artifact,
    baseCards,
    content,
    exportRef,
    onContinuePrompt,
    setCards,
    subagentEvents,
  });

  const cardEntries = useMemo(
    () =>
      cards.map((day, dayIndex) => ({
        day,
        dayIndex,
        dayKey: `day-${dayIndex + 1}`,
      })),
    [cards]
  );

  const totalBaseBudget = useMemo(() => cards.reduce((sum, day) => sum + day.baseBudget, 0), [cards]);
  const budgetProjection = useMemo(() => {
    const dayCount = Math.max(cards.length, 1);
    return getBudgetProjection(totalBaseBudget / dayCount, dayCount, modeToSliderValue(budgetMode));
  }, [budgetMode, cards.length, totalBaseBudget]);

  const familyBudget = Math.round(budgetProjection.totalBudget * 2.4);
  const childFriendlyBudget = Math.round(budgetProjection.totalBudget * 1.7);
  const hasItineraryContent = useMemo(() => looksLikeItineraryContent(content, baseCards), [baseCards, content]);

  const conflictMap = useMemo(() => {
    const map = new Map<string, ReturnType<typeof detectDayConflicts>>();
    cardEntries.forEach(({ day, dayKey }) => {
      const distanceM = routeByDay[dayKey]?.distance_m;
      map.set(dayKey, detectDayConflicts(day, distanceM));
    });
    return map;
  }, [cardEntries, routeByDay]);

  const totalConflicts = useMemo(
    () => Array.from(conflictMap.values()).reduce((sum, list) => sum + list.length, 0),
    [conflictMap]
  );

  if (cards.length === 0 && !artifactAvailable) return null;

  const handleTogglePeriod = (periodKey: string) => {
    setExpandedPeriods((prev) => ({ ...prev, [periodKey]: !prev[periodKey] }));
  };

  const handleToggleTips = (dayKey: string) => {
    setExpandedTips((prev) => ({ ...prev, [dayKey]: !prev[dayKey] }));
  };

  const handleOneClickFix = (dayKey: string, dayIndex: number, day: DayPlanCard) => {
    const conflicts = conflictMap.get(dayKey) || [];
    if (conflicts.length === 0) {
      return;
    }

    const fixed = applyConflictFixes(day, conflicts);
    setCards((prev) => prev.map((item, index) => (index === dayIndex ? fixed : item)));
  };

  const handleToggleChecklist = (itemId: string, checked: boolean) => {
    setCompletedChecklist((prev) => ({ ...prev, [itemId]: checked }));
  };

  const handleOneClickFixWithFeedback = (dayKey: string, dayIndex: number, day: DayPlanCard) => {
    const conflicts = conflictMap.get(dayKey) || [];
    if (conflicts.length === 0) {
      message.info('当前无冲突，无需修复。');
      return;
    }

    handleOneClickFix(dayKey, dayIndex, day);
    message.success(`${day.dayLabel} 已应用修复建议`);
  };

  const tabItems: ToolkitTabItem[] = [];

  if (hasItineraryContent) {
    tabItems.push({
      key: 'itinerary',
      label: '每日行程',
      icon: <CompassOutlined />,
      children: (
        <ToolkitItineraryTab
          messageId={messageId}
          exportRef={exportRef}
          budgetMode={budgetMode}
          budgetProjection={budgetProjection}
          familyBudget={familyBudget}
          childFriendlyBudget={childFriendlyBudget}
          confidence={confidence}
          cardEntries={cardEntries}
          conflictMap={conflictMap}
          favoriteSpots={favoriteSpots}
          expandedPeriods={expandedPeriods}
          expandedTips={expandedTips}
          quickRefineActions={QUICK_REFINE_ACTIONS}
          routeByDay={routeByDay}
          routeLoadingDay={routeLoadingDay}
          onBudgetModeChange={setBudgetMode}
          onExportImage={handleExportImage}
          onFetchRoute={handleFetchRoute}
          onOneClickFix={handleOneClickFixWithFeedback}
          onQuickRefine={runQuickRefine}
          onReorderByDistance={handleReorderByDistance}
          onShare={handleShare}
          onToggleFavoriteSpot={handleToggleFavoriteSpot}
          onTogglePeriod={handleTogglePeriod}
          onToggleTips={handleToggleTips}
        />
      ),
    });
  }

  tabItems.push({
      key: 'compare',
      label: '多方案对比',
      icon: <FundOutlined />,
      children: <ToolkitCompareTab variants={variants} onChooseVariant={handleChooseVariant} />,
    });

  if (hasItineraryContent) {
    tabItems.push({
      key: 'conflicts',
      label: '冲突检测',
      icon: <ReloadOutlined />,
      children: (
        <ToolkitConflictsTab
          cardEntries={cardEntries}
          conflictMap={conflictMap}
          messageId={messageId}
          totalConflicts={totalConflicts}
          onOneClickFix={handleOneClickFixWithFeedback}
        />
      ),
    });

    tabItems.push({
      key: 'favorites',
      label: '候选池',
      icon: <HeartOutlined />,
      children: (
        <ToolkitFavoritesTab
          canBuildFromFavorites={Boolean(onContinuePrompt)}
          favoriteSpotList={favoriteSpotList}
          onBuildFromFavorites={handleBuildFromFavorites}
          onToggleFavoriteSpot={handleToggleFavoriteSpot}
        />
      ),
    });
  }

  tabItems.push(
    {
      key: 'practical',
      label: '实用信息',
      icon: <InfoCircleOutlined />,
      children: <ToolkitPracticalTab messageId={messageId} practicalInfo={practicalInfo} />,
    },
    {
      key: 'checklist',
      label: '执行清单',
      icon: <CheckSquareOutlined />,
      children: (
        <ToolkitChecklistTab
          checklist={checklist}
          completedChecklist={completedChecklist}
          messageId={messageId}
          onToggleChecklist={handleToggleChecklist}
        />
      ),
    },
    {
      key: 'reminders',
      label: '出发提醒',
      icon: <ReloadOutlined />,
      children: <ToolkitRemindersTab messageId={messageId} reminders={reminders} />,
    },
  );

  return (
    <Card
      size="small"
      style={{ marginTop: 12, borderRadius: 12, border: '1px solid #e2e8f0', background: '#f8fafc' }}
      styles={{ body: { padding: 12 } }}
    >
      {artifactAvailable && artifact && (
        <ToolkitOverviewPanel
          artifact={artifact}
          subagentEvents={subagentEvents}
        />
      )}
      <Tabs size="small" items={tabItems} />
    </Card>
  );
};

export default TravelPlanToolkit;
