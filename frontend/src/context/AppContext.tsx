'use client';

import React, { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { apiService } from '@/services/api';
import type { AppConfig, ChatMode, Message, ModelInfo, SessionInfo } from '@/types';
import { logger } from '@/utils/logger';

const DEFAULT_MODELS: ModelInfo[] = [
  {
    model_id: 'minimax-m2-5',
    name: 'MiniMax M2.5',
    provider: 'anthropic',
    model: 'MiniMax-M2.5',
  },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:38000';

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
  const [config, setConfig] = useState<AppConfig>({ apiBase: API_BASE });
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [currentModelId, setCurrentModelIdState] = useState<string | null>('minimax-m2-5');
  const [loadingModels] = useState(false);

  const [currentSessionId, setCurrentSessionIdState] = useState<string | null>(null);
  const [messages, setMessagesState] = useState<Message[]>([]);
  // Local per-session cache avoids extra round-trips when users switch tabs rapidly.
  const [sessionMessages, setSessionMessages] = useState<Record<string, Message[]>>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const [stopStreaming, setStopStreaming] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [chatMode, setChatModeState] = useState<ChatMode>('react');

  const loadSessions = async () => {
    try {
      const data = await apiService.getSessions();
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      // Keep recent empty sessions visible for short-term navigation continuity.
      const activeSessions = data.sessions.filter(
        (session) => session.message_count > 0 || new Date(session.last_active) > oneHourAgo
      );
      setSessions(activeSessions);
    } catch (error) {
      logger.error('加载会话失败:', error);
    }
  };

  useEffect(() => {
    const loadModels = async () => {
      try {
        // Use native fetch + short timeout here so model bootstrap failure never blocks app shell.
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);
        const response = await fetch(`${API_BASE}/api/models`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!response.ok) return;

        const data = await response.json();
        if (!data.success || !Array.isArray(data.models) || data.models.length === 0) return;

        const modelExists = data.models.some((model: ModelInfo) => model.model_id === currentModelId);
        setAvailableModels(data.models);
        setCurrentModelIdState(modelExists ? currentModelId : data.models[0].model_id);
      } catch {
        // Keep default models silently.
      }
    };

    const timer = setTimeout(loadModels, 1000);
    return () => clearTimeout(timer);
  }, [currentModelId]);

  useEffect(() => {
    loadSessions();
  }, []);

  const handleSetCurrentModelId = async (modelId: string) => {
    setCurrentModelIdState(modelId);
    if (!currentSessionId) return;
    try {
      await apiService.setSessionModel(currentSessionId, modelId);
    } catch (error) {
      logger.error('设置会话模型失败:', error);
    }
  };

  const addMessage = (message: Message) => {
    setMessagesState((prev) => {
      const next = [...prev, message];
      if (currentSessionId) {
        setSessionMessages((cache) => ({ ...cache, [currentSessionId]: next }));
      }
      return next;
    });
  };

  const clearMessages = () => {
    setMessagesState([]);
    if (currentSessionId) {
      setSessionMessages((cache) => ({ ...cache, [currentSessionId]: [] }));
    }
  };

  const setMessages = (newMessages: Message[]) => {
    setMessagesState(newMessages);
    if (currentSessionId) {
      setSessionMessages((cache) => ({ ...cache, [currentSessionId]: newMessages }));
    }
  };

  const setCurrentSessionId = (id: string | null) => {
    setCurrentSessionIdState(id);
  };

  const refreshSessions = async (includeEmpty: boolean = false) => {
    try {
      const data = await apiService.getSessions();
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      const uniqueSessionsMap = new Map(data.sessions.map((session) => [session.session_id, session]));
      const uniqueSessions = Array.from(uniqueSessionsMap.values());

      if (includeEmpty) {
        setSessions(uniqueSessions);
        return;
      }

      const activeSessions = uniqueSessions.filter(
        (session) => session.message_count > 0 || new Date(session.last_active) > oneHourAgo
      );
      setSessions(activeSessions);
    } catch {
      // Ignore refresh failures.
    }
  };

  const switchSession = async (id: string | null) => {
    // Persist current draft history into local cache before switching session scope.
    if (currentSessionId && messages.length > 0) {
      setSessionMessages((cache) => ({ ...cache, [currentSessionId]: messages }));
    }

    setCurrentSessionIdState(id);
    setMessagesState(id && sessionMessages[id] ? sessionMessages[id] : []);

    if (!id) return;
    try {
      const data = await apiService.getSessionModel(id);
      if (data.success && data.model_id && data.model_id !== 'default') {
        setCurrentModelIdState(data.model_id);
      }
    } catch (error) {
      logger.error('获取会话模型失败:', error);
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
