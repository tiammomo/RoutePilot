import { useCallback } from 'react';
import { useChatStore } from '@/stores/chat';
import { useSessionStore } from '@/stores/session';
import { apiService } from '@/services/api';
import type { Message } from '@/types';

interface UseSendMessageOptions {
  onSuccess?: (message: Message) => void;
  onError?: (error: string) => void;
}

export const useSendMessage = (options: UseSendMessageOptions = {}) => {
  const { onSuccess, onError } = options;

  const { addMessage, setStreaming, startThinking, stopThinking, resetStreamingState } =
    useChatStore();
  const { currentSessionId, createSession, setCurrentSessionId, refreshSessions } =
    useSessionStore();

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      const userMessage: Message = {
        role: 'user',
        content: content.trim(),
        timestamp: new Date().toLocaleTimeString('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
        }),
      };

      // Create session if needed
      let sessionId = currentSessionId;
      if (!sessionId) {
        sessionId = await createSession();
        await setCurrentSessionId(sessionId);
      }

      addMessage(userMessage);
      startThinking();
      setStreaming(true);

      try {
        await apiService.fetchStreamChat(
          {
            message: content,
            session_id: sessionId,
          },
          {
            onChunk: (chunk) => {
              useChatStore.getState().updateStreamingMessage(chunk);
            },
            onReasoning: (reasoning) => {
              useChatStore.getState().updateStreamingReasoning(reasoning);
            },
            onReasoningStart: () => {
              startThinking();
            },
            onReasoningEnd: () => {
              stopThinking();
            },
            onReasoningTimestamp: () => {},
            onAnswerStart: () => {},
            onMetadata: () => {},
            onComplete: () => {
              const finalMessage = {
                role: 'assistant' as const,
                content: useChatStore.getState().streamingMessage,
                reasoning: useChatStore.getState().streamingReasoning,
                timestamp: new Date().toLocaleTimeString('zh-CN', {
                  hour: '2-digit',
                  minute: '2-digit',
                }),
              };

              addMessage(finalMessage);
              setStreaming(false);
              stopThinking();
              resetStreamingState();
              onSuccess?.(finalMessage);
              refreshSessions();
            },
            onError: (errorMsg) => {
              setStreaming(false);
              stopThinking();
              resetStreamingState();
              onError?.(errorMsg);
            },
          }
        );
      } catch (error) {
        setStreaming(false);
        stopThinking();
        resetStreamingState();
        onError?.(error instanceof Error ? error.message : '未知错误');
      }
    },
    [
      currentSessionId,
      addMessage,
      startThinking,
      setStreaming,
      stopThinking,
      resetStreamingState,
      createSession,
      setCurrentSessionId,
      refreshSessions,
      onSuccess,
      onError,
    ]
  );

  return { sendMessage };
};
