import { App } from 'antd';
import { beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import html2canvas from 'html2canvas';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import TravelPlanToolkit from '@/components/TravelPlanToolkit';
import { artifactClient, shareClient } from '@/services/api';

const artifactClientMock = vi.hoisted(() => ({
  getArtifactHistory: vi.fn(),
}));

vi.mock('html2canvas', () => ({
  default: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  artifactClient: artifactClientMock,
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

const ARTIFACT_SAMPLE = {
  intent: { name: 'hangzhou-weekend', entities: {}, detail: {} },
  research: {
    summary: '围绕西湖、灵隐寺与河坊街安排周末两日轻松游。',
    evidence: [{ title: '西湖开放信息' }, { title: '灵隐寺预约提示' }],
    destinations: ['杭州'],
    sourceTools: ['search_city', 'search_attractions'],
  },
  itinerary: {
    planId: 'plan-hz-weekend',
    explanation: '周末两天轻松版 itinerary。',
    steps: [{ tool: 'search_cities', status: 'completed' }],
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

describe('TravelPlanToolkit', () => {
  beforeEach(() => {
    vi.mocked(artifactClient.getArtifactHistory).mockReset();
    vi.mocked(artifactClient.getArtifactHistory).mockResolvedValue({
      success: true,
      session_id: 'session-1',
      count: 0,
      entries: [],
    });
  });

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
    renderWithApp(
      <TravelPlanToolkit
        messageId="msg-budget"
        content={SAMPLE_CONTENT}
        artifact={ARTIFACT_SAMPLE}
        onContinuePrompt={onContinuePrompt}
      />
    );

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
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('计划编号：plan-hz-weekend'));
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('目的地：杭州'));
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
      expect(screen.getAllByText('待处理').length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole('checkbox', { name: /Book intercity transportation/i }));

    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: /Book intercity transportation/i })).toBeChecked();
      expect(screen.getByText('已完成')).toBeInTheDocument();
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

  it('builds itinerary again from favorite spots', async () => {
    const onContinuePrompt = vi.fn();
    renderWithApp(
      <TravelPlanToolkit
        messageId="msg-favorites"
        content={SAMPLE_CONTENT}
        artifact={ARTIFACT_SAMPLE}
        onContinuePrompt={onContinuePrompt}
      />
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/收藏 外滩/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/收藏 外滩/i));
    fireEvent.click(screen.getByRole('tab', { name: /候选池/i }));

    await waitFor(() => {
      expect(screen.getByText(/候选景点 1/)).toBeInTheDocument();
      expect(screen.getByText('用候选池重做方案')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('用候选池重做方案'));

    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('外滩'));
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('重新生成一版更精炼的旅行方案'));
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('计划编号：plan-hz-weekend'));
  });

  it('prefers artifact data for overview and shared content', async () => {
    vi.mocked(shareClient.createShareLink).mockResolvedValue({
      success: true,
      share_id: 'share-1',
      share_url: 'https://example.com/share-1',
    });
    const clipboardWriteText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardWriteText },
      configurable: true,
    });

    renderWithApp(
      <TravelPlanToolkit
        messageId="msg-share"
        content={SINGLE_PLAN_CONTENT}
        artifact={ARTIFACT_SAMPLE}
        subagentEvents={[
          { subagent: 'planning' },
          { subagent: 'budget', status: 'completed' },
          { subagent: 'verification', status: 'completed' },
        ]}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('杭州旅行方案')).toBeInTheDocument();
      expect(screen.getByText('计划编号')).toBeInTheDocument();
      expect(screen.getByText('plan-hz-weekend')).toBeInTheDocument();
      expect(screen.getByText('预算估算约 ¥1680')).toBeInTheDocument();
      expect(screen.getByText('结构化步骤')).toBeInTheDocument();
      expect(screen.getByText('证据条目')).toBeInTheDocument();
      expect(screen.getByText(/子 Agent 轨迹：规划 -> 预算 -> 校验/)).toBeInTheDocument();
      expect(screen.getByText('预算:completed')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: '分享旅行方案' }));

    await waitFor(() => {
      expect(shareClient.createShareLink).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '杭州旅行方案',
          content: expect.stringContaining('预算：预算估算约 ¥1680'),
          html_content: expect.stringContaining('<!doctype html>'),
        })
      );
    });
    expect(shareClient.createShareLink).toHaveBeenCalledWith(
      expect.objectContaining({
        content: expect.stringContaining('子 Agent：规划 -> 预算 -> 校验'),
        html_content: expect.stringContaining('多 Agent 协作轨迹'),
      })
    );
    expect(clipboardWriteText).toHaveBeenCalledWith('https://example.com/share-1');
  });

  it('exports artifact-first image metadata when artifact exists', async () => {
    const clickSpy = vi.fn();
    const anchor = document.createElement('a');
    anchor.click = clickSpy;

    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      if (tagName.toLowerCase() === 'a') {
        return anchor;
      }
      return document.createElementNS('http://www.w3.org/1999/xhtml', tagName) as HTMLElement;
    });

    vi.mocked(html2canvas).mockResolvedValue({
      toDataURL: () => 'data:image/png;base64,artifact-export',
    } as never);

    try {
      renderWithApp(
        <TravelPlanToolkit
          messageId="msg-export"
          content={SINGLE_PLAN_CONTENT}
          artifact={ARTIFACT_SAMPLE}
          subagentEvents={[
            { subagent: 'planning' },
            { subagent: 'budget', status: 'completed' },
            { subagent: 'verification', status: 'completed' },
          ]}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: '导出旅行方案图片' }));

      await waitFor(() => {
        expect(clickSpy).toHaveBeenCalled();
      });

      expect(anchor.download).toContain('travel-plan-plan-hz-weekend-');
      expect(anchor.download).toMatch(/\.png$/);
    } finally {
      createElementSpy.mockRestore();
    }
  });

  it('uses artifact context when continuing from compare variants', async () => {
    const onContinuePrompt = vi.fn();
    renderWithApp(
      <TravelPlanToolkit
        messageId="msg-variant"
        content={SAMPLE_CONTENT}
        artifact={ARTIFACT_SAMPLE}
        onContinuePrompt={onContinuePrompt}
      />
    );

    fireEvent.click(screen.getByRole('tab', { name: /多方案对比/i }));

    await waitFor(() => {
      expect(screen.getByText('选中“省钱版”继续细化')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('选中“省钱版”继续细化'));

    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('计划编号：plan-hz-weekend'));
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('目的地：杭州'));
    expect(onContinuePrompt).toHaveBeenCalledWith(expect.stringContaining('原方案：'));
  });
  it('prefers persisted artifact history for compare tab when session snapshots are available', async () => {
    vi.mocked(artifactClient.getArtifactHistory).mockResolvedValue({
      success: true,
      session_id: 'session-compare',
      count: 2,
      entries: [
        {
          run_id: 'run-current',
          message_timestamp: '2026-03-27T10:30:00Z',
          message_index: 5,
          artifact: {
            ...ARTIFACT_SAMPLE,
            itinerary: {
              ...ARTIFACT_SAMPLE.itinerary,
              planId: 'plan-hz-current',
              steps: [{ tool: 'search_city' }, { tool: 'plan' }],
            },
          },
        },
        {
          run_id: 'run-older',
          message_timestamp: '2026-03-26T08:00:00Z',
          message_index: 3,
          artifact: {
            ...ARTIFACT_SAMPLE,
            research: {
              ...ARTIFACT_SAMPLE.research,
              destinations: ['苏州'],
              evidence: [{ title: '园林开放' }],
            },
            itinerary: {
              ...ARTIFACT_SAMPLE.itinerary,
              planId: 'plan-sz-older',
              steps: [{ tool: 'research' }],
            },
            budget: {
              ...ARTIFACT_SAMPLE.budget,
              executionBudget: { totalBudget: 1320 },
            },
            verification: {
              ...ARTIFACT_SAMPLE.verification,
              summary: '需再次校验',
              passed: false,
            },
          },
        },
      ],
    });

    renderWithApp(
      <TravelPlanToolkit
        messageId="msg-compare-history"
        content={SINGLE_PLAN_CONTENT}
        diagnostics={{ sessionId: 'session-compare', runId: 'run-current' }}
        artifact={ARTIFACT_SAMPLE}
        onContinuePrompt={vi.fn()}
      />
    );

    fireEvent.click(screen.getAllByRole('tab')[1]);

    await waitFor(() => {
      expect(screen.getByText(/persisted artifact history/i)).toBeInTheDocument();
      expect(screen.getAllByRole('row').length).toBeGreaterThan(4);
      expect(screen.getAllByText(/plan-hz-weekend/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/plan-sz-older/).length).toBeGreaterThan(0);
    });
  });
});
