'use client';

import { useEffect, useRef, useState } from 'react';
import { modelClient } from '@/services/api';
import type { ModelInfo } from '@/types';
import { logger } from '@/utils/logger';

export const DEFAULT_MODELS: ModelInfo[] = [
  {
    model_id: 'mimo-v2.5-pro',
    name: 'mimo-v2.5-pro',
    provider: 'anthropic-compatible',
    model: 'mimo-v2.5-pro',
  },
];

export function resolveBootstrapModelId(models: ModelInfo[], preferredModelId: string | null): string | null {
  if (models.length === 0) return null;
  if (preferredModelId && models.some((model) => model.model_id === preferredModelId)) {
    return preferredModelId;
  }
  return models[0].model_id;
}

interface UseModelBootstrapStateOptions {
  currentSessionId: string | null;
}

interface UseModelBootstrapStateResult {
  availableModels: ModelInfo[];
  currentModelId: string | null;
  loadingModels: boolean;
  recoverModelId: (modelId: string) => void;
  setCurrentModelId: (modelId: string) => Promise<void>;
}

export function useModelBootstrapState({
  currentSessionId,
}: UseModelBootstrapStateOptions): UseModelBootstrapStateResult {
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [currentModelId, setCurrentModelIdState] = useState<string | null>(DEFAULT_MODELS[0]?.model_id ?? null);
  const [loadingModels, setLoadingModels] = useState(false);
  const currentModelIdRef = useRef<string | null>(DEFAULT_MODELS[0]?.model_id ?? null);

  const updateCurrentModelId = (modelId: string | null) => {
    currentModelIdRef.current = modelId;
    setCurrentModelIdState(modelId);
  };

  useEffect(() => {
    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const controller = new AbortController();
    const loadModels = async () => {
      const shouldShowLoader = availableModels.length === 0;
      if (shouldShowLoader && active) {
        setLoadingModels(true);
      }

      timeoutId = setTimeout(() => controller.abort(), 3000);
      try {
        // Keep model bootstrap isolated so shell rendering never depends on it.
        const data = await modelClient.getAvailableModels({ signal: controller.signal, timeoutMs: 3000 });
        if (!active || !data.success || !Array.isArray(data.models) || data.models.length === 0) return;

        setAvailableModels(data.models);
        updateCurrentModelId(resolveBootstrapModelId(data.models, currentModelIdRef.current));
      } catch {
        // Keep default models silently.
      } finally {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        if (active) {
          setLoadingModels(false);
        }
      }
    };

    const timer = setTimeout(loadModels, 1000);
    return () => {
      active = false;
      clearTimeout(timer);
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      controller.abort();
    };
  }, []);

  const recoverModelId = (modelId: string) => {
    updateCurrentModelId(modelId);
  };

  const setCurrentModelId = async (modelId: string) => {
    updateCurrentModelId(modelId);
    if (!currentSessionId) return;

    try {
      await modelClient.setSessionModel(currentSessionId, modelId);
    } catch (error) {
      logger.error('设置会话模型失败:', error);
      throw error;
    }
  };

  return {
    availableModels,
    currentModelId,
    loadingModels,
    recoverModelId,
    setCurrentModelId,
  };
}
