import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message, SessionInfo } from '@/types';

const sessionClientMock = vi.hoisted(() => ({
  getSessions: vi.fn(),
  getSessionMessages: vi.fn(),
}));

const artifactClientMock = vi.hoisted(() => ({
  getLatestArtifact: vi.fn(),
}));

const modelClientMock = vi.hoisted(() => ({
  getSessionModel: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  artifactClient: artifactClientMock,
  sessionClient: sessionClientMock,
  modelClient: modelClientMock,
}));

import {
  buildVisibleSessions,
  persistStoredSessionId,
  readStoredSessionId,
  useSessionHistoryState,
} from '@/context/useSessionHistoryState';

function buildSession(sessionId: string, overrides: Partial<SessionInfo> = {}): SessionInfo {
  return {
    session_id: sessionId,
    name: sessionId,
    last_active: '2026-03-26T12:00:00.000Z',
    message_count: 1,
    ...overrides,
  };
}

function buildMessage(content: string): Message {
  return {
    role: 'assistant',
    content,
    timestamp: '12:00:00',
  };
}

describe('useSessionHistoryState helpers', () => {
  it('dedupes sessions and hides old empty sessions by default', () => {
    const sessions = [
      buildSession('session-1'),
      buildSession('session-1', { name: 'duplicate' }),
      buildSession('session-2', { message_count: 0, last_active: '2026-03-26T11:30:00.000Z' }),
      buildSession('session-3', { message_count: 0, last_active: '2026-03-26T09:30:00.000Z' }),
    ];

    expect(
      buildVisibleSessions(sessions, {
        now: new Date('2026-03-26T12:00:00.000Z'),
      }).map((session) => session.session_id)
    ).toEqual(['session-1', 'session-2']);

    expect(buildVisibleSessions(sessions, { includeEmpty: true }).map((session) => session.session_id)).toEqual([
      'session-1',
      'session-2',
      'session-3',
    ]);
  });

  it('ignores stored session id when share recovery is active', () => {
    const storage = {
      getItem: vi.fn().mockReturnValue('session-1'),
      removeItem: vi.fn(),
      setItem: vi.fn(),
    };

    expect(readStoredSessionId('?share=share-1', storage)).toBeNull();
    expect(readStoredSessionId('', storage)).toBe('session-1');

    persistStoredSessionId(storage, 'session-2');
    expect(storage.setItem).toHaveBeenCalledWith('moyuan-current-session-id', 'session-2');

    persistStoredSessionId(storage, null);
    expect(storage.removeItem).toHaveBeenCalledWith('moyuan-current-session-id');
  });
});

describe('useSessionHistoryState', () => {
  beforeEach(() => {
    window.localStorage.clear();
    sessionClientMock.getSessions.mockReset();
    sessionClientMock.getSessionMessages.mockReset();
    artifactClientMock.getLatestArtifact.mockReset();
    modelClientMock.getSessionModel.mockReset();
    sessionClientMock.getSessions.mockResolvedValue({ sessions: [] });
    artifactClientMock.getLatestArtifact.mockResolvedValue({
      success: true,
      session_id: 'session-1',
      artifact_found: false,
      artifact: null,
      run_id: null,
      message_timestamp: null,
      message_index: null,
    });
    modelClientMock.getSessionModel.mockResolvedValue({ success: true, model_id: 'mimo-v2.5-pro' });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('reuses cached session history when switching back to a previously opened session', async () => {
    sessionClientMock.getSessionMessages.mockImplementation(async (sessionId: string) => {
      if (sessionId === 'session-1') {
        return {
          success: true,
          messages: [{ role: 'assistant', content: 'server copy', timestamp: '10:00:00' }],
        };
      }

      return {
        success: true,
        messages: [{ role: 'assistant', content: 'other session', timestamp: '10:05:00' }],
      };
    });

    const onRecoveredModelId = vi.fn();
    const { result } = renderHook(() => useSessionHistoryState({ onRecoveredModelId }));

    await waitFor(() => expect(sessionClientMock.getSessions).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.switchSession('session-1');
    });
    expect(result.current.messages[0]?.content).toBe('server copy');

    act(() => {
      result.current.setMessages([buildMessage('draft copy')]);
    });

    await act(async () => {
      await result.current.switchSession('session-2');
    });
    expect(result.current.messages[0]?.content).toBe('other session');

    await act(async () => {
      await result.current.switchSession('session-1');
    });

    expect(result.current.messages[0]?.content).toBe('draft copy');
    expect(sessionClientMock.getSessionMessages).toHaveBeenCalledTimes(2);
    expect(sessionClientMock.getSessionMessages).toHaveBeenNthCalledWith(1, 'session-1');
    expect(sessionClientMock.getSessionMessages).toHaveBeenNthCalledWith(2, 'session-2');
    expect(onRecoveredModelId).toHaveBeenCalledWith('mimo-v2.5-pro');
  });

  it('hydrates the latest assistant message from the artifact endpoint when session messages miss diagnostics', async () => {
    sessionClientMock.getSessionMessages.mockResolvedValue({
      success: true,
      messages: [{ role: 'assistant', content: 'server copy', timestamp: '10:00:00' }],
    });
    artifactClientMock.getLatestArtifact.mockResolvedValue({
      success: true,
      session_id: 'session-1',
      artifact_found: true,
      run_id: 'run-1',
      message_timestamp: '10:00:00',
      message_index: 0,
      artifact: {
        intent: { name: 'weekend trip', entities: {}, detail: {} },
        research: { summary: 'Saved research', evidence: [], destinations: ['杭州'], sourceTools: ['search_city'] },
        itinerary: {
          planId: 'plan-restored',
          explanation: 'Restored itinerary',
          steps: [],
          validationStatus: 'pass',
          validationErrors: [],
        },
        budget: { summary: {}, executionBudget: {}, staleResultCount: 0, fallbackSteps: 0 },
        verification: { passed: true, shouldRetry: false, issues: [], refreshTargets: [], summary: 'ok' },
        answer: 'server copy',
        reasoning: '',
        toolsUsed: ['calculate_budget'],
        metadata: {},
      },
    });

    const { result } = renderHook(() => useSessionHistoryState({ onRecoveredModelId: vi.fn() }));

    await waitFor(() => expect(sessionClientMock.getSessions).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.switchSession('session-1');
    });

    expect(artifactClientMock.getLatestArtifact).toHaveBeenCalledWith('session-1');
    expect(result.current.messages[0]?.diagnostics?.artifact?.itinerary.planId).toBe('plan-restored');
    expect(result.current.messages[0]?.diagnostics?.sessionId).toBe('session-1');
    expect(result.current.messages[0]?.diagnostics?.runId).toBe('run-1');
  });
});
