'use client';

import React from 'react';
import { Button, Divider, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { DayPlanCard, ItineraryConflict } from '@/utils/travelPlan';

interface ConflictCardContentProps {
  conflicts: ItineraryConflict[];
  day: DayPlanCard;
  dayIndex: number;
  dayKey: string;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
}

function severityColor(severity: ItineraryConflict['severity']): 'red' | 'orange' | 'gold' {
  if (severity === 'high') return 'red';
  if (severity === 'medium') return 'orange';
  return 'gold';
}

export const ConflictCardContent: React.FC<ConflictCardContentProps> = ({
  conflicts,
  day,
  dayIndex,
  dayKey,
  onOneClickFix,
}) => {
  if (conflicts.length === 0) {
    return <span style={{ fontSize: 13, color: '#16a34a' }}>无冲突</span>;
  }

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {conflicts.map((conflict) => (
        <div key={`${dayKey}-${conflict.id}`}>
          <Tag color={severityColor(conflict.severity)}>{conflict.type}</Tag>
          <div style={{ fontWeight: 600, marginTop: 2 }}>{conflict.title}</div>
          <div style={{ fontSize: 13, color: '#475569' }}>{conflict.description}</div>
          <div style={{ fontSize: 12, color: '#7c3aed' }}>建议：{conflict.suggestion}</div>
        </div>
      ))}
      <Divider style={{ margin: '6px 0' }} />
      <Button size="small" icon={<ReloadOutlined />} onClick={() => onOneClickFix(dayKey, dayIndex, day)}>
        一键修复此日
      </Button>
    </div>
  );
};
