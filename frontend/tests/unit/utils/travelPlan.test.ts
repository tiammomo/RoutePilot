import { describe, expect, it } from 'vitest';
import {
  buildConfidenceSummary,
  getBudgetProjection,
  parseDayPlanCards,
  parsePlanVariants,
  reorderByDistance,
} from '@/utils/travelPlan';

describe('travelPlan utils', () => {
  it('parses day plan cards from structured content', () => {
    const content = `
## Day 1
上午：外滩散步，南京路
下午：豫园、城隍庙
晚上：陆家嘴夜景
预算：1200
小贴士：早点预约热门餐厅
`;

    const cards = parseDayPlanCards(content);
    expect(cards).toHaveLength(1);
    expect(cards[0].dayLabel).toContain('Day 1');
    expect(cards[0].baseBudget).toBe(1200);
    expect(cards[0].tips[0]).toContain('早点预约');
  });

  it('parses compare variants', () => {
    const content = `
方案A（省钱版）
...
方案B（舒适版）
...
`;
    const variants = parsePlanVariants(content);
    expect(variants.length).toBeGreaterThanOrEqual(2);
  });

  it('projects budget by slider value', () => {
    const saving = getBudgetProjection(1000, 3, 10);
    const comfort = getBudgetProjection(1000, 3, 90);
    expect(saving.totalBudget).toBeLessThan(comfort.totalBudget);
    expect(comfort.hotelShare).toBeGreaterThan(saving.hotelShare);
  });

  it('reorders route points without dropping entries', () => {
    const input = [
      { name: 'A', lat: 30, lng: 120 },
      { name: 'B', lat: 30.1, lng: 120.2 },
      { name: 'C', lat: 33, lng: 116 },
    ];
    const output = reorderByDistance(input);
    expect(output).toHaveLength(3);
    expect(output[0].name).toBe('A');
    expect(output.map((item) => item.name).sort()).toEqual(['A', 'B', 'C']);
  });

  it('builds confidence score from diagnostics', () => {
    const summary = buildConfidenceSummary({
      verificationPassed: false,
      staleResultCount: 2,
      fallbackSteps: 1,
    });
    expect(summary.score).toBeLessThan(70);
    expect(summary.risks.length).toBeGreaterThan(0);
  });
});
