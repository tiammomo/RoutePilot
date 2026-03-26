'use client';

import { useEffect, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import { shareClient, type StreamMetadata } from '@/services/api';
import type { Message } from '@/types';
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
    content,
    timestamp: messageTimestamp(),
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
        setMessages([buildSharedAssistantMessage(result.content)]);
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
