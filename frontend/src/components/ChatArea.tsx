'use client';

import React, { useEffect, useRef, useState } from 'react';
import { App, Button, Input, Space } from 'antd';
import { SendOutlined, StopOutlined } from '@ant-design/icons';
import { useAppContext } from '@/context/AppContext';
import { apiService } from '@/services/api';
import { logger } from '@/utils/logger';
import MessageList from './MessageList';
import ChatModeSelector from './ChatModeSelector';

const { TextArea } = Input;

const ChatArea: React.FC = () => {
  const {
    currentSessionId,
    setCurrentSessionId,
    messages,
    addMessage,
    isStreaming,
    setIsStreaming,
    setStopStreaming,
    refreshSessions,
    chatMode,
    setChatMode,
  } = useAppContext();

  const { message } = App.useApp();

  const [inputValue, setInputValue] = useState('');
  const [streamingMessage, setStreamingMessage] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasoningExpanded, setReasoningExpanded] = useState<Record<string, boolean>>({});
  const [currentTool, setCurrentTool] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef(false);
  const skipNextSessionResetRef = useRef(false);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
  }, [messages, streamingMessage, streamingReasoning, isThinking, waitingForResponse, currentTool]);

  useEffect(() => {
    if (skipNextSessionResetRef.current) {
      skipNextSessionResetRef.current = false;
      return;
    }

    setStreamingMessage('');
    setStreamingReasoning('');
    setWaitingForResponse(false);
    setIsThinking(false);
    setError(null);
    setIsStreaming(false);
    setStopStreaming(false);
    setCurrentTool(null);
    stopRef.current = false;
  }, [currentSessionId, setIsStreaming, setStopStreaming]);

  const toggleReasoning = (messageId: string) => {
    setReasoningExpanded((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  };

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed) {
      message.warning('请输入内容');
      return;
    }

    try {
      const isFirstMessage = !currentSessionId || messages.length === 0;

      let sessionId = currentSessionId;
      if (!sessionId) {
        const data = await apiService.createSession();
        sessionId = data.session_id;
        skipNextSessionResetRef.current = true;
        setCurrentSessionId(sessionId);
      }

      addMessage({
        role: 'user',
        content: trimmed,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      });

      setInputValue('');
      setIsStreaming(true);
      setStopStreaming(false);
      setWaitingForResponse(true);
      setIsThinking(true);
      setError(null);
      setCurrentTool(null);
      setStreamingMessage('');
      setStreamingReasoning('');
      stopRef.current = false;

      if (isFirstMessage && sessionId) {
        try {
          const sessionName = trimmed.slice(0, 15) + (trimmed.length > 15 ? '...' : '');
          await apiService.updateSessionName(sessionId, sessionName);
        } catch (err) {
          logger.error('设置会话名称失败:', err);
        }
      }

      let fullResponse = '';
      let fullReasoning = '';
      let reasoningTimestamp = '';

      await apiService.fetchStreamChat(
        {
          message: trimmed,
          session_id: sessionId!,
          mode: chatMode,
        },
        {
          onChunk: (content) => {
            fullResponse += content;
            setStreamingMessage((prev) => prev + content);
          },
          onReasoning: (content) => {
            fullReasoning += content;
            setStreamingReasoning((prev) => prev + content);
          },
          onReasoningStart: () => {
            setIsThinking(true);
          },
          onReasoningTimestamp: (timestamp) => {
            reasoningTimestamp = timestamp;
          },
          onReasoningEnd: () => {
            setIsThinking(false);
          },
          onAnswerStart: () => {
            // no-op
          },
          onToolStart: (toolName: string) => {
            setCurrentTool(toolName);
          },
          onToolEnd: () => {
            setCurrentTool(null);
          },
          onMetadata: () => {
            // no-op
          },
          onError: (errorMsg) => {
            message.destroy();
            message.error('错误: ' + errorMsg);
            setWaitingForResponse(false);
            setIsThinking(false);
            setCurrentTool(null);
            setError(errorMsg);
            fullResponse = `抱歉，出现错误：${errorMsg}`;
          },
          onComplete: () => {
            message.destroy();
            const finalReasoning = reasoningTimestamp
              ? `[Timestamp: ${reasoningTimestamp}]\n\n${fullReasoning}`
              : fullReasoning;
            const finalContent = fullResponse || streamingMessage;

            addMessage({
              role: 'assistant',
              content: finalContent,
              reasoning: finalReasoning,
              timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
            });

            setStreamingMessage('');
            setStreamingReasoning('');
            setWaitingForResponse(false);
            setIsStreaming(false);
            setIsThinking(false);
            setCurrentTool(null);
            stopRef.current = false;
          },
          onStop: () => stopRef.current,
        }
      );

      refreshSessions();
    } catch (err: unknown) {
      message.destroy();
      const errorMsg = err instanceof Error ? err.message : '未知错误';
      message.error('发送失败: ' + errorMsg);
      setWaitingForResponse(false);
      setIsThinking(false);
      setCurrentTool(null);
      setError(errorMsg);
    }
  };

  const handleStop = () => {
    stopRef.current = true;
    setStopStreaming(true);
    setWaitingForResponse(false);
    setIsThinking(false);
    setIsStreaming(false);
    setCurrentTool(null);

    if (streamingMessage || streamingReasoning) {
      addMessage({
        role: 'assistant',
        content: (streamingMessage || '已停止生成') + '\n\n⚠️ 已停止生成',
        reasoning: streamingReasoning,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      });
    }

    setStreamingMessage('');
    setStreamingReasoning('');
  };

  return (
    <div
      className="chat-input-area"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        padding: '24px',
        background: 'linear-gradient(180deg, #fafbfc 0%, #f3f4f6 100%)',
      }}
    >
      <div style={{ flex: 1, overflow: 'auto', marginBottom: '16px' }}>
        <MessageList
          messages={messages}
          streamingMessage={streamingMessage}
          streamingReasoning={streamingReasoning}
          isWaiting={waitingForResponse}
          isThinking={isThinking}
          currentTool={currentTool}
          reasoningExpanded={reasoningExpanded}
          onToggleReasoning={toggleReasoning}
        />

        {error && (
          <div
            style={{
              color: '#dc2626',
              padding: '14px 18px',
              background: 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)',
              borderRadius: '12px',
              margin: '0 16px 16px',
              border: '1px solid rgba(220, 38, 38, 0.2)',
              boxShadow: '0 2px 8px rgba(220, 38, 38, 0.1)',
            }}
          >
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div>
        <div
          style={{
            marginBottom: '14px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
            borderRadius: '14px',
            border: '1px solid rgba(0, 0, 0, 0.06)',
            boxShadow: '0 2px 10px rgba(0, 0, 0, 0.04)',
          }}
        >
          <ChatModeSelector value={chatMode} onChange={setChatMode} disabled={isStreaming} />
          <div
            style={{
              fontSize: '12px',
              color: '#722ed1',
              background: 'rgba(114, 46, 209, 0.08)',
              padding: '4px 12px',
              borderRadius: '12px',
            }}
          >
            {chatMode === 'direct' && '⚡ 快速响应'}
            {chatMode === 'react' && '🧠 深度思考'}
            {chatMode === 'plan' && '📋 先规划后执行'}
          </div>
        </div>

        <div
          style={{
            background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
            borderRadius: '20px',
            padding: '12px',
            boxShadow: '0 8px 30px rgba(0, 0, 0, 0.12)',
            border: '1px solid rgba(0, 0, 0, 0.08)',
          }}
        >
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={isStreaming ? '正在生成回答中...' : '输入你的旅游需求...'}
              disabled={isStreaming}
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{
                resize: 'none',
                border: 'none',
                boxShadow: 'none',
                outline: 'none',
              }}
            />
            {isStreaming ? (
              <Button
                type="primary"
                danger
                icon={<StopOutlined />}
                onClick={handleStop}
                style={{
                  borderRadius: '14px',
                  height: '42px',
                  padding: '0 20px',
                  background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                  border: 'none',
                  boxShadow: '0 4px 15px rgba(239, 68, 68, 0.4)',
                }}
              >
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim()}
                style={{
                  borderRadius: '14px',
                  height: '42px',
                  padding: '0 24px',
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  border: 'none',
                  boxShadow: '0 4px 15px rgba(102, 126, 234, 0.4)',
                }}
              >
                发送
              </Button>
            )}
          </Space.Compact>
        </div>
      </div>
    </div>
  );
};

export default ChatArea;
