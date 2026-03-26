import { describe, expect, it } from 'vitest';
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
  });
});
