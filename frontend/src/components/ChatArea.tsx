'use client';

import React, { useEffect, useRef, useState } from 'react';
import { App, Badge, Button, Checkbox, Input, InputNumber, Popover, Select, Space, Tabs, Tag } from 'antd';
import {
  BulbOutlined,
  ClockCircleOutlined,
  FilterOutlined,
  SendOutlined,
  StopOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useAppContext } from '@/context/AppContext';
import { apiService, type StreamMetadata } from '@/services/api';
import type { PlanPreview, StreamStageEvent } from '@/types';
import { logger } from '@/utils/logger';
import MessageList from './MessageList';
import ChatModeSelector from './ChatModeSelector';
import CityExplorer from './CityExplorer';
import SystemStatusPanel from './SystemStatusPanel';

const { TextArea } = Input;
const ANSWER_CHARS_PER_TICK = 1;
const REASONING_CHARS_PER_TICK = 2;
const STREAM_FLUSH_INTERVAL_MS = 28;
const MAX_EVENT_LOGS = 14;
const MAX_STAGE_LOGS = 8;
const PRESET_CONSTRAINTS = ['亲子', '老人', '无车', '雨天', '少走路'] as const;
const QUICK_START_PROMPTS = [
  '帮我做一个上海周末 2 天轻松游，地铁可达，预算 1500 元以内',
  '请规划北京亲子 3 日游，包含室内备选和午休节奏',
  '做一个杭州 2 天游预算版，优先高性价比美食和免费景点',
];

interface RuntimeLog {
  id: string;
  label: string;
  detail?: string;
  time: string;
}

function takeChars(source: string, count: number): [string, string] {
  if (!source) return ['', ''];
  const chars = Array.from(source);
  return [chars.slice(0, count).join(''), chars.slice(count).join('')];
}

