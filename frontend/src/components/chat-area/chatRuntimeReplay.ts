'use client';

import { handleChatStreamLine } from '@/services/api/chatStreamParser';
import { SSEConnectionStatus, type StreamCompletionPayload, type StreamMetadata } from '@/services/api/chatStreamTypes';
import type {
  MessageDiagnostics,
  PlanPreview,
  StreamStageEvent,
  SubagentEvent,
  TripPlanArtifact,
} from '@/types';
import { mergeTripPlanArtifact } from '@/utils/agentArtifacts';
import { buildCompletionDiagnostics, buildFinalReasoning } from './runtimeMessageBuilders';

type ChatStreamGoldenEventPayload = Record<string, unknown>;

type ChatStreamGoldenModeKey = 'direct' | 'react' | 'plan';

interface ChatStreamGoldenModeFixture {
  request: {
    message: string;
    mode: ChatStreamGoldenModeKey;
  };
  response: {
    status_code: number;
    headers: Record<string, string>;
  };
  event_sequence: string[];
  key_events: {
    session_id?: ChatStreamGoldenEventPayload;
    plan_preview?: ChatStreamGoldenEventPayload;
    metadata?: ChatStreamGoldenEventPayload;
    done?: ChatStreamGoldenEventPayload;
    artifact_patches?: ChatStreamGoldenEventPayload[];
    answer_chunks?: ChatStreamGoldenEventPayload[];
    reasoning_chunks?: ChatStreamGoldenEventPayload[];
    stages?: ChatStreamGoldenEventPayload[];
    subagent_starts?: ChatStreamGoldenEventPayload[];
    subagent_ends?: ChatStreamGoldenEventPayload[];
    tool_starts?: ChatStreamGoldenEventPayload[];
    tool_ends?: ChatStreamGoldenEventPayload[];
  };
}

export interface ChatStreamGoldenFixture {
  schema_version: number;
  source_snapshot_schema_version: number;
  endpoint: string;
  registered_event_types: string[];
  modes: Record<ChatStreamGoldenModeKey, ChatStreamGoldenModeFixture>;
}

export interface FrontendChatRuntimeModeFixture {
  request: ChatStreamGoldenModeFixture['request'];
  response: ChatStreamGoldenModeFixture['response'];
  assistant_message: {
    content: string;
    reasoning: string;
    diagnostics?: MessageDiagnostics;
  } | null;
  runtime_state: {
    session_id: string | null;
    connection_status: SSEConnectionStatus;
    stage_history: StreamStageEvent[];
    plan_preview: PlanPreview | null;
    artifact: TripPlanArtifact | null;
    metadata: StreamMetadata | null;
    subagent_events: SubagentEvent[];
  };
}

export interface FrontendChatRuntimeGoldenFixture {
  schema_version: number;
  source_fixture_schema_version: number;
  endpoint: string;
  modes: Record<ChatStreamGoldenModeKey, FrontendChatRuntimeModeFixture>;
}

const ARRAY_EVENT_KEYS: Record<string, keyof ChatStreamGoldenModeFixture['key_events']> = {
  artifact_patch: 'artifact_patches',
  chunk: 'answer_chunks',
  reasoning_chunk: 'reasoning_chunks',
  stage: 'stages',
  subagent_end: 'subagent_ends',
  subagent_start: 'subagent_starts',
  tool_end: 'tool_ends',
  tool_start: 'tool_starts',
};

const SINGLE_EVENT_KEYS: Record<string, keyof ChatStreamGoldenModeFixture['key_events']> = {
  done: 'done',
  metadata: 'metadata',
  plan_preview: 'plan_preview',
  session_id: 'session_id',
};

function clonePayload<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function buildReplayEvents(modeFixture: ChatStreamGoldenModeFixture): ChatStreamGoldenEventPayload[] {
  const keyEvents = modeFixture.key_events;
  const arrayQueues: Partial<Record<keyof ChatStreamGoldenModeFixture['key_events'], ChatStreamGoldenEventPayload[]>> =
    {};
  const usedSingles = new Set<keyof ChatStreamGoldenModeFixture['key_events']>();

  for (const [eventType, eventKey] of Object.entries(ARRAY_EVENT_KEYS)) {
    const items = keyEvents[eventKey];
    if (Array.isArray(items)) {
      arrayQueues[eventKey] = clonePayload(items);
      continue;
    }
    if (items) {
      arrayQueues[eventKey] = [clonePayload(items as ChatStreamGoldenEventPayload)];
      continue;
    }
    arrayQueues[eventKey] = [];
  }

  return modeFixture.event_sequence.map((eventType) => {
    const arrayKey = ARRAY_EVENT_KEYS[eventType];
    if (arrayKey) {
      const next = arrayQueues[arrayKey]?.shift();
      return next ? clonePayload(next) : { type: eventType };
    }

    const singleKey = SINGLE_EVENT_KEYS[eventType];
    if (singleKey && !usedSingles.has(singleKey)) {
      usedSingles.add(singleKey);
      const payload = keyEvents[singleKey];
      if (payload && !Array.isArray(payload)) {
        return clonePayload(payload);
      }
    }

    return { type: eventType };
  });
}

