import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildComparePrompt, buildPlanPrompt, CURATED_PROMPTS } from '@/components/city-explorer/shared';

const cityClientMock = vi.hoisted(() => ({
  getRegions: vi.fn(),
  getTags: vi.fn(),
  getCities: vi.fn(),
  getCityDetail: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  cityClient: cityClientMock,
}));

import CityExplorer from '@/components/CityExplorer';

const renderWithApp = (ui: React.ReactElement) => render(<App>{ui}</App>);

const baseCity = {
  id: 'hangzhou',
  name: '\u676d\u5dde',
  region: '\u534e\u4e1c',
  tags: ['\u7f8e\u98df', '\u897f\u6e56', '\u5468\u672b'],
  description: '\u9002\u5408\u6162\u8282\u594f\u5468\u672b\u6e38\u3002',
  avg_budget_per_day: 480,
  best_seasons: ['\u6625\u5b63', '\u79cb\u5b63'],
  trip_duration: '2-3\u5929',
  walk_intensity: 'low' as const,
  rain_friendly: true,
  family_friendly: true,
  food_friendly: true,
  style_label: '\u8f7b\u677e\u6162\u6e38',
  editorial_note: '\u7b2c\u4e00\u6b21\u53bb\u4e5f\u5f88\u5bb9\u6613\u4e0a\u624b\u3002',
  data_source: 'curated' as const,
};

describe('CityExplorer', () => {
  beforeEach(() => {
    cityClientMock.getRegions.mockReset();
    cityClientMock.getTags.mockReset();
    cityClientMock.getCities.mockReset();
    cityClientMock.getCityDetail.mockReset();

    cityClientMock.getRegions.mockResolvedValue({ regions: ['\u534e\u4e1c', '\u534e\u5317'] });
    cityClientMock.getTags.mockResolvedValue({ tags: ['\u7f8e\u98df', '\u4eb2\u5b50'] });
    cityClientMock.getCities.mockResolvedValue({ cities: [baseCity] });
    cityClientMock.getCityDetail.mockResolvedValue({
      ...baseCity,
      attractions: [
        {
          name: '\u897f\u6e56',
          type: '\u81ea\u7136',
          duration: '2-3h',
          ticket: 0,
          district: '\u897f\u6e56\u533a',
          note: '\u6e05\u6668\u548c\u508d\u665a\u66f4\u8212\u670d\u3002',
        },
      ],
    });
  });

  it('loads curated cities and triggers curated prompt actions', async () => {
    const onUsePrompt = vi.fn();
    renderWithApp(<CityExplorer onUsePrompt={onUsePrompt} />);

    await waitFor(() => {
      expect(screen.getByText(baseCity.name)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /\u5468\u672b\u5feb\u95ea/ }));
    expect(onUsePrompt).toHaveBeenCalledWith(CURATED_PROMPTS[0].prompt);
  });

  it('syncs favorite cities into the shortlist and plans from the hero panel', async () => {
    const onUsePrompt = vi.fn();
    renderWithApp(<CityExplorer onUsePrompt={onUsePrompt} />);

    await waitFor(() => {
      expect(screen.getByText(baseCity.name)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /\u6536\u85cf 杭州/ }));

    await waitFor(() => {
      expect(screen.getAllByText(baseCity.name).length).toBeGreaterThan(1);
    });

    fireEvent.click(screen.getByRole('button', { name: /\u89c4\u5212\u5019\u9009\u57ce\u5e02 杭州/ }));
    expect(onUsePrompt).toHaveBeenCalledWith(buildPlanPrompt(baseCity.name));
  });

  it('opens city detail drawer from city cards', async () => {
    renderWithApp(<CityExplorer onUsePrompt={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(baseCity.name)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /\u8be6\u60c5/ }));

    await waitFor(() => {
      expect(cityClientMock.getCityDetail).toHaveBeenCalledWith('hangzhou');
    });

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('\u6838\u5fc3\u666f\u70b9')).toBeInTheDocument();
    expect(within(drawer).getByText('\u897f\u6e56')).toBeInTheDocument();
  });

  it('builds compare prompts from the compare panel', async () => {
    const onUsePrompt = vi.fn();
    renderWithApp(<CityExplorer onUsePrompt={onUsePrompt} />);

    await waitFor(() => {
      expect(screen.getByText(baseCity.name)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /\u52a0\u5165\u5bf9\u6bd4/ }));
    fireEvent.click(await screen.findByRole('button', { name: /\u8ba9\u52a9\u624b\u5bf9\u6bd4/ }));

    expect(onUsePrompt).toHaveBeenCalledWith(buildComparePrompt([baseCity.name]));
  });
});
