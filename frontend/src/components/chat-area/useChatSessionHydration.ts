'use client';

import { useEffect, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import { shareClient, type StreamMetadata } from '@/services/api';
import type { ArtifactDeliveryBundle, ExecutionReceipt, Message, SubagentEvent, TripPlanArtifact } from '@/types';
import { logger } from '@/utils/logger';
import { messageTimestamp, type ActiveView } from './shared';

interface ChatHydrationMessageApi {
  success: (content: string) => void;
  error: (content: string) => void;
}

interface UseChatSessionHydrationOptions {
  currentSessionId: string | null;
  clearStreamRuntimeRefs: () => void;
  messageApi: ChatHydrationMessageApi;
  resetArtifactRuntimeState: () => void;
  resetRunState: () => void;
  setActiveView: Dispatch<SetStateAction<ActiveView>>;
  setCurrentSessionId: (id: string | null) => void;
  setIsStreaming: (value: boolean) => void;
  setMessages: (messages: Message[]) => void;
  setStopStreaming: (value: boolean) => void;
  setStreamingMessage: (value: string) => void;
  setStreamingReasoning: (value: string) => void;
  stopRef: MutableRefObject<boolean>;
}

interface UseChatSessionHydrationResult {
  clearHydrationMetadata: () => void;
  markSkipNextSessionReset: () => void;
  metadataRef: MutableRefObject<StreamMetadata | null>;
  setHydrationMetadata: (metadata: StreamMetadata | null) => void;
}

export function extractShareId(search: string): string | null {
  const shareId = new URLSearchParams(search).get('share');
  return shareId?.trim() || null;
}

export function buildSharedAssistantMessage(content: string): Message {
  return {
    role: 'assistant',
    content: content.trim(),
    timestamp: messageTimestamp(),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function trimText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function deliveryBundleShareContent(bundle: ArtifactDeliveryBundle | null | undefined): string {
  return trimText(bundle?.share?.content) || trimText(bundle?.descriptor?.shareContent);
}

function deliveryBundleArtifact(bundle: ArtifactDeliveryBundle | null | undefined): TripPlanArtifact | null {
  return isRecord(bundle?.artifact) ? (bundle.artifact as unknown as TripPlanArtifact) : null;
}

function deliveryBundleExecutionReceipt(bundle: ArtifactDeliveryBundle | null | undefined): ExecutionReceipt | null {
  return isRecord(bundle?.executionReceipt) ? (bundle.executionReceipt as unknown as ExecutionReceipt) : null;
}

function deliveryBundleSubagentEvents(bundle: ArtifactDeliveryBundle | null | undefined): SubagentEvent[] {
  const executionReceipt = deliveryBundleExecutionReceipt(bundle);
  if (!executionReceipt?.segments?.length) return [];

  return executionReceipt.segments.reduce<SubagentEvent[]>((events, segment) => {
      const subagent = trimText(segment.subagent);
      if (!subagent) return events;

      events.push({
        subagent,
        sequence: typeof segment.sequence === 'number' ? segment.sequence : null,
        trigger: trimText(segment.trigger) || null,
        description: trimText(segment.description) || null,
        skills: Array.isArray(segment.skills) ? segment.skills.filter((skill): skill is string => typeof skill === 'string') : [],
        toolNames: Array.isArray(segment.toolNames)
          ? segment.toolNames.filter((tool): tool is string => typeof tool === 'string')
          : Array.isArray(segment.toolsUsed)
            ? segment.toolsUsed.filter((tool): tool is string => typeof tool === 'string')
            : [],
        status: trimText(segment.status) || null,
        summary: trimText(segment.summary) || null,
      });
      return events;
    }, []);
}

export function buildSharedAssistantMessageFromBundle(
  content: string,
  deliveryBundle: ArtifactDeliveryBundle | null | undefined
): Message {
  const artifact = deliveryBundleArtifact(deliveryBundle);
  const executionReceipt = deliveryBundleExecutionReceipt(deliveryBundle);
  const subagentEvents = deliveryBundleSubagentEvents(deliveryBundle);
  const diagnostics =
    artifact || executionReceipt || subagentEvents.length > 0
      ? {
          artifact,
          executionReceipt: executionReceipt ?? undefined,
          subagentEvents: subagentEvents.length > 0 ? subagentEvents : undefined,
        }
      : undefined;

  return {
    role: 'assistant',
    content: deliveryBundleShareContent(deliveryBundle) || trimText(content),
    timestamp: messageTimestamp(),
    diagnostics,
  };
}

export function useChatSessionHydration({
  currentSessionId,
  clearStreamRuntimeRefs,
  messageApi,
  resetArtifactRuntimeState,
  resetRunState,
  setActiveView,
  setCurrentSessionId,
  setIsStreaming,
  setMessages,
  setStopStreaming,
  setStreamingMessage,
  setStreamingReasoning,
  stopRef,
}: UseChatSessionHydrationOptions): UseChatSessionHydrationResult {
  const metadataRef = useRef<StreamMetadata | null>(null);
  const hasHandledShareRef = useRef(false);
  const skipNextSessionResetRef = useRef(false);

  const clearHydrationMetadata = () => {
    metadataRef.current = null;
  };

  const setHydrationMetadata = (metadata: StreamMetadata | null) => {
    metadataRef.current = metadata;
  };

  const markSkipNextSessionReset = () => {
    skipNextSessionResetRef.current = true;
  };

  const resetTransientRuntimeState = () => {
    clearStreamRuntimeRefs();
    setStreamingMessage('');
    setStreamingReasoning('');
    resetRunState();
    setIsStreaming(false);
    setStopStreaming(false);
    resetArtifactRuntimeState();
    clearHydrationMetadata();
    stopRef.current = false;
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (hasHandledShareRef.current) return;

    const shareId = extractShareId(window.location.search);
    if (!shareId) return;

    hasHandledShareRef.current = true;
    const loadSharedContent = async () => {
      try {
        resetTransientRuntimeState();
        const result = await shareClient.getShareDetail(shareId);
        setCurrentSessionId(null);
        setMessages([buildSharedAssistantMessageFromBundle(result.content, result.delivery_bundle ?? null)]);
        setActiveView('chat');
        messageApi.success('已打开分享方案');
      } catch (error) {
        logger.error('加载分享失败:', error);
        messageApi.error(`加载分享失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    };

    void loadSharedContent();
  }, [messageApi, setActiveView, setCurrentSessionId, setMessages]);

  useEffect(() => {
    if (skipNextSessionResetRef.current) {
      skipNextSessionResetRef.current = false;
      return;
    }

    resetTransientRuntimeState();
  }, [currentSessionId]);

  return {
    clearHydrationMetadata,
    markSkipNextSessionReset,
    metadataRef,
    setHydrationMetadata,
  };
}
