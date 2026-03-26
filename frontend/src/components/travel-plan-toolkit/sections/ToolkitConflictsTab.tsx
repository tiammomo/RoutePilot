'use client';

import React from 'react';
import { Button, Card, Divider, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { DayPlanCard, ItineraryConflict } from '@/utils/travelPlan';
import type { CardEntry } from './types';

interface ToolkitConflictsTabProps {
  cardEntries: CardEntry[];
  conflictMap: Map<string, ItineraryConflict[]>;
  messageId: string;
  totalConflicts: number;
  onOneClickFix: (dayKey: string, dayIndex: number, day: DayPlanCard) => void;
}

export const ToolkitConflictsTab: React.FC<ToolkitConflictsTabProps> = ({
  cardEntries,
  conflictMap,
  messageId,
  totalConflicts,
  onOneClickFix,
}) => (
  <div style={{ display: 'grid', gap: 10 }}>
    <Tag color={totalConflicts > 0 ? 'orange' : 'green'}>
      {totalConflicts > 0 ? `检测到 ${totalConflicts} 个冲突风险` : '未检测到明显冲突'}
    </Tag>
    {cardEntries.map(({ day, dayIndex, dayKey }) => {
      const conflicts = conflictMap.get(dayKey) || [];
      if (conflicts.length === 0) {
        return (
          <Card key={`${messageId}-conflict-${dayKey}`} size="small" title={day.dayLabel}>
            <span style={{ fontSize: 13, color: '#16a34a' }}>无冲突</span>
          </Card>
        );
      }

      return (
        <Card key={`${messageId}-conflict-${dayKey}`} size="small" title={day.dayLabel}>
          <div style={{ display: 'grid', gap: 8 }}>
            {conflicts.map((conflict) => (
              <div key={`${dayKey}-${conflict.id}`}>
                <Tag color={conflict.severity === 'high' ? 'red' : conflict.severity === 'medium' ? 'orange' : 'gold'}>
                  {conflict.type}
                </Tag>
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
        </Card>
      );
    })}
  </div>
);
