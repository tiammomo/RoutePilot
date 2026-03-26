'use client';

import React from 'react';
import { Checkbox } from 'antd';
import type { ChecklistItem } from '@/utils/travelPlan';
import { ChecklistStatusTag } from './ChecklistStatusTag';

interface ChecklistItemRowProps {
  item: ChecklistItem;
  completed: boolean;
  itemKey: string;
  onToggleChecklist: (itemId: string, checked: boolean) => void;
}

export const ChecklistItemRow: React.FC<ChecklistItemRowProps> = ({ item, completed, itemKey, onToggleChecklist }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
      borderRadius: 12,
      padding: '10px 12px',
      border: completed ? '1px solid #bbf7d0' : '1px solid #dbeafe',
      background: completed ? '#f0fdf4' : '#f8fafc',
    }}
  >
    <Checkbox key={itemKey} checked={completed} onChange={(event) => onToggleChecklist(item.id, event.target.checked)}>
      {item.label}
    </Checkbox>
    <ChecklistStatusTag completed={completed} />
  </div>
);
