'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Card } from 'antd';
import { cityClient } from '@/services/api';
import type { CityDetail, CitySummary } from '@/types';
import {
  CityExplorerComparePanel,
  CityExplorerDetailDrawer,
  CityExplorerFilterBar,
  CityExplorerGrid,
  CityExplorerHero,
} from '@/components/city-explorer/sections';
import { buildCityProfile, type QuickFilterKey } from '@/components/city-explorer/shared';

interface CityExplorerProps {
  onUsePrompt: (prompt: string) => void;
}

const QUICK_FILTER_LABELS: Record<QuickFilterKey, string> = {
  weekend: '周末可去',
  budget: '预算友好',
  family: '亲子友好',
  easywalk: '少走路',
  rainy: '雨天也能玩',
  food: '美食优先',
};

export default function CityExplorer({ onUsePrompt }: CityExplorerProps) {
  const initialVisibleCityCount = 24;
  const loadMoreCityCount = 24;
  const [regions, setRegions] = useState<string[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [selectedRegion, setSelectedRegion] = useState<string | undefined>(undefined);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedQuickFilters, setSelectedQuickFilters] = useState<QuickFilterKey[]>([]);
  const [cities, setCities] = useState<CitySummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isFilterLoading, setIsFilterLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCityDetail, setActiveCityDetail] = useState<CityDetail | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [compareCityIds, setCompareCityIds] = useState<string[]>([]);
  const [favoriteCityIds, setFavoriteCityIds] = useState<string[]>([]);
  const [visibleCityCount, setVisibleCityCount] = useState(initialVisibleCityCount);

  useEffect(() => {
    async function loadFilterOptions() {
      try {
        setIsFilterLoading(true);
        const [regionData, tagData] = await Promise.all([cityClient.getRegions(), cityClient.getTags()]);
        setRegions(regionData.regions || []);
        setTags(tagData.tags || []);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : '加载筛选项失败');
      } finally {
        setIsFilterLoading(false);
      }
    }

    void loadFilterOptions();
  }, []);

  useEffect(() => {
    async function loadCities() {
      try {
        setIsLoading(true);
        setError(null);
        const response = await cityClient.getCities({ region: selectedRegion, tags: selectedTags });
        setCities(response.cities || []);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : '加载城市失败');
      } finally {
        setIsLoading(false);
      }
    }

    void loadCities();
  }, [selectedRegion, selectedTags]);

  useEffect(() => {
    setVisibleCityCount(initialVisibleCityCount);
  }, [selectedQuickFilters, selectedRegion, selectedTags]);

  const filteredCities = useMemo(() => {
    return cities.filter((city) => {
      if (selectedQuickFilters.length === 0) return true;
      const profile = buildCityProfile(city);

      return selectedQuickFilters.every((filterKey) => {
        if (filterKey === 'weekend') return /^2/.test(profile.tripDuration);
        if (filterKey === 'budget') return profile.budgetLevel === 'low';
        if (filterKey === 'family') return profile.familyFriendly;
        if (filterKey === 'easywalk') return profile.walkIntensity === 'low';
        if (filterKey === 'rainy') return profile.rainFriendly;
        if (filterKey === 'food') return profile.foodFriendly;
        return true;
      });
    });
  }, [cities, selectedQuickFilters]);

  const compareCities = useMemo(
    () => filteredCities.filter((city) => compareCityIds.includes(city.id)).slice(0, 3),
    [compareCityIds, filteredCities]
  );

  const favoriteCities = useMemo(() => cities.filter((city) => favoriteCityIds.includes(city.id)), [cities, favoriteCityIds]);

  const displayedCities = useMemo(() => filteredCities.slice(0, visibleCityCount), [filteredCities, visibleCityCount]);

  const summaryText = useMemo(() => {
    const segments: string[] = [];
    if (selectedRegion) segments.push(selectedRegion);
    if (selectedTags.length > 0) segments.push(selectedTags.join(' / '));
    if (selectedQuickFilters.length > 0) {
      segments.push(selectedQuickFilters.map((key) => QUICK_FILTER_LABELS[key]).join(' / '));
    }
    return segments.length > 0 ? segments.join(' / ') : '全部真实策展城市';
  }, [selectedQuickFilters, selectedRegion, selectedTags]);

  const activeDetailProfile = activeCityDetail ? buildCityProfile(activeCityDetail) : null;

  async function openCityDetail(cityId: string) {
    try {
      const detail = await cityClient.getCityDetail(cityId);
      setActiveCityDetail(detail);
      setIsDetailOpen(true);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : '加载城市详情失败');
    }
  }

  function toggleQuickFilter(filterKey: QuickFilterKey) {
    setSelectedQuickFilters((previous) =>
      previous.includes(filterKey) ? previous.filter((item) => item !== filterKey) : [...previous, filterKey]
    );
  }

  function toggleCompareCity(cityId: string) {
    setCompareCityIds((previous) => {
      if (previous.includes(cityId)) return previous.filter((item) => item !== cityId);
      if (previous.length >= 3) return [...previous.slice(1), cityId];
      return [...previous, cityId];
    });
  }

  function toggleFavoriteCity(cityId: string) {
    setFavoriteCityIds((previous) =>
      previous.includes(cityId) ? previous.filter((item) => item !== cityId) : [...previous, cityId]
    );
  }

  return (
    <div style={{ margin: '0 16px 16px' }}>
      <Card
        style={{
          borderRadius: 24,
          border: '1px solid rgba(15, 23, 42, 0.1)',
          background:
            'radial-gradient(circle at 12% 0%, rgba(14,165,233,0.18), transparent 36%), radial-gradient(circle at 100% 100%, rgba(15,118,110,0.12), transparent 30%), linear-gradient(150deg, #ffffff 0%, #f8fbff 44%, #eef6ff 100%)',
          overflow: 'hidden',
          boxShadow: '0 16px 42px rgba(15, 23, 42, 0.08)',
        }}
        styles={{ body: { padding: 22, position: 'relative' } }}
      >
        <div
          style={{
            pointerEvents: 'none',
            position: 'absolute',
            inset: 0,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              width: 320,
              height: 320,
              borderRadius: '50%',
              right: -120,
              top: -130,
              background: 'radial-gradient(circle, rgba(3, 105, 161, 0.16) 0%, transparent 68%)',
            }}
          />
          <div
            style={{
              position: 'absolute',
              width: 260,
              height: 260,
              borderRadius: '50%',
              left: -100,
              bottom: -120,
              background: 'radial-gradient(circle, rgba(15, 118, 110, 0.14) 0%, transparent 70%)',
            }}
          />
        </div>

        <div style={{ display: 'grid', gap: 16, position: 'relative', zIndex: 1 }}>
          <CityExplorerHero
            compareCities={compareCities}
            favoriteCities={favoriteCities}
            onUsePrompt={onUsePrompt}
            summaryText={summaryText}
          />

          <CityExplorerFilterBar
            isFilterLoading={isFilterLoading}
            onUsePrompt={onUsePrompt}
            regions={regions}
            selectedQuickFilters={selectedQuickFilters}
            selectedRegion={selectedRegion}
            selectedTags={selectedTags}
            tags={tags}
            toggleQuickFilter={toggleQuickFilter}
            setSelectedRegion={setSelectedRegion}
            setSelectedTags={setSelectedTags}
          />

          <CityExplorerComparePanel
            compareCities={compareCities}
            onClearCompare={() => setCompareCityIds([])}
            onUsePrompt={onUsePrompt}
          />

          <CityExplorerGrid
            compareCityIds={compareCityIds}
            displayedCities={displayedCities}
            error={error}
            favoriteCityIds={favoriteCityIds}
            filteredCities={filteredCities}
            initialVisibleCityCount={initialVisibleCityCount}
            isLoading={isLoading}
            loadMoreCityCount={loadMoreCityCount}
            onOpenCityDetail={openCityDetail}
            onToggleCompareCity={toggleCompareCity}
            onToggleFavoriteCity={toggleFavoriteCity}
            onUsePrompt={onUsePrompt}
            setVisibleCityCount={setVisibleCityCount}
            visibleCityCount={visibleCityCount}
          />
        </div>
      </Card>

      <CityExplorerDetailDrawer
        activeCityDetail={activeCityDetail}
        activeDetailProfile={activeDetailProfile}
        favoriteCities={favoriteCities}
        isDetailOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        onUsePrompt={onUsePrompt}
      />
    </div>
  );
}
