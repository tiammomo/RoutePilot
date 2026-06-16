'use client';

import React, { createContext, useContext, useState, type ReactNode } from 'react';
import type { AppConfig, ChatMode, Message, ModelInfo, SessionInfo } from '@/types';
import { useModelBootstrapState } from './useModelBootstrapState';
import { useSessionHistoryState } from './useSessionHistoryState';

const DEFAULT_API_BASE =
  (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  'http://localhost:38083';

interface AppState {
  config: AppConfig;
  setConfig: (config: AppConfig) => void;

  availableModels: ModelInfo[];
  currentModelId: string | null;
  setCurrentModelId: (modelId: string) => Promise<void>;
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
    onRecoveredModelId: (modelId) => recoverModelId(modelId),
  });
  const { availableModels, currentModelId, loadingModels, recoverModelId, setCurrentModelId } =
    useModelBootstrapState({
      currentSessionId,
    });

  const value: AppState = {
    config,
    setConfig,
    availableModels,
    currentModelId,
    setCurrentModelId,
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
