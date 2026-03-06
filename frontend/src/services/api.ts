import axios, { AxiosError } from 'axios';
import {
  SessionInfo,
  ChatRequest,
  ChatResponse,
  AvailableModelsResponse,
  SetModelRequest,
  SetModelResponse,
  GetSessionModelResponse
} from '@/types';
import { logger } from '@/utils/logger';

// 调试：打印环境变量
const API_BASE = (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE)
  || process.env.NEXT_PUBLIC_API_BASE
  || 'http://localhost:38000';

console.log('[API] API_BASE:', API_BASE);

const API_PREFIX = `${API_BASE}/api`;

// SSE 连接状态
export enum SSEConnectionStatus {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  STREAMING = 'streaming',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
  DISCONNECTED = 'disconnected'
}

// SSE 事件类型
export enum SSEEventType {
  SESSION_ID = 'session_id',
  REASONING_START = 'reasoning_start',
  REASONING_CHUNK = 'reasoning_chunk',
  REASONING_END = 'reasoning_end',
  ANSWER_START = 'answer_start',
  CHUNK = 'chunk',
  ERROR = 'error',
  DONE = 'done',
  HEARTBEAT = 'heartbeat',
  METADATA = 'metadata',
  REASONING_TIMESTAMP = 'reasoning_timestamp'
}

class APIService {
  // 重连配置
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private baseReconnectDelay = 1000;
  private currentRequestKey: string | null = null;
  private pendingRequests = new Map<string, AbortController>();
  private connectionStatus: SSEConnectionStatus = SSEConnectionStatus.IDLE;

  /**
   * 获取当前连接状态
   */
  getConnectionStatus(): SSEConnectionStatus {
    return this.connectionStatus;
  }

  /**
   * 生成请求唯一键，用于去重
   */
  private getRequestKey(request: ChatRequest): string {
    return `${request.session_id || 'new'}:${request.message.slice(0, 50)}`;
  }

  /**
   * 取消指定请求
   */
  cancelRequest(key: string): boolean {
    const controller = this.pendingRequests.get(key);
    if (controller) {
      controller.abort();
      this.pendingRequests.delete(key);
      return true;
    }
    return false;
  }

  /**
   * 取消所有待处理请求
   */
  cancelAllRequests(): void {
    for (const controller of this.pendingRequests.values()) {
      controller.abort();
    }
    this.pendingRequests.clear();
  }

  /**
   * 计算重连延迟（指数退避）
   */
  private getReconnectDelay(attempt: number): number {
    return this.baseReconnectDelay * Math.pow(2, attempt - 1);
  }

  /**
   * 重置重连计数
   */
  private resetReconnectAttempts(): void {
    this.reconnectAttempts = 0;
  }

  async checkHealth(): Promise<{ status: string; agent: string; version: string }> {
    const response = await axios.get(`${API_PREFIX}/health`);
    return response.data;
  }

  async createSession(): Promise<{ session_id: string }> {
    const url = `${API_PREFIX}/session/new`;
    console.log('[API] createSession 发送请求到:', url);
    try {
      const response = await axios.post(url);
      console.log('[API] createSession 响应:', response.data);
      return response.data;
    } catch (error) {
      console.error('[API] createSession 错误:', error);
      if (error instanceof AxiosError) {
        console.error('[API] axios 错误状态:', error.response?.status);
        console.error('[API] axios 错误数据:', error.response?.data);
        console.error('[API] axios 错误消息:', error.message);
      }
      throw error;
    }
  }

  async getSessions(): Promise<{ sessions: SessionInfo[] }> {
    const url = `${API_PREFIX}/sessions`;
    console.log('[API] getSessions URL:', url);
    try {
      const response = await axios.get(url);
      console.log('[API] getSessions 响应:', response.data);
      return response.data;
    } catch (error) {
      console.error('[API] getSessions 错误:', error);
      throw error;
    }
  }

  async deleteSession(sessionId: string): Promise<{ success: boolean }> {
    const response = await axios.delete(`${API_PREFIX}/session/${sessionId}`);
    return response.data;
  }

  async clearChat(sessionId: string): Promise<ChatResponse> {
    const response = await axios.post(`${API_PREFIX}/clear`, null, {
      params: { session_id: sessionId }
    });
    return response.data;
  }

