'use client';

import { useEffect, useRef, useState } from 'react';
import { modelClient, sessionClient } from '@/services/api';
import type { Message, SessionInfo } from '@/types';
import { logger } from '@/utils/logger';
import { normalizePersistedMessages } from '@/utils/sessionMessages';

export const SESSION_STORAGE_KEY = 'moyuan-current-session-id';

export function hasOwnSessionMessages(cache: Record<string, Message[]>, sessionId: string): boolean {
  return Object.prototype.hasOwnProperty.call(cache, sessionId);
}

export function buildVisibleSessions(
  sessions: SessionInfo[],
  options: { includeEmpty?: boolean; now?: Date } = {}
): SessionInfo[] {
  const uniqueSessions = Array.from(new Map(sessions.map((session) => [session.session_id, session])).values());
  if (options.includeEmpty) return uniqueSessions;

  const now = options.now ?? new Date();
  const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
  return uniqueSessions.filter((session) => session.message_count > 0 || new Date(session.last_active) > oneHourAgo);
}

export function readStoredSessionId(search: string, storage: Pick<Storage, 'getItem'>): string | null {
  if (search.includes('share=')) return null;
  return storage.getItem(SESSION_STORAGE_KEY);
}

export function persistStoredSessionId(storage: Pick<Storage, 'setItem' | 'removeItem'>, sessionId: string | null): void {
  if (sessionId) {
    storage.setItem(SESSION_STORAGE_KEY, sessionId);
    return;
  }
  storage.removeItem(SESSION_STORAGE_KEY);
}

interface UseSessionHistoryStateOptions {
  onRecoveredModelId: (modelId: string) => void;
}

interface UseSessionHistoryStateResult {
  currentSessionId: string | null;
  setCurrentSessionId: (id: string | null) => void;
  switchSession: (id: string | null) => Promise<void>;
  refreshSessions: (includeEmpty?: boolean) => Promise<void>;
  sessions: SessionInfo[];
  messages: Message[];
  addMessage: (message: Message) => void;
  clearMessages: () => void;
  setMessages: (messages: Message[]) => void;
}

export function useSessionHistoryState({
  onRecoveredModelId,
}: UseSessionHistoryStateOptions): UseSessionHistoryStateResult {
  const [currentSessionId, setCurrentSessionIdState] = useState<string | null>(null);
  const [messages, setMessagesState] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const sessionMessagesRef = useRef<Record<string, Message[]>>({});

  const cacheSessionMessages = (sessionId: string, nextMessages: Message[]) => {
    sessionMessagesRef.current = {
      ...sessionMessagesRef.current,
      [sessionId]: nextMessages,
    };
  };

  const loadSessionMessages = async (sessionId: string): Promise<Message[]> => {
    if (hasOwnSessionMessages(sessionMessagesRef.current, sessionId)) {
      return sessionMessagesRef.current[sessionId];
    }

    const data = await sessionClient.getSessionMessages(sessionId);
    const normalizedMessages = normalizePersistedMessages(data.messages);
    cacheSessionMessages(sessionId, normalizedMessages);
    return normalizedMessages;
  };

  const refreshSessions = async (includeEmpty: boolean = false) => {
    try {
      const data = await sessionClient.getSessions();
      setSessions(buildVisibleSessions(data.sessions, { includeEmpty }));
    } catch (error) {
      logger.error('加载会话失败:', error);
    }
  };

  const addMessage = (message: Message) => {
    setMessagesState((previous) => {
      const nextMessages = [...previous, message];
      if (currentSessionId) cacheSessionMessages(currentSessionId, nextMessages);
      return nextMessages;
    });
  };

  const clearMessages = () => {
    setMessagesState([]);
    if (currentSessionId) cacheSessionMessages(currentSessionId, []);
  };

  const setMessages = (nextMessages: Message[]) => {
    setMessagesState(nextMessages);
    if (currentSessionId) cacheSessionMessages(currentSessionId, nextMessages);
  };

  const switchSession = async (id: string | null) => {
    if (currentSessionId) {
      cacheSessionMessages(currentSessionId, messages);
    }

    setCurrentSessionIdState(id);
    if (!id) {
      setMessagesState([]);
      return;
    }

    try {
      const nextMessages = await loadSessionMessages(id);
      setMessagesState(nextMessages);
    } catch (error) {
      logger.error('加载会话消息失败:', error);
      setCurrentSessionIdState(null);
      setMessagesState([]);
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
      }
      return;
    }

    try {
      const data = await modelClient.getSessionModel(id);
      if (data.success && data.model_id && data.model_id !== 'default') {
        onRecoveredModelId(data.model_id);
      }
    } catch (error) {
      logger.error('获取会话模型失败:', error);
    }
  };

  useEffect(() => {
    void refreshSessions();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const storedSessionId = readStoredSessionId(window.location.search, window.localStorage);
    if (!storedSessionId) return;
    void switchSession(storedSessionId);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    persistStoredSessionId(window.localStorage, currentSessionId);
  }, [currentSessionId]);

  return {
    currentSessionId,
    setCurrentSessionId: setCurrentSessionIdState,
    switchSession,
    refreshSessions,
    sessions,
    messages,
    addMessage,
    clearMessages,
    setMessages,
  };
}
