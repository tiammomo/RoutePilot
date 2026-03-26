'use client';

import React from 'react';
import { Button, Card, Progress, Slider, Space, Statistic, Tag, Tooltip } from 'antd';
import { FileImageOutlined, FundOutlined, ShareAltOutlined } from '@ant-design/icons';
import type { BudgetProjection, ConfidenceSummary } from '@/utils/travelPlan';
import { modeToSliderValue, sliderToMode, type BudgetMode, type QuickRefineAction } from '../../shared';

interface ItineraryBudgetPanelProps {
  budgetMode: BudgetMode;
  budgetProjection: BudgetProjection;
  childFriendlyBudget: number;
  confidence: ConfidenceSummary;
  familyBudget: number;
  onBudgetModeChange: (mode: BudgetMode) => void;
  onExportImage: () => void;
  onQuickRefine: (action: QuickRefineAction) => void;
  onShare: () => void;
  quickRefineActions: QuickRefineAction[];
}

export const ItineraryBudgetPanel: React.FC<ItineraryBudgetPanelProps> = ({
  budgetMode,
  budgetProjection,
  childFriendlyBudget,
  confidence,
  familyBudget,
  onBudgetModeChange,
  onExportImage,
  onQuickRefine,
  onShare,
  quickRefineActions,
}) => (
  <Card size="small">
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <Space>
          <FundOutlined style={{ color: '#0f766e' }} />
          <span style={{ fontSize: 13, color: '#334155' }}>预算档位</span>
          <Tag color={budgetMode === 'saving' ? 'blue' : budgetMode === 'balanced' ? 'gold' : 'green'}>
            {budgetMode === 'saving' ? '省钱' : budgetMode === 'balanced' ? '均衡' : '舒适'}
          </Tag>
        </Space>
        <Space>
          <Tooltip title="导出图片长图">
            <Button size="small" icon={<FileImageOutlined />} onClick={onExportImage} />
          </Tooltip>
          <Tooltip title="生成可分享短链">
            <Button size="small" icon={<ShareAltOutlined />} onClick={onShare} />
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

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Tag color="blue">总预算：¥{budgetProjection.totalBudget}</Tag>
        <Tag color="cyan">住宿：{Math.round(budgetProjection.hotelShare * 100)}%</Tag>
        <Tag color="orange">餐饮：{Math.round(budgetProjection.foodShare * 100)}%</Tag>
        <Tag color="purple">交通：{Math.round(budgetProjection.trafficShare * 100)}%</Tag>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: 10,
        }}
      >
        <Card size="small" styles={{ body: { padding: 10 } }}>
          <Statistic title="人均预估" value={budgetProjection.totalBudget} prefix="¥" styles={{ content: { fontSize: 18 } }} />
        </Card>
        <Card size="small" styles={{ body: { padding: 10 } }}>
          <Statistic title="家庭总价" value={familyBudget} prefix="¥" styles={{ content: { fontSize: 18 } }} />
        </Card>
        <Card size="small" styles={{ body: { padding: 10 } }}>
          <Statistic title="亲子轻量版" value={childFriendlyBudget} prefix="¥" styles={{ content: { fontSize: 18 } }} />
        </Card>
        <Card size="small" styles={{ body: { padding: 10 } }}>
          <Statistic title="日均预算" value={budgetProjection.perDayBudget} prefix="¥" styles={{ content: { fontSize: 18 } }} />
        </Card>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {quickRefineActions.map((action) => (
          <Button key={action.key} size="small" onClick={() => onQuickRefine(action)}>
            {action.label}
          </Button>
        ))}
      </div>

      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 13, color: '#334155' }}>结果可信度</span>
          <Tag color={confidence.level === 'high' ? 'green' : confidence.level === 'medium' ? 'gold' : 'red'}>
            {confidence.level}
          </Tag>
        </div>
        <Progress percent={confidence.score} size="small" />
        <div style={{ display: 'grid', gap: 4, marginTop: 6 }}>
          {confidence.risks.map((risk, index) => (
            <div key={`confidence-risk-${index}`} style={{ fontSize: 12, color: '#92400e' }}>
              风险提示：{risk}
            </div>
          ))}
        </div>
      </div>
    </div>
  </Card>
);
