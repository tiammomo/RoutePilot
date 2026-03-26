'use client';

import React from 'react';
import { Checkbox } from 'antd';
import type { ChecklistItem } from '@/utils/travelPlan';

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
  <div style={{ display: 'grid', gap: 8 }}>
    {checklist.map((item) => (
      <Checkbox
        key={`${messageId}-${item.id}`}
        checked={Boolean(completedChecklist[item.id])}
        onChange={(event) => onToggleChecklist(item.id, event.target.checked)}
      >
        {item.label}
      </Checkbox>
    ))}
  </div>
);
