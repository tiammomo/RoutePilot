import { describe, expect, it } from 'vitest';
import { hydrateMessagesWithLatestArtifact, normalizePersistedMessages } from '@/utils/sessionMessages';

describe('normalizePersistedMessages', () => {
  it('keeps assistant diagnostics for artifact-backed sessions', () => {
    const messages = normalizePersistedMessages([
      {
        role: 'assistant',
        content: 'saved answer',
        timestamp: '10:00:00',
        diagnostics: {
          planId: 'plan-321',
          artifact: {
            intent: { name: 'itinerary', entities: {}, detail: {} },
            research: { summary: 'Saved research', evidence: [], destinations: [], sourceTools: [] },
            itinerary: { planId: 'plan-321', explanation: '', steps: [], validationStatus: 'pass', validationErrors: [] },
            budget: { summary: {}, executionBudget: {}, staleResultCount: 0, fallbackSteps: 0 },
            verification: { passed: true, shouldRetry: false, issues: [], refreshTargets: [], summary: 'ok' },
            answer: 'saved answer',
            reasoning: '',
            toolsUsed: [],
            metadata: {},
          },
          subagentEvents: [{ subagent: 'planning', status: 'completed', timestamp: '10:00:01' }],
        },
      },
    ]);

    expect(messages).toHaveLength(1);
    expect(messages[0].diagnostics?.planId).toBe('plan-321');
    expect(messages[0].diagnostics?.artifact?.itinerary.planId).toBe('plan-321');
    expect(messages[0].diagnostics?.subagentEvents?.[0]?.subagent).toBe('planning');
  });

  it('hydrates the latest assistant message from persisted artifact payloads', () => {
    const messages = normalizePersistedMessages([
      {
        role: 'user',
        content: '帮我做个杭州周末计划',
        timestamp: '10:00:00',
      },
      {
        role: 'assistant',
        content: 'saved answer',
        timestamp: '10:01:00',
      },
    ]);

    const hydrated = hydrateMessagesWithLatestArtifact(messages, {
      success: true,
      session_id: 'session-1',
      artifact_found: true,
      run_id: 'run-restored',
      message_index: 1,
      message_timestamp: '10:01:00',
      artifact: {
        intent: { name: 'hangzhou weekend', entities: {}, detail: {} },
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
        answer: 'saved answer',
        reasoning: '',
        toolsUsed: ['calculate_budget'],
        metadata: {},
      },
    });

    expect(hydrated[1].diagnostics?.planId).toBe('plan-restored');
    expect(hydrated[1].diagnostics?.runId).toBe('run-restored');
    expect(hydrated[1].diagnostics?.artifact?.research.destinations).toEqual(['杭州']);
  });
});
