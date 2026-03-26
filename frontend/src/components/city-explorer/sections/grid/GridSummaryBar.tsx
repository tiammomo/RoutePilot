'use client';

import React from 'react';
import { Button, Space } from 'antd';

interface GridSummaryBarProps {
  displayedCityCount: number;
  filteredCityCount: number;
  initialVisibleCityCount: number;
  loadMoreCityCount: number;
  onLoadMore: () => void;
  onReset: () => void;
  visibleCityCount: number;
}

export const GridSummaryBar: React.FC<GridSummaryBarProps> = ({
  displayedCityCount,
  filteredCityCount,
  initialVisibleCityCount,
  loadMoreCityCount,
  onLoadMore,
  onReset,
  visibleCityCount,
}) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
    <div style={{ fontSize: 13, color: '#475569' }}>
      已展示 <span style={{ fontWeight: 700, color: '#0f172a' }}>{displayedCityCount}</span> / {filteredCityCount} 座城市
    </div>
    <Space wrap size={8}>
      {filteredCityCount > visibleCityCount && (
        <Button size="small" onClick={onLoadMore}>
          再看 {loadMoreCityCount} 个
        </Button>
      )}
      {visibleCityCount > initialVisibleCityCount && (
        <Button size="small" onClick={onReset}>
          收起列表
        </Button>
      )}
    </Space>
  </div>
);
