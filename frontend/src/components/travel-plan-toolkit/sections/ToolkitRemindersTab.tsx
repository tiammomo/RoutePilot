'use client';

import React from 'react';
import { Card, Space, Tag } from 'antd';
import type { ReminderItem } from '@/utils/travelPlan';

interface ToolkitRemindersTabProps {
  messageId: string;
  reminders: ReminderItem[];
}

export const ToolkitRemindersTab: React.FC<ToolkitRemindersTabProps> = ({ messageId, reminders }) => (
  <div style={{ display: 'grid', gap: 10 }}>
    {reminders.map((item) => (
      <Card key={`${messageId}-${item.id}`} size="small">
        <Space orientation="vertical" size={2}>
          <Tag color="blue">{item.phase}</Tag>
          <div style={{ fontWeight: 600 }}>{item.title}</div>
          <div style={{ fontSize: 13, color: '#475569' }}>{item.detail}</div>
        </Space>
      </Card>
    ))}
  </div>
);
