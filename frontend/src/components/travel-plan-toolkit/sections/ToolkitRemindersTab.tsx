'use client';

import React from 'react';
import type { ReminderItem } from '@/utils/travelPlan';
import { RemindersList } from './reminders-tab/RemindersList';

interface ToolkitRemindersTabProps {
  messageId: string;
  reminders: ReminderItem[];
}

export const ToolkitRemindersTab: React.FC<ToolkitRemindersTabProps> = ({ messageId, reminders }) => (
  <RemindersList messageId={messageId} reminders={reminders} />
);
