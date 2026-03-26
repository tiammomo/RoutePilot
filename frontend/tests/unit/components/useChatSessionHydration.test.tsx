import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { useRef, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/types';
import {
  buildSharedAssistantMessage,
  extractShareId,
  useChatSessionHydration,
} from '@/components/chat-area/useChatSessionHydration';

const shareClientMock = vi.hoisted(() => ({
  getShareDetail: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  shareClient: shareClientMock,
}));

function HydrationProbe({
  initialSessionId = 'session-1',
  messageApi = { success: vi.fn(), error: vi.fn() },
  runtimeSpies = {
    clearStreamRuntimeRefs: vi.fn(),
    resetArtifactRuntimeState: vi.fn(),
    resetRunState: vi.fn(),
  },
}: {
  initialSessionId?: string | null;
  messageApi?: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };
  runtimeSpies?: {
    clearStreamRuntimeRefs: ReturnType<typeof vi.fn>;
    resetArtifactRuntimeState: ReturnType<typeof vi.fn>;
    resetRunState: ReturnType<typeof vi.fn>;
  };
}) {
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(initialSessionId);
  const [activeView, setActiveView] = useState<'chat' | 'city' | 'status'>('status');
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingMessage, setStreamingMessage] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [stopStreaming, setStopStreaming] = useState(false);
  const stopRef = useRef(false);

  const { markSkipNextSessionReset } = useChatSessionHydration({
    currentSessionId,
    clearStreamRuntimeRefs: runtimeSpies.clearStreamRuntimeRefs,
    messageApi,
    resetArtifactRuntimeState: runtimeSpies.resetArtifactRuntimeState,
    resetRunState: runtimeSpies.resetRunState,
    setActiveView,
    setCurrentSessionId,
    setIsStreaming,
    setMessages,
    setStopStreaming,
    setStreamingMessage,
    setStreamingReasoning,
    stopRef,
  });

  return (
    <div>
      <div data-testid="session-id">{currentSessionId ?? 'none'}</div>
      <div data-testid="active-view">{activeView}</div>
      <div data-testid="message-content">{messages[0]?.content ?? 'empty'}</div>
      <div data-testid="streaming-message">{streamingMessage || 'empty'}</div>
      <div data-testid="streaming-reasoning">{streamingReasoning || 'empty'}</div>
      <div data-testid="is-streaming">{String(isStreaming)}</div>
      <div data-testid="stop-streaming">{String(stopStreaming)}</div>
      <div data-testid="stop-ref">{String(stopRef.current)}</div>
      <button
        onClick={() => {
          setStreamingMessage('draft');
          setStreamingReasoning('trace');
          setIsStreaming(true);
          setStopStreaming(true);
          stopRef.current = true;
        }}
      >
        seed runtime
      </button>
      <button onClick={() => markSkipNextSessionReset()}>skip reset</button>
      <button onClick={() => setCurrentSessionId((value) => (value === 'session-1' ? 'session-2' : 'session-1'))}>
        switch session
      </button>
    </div>
  );
}

describe('useChatSessionHydration', () => {
  beforeEach(() => {
    shareClientMock.getShareDetail.mockReset();
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('extracts share ids and builds shared assistant messages', () => {
    expect(extractShareId('?foo=1&share=demo-share')).toBe('demo-share');
    expect(extractShareId('?foo=1')).toBeNull();
    expect(buildSharedAssistantMessage('共享方案').content).toBe('共享方案');
  });

  it('hydrates shared content from the share query parameter', async () => {
    window.history.replaceState({}, '', '/?share=shared-plan-1');
    shareClientMock.getShareDetail.mockResolvedValue({
      success: true,
      share_id: 'shared-plan-1',
      share_url: 'https://example.test/share/shared-plan-1',
      content: '共享行程内容',
      created_at: new Date().toISOString(),
    });
    const messageApi = { success: vi.fn(), error: vi.fn() };
    const runtimeSpies = {
      clearStreamRuntimeRefs: vi.fn(),
      resetArtifactRuntimeState: vi.fn(),
      resetRunState: vi.fn(),
    };

    render(<HydrationProbe messageApi={messageApi} runtimeSpies={runtimeSpies} />);

    await waitFor(() => expect(screen.getByTestId('message-content')).toHaveTextContent('共享行程内容'));
    expect(screen.getByTestId('session-id')).toHaveTextContent('none');
    expect(screen.getByTestId('active-view')).toHaveTextContent('chat');
    expect(messageApi.success).toHaveBeenCalledWith('已打开分享方案');
    expect(runtimeSpies.clearStreamRuntimeRefs).toHaveBeenCalled();
  });

  it('resets transient runtime state when the session changes', async () => {
    render(<HydrationProbe />);

    fireEvent.click(screen.getByRole('button', { name: /seed runtime/i }));
    expect(screen.getByTestId('streaming-message')).toHaveTextContent('draft');

    fireEvent.click(screen.getByRole('button', { name: /switch session/i }));

    await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent('session-2'));
    expect(screen.getByTestId('streaming-message')).toHaveTextContent('empty');
    expect(screen.getByTestId('streaming-reasoning')).toHaveTextContent('empty');
    expect(screen.getByTestId('is-streaming')).toHaveTextContent('false');
    expect(screen.getByTestId('stop-streaming')).toHaveTextContent('false');
    expect(screen.getByTestId('stop-ref')).toHaveTextContent('false');
  });

  it('skips the next session reset when explicitly marked', async () => {
    render(<HydrationProbe />);

    fireEvent.click(screen.getByRole('button', { name: /seed runtime/i }));
    fireEvent.click(screen.getByRole('button', { name: /skip reset/i }));
    fireEvent.click(screen.getByRole('button', { name: /switch session/i }));

    await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent('session-2'));
    expect(screen.getByTestId('streaming-message')).toHaveTextContent('draft');
    expect(screen.getByTestId('streaming-reasoning')).toHaveTextContent('trace');
    expect(screen.getByTestId('is-streaming')).toHaveTextContent('true');
    expect(screen.getByTestId('stop-streaming')).toHaveTextContent('true');
    expect(screen.getByTestId('stop-ref')).toHaveTextContent('true');
  });
});
