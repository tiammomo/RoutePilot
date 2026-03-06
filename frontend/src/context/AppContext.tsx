'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Message, AppConfig, ModelInfo, SessionInfo, ChatMode } from '@/types';
import { apiService } from '@/services/api';
import { logger } from '@/utils/logger';

// 默认模型列表 - 快速加载，无需等待 API
const DEFAULT_MODELS: ModelInfo[] = [{
  model_id: 'minimax-m2-5',
  name: 'MiniMax M2.5',
  provider: 'anthropic',
  model: 'MiniMax-M2.5'
}];

// API 基础地址
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:38000';

interface AppState {
  // 配置
  config: AppConfig;
  setConfig: (config: AppConfig) => void;

  // 模型管理
  availableModels: ModelInfo[];
  currentModelId: string | null;
  setCurrentModelId: (modelId: string) => void;
  loadingModels: boolean;

  // 对话模式
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;

  // 会话
  currentSessionId: string | null;
  setCurrentSessionId: (id: string | null) => void;
  switchSession: (id: string | null) => Promise<void>;
  refreshSessions: () => Promise<void>;
  sessions: SessionInfo[];

  // 消息
  messages: Message[];
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;

  // 流式控制
  isStreaming: boolean;
  setIsStreaming: (streaming: boolean) => void;
  stopStreaming: boolean;
  setStopStreaming: (stop: boolean) => void;
}

const AppContext = createContext<AppState | undefined>(undefined);

export const AppProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<AppConfig>({
    apiBase: API_BASE
  });

  // 模型相关状态 - 立即使用默认模型，无需等待
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [currentModelId, setCurrentModelIdState] = useState<string | null>('minimax-m2-5');
  const [loadingModels, setLoadingModels] = useState(false);

  const [currentSessionId, setCurrentSessionIdState] = useState<string | null>(null);
  const [messages, setMessagesState] = useState<Message[]>([]);
  const [sessionMessages, setSessionMessages] = useState<Record<string, Message[]>>({});

  const [isStreaming, setIsStreaming] = useState(false);
  const [stopStreaming, setStopStreaming] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);

  // 对话模式状态
  const [chatMode, setChatModeState] = useState<ChatMode>('react');

  // 加载会话列表
  const loadSessions = async () => {
    try {
      const data = await apiService.getSessions();
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      const activeSessions = data.sessions.filter(s =>
        s.message_count > 0 ||
        new Date(s.last_active) > oneHourAgo
      );
      setSessions(activeSessions);
    } catch (error) {
      logger.error('加载会话失败:', error);
    }
  };

  // 加载可用模型列表 - 使用默认值，后台静默更新
  // 优化：默认模型立即显示，不显示加载状态
  useEffect(() => {
    const loadModels = async () => {
      try {
        // 添加超时保护：3秒内如果没有响应就放弃
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);

        const response = await fetch(
          `${API_BASE}/api/models`,
          { signal: controller.signal }
        );
        clearTimeout(timeoutId);

        if (!response.ok) return;

        const data = await response.json();
        if (data.success && data.models && data.models.length > 0) {
          const currentId = currentModelId;
          const modelExists = data.models.some((m: ModelInfo) => m.model_id === currentId);
          setAvailableModels(data.models);
          setCurrentModelIdState(modelExists ? currentId : data.models[0].model_id);
        }
        // 失败时保持默认模型，不更新状态
      } catch {
        // 静默失败，保持默认模型
      }
    };

    // 仅在组件挂载后静默加载，不触发 loading 状态
    // 默认模型已经立即可用，不需要显示加载状态
    const timer = setTimeout(loadModels, 1000); // 延迟1秒加载，让UI先渲染
    return () => clearTimeout(timer);
  }, []);

  // 初始加载会话列表
  useEffect(() => {
    loadSessions();
  }, []);

  const handleSetCurrentModelId = async (modelId: string) => {
    setCurrentModelIdState(modelId);
    if (currentSessionId) {
      try {
        await apiService.setSessionModel(currentSessionId, modelId);
      } catch (error) {
        logger.error('设置会话模型失败:', error);
      }
    }
  };

  const addMessage = (message: Message) => {
    setMessagesState(prev => {
      const newMessages = [...prev, message];
      if (currentSessionId) {
        setSessionMessages(cache => ({
          ...cache,
          [currentSessionId]: newMessages
        }));
      }
      return newMessages;
    });
  };

  const clearMessages = () => {
    setMessagesState([]);
    if (currentSessionId) {
      setSessionMessages(cache => ({
        ...cache,
        [currentSessionId]: []
      }));
    }
  };

  const setMessages = (newMessages: Message[]) => {
    setMessagesState(newMessages);
    if (currentSessionId) {
      setSessionMessages(cache => ({
        ...cache,
        [currentSessionId]: newMessages
      }));
    }
  };

  const setCurrentSessionId = (id: string | null) => {
    setCurrentSessionIdState(id);
  };

  const refreshSessions = async (includeEmpty: boolean = false) => {
    try {
      const data = await apiService.getSessions();
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);

      // 去重：使用 Map 确保 session_id 唯一，保留最后出现的
      const uniqueSessionsMap = new Map(data.sessions.map(s => [s.session_id, s]));
      const uniqueSessions = Array.from(uniqueSessionsMap.values());

      if (includeEmpty) {
        setSessions(uniqueSessions);
      } else {
        const activeSessions = uniqueSessions.filter(s =>
          s.message_count > 0 ||
          new Date(s.last_active) > oneHourAgo
        );
        setSessions(activeSessions);
      }
    } catch (error) {
      // 静默失败
    }
  };

  const switchSession = async (id: string | null) => {
    if (currentSessionId && messages.length > 0) {
      setSessionMessages(cache => ({
        ...cache,
        [currentSessionId]: messages
      }));
    }

    setCurrentSessionIdState(id);

    if (id && sessionMessages[id]) {
      setMessagesState(sessionMessages[id]);
    } else {
      setMessagesState([]);
    }

    if (id) {
      try {
        const data = await apiService.getSessionModel(id);
        if (data.success && data.model_id && data.model_id !== 'default') {
          setCurrentModelIdState(data.model_id);
        }
      } catch (error) {
        logger.error('获取会话模型失败:', error);
      }
    }
  };

  const handleSetChatMode = (mode: ChatMode) => {
    setChatModeState(mode);
  };

  const value: AppState = {
    config,
    setConfig,
    availableModels,
    currentModelId,
    setCurrentModelId: handleSetCurrentModelId,
    loadingModels,
    chatMode,
    setChatMode: handleSetChatMode,
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
  if (!context) {
    throw new Error('useAppContext must be used within AppProvider');
  }
  return context;
};
