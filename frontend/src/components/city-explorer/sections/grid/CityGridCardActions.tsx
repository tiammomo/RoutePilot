'use client';

import React from 'react';
import { Button } from 'antd';
import { RiseOutlined } from '@ant-design/icons';

interface CityGridCardActionsProps {
  cityName: string;
  inCompare: boolean;
  onOpenCityDetail: () => void;
  onToggleCompareCity: () => void;
  onUsePlanPrompt: () => void;
}

export const CityGridCardActions: React.FC<CityGridCardActionsProps> = ({
  cityName,
  inCompare,
  onOpenCityDetail,
  onToggleCompareCity,
  onUsePlanPrompt,
}) => (
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
    <Button size="small" aria-label={`查看${cityName}详情`} onClick={onOpenCityDetail}>
      详情
    </Button>
    <Button
      size="small"
      aria-label={`${inCompare ? '移出对比' : '加入对比'} ${cityName}`}
      icon={<RiseOutlined />}
      onClick={onToggleCompareCity}
    >
      {inCompare ? '移出对比' : '加入对比'}
    </Button>
    <Button size="small" type="primary" aria-label={`规划 ${cityName}`} onClick={onUsePlanPrompt}>
      规划
    </Button>
  </div>
);
