'use client';

import React from 'react';
import { Button, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PlanVariant } from '@/utils/travelPlan';
import type { CompareRow } from '../shared';

interface ToolkitCompareTabProps {
  variants: PlanVariant[];
  onChooseVariant: (variant: PlanVariant) => void;
}

export const ToolkitCompareTab: React.FC<ToolkitCompareTabProps> = ({ variants, onChooseVariant }) => {
  if (variants.length < 2) {
    return <div style={{ fontSize: 13, color: '#64748b' }}>未检测到 2 套以上可比较方案，尝试在提问中加入“省钱版 vs 轻松版”。</div>;
  }

  const compareColumns: ColumnsType<CompareRow> = [
    {
      title: '对比项',
      dataIndex: 'metric',
      key: 'metric',
      width: 120,
      fixed: 'left',
    },
    ...variants.map((variant) => ({
      title: variant.title,
      dataIndex: ['values', variant.id],
      key: variant.id,
      render: (_: string, row: CompareRow) => row.values[variant.id] || '-',
    })),
  ];

  const compareRows: CompareRow[] = [
    {
      key: 'positioning',
      metric: '方案定位',
      values: Object.fromEntries(variants.map((variant) => [variant.id, variant.title])),
    },
    {
      key: 'highlights',
      metric: '核心亮点',
      values: Object.fromEntries(
        variants.map((variant) => {
          const lines = variant.content
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean);
          return [variant.id, lines.slice(0, 3).join('；') || '-'];
        })
      ),
    },
    {
      key: 'suitable',
      metric: '适合人群',
      values: Object.fromEntries(
        variants.map((variant) => {
          const lower = variant.title.toLowerCase();
          if (lower.includes('省')) return [variant.id, '预算优先 / 行程紧凑'];
          if (lower.includes('舒') || lower.includes('轻松')) return [variant.id, '体验优先 / 节奏轻松'];
          return [variant.id, '综合平衡 / 首次出行'];
        })
      ),
    },
  ];

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Table size="small" pagination={false} rowKey="key" columns={compareColumns} dataSource={compareRows} scroll={{ x: 720 }} />

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {variants.map((variant) => (
          <Button key={variant.id} onClick={() => onChooseVariant(variant)}>
            选中“{variant.title}”继续细化
          </Button>
        ))}
      </div>
    </div>
  );
};