export function replayChatRuntimeMode(modeFixture: ChatStreamGoldenModeFixture): FrontendChatRuntimeModeFixture {
  let artifact: TripPlanArtifact | null = null;
  let metadata: StreamMetadata | null = null;
  let planPreview: PlanPreview | null = null;
  let sessionId: string | null = null;
  let answer = '';
  let reasoning = '';
  let reasoningTimestamp = '';
  let completion: StreamCompletionPayload | undefined;
  let diagnostics: MessageDiagnostics | undefined;
  const stageHistory: StreamStageEvent[] = [];
  const subagentEvents: SubagentEvent[] = [];
  let connectionStatus = SSEConnectionStatus.IDLE;

  const lifecycle = {
    finalizeRequest: () => undefined,
    setConnectionStatus: (status: SSEConnectionStatus) => {
      connectionStatus = status;
    },
  };

  const replayEvents = buildReplayEvents(modeFixture);
  for (const event of replayEvents) {
    const line = `data: ${JSON.stringify(event)}`;
    handleChatStreamLine(
      line,
      {
        onChunk: (content) => {
          answer += content;
        },
        onReasoning: (content) => {
          reasoning += content;
        },
        onReasoningStart: () => undefined,
        onReasoningEnd: () => undefined,
        onReasoningTimestamp: (timestamp) => {
          reasoningTimestamp = timestamp;
        },
        onAnswerStart: () => undefined,
        onMetadata: (nextMetadata) => {
          metadata = nextMetadata;
          artifact = mergeTripPlanArtifact(artifact, nextMetadata.artifact);
        },
        onError: () => undefined,
        onComplete: (payload) => {
          completion = payload;
          artifact = mergeTripPlanArtifact(artifact, payload?.artifact);
          diagnostics = buildCompletionDiagnostics({
            artifact,
            completion: payload,
            metadata,
            subagentEvents,
          });
        },
        onSessionId: (nextSessionId) => {
          sessionId = nextSessionId;
        },
        onStage: (stage) => {
          stageHistory.push(stage);
        },
        onPlanPreview: (preview) => {
          planPreview = preview;
          artifact = mergeTripPlanArtifact(artifact, preview.artifact ?? preview.artifactPatch);
        },
        onSubagentStart: (eventPayload) => {
          subagentEvents.push(eventPayload);
        },
        onSubagentEnd: (eventPayload) => {
          subagentEvents.push(eventPayload);
        },
        onArtifactPatch: (_subagent, patch) => {
          artifact = mergeTripPlanArtifact(artifact, patch);
        },
        onToolStart: () => undefined,
        onToolEnd: () => undefined,
      },
      lifecycle
    );
  }

  return {
    request: clonePayload(modeFixture.request),
    response: clonePayload(modeFixture.response),
    assistant_message: completion
      ? {
          content: answer,
          reasoning: buildFinalReasoning(reasoning, reasoningTimestamp || undefined),
          diagnostics,
        }
      : null,
    runtime_state: {
      session_id: sessionId,
      connection_status: connectionStatus,
      stage_history: stageHistory,
      plan_preview: planPreview,
      artifact,
      metadata,
      subagent_events: subagentEvents,
    },
  };
}

export function buildFrontendChatRuntimeGoldenFixture(
  sourceFixture: ChatStreamGoldenFixture
): FrontendChatRuntimeGoldenFixture {
  return {
    schema_version: 1,
    source_fixture_schema_version: sourceFixture.schema_version,
    endpoint: sourceFixture.endpoint,
    modes: {
      direct: replayChatRuntimeMode(sourceFixture.modes.direct),
      react: replayChatRuntimeMode(sourceFixture.modes.react),
      plan: replayChatRuntimeMode(sourceFixture.modes.plan),
    },
  };
}
