'use client';

import { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import html2canvas from 'html2canvas';
import type React from 'react';
import type { ExecutionReceipt, RoutePreviewResponse, SubagentEvent, TripPlanArtifact } from '@/types';
import { mapClient, shareClient } from '@/services/api';
import { buildRoutePoints, reorderByDistance } from '@/utils/travelPlan';
import type { DayPlanCard, PlanVariant, SpotDecisionInfo } from '@/utils/travelPlan';
import { buildArtifactDeliveryBundle, buildArtifactDeliveryDescriptor, type QuickRefineAction } from './shared';
import { buildArtifactAwarePrompt, buildFavoritesQuickRefineAction, buildVariantContinuePrompt } from './actionPrompts';

interface UseTravelPlanToolkitActionsOptions {
  artifact?: TripPlanArtifact | null;
  baseCards: DayPlanCard[];
  content: string;
  executionReceipt?: ExecutionReceipt | null;
  exportRef: React.RefObject<HTMLDivElement | null>;
  onContinuePrompt?: (prompt: string) => void;
  setCards: React.Dispatch<React.SetStateAction<DayPlanCard[]>>;
  subagentEvents?: SubagentEvent[];
}

export function useTravelPlanToolkitActions({
  artifact = null,
  baseCards,
  content,
  executionReceipt = null,
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
    onContinuePrompt(buildArtifactAwarePrompt(action.prompt, artifact));
    message.success(`已填入“${action.label}”优化指令`);
  };

  const handleChooseVariant = (variant: PlanVariant) => {
    if (!onContinuePrompt) {
      message.info('当前会话不支持一键继续细化。');
      return;
    }

    onContinuePrompt(buildVariantContinuePrompt(variant, artifact));
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
    let exportShell: HTMLDivElement | null = null;

    try {
      const descriptor = buildArtifactDeliveryDescriptor(artifact, subagentEvents, { fallbackContent: content });
      const exportedAt = new Intl.DateTimeFormat('zh-CN', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date());

      exportShell = document.createElement('div');
      exportShell.style.position = 'fixed';
      exportShell.style.left = '-10000px';
      exportShell.style.top = '0';
      exportShell.style.width = '920px';
      exportShell.style.padding = '28px';
      exportShell.style.background = 'linear-gradient(180deg, #f8fbff 0%, #ffffff 28%, #f8fafc 100%)';
      exportShell.style.boxSizing = 'border-box';

      const header = document.createElement('div');
      header.style.display = 'grid';
      header.style.gap = '12px';
      header.style.padding = '20px 22px';
      header.style.marginBottom = '18px';
      header.style.borderRadius = '20px';
      header.style.background = 'linear-gradient(135deg, #082f49 0%, #0f766e 100%)';
      header.style.color = '#ffffff';

      const headerTop = document.createElement('div');
      headerTop.style.display = 'flex';
      headerTop.style.justifyContent = 'space-between';
      headerTop.style.alignItems = 'center';
      headerTop.style.gap = '16px';

      const brand = document.createElement('div');
      brand.style.display = 'grid';
      brand.style.gap = '4px';

      const brandTitle = document.createElement('div');
      brandTitle.textContent = 'Moyuan Travel Agent';
      brandTitle.style.fontSize = '16px';
      brandTitle.style.fontWeight = '700';

      const brandSubtitle = document.createElement('div');
      brandSubtitle.textContent = 'AI 旅行方案导出卡片';
      brandSubtitle.style.fontSize = '12px';
      brandSubtitle.style.opacity = '0.82';

      brand.appendChild(brandTitle);
      brand.appendChild(brandSubtitle);

      const meta = document.createElement('div');
      meta.style.textAlign = 'right';

      const metaTitle = document.createElement('div');
      metaTitle.textContent = descriptor.title;
      metaTitle.style.fontSize = '20px';
      metaTitle.style.fontWeight = '700';

      const metaTime = document.createElement('div');
      metaTime.textContent = `导出时间 ${exportedAt}`;
      metaTime.style.fontSize = '12px';
      metaTime.style.opacity = '0.82';

      meta.appendChild(metaTitle);
      meta.appendChild(metaTime);

      headerTop.appendChild(brand);
      headerTop.appendChild(meta);
      header.appendChild(headerTop);

      if (descriptor.summary && !descriptor.summaryLines.includes(descriptor.summary)) {
        const summaryText = document.createElement('div');
        summaryText.textContent = descriptor.summary;
        summaryText.style.fontSize = '13px';
        summaryText.style.lineHeight = '1.7';
        summaryText.style.opacity = '0.92';
        header.appendChild(summaryText);
      }

      if (descriptor.summaryLines.length > 0) {
        const summaryList = document.createElement('div');
        summaryList.style.display = 'grid';
        summaryList.style.gap = '6px';
        summaryList.style.padding = '14px 16px';
        summaryList.style.borderRadius = '16px';
        summaryList.style.background = 'rgba(255,255,255,0.12)';

        descriptor.summaryLines.forEach((line) => {
          const summaryLine = document.createElement('div');
          summaryLine.textContent = line;
          summaryLine.style.fontSize = '13px';
          summaryLine.style.lineHeight = '1.5';
          summaryList.appendChild(summaryLine);
        });

        header.appendChild(summaryList);
      }

      if (descriptor.htmlSections.length > 0) {
        const sectionGrid = document.createElement('div');
        sectionGrid.style.display = 'grid';
        sectionGrid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(200px, 1fr))';
        sectionGrid.style.gap = '10px';

        descriptor.htmlSections.forEach((section) => {
          const sectionCard = document.createElement('div');
          sectionCard.style.padding = '12px 14px';
          sectionCard.style.borderRadius = '14px';
          sectionCard.style.background = 'rgba(255,255,255,0.12)';

          const sectionTitle = document.createElement('div');
          sectionTitle.textContent = section.title;
          sectionTitle.style.fontSize = '12px';
          sectionTitle.style.fontWeight = '700';
          sectionTitle.style.marginBottom = '6px';
          sectionCard.appendChild(sectionTitle);

          section.items.slice(0, 3).forEach((item) => {
            const sectionItem = document.createElement('div');
            sectionItem.textContent = `• ${item}`;
            sectionItem.style.fontSize = '12px';
            sectionItem.style.lineHeight = '1.5';
            sectionItem.style.opacity = '0.88';
            sectionCard.appendChild(sectionItem);
          });

          sectionGrid.appendChild(sectionCard);
        });

        header.appendChild(sectionGrid);
      }

      const clonedCard = exportRef.current.cloneNode(true) as HTMLDivElement;
      clonedCard.style.maxWidth = '100%';

      exportShell.appendChild(header);
      exportShell.appendChild(clonedCard);
      document.body.appendChild(exportShell);

      const canvas = await html2canvas(exportShell, {
        scale: 2,
        backgroundColor: '#f8fbff',
        useCORS: true,
      });
      const dataUrl = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = dataUrl;
      link.download = `${descriptor.filenameBase}-${new Date().toISOString().slice(0, 10)}.png`;
      link.click();
      message.success('已导出旅行方案图片');
    } catch (error) {
      message.error(`导出失败：${error instanceof Error ? error.message : '未知错误'}`);
    } finally {
      if (exportShell?.parentNode) {
        exportShell.parentNode.removeChild(exportShell);
      }
    }
  };

  const handleShare = async () => {
    try {
      const bundle = buildArtifactDeliveryBundle(artifact, subagentEvents, {
        executionReceipt,
        fallbackContent: content,
      });
      const result = await shareClient.createShareLink({
        title: bundle.share.title,
        content: bundle.share.content,
        html_content: bundle.htmlContent,
        delivery_bundle: bundle,
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
