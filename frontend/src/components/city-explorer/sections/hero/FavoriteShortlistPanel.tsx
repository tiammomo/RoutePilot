'use client';

import React from 'react';
import { Button, Tag } from 'antd';
import type { CitySummary } from '@/types';
import { buildCityProfile, buildPlanPrompt } from '../../shared';

interface FavoriteShortlistPanelProps {
  favoriteCities: CitySummary[];
  onUsePrompt: (prompt: string) => void;
}

export const FavoriteShortlistPanel: React.FC<FavoriteShortlistPanelProps> = ({ favoriteCities, onUsePrompt }) => (
  <div
    style={{
      borderRadius: 20,
      padding: 18,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.96) 0%, #f8fafc 100%)',
      border: '1px solid #dbe4ee',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.8)',
      display: 'grid',
      gap: 10,
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
      <div style={{ fontSize: 16, fontWeight: 800, color: '#0f172a' }}>候选池</div>
      <Tag color="blue" style={{ marginInlineEnd: 0, borderRadius: 999, paddingInline: 10 }}>
        {favoriteCities.length}/4
      </Tag>
    </div>

    {favoriteCities.length === 0 ? (
      <div
        style={{
          minHeight: 108,
          borderRadius: 14,
          border: '1px dashed #cbd5e1',
          background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
          display: 'grid',
          placeItems: 'center',
          fontSize: 13,
          color: '#64748b',
          textAlign: 'center',
          padding: 12,
        }}
      >
        先把感兴趣的城市加入候选池，后面做对比和规划会更快。
      </div>
    ) : (
      favoriteCities.slice(0, 4).map((city) => (
        <div
          key={`favorite-${city.id}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            border: '1px solid #e2e8f0',
            borderRadius: 12,
            padding: '10px 12px',
            background: '#ffffff',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 700, color: '#1f2937' }}>{city.name}</div>
            <div
              style={{
                fontSize: 12,
                color: '#64748b',
                lineHeight: 1.55,
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {buildCityProfile(city).recommendation}
            </div>
          </div>
          <Button
            size="small"
            type="primary"
            aria-label={`规划候选城市 ${city.name}`}
            style={{ borderRadius: 999, border: 'none', background: 'linear-gradient(135deg, #0284c7 0%, #0f766e 100%)' }}
            onClick={() => onUsePrompt(buildPlanPrompt(city.name))}
          >
            去规划
          </Button>
        </div>
      ))
    )}
  </div>
);
