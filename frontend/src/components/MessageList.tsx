'use client';

import React, { useState } from 'react';
import { Card, App } from 'antd';
import { Message } from '@/types';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import {
  BulbOutlined,
  DownOutlined,
  UpOutlined,
  CopyOutlined,
  CheckOutlined,
  UserOutlined,
  RobotOutlined
} from '@ant-design/icons';

interface Props {
  messages: Message[];
  streamingMessage?: string;
  streamingReasoning?: string;
  isThinking?: boolean;
  reasoningExpanded?: Record<string, boolean>;
  onToggleReasoning?: (messageId: string) => void;
}

const cleanContent = (content: string): string => {
  if (!content) return '';
  return content
    .replace(/\n{2,}/g, '\n')
    .replace(/[ \t]+$/gm, '')
    .trim();
};

const markdownComponents: Components = {
  p: ({ children }) => <p style={{ margin: 0, padding: 0 }}>{children}</p>,
  li: ({ children }) => <li style={{ margin: 0, padding: 0, lineHeight: 1.6 }}>{children}</li>,
  h1: ({ children }) => <h1 style={{ margin: '4px 0 2px 0', fontSize: '1.5em', fontWeight: 600 }}>{children}</h1>,
  h2: ({ children }) => <h2 style={{ margin: '4px 0 2px 0', fontSize: '1.3em', fontWeight: 600 }}>{children}</h2>,
  h3: ({ children }) => <h3 style={{ margin: '4px 0 2px 0', fontSize: '1.1em', fontWeight: 600 }}>{children}</h3>,
  ol: ({ children }) => <ol style={{ margin: '2px 0', paddingLeft: '20px' }}>{children}</ol>,
  ul: ({ children }) => <ul style={{ margin: '2px 0', paddingLeft: '20px' }}>{children}</ul>,
};

interface ReasoningBlockProps {
  reasoning: string;
  messageId: string;
  isExpanded: boolean;
  onToggle: (messageId: string) => void;
  isStreaming?: boolean;
}

// 复制按钮组件
interface CopyButtonProps {
  content: string;
}

const CopyButton: React.FC<CopyButtonProps> = ({ content }) => {
  const [copied, setCopied] = useState(false);
  // 使用 antd App 上下文获取 message 实例
  const { message } = App.useApp();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      message.success('已复制到剪贴板');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      message.error('复制失败，请手动选择复制');
    }
  };

  return (
    <button
      onClick={handleCopy}
      title={copied ? '已复制' : '复制'}
      style={{
        background: 'transparent',
        border: 'none',
        cursor: 'pointer',
        padding: '4px 8px',
        borderRadius: '4px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: copied ? '#52c41a' : 'inherit',
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(0, 0, 0, 0.06)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent';
      }}
    >
      {copied ? <CheckOutlined style={{ fontSize: '14px' }} /> : <CopyOutlined style={{ fontSize: '14px' }} />}
    </button>
  );
};

