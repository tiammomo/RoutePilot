'use client';

import React, { useState } from 'react';
import { Card, message } from 'antd';
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

  // 提取时间戳
  const timestampMatch = reasoning.match(/\[Timestamp: ([^\]]+)\]/);
  const timestamp = timestampMatch ? timestampMatch[1] : null;

  // 去除时间戳行，只显示内容
  const cleanReasoning = reasoning.replace(/\[Timestamp: [^\]]+\]\n?\n?/g, '').trim();

  return (
    <div
      style={{
        marginBottom: '8px',
        background: '#fafafa',
        borderRadius: '8px',
        border: '1px solid #e8e8e8',
        overflow: 'hidden'
      }}
    >
      <div
        onClick={() => onToggle(messageId)}
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '8px 12px',
          cursor: 'pointer',
          background: '#f5f5f5',
          borderBottom: isExpanded ? '1px solid #e8e8e8' : 'none',
          userSelect: 'none'
        }}
      >
        <BulbOutlined
          style={{
            color: isStreaming ? '#722ed1' : '#52c41a',
            marginRight: '8px',
            fontSize: '14px'
          }}
        />
        <span style={{ fontSize: '13px', color: '#666', flex: 1 }}>
          {isStreaming ? 'Thinking...' : 'Reasoning Process'}
        </span>
        {timestamp && !isStreaming && (
          <span style={{ fontSize: '11px', color: '#999', marginRight: '8px' }}>
            {timestamp}
          </span>
        )}
        {isExpanded ? (
          <UpOutlined style={{ color: '#999', fontSize: '12px' }} />
        ) : (
          <DownOutlined style={{ color: '#999', fontSize: '12px' }} />
        )}
      </div>

      {isExpanded && (
        <div
          style={{
            padding: '12px',
            background: '#fff',
            fontFamily: 'monospace',
            fontSize: '12px',
            lineHeight: '1.7',
            whiteSpace: 'pre-wrap',
            maxHeight: '300px',
            overflow: 'auto',
            color: '#666'
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

  // 用户头像颜色
  const userAvatarColors = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  const aiAvatarColors = 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' as const : 'row' as const,
        justifyContent: 'flex-start',
        marginBottom: '16px',
        alignItems: 'flex-start',
        gap: '12px',
        maxWidth: '100%',
        padding: '0 16px',
      }}
    >
      {/* 头像 */}
      <div
        className="chat-avatar"
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          background: isUser ? userAvatarColors : aiAvatarColors,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
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

        {/* 消息气泡卡片 */}
        <Card
          className="chat-message-card"
          style={{
            background: isUser
              ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
              : '#fff',
            color: isUser ? 'white' : '#262730',
            borderRadius: '12px',
            border: isUser ? 'none' : '1px solid #e8e8e8',
            boxShadow: isUser ? '0 2px 8px rgba(102, 126, 234, 0.3)' : 'none',
          }}
          styles={{ body: { padding: '14px 16px' } }}
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
  // 流式消息组件
  const StreamingMessageItem: React.FC<{ content: string; reasoning?: string; isThinking?: boolean }> = ({ content, reasoning, isThinking: thinking }) => {
    // 显示思考内容的条件：有 reasoning 或正在思考
    const showReasoning = reasoning || thinking;

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'row' as const,
          justifyContent: 'flex-start',
          marginBottom: '16px',
          alignItems: 'flex-start',
          gap: '12px',
          maxWidth: '100%',
          padding: '0 16px',
        }}
      >
        {/* AI头像 */}
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          }}
        >
          <RobotOutlined style={{ color: 'white', fontSize: '18px' }} />
        </div>

        <div style={{ flex: 1, maxWidth: 'calc(100% - 52px)' }}>
          {/* 用户名 */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '6px', gap: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, color: '#262730' }}>
              小帅助手
            </span>
            <span style={{ fontSize: '11px', opacity: 0.6, color: '#999' }}>
              {thinking ? '深度思考中...' : '生成中...'}
            </span>
          </div>

          {/* 消息气泡 */}
          <Card
            className="chat-message-card"
            style={{
              background: '#fff',
              borderRadius: '12px',
              border: '1px solid #e8e8e8',
            }}
            styles={{ body: { padding: '14px 16px' } }}
          >
            {/* 流式思考过程 */}
            {showReasoning && (
              <div
                style={{
                  marginBottom: '8px',
                  background: '#fafafa',
                  borderRadius: '8px',
                  border: '1px solid #e8e8e8',
                  overflow: 'hidden'
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '8px 12px',
                    background: thinking ? '#f0f5ff' : '#f5f5f5',
                    userSelect: 'none'
                  }}
                >
                  <BulbOutlined style={{ color: thinking ? '#722ed1' : '#722ed1', marginRight: '8px', fontSize: '14px' }} />
                  <span style={{ fontSize: '13px', color: '#666', flex: 1 }}>
                    {thinking ? '深度思考中...' : 'Reasoning Process'}
                  </span>
                  {/* 动态加载点 */}
                  <span className="thinking-dots" style={{ color: '#999' }}>...</span>
                </div>
                <div
                  style={{
                    padding: '12px',
                    background: '#fff',
                    fontFamily: 'monospace',
                    fontSize: '12px',
                    lineHeight: '1.7',
                    whiteSpace: 'pre-wrap',
                    maxHeight: thinking ? '200px' : '300px',
                    overflow: 'auto',
                    color: '#666'
                  }}
                >
                  <ReactMarkdown components={markdownComponents}>
                    {cleanContent(reasoning || '')}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* 回答内容 */}
            {(content || !thinking) && (
              <div style={{ lineHeight: 1.7, fontSize: '14px' }}>
                <ReactMarkdown components={markdownComponents}>
                  {cleanContent(content)}
                </ReactMarkdown>
              </div>
            )}
          </Card>
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
