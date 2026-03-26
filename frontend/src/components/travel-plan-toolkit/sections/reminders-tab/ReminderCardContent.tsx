'use client';

import React from 'react';
import { Space } from 'antd';
import type { ReminderItem } from '@/utils/travelPlan';
import { ReminderPhaseTag } from './ReminderPhaseTag';

interface ReminderCardContentProps {
  item: ReminderItem;
}

export const ReminderCardContent: React.FC<ReminderCardContentProps> = ({ item }) => (
  <Space orientation="vertical" size={2}>
    <ReminderPhaseTag phase={item.phase} />
    <div style={{ fontWeight: 600 }}>{item.title}</div>
    <div style={{ fontSize: 13, color: '#475569' }}>{item.detail}</div>
  </Space>
);
