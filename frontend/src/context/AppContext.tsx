'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Message, AppConfig, ModelInfo, SessionInfo, ChatMode } from '@/types';
import { apiService } from '@/services/api';
import { logger } from '@/utils/logger';

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
    apiBase: process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000'
  });

  // 模型相关状态
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [currentModelId, setCurrentModelIdState] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(true);

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

  // 加载可用模型列表
  useEffect(() => {
    const loadModels = async () => {
      // 超时控制：10秒后强制结束加载
      const TIMEOUT = 10000;
      let loaded = false;

      const setLoaded = () => { loaded = true; };

      const timeoutId = setTimeout(() => {
        if (!loaded) {
          logger.warn('模型列表加载超时，使用默认模型');
          setAvailableModels([{
            model_id: 'minimax-m2-5',
            name: 'MiniMax M2.5',
            provider: 'anthropic',
            model: 'MiniMax-M2.5'
          }]);
          setCurrentModelIdState('minimax-m2-5');
          setLoadingModels(false);
        }
      }, TIMEOUT);

      try {
        setLoadingModels(true);
        const data = await apiService.getAvailableModels();
        if (data.success && data.models.length > 0) {
          setAvailableModels(data.models);
          setCurrentModelIdState(data.models[0].model_id);
        } else {
          // API 返回空列表，使用默认模型
          setAvailableModels([{
            model_id: 'minimax-m2-5',
            name: 'MiniMax M2.5',
            provider: 'anthropic',
            model: 'MiniMax-M2.5'
          }]);
          setCurrentModelIdState('minimax-m2-5');
        }
      } catch (error) {
        logger.error('加载模型列表失败:', error);
        // 使用默认模型作为降级
        setAvailableModels([{
          model_id: 'minimax-m2-5',
          name: 'MiniMax M2.5',
          provider: 'anthropic',
          model: 'MiniMax-M2.5'
        }]);
        setCurrentModelIdState('minimax-m2-5');
      } finally {
        loaded = true;
        clearTimeout(timeoutId);
        setLoadingModels(false);
      }
    };

    loadModels();
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
