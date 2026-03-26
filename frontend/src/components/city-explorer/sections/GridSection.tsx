'use client';

import React from 'react';
import { Alert, Empty, Spin } from 'antd';
import type { CitySummary } from '@/types';
import { CityGridCard } from './grid/CityGridCard';
import { GridSummaryBar } from './grid/GridSummaryBar';

interface CityExplorerGridProps {
  compareCityIds: string[];
  displayedCities: CitySummary[];
  error: string | null;
  favoriteCityIds: string[];
  filteredCities: CitySummary[];
  initialVisibleCityCount: number;
  isLoading: boolean;
  loadMoreCityCount: number;
  onOpenCityDetail: (cityId: string) => void;
  onToggleCompareCity: (cityId: string) => void;
  onToggleFavoriteCity: (cityId: string) => void;
  onUsePrompt: (prompt: string) => void;
  setVisibleCityCount: React.Dispatch<React.SetStateAction<number>>;
  visibleCityCount: number;
}

export const CityExplorerGrid: React.FC<CityExplorerGridProps> = ({
  compareCityIds,
  displayedCities,
  error,
  favoriteCityIds,
  filteredCities,
  initialVisibleCityCount,
  isLoading,
  loadMoreCityCount,
  onOpenCityDetail,
  onToggleCompareCity,
  onToggleFavoriteCity,
  onUsePrompt,
  setVisibleCityCount,
  visibleCityCount,
}) => {
  if (error) return <Alert type="error" showIcon message={error} />;

  if (isLoading) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Spin />
      </div>
    );
  }

  if (filteredCities.length === 0) {
    return <Empty description="没有找到符合当前筛选条件的城市" />;
  }

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <GridSummaryBar
        displayedCityCount={displayedCities.length}
        filteredCityCount={filteredCities.length}
        initialVisibleCityCount={initialVisibleCityCount}
        loadMoreCityCount={loadMoreCityCount}
        onLoadMore={() => setVisibleCityCount((count) => count + loadMoreCityCount)}
        onReset={() => setVisibleCityCount(initialVisibleCityCount)}
        visibleCityCount={visibleCityCount}
      />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
        {displayedCities.map((city) => (
          <CityGridCard
            key={city.id}
            city={city}
            favorite={favoriteCityIds.includes(city.id)}
            inCompare={compareCityIds.includes(city.id)}
            onOpenCityDetail={onOpenCityDetail}
            onToggleCompareCity={onToggleCompareCity}
            onToggleFavoriteCity={onToggleFavoriteCity}
            onUsePrompt={onUsePrompt}
          />
        ))}
      </div>
    </div>
  );
};
