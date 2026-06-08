import { randomUUID } from 'crypto';
import type { Message, MessageMetadata } from '@/types/backend';
import type { RealtimeMessage } from '@/types';

const TOOL_DETAIL_PREVIEW_LIMIT = 12000;

function parseMetadata(metadataJson?: string | null): MessageMetadata | null {
  if (!metadataJson) {
    return null;
  }

  try {
    const parsed = JSON.parse(metadataJson) as MessageMetadata;
    return parsed;
  } catch (error) {
    console.warn('[chat-serializer] Failed to parse metadata JSON:', error);
    return null;
  }
}

function truncateText(value: string, limit = TOOL_DETAIL_PREVIEW_LIMIT): string {
  if (value.length <= limit) {
    return value;
  }

  return `${value.slice(0, limit)}\n\n... 已截断 ${value.length - limit} 个字符，完整输出仍保存在服务端消息记录中。`;
}

function compactMetadataForClient(metadata: MessageMetadata | null): MessageMetadata | null {
  if (!metadata) {
    return null;
  }

  const compacted: MessageMetadata = { ...metadata };
  const keys = ['toolOutput', 'tool_output', 'output', 'result', 'content', 'diff', 'diffInfo', 'diff_info'];

  keys.forEach((key) => {
    const value = compacted[key];
    if (typeof value === 'string') {
      compacted[key] = truncateText(value);
    }
  });

  return compacted;
}

export function serializeMessage(
  message: Message,
  overrides: Partial<RealtimeMessage> = {}
): RealtimeMessage {
  const metadata = compactMetadataForClient(parseMetadata(message.metadataJson));
  const content =
    message.messageType === 'tool_result'
      ? truncateText(message.content, TOOL_DETAIL_PREVIEW_LIMIT)
      : message.content;

  return {
    id: message.id,
    projectId: message.projectId,
    role: message.role,
    messageType: message.messageType,
    content,
    metadata,
    parentMessageId: message.parentMessageId ?? null,
    conversationId: message.conversationId ?? null,
    sessionId: message.sessionId ?? null,
    cliSource: message.cliSource ?? null,
    requestId: message.requestId ?? undefined,
    createdAt: message.createdAt.toISOString(),
    updatedAt: message.updatedAt.toISOString(),
    ...overrides,
  };
}

export function serializeMessages(messages: Message[]): RealtimeMessage[] {
  return messages.map((message) => serializeMessage(message));
}

export function createRealtimeMessage(
  payload: Partial<RealtimeMessage> & Pick<RealtimeMessage, 'projectId' | 'role' | 'messageType' | 'content'>
): RealtimeMessage {
  const createdAt = payload.createdAt ?? new Date().toISOString();
  const updatedAt =
    payload.updatedAt ??
    createdAt;

  return {
    id: payload.id ?? randomUUID(),
    projectId: payload.projectId,
    role: payload.role,
    messageType: payload.messageType,
    content: payload.content,
    metadata: payload.metadata ?? null,
    parentMessageId: payload.parentMessageId ?? null,
    conversationId: payload.conversationId ?? null,
    sessionId: payload.sessionId ?? null,
    cliSource: payload.cliSource ?? null,
    requestId: payload.requestId ?? undefined,
    createdAt,
    updatedAt,
    isStreaming: payload.isStreaming,
    isFinal: payload.isFinal,
    isOptimistic: payload.isOptimistic,
  };
}
