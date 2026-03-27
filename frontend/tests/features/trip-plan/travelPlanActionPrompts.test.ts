import { describe, expect, it } from 'vitest';
import type { TripPlanArtifact } from '@/types';
import type { PlanVariant, SpotDecisionInfo } from '@/utils/travelPlan';
import {
  buildArtifactAwarePrompt,
  buildFavoritesQuickRefineAction,
  buildVariantContinuePrompt,
} from '@/components/travel-plan-toolkit/actionPrompts';

const ARTIFACT_SAMPLE: TripPlanArtifact = {
  intent: { name: 'hangzhou-weekend', entities: {}, detail: {} },
  research: {
    summary: '围绕西湖和灵隐寺安排 2 天轻松游。',
    evidence: [],
    destinations: ['杭州'],
    sourceTools: ['search_city'],
  },
  itinerary: {
    planId: 'plan-hz-weekend',
    explanation: '周末两天轻松版 itinerary。',
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

describe('travel plan action prompts', () => {
  it('builds continue prompts for chosen variants', () => {
    const variant: PlanVariant = {
      id: 'variant-1',
      title: '轻松版',
      content: 'Day 1\n上午：武康路\n下午：新天地',
    };

    expect(buildVariantContinuePrompt(variant, ARTIFACT_SAMPLE)).toContain('请基于“轻松版”继续细化');
    expect(buildVariantContinuePrompt(variant, ARTIFACT_SAMPLE)).toContain('计划编号：plan-hz-weekend');
    expect(buildVariantContinuePrompt(variant, ARTIFACT_SAMPLE)).toContain('目的地：杭州');
    expect(buildVariantContinuePrompt(variant, ARTIFACT_SAMPLE)).toContain('原方案：');
    expect(buildVariantContinuePrompt(variant, ARTIFACT_SAMPLE)).toContain('上午：武康路');
  });

  it('builds favorites-based quick refine actions', () => {
    const spots: SpotDecisionInfo[] = [
      { name: '外滩', stayDuration: '1-2h', bestArrival: '10:00-12:00', audience: '大众友好', costHint: '中等' },
      { name: '豫园', stayDuration: '1-2h', bestArrival: '10:00-12:00', audience: '大众友好', costHint: '中等' },
    ];

    const action = buildFavoritesQuickRefineAction(spots);
    expect(action.key).toBe('favorites-build');
    expect(action.label).toBe('根据候选池重做');
    expect(action.prompt).toContain('外滩、豫园');
  });

  it('wraps generic quick refine prompts with artifact editing context', () => {
    const prompt = buildArtifactAwarePrompt('请改成更省钱版本，并保留核心体验。', ARTIFACT_SAMPLE);
    expect(prompt).toContain('请基于当前结构化旅行方案继续编辑');
    expect(prompt).toContain('计划编号：plan-hz-weekend');
    expect(prompt).toContain('预算：预算估算约 ¥1680');
    expect(prompt).toContain('任务要求：');
  });
});
