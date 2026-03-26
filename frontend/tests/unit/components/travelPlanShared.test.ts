import { describe, expect, it } from 'vitest';
import {
  artifactBudgetSummary,
  artifactDestinations,
  buildArtifactExportDescriptor,
  buildArtifactSharePayload,
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

    const exportDescriptor = buildArtifactExportDescriptor(
      artifact,
      [{ subagent: 'planning' }, { subagent: 'budget' }, { subagent: 'verification' }]
    );

    expect(exportDescriptor.title).toBe('杭州旅行方案');
    expect(exportDescriptor.filenameBase).toBe('travel-plan-plan-hz');
    expect(exportDescriptor.summaryLines).toContain('目的地：杭州');
    expect(exportDescriptor.summaryLines).toContain('预算：预算估算约 ¥1680');
  });
});
