'use client';

import React from 'react';
import { Button, Card, Tag } from 'antd';
import { HeartFilled, HeartOutlined } from '@ant-design/icons';
import type { CitySummary } from '@/types';
import { buildCityProfile, budgetLabel, buildPlanPrompt, seasonLabel } from '../../shared';
import { CityGridCardActions } from './CityGridCardActions';
import { CityGridCardMetrics } from './CityGridCardMetrics';

interface CityGridCardProps {
  city: CitySummary;
  favorite: boolean;
  inCompare: boolean;
  onOpenCityDetail: (cityId: string) => void;
  onToggleCompareCity: (cityId: string) => void;
  onToggleFavoriteCity: (cityId: string) => void;
  onUsePrompt: (prompt: string) => void;
}

export const CityGridCard: React.FC<CityGridCardProps> = ({
  city,
  favorite,
  inCompare,
  onOpenCityDetail,
  onToggleCompareCity,
  onToggleFavoriteCity,
  onUsePrompt,
}) => {
  const profile = buildCityProfile(city);

  return (
    <Card
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

        <CityGridCardMetrics city={city} profile={profile} />

        <CityGridCardActions
          cityName={city.name}
          inCompare={inCompare}
          onOpenCityDetail={() => onOpenCityDetail(city.id)}
          onToggleCompareCity={() => onToggleCompareCity(city.id)}
          onUsePlanPrompt={() => onUsePrompt(buildPlanPrompt(city.name))}
        />
      </div>
    </Card>
  );
};