const ReasoningBlock: React.FC<ReasoningBlockProps> = ({
  reasoning,
  messageId,
  isExpanded,
  onToggle,
  isStreaming = false
}) => {
  if (!reasoning) return null;

  // 定义渐变样式
  const reasoningGradient = 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)';
  const thinkingGradient = 'linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%)';

  // 提取时间戳
  const timestampMatch = reasoning.match(/\[Timestamp: ([^\]]+)\]/);
  const timestamp = timestampMatch ? timestampMatch[1] : null;

  // 去除时间戳行，只显示内容
  const cleanReasoning = reasoning.replace(/\[Timestamp: [^\]]+\]\n?\n?/g, '').trim();

  return (
    <div
      style={{
        marginBottom: '12px',
        background: isStreaming ? thinkingGradient : reasoningGradient,
        borderRadius: '12px',
        border: '1px solid rgba(114, 46, 209, 0.15)',
        overflow: 'hidden',
        boxShadow: '0 2px 8px rgba(114, 46, 209, 0.08)',
        transition: 'all 0.3s ease'
      }}
    >
      <div
        onClick={() => onToggle(messageId)}
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 14px',
          cursor: 'pointer',
          background: isStreaming
            ? 'linear-gradient(135deg, #e8f4fd 0%, #dbeafe 100%)'
            : 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
          borderBottom: isExpanded ? '1px solid rgba(114, 46, 209, 0.1)' : 'none',
          userSelect: 'none',
          transition: 'background 0.3s ease'
        }}
      >
        <div
          style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            background: isStreaming
              ? 'linear-gradient(135deg, #722ed1 0%, #9254de 100%)'
              : 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginRight: '10px',
            boxShadow: isStreaming ? '0 2px 8px rgba(114, 46, 209, 0.3)' : '0 2px 8px rgba(82, 196, 26, 0.3)'
          }}
        >
          <BulbOutlined
            style={{
              color: '#fff',
              fontSize: '12px',
              animation: isStreaming ? 'pulse 1.5s infinite' : 'none'
            }}
          />
        </div>
        <span style={{
          fontSize: '13px',
          color: '#1f2937',
          flex: 1,
          fontWeight: 500
        }}>
          {isStreaming ? '🤔 深度思考中...' : '💡 推理过程'}
        </span>
        {timestamp && !isStreaming && (
          <span style={{
            fontSize: '11px',
            color: '#9ca3af',
            marginRight: '8px',
            background: 'rgba(0,0,0,0.05)',
            padding: '2px 8px',
            borderRadius: '10px'
          }}>
            {timestamp}
          </span>
        )}
        {isExpanded ? (
          <UpOutlined style={{ color: '#722ed1', fontSize: '12px' }} />
        ) : (
          <DownOutlined style={{ color: '#722ed1', fontSize: '12px' }} />
        )}
      </div>

      {isExpanded && (
        <div
          style={{
            padding: '14px',
            background: '#ffffff',
            fontFamily: '"SF Mono", "Monaco", "Inconsolata", monospace',
            fontSize: '12px',
            lineHeight: '1.8',
            whiteSpace: 'pre-wrap',
            maxHeight: '350px',
            overflow: 'auto',
            color: '#4b5563',
            borderTop: '1px dashed rgba(114, 46, 209, 0.1)'
          }}
        >
          <ReactMarkdown components={markdownComponents}>
            {cleanContent(cleanReasoning)}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
};

const MessageItem: React.FC<{
  msg: Message;
  reasoningExpanded: Record<string, boolean>;
  onToggleReasoning: (messageId: string) => void;
}> = ({ msg, reasoningExpanded, onToggleReasoning }) => {
  const isUser = msg.role === 'user';
  const messageId = `msg_${msg.timestamp}_${msg.content.slice(0, 10)}`;
  const isExpanded = reasoningExpanded[messageId] ?? false;

  // 用户头像颜色 - 现代清新渐变
  const userAvatarColors = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  const aiAvatarColors = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';
  // 新增：现代清新风格配色
  const userBubbleGradient = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  const aiBubbleBg = '#ffffff';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' as const : 'row' as const,
        justifyContent: 'flex-start',
        marginBottom: '20px',
        alignItems: 'flex-start',
        gap: '14px',
        maxWidth: '100%',
        padding: '0 16px',
        animation: 'fadeInUp 0.4s ease-out'
      }}
    >
      {/* 头像 - 带光环效果 */}
      <div
        className="chat-avatar"
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          background: isUser ? userAvatarColors : aiAvatarColors,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: isUser
            ? '0 4px 15px rgba(102, 126, 234, 0.4), 0 0 0 3px rgba(102, 126, 234, 0.15)'
            : '0 4px 15px rgba(17, 153, 142, 0.4), 0 0 0 3px rgba(17, 153, 142, 0.15)',
          transition: 'all 0.3s ease',
          position: 'relative' as const,
        }}
      >
        {isUser ? (
          <UserOutlined style={{ color: 'white', fontSize: '18px' }} />
        ) : (
          <RobotOutlined style={{ color: 'white', fontSize: '18px' }} />
        )}
      </div>

      <div style={{ flex: 1, maxWidth: 'calc(100% - 52px)' }}>
        {/* 用户名和时间 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            marginBottom: '6px',
            gap: '8px',
          }}
        >
          <span
            style={{
              fontSize: '13px',
              fontWeight: 500,
              color: isUser ? 'white' : '#262730',
            }}
          >
            {isUser ? '你' : '小帅助手'}
          </span>
          <span
            style={{
              fontSize: '11px',
              opacity: 0.6,
              color: isUser ? 'rgba(255,255,255,0.7)' : '#999',
            }}
          >
            {msg.timestamp}
          </span>
        </div>

        {/* 消息气泡卡片 - 现代清新风格 */}
        <Card
          className="chat-message-card"
          style={{
            background: isUser
              ? userBubbleGradient
              : aiBubbleBg,
            color: isUser ? 'white' : '#1f2937',
            borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
            border: isUser ? 'none' : '1px solid rgba(0, 0, 0, 0.06)',
            boxShadow: isUser
              ? '0 4px 20px rgba(102, 126, 234, 0.35), 0 2px 8px rgba(0, 0, 0, 0.08)'
              : '0 2px 12px rgba(0, 0, 0, 0.04)',
            transition: 'all 0.3s ease',
            transform: 'translateY(0)',
          }}
          styles={{ body: { padding: '16px 18px' } }}
        >
          {/* 思考过程（仅AI消息） */}
          {!isUser && msg.reasoning && (
            <ReasoningBlock
              reasoning={msg.reasoning}
              messageId={messageId}
              isExpanded={isExpanded}
              onToggle={onToggleReasoning}
            />
          )}

          {/* 消息内容 */}
          <div style={{ lineHeight: 1.7, fontSize: '14px' }}>
            <ReactMarkdown components={markdownComponents}>
              {cleanContent(msg.content)}
            </ReactMarkdown>
          </div>
        </Card>

        {/* 复制按钮（仅在消息内容非空时显示） */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
          <CopyButton content={msg.content} />
        </div>
      </div>
    </div>
  );
};

