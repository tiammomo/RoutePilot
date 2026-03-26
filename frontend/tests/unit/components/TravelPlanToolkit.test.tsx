import { App } from 'antd';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import TravelPlanToolkit from '@/components/TravelPlanToolkit';

vi.mock('html2canvas', () => ({
  default: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  mapClient: {
    getRoutePreview: vi.fn(),
  },
  shareClient: {
    createShareLink: vi.fn(),
  },
}));

const renderWithApp = (ui: React.ReactElement) => render(<App>{ui}</App>);

const SAMPLE_CONTENT = [
  'Day 1',
  '上午：外滩 09:00 漫步；10:30 南京路早餐',
  '下午：豫园 13:00；城隍庙 15:00',
  '晚上：陆家嘴夜景 19:00',
  '预算：900',
  '小贴士：热门餐厅提前取号。',
  '',
  '省钱版',
  'Day 1',
  '上午：外滩',
  '下午：豫园',
  '晚上：南京路',
  '',
  '轻松版',
  'Day 1',
  '上午：武康路',
  '下午：新天地',
  '晚上：徐汇滨江',
].join('\n');

const CONFLICT_CONTENT = [
  'Day 1',
  '上午：博物馆 09:30；外滩 09:00',
  '下午：新天地 14:00',
  '晚上：博物馆 19:00',
  '预算：800',
  '小贴士：夜间景点先确认开放时间。',
].join('\n');

const SINGLE_PLAN_CONTENT = [
  'Day 1',
  '上午：外滩 09:00 漫步',
  '下午：豫园 13:00',
  '晚上：南京路 19:00',
  '预算：700',
].join('\n');

describe('TravelPlanToolkit', () => {
  it('renders primary tabs for itinerary planning', () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-1" content={SAMPLE_CONTENT} />);

    expect(screen.getByRole('tab', { name: /每日行程/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /执行清单/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /实用信息/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /出发提醒/i })).toBeInTheDocument();
  });

  it('renders itinerary actions on the default tab', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-1a" content={SAMPLE_CONTENT} />);

    await waitFor(() => {
      expect(screen.getByText('换成更省钱')).toBeInTheDocument();
      expect(screen.getAllByText('真实路线').length).toBeGreaterThan(0);
      expect(screen.getAllByText('一键修复冲突').length).toBeGreaterThan(0);
      expect(screen.getAllByText('按距离重排').length).toBeGreaterThan(0);
    });
  });

  it('renders budget stats, confidence hints and quick refine actions', async () => {
    const onContinuePrompt = vi.fn();
    renderWithApp(<TravelPlanToolkit messageId="msg-budget" content={SAMPLE_CONTENT} onContinuePrompt={onContinuePrompt} />);

    await waitFor(() => {
      expect(screen.getByText('预算档位')).toBeInTheDocument();
      expect(screen.getByText(/总预算：/)).toBeInTheDocument();
      expect(screen.getByText('人均预估')).toBeInTheDocument();
      expect(screen.getByText('结果可信度')).toBeInTheDocument();
      expect(screen.getByText(/No verification metadata available/)).toBeInTheDocument();
      expect(screen.getByText('少走路版')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('少走路版'));

    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('少走路版本'));
  });

  it('renders itinerary decision cards, tips and conflict reminders', async () => {
    const { rerender } = renderWithApp(<TravelPlanToolkit messageId="msg-1b" content={SAMPLE_CONTENT} />);

    await waitFor(() => {
      expect(screen.getAllByText('景点决策卡').length).toBeGreaterThan(0);
      expect(screen.getAllByText('小贴士：热门餐厅提前取号。').length).toBeGreaterThan(0);
      expect(screen.getAllByText(/最佳到达：/).length).toBeGreaterThan(0);
    });

    rerender(
      <App>
        <TravelPlanToolkit messageId="msg-1c" content={CONFLICT_CONTENT} />
      </App>
    );

    await waitFor(() => {
      expect(screen.getByText('本日风险提醒')).toBeInTheDocument();
      expect(screen.getAllByText(/Morning time conflict/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Potential closing-time risk/).length).toBeGreaterThan(0);
    });
  });

  it('shows compare actions for multi-variant plans', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-2" content={SAMPLE_CONTENT} onContinuePrompt={vi.fn()} />);

    fireEvent.click(screen.getByRole('tab', { name: /多方案对比/i }));

    await waitFor(() => {
      expect(screen.getAllByText('对比项').length).toBeGreaterThan(0);
      expect(screen.getByText('方案定位')).toBeInTheDocument();
      expect(screen.getByText('核心亮点')).toBeInTheDocument();
      expect(screen.getByText('适合人群')).toBeInTheDocument();
      expect(screen.getByText('选中“省钱版”继续细化')).toBeInTheDocument();
      expect(screen.getByText('选中“轻松版”继续细化')).toBeInTheDocument();
    });
  });

  it('shows compare empty state when there are not enough variants', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-2b" content={SINGLE_PLAN_CONTENT} />);

    fireEvent.click(screen.getByRole('tab', { name: /多方案对比/i }));

    await waitFor(() => {
      expect(screen.getByText(/未检测到 2 套以上可比较方案/)).toBeInTheDocument();
    });
  });

  it('renders conflict summary and one-click fix actions', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-conflict" content={CONFLICT_CONTENT} />);

    fireEvent.click(screen.getByRole('tab', { name: /冲突检测/i }));

    await waitFor(() => {
      expect(screen.getByText(/检测到 2 个冲突风险/)).toBeInTheDocument();
      expect(screen.getAllByText('Morning time conflict').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Potential closing-time risk').length).toBeGreaterThan(0);
      expect(screen.getByText('一键修复此日')).toBeInTheDocument();
    });
  });

  it('renders no-conflict summary when itinerary has no detected issues', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-no-conflict" content={SINGLE_PLAN_CONTENT} />);

    fireEvent.click(screen.getByRole('tab', { name: /冲突检测/i }));

    await waitFor(() => {
      expect(screen.getByText('未检测到明显冲突')).toBeInTheDocument();
      expect(screen.getByText('无冲突')).toBeInTheDocument();
    });
  });

  it('renders checklist items and practical info cards', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-3" content={SAMPLE_CONTENT} />);

    fireEvent.click(screen.getByRole('tab', { name: /执行清单/i }));
    await waitFor(() => {
      expect(screen.getByText('Book intercity transportation')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('tab', { name: /实用信息/i }));
    await waitFor(() => {
      expect(screen.getByText('天气与穿衣')).toBeInTheDocument();
      expect(screen.getByText('交通建议')).toBeInTheDocument();
      expect(screen.getAllByText('常规').length).toBeGreaterThan(0);
      expect(screen.getByText('建议')).toBeInTheDocument();
      expect(screen.getByText('注意')).toBeInTheDocument();
    });
  });

  it('renders reminder timeline cards and phase labels', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-4" content={SAMPLE_CONTENT} />);

    fireEvent.click(screen.getByRole('tab', { name: /出发提醒/i }));

    await waitFor(() => {
      expect(screen.getByText('T-7')).toBeInTheDocument();
      expect(screen.getByText('出发前一周')).toBeInTheDocument();
      expect(screen.getByText('Confirm bookings')).toBeInTheDocument();
      expect(screen.getByText('T-1')).toBeInTheDocument();
      expect(screen.getByText('Final check')).toBeInTheDocument();
    });
  });
});