function nowLabel(): string {
  return new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function normalizeStepLabel(step: Record<string, unknown>, index: number): string {
  const title = typeof step.title === 'string' ? step.title : '';
  const description = typeof step.description === 'string' ? step.description : '';
  const tool = typeof step.tool === 'string' ? step.tool : '';
  return title || description || tool || `步骤 ${index + 1}`;
}

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
    setMessages,
  } = useAppContext();
  const { message } = App.useApp();

  const [activeView, setActiveView] = useState<'chat' | 'city' | 'status'>('chat');
  const [inputValue, setInputValue] = useState('');
  const [streamingMessage, setStreamingMessage] = useState('');
  const [streamingReasoning, setStreamingReasoning] = useState('');
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasoningExpanded, setReasoningExpanded] = useState<Record<string, boolean>>({});
  const [currentTool, setCurrentTool] = useState<string | null>(null);
  const [stageState, setStageState] = useState<StreamStageEvent | null>(null);
  const [stageHistory, setStageHistory] = useState<StreamStageEvent[]>([]);
  const [runtimeLogs, setRuntimeLogs] = useState<RuntimeLog[]>([]);
  const [planPreview, setPlanPreview] = useState<PlanPreview | null>(null);
  const [selectedConstraints, setSelectedConstraints] = useState<string[]>([]);
  const [budgetUpperLimit, setBudgetUpperLimit] = useState<number | null>(null);
  const [compareModeEnabled, setCompareModeEnabled] = useState(false);
  const [comparePlanCount, setComparePlanCount] = useState<2 | 3>(2);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const stopRef = useRef(false);
  const skipNextSessionResetRef = useRef(false);
  const metadataRef = useRef<StreamMetadata | null>(null);
  const fullResponseRef = useRef('');
  const fullReasoningRef = useRef('');
  const reasoningTimestampRef = useRef('');
  const streamQueueRef = useRef({ answer: '', reasoning: '' });
  const flushTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRafRef = useRef<number | null>(null);
  const hasHandledShareRef = useRef(false);

  const pushRuntimeLog = (label: string, detail?: string) => {
    const item: RuntimeLog = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      label,
      detail,
      time: nowLabel(),
    };
    setRuntimeLogs((prev) => [...prev.slice(-MAX_EVENT_LOGS + 1), item]);
  };

  const scheduleScrollToBottom = () => {
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = window.requestAnimationFrame(() => {
      scrollRafRef.current = null;
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
    });
  };

  const stopFlushTimer = () => {
    if (flushTimerRef.current !== null) {
      clearInterval(flushTimerRef.current);
      flushTimerRef.current = null;
    }
  };

  const flushStreamingQueue = () => {
    let didUpdate = false;

    if (streamQueueRef.current.reasoning) {
      const [chunk, rest] = takeChars(streamQueueRef.current.reasoning, REASONING_CHARS_PER_TICK);
      streamQueueRef.current.reasoning = rest;
      if (chunk) {
        didUpdate = true;
        setStreamingReasoning((prev) => prev + chunk);
      }
    }

    if (streamQueueRef.current.answer) {
      const [chunk, rest] = takeChars(streamQueueRef.current.answer, ANSWER_CHARS_PER_TICK);
      streamQueueRef.current.answer = rest;
      if (chunk) {
        didUpdate = true;
        setStreamingMessage((prev) => prev + chunk);
      }
    }

    if (didUpdate) scheduleScrollToBottom();
    if (!streamQueueRef.current.answer && !streamQueueRef.current.reasoning) stopFlushTimer();
  };

  const startFlushTimer = () => {
    if (flushTimerRef.current !== null) return;
    flushTimerRef.current = setInterval(flushStreamingQueue, STREAM_FLUSH_INTERVAL_MS);
  };

  const enqueueAnswer = (content: string) => {
    if (!content) return;
    streamQueueRef.current.answer += content;
    startFlushTimer();
  };

  const enqueueReasoning = (content: string) => {
    if (!content) return;
    streamQueueRef.current.reasoning += content;
    startFlushTimer();
  };

  const drainStreamingQueueToRefs = () => {
    if (streamQueueRef.current.answer) {
      fullResponseRef.current += streamQueueRef.current.answer;
      streamQueueRef.current.answer = '';
    }
    if (streamQueueRef.current.reasoning) {
      fullReasoningRef.current += streamQueueRef.current.reasoning;
      streamQueueRef.current.reasoning = '';
    }
  };

  const clearStreamRuntimeRefs = () => {
    stopFlushTimer();
    streamQueueRef.current.answer = '';
    streamQueueRef.current.reasoning = '';
    fullResponseRef.current = '';
    fullReasoningRef.current = '';
    reasoningTimestampRef.current = '';
  };

  useEffect(() => {
    return () => {
      stopFlushTimer();
      if (scrollRafRef.current !== null) {
        window.cancelAnimationFrame(scrollRafRef.current);
        scrollRafRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (hasHandledShareRef.current) return;

    const params = new URLSearchParams(window.location.search);
    const shareId = params.get('share');
    if (!shareId) return;

    hasHandledShareRef.current = true;
    const loadSharedContent = async () => {
      try {
        const result = await apiService.getShareDetail(shareId);
        setCurrentSessionId(null);
        setMessages([
          {
            role: 'assistant',
            content: result.content,
            timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setActiveView('chat');
        message.success('已打开分享方案');
      } catch (error) {
        message.error(`加载分享失败: ${error instanceof Error ? error.message : '未知错误'}`);
      }
    };

    loadSharedContent();
  }, [message, setCurrentSessionId, setMessages]);

  const streamScrollMarker = `${Math.floor(streamingMessage.length / 8)}-${Math.floor(
    streamingReasoning.length / 12
  )}`;
  useEffect(() => {
    scheduleScrollToBottom();
  }, [messages.length, streamScrollMarker, isThinking, waitingForResponse, currentTool, runtimeLogs.length]);

  useEffect(() => {
    if (skipNextSessionResetRef.current) {
      skipNextSessionResetRef.current = false;
      return;
    }

    clearStreamRuntimeRefs();
    setStreamingMessage('');
    setStreamingReasoning('');
    setWaitingForResponse(false);
    setIsThinking(false);
    setError(null);
    setIsStreaming(false);
    setStopStreaming(false);
    setCurrentTool(null);
    setStageState(null);
    setStageHistory([]);
    setRuntimeLogs([]);
    setPlanPreview(null);
    metadataRef.current = null;
    stopRef.current = false;
  }, [currentSessionId, setIsStreaming, setStopStreaming]);

  const toggleReasoning = (messageId: string) => {
    setReasoningExpanded((prev) => ({ ...prev, [messageId]: !prev[messageId] }));
  };

  const selectedConstraintCount =
    selectedConstraints.length + (budgetUpperLimit && budgetUpperLimit > 0 ? 1 : 0) + (compareModeEnabled ? 1 : 0);

  const buildEnhancedPrompt = (rawInput: string) => {
    const constraints = [...selectedConstraints];
    if (budgetUpperLimit && budgetUpperLimit > 0) constraints.push(`预算上限 ${budgetUpperLimit} 元`);
    const constraintLine = constraints.length > 0 ? `约束条件：${constraints.join('、')}` : '';
    const compareLine = compareModeEnabled
      ? `请同时生成 ${comparePlanCount} 套方案用于对比（至少包含省钱版、均衡版、舒适版中的任意组合）。`
      : '';

    const formatLine =
      '请按“每日行程卡”输出：每一天包含上午/下午/晚上安排、当日预算、小贴士，并在每一天给出景点点位列表。最后附上可执行清单与T-7/T-3/T-1提醒。';

    return [rawInput, constraintLine, compareLine, formatLine].filter(Boolean).join('\n\n');
  };

  const handleSend = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed) {
      message.warning('请输入内容');
      return;
    }

    try {
      const enrichedPrompt = buildEnhancedPrompt(trimmed);
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

      clearStreamRuntimeRefs();
      setInputValue('');
      setIsStreaming(true);
      setStopStreaming(false);
      setWaitingForResponse(true);
      setIsThinking(true);
      setError(null);
      setCurrentTool(null);
      setStreamingMessage('');
      setStreamingReasoning('');
      setStageState(null);
      setStageHistory([]);
      setRuntimeLogs([]);
      setPlanPreview(null);
      metadataRef.current = null;
      stopRef.current = false;
      pushRuntimeLog('开始执行', `模式: ${chatMode.toUpperCase()}`);

      if (isFirstMessage && sessionId) {
        try {
          const sessionName = trimmed.slice(0, 15) + (trimmed.length > 15 ? '...' : '');
          await apiService.updateSessionName(sessionId, sessionName);
        } catch (err) {
          logger.error('设置会话名称失败:', err);
        }
      }

      await apiService.fetchStreamChat(
        { message: enrichedPrompt, session_id: sessionId, mode: chatMode },
        {
          onSessionId: (sid) => {
            if (!currentSessionId) {
              skipNextSessionResetRef.current = true;
              setCurrentSessionId(sid);
            }
          },
          onStage: (stage) => {
            setStageState(stage);
            setStageHistory((prev) => [...prev, stage].slice(-MAX_STAGE_LOGS));
            pushRuntimeLog('阶段', stage.label || stage.stage || '阶段更新');
          },
          onPlanPreview: (preview) => {
            setPlanPreview(preview);
            pushRuntimeLog('计划预览', preview.intent || '已生成');
          },
          onChunk: (content) => {
            fullResponseRef.current += content;
            enqueueAnswer(content);
          },
          onReasoning: (content) => {
            fullReasoningRef.current += content;
            enqueueReasoning(content);
          },
          onReasoningStart: () => setIsThinking(true),
          onReasoningTimestamp: (timestamp) => {
            reasoningTimestampRef.current = timestamp;
          },
          onReasoningEnd: () => setIsThinking(false),
          onAnswerStart: () => setIsThinking(false),
          onToolStart: (toolName) => {
            setCurrentTool(toolName);
            pushRuntimeLog('工具启动', toolName);
          },
          onToolEnd: (toolName) => {
            setCurrentTool(null);
            pushRuntimeLog('工具完成', toolName);
          },
          onMetadata: (data) => {
            metadataRef.current = data;
            pushRuntimeLog('执行完成', `工具 ${data.toolsUsed.length} 个`);
          },
          onError: (errorMsg) => {
            message.destroy();
            message.error(`错误: ${errorMsg}`);
            clearStreamRuntimeRefs();
            setWaitingForResponse(false);
            setIsThinking(false);
            setCurrentTool(null);
            setError(errorMsg);
            setStageState(null);
            pushRuntimeLog('执行失败', errorMsg);
            fullResponseRef.current = `抱歉，发生错误：${errorMsg}`;
            setStreamingMessage(fullResponseRef.current);
          },
          onComplete: () => {
            message.destroy();
            drainStreamingQueueToRefs();

            const finalReasoning = reasoningTimestampRef.current
              ? `[Timestamp: ${reasoningTimestampRef.current}]\n\n${fullReasoningRef.current}`
              : fullReasoningRef.current;
            const finalContent = fullResponseRef.current;
            const finalMetadata = metadataRef.current;

            clearStreamRuntimeRefs();
            addMessage({
              role: 'assistant',
              content: finalContent,
              reasoning: finalReasoning,
              diagnostics: finalMetadata
                ? {
                    toolsUsed: finalMetadata.toolsUsed,
                    verificationPassed: finalMetadata.verificationPassed,
                    staleResultCount: finalMetadata.staleResultCount,
                    fallbackSteps: finalMetadata.fallbackSteps,
                    planId: finalMetadata.planId,
                    executionStats: finalMetadata.executionStats,
                  }
                : undefined,
              timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
            });

            setStreamingMessage('');
            setStreamingReasoning('');
            metadataRef.current = null;
            setWaitingForResponse(false);
            setIsStreaming(false);
            setIsThinking(false);
            setCurrentTool(null);
            setStageState(null);
            stopRef.current = false;
            pushRuntimeLog('结束', '已生成最终回答');
          },
          onStop: () => stopRef.current,
        }
      );

      refreshSessions();
    } catch (err: unknown) {
      message.destroy();
      const errorMsg = err instanceof Error ? err.message : '未知错误';
      message.error(`发送失败: ${errorMsg}`);
      setWaitingForResponse(false);
      setIsThinking(false);
      setCurrentTool(null);
      setError(errorMsg);
      clearStreamRuntimeRefs();
    }
  };

  const handleStop = () => {
    stopRef.current = true;
    setStopStreaming(true);
    drainStreamingQueueToRefs();

    const stoppedContent = fullResponseRef.current;
    const stoppedReasoning = fullReasoningRef.current;
    clearStreamRuntimeRefs();

    setWaitingForResponse(false);
    setIsThinking(false);
    setIsStreaming(false);
    setCurrentTool(null);
    setStageState(null);
    metadataRef.current = null;
    pushRuntimeLog('已停止', '用户中断本次生成');

    if (stoppedContent || stoppedReasoning) {
      addMessage({
        role: 'assistant',
        content: `${stoppedContent || '已停止生成'}\n\n⚠️ 已停止生成`,
        reasoning: stoppedReasoning,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      });
    }

    setStreamingMessage('');
    setStreamingReasoning('');
  };

  const handleUsePromptFromExplorer = (prompt: string) => {
    setInputValue(prompt);
    setChatMode('plan');
    setActiveView('chat');
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
      <div style={{ marginBottom: 10 }}>
        <Tabs
          activeKey={activeView}
          onChange={(value) => setActiveView(value as 'chat' | 'city' | 'status')}
          items={[
            { key: 'chat', label: '对话体验' },
            { key: 'city', label: '城市探索' },
            { key: 'status', label: '系统状态' },
          ]}
        />
      </div>

      <div style={{ flex: 1, overflow: 'auto', marginBottom: '16px' }}>
        {activeView === 'chat' && (
          <>
            <ExecutionInsights
              isStreaming={isStreaming}
              isThinking={isThinking}
              currentTool={currentTool}
              stageState={stageState}
              stageHistory={stageHistory}
              runtimeLogs={runtimeLogs}
              planPreview={planPreview}
              metadata={metadataRef.current}
            />

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

            {messages.length === 0 && !waitingForResponse && !isStreaming && (
              <div
                style={{
                  margin: '0 16px 16px',
                  padding: '14px',
                  borderRadius: '14px',
                  border: '1px dashed rgba(30, 64, 175, 0.35)',
                  background: 'linear-gradient(135deg, #ffffff 0%, #eff6ff 100%)',
                }}
              >
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e3a8a', marginBottom: '8px' }}>
                  3 秒上手示例
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {QUICK_START_PROMPTS.map((prompt) => (
                    <Button key={prompt} size="small" onClick={() => setInputValue(prompt)}>
                      {prompt}
                    </Button>
                  ))}
                </div>
              </div>
            )}
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
          </>
        )}

        {activeView === 'city' && <CityExplorer onUsePrompt={handleUsePromptFromExplorer} />}
        {activeView === 'status' && <SystemStatusPanel />}
      </div>

      {activeView === 'chat' && (
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
              {chatMode === 'direct' && '快速回答'}
              {chatMode === 'react' && '推理与工具执行'}
              {chatMode === 'plan' && '先计划再执行'}
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
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px',
              }}
            >
              <Popover
                trigger="click"
                placement="topLeft"
                title={<span style={{ fontSize: '13px' }}>约束条件设置</span>}
                content={
                  <div style={{ width: 340, maxWidth: 'calc(100vw - 64px)' }}>
                    <div style={{ fontSize: '12px', color: '#334155', marginBottom: '8px' }}>出行限制</div>
                    <Checkbox.Group
                      options={PRESET_CONSTRAINTS.map((item) => ({ label: item, value: item }))}
                      value={selectedConstraints}
                      onChange={(values) => setSelectedConstraints(values as string[])}
                    />

                    <div style={{ fontSize: '12px', color: '#334155', margin: '12px 0 6px' }}>预算上限</div>
                    <InputNumber
                      min={100}
                      max={99999}
                      value={budgetUpperLimit ?? undefined}
                      onChange={(value) => setBudgetUpperLimit(typeof value === 'number' ? value : null)}
                      placeholder="预算上限(元)"
                      style={{ width: '100%' }}
                    />

                    <div
                      style={{ marginTop: '10px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}
                    >
                      <Checkbox
                        checked={compareModeEnabled}
                        onChange={(event) => setCompareModeEnabled(event.target.checked)}
                      >
                        比较模式
                      </Checkbox>
                      <Select
                        size="small"
                        style={{ width: 120 }}
                        value={comparePlanCount}
                        disabled={!compareModeEnabled}
                        options={[
                          { label: '2 套方案', value: 2 },
                          { label: '3 套方案', value: 3 },
                        ]}
                        onChange={(value) => setComparePlanCount(value as 2 | 3)}
                      />
                    </div>
                  </div>
                }
              >
                <Badge count={selectedConstraintCount} size="small">
                  <Button icon={<FilterOutlined />} size="small">
                    行程约束
                  </Button>
                </Badge>
              </Popover>

              {selectedConstraintCount > 0 && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    flexWrap: 'wrap',
                    justifyContent: 'flex-end',
                  }}
                >
                  {selectedConstraints.slice(0, 3).map((item) => (
                    <Tag key={item} color="blue">
                      {item}
                    </Tag>
                  ))}
                  {budgetUpperLimit && budgetUpperLimit > 0 && <Tag color="gold">≤ {budgetUpperLimit}元</Tag>}
                  {compareModeEnabled && <Tag color="purple">比较 {comparePlanCount} 套</Tag>}
                </div>
              )}
            </div>

            <Space.Compact style={{ width: '100%' }}>
              <TextArea
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={isStreaming ? '正在生成回答...' : '输入你的旅行需求，例如：上海三日游如何安排'}
                disabled={isStreaming}
                autoSize={{ minRows: 1, maxRows: 4 }}
                style={{ resize: 'none', border: 'none', boxShadow: 'none', outline: 'none' }}
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
      )}
    </div>
  );
};

