import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';

const sessionClientMock = vi.hoisted(() => ({
  getSessions: vi.fn(),
  getSessionMessages: vi.fn(),
}));

const artifactClientMock = vi.hoisted(() => ({
  getLatestArtifact: vi.fn(),
}));

const modelClientMock = vi.hoisted(() => ({
  getAvailableModels: vi.fn(),
  getSessionModel: vi.fn(),
  setSessionModel: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  artifactClient: artifactClientMock,
  sessionClient: sessionClientMock,
  modelClient: modelClientMock,
}));

import { AppProvider, useAppContext } from '@/context/AppContext';

function Probe() {
  const { currentSessionId, messages } = useAppContext();
  const firstMessage = messages[0];
  return (
    <div>
      <div data-testid="session-id">{currentSessionId ?? 'none'}</div>
      <div data-testid="message-content">{firstMessage?.content ?? 'empty'}</div>
      <div data-testid="plan-id">{firstMessage?.diagnostics?.artifact?.itinerary.planId ?? 'none'}</div>
    </div>
  );
}

describe('AppProvider session hydration', () => {
  beforeEach(() => {
    window.localStorage.clear();
    sessionClientMock.getSessions.mockReset();
    sessionClientMock.getSessionMessages.mockReset();
    artifactClientMock.getLatestArtifact.mockReset();
    modelClientMock.getAvailableModels.mockReset();
    modelClientMock.getSessionModel.mockReset();
    modelClientMock.setSessionModel.mockReset();
    modelClientMock.getAvailableModels.mockResolvedValue({ success: false, models: [] });
    artifactClientMock.getLatestArtifact.mockResolvedValue({
      success: true,
      session_id: 'session-1',
      artifact_found: false,
      artifact: null,
      run_id: null,
      message_timestamp: null,
      message_index: null,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('restores stored session messages and diagnostics after refresh', async () => {
    const now = new Date().toISOString();
    window.localStorage.setItem('moyuan-current-session-id', 'session-1');

    sessionClientMock.getSessions.mockResolvedValue({
      sessions: [{ session_id: 'session-1', message_count: 2, last_active: now, name: 'Saved session' }],
    });
    sessionClientMock.getSessionMessages.mockResolvedValue({
      success: true,
      messages: [
        {
          role: 'assistant',
          content: 'saved answer',
          timestamp: '10:01:00',
          diagnostics: {
            artifact: {
              intent: { name: 'itinerary', entities: {}, detail: {} },
              research: { summary: 'Saved research', evidence: [], destinations: [], sourceTools: [] },
              itinerary: {
                planId: 'plan-restored',
                explanation: 'Restored itinerary',
                steps: [],
                validationStatus: 'pass',
                validationErrors: [],
              },
              budget: { summary: {}, executionBudget: {}, staleResultCount: 0, fallbackSteps: 0 },
              verification: { passed: true, shouldRetry: false, issues: [], refreshTargets: [], summary: 'ok' },
              answer: 'saved answer',
              reasoning: '',
              toolsUsed: [],
              metadata: {},
            },
          },
        },
      ],
    });
    modelClientMock.getSessionModel.mockResolvedValue({
      success: true,
      model_id: 'minimax-m2-5',
    });

    render(
      <AppProvider>
        <Probe />
      </AppProvider>
    );

    await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent('session-1'));
    await waitFor(() => expect(screen.getByTestId('message-content')).toHaveTextContent('saved answer'));
    expect(screen.getByTestId('plan-id')).toHaveTextContent('plan-restored');
    expect(sessionClientMock.getSessionMessages).toHaveBeenCalledWith('session-1');
  });

  it('backfills persisted artifact diagnostics from the artifact endpoint during session restore', async () => {
    const now = new Date().toISOString();
    window.localStorage.setItem('moyuan-current-session-id', 'session-2');

    sessionClientMock.getSessions.mockResolvedValue({
      sessions: [{ session_id: 'session-2', message_count: 1, last_active: now, name: 'Restored artifact session' }],
    });
    sessionClientMock.getSessionMessages.mockResolvedValue({
      success: true,
      messages: [
        {
          role: 'assistant',
          content: 'saved answer',
          timestamp: '10:05:00',
        },
      ],
    });
    artifactClientMock.getLatestArtifact.mockResolvedValue({
      success: true,
      session_id: 'session-2',
      artifact_found: true,
      run_id: 'run-artifact',
      message_timestamp: '10:05:00',
      message_index: 0,
      artifact: {
        intent: { name: 'itinerary', entities: {}, detail: {} },
        research: { summary: 'Saved research', evidence: [], destinations: ['杭州'], sourceTools: [] },
        itinerary: {
          planId: 'plan-from-artifact',
          explanation: 'Restored itinerary',
          steps: [],
          validationStatus: 'pass',
          validationErrors: [],
        },
        budget: { summary: {}, executionBudget: {}, staleResultCount: 0, fallbackSteps: 0 },
        verification: { passed: true, shouldRetry: false, issues: [], refreshTargets: [], summary: 'ok' },
        answer: 'saved answer',
        reasoning: '',
        toolsUsed: [],
        metadata: {},
      },
    });
    modelClientMock.getSessionModel.mockResolvedValue({
      success: true,
      model_id: 'minimax-m2-5',
    });

    render(
      <AppProvider>
        <Probe />
      </AppProvider>
    );

    await waitFor(() => expect(screen.getByTestId('session-id')).toHaveTextContent('session-2'));
    await waitFor(() => expect(screen.getByTestId('plan-id')).toHaveTextContent('plan-from-artifact'));
    expect(artifactClientMock.getLatestArtifact).toHaveBeenCalledWith('session-2');
  });
});
