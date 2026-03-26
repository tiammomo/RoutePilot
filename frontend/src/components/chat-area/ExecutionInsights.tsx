'use client';

import React from 'react';
import { Tag } from 'antd';
import { BulbOutlined, ClockCircleOutlined, ToolOutlined } from '@ant-design/icons';
import type { StreamMetadata } from '@/services/api';
import type { PlanPreview, StreamStageEvent, SubagentEvent, TripPlanArtifact } from '@/types';
import { buildSubagentEventKey } from '@/utils/subagentEvents';
import { normalizeStepLabel, subagentLabel, type RuntimeLog } from './shared';

interface ExecutionInsightsProps {
  isStreaming: boolean;
  isThinking: boolean;
  currentTool: string | null;
  stageState: StreamStageEvent | null;
  stageHistory: StreamStageEvent[];
  runtimeLogs: RuntimeLog[];
  planPreview: PlanPreview | null;
  metadata: StreamMetadata | null;
  artifact: TripPlanArtifact | null;
  activeSubagent: string | null;
  subagentEvents: SubagentEvent[];
}

const ExecutionInsights: React.FC<ExecutionInsightsProps> = ({
  isStreaming,
  isThinking,
  currentTool,
  stageState,
  stageHistory,
  runtimeLogs,
  planPreview,
  metadata,
  artifact,
  activeSubagent,
  subagentEvents,
}) => {
  const shouldShow =
    isStreaming ||
    isThinking ||
    Boolean(currentTool) ||
    Boolean(planPreview) ||
    stageHistory.length > 0 ||
    runtimeLogs.length > 0 ||
    Boolean(metadata) ||
    Boolean(artifact) ||
    subagentEvents.length > 0;

  if (!shouldShow) return null;

  const progressValue = stageState?.progress;
  const progressText =
    typeof progressValue === 'number' && Number.isFinite(progressValue)
      ? `${Math.round(Math.max(0, Math.min(100, progressValue * 100)))}%`
      : '进行中';

  return (
    <div
      style={{
        margin: '0 16px 16px',
        padding: '12px',
        background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
        borderRadius: '14px',
        border: '1px solid rgba(37, 99, 235, 0.14)',
        boxShadow: '0 4px 12px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
        <Tag color={isStreaming ? 'blue' : 'default'}>{isStreaming ? '运行中' : '已结束'}</Tag>
        {isThinking && <Tag color="purple">思考中</Tag>}
        {currentTool && <Tag color="gold">工具: {currentTool}</Tag>}
        {stageState?.label && <Tag color="cyan">阶段: {stageState.label}</Tag>}
        {activeSubagent && <Tag color="geekblue">子 Agent: {subagentLabel(activeSubagent)}</Tag>}
        {artifact?.itinerary.planId && <Tag color="purple">Artifact #{artifact.itinerary.planId}</Tag>}
      </div>

      {stageState && (
        <div
          style={{
            marginBottom: '10px',
            padding: '8px 10px',
            borderRadius: '10px',
            background: '#eff6ff',
            fontSize: '12px',
            color: '#1d4ed8',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{stageState.label || stageState.stage || '阶段更新'}</span>
          <span>{progressText}</span>
        </div>
      )}

      {planPreview && (
        <div
          style={{
            marginBottom: '10px',
            padding: '10px',
            borderRadius: '10px',
            background: '#f5f3ff',
            border: '1px solid rgba(124, 58, 237, 0.2)',
          }}
        >
          <div style={{ fontSize: '12px', color: '#6d28d9', marginBottom: '6px', fontWeight: 600 }}>
            Plan 预览 {planPreview.planId ? `#${planPreview.planId}` : ''}
          </div>
          <div style={{ fontSize: '12px', color: '#5b21b6', marginBottom: '6px' }}>
            意图: {planPreview.intent || '未知'} | 校验: {planPreview.validationStatus || '未知'}
          </div>
          {planPreview.explanation && (
            <div style={{ fontSize: '12px', color: '#4c1d95', marginBottom: '6px' }}>{planPreview.explanation}</div>
          )}
          {planPreview.steps.length > 0 && (
            <ol style={{ margin: '0 0 0 18px', padding: 0, fontSize: '12px', color: '#4c1d95', lineHeight: 1.7 }}>
              {planPreview.steps.slice(0, 6).map((step, index) => (
                <li key={`${index}-${normalizeStepLabel(step, index)}`}>{normalizeStepLabel(step, index)}</li>
              ))}
            </ol>
          )}
        </div>
      )}

      {(artifact || subagentEvents.length > 0) && (
        <div
          style={{
            marginBottom: '10px',
            padding: '10px',
            borderRadius: '10px',
            background: '#ecfeff',
            border: '1px solid rgba(8, 145, 178, 0.18)',
          }}
        >
          <div style={{ fontSize: '12px', color: '#0f766e', marginBottom: '8px', fontWeight: 600 }}>
            Artifact / 子 Agent 轨迹
          </div>

          {artifact && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '8px' }}>
              <Tag color="blue">Intent: {artifact.intent.name || 'general'}</Tag>
              <Tag color={artifact.verification.passed === false ? 'red' : artifact.verification.passed ? 'green' : 'default'}>
                校验: {artifact.verification.passed === false ? '未通过' : artifact.verification.passed ? '通过' : '待定'}
              </Tag>
              <Tag color="gold">Tools: {artifact.toolsUsed.length}</Tag>
              {artifact.research.evidence.length > 0 && <Tag color="cyan">Evidence: {artifact.research.evidence.length}</Tag>}
            </div>
          )}

          {subagentEvents.length > 0 && (
            <div style={{ display: 'grid', gap: '6px' }}>
              {subagentEvents
                .slice()
                .reverse()
                .map((event, index) => (
                  <div key={buildSubagentEventKey(event, index)} style={{ fontSize: '12px', color: '#155e75' }}>
                    [{event.timestamp || '--:--:--'}] {subagentLabel(event.subagent)}
                    {event.status ? ` -> ${event.status}` : ` -> ${event.trigger || 'started'}`}
                    {event.skills?.length ? ` | ${event.skills.join(', ')}` : ''}
                    {event.summary ? ` | ${event.summary}` : ''}
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
        <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '10px' }}>
          <div style={{ fontSize: '12px', color: '#334155', marginBottom: '6px', fontWeight: 600 }}>
            <ClockCircleOutlined style={{ marginRight: 6 }} />
            执行时间线
          </div>
          <div style={{ maxHeight: '140px', overflow: 'auto', display: 'grid', gap: '6px' }}>
            {runtimeLogs.length === 0 && <div style={{ fontSize: '12px', color: '#94a3b8' }}>等待事件...</div>}
            {runtimeLogs
              .slice()
              .reverse()
              .map((item) => (
                <div key={item.id} style={{ fontSize: '12px', color: '#334155' }}>
                  [{item.time}] {item.label}
                  {item.detail ? ` / ${item.detail}` : ''}
                </div>
              ))}
          </div>
        </div>

        <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '10px' }}>
          <div style={{ fontSize: '12px', color: '#334155', marginBottom: '6px', fontWeight: 600 }}>
            <ToolOutlined style={{ marginRight: 6 }} />
            运行诊断
          </div>
          <div style={{ fontSize: '12px', color: '#475569', lineHeight: 1.8 }}>
            <div>阶段更新: {stageHistory.length} 次</div>
            <div>工具调用: {metadata?.toolsUsed?.length || 0} 个</div>
            <div>
              验证状态:{' '}
              {metadata?.verificationPassed === null || metadata?.verificationPassed === undefined
                ? '未知'
                : metadata.verificationPassed
                  ? '通过'
                  : '未通过'}
            </div>
            <div>过期结果: {metadata?.staleResultCount || 0}</div>
            <div>回退次数: {metadata?.fallbackSteps || 0}</div>
            {metadata?.planId && <div>计划 ID: {metadata.planId}</div>}
            <div>子 Agent 事件: {subagentEvents.length}</div>
            {artifact?.research.summary && <div>Research: {artifact.research.summary}</div>}
          </div>
        </div>
      </div>

      <div style={{ marginTop: '8px', fontSize: '11px', color: '#64748b' }}>
        <BulbOutlined style={{ marginRight: 6 }} />
        以上内容来自后端 SSE 事件: stage、plan_preview、subagent_start / subagent_end、artifact_patch、tool_start / tool_end、metadata
      </div>
    </div>
  );
};

export default ExecutionInsights;
