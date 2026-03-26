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
  '预算：800',
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
    });
  });

  it('shows compare actions for multi-variant plans', async () => {
    renderWithApp(<TravelPlanToolkit messageId="msg-2" content={SAMPLE_CONTENT} onContinuePrompt={vi.fn()} />);

    fireEvent.click(screen.getByRole('tab', { name: /多方案对比/i }));

    await waitFor(() => {
      expect(screen.getByText('选中“省钱版”继续细化')).toBeInTheDocument();
      expect(screen.getByText('选中“轻松版”继续细化')).toBeInTheDocument();
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
    });
  });
});
