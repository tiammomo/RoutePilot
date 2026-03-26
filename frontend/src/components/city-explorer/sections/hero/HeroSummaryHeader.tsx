'use client';

import React from 'react';
import { CompassOutlined, HeartFilled, SwapOutlined } from '@ant-design/icons';

interface HeroSummaryHeaderProps {
  compareCount: number;
  favoriteCount: number;
  summaryText: string;
}

function SummaryStatCard({
  accentColor,
  background,
  children,
}: {
  accentColor: string;
  background: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: 'grid',
        gap: 2,
        minWidth: 190,
        maxWidth: 260,
        padding: '8px 12px',
        borderRadius: 12,
        border: `1px solid ${accentColor}`,
        background,
      }}
    >
      {children}
    </div>
  );
}

export const HeroSummaryHeader: React.FC<HeroSummaryHeaderProps> = ({ compareCount, favoriteCount, summaryText }) => (
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
      <SummaryStatCard accentColor="#bfdbfe" background="linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%)">
        <span style={{ fontSize: 11, color: '#1d4ed8', fontWeight: 700 }}>当前视图</span>
        <span style={{ fontSize: 12, color: '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {summaryText}
        </span>
      </SummaryStatCard>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 12px',
          borderRadius: 12,
          border: '1px solid rgba(245, 158, 11, 0.35)',
          background: compareCount > 0 ? 'linear-gradient(180deg, #fff7ed 0%, #fffbeb 100%)' : '#ffffff',
          color: compareCount > 0 ? '#92400e' : '#64748b',
          fontSize: 13,
          fontWeight: 700,
        }}
      >
        <SwapOutlined />
        对比池 {compareCount}/3
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '8px 12px',
          borderRadius: 12,
          border: '1px solid rgba(239, 68, 68, 0.3)',
          background: favoriteCount > 0 ? 'linear-gradient(180deg, #fff1f2 0%, #fff7f7 100%)' : '#ffffff',
          color: favoriteCount > 0 ? '#be123c' : '#64748b',
          fontSize: 13,
          fontWeight: 700,
        }}
      >
        <HeartFilled style={{ color: favoriteCount > 0 ? '#e11d48' : '#94a3b8' }} />
        候选池 {favoriteCount}
      </div>
    </div>
  </div>
);
