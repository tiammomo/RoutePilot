'use client';

import React from 'react';
import { Card, Tag } from 'antd';
import type { SubagentEvent } from '@/types';
import { buildSubagentEventKey } from '@/utils/subagentEvents';
import { subagentLabel } from '../shared';

interface ToolkitOverviewPanelProps {
  artifactIntent: string;
  artifactPlanId: string | null;
  artifactValidationStatus: string;
  artifactVerification: boolean | null;
  artifactTools: string[];
  artifactEvidenceCount: number;
  artifactStepCount: number;
  artifactSummary: string;
  subagentEvents: SubagentEvent[];
}

export const ToolkitOverviewPanel: React.FC<ToolkitOverviewPanelProps> = ({
  artifactIntent,
  artifactPlanId,
  artifactValidationStatus,
  artifactVerification,
  artifactTools,
  artifactEvidenceCount,
  artifactStepCount,
  artifactSummary,
  subagentEvents,
}) => (
  <Card size="small" style={{ marginBottom: 12 }}>
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {artifactIntent && <Tag color="blue">Intent: {artifactIntent}</Tag>}
        {artifactPlanId && <Tag color="purple">Plan #{artifactPlanId}</Tag>}
        {artifactValidationStatus && <Tag color="cyan">Validation: {artifactValidationStatus}</Tag>}
        <Tag color={artifactVerification === false ? 'red' : artifactVerification ? 'green' : 'default'}>
          校验: {artifactVerification === false ? '未通过' : artifactVerification ? '通过' : '待定'}
        </Tag>
        <Tag color="gold">Tools: {artifactTools.length}</Tag>
        {artifactEvidenceCount > 0 && <Tag color="geekblue">Evidence: {artifactEvidenceCount}</Tag>}
        {artifactStepCount > 0 && <Tag color="processing">Structured Steps: {artifactStepCount}</Tag>}
      </div>

      {artifactSummary && <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.7 }}>{artifactSummary}</div>}

      {subagentEvents.length > 0 && (
        <div style={{ display: 'grid', gap: 6 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#155e75' }}>子 Agent 轨迹</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {subagentEvents.map((event, index) => (
              <Tag key={buildSubagentEventKey(event, index)} color={event.status ? 'green' : 'blue'}>
                {subagentLabel(event.subagent)}
                {event.status ? `:${event.status}` : ''}
              </Tag>
            ))}
          </div>
        </div>
      )}
    </div>
  </Card>
);
