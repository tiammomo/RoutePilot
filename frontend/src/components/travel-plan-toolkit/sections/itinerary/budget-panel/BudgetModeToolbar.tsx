'use client';

import React from 'react';
import { Button, Slider, Space, Tag, Tooltip } from 'antd';
import { FileImageOutlined, FundOutlined, ShareAltOutlined } from '@ant-design/icons';
import { modeToSliderValue, sliderToMode, type BudgetMode } from '../../../shared';

interface BudgetModeToolbarProps {
  budgetMode: BudgetMode;
  onBudgetModeChange: (mode: BudgetMode) => void;
  onExportImage: () => void;
  onShare: () => void;
}

function budgetModeColor(mode: BudgetMode): 'blue' | 'gold' | 'green' {
  if (mode === 'saving') return 'blue';
  if (mode === 'balanced') return 'gold';
  return 'green';
}

function budgetModeLabel(mode: BudgetMode): string {
  if (mode === 'saving') return '省钱';
  if (mode === 'balanced') return '均衡';
  return '舒适';
}

export const BudgetModeToolbar: React.FC<BudgetModeToolbarProps> = ({
  budgetMode,
  onBudgetModeChange,
  onExportImage,
  onShare,
}) => (
  <div style={{ display: 'grid', gap: 10 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
      <Space>
        <FundOutlined style={{ color: '#0f766e' }} />
        <span style={{ fontSize: 13, color: '#334155' }}>预算档位</span>
        <Tag color={budgetModeColor(budgetMode)}>{budgetModeLabel(budgetMode)}</Tag>
      </Space>
      <Space>
        <Tooltip title="导出图片长图">
          <Button aria-label="导出旅行方案图片" size="small" icon={<FileImageOutlined />} onClick={onExportImage} />
        </Tooltip>
        <Tooltip title="生成可分享短链">
          <Button aria-label="分享旅行方案" size="small" icon={<ShareAltOutlined />} onClick={onShare} />
        </Tooltip>
      </Space>
    </div>

    <Slider
      min={0}
      max={100}
      value={modeToSliderValue(budgetMode)}
      marks={{ 10: '省钱', 50: '均衡', 90: '舒适' }}
      onChange={(value) => onBudgetModeChange(sliderToMode(Array.isArray(value) ? value[0] : value))}
    />
  </div>
);
