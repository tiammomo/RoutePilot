'use client';

import React from 'react';
import { Card } from 'antd';
import type { ReminderItem } from '@/utils/travelPlan';
import { ReminderCardContent } from './ReminderCardContent';

interface RemindersListProps {
  messageId: string;
  reminders: ReminderItem[];
}

export const RemindersList: React.FC<RemindersListProps> = ({ messageId, reminders }) => (
  <div style={{ display: 'grid', gap: 10 }}>
    {reminders.map((item) => (
      <Card key={`${messageId}-${item.id}`} size="small">
        <ReminderCardContent item={item} />
      </Card>
    ))}
  </div>
);
