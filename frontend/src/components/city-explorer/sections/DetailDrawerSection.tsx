'use client';

import React from 'react';
import { Button, Card, Drawer, Space, Tag } from 'antd';
import { EnvironmentOutlined } from '@ant-design/icons';
import type { CityDetail, CitySummary } from '@/types';
import { budgetLabel, buildComparePrompt, buildPlanPrompt, type DerivedCityProfile, seasonLabel, walkLabel } from '../shared';

interface CityExplorerDetailDrawerProps {
  activeCityDetail: CityDetail | null;
  activeDetailProfile: DerivedCityProfile | null;
  favoriteCities: CitySummary[];
  isDetailOpen: boolean;
  onClose: () => void;
  onUsePrompt: (prompt: string) => void;
}

export const CityExplorerDetailDrawer: React.FC<CityExplorerDetailDrawerProps> = ({
  activeCityDetail,
  activeDetailProfile,
  favoriteCities,
  isDetailOpen,
  onClose,
  onUsePrompt,
}) => (
  <Drawer
    title={
      <span>
        <EnvironmentOutlined style={{ marginRight: 8 }} />
        {activeCityDetail?.name || '\u57ce\u5e02\u8be6\u60c5'}
      </span>
    }
    open={isDetailOpen}
    onClose={onClose}
    size="large"
  >
    {activeCityDetail && activeDetailProfile && (
      <div style={{ display: 'grid', gap: 14 }}>
        <Card size="small" style={{ borderRadius: 14 }}>
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#0f172a' }}>{'\u57ce\u5e02\u6c14\u8d28'}</div>
            <div style={{ color: '#334155', lineHeight: 1.8 }}>{activeCityDetail.description}</div>
            <div style={{ fontSize: 13, color: '#475569' }}>{activeDetailProfile.recommendation}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Tag color="blue">{budgetLabel(activeDetailProfile.budgetLevel)}</Tag>
              <Tag color="green">{activeDetailProfile.tripDuration}</Tag>
              <Tag color="purple">{activeDetailProfile.styleLabel}</Tag>
              <Tag color="cyan">{walkLabel(activeDetailProfile.walkIntensity)}</Tag>
              <Tag color="gold">{'\u771f\u5b9e\u7b56\u5c55'}</Tag>
            </div>
          </div>
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
          <Card size="small" styles={{ body: { padding: 12 } }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{'\u4eba\u5747\u9884\u7b97'}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{`\u00a5${activeCityDetail.avg_budget_per_day}`}</div>
          </Card>
          <Card size="small" styles={{ body: { padding: 12 } }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{'\u5bb6\u5ead\u9884\u7b97'}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#111827' }}>{`\u00a5${Math.round(activeCityDetail.avg_budget_per_day * 2.4)}`}</div>
          </Card>
          <Card size="small" styles={{ body: { padding: 12 } }}>
            <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{'\u6700\u4f73\u5b63\u8282'}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827' }}>{seasonLabel(activeCityDetail.best_seasons)}</div>
          </Card>
        </div>

        <Card size="small" title={'\u600e\u4e48\u73a9\u66f4\u987a'}>
          <div style={{ display: 'grid', gap: 8, fontSize: 13, color: '#475569' }}>
            <div>{`\u63a8\u8350\u8282\u594f\uff1a${activeDetailProfile.tripDuration}\uff0c\u5148\u5b89\u6392\u6838\u5fc3\u7247\u533a\uff0c\u518d\u505a\u8de8\u533a\u5ef6\u5c55\u3002`}</div>
            <div>
              {activeDetailProfile.rainFriendly
                ? '\u96e8\u5929\u7b56\u7565\uff1a\u53ef\u4fdd\u7559\u5927\u90e8\u5206\u884c\u7a0b\uff0c\u4f18\u5148\u9986\u548c\u8857\u533a\u3002'
                : '\u96e8\u5929\u7b56\u7565\uff1a\u5efa\u8bae\u9884\u7559 1-2 \u4e2a\u5ba4\u5185\u5907\u9009\u70b9\u3002'}
            </div>
            <div>
              {`\u4f53\u529b\u7ba1\u7406\uff1a${walkLabel(activeDetailProfile.walkIntensity)}\uff0c\u4e0d\u8981\u628a\u9ad8\u5bc6\u5ea6\u6253\u5361\u5168\u5806\u5728\u540c\u4e00\u5929\u3002`}
            </div>
          </div>
        </Card>

        <Card size="small" title={'\u6838\u5fc3\u666f\u70b9'}>
          <div style={{ display: 'grid', gap: 8 }}>
            {activeCityDetail.attractions.map((attraction) => (
              <div
                key={attraction.name}
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: 12,
                  padding: '10px 12px',
                  background: '#ffffff',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <div style={{ fontWeight: 700, color: '#1f2937' }}>{attraction.name}</div>
                  <Tag color="geekblue">{attraction.type}</Tag>
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                  {`\u5efa\u8bae\u505c\u7559 ${attraction.duration} / \u95e8\u7968 \u00a5${attraction.ticket}${attraction.district ? ` / ${attraction.district}` : ''}`}
                </div>
                {attraction.note && <div style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>{attraction.note}</div>}
              </div>
            ))}
          </div>
        </Card>

        <Card size="small" title={'\u4e0b\u4e00\u6b65'}>
          <Space wrap>
            <Button type="primary" onClick={() => onUsePrompt(buildPlanPrompt(activeCityDetail.name))}>
              {'\u76f4\u63a5\u89c4\u5212\u8fd9\u5ea7\u57ce\u5e02'}
            </Button>
            <Button onClick={() => onUsePrompt(buildComparePrompt([activeCityDetail.name, ...favoriteCities.slice(0, 2).map((city) => city.name)]))}>
              {'\u548c\u5019\u9009\u57ce\u5e02\u5bf9\u6bd4'}
            </Button>
          </Space>
        </Card>
      </div>
    )}
  </Drawer>
);
