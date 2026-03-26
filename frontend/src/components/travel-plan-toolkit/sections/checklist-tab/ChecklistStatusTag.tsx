'use client';

import React from 'react';
import { checklistStatusMeta } from '../../shared';

interface ChecklistStatusTagProps {
  completed: boolean;
}

export const ChecklistStatusTag: React.FC<ChecklistStatusTagProps> = ({ completed }) => {
  const meta = checklistStatusMeta(completed);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        borderRadius: 999,
        padding: '2px 8px',
        fontSize: 11,
        fontWeight: 700,
        background: meta.background,
        border: `1px solid ${meta.border}`,
        color: meta.color,
      }}
    >
      {meta.label}
    </span>
  );
};
