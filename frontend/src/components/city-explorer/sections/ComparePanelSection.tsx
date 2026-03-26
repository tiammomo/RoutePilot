'use client';

import React from 'react';
import { Button, Card, Space, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { SwapOutlined } from '@ant-design/icons';
import type { CitySummary } from '@/types';
import { buildCityProfile, budgetLabel, buildComparePrompt, type CompareTableRow, seasonLabel, walkLabel } from '../shared';

interface CityExplorerComparePanelProps {
  compareCities: CitySummary[];
  onClearCompare: () => void;
  onUsePrompt: (prompt: string) => void;
}

export const CityExplorerComparePanel: React.FC<CityExplorerComparePanelProps> = ({
  compareCities,
  onClearCompare,
  onUsePrompt,
}) => {
  if (compareCities.length === 0) return null;

  const compareColumns: ColumnsType<CompareTableRow> = [
    {
      title: '\u5bf9\u6bd4\u9879',
      dataIndex: 'metric',
      key: 'metric',
      width: 140,
      fixed: 'left',
      render: (value: string) => <span style={{ fontWeight: 700, color: '#1f2937' }}>{value}</span>,
    },
    ...compareCities.map((city) => ({
      title: city.name,
      dataIndex: ['values', city.id],
      key: city.id,
      width: 220,
      render: (_value: string, row: CompareTableRow) => (
        <div style={{ whiteSpace: 'pre-wrap', color: '#334155', lineHeight: 1.7 }}>{row.values[city.id] || '-'}</div>
      ),
    })),
  ];

  const compareRows: CompareTableRow[] = [
    {
      key: 'region',
      metric: '\u5730\u533a',
      values: Object.fromEntries(compareCities.map((city) => [city.id, city.region])),
    },
    {
      key: 'budget',
      metric: '\u9884\u7b97',
      values: Object.fromEntries(
        compareCities.map((city) => [city.id, `\u00a5${city.avg_budget_per_day} / ${budgetLabel(buildCityProfile(city).budgetLevel)}`])
      ),
    },
    {
      key: 'days',
      metric: '\u9002\u5408\u5929\u6570',
      values: Object.fromEntries(compareCities.map((city) => [city.id, buildCityProfile(city).tripDuration])),
    },
    {
      key: 'walk',
      metric: '\u6b65\u884c\u5f3a\u5ea6',
      values: Object.fromEntries(compareCities.map((city) => [city.id, walkLabel(buildCityProfile(city).walkIntensity)])),
    },
    {
      key: 'season',
      metric: '\u5408\u9002\u5b63\u8282',
      values: Object.fromEntries(compareCities.map((city) => [city.id, seasonLabel(city.best_seasons)])),
    },
    {
      key: 'style',
      metric: '\u65c5\u884c\u6c14\u8d28',
      values: Object.fromEntries(compareCities.map((city) => [city.id, buildCityProfile(city).styleLabel])),
    },
    {
      key: 'note',
      metric: '\u7f16\u8f91\u5efa\u8bae',
      values: Object.fromEntries(compareCities.map((city) => [city.id, buildCityProfile(city).recommendation])),
    },
  ];

  return (
    <Card
      size="small"
      style={{ borderRadius: 16, border: '1px solid #fde68a', background: 'linear-gradient(180deg, #fffdf2 0%, #ffffff 100%)' }}
      styles={{ body: { padding: 14 } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#92400e' }}>{'\u57ce\u5e02\u5bf9\u6bd4\u6c60'}</div>
          <div style={{ fontSize: 12, color: '#78716c' }}>
            {'\u6700\u591a\u653e 3 \u4e2a\u771f\u5b9e\u57ce\u5e02\uff0c\u5feb\u901f\u6bd4\u8f83\u540e\u76f4\u63a5\u7ee7\u7eed\u89c4\u5212\u3002'}
          </div>
        </div>
        <Space wrap>
          <Button icon={<SwapOutlined />} onClick={() => onUsePrompt(buildComparePrompt(compareCities.map((city) => city.name)))}>
            {'\u8ba9\u52a9\u624b\u5bf9\u6bd4'}
          </Button>
          <Button onClick={onClearCompare}>{'\u6e05\u7a7a'}</Button>
        </Space>
      </div>
      <Table size="small" pagination={false} rowKey="key" columns={compareColumns} dataSource={compareRows} scroll={{ x: 780 }} />
    </Card>
  );
};
