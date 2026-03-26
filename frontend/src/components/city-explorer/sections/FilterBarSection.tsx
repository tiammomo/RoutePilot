'use client';

import React from 'react';
import { Button, Select, Space } from 'antd';
import { QUICK_FILTERS, type QuickFilterKey } from '../shared';

interface CityExplorerFilterBarProps {
  isFilterLoading: boolean;
  onUsePrompt: (prompt: string) => void;
  regions: string[];
  selectedQuickFilters: QuickFilterKey[];
  selectedRegion: string | undefined;
  selectedTags: string[];
  tags: string[];
  toggleQuickFilter: (filterKey: QuickFilterKey) => void;
  setSelectedRegion: (value: string | undefined) => void;
  setSelectedTags: (value: string[]) => void;
}

export const CityExplorerFilterBar: React.FC<CityExplorerFilterBarProps> = ({
  isFilterLoading,
  onUsePrompt,
  regions,
  selectedQuickFilters,
  selectedRegion,
  selectedTags,
  tags,
  toggleQuickFilter,
  setSelectedRegion,
  setSelectedTags,
}) => (
  <div
    style={{
      border: '1px solid #dbe4ee',
      borderRadius: 16,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.9) 0%, #f8fbff 100%)',
      padding: 12,
      display: 'grid',
      gap: 10,
    }}
  >
    <Space wrap size={[10, 10]}>
      <Select
        allowClear
        loading={isFilterLoading}
        placeholder="按地区筛选城市"
        style={{ width: 190 }}
        value={selectedRegion}
        onChange={(value) => setSelectedRegion(value)}
        options={regions.map((item) => ({ label: item, value: item }))}
      />
      <Select
        mode="multiple"
        loading={isFilterLoading}
        placeholder="按标签缩小范围"
        style={{ width: 340, maxWidth: '100%' }}
        value={selectedTags}
        onChange={(value) => setSelectedTags(value)}
        options={tags.map((item) => ({ label: item, value: item }))}
      />
      <Button
        type="primary"
        style={{
          borderRadius: 999,
          border: 'none',
          background: 'linear-gradient(135deg, #0369a1 0%, #0f766e 100%)',
          boxShadow: '0 8px 20px rgba(14, 116, 144, 0.28)',
        }}
        onClick={() =>
          onUsePrompt(
            '请基于当前真实策展城市库，结合已选地区、标签和场景偏好，帮我筛出更适合的目的地，并说明推荐理由和不推荐的边界。'
          )
        }
      >
        让助手帮我选
      </Button>
    </Space>

    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {QUICK_FILTERS.map((filter) => {
        const active = selectedQuickFilters.includes(filter.key);
        return (
          <Button
            key={filter.key}
            size="small"
            type={active ? 'primary' : 'default'}
            onClick={() => toggleQuickFilter(filter.key)}
            style={
              active
                ? {
                    borderRadius: 999,
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #0284c7 0%, #0f766e 100%)',
                    borderColor: 'transparent',
                    boxShadow: '0 8px 16px rgba(2, 132, 199, 0.24)',
                  }
                : {
                    borderRadius: 999,
                    borderColor: '#cbd5e1',
                    color: '#334155',
                    background: '#ffffff',
                  }
            }
          >
            {filter.label}
          </Button>
        );
      })}
    </div>
  </div>
);
