'use client';

import React from 'react';
import type { CitySummary } from '@/types';
import { boolLabel, foodLabel, type DerivedCityProfile, walkLabel } from '../../shared';

interface CityGridCardMetricsProps {
  city: CitySummary;
  profile: DerivedCityProfile;
}

export const CityGridCardMetrics: React.FC<CityGridCardMetricsProps> = ({ city, profile }) => (
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
    <div>人均预算：¥{city.avg_budget_per_day}</div>
    <div>步行强度：{walkLabel(profile.walkIntensity)}</div>
    <div>雨天适配：{boolLabel(profile.rainFriendly)}</div>
    <div>亲子友好：{boolLabel(profile.familyFriendly)}</div>
    <div>美食指数：{foodLabel(profile.foodFriendly)}</div>
    <div>数据来源：{city.data_source}</div>
  </div>
);
