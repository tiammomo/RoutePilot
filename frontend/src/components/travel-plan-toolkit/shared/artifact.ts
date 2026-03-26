'use client';

import type { SubagentEvent, TripPlanArtifact } from '@/types';
import { subagentLabel } from './subagents';

function uniqueStrings(items: string[]): string[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const normalized = item.trim();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

function trimText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function artifactDestinations(artifact: TripPlanArtifact | null | undefined): string[] {
  if (!artifact) return [];
  return uniqueStrings(
    (artifact.research.destinations || [])
      .map((item) => trimText(item))
      .filter(Boolean)
  );
}

export function artifactBudgetSummary(artifact: TripPlanArtifact | null | undefined): string {
  if (!artifact) return '';

  const summary = isRecord(artifact.budget.summary) ? artifact.budget.summary : {};
  const executionBudget = isRecord(artifact.budget.executionBudget) ? artifact.budget.executionBudget : {};
  const toolCount = typeof summary.toolCount === 'number' ? summary.toolCount : typeof summary.tool_count === 'number' ? summary.tool_count : 0;
  const totalEstimate =
    typeof executionBudget.total === 'number'
      ? executionBudget.total
      : typeof executionBudget.totalBudget === 'number'
        ? executionBudget.totalBudget
        : typeof summary.totalBudget === 'number'
          ? summary.totalBudget
          : null;

  if (typeof totalEstimate === 'number' && Number.isFinite(totalEstimate) && totalEstimate > 0) {
    return `预算估算约 ¥${Math.round(totalEstimate)}`;
  }
  if (Object.keys(executionBudget).length > 0) return '已生成执行预算明细';
  if (toolCount > 0) return `已完成预算评估（${toolCount} 个预算工具）`;
  if (artifact.budget.fallbackSteps > 0 || artifact.budget.staleResultCount > 0) return '预算评估已完成，含回退/时效提醒';
  return '';
}

export function artifactVerificationLabel(artifact: TripPlanArtifact | null | undefined): string {
  if (!artifact) return '';
  if (artifact.verification.passed === true) return '校验通过';
  if (artifact.verification.passed === false) return '校验未通过';
  if (trimText(artifact.verification.summary)) return trimText(artifact.verification.summary);
  return '';
}

export function buildArtifactSharePayload(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[],
  fallbackContent: string
): { title: string; content: string } {
  if (!artifact) {
    return {
      title: '旅行方案',
      content: fallbackContent,
    };
  }

  const destinations = artifactDestinations(artifact);
  const titleBase = destinations.length > 0 ? `${destinations.slice(0, 2).join(' / ')}旅行方案` : '旅行方案';
  const budgetLine = artifactBudgetSummary(artifact);
  const verificationLine = artifactVerificationLabel(artifact);
  const planId = trimText(artifact.itinerary.planId);
  const answer = trimText(artifact.answer);
  const explanation = trimText(artifact.itinerary.explanation);
  const researchSummary = trimText(artifact.research.summary);
  const subagentTrail = uniqueStrings(subagentEvents.map((event) => subagentLabel(trimText(event.subagent)))).join(' -> ');
  const toolsUsed = uniqueStrings([...(artifact.research.sourceTools || []), ...(artifact.toolsUsed || [])]).join(' / ');

  const lines = [
    titleBase,
    destinations.length > 0 ? `目的地：${destinations.join('、')}` : '',
    planId ? `计划编号：${planId}` : '',
    budgetLine ? `预算：${budgetLine}` : '',
    verificationLine ? `校验：${verificationLine}` : '',
    toolsUsed ? `工具：${toolsUsed}` : '',
    subagentTrail ? `子 Agent：${subagentTrail}` : '',
    researchSummary ? `研究摘要：${researchSummary}` : '',
    answer || explanation || fallbackContent,
  ].filter(Boolean);

  return {
    title: titleBase,
    content: lines.join('\n'),
  };
}
