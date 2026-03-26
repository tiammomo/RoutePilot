'use client';

import React from 'react';
import type { ChecklistItem } from '@/utils/travelPlan';
import { ChecklistList } from './checklist-tab/ChecklistList';

interface ToolkitChecklistTabProps {
  checklist: ChecklistItem[];
  completedChecklist: Record<string, boolean>;
  messageId: string;
  onToggleChecklist: (itemId: string, checked: boolean) => void;
}

export const ToolkitChecklistTab: React.FC<ToolkitChecklistTabProps> = ({
  checklist,
  completedChecklist,
  messageId,
  onToggleChecklist,
}) => (
  <ChecklistList
    checklist={checklist}
    completedChecklist={completedChecklist}
    messageId={messageId}
    onToggleChecklist={onToggleChecklist}
  />
);
