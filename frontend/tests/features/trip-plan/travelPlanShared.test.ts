import { describe, expect, it } from 'vitest';
import {
  artifactBudgetSummary,
  artifactDestinations,
  buildArtifactCompareVariant,
  buildArtifactDeliveryDescriptor,
  buildArtifactDeliveryHtml,
  buildArtifactExportDescriptor,
  buildArtifactOverviewDescriptor,
  buildArtifactSharePayload,
  formatArtifactSnapshotLabel,
  subagentLabel,
} from '@/components/travel-plan-toolkit/shared';
import { sliderToMode, modeToSliderValue } from '@/components/travel-plan-toolkit/shared/budget';
import { checklistStatusMeta } from '@/components/travel-plan-toolkit/shared/checklist';
import { practicalToneLabel } from '@/components/travel-plan-toolkit/shared/practical';
import { reminderPhaseMeta } from '@/components/travel-plan-toolkit/shared/reminders';
import { compactTips } from '@/components/travel-plan-toolkit/shared/timeline';

describe('travelPlan shared helpers', () => {
  it('normalizes and deduplicates tips', () => {
    expect(compactTips(['小贴士：热门餐厅提前取号。', 'tips: 热门餐厅提前取号。', '  '])).toEqual([
      '热门餐厅提前取号。',
    ]);
  });

  it('maps slider values and labels across budget/practical/reminder/checklist helpers', () => {
    expect(sliderToMode(10)).toBe('saving');
    expect(sliderToMode(50)).toBe('balanced');
    expect(sliderToMode(90)).toBe('comfort');
    expect(modeToSliderValue('comfort')).toBe(90);

    expect(practicalToneLabel('good')).toBe('建议');
    expect(reminderPhaseMeta('T-3')).toEqual({ color: 'cyan', subtitle: '出发前三天' });
    expect(checklistStatusMeta(true).label).toBe('已完成');
    expect(checklistStatusMeta(false).label).toBe('待处理');
    expect(subagentLabel('budget')).toBe('预算');
  });

  it('builds artifact-first destinations, budget copy and share payloads', () => {
    const artifact = {
      intent: { name: 'hangzhou-weekend', entities: {}, detail: {} },
      research: {
        summary: '围绕西湖和灵隐寺安排 2 天轻松游。',
        evidence: [],
        destinations: ['杭州'],
        sourceTools: ['search_city', 'search_attractions'],
      },
      itinerary: {
        planId: 'plan-hz',
        explanation: '周末 2 天轻松逛西湖周边。',
        steps: [],
        validationStatus: 'pass',
        validationErrors: [],
      },
      budget: {
        summary: { toolCount: 1 },
        executionBudget: { totalBudget: 1680 },
        staleResultCount: 0,
        fallbackSteps: 0,
      },
      verification: {
        passed: true,
        shouldRetry: false,
        issues: [],
        refreshTargets: [],
        summary: '校验通过',
      },
      answer: '杭州周末轻松版方案',
      reasoning: '',
      toolsUsed: ['calculate_budget'],
      metadata: {},
    };

    expect(artifactDestinations(artifact)).toEqual(['杭州']);
    expect(artifactBudgetSummary(artifact)).toBe('预算估算约 ¥1680');

    const payload = buildArtifactSharePayload(
      artifact,
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }],
      'fallback content'
    );

    expect(payload.title).toBe('杭州旅行方案');
    expect(payload.content).toContain('目的地：杭州');
    expect(payload.content).toContain('预算：预算估算约 ¥1680');
    expect(payload.content).toContain('子 Agent：规划 -> 预算 -> 校验');
    expect(payload.htmlContent).toContain('<!doctype html>');
    expect(payload.htmlContent).toContain('杭州旅行方案');
    expect(payload.htmlContent).toContain('方案概览');

    const deliveryDescriptor = buildArtifactDeliveryDescriptor(
      artifact,
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }]
    );

    expect(deliveryDescriptor.title).toBe('杭州旅行方案');
    expect(deliveryDescriptor.filenameBase).toBe('travel-plan-plan-hz');
    expect(deliveryDescriptor.summaryLines).toContain('目的地：杭州');
    expect(deliveryDescriptor.htmlSections).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'overview', title: '方案概览' }),
        expect.objectContaining({ key: 'summary', title: '行程摘要' }),
        expect.objectContaining({ key: 'subagents', title: '多 Agent 协作轨迹' }),
      ])
    );

    const deliveryHtml = buildArtifactDeliveryHtml(
      artifact,
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }]
    );
    expect(deliveryHtml).toContain('<title>杭州旅行方案 | Moyuan Travel Agent</title>');
    expect(deliveryHtml).toContain('多 Agent 协作轨迹');

    const exportDescriptor = buildArtifactExportDescriptor(
      artifact,
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }]
    );

    expect(exportDescriptor.title).toBe('杭州旅行方案');
    expect(exportDescriptor.filenameBase).toBe('travel-plan-plan-hz');
    expect(exportDescriptor.summaryLines).toContain('目的地：杭州');
    expect(exportDescriptor.summaryLines).toContain('预算：预算估算约 ¥1680');

    const compareVariant = buildArtifactCompareVariant(artifact, {
      id: 'variant-1',
      messageTimestamp: '2026-03-27T10:30:00Z',
      runId: 'run-1',
      source: 'artifact-history',
    });

    expect(compareVariant?.title).toContain('plan-hz');
    expect(compareVariant?.runId).toBe('run-1');
    expect(formatArtifactSnapshotLabel('2026-03-27T10:30:00Z')).toBe('2026-03-27 10:30');

    const overviewDescriptor = buildArtifactOverviewDescriptor(
      {
        ...artifact,
        research: {
          ...artifact.research,
          evidence: [{ title: '西湖开放信息' }, { title: '灵隐寺预约提示' }],
        },
        budget: {
          ...artifact.budget,
          staleResultCount: 1,
          fallbackSteps: 2,
        },
        verification: {
          ...artifact.verification,
          issues: [{ severity: 'medium' }],
          shouldRetry: true,
        },
      },
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }]
    );

    expect(overviewDescriptor?.title).toBe('杭州旅行方案');
    expect(overviewDescriptor?.metrics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: '目的地', value: '杭州' }),
        expect.objectContaining({ label: '计划编号', value: 'plan-hz' }),
        expect.objectContaining({ label: '预算摘要', value: '预算估算约 ¥1680' }),
        expect.objectContaining({ label: '证据条目', value: '2' }),
      ])
    );
    expect(overviewDescriptor?.warnings).toEqual(
      expect.arrayContaining([
        '检测到 1 个待处理风险',
        '当前方案建议再次校验',
        '预算链路存在 1 条时效结果',
        '预算链路包含 2 个回退步骤',
      ])
    );
  });
});
