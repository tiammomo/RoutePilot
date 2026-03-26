'use client';

import React from 'react';
import type { ChecklistItem } from '@/utils/travelPlan';
import { ChecklistItemRow } from './ChecklistItemRow';

interface ChecklistListProps {
  checklist: ChecklistItem[];
  completedChecklist: Record<string, boolean>;
  messageId: string;
  onToggleChecklist: (itemId: string, checked: boolean) => void;
}

export const ChecklistList: React.FC<ChecklistListProps> = ({
  checklist,
  completedChecklist,
  messageId,
  onToggleChecklist,
}) => (
  <div style={{ display: 'grid', gap: 8 }}>
    {checklist.map((item) => (
      <ChecklistItemRow
        key={`${messageId}-${item.id}`}
        item={item}
        itemKey={`${messageId}-${item.id}`}
        completed={Boolean(completedChecklist[item.id])}
        onToggleChecklist={onToggleChecklist}
      />
    ))}
  </div>
);
