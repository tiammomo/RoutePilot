'use client';

import { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import html2canvas from 'html2canvas';
import type React from 'react';
import type { RoutePreviewResponse, SubagentEvent, TripPlanArtifact } from '@/types';
import { mapClient, shareClient } from '@/services/api';
import { buildRoutePoints, reorderByDistance } from '@/utils/travelPlan';
import type { DayPlanCard, PlanVariant, SpotDecisionInfo } from '@/utils/travelPlan';
import { buildArtifactSharePayload, type QuickRefineAction } from './shared';
import { buildFavoritesQuickRefineAction, buildVariantContinuePrompt } from './actionPrompts';

interface UseTravelPlanToolkitActionsOptions {
  artifact?: TripPlanArtifact | null;
  baseCards: DayPlanCard[];
  content: string;
  exportRef: React.RefObject<HTMLDivElement | null>;
  onContinuePrompt?: (prompt: string) => void;
  setCards: React.Dispatch<React.SetStateAction<DayPlanCard[]>>;
  subagentEvents?: SubagentEvent[];
}

export function useTravelPlanToolkitActions({
  artifact = null,
  baseCards,
  content,
  exportRef,
  onContinuePrompt,
  setCards,
  subagentEvents = [],
}: UseTravelPlanToolkitActionsOptions) {
  const { message } = App.useApp();
  const [favoriteSpots, setFavoriteSpots] = useState<Record<string, SpotDecisionInfo>>({});
  const [routeByDay, setRouteByDay] = useState<Record<string, RoutePreviewResponse | undefined>>({});
  const [routeLoadingDay, setRouteLoadingDay] = useState<string | null>(null);

  useEffect(() => {
    setRouteByDay({});
  }, [baseCards]);

  const favoriteSpotList = useMemo(() => Object.values(favoriteSpots), [favoriteSpots]);

  const runQuickRefine = (action: QuickRefineAction) => {
    if (!onContinuePrompt) {
      message.info('当前会话不支持继续优化。');
      return;
    }
    onContinuePrompt(action.prompt);
    message.success(`已填入“${action.label}”优化指令`);
  };

  const handleChooseVariant = (variant: PlanVariant) => {
    if (!onContinuePrompt) {
      message.info('当前会话不支持一键继续细化。');
      return;
    }

    onContinuePrompt(buildVariantContinuePrompt(variant));
    message.success(`已选择 ${variant.title}，可继续细化`);
  };

  const handleBuildFromFavorites = () => {
    if (favoriteSpotList.length === 0) {
      message.info('当前候选池为空。');
      return;
    }
    runQuickRefine(buildFavoritesQuickRefineAction(favoriteSpotList));
  };

  const handleToggleFavoriteSpot = (spot: SpotDecisionInfo) => {
    setFavoriteSpots((prev) => {
      if (prev[spot.name]) {
        const next = { ...prev };
        delete next[spot.name];
        return next;
      }
      return { ...prev, [spot.name]: spot };
    });
  };

  const handleFetchRoute = async (dayKey: string, day: DayPlanCard) => {
    if (day.spots.length < 2) {
      message.warning('当天景点少于 2 个，无法生成路线。');
      return;
    }

    try {
      setRouteLoadingDay(dayKey);
      const result = await mapClient.getRoutePreview({ spots: day.spots.slice(0, 12), provider: 'amap' });
      setRouteByDay((prev) => ({ ...prev, [dayKey]: result }));
      message.success(`已获取 ${day.dayLabel} 真实路线`);
    } catch (error) {
      message.error(`路线获取失败：${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      setRouteLoadingDay(null);
    }
  };

  const handleReorderByDistance = (dayKey: string, dayIndex: number, day: DayPlanCard) => {
    const route = routeByDay[dayKey];
    const orderedSpots = route?.points?.length
      ? route.points.map((point) => point.name)
      : reorderByDistance(buildRoutePoints(day.spots)).map((point) => point.name);

    setCards((prev) => prev.map((item, index) => (index === dayIndex ? { ...item, spots: orderedSpots } : item)));
    message.success(`${day.dayLabel} 已按距离重排`);
  };

  const handleExportImage = async () => {
    if (!exportRef.current) return;
    try {
      const canvas = await html2canvas(exportRef.current, {
        scale: 2,
        backgroundColor: '#ffffff',
        useCORS: true,
      });
      const dataUrl = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = dataUrl;
      link.download = `travel-plan-${new Date().toISOString().slice(0, 10)}.png`;
      link.click();
      message.success('已导出长图');
    } catch (error) {
      message.error(`导出失败：${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  const handleShare = async () => {
    try {
      const payload = buildArtifactSharePayload(artifact, subagentEvents, content);
      const result = await shareClient.createShareLink({
        title: payload.title,
        content: payload.content,
      });
      await navigator.clipboard.writeText(result.share_url);
      message.success('分享短链已复制到剪贴板');
    } catch (error) {
      message.error(`分享失败：${error instanceof Error ? error.message : '未知错误'}`);
    }
  };

  return {
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
  };
}
