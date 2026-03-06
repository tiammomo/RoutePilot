'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Input, Button, Space, Card, App } from 'antd';
import { SendOutlined, StopOutlined, RobotOutlined } from '@ant-design/icons';
import { useAppContext } from '@/context/AppContext';
import { apiService } from '@/services/api';
import { logger } from '@/utils/logger';
import MessageList from './MessageList';
import ChatModeSelector from './ChatModeSelector';

const { TextArea } = Input;

// 自定义 Hook：动态加载动画
const useLoadingDots = (isLoading: boolean) => {
  const [dots, setDots] = useState('');

  useEffect(() => {
    if (!isLoading) {
      setDots('');
      return;
    }

    const interval = setInterval(() => {
      setDots((prev) => {
        if (prev === '') return '.';
        if (prev === '.') return '..';
        if (prev === '..') return '...';
        return '';
      });
    }, 500);

    return () => clearInterval(interval);
  }, [isLoading]);

  return dots;
};

const ChatArea: React.FC = () => {
  const {
    currentSessionId,
    setCurrentSessionId,
    messages,
    addMessage,
    isStreaming,
    setIsStreaming,
    stopStreaming,
    setStopStreaming,
    refreshSessions,
    chatMode,
    setChatMode,
  } = useAppContext();

  // 使用 antd App 上下文获取 message 实例
  const { message } = App.useApp();

  const [inputValue, setInputValue] = useState('');
  const [streamingMessage, setStreamingMessage] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStartTime, setThinkingStartTime] = useState<number | null>(null);
  const [thinkingElapsed, setThinkingElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [reasoningExpanded, setReasoningExpanded] = useState<Record<string, boolean>>({});
  const [currentTool, setCurrentTool] = useState<string | null>(null); // 当前执行的工具
  const [toolsUsed, setToolsUsed] = useState<string[]>([]); // 已使用的工具列表
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef(false); // 使用 ref 追踪停止状态，避免闭包问题

  const loadingDots = useLoadingDots(waitingForResponse);

  // 思考计时器
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isThinking && thinkingStartTime) {
      interval = setInterval(() => {
        setThinkingElapsed(Math.floor((Date.now() - thinkingStartTime) / 1000));
      }, 1000);
    } else if (!isThinking) {
      setThinkingElapsed(0);
    }
    return () => clearInterval(interval);
  }, [isThinking, thinkingStartTime]);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage, streamingReasoning, isThinking, waitingForResponse]);

  // 监听会话变化，重置所有流式状态
  useEffect(() => {
    setStreamingMessage('');
    setStreamingReasoning('');
    setWaitingForResponse(false);
    setIsThinking(false);
    setThinkingStartTime(null);
    setThinkingElapsed(0);
    setError(null);
    setIsStreaming(false);
    setStopStreaming(false);
    setCurrentTool(null);
    setToolsUsed([]);
  }, [currentSessionId]);

  const toggleReasoning = (messageId: string) => {
    setReasoningExpanded(prev => ({
      ...prev,
      [messageId]: !prev[messageId]
    }));
  };

  const handleSend = async () => {
    console.log('[ChatArea] handleSend 被调用, inputValue:', inputValue);
    console.log('[ChatArea] currentSessionId:', currentSessionId);

    if (!inputValue.trim()) {
      console.log('[ChatArea] 输入为空，直接返回');
      message.warning('请输入内容');
      return;
    }

    try {
      // 显示加载状态
      message.loading('正在发送...', 0);

      const userMessageContent = inputValue.trim();
      const isFirstMessage = !currentSessionId || messages.length === 0;

      let sessionId = currentSessionId;
      if (!sessionId) {
        console.log('[ChatArea] 创建新会话...');
        const data = await apiService.createSession();
        console.log('[ChatArea] 会话创建成功:', data);
        sessionId = data.session_id;
        setCurrentSessionId(sessionId);
      }

      const userMessage = {
        role: 'user' as const,
        content: inputValue,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      };

      addMessage(userMessage);
      setInputValue('');
      setIsStreaming(true);
      setStopStreaming(false);
      setWaitingForResponse(true);
      setIsThinking(true);
      setThinkingStartTime(Date.now());
      setError(null);

      setStreamingMessage('');
      setStreamingReasoning('');

      // 设置会话名称
      if (isFirstMessage) {
        try {
          const sessionName = userMessageContent.slice(0, 15) + (userMessageContent.length > 15 ? '...' : '');
          await apiService.updateSessionName(sessionId, sessionName);
        } catch (error) {
          logger.error('设置会话名称失败:', error);
        }
      }

      let fullResponse = '';
      let fullReasoning = '';
      let reasoningTimestamp = '';

      console.log('[ChatArea] 开始调用 fetchStreamChat, sessionId:', sessionId);

      await apiService.fetchStreamChat(
        {
          message: userMessage.content,
          session_id: sessionId,
          mode: chatMode,
        },
        {
          onChunk: (content) => {
            console.log('[ChatArea] onChunk:', content.slice(0, 50));
            fullResponse += content;
            setStreamingMessage((prev) => prev + content);
          },
          onReasoning: (content) => {
            console.log('[ChatArea] onReasoning:', content.slice(0, 50));
            fullReasoning += content;
            setStreamingReasoning((prev) => prev + content);
          },
          onReasoningStart: () => {
            console.log('[ChatArea] onReasoningStart');
            setIsThinking(true);
            if (!thinkingStartTime) {
              setThinkingStartTime(Date.now());
            }
          },
          onReasoningTimestamp: (timestamp) => {
            reasoningTimestamp = timestamp;
          },
          onReasoningEnd: () => {
            console.log('[ChatArea] onReasoningEnd');
            setIsThinking(false);
          },
          onAnswerStart: () => {
            console.log('[ChatArea] onAnswerStart');
          },
          onToolStart: (toolName: string) => {
            console.log('[ChatArea] onToolStart:', toolName);
            setCurrentTool(toolName);
            setToolsUsed(prev => [...prev, toolName]);
          },
          onToolEnd: (toolName: string, result: string) => {
            console.log('[ChatArea] onToolEnd:', toolName);
            setCurrentTool(null);
          },
          onMetadata: (data) => {
            console.log('[ChatArea] onMetadata:', data);
          },
          onError: (errorMsg) => {
            console.error('[ChatArea] onError:', errorMsg);
            message.destroy();
            message.error('错误: ' + errorMsg);
            setWaitingForResponse(false);
            setIsThinking(false);
            setError(errorMsg);
            fullResponse = `抱歉，出现错误：${errorMsg}`;
          },
          onComplete: () => {
            console.log('[ChatArea] onComplete');
            message.destroy();
            const finalReasoning = reasoningTimestamp ? `[Timestamp: ${reasoningTimestamp}]\n\n${fullReasoning}` : fullReasoning;
            const finalContent = fullResponse || streamingMessage;

            const finalMessage = {
              role: 'assistant' as const,
              content: finalContent,
              reasoning: finalReasoning,
              timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
            };

            addMessage(finalMessage);
            setStreamingMessage('');
            setStreamingReasoning('');
            setWaitingForResponse(false);
            setIsStreaming(false);
            setIsThinking(false);  // 关键：流结束后重置思考状态
            setCurrentTool(null);  // 重置工具状态
            stopRef.current = false;
          },
          onStop: () => stopRef.current,
        }
      );

      refreshSessions();
    } catch (error: unknown) {
      console.error('[ChatArea] handleSend 错误:', error);
      message.destroy();
      const errorMsg = error instanceof Error ? error.message : '未知错误';
      message.error('发送失败: ' + errorMsg);
      setWaitingForResponse(false);
      setIsThinking(false);
      setError(errorMsg);
    }
  };

  const handleStop = () => {
    stopRef.current = true;
    setStopStreaming(true);
    setWaitingForResponse(false);
    setIsThinking(false);
    setIsStreaming(false);

    if (streamingMessage || streamingReasoning) {
      const finalMessage = {
        role: 'assistant' as const,
        content: (streamingMessage || '已停止生成') + '\n\n⚠️ 已停止生成',
        reasoning: streamingReasoning,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      };
      addMessage(finalMessage);
    }

    setStreamingMessage('');
    setStreamingReasoning('');
  };

  return (
    <div className="chat-input-area" style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '24px',
      background: 'linear-gradient(180deg, #fafbfc 0%, #f3f4f6 100%)'
    }}>
      {/* 现代化头部 */}
      <div className="chat-header" style={{
        marginBottom: '20px',
        padding: '20px 24px',
        background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
        borderRadius: '16px',
        boxShadow: '0 2px 12px rgba(0, 0, 0, 0.06)',
        border: '1px solid rgba(0, 0, 0, 0.04)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '14px',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 15px rgba(102, 126, 234, 0.4)'
          }}>
            <span style={{ fontSize: '24px' }}>✈️</span>
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '22px', fontWeight: 600, color: '#1f2937' }}>小帅旅游助手</h2>
            <p style={{ margin: '4px 0 0 0', color: '#6b7280', fontSize: '13px' }}>为您提供个性化的旅游推荐和路线规划</p>
          </div>
        </div>
        {/* 状态指示器 */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 14px',
          background: isStreaming ? 'rgba(17, 153, 142, 0.1)' : 'rgba(107, 114, 128, 0.1)',
          borderRadius: '20px'
        }}>
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: isStreaming ? '#11998e' : '#6b7280',
            animation: isStreaming ? 'pulse 2s infinite' : 'none'
          }} />
          <span style={{
            fontSize: '12px',
            color: isStreaming ? '#11998e' : '#6b7280',
            fontWeight: 500
          }}>
            {isStreaming ? '工作中' : '在线'}
          </span>
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', marginBottom: '16px' }}>
        <MessageList
          messages={messages}
          streamingMessage={streamingMessage}
          streamingReasoning={streamingReasoning}
          isThinking={isThinking}
          reasoningExpanded={reasoningExpanded}
          onToggleReasoning={toggleReasoning}
        />

        {/* 工具执行状态提示 */}
        {currentTool && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '12px 20px',
            margin: '0 16px 16px',
            background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
            borderRadius: '12px',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            boxShadow: '0 2px 12px rgba(245, 158, 11, 0.15)',
            animation: 'fadeInUp 0.3s ease-out'
          }}>
            <div style={{
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: '10px',
              animation: 'pulse 1.5s infinite'
            }}>
              <span style={{ fontSize: '10px' }}>⚡</span>
            </div>
            <span style={{ color: '#92400e', fontSize: '13px', fontWeight: 500 }}>
              正在调用工具: <strong>{currentTool}</strong>
            </span>
          </div>
        )}

        {/* 错误显示 */}
        {error && (
          <div style={{
            color: '#dc2626',
            padding: '14px 18px',
            background: 'linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%)',
            borderRadius: '12px',
            margin: '0 16px 16px',
            border: '1px solid rgba(220, 38, 38, 0.2)',
            boxShadow: '0 2px 8px rgba(220, 38, 38, 0.1)'
          }}>
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div>
        {!currentSessionId && messages.length === 0 && (
          <div style={{
            marginBottom: '16px',
            maxWidth: '100%'
          }}>
            {/* 欢迎提示 */}
            <div style={{
              textAlign: 'center',
              padding: '20px',
              background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8eb 100%)',
              borderRadius: '12px',
              marginBottom: '16px'
            }}>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#262730', marginBottom: '8px' }}>
                欢迎使用小帅旅游助手
              </div>
              <div style={{ fontSize: '13px', color: '#666' }}>
                我可以帮您规划旅游路线、推荐景点、提供旅行建议等
              </div>
            </div>

            {/* 示例问题 - 现代胶囊按钮 */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{
                fontSize: '13px',
                color: '#9ca3af',
                marginBottom: '12px',
                textAlign: 'center',
                fontWeight: 500
              }}>
                💬 试试这样问我：
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', justifyContent: 'center' }}>
                {[
                  { text: '推荐一个周末短途旅行目的地', emoji: '🏃', color: '#10b981' },
                  { text: '北京三日游怎么安排？', emoji: '🏯', color: '#ef4444' },
                  { text: '去云南旅游需要注意什么？', emoji: '🌸', color: '#8b5cf6' },
                  { text: '给我一个三亚自由行攻略', emoji: '🏖️', color: '#0ea5e9' }
                ].map((item, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      console.log('[ChatArea] 设置输入值:', item.text);
                      setInputValue(item.text);
                    }}
                    style={{
                      padding: '10px 16px',
                      background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
                      border: '1px solid rgba(0, 0, 0, 0.08)',
                      borderRadius: '24px',
                      fontSize: '13px',
                      color: '#374151',
                      cursor: 'pointer',
                      transition: 'all 0.3s ease',
                      boxShadow: '0 2px 8px rgba(0, 0, 0, 0.04)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = 'translateY(-2px)';
                      e.currentTarget.style.boxShadow = '0 6px 20px rgba(0, 0, 0, 0.1)';
                      e.currentTarget.style.borderColor = item.color;
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = 'translateY(0)';
                      e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.04)';
                      e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.08)';
                    }}
                  >
                    <span>{item.emoji}</span>
                    <span>{item.text}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 模式选择器 - 现代风格 */}
        <div style={{
          marginBottom: '14px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
          borderRadius: '14px',
          border: '1px solid rgba(0, 0, 0, 0.06)',
          boxShadow: '0 2px 10px rgba(0, 0, 0, 0.04)'
        }}>
          <ChatModeSelector
            value={chatMode}
            onChange={setChatMode}
            disabled={isStreaming}
          />
          <div style={{
            fontSize: '12px',
            color: '#722ed1',
            background: 'rgba(114, 46, 209, 0.08)',
            padding: '4px 12px',
            borderRadius: '12px'
          }}>
            {chatMode === 'direct' && '⚡ 快速响应'}
            {chatMode === 'react' && '🧠 深度思考'}
            {chatMode === 'plan' && '📋 先规划后执行'}
          </div>
        </div>

        {/* 输入区域 - 现代卡片风格 */}
        <div style={{
          background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
          borderRadius: '20px',
          padding: '12px',
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.12)',
          border: '1px solid rgba(0, 0, 0, 0.08)'
        }}>
          <Space.Compact style={{ width: '100%' }}>
            <TextArea
              value={inputValue}
              onChange={(e) => {
                console.log('[ChatArea] 输入框变化:', e.target.value);
                setInputValue(e.target.value);
              }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  console.log('[ChatArea] 按下回车键，调用 handleSend');
                  handleSend();
                }
              }}
              placeholder={isStreaming ? "正在生成回答中..." : "输入你的旅游需求..."}
              disabled={isStreaming}
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{
                resize: 'none',
                border: 'none',
                boxShadow: 'none',
                outline: 'none'
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
                  boxShadow: '0 4px 15px rgba(239, 68, 68, 0.4)'
                }}
              >
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={() => {
                  console.log('[ChatArea] 发送按钮被点击, inputValue:', inputValue);
                  handleSend();
                }}
                disabled={!inputValue.trim()}
                style={{
                  borderRadius: '14px',
                  height: '42px',
                  padding: '0 24px',
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  border: 'none',
                  boxShadow: '0 4px 15px rgba(102, 126, 234, 0.4)'
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