  async updateSessionName(sessionId: string, name: string): Promise<{ success: boolean; message: string }> {
    const response = await axios.put(`${API_PREFIX}/session/${sessionId}/name`, { name });
    return response.data;
  }

  async getAvailableModels(): Promise<AvailableModelsResponse> {
    const url = `${API_PREFIX}/models`;
    console.log('[API] getAvailableModels URL:', url);
    try {
      const response = await axios.get(url);
      console.log('[API] getAvailableModels 响应:', response.data);
      return response.data;
    } catch (error) {
      console.error('[API] getAvailableModels 错误:', error);
      throw error;
    }
  }

  async setSessionModel(sessionId: string, modelId: string): Promise<SetModelResponse> {
    const response = await axios.put(
      `${API_PREFIX}/session/${sessionId}/model`,
      { model_id: modelId } as SetModelRequest
    );
    return response.data;
  }

  async getSessionModel(sessionId: string): Promise<GetSessionModelResponse> {
    const response = await axios.get(`${API_PREFIX}/session/${sessionId}/model`);
    return response.data;
  }

  async fetchStreamChat(request: ChatRequest, callbacks: {
    onChunk: (content: string) => void;
    onReasoning: (content: string) => void;
    onReasoningStart: () => void;
    onReasoningEnd: () => void;
    onReasoningTimestamp: (timestamp: string) => void;
    onAnswerStart: () => void;
    onToolStart?: (toolName: string) => void;
    onToolEnd?: (toolName: string, result: string) => void;
    onMetadata: (data: { totalSteps: number; toolsUsed: string[]; hasReasoning: boolean; reasoningLength: number; answerLength: number }) => void;
    onError: (error: string) => void;
    onComplete: () => void;
    onStop?: () => boolean;
    onConnectionChange?: (status: SSEConnectionStatus) => void;
  }): Promise<void> {
    const requestKey = this.getRequestKey(request);

    // 检查是否有相同请求正在进行
    if (this.pendingRequests.has(requestKey)) {
      callbacks.onError('请求已在处理中');
      return;
    }

    // 添加请求到挂起队列
    const controller = new AbortController();
    this.pendingRequests.set(requestKey, controller);

    await this._executeStreamRequest(request, callbacks, controller, requestKey);
  }

