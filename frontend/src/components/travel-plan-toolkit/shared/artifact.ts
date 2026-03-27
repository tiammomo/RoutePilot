'use client';

import type { SubagentEvent, TripPlanArtifact } from '@/types';
import type { PlanVariant } from '@/utils/travelPlan';
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

export interface ArtifactOverviewMetric {
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

export interface ArtifactOverviewDescriptor {
  title: string;
  summary: string;
  metrics: ArtifactOverviewMetric[];
  warnings: string[];
  subagentTrail: string[];
}

export interface ArtifactDeliverySection {
  key: string;
  title: string;
  items: string[];
}

export interface ArtifactDeliveryDescriptor {
  title: string;
  filenameBase: string;
  summary: string;
  summaryLines: string[];
  metrics: ArtifactOverviewMetric[];
  warnings: string[];
  subagentTrail: string[];
  shareContent: string;
  htmlDocumentTitle: string;
  htmlSections: ArtifactDeliverySection[];
}

interface BuildArtifactDeliveryDescriptorOptions {
  fallbackContent?: string;
  fallbackTitle?: string;
}

interface BuildArtifactCompareVariantOptions {
  fallbackContent?: string;
  fallbackTitle?: string;
  id: string;
  messageTimestamp?: string | null;
  runId?: string | null;
  source: 'artifact-history' | 'artifact-current';
  subagentEvents?: SubagentEvent[];
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

function artifactSummary(artifact: TripPlanArtifact | null | undefined, fallbackContent: string): string {
  if (!artifact) return trimText(fallbackContent);
  return (
    trimText(artifact.research.summary) ||
    trimText(artifact.itinerary.explanation) ||
    trimText(artifact.verification.summary) ||
    trimText(artifact.answer) ||
    trimText(fallbackContent)
  );
}

function artifactSubagentTrail(subagentEvents: SubagentEvent[]): string[] {
  return uniqueStrings(subagentEvents.map((event) => subagentLabel(trimText(event.subagent))));
}

function artifactFilenameBase(planId: string, destinations: string[]): string {
  const rawFilenameBase = planId ? `travel-plan-${planId}` : `travel-plan-${destinations.join('-') || 'artifact'}`;
  const normalized = rawFilenameBase
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return normalized || 'travel-plan';
}

function artifactMetrics(
  artifact: TripPlanArtifact,
  destinations: string[],
  planId: string,
  budgetLine: string,
  verificationLine: string
): ArtifactOverviewMetric[] {
  const evidenceCount = artifact.research.evidence.length;
  const stepCount = artifact.itinerary.steps.length;
  const toolCount = uniqueStrings([...(artifact.research.sourceTools || []), ...(artifact.toolsUsed || [])]).length;

  const rawMetrics: Array<ArtifactOverviewMetric | null> = [
    destinations.length > 0 ? { label: '目的地', value: destinations.join(' / '), tone: 'info' } : null,
    planId ? { label: '计划编号', value: planId, tone: 'default' } : null,
    budgetLine ? { label: '预算摘要', value: budgetLine, tone: 'warning' } : null,
    verificationLine
      ? {
          label: '校验状态',
          value: verificationLine,
          tone: artifact.verification.passed === false ? 'danger' : artifact.verification.passed ? 'success' : 'default',
        }
      : null,
    stepCount > 0 ? { label: '结构化步骤', value: `${stepCount}`, tone: 'info' } : null,
    evidenceCount > 0 ? { label: '证据条目', value: `${evidenceCount}`, tone: 'info' } : null,
    toolCount > 0 ? { label: '工具触达', value: `${toolCount}`, tone: 'default' } : null,
  ];

  return rawMetrics.filter((item) => item !== null);
}

function artifactWarnings(artifact: TripPlanArtifact): string[] {
  return [
    artifact.verification.issues.length > 0 ? `检测到 ${artifact.verification.issues.length} 个待处理风险` : '',
    artifact.verification.shouldRetry ? '当前方案建议再次校验' : '',
    artifact.budget.staleResultCount > 0 ? `预算链路存在 ${artifact.budget.staleResultCount} 条时效结果` : '',
    artifact.budget.fallbackSteps > 0 ? `预算链路包含 ${artifact.budget.fallbackSteps} 个回退步骤` : '',
  ].filter(Boolean);
}

function artifactSummaryLines(
  destinations: string[],
  planId: string,
  budgetLine: string,
  verificationLine: string,
  subagentTrail: string[]
): string[] {
  return [
    destinations.length > 0 ? `目的地：${destinations.join('、')}` : '',
    planId ? `计划编号：${planId}` : '',
    budgetLine ? `预算：${budgetLine}` : '',
    verificationLine ? `校验：${verificationLine}` : '',
    subagentTrail.length > 0 ? `子 Agent：${subagentTrail.join(' -> ')}` : '',
  ].filter(Boolean);
}

function artifactShareContent(
  title: string,
  summaryLines: string[],
  toolsUsed: string,
  researchSummary: string,
  summary: string,
  fallbackContent: string
): string {
  return [
    title,
    ...summaryLines,
    toolsUsed ? `工具：${toolsUsed}` : '',
    researchSummary ? `研究摘要：${researchSummary}` : '',
    summary || fallbackContent,
  ]
    .filter(Boolean)
    .join('\n');
}

function artifactHtmlSections(
  summaryLines: string[],
  warnings: string[],
  subagentTrail: string[],
  summary: string
): ArtifactDeliverySection[] {
  const sections: ArtifactDeliverySection[] = [];

  if (summaryLines.length > 0) {
    sections.push({ key: 'overview', title: '方案概览', items: summaryLines });
  }
  if (summary) {
    sections.push({ key: 'summary', title: '行程摘要', items: [summary] });
  }
  if (warnings.length > 0) {
    sections.push({ key: 'warnings', title: '风险提示', items: warnings });
  }
  if (subagentTrail.length > 0) {
    sections.push({ key: 'subagents', title: '多 Agent 协作轨迹', items: [subagentTrail.join(' -> ')] });
  }

  return sections;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function buildArtifactDeliveryDescriptor(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[],
  { fallbackContent = '', fallbackTitle = '旅行方案' }: BuildArtifactDeliveryDescriptorOptions = {}
): ArtifactDeliveryDescriptor {
  const subagentTrail = artifactSubagentTrail(subagentEvents);
  const summary = artifactSummary(artifact, fallbackContent);

  if (!artifact) {
    const summaryLines = summary ? [summary] : [];
    return {
      title: fallbackTitle,
      filenameBase: 'travel-plan',
      summary,
      summaryLines,
      metrics: [],
      warnings: [],
      subagentTrail,
      shareContent: [fallbackTitle, summary].filter(Boolean).join('\n'),
      htmlDocumentTitle: fallbackTitle,
      htmlSections: artifactHtmlSections(summaryLines, [], subagentTrail, summary),
    };
  }

  const destinations = artifactDestinations(artifact);
  const budgetLine = artifactBudgetSummary(artifact);
  const verificationLine = artifactVerificationLabel(artifact);
  const planId = trimText(artifact.itinerary.planId);
  const researchSummary = trimText(artifact.research.summary);
  const title = destinations.length > 0 ? `${destinations.slice(0, 2).join(' / ')}旅行方案` : fallbackTitle;
  const warnings = artifactWarnings(artifact);
  const summaryLines = artifactSummaryLines(destinations, planId, budgetLine, verificationLine, subagentTrail);
  const toolsUsed = uniqueStrings([...(artifact.research.sourceTools || []), ...(artifact.toolsUsed || [])]).join(' / ');

  return {
    title,
    filenameBase: artifactFilenameBase(planId, destinations),
    summary,
    summaryLines,
    metrics: artifactMetrics(artifact, destinations, planId, budgetLine, verificationLine),
    warnings,
    subagentTrail,
    shareContent: artifactShareContent(title, summaryLines, toolsUsed, researchSummary, summary, fallbackContent),
    htmlDocumentTitle: `${title} | Moyuan Travel Agent`,
    htmlSections: artifactHtmlSections(summaryLines, warnings, subagentTrail, summary),
  };
}

export function buildArtifactDeliveryHtml(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[],
  options: BuildArtifactDeliveryDescriptorOptions = {}
): string {
  const descriptor = buildArtifactDeliveryDescriptor(artifact, subagentEvents, options);
  const summaryHtml = descriptor.summary ? `<p class="delivery-summary">${escapeHtml(descriptor.summary)}</p>` : '';
  const sectionsHtml = descriptor.htmlSections
    .map(
      (section) => `
        <section class="delivery-section">
          <h2>${escapeHtml(section.title)}</h2>
          <ul>${section.items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
        </section>
      `
    )
    .join('');

  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(descriptor.htmlDocumentTitle)}</title>
    <style>
      body { margin: 0; font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif; background: #f8fafc; color: #0f172a; }
      main { max-width: 900px; margin: 0 auto; padding: 32px 24px 48px; }
      .hero { border-radius: 24px; padding: 24px 28px; background: linear-gradient(135deg, #082f49 0%, #0f766e 100%); color: #fff; }
      .hero h1 { margin: 0; font-size: 30px; line-height: 1.2; }
      .delivery-summary { margin: 14px 0 0; font-size: 15px; line-height: 1.7; opacity: 0.92; }
      .delivery-section { margin-top: 18px; padding: 18px 20px; border-radius: 18px; background: #fff; border: 1px solid #e2e8f0; }
      .delivery-section h2 { margin: 0 0 10px; font-size: 16px; }
      .delivery-section ul { margin: 0; padding-left: 18px; display: grid; gap: 8px; }
      .delivery-section li { line-height: 1.6; }
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1>${escapeHtml(descriptor.title)}</h1>
        ${summaryHtml}
      </section>
      ${sectionsHtml}
    </main>
  </body>
</html>`;
}

export function buildArtifactOverviewDescriptor(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[]
): ArtifactOverviewDescriptor | null {
  if (!artifact) return null;
  const descriptor = buildArtifactDeliveryDescriptor(artifact, subagentEvents);

  return {
    title: descriptor.title,
    summary: descriptor.summary,
    metrics: descriptor.metrics,
    warnings: descriptor.warnings,
    subagentTrail: descriptor.subagentTrail,
  };
}

export function formatArtifactSnapshotLabel(timestamp: string | null | undefined): string {
  const value = trimText(timestamp);
  if (!value) return '-';
  if (value.includes('T')) {
    return value.replace('T', ' ').replace('Z', '').slice(0, 16);
  }
  return value;
}

export function buildArtifactCompareVariant(
  artifact: TripPlanArtifact | null | undefined,
  {
    fallbackContent = '',
    fallbackTitle = '历史方案',
    id,
    messageTimestamp = null,
    runId = null,
    source,
    subagentEvents = [],
  }: BuildArtifactCompareVariantOptions
): PlanVariant | null {
  if (!artifact) return null;

  const destinations = artifactDestinations(artifact);
  const planId = trimText(artifact.itinerary.planId);
  const snapshotLabel = formatArtifactSnapshotLabel(messageTimestamp);
  const titleBase = destinations.length > 0 ? destinations.slice(0, 2).join(' / ') : fallbackTitle;
  const title = planId ? `${titleBase} · ${planId}` : snapshotLabel !== '-' ? `${titleBase} · ${snapshotLabel}` : titleBase;

  return {
    id,
    title,
    content: buildArtifactSharePayload(artifact, subagentEvents, fallbackContent).content,
    artifact,
    source,
    runId,
    messageTimestamp,
  };
}

export function buildArtifactEditingContext(artifact: TripPlanArtifact | null | undefined): string {
  if (!artifact) return '';
  const descriptor = buildArtifactDeliveryDescriptor(artifact, []);
  const lines = [...descriptor.summaryLines];
  if (descriptor.summary && !lines.includes(descriptor.summary)) {
    lines.push(descriptor.summary);
  }

  if (lines.length === 0) return '';
  return `请基于当前结构化旅行方案继续编辑：\n${lines.map((line) => `- ${line}`).join('\n')}`;
}

export function buildArtifactSharePayload(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[],
  fallbackContent: string
): { title: string; content: string; htmlContent: string } {
  const descriptor = buildArtifactDeliveryDescriptor(artifact, subagentEvents, { fallbackContent });
  return {
    title: descriptor.title,
    content: descriptor.shareContent,
    htmlContent: buildArtifactDeliveryHtml(artifact, subagentEvents, { fallbackContent }),
  };
}

export function buildArtifactExportDescriptor(
  artifact: TripPlanArtifact | null | undefined,
  subagentEvents: SubagentEvent[],
  fallbackTitle: string = '旅行方案'
): { title: string; filenameBase: string; summaryLines: string[] } {
  const descriptor = buildArtifactDeliveryDescriptor(artifact, subagentEvents, { fallbackTitle });
  return {
    title: descriptor.title,
    filenameBase: descriptor.filenameBase,
    summaryLines: descriptor.summaryLines,
  };
}
