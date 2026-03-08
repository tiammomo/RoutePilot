import axios from 'axios';
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

const API_BASE = (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE)
  || process.env.NEXT_PUBLIC_API_BASE
  || 'http://localhost:38000';

const API_PREFIX = `${API_BASE}/api`;

export enum SSEConnectionStatus {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  STREAMING = 'streaming',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
  DISCONNECTED = 'disconnected'
}

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

export interface StreamMetadata {
  totalSteps: number;
  toolsUsed: string[];
  hasReasoning: boolean;
  reasoningLength: number;
  answerLength: number;
  verificationPassed: boolean | null;
  staleResultCount: number;
  fallbackSteps: number;
}

type StreamCallbacks = {
  onChunk: (content: string) => void;
  onReasoning: (content: string) => void;
  onReasoningStart: () => void;
  onReasoningEnd: () => void;
  onReasoningTimestamp: (timestamp: string) => void;
  onAnswerStart: () => void;
  onToolStart?: (toolName: string) => void;
  onToolEnd?: (toolName: string, result: string) => void;
  onMetadata: (data: StreamMetadata) => void;
  onError: (error: string) => void;
  onComplete: () => void;
  onStop?: () => boolean;
  onConnectionChange?: (status: SSEConnectionStatus) => void;
};

class APIService {
  private maxReconnectAttempts = 3;
  private baseReconnectDelay = 1000;
  private pendingRequests = new Map<string, AbortController>();
  private connectionStatus: SSEConnectionStatus = SSEConnectionStatus.IDLE;

  getConnectionStatus(): SSEConnectionStatus {
    return this.connectionStatus;
  }

  private getRequestKey(request: ChatRequest): string {
    return `${request.session_id || 'new'}:${request.message.slice(0, 50)}`;
  }

  cancelRequest(key: string): boolean {
    const controller = this.pendingRequests.get(key);
    if (!controller) {
      return false;
    }
    controller.abort();
    this.pendingRequests.delete(key);
    return true;
  }

  cancelAllRequests(): void {
    for (const controller of this.pendingRequests.values()) {
      controller.abort();
    }
    this.pendingRequests.clear();
  }

  private getReconnectDelay(attempt: number): number {
    return this.baseReconnectDelay * Math.pow(2, attempt - 1);
  }

  async checkHealth(): Promise<{ status: string; agent: string; version: string }> {
    const response = await axios.get(`${API_PREFIX}/health`);
    return response.data;
  }

  async createSession(): Promise<{ session_id: string }> {
    const response = await axios.post(`${API_PREFIX}/session/new`);
    return response.data;
  }

  async getSessions(): Promise<{ sessions: SessionInfo[] }> {
    const response = await axios.get(`${API_PREFIX}/sessions`);
    return response.data;
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
    const response = await axios.get(`${API_PREFIX}/models`);
    return response.data;
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

  async fetchStreamChat(request: ChatRequest, callbacks: StreamCallbacks): Promise<void> {
    const requestKey = this.getRequestKey(request);
    if (this.pendingRequests.has(requestKey)) {
      callbacks.onError('请求已在处理中');
      return;
    }

    const controller = new AbortController();
    this.pendingRequests.set(requestKey, controller);

    await this.executeStreamRequest(request, callbacks, controller, requestKey);
  }

  private async executeStreamRequest(
    request: ChatRequest,
    callbacks: StreamCallbacks,
    controller: AbortController,
    requestKey: string,
    attempt: number = 1
  ): Promise<void> {
    if (attempt > 1) {
      this.connectionStatus = SSEConnectionStatus.RECONNECTING;
      callbacks.onConnectionChange?.(this.connectionStatus);
      logger.info(`SSE reconnect attempt ${attempt - 1}`);
    } else {
      this.connectionStatus = SSEConnectionStatus.CONNECTING;
      callbacks.onConnectionChange?.(this.connectionStatus);
    }

    const timeoutId = setTimeout(() => {
      controller.abort();
      logger.warn('SSE request timed out and was aborted');
    }, 180000);

    try {
      const response = await fetch(`${API_PREFIX}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      this.connectionStatus = SSEConnectionStatus.STREAMING;
      callbacks.onConnectionChange?.(this.connectionStatus);

      if (!response.ok) {
        const errorText = await response.text();
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(`HTTP error! status: ${response.status} - ${errorText}`);
        this.pendingRequests.delete(requestKey);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError('无法读取响应流');
        this.pendingRequests.delete(requestKey);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';

      let streamEnded = false;

      while (true) {
        if (controller.signal.aborted) {
          break;
        }
        if (callbacks.onStop && callbacks.onStop()) {
          await reader.cancel();
          break;
        }

        const { done, value } = await reader.read();
        if (done) {
          if (buffer.trim()) {
            streamEnded = this.handleSSELine(buffer, callbacks, requestKey) || streamEnded;
          }
          this.connectionStatus = SSEConnectionStatus.IDLE;
          if (!streamEnded) {
            callbacks.onComplete();
          }
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          streamEnded = this.handleSSELine(line, callbacks, requestKey) || streamEnded;
          if (streamEnded) {
            await reader.cancel();
            break;
          }
        }

        if (streamEnded) {
          break;
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
      if (attempt < this.maxReconnectAttempts) {
        this.connectionStatus = SSEConnectionStatus.RECONNECTING;
        callbacks.onConnectionChange?.(this.connectionStatus);

        const delay = this.getReconnectDelay(attempt);
        await new Promise((resolve) => setTimeout(resolve, delay));
        return this.executeStreamRequest(request, callbacks, controller, requestKey, attempt + 1);
      }

      this.connectionStatus = SSEConnectionStatus.ERROR;
      callbacks.onError(`网络错误: ${errorMessage}`);
    }
  }

  private handleSSELine(line: string, callbacks: StreamCallbacks, requestKey: string): boolean {
    const trimmed = line.replace(/\r$/, '').trim();
    if (!trimmed.startsWith('data:')) {
      return false;
    }

    const dataStr = trimmed.slice(5).trim();
    if (!dataStr) {
      return false;
    }

    if (dataStr === '[DONE]') {
      this.connectionStatus = SSEConnectionStatus.IDLE;
      callbacks.onComplete();
      this.pendingRequests.delete(requestKey);
      return true;
    }

    try {
      const data = JSON.parse(dataStr);
      const dataType = data.type;

      if (dataType === 'heartbeat') {
        return false;
      } else if (dataType === 'metadata' || dataType === 'reasoning_metadata') {
        callbacks.onMetadata({
          totalSteps: data.total_steps || 0,
          toolsUsed: data.tools_used || [],
          hasReasoning: data.has_reasoning || false,
          reasoningLength: data.reasoning_length || 0,
          answerLength: data.answer_length || 0,
          verificationPassed: data.verification_passed === undefined ? null : Boolean(data.verification_passed),
          staleResultCount: Number(data.stale_result_count || 0),
          fallbackSteps: Number(data.fallback_steps || 0),
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
      } else if (dataType === 'done') {
        this.connectionStatus = SSEConnectionStatus.IDLE;
        callbacks.onComplete();
        this.pendingRequests.delete(requestKey);
        return true;
      } else if (data.chunk) {
        callbacks.onChunk(data.chunk);
      } else if (data.error) {
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(data.error);
        this.pendingRequests.delete(requestKey);
      }
    } catch {
      // Ignore malformed SSE chunks and continue.
    }
    return false;
  }
}

export const apiService = new APIService();