  /**
   * 执行流式请求（内部方法，支持重连）
   */
  private async _executeStreamRequest(
    request: ChatRequest,
    callbacks: {
      onChunk: (content: string) => void;
      onReasoning: (content: string) => void;
      onReasoningStart: () => void;
      onReasoningEnd: () => void;
      onReasoningTimestamp: (timestamp: string) => void;
      onAnswerStart: () => void;
      onToolStart?: (toolName: string) => void;
      onToolEnd?: (toolName: string, result: string) => void;
      onMetadata: (data: { totalSteps: number; toolsUsed: string[]; hasReasoning: boolean; reasoningLength: number; answerLength: number }) => void;
      onError: (error: string) => void;
      onComplete: () => void;
      onStop?: () => boolean;
      onConnectionChange?: (status: SSEConnectionStatus) => void;
    },
    controller: AbortController,
    requestKey: string,
    attempt: number = 1
  ): Promise<void> {
    // 设置连接状态
    if (attempt > 1) {
      this.connectionStatus = SSEConnectionStatus.RECONNECTING;
      callbacks.onConnectionChange?.(this.connectionStatus);
      logger.info(`第 ${attempt - 1} 次重连尝试...`);
    } else {
      this.connectionStatus = SSEConnectionStatus.CONNECTING;
      callbacks.onConnectionChange?.(this.connectionStatus);
    }

    // 设置超时控制器（180秒超时，需大于后端120秒超时）
    const timeoutId = setTimeout(() => {
      controller.abort();
      logger.warn('请求超时，已自动取消');
    }, 180000);

    try {
      const url = `${API_PREFIX}/chat/stream`;
      console.log('[API] fetchStreamChat 发送请求到:', url);

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      this.resetReconnectAttempts();
      this.connectionStatus = SSEConnectionStatus.STREAMING;
      callbacks.onConnectionChange?.(this.connectionStatus);

      console.log('[API] fetchStreamChat 响应状态:', response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('[API] fetchStreamChat HTTP错误:', response.status, errorText);
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(`HTTP error! status: ${response.status} - ${errorText}`);
        this.pendingRequests.delete(requestKey);
        return;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        console.error('[API] fetchStreamChat 无法获取reader');
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError('无法读取响应流');
        this.pendingRequests.delete(requestKey);
        return;
      }

      console.log('[API] fetchStreamChat 开始读取流...');

      while (true) {
        if (controller.signal.aborted) {
          break;
        }
        if (callbacks.onStop && callbacks.onStop()) {
          reader.cancel();
          break;
        }

        const { done, value } = await reader.read();

        if (done) {
          this.connectionStatus = SSEConnectionStatus.IDLE;
          callbacks.onComplete();
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();

            if (dataStr === '[DONE]') {
              this.connectionStatus = SSEConnectionStatus.IDLE;
              callbacks.onComplete();
              this.pendingRequests.delete(requestKey);
              return;
            }

            try {
              const data = JSON.parse(dataStr);
              const dataType = data.type;

              if (dataType === 'heartbeat') {
                continue;
              } else if (dataType === 'metadata' || dataType === 'reasoning_metadata') {
                callbacks.onMetadata({
                  totalSteps: data.total_steps || 0,
                  toolsUsed: data.tools_used || [],
                  hasReasoning: data.has_reasoning || false,
                  reasoningLength: data.reasoning_length || 0,
                  answerLength: data.answer_length || 0
                });
                if (dataType === 'reasoning_metadata' && data.has_reasoning) {
                  callbacks.onReasoningStart();
                }
              } else if (dataType === 'reasoning_start') {
                callbacks.onReasoningStart();
              } else if (dataType === 'reasoning_timestamp' && data.timestamp) {
                callbacks.onReasoningTimestamp(data.timestamp);
              } else if (dataType === 'reasoning_chunk' && data.content) {
                callbacks.onReasoning(data.content);
              } else if (dataType === 'reasoning_end') {
                callbacks.onReasoningEnd();
              } else if (dataType === 'answer_start') {
                callbacks.onAnswerStart();
              } else if (dataType === 'tool_start' && data.tool) {
                callbacks.onToolStart?.(data.tool);
              } else if (dataType === 'tool_end' && data.tool) {
                callbacks.onToolEnd?.(data.tool, data.result || '');
              } else if (dataType === 'chunk' && data.content) {
                callbacks.onChunk(data.content);
              } else if (dataType === 'error' && data.content) {
                this.connectionStatus = SSEConnectionStatus.ERROR;
                callbacks.onError(data.content);
                this.pendingRequests.delete(requestKey);
                return;
              } else if (dataType === 'done') {
                this.connectionStatus = SSEConnectionStatus.IDLE;
                callbacks.onComplete();
                this.pendingRequests.delete(requestKey);
                return;
              } else if (data.chunk) {
                callbacks.onChunk(data.chunk);
              } else if (data.error) {
                this.connectionStatus = SSEConnectionStatus.ERROR;
                callbacks.onError(data.error);
                this.pendingRequests.delete(requestKey);
                return;
              }
            } catch (e) {
              // 忽略JSON解析错误
            }
          }
        }
      }

      this.pendingRequests.delete(requestKey);

    } catch (error: unknown) {
      clearTimeout(timeoutId);
      this.pendingRequests.delete(requestKey);

      if (controller.signal.aborted) {
        this.connectionStatus = SSEConnectionStatus.DISCONNECTED;
        return;
      }

      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error('[API] fetchStreamChat 网络错误:', errorMessage);

      if (attempt < this.maxReconnectAttempts) {
        this.connectionStatus = SSEConnectionStatus.RECONNECTING;
        callbacks.onConnectionChange?.(this.connectionStatus);

        const delay = this.getReconnectDelay(attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
        return this._executeStreamRequest(request, callbacks, controller, requestKey, attempt + 1);
      }

      this.connectionStatus = SSEConnectionStatus.ERROR;
      callbacks.onError('网络错误: ' + errorMessage);
    }
  }
}

export const apiService = new APIService();
