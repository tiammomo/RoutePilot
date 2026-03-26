import { describe, expect, it, vi } from 'vitest';
import { CHAT_STREAM_EVENT_TYPES } from '@/types';
import { handleChatStreamLine } from './chatStreamParser';
import { SSEConnectionStatus, type StreamCallbacks } from './chatStreamTypes';

function createCallbacks(): StreamCallbacks {
  return {
    onChunk: vi.fn(),
    onReasoning: vi.fn(),
    onReasoningStart: vi.fn(),
    onReasoningEnd: vi.fn(),
    onReasoningTimestamp: vi.fn(),
    onAnswerStart: vi.fn(),
    onMetadata: vi.fn(),
    onError: vi.fn(),
    onComplete: vi.fn(),
    onSessionId: vi.fn(),
    onStage: vi.fn(),
    onPlanPreview: vi.fn(),
    onSubagentStart: vi.fn(),
    onSubagentEnd: vi.fn(),
    onArtifactPatch: vi.fn(),
    onToolStart: vi.fn(),
    onToolEnd: vi.fn(),
    onConnectionChange: vi.fn(),
  };
}

describe('handleChatStreamLine', () => {
  it('normalizes plan preview payloads', () => {
    const callbacks = createCallbacks();
    const lifecycle = {
      finalizeRequest: vi.fn(),
      setConnectionStatus: vi.fn(),
    };

    const terminal = handleChatStreamLine(
      `data: ${JSON.stringify({
        type: CHAT_STREAM_EVENT_TYPES.PLAN_PREVIEW,
        plan_id: 'plan-1',
        intent: 'weekend',
        explanation: 'fit',
        validation_status: 'ok',
        validation_errors: [{ code: 'TOOL_NOT_REGISTERED', step_id: 's1' }],
        steps: [{ title: 'step-1' }],
        artifact: { title: 'artifact' },
        artifact_patch: { title: 'patch' },
        subagent: 'planner',
        skills: ['planning'],
      })}`,
      callbacks,
      lifecycle
    );

    expect(terminal).toBe(false);
    expect(callbacks.onPlanPreview).toHaveBeenCalledWith({
      planId: 'plan-1',
      intent: 'weekend',
      explanation: 'fit',
      validationStatus: 'ok',
      validationErrors: [{ code: 'TOOL_NOT_REGISTERED', step_id: 's1' }],
      steps: [{ title: 'step-1' }],
      artifact: { title: 'artifact' },
      artifactPatch: { title: 'patch' },
      subagent: 'planner',
      skills: ['planning'],
    });
    expect(lifecycle.finalizeRequest).not.toHaveBeenCalled();
  });

  it('treats done as a terminal event', () => {
    const callbacks = createCallbacks();
    const lifecycle = {
      finalizeRequest: vi.fn(),
      setConnectionStatus: vi.fn(),
    };

    const terminal = handleChatStreamLine(
      `data: ${JSON.stringify({
        type: CHAT_STREAM_EVENT_TYPES.DONE,
        artifact: { title: 'trip' },
        run_id: 'run-1',
        request_id: 'req-1',
        trace_id: 'trace-1',
      })}`,
      callbacks,
      lifecycle
    );

    expect(terminal).toBe(true);
    expect(lifecycle.setConnectionStatus).toHaveBeenCalledWith(SSEConnectionStatus.IDLE);
    expect(lifecycle.finalizeRequest).toHaveBeenCalledTimes(1);
    expect(callbacks.onComplete).toHaveBeenCalledWith({
      artifact: { title: 'trip' },
      runId: 'run-1',
      requestId: 'req-1',
      traceId: 'trace-1',
    });
  });

  it('treats error payloads as terminal failures', () => {
    const callbacks = createCallbacks();
    const lifecycle = {
      finalizeRequest: vi.fn(),
      setConnectionStatus: vi.fn(),
    };

    const terminal = handleChatStreamLine(
      `data: ${JSON.stringify({
        type: CHAT_STREAM_EVENT_TYPES.ERROR,
        content: 'boom',
      })}`,
      callbacks,
      lifecycle
    );

    expect(terminal).toBe(true);
    expect(lifecycle.setConnectionStatus).toHaveBeenCalledWith(SSEConnectionStatus.ERROR);
    expect(lifecycle.finalizeRequest).toHaveBeenCalledTimes(1);
    expect(callbacks.onError).toHaveBeenCalledWith('boom');
  });
});
