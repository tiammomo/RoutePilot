'use client';

import React from 'react';
import { Button, Tag } from 'antd';
import { CompassOutlined, HeartFilled, SwapOutlined } from '@ant-design/icons';
import type { CitySummary } from '@/types';
import { buildCityProfile, buildPlanPrompt, CURATED_PROMPTS } from '../shared';

interface CityExplorerHeroProps {
  compareCities: CitySummary[];
  favoriteCities: CitySummary[];
  onUsePrompt: (prompt: string) => void;
  summaryText: string;
}

export const CityExplorerHero: React.FC<CityExplorerHeroProps> = ({
  compareCities,
  favoriteCities,
  onUsePrompt,
  summaryText,
}) => (
  <div
    style={{
      display: 'grid',
      gap: 16,
      position: 'relative',
      zIndex: 1,
    }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
      <div style={{ display: 'flex', gap: 12 }}>
        <div
          style={{
            width: 42,
            height: 42,
            borderRadius: 14,
            display: 'grid',
            placeItems: 'center',
            background: 'linear-gradient(135deg, #0c4a6e 0%, #0f766e 100%)',
            boxShadow: '0 10px 24px rgba(2, 132, 199, 0.35)',
          }}
        >
          <CompassOutlined style={{ color: '#f0f9ff', fontSize: 20 }} />
        </div>
        <div>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: 0.2, color: '#0f172a', marginBottom: 4 }}>城市探索</div>
          <div style={{ fontSize: 13, color: '#475569', maxWidth: 760, lineHeight: 1.75 }}>
            当前只展示真实策展城市库，详情中的景点名称、区位和备注都来自人工整理，不再混入模板化生成城市。
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <div
          style={{
            display: 'grid',
            gap: 2,
            minWidth: 190,
            maxWidth: 260,
            padding: '8px 12px',
            borderRadius: 12,
            border: '1px solid #bfdbfe',
            background: 'linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%)',
          }}
        >
          <span style={{ fontSize: 11, color: '#1d4ed8', fontWeight: 700 }}>当前视图</span>
          <span style={{ fontSize: 12, color: '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {summaryText}
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 12px',
            borderRadius: 12,
            border: '1px solid rgba(245, 158, 11, 0.35)',
            background: compareCities.length > 0 ? 'linear-gradient(180deg, #fff7ed 0%, #fffbeb 100%)' : '#ffffff',
            color: compareCities.length > 0 ? '#92400e' : '#64748b',
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          <SwapOutlined />
          对比池 {compareCities.length}/3
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 12px',
            borderRadius: 12,
            border: '1px solid rgba(239, 68, 68, 0.3)',
            background: favoriteCities.length > 0 ? 'linear-gradient(180deg, #fff1f2 0%, #fff7f7 100%)' : '#ffffff',
            color: favoriteCities.length > 0 ? '#be123c' : '#64748b',
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          <HeartFilled style={{ color: favoriteCities.length > 0 ? '#e11d48' : '#94a3b8' }} />
          候选池 {favoriteCities.length}
        </div>
      </div>
    </div>

    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: 16,
        alignItems: 'stretch',
      }}
    >
      <div
        style={{
          borderRadius: 20,
          padding: 20,
          background: 'linear-gradient(180deg, rgba(255,255,255,0.98) 0%, #f8fbff 100%)',
          border: '1px solid #dbe4ee',
          boxShadow: '0 14px 30px rgba(15, 23, 42, 0.08)',
          color: '#0f172a',
          display: 'grid',
          gap: 16,
          alignContent: 'start',
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            width: 'fit-content',
            padding: '6px 10px',
            borderRadius: 999,
            border: '1px solid #dbeafe',
            background: '#eff6ff',
            color: '#1d4ed8',
            fontSize: 12,
            fontWeight: 700,
          }}
        >
          <CompassOutlined />
          灵感起点
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ fontSize: 24, fontWeight: 800, lineHeight: 1.2, color: '#0f172a', maxWidth: 520 }}>
            从场景出发，找到对的城市
          </div>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 10,
          }}
        >
          {CURATED_PROMPTS.map((item) => (
            <Button
              key={item.label}
              block
              style={{
                height: '100%',
                minHeight: 92,
                padding: '14px 16px',
                borderRadius: 16,
                border: `1px solid ${item.borderColor}`,
                background: item.background,
                color: '#0f172a',
                boxShadow: 'none',
                whiteSpace: 'normal',
              }}
              onClick={() => onUsePrompt(item.prompt)}
            >
              <div style={{ display: 'grid', gap: 6, textAlign: 'left' }}>
                <span style={{ fontSize: 16, fontWeight: 700 }}>{item.label}</span>
                <span style={{ fontSize: 12, lineHeight: 1.65, color: '#64748b', fontWeight: 500 }}>{item.hint}</span>
              </div>
            </Button>
          ))}
        </div>
      </div>

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
                style={{ borderRadius: 999, border: 'none', background: 'linear-gradient(135deg, #0284c7 0%, #0f766e 100%)' }}
                onClick={() => onUsePrompt(buildPlanPrompt(city.name))}
              >
                去规划
              </Button>
            </div>
          ))
        )}
      </div>
    </div>
  </div>
);
