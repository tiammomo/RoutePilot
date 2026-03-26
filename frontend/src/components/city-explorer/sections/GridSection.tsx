'use client';

import React from 'react';
import { Alert, Button, Card, Empty, Space, Spin, Tag } from 'antd';
import { HeartFilled, HeartOutlined, RiseOutlined } from '@ant-design/icons';
import type { CitySummary } from '@/types';
import { buildCityProfile, boolLabel, budgetLabel, buildPlanPrompt, foodLabel, seasonLabel, walkLabel } from '../shared';

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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 13, color: '#475569' }}>
          已展示 <span style={{ fontWeight: 700, color: '#0f172a' }}>{displayedCities.length}</span> / {filteredCities.length} 座城市
        </div>
        <Space wrap size={8}>
          {filteredCities.length > visibleCityCount && (
            <Button size="small" onClick={() => setVisibleCityCount((count) => count + loadMoreCityCount)}>
              再看 24 个
            </Button>
          )}
          {visibleCityCount > initialVisibleCityCount && (
            <Button size="small" onClick={() => setVisibleCityCount(initialVisibleCityCount)}>
              收起列表
            </Button>
          )}
        </Space>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
        {displayedCities.map((city) => {
          const profile = buildCityProfile(city);
          const inCompare = compareCityIds.includes(city.id);
          const favorite = favoriteCityIds.includes(city.id);

          return (
            <Card
              key={city.id}
              size="small"
              style={{
                borderRadius: 16,
                border: inCompare ? '1px solid #f59e0b' : '1px solid #e2e8f0',
                background: inCompare
                  ? 'linear-gradient(180deg, #fffaf0 0%, #ffffff 100%)'
                  : 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              }}
              styles={{ body: { padding: 12 } }}
            >
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 17, fontWeight: 700, color: '#0f172a' }}>{city.name}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{city.region}</div>
                  </div>
                  <Button
                    type="text"
                    size="small"
                    aria-label={favorite ? `取消收藏 ${city.name}` : `收藏 ${city.name}`}
                    icon={favorite ? <HeartFilled style={{ color: '#ef4444' }} /> : <HeartOutlined />}
                    onClick={() => onToggleFavoriteCity(city.id)}
                  />
                </div>

                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                    {budgetLabel(profile.budgetLevel)}
                  </Tag>
                  <Tag color="green" style={{ marginInlineEnd: 0 }}>
                    {profile.tripDuration}
                  </Tag>
                  <Tag color="purple" style={{ marginInlineEnd: 0 }}>
                    {profile.styleLabel}
                  </Tag>
                  <Tag color="cyan" style={{ marginInlineEnd: 0 }}>
                    {seasonLabel(city.best_seasons)}
                  </Tag>
                </div>

                <div style={{ fontSize: 12, lineHeight: 1.65, color: '#334155', minHeight: 58 }}>{profile.recommendation}</div>

                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {city.tags.slice(0, 3).map((tag) => (
                    <Tag key={`${city.id}-${tag}`} style={{ marginBottom: 4 }}>
                      {tag}
                    </Tag>
                  ))}
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 6,
                    fontSize: 12,
                    color: '#475569',
                    background: '#f8fafc',
                    borderRadius: 10,
                    padding: 8,
                  }}
                >
                  <div>人均预算：￥{city.avg_budget_per_day}</div>
                  <div>步行强度：{walkLabel(profile.walkIntensity)}</div>
                  <div>雨天适配：{boolLabel(profile.rainFriendly)}</div>
                  <div>亲子友好：{boolLabel(profile.familyFriendly)}</div>
                  <div>美食指数：{foodLabel(profile.foodFriendly)}</div>
                  <div>数据来源：{city.data_source}</div>
                </div>

                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <Button size="small" aria-label={`查看${city.name}详情`} onClick={() => onOpenCityDetail(city.id)}>
                    详情
                  </Button>
                  <Button
                    size="small"
                    aria-label={`${inCompare ? '移出对比' : '加入对比'} ${city.name}`}
                    icon={<RiseOutlined />}
                    onClick={() => onToggleCompareCity(city.id)}
                  >
                    {inCompare ? '移出对比' : '加入对比'}
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    aria-label={`规划 ${city.name}`}
                    onClick={() => onUsePrompt(buildPlanPrompt(city.name))}
                  >
                    规划
                  </Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
};
