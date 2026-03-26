'use client';

import React from 'react';
import { Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PlanVariant } from '@/utils/travelPlan';
import type { CompareRow } from '../../shared';

interface VariantComparisonTableProps {
  variants: PlanVariant[];
}

function buildCompareRows(variants: PlanVariant[]): CompareRow[] {
  return [
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
}

function buildCompareColumns(variants: PlanVariant[]): ColumnsType<CompareRow> {
  return [
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
}

export const VariantComparisonTable: React.FC<VariantComparisonTableProps> = ({ variants }) => (
  <Table
    size="small"
    pagination={false}
    rowKey="key"
    columns={buildCompareColumns(variants)}
    dataSource={buildCompareRows(variants)}
    scroll={{ x: 720 }}
  />
);
