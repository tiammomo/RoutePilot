'use client';

import React from 'react';
import { Tag } from 'antd';
import type { ReminderItem } from '@/utils/travelPlan';
import { reminderPhaseMeta } from '../../shared';

interface ReminderPhaseTagProps {
  phase: ReminderItem['phase'];
}

export const ReminderPhaseTag: React.FC<ReminderPhaseTagProps> = ({ phase }) => {
  const meta = reminderPhaseMeta(phase);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <Tag color={meta.color} style={{ marginInlineEnd: 0 }}>
        {phase}
      </Tag>
      <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>{meta.subtitle}</span>
    </div>
  );
};
