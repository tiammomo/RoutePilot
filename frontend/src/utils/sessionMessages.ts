import type { LatestArtifactResponse, Message, MessageDiagnostics, SubagentEvent, TripPlanArtifact } from '@/types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function normalizeSubagentEvents(value: unknown): SubagentEvent[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value
    .filter(isRecord)
    .map((event) => ({
      subagent: typeof event.subagent === 'string' ? event.subagent : 'unknown',
      description: typeof event.description === 'string' ? event.description : null,
      skills: Array.isArray(event.skills) ? event.skills.filter((item): item is string => typeof item === 'string') : [],
      toolNames: Array.isArray(event.toolNames)
        ? event.toolNames.filter((item): item is string => typeof item === 'string')
        : [],
      sequence: typeof event.sequence === 'number' ? event.sequence : null,
      trigger: typeof event.trigger === 'string' ? event.trigger : null,
      status: typeof event.status === 'string' ? event.status : null,
      summary: typeof event.summary === 'string' ? event.summary : null,
      timestamp: typeof event.timestamp === 'string' ? event.timestamp : undefined,
    }));
}

function normalizeDiagnostics(value: unknown): MessageDiagnostics | undefined {
  if (!isRecord(value)) return undefined;

  return {
    toolsUsed: Array.isArray(value.toolsUsed) ? value.toolsUsed.filter((item): item is string => typeof item === 'string') : [],
    verificationPassed:
      typeof value.verificationPassed === 'boolean' || value.verificationPassed === null
        ? value.verificationPassed
        : null,
    staleResultCount: typeof value.staleResultCount === 'number' ? value.staleResultCount : 0,
    fallbackSteps: typeof value.fallbackSteps === 'number' ? value.fallbackSteps : 0,
    planId: typeof value.planId === 'string' ? value.planId : null,
    executionStats: isRecord(value.executionStats) ? value.executionStats : undefined,
    artifact: isRecord(value.artifact) ? (value.artifact as unknown as TripPlanArtifact) : null,
    subagentEvents: normalizeSubagentEvents(value.subagentEvents),
    runId: typeof value.runId === 'string' ? value.runId : undefined,
    requestId: typeof value.requestId === 'string' ? value.requestId : undefined,
    traceId: typeof value.traceId === 'string' ? value.traceId : undefined,
  };
}

export function normalizePersistedMessages(value: unknown): Message[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter(isRecord)
    .map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: typeof message.content === 'string' ? message.content : '',
      timestamp: typeof message.timestamp === 'string' ? message.timestamp : '--:--:--',
      reasoning: typeof message.reasoning === 'string' ? message.reasoning : undefined,
      diagnostics: normalizeDiagnostics(message.diagnostics),
    }));
}

export function findLatestAssistantMessageIndex(messages: Message[]): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.role === 'assistant') return index;
  }
  return -1;
}

function resolveArtifactTargetIndex(messages: Message[], preferredIndex?: number | null): number {
  if (
    typeof preferredIndex === 'number' &&
    preferredIndex >= 0 &&
    preferredIndex < messages.length &&
    messages[preferredIndex]?.role === 'assistant'
  ) {
    return preferredIndex;
  }
  return findLatestAssistantMessageIndex(messages);
}

export function hydrateMessagesWithLatestArtifact(
  messages: Message[],
  latestArtifact: LatestArtifactResponse | null | undefined
): Message[] {
  if (!latestArtifact?.success || !latestArtifact.artifact_found || !latestArtifact.artifact) {
    return messages;
  }
  const artifact = latestArtifact.artifact;

  const targetIndex = resolveArtifactTargetIndex(messages, latestArtifact.message_index);
  if (targetIndex < 0) return messages;

  return messages.map((message, index) => {
    if (index !== targetIndex) return message;

    return {
      ...message,
      content: message.content || artifact.answer || '',
      diagnostics: {
        ...message.diagnostics,
        artifact,
        planId: artifact.itinerary.planId ?? message.diagnostics?.planId ?? null,
        runId: latestArtifact.run_id ?? message.diagnostics?.runId,
      },
    };
  });
}
