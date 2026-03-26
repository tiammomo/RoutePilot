'use client';

import React from 'react';
import { Card, Tag } from 'antd';
import type { SubagentEvent, TripPlanArtifact } from '@/types';
import { buildSubagentEventKey } from '@/utils/subagentEvents';
import { artifactBudgetSummary, artifactDestinations, artifactVerificationLabel, subagentLabel } from '../shared';

interface ToolkitOverviewPanelProps {
  artifact: TripPlanArtifact;
  subagentEvents: SubagentEvent[];
}

export const ToolkitOverviewPanel: React.FC<ToolkitOverviewPanelProps> = ({
  artifact,
  subagentEvents,
}) => {
  const destinations = artifactDestinations(artifact);
  const artifactBudget = artifactBudgetSummary(artifact);
  const verificationLabel = artifactVerificationLabel(artifact);
  const artifactSummary = artifact.research.summary || artifact.verification.summary || '';

  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <div style={{ display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {artifact.intent.name && <Tag color="blue">Intent: {artifact.intent.name}</Tag>}
          {artifact.itinerary.planId && <Tag color="purple">Plan #{artifact.itinerary.planId}</Tag>}
          {artifact.itinerary.validationStatus && <Tag color="cyan">Validation: {artifact.itinerary.validationStatus}</Tag>}
          {verificationLabel && (
            <Tag color={artifact.verification.passed === false ? 'red' : artifact.verification.passed ? 'green' : 'default'}>
              {verificationLabel}
            </Tag>
          )}
          <Tag color="gold">Tools: {artifact.toolsUsed.length}</Tag>
          {destinations.length > 0 && <Tag color="geekblue">Destinations: {destinations.join(' / ')}</Tag>}
          {artifact.research.evidence.length > 0 && <Tag color="geekblue">Evidence: {artifact.research.evidence.length}</Tag>}
          {artifact.itinerary.steps.length > 0 && <Tag color="processing">Structured Steps: {artifact.itinerary.steps.length}</Tag>}
          {artifactBudget && <Tag color="volcano">{artifactBudget}</Tag>}
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
};