const ExecutionInsights: React.FC<{
  isStreaming: boolean;
  isThinking: boolean;
  currentTool: string | null;
  stageState: StreamStageEvent | null;
  stageHistory: StreamStageEvent[];
  runtimeLogs: RuntimeLog[];
  planPreview: PlanPreview | null;
  metadata: StreamMetadata | null;
}> = ({ isStreaming, isThinking, currentTool, stageState, stageHistory, runtimeLogs, planPreview, metadata }) => {
  const shouldShow =
    isStreaming ||
    isThinking ||
    Boolean(currentTool) ||
    Boolean(planPreview) ||
    stageHistory.length > 0 ||
    runtimeLogs.length > 0 ||
    Boolean(metadata);

  if (!shouldShow) return null;

  const progressValue = stageState?.progress;
  const progressText =
    typeof progressValue === 'number' && Number.isFinite(progressValue)
      ? `${Math.round(Math.max(0, Math.min(100, progressValue * 100)))}%`
      : '进行中';

  return (
    <div
      style={{
        margin: '0 16px 16px',
        padding: '12px',
        background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
        borderRadius: '14px',
        border: '1px solid rgba(37, 99, 235, 0.14)',
        boxShadow: '0 4px 12px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
        <Tag color={isStreaming ? 'blue' : 'default'}>{isStreaming ? '运行中' : '已结束'}</Tag>
        {isThinking && <Tag color="purple">思考中</Tag>}
        {currentTool && <Tag color="gold">工具: {currentTool}</Tag>}
        {stageState?.label && <Tag color="cyan">阶段: {stageState.label}</Tag>}
      </div>

      {stageState && (
        <div
          style={{
            marginBottom: '10px',
            padding: '8px 10px',
            borderRadius: '10px',
            background: '#eff6ff',
            fontSize: '12px',
            color: '#1d4ed8',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{stageState.label || stageState.stage || '阶段更新'}</span>
          <span>{progressText}</span>
        </div>
      )}

      {planPreview && (
        <div
          style={{
            marginBottom: '10px',
            padding: '10px',
            borderRadius: '10px',
            background: '#f5f3ff',
            border: '1px solid rgba(124, 58, 237, 0.2)',
          }}
        >
          <div style={{ fontSize: '12px', color: '#6d28d9', marginBottom: '6px', fontWeight: 600 }}>
            Plan 预览 {planPreview.planId ? `#${planPreview.planId}` : ''}
          </div>
          <div style={{ fontSize: '12px', color: '#5b21b6', marginBottom: '6px' }}>
            意图: {planPreview.intent || '未知'} | 校验: {planPreview.validationStatus || '未知'}
          </div>
          {planPreview.explanation && (
            <div style={{ fontSize: '12px', color: '#4c1d95', marginBottom: '6px' }}>{planPreview.explanation}</div>
          )}
          {planPreview.steps.length > 0 && (
            <ol style={{ margin: '0 0 0 18px', padding: 0, fontSize: '12px', color: '#4c1d95', lineHeight: 1.7 }}>
              {planPreview.steps.slice(0, 6).map((step, index) => (
                <li key={`${index}-${normalizeStepLabel(step, index)}`}>{normalizeStepLabel(step, index)}</li>
              ))}
            </ol>
          )}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
        <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '10px' }}>
          <div style={{ fontSize: '12px', color: '#334155', marginBottom: '6px', fontWeight: 600 }}>
            <ClockCircleOutlined style={{ marginRight: 6 }} />
            执行时间线
          </div>
          <div style={{ maxHeight: '140px', overflow: 'auto', display: 'grid', gap: '6px' }}>
            {runtimeLogs.length === 0 && <div style={{ fontSize: '12px', color: '#94a3b8' }}>等待事件...</div>}
            {runtimeLogs
              .slice()
              .reverse()
              .map((item) => (
                <div key={item.id} style={{ fontSize: '12px', color: '#334155' }}>
                  [{item.time}] {item.label}
                  {item.detail ? ` · ${item.detail}` : ''}
                </div>
              ))}
          </div>
        </div>

        <div style={{ background: '#f8fafc', borderRadius: '10px', padding: '10px' }}>
          <div style={{ fontSize: '12px', color: '#334155', marginBottom: '6px', fontWeight: 600 }}>
            <ToolOutlined style={{ marginRight: 6 }} />
            运行诊断
          </div>
          <div style={{ fontSize: '12px', color: '#475569', lineHeight: 1.8 }}>
            <div>阶段更新: {stageHistory.length} 次</div>
            <div>工具调用: {metadata?.toolsUsed?.length || 0} 个</div>
            <div>
              验证状态:{' '}
              {metadata?.verificationPassed === null || metadata?.verificationPassed === undefined
                ? '未知'
                : metadata.verificationPassed
                  ? '通过'
                  : '未通过'}
            </div>
            <div>过期结果: {metadata?.staleResultCount || 0}</div>
            <div>回退次数: {metadata?.fallbackSteps || 0}</div>
            {metadata?.planId && <div>计划ID: {metadata.planId}</div>}
          </div>
        </div>
      </div>

      <div style={{ marginTop: '8px', fontSize: '11px', color: '#64748b' }}>
        <BulbOutlined style={{ marginRight: 6 }} />
        以上内容来自后端 SSE 事件: stage、plan_preview、tool_start/tool_end、metadata
      </div>
    </div>
  );
};

export default ChatArea;
