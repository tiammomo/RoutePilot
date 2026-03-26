import type { ArtifactPatch, ChatStreamEventType, TripPlanArtifact } from '@/types';
import { CHAT_STREAM_EVENT_TYPES } from '@/types';
import { SSEConnectionStatus, type StreamCallbacks } from './chatStreamTypes';

interface ChatStreamLifecycle {
  finalizeRequest: () => void;
  setConnectionStatus: (status: SSEConnectionStatus) => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function unknownArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

const CHAT_STREAM_EVENT_TYPE_SET = new Set<string>(Object.values(CHAT_STREAM_EVENT_TYPES));

function parseChatStreamEventType(value: unknown): ChatStreamEventType | null {
  if (typeof value !== 'string' || !CHAT_STREAM_EVENT_TYPE_SET.has(value)) return null;
  return value as ChatStreamEventType;
}

export function handleChatStreamLine(
  line: string,
  callbacks: StreamCallbacks,
  lifecycle: ChatStreamLifecycle
): boolean {
  const trimmed = line.replace(/\r$/, '').trim();
  if (!trimmed.startsWith('data:')) return false;

  const dataStr = trimmed.slice(5).trim();
  if (!dataStr) return false;

  if (dataStr === '[DONE]') {
    lifecycle.setConnectionStatus(SSEConnectionStatus.IDLE);
    callbacks.onComplete();
    lifecycle.finalizeRequest();
    return true;
  }

  try {
    const data = JSON.parse(dataStr) as Record<string, unknown>;
    const dataType = parseChatStreamEventType(data.type);

    if (dataType === CHAT_STREAM_EVENT_TYPES.SESSION_ID && typeof data.session_id === 'string') {
      callbacks.onSessionId?.(data.session_id);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.STAGE) {
      callbacks.onStage?.({
        stage: typeof data.stage === 'string' ? data.stage : undefined,
        label: typeof data.label === 'string' ? data.label : undefined,
        progress: data.progress === undefined ? null : Number(data.progress),
        subagent: typeof data.subagent === 'string' ? data.subagent : null,
      });
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.PLAN_PREVIEW) {
      callbacks.onPlanPreview?.({
        planId: typeof data.plan_id === 'string' ? data.plan_id : null,
        intent: typeof data.intent === 'string' ? data.intent : null,
        explanation: typeof data.explanation === 'string' ? data.explanation : null,
        validationStatus: typeof data.validation_status === 'string' ? data.validation_status : null,
        validationErrors: unknownArray(data.validation_errors),
        steps: recordArray(data.steps),
        artifact: isRecord(data.artifact) ? (data.artifact as unknown as TripPlanArtifact) : null,
        artifactPatch: isRecord(data.artifact_patch) ? (data.artifact_patch as ArtifactPatch) : null,
        subagent: typeof data.subagent === 'string' ? data.subagent : null,
        skills: stringArray(data.skills),
      });
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.SUBAGENT_START && typeof data.subagent === 'string') {
      callbacks.onSubagentStart?.({
        subagent: data.subagent,
        description: typeof data.description === 'string' ? data.description : null,
        skills: stringArray(data.skills),
        toolNames: stringArray(data.tool_names),
        sequence: data.sequence === undefined ? null : Number(data.sequence),
        trigger: typeof data.trigger === 'string' ? data.trigger : null,
      });
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.SUBAGENT_END && typeof data.subagent === 'string') {
      callbacks.onSubagentEnd?.({
        subagent: data.subagent,
        sequence: data.sequence === undefined ? null : Number(data.sequence),
        status: typeof data.status === 'string' ? data.status : null,
        summary: typeof data.summary === 'string' ? data.summary : null,
      });
      return false;
    }

    if (
      dataType === CHAT_STREAM_EVENT_TYPES.ARTIFACT_PATCH &&
      typeof data.subagent === 'string' &&
      isRecord(data.artifact_patch)
    ) {
      callbacks.onArtifactPatch?.(data.subagent, data.artifact_patch as ArtifactPatch);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.METADATA) {
      callbacks.onMetadata({
        totalSteps: Number(data.total_steps || 0),
        toolsUsed: stringArray(data.tools_used),
        hasReasoning: Boolean(data.has_reasoning),
        reasoningLength: Number(data.reasoning_length || 0),
        answerLength: Number(data.answer_length || 0),
        verificationPassed: data.verification_passed === undefined ? null : Boolean(data.verification_passed),
        staleResultCount: Number(data.stale_result_count || 0),
        fallbackSteps: Number(data.fallback_steps || 0),
        planId: typeof data.plan_id === 'string' ? data.plan_id : null,
        executionStats: isRecord(data.execution_stats) ? data.execution_stats : undefined,
        runId: typeof data.run_id === 'string' ? data.run_id : '',
        requestId: typeof data.request_id === 'string' ? data.request_id : '',
        traceId: typeof data.trace_id === 'string' ? data.trace_id : '',
        artifact: isRecord(data.artifact) ? (data.artifact as unknown as TripPlanArtifact) : null,
      });
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.REASONING_START) {
      callbacks.onReasoningStart();
      return false;
    }

    if (typeof data.type === 'string' && data.type === 'reasoning_timestamp' && typeof data.timestamp === 'string') {
      callbacks.onReasoningTimestamp(data.timestamp);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.REASONING_CHUNK && typeof data.content === 'string') {
      callbacks.onReasoning(data.content);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.REASONING_END) {
      callbacks.onReasoningEnd();
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.ANSWER_START) {
      callbacks.onAnswerStart();
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.TOOL_START && typeof data.tool === 'string') {
      callbacks.onToolStart?.(data.tool);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.TOOL_END && typeof data.tool === 'string') {
      callbacks.onToolEnd?.(data.tool, typeof data.result === 'string' ? data.result : '');
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.CHUNK && typeof data.content === 'string') {
      callbacks.onChunk(data.content);
      return false;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.ERROR && typeof data.content === 'string') {
      lifecycle.setConnectionStatus(SSEConnectionStatus.ERROR);
      callbacks.onError(data.content);
      lifecycle.finalizeRequest();
      return true;
    }

    if (dataType === CHAT_STREAM_EVENT_TYPES.DONE) {
      lifecycle.setConnectionStatus(SSEConnectionStatus.IDLE);
      callbacks.onComplete({
        artifact: isRecord(data.artifact) ? (data.artifact as unknown as TripPlanArtifact) : null,
        runId: typeof data.run_id === 'string' ? data.run_id : '',
        requestId: typeof data.request_id === 'string' ? data.request_id : '',
        traceId: typeof data.trace_id === 'string' ? data.trace_id : '',
      });
      lifecycle.finalizeRequest();
      return true;
    }

    if (typeof data.chunk === 'string') callbacks.onChunk(data.chunk);
    if (typeof data.error === 'string') {
      lifecycle.setConnectionStatus(SSEConnectionStatus.ERROR);
      callbacks.onError(data.error);
      lifecycle.finalizeRequest();
      return true;
    }
  } catch {
    // Ignore malformed SSE chunks.
  }

  return false;
}