const MessageList: React.FC<Props> = ({
  messages,
  streamingMessage,
  streamingReasoning,
  isThinking = false,
  reasoningExpanded = {},
  onToggleReasoning
}) => {
  // 现代化配色定义
  const reasoningGradient = 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)';
  const thinkingGradient = 'linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%)';

  // 流式消息组件 - 全新设计
  const StreamingMessageItem: React.FC<{ content: string; reasoning?: string; isThinking?: boolean }> = ({ content, reasoning, isThinking: thinking }) => {
    const hasContent = content && content.length > 0;

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'row',
          justifyContent: 'flex-start',
          marginBottom: '16px',
          alignItems: 'flex-start',
          gap: '12px',
          maxWidth: '100%',
          padding: '0 16px',
          animation: 'fadeInUp 0.3s ease-out'
        }}
      >
        {/* AI头像 */}
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 2px 8px rgba(102, 126, 234, 0.3)'
          }}
        >
          <RobotOutlined style={{ color: 'white', fontSize: '16px' }} />
        </div>

        <div style={{ flex: 1, maxWidth: 'calc(100% - 48px)' }}>
          {/* 用户名和时间 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px', gap: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, color: '#1f2937' }}>
              小帅助手
            </span>
            {thinking && (
              <span style={{
                fontSize: '11px',
                color: '#8b5cf6',
                background: 'rgba(139, 92, 246, 0.1)',
                padding: '2px 8px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}>
                <span style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: '#8b5cf6',
                  animation: 'pulse 1.5s infinite'
                }} />
                思考中
              </span>
            )}
          </div>

          {/* 简洁的思考指示器 - 仅在思考且无内容时显示 */}
          {thinking && !hasContent && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '12px 16px',
              background: 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
              borderRadius: '12px',
              border: '1px solid rgba(139, 92, 246, 0.2)',
              maxWidth: 'fit-content'
            }}>
              <div style={{
                display: 'flex',
                gap: '4px'
              }}>
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: '#8b5cf6',
                      animation: `bounce 1.4s infinite ease-in-out both`,
                      animationDelay: `${i * 0.16}s`
                    }}
                  />
                ))}
              </div>
              <span style={{ fontSize: '13px', color: '#6d28d9' }}>
                正在思考...
              </span>
            </div>
          )}

          {/* 内容区域 - 回答正在生成时 */}
          {hasContent && (
            <div
              style={{
                background: '#ffffff',
                borderRadius: '16px',
                padding: '14px 16px',
                border: '1px solid rgba(0, 0, 0, 0.06)',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
                minHeight: '40px'
              }}
            >
              <div style={{ lineHeight: 1.7, fontSize: '14px', color: '#1f2937' }}>
                <ReactMarkdown components={markdownComponents}>
                  {cleanContent(content)}
                </ReactMarkdown>
              </div>
              {/* 打字机光标效果 */}
              {thinking && (
                <span style={{
                  display: 'inline-block',
                  width: '2px',
                  height: '16px',
                  background: '#667eea',
                  marginLeft: '2px',
                  animation: 'blink 0.8s infinite'
                }} />
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="chat-message-container" style={{ maxWidth: '900px', margin: '0 auto', width: '100%' }}>
      {messages.map((msg, index) => (
        <MessageItem
          key={index}
          msg={msg}
          reasoningExpanded={reasoningExpanded}
          onToggleReasoning={onToggleReasoning || (() => {})}
        />
      ))}

      {/* 流式消息：当 isThinking 或有 streamingMessage 时显示 */}
      {(isThinking || streamingMessage) && (
        <StreamingMessageItem
          content={streamingMessage || ''}
          reasoning={streamingReasoning}
          isThinking={isThinking}
        />
      )}
    </div>
  );
};

export default MessageList;
