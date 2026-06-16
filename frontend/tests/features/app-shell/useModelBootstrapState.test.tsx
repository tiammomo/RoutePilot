import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const modelClientMock = vi.hoisted(() => ({
  getAvailableModels: vi.fn(),
  setSessionModel: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  modelClient: modelClientMock,
}));

import { DEFAULT_MODELS, resolveBootstrapModelId, useModelBootstrapState } from '@/context/useModelBootstrapState';

describe('useModelBootstrapState helpers', () => {
  it('keeps the preferred model when it is still available', () => {
    expect(resolveBootstrapModelId(DEFAULT_MODELS, 'mimo-v2.5-pro')).toBe('mimo-v2.5-pro');
  });

  it('falls back to the first available model when preferred model is missing', () => {
    expect(
      resolveBootstrapModelId(
        [
          {
            model_id: 'mimo-v2.5-pro',
            name: 'mimo-v2.5-pro',
            provider: 'anthropic-compatible',
            model: 'mimo-v2.5-pro',
          },
        ],
        'missing-model'
      )
    ).toBe('mimo-v2.5-pro');
  });
});

describe('useModelBootstrapState', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    modelClientMock.getAvailableModels.mockReset();
    modelClientMock.setSessionModel.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('bootstraps available models and keeps the recovered model selection', async () => {
    modelClientMock.getAvailableModels.mockResolvedValue({
      success: true,
      models: [
        {
          model_id: 'mimo-v2.5-pro',
          name: 'mimo-v2.5-pro',
          provider: 'anthropic-compatible',
          model: 'mimo-v2.5-pro',
        },
        {
          model_id: 'gpt-4o-mini',
          name: 'GPT-4o Mini',
          provider: 'openai',
          model: 'gpt-4o-mini',
        },
      ],
    });

    const { result } = renderHook(() => useModelBootstrapState({ currentSessionId: null }));

    await act(async () => {
      result.current.recoverModelId('gpt-4o-mini');
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(modelClientMock.getAvailableModels).toHaveBeenCalledTimes(1);
    expect(result.current.currentModelId).toBe('gpt-4o-mini');
    expect(result.current.availableModels).toHaveLength(2);
  });

  it('persists the selected model to the current session', async () => {
    modelClientMock.getAvailableModels.mockResolvedValue({
      success: false,
      models: [],
    });
    modelClientMock.setSessionModel.mockResolvedValue({
      success: true,
      model_id: 'mimo-v2.5-pro',
    });

    const { result } = renderHook(() => useModelBootstrapState({ currentSessionId: 'session-1' }));

    await act(async () => {
      await result.current.setCurrentModelId('mimo-v2.5-pro');
    });

    expect(result.current.currentModelId).toBe('mimo-v2.5-pro');
    expect(modelClientMock.setSessionModel).toHaveBeenCalledWith('session-1', 'mimo-v2.5-pro');
  });

  it('rethrows session model sync failures so the UI can surface them', async () => {
    modelClientMock.getAvailableModels.mockResolvedValue({
      success: false,
      models: [],
    });
    modelClientMock.setSessionModel.mockRejectedValue(new Error('sync failed'));

    const { result } = renderHook(() => useModelBootstrapState({ currentSessionId: 'session-1' }));

    await act(async () => {
      await expect(result.current.setCurrentModelId('mimo-v2.5-pro')).rejects.toThrow('sync failed');
    });
  });
});
