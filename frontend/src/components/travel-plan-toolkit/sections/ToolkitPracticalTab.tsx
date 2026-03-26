'use client';

import React from 'react';
import { InfoCircleOutlined } from '@ant-design/icons';
import type { PracticalInfoCard } from '@/utils/travelPlan';
import { practicalToneStyle } from '../shared';

interface ToolkitPracticalTabProps {
  messageId: string;
  practicalInfo: PracticalInfoCard[];
}

export const ToolkitPracticalTab: React.FC<ToolkitPracticalTabProps> = ({ messageId, practicalInfo }) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
      gap: 10,
    }}
  >
    {practicalInfo.map((item) => {
      const tone = practicalToneStyle(item.tone);
      return (
        <div
          key={`${messageId}-practical-${item.id}`}
          style={{
            borderRadius: 14,
            padding: 14,
            background: tone.background,
            border: `1px solid ${tone.border}`,
            color: tone.color,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <InfoCircleOutlined />
            <div style={{ fontWeight: 700 }}>{item.title}</div>
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>{item.value}</div>
        </div>
      );
    })}
  </div>
);
