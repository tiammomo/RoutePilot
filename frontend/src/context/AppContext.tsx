'use client';

import React, { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { modelClient } from '@/services/api';
import type { AppConfig, ChatMode, Message, ModelInfo, SessionInfo } from '@/types';
import { logger } from '@/utils/logger';
import { useSessionHistoryState } from './useSessionHistoryState';

const DEFAULT_MODELS: ModelInfo[] = [
  {
    model_id: 'minimax-m2-5',
    name: 'MiniMax M2.5',
    provider: 'anthropic',
    model: 'MiniMax-M2.5',
  },
];

const DEFAULT_API_BASE =
  (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  'http://localhost:38000';

interface AppState {
  config: AppConfig;
  setConfig: (config: AppConfig) => void;

  availableModels: ModelInfo[];
  currentModelId: string | null;
  setCurrentModelId: (modelId: string) => void;
  loadingModels: boolean;

  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;

  currentSessionId: string | null;
  setCurrentSessionId: (id: string | null) => void;
  switchSession: (id: string | null) => Promise<void>;
  refreshSessions: (includeEmpty?: boolean) => Promise<void>;
  sessions: SessionInfo[];

  messages: Message[];
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;

  isStreaming: boolean;
  setIsStreaming: (streaming: boolean) => void;
  stopStreaming: boolean;
  setStopStreaming: (stop: boolean) => void;
}

const AppContext = createContext<AppState | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<AppConfig>({ apiBase: DEFAULT_API_BASE });
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [currentModelId, setCurrentModelIdState] = useState<string | null>('minimax-m2-5');
  const [loadingModels] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [stopStreaming, setStopStreaming] = useState(false);
  const [chatMode, setChatModeState] = useState<ChatMode>('react');
  const {
    currentSessionId,
    setCurrentSessionId,
    switchSession,
    refreshSessions,
    sessions,
    messages,
    addMessage,
    clearMessages,
    setMessages,
  } = useSessionHistoryState({
    onRecoveredModelId: (modelId) => setCurrentModelIdState(modelId),
  });

  useEffect(() => {
    const loadModels = async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      try {
        // Keep model bootstrap isolated so shell rendering never depends on it.
        const data = await modelClient.getAvailableModels({ signal: controller.signal, timeoutMs: 3000 });
        if (!data.success || !Array.isArray(data.models) || data.models.length === 0) return;

        const modelExists = data.models.some((model: ModelInfo) => model.model_id === currentModelId);
        setAvailableModels(data.models);
        setCurrentModelIdState(modelExists ? currentModelId : data.models[0].model_id);
      } catch {
        // Keep default models silently.
      } finally {
        clearTimeout(timeoutId);
      }
    };

    const timer = setTimeout(loadModels, 1000);
    return () => clearTimeout(timer);
  }, [currentModelId]);

  const handleSetCurrentModelId = async (modelId: string) => {
    setCurrentModelIdState(modelId);
    if (!currentSessionId) return;
    try {
      await modelClient.setSessionModel(currentSessionId, modelId);
    } catch (error) {
      logger.error('璁剧疆浼氳瘽妯″瀷澶辫触:', error);
    }
  };

  const value: AppState = {
    config,
    setConfig,
    availableModels,
    currentModelId,
    setCurrentModelId: handleSetCurrentModelId,
    loadingModels,
    chatMode,
    setChatMode: setChatModeState,
    currentSessionId,
    setCurrentSessionId,
    switchSession,
    refreshSessions,
    sessions,
    messages,
    addMessage,
    clearMessages,
    setMessages,
    isStreaming,
    setIsStreaming,
    stopStreaming,
    setStopStreaming,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useAppContext = (): AppState => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
};
