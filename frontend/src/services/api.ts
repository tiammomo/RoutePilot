import axios from 'axios';
import {
  AvailableModelsResponse,
  ChatRequest,
  ChatResponse,
  CityDetail,
  CityListResponse,
  GetSessionModelResponse,
  HealthResponse,
  LLMHealthResponse,
  PlanPreview,
  RegionListResponse,
  RoutePreviewRequest,
  RoutePreviewResponse,
  SessionInfo,
  ShareCreateRequest,
  ShareCreateResponse,
  ShareDetailResponse,
  SetModelRequest,
  SetModelResponse,
  StreamStageEvent,
  TagListResponse,
  ToolIntentsHealthResponse,
  ToolsHealthResponse,
} from '@/types';
import { logger } from '@/utils/logger';

// Keep runtime override order explicit: window.ENV (deployment inject) > build-time env > local default.
const API_BASE =
  (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  'http://localhost:38000';
const API_PREFIX = `${API_BASE}/api`;

export enum SSEConnectionStatus {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  STREAMING = 'streaming',
  RECONNECTING = 'reconnecting',
  ERROR = 'error',
  DISCONNECTED = 'disconnected',
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
  planId?: string | null;
  executionStats?: Record<string, unknown>;
  runId?: string;
}

// Chat stream callbacks intentionally separate "reasoning" and "answer" channels
// so UI can independently animate them (think-first, answer-later).
type StreamCallbacks = {
  onSessionId?: (sessionId: string) => void;
  onStage?: (stage: StreamStageEvent) => void;
  onPlanPreview?: (preview: PlanPreview) => void;
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
    // De-duplicate only near-identical in-flight requests, while allowing follow-up turns.
    return `${request.session_id || 'new'}:${request.message.slice(0, 50)}`;
  }

  cancelAllRequests(): void {
    for (const controller of this.pendingRequests.values()) controller.abort();
    this.pendingRequests.clear();
  }

  private getReconnectDelay(attempt: number): number {
    return this.baseReconnectDelay * Math.pow(2, attempt - 1);
  }

  async checkHealth(): Promise<HealthResponse> {
    const response = await axios.get(`${API_PREFIX}/health`);
    return response.data;
  }

  async checkLLMHealth(): Promise<LLMHealthResponse> {
    const response = await axios.get(`${API_PREFIX}/health/llm`);
    return response.data;
  }

  async checkToolsHealth(): Promise<ToolsHealthResponse> {
    const response = await axios.get(`${API_PREFIX}/health/tools`);
    return response.data;
  }

  async checkToolsIntentsHealth(): Promise<ToolIntentsHealthResponse> {
    const response = await axios.get(`${API_PREFIX}/health/tools/intents`);
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
    const response = await axios.post(`${API_PREFIX}/clear`, null, { params: { session_id: sessionId } });
    return response.data;
  }

  async updateSessionName(sessionId: string, name: string): Promise<{ success: boolean; message?: string }> {
    const response = await axios.put(`${API_PREFIX}/session/${sessionId}/name`, { name });
    return response.data;
  }

  async getAvailableModels(): Promise<AvailableModelsResponse> {
    const response = await axios.get(`${API_PREFIX}/models`);
    return response.data;
  }

  async setSessionModel(sessionId: string, modelId: string): Promise<SetModelResponse> {
    const response = await axios.put(`${API_PREFIX}/session/${sessionId}/model`, { model_id: modelId } as SetModelRequest);
    return response.data;
  }

  async getSessionModel(sessionId: string): Promise<GetSessionModelResponse> {
    const response = await axios.get(`${API_PREFIX}/session/${sessionId}/model`);
    return response.data;
  }

  async getRegions(): Promise<RegionListResponse> {
    const response = await axios.get(`${API_PREFIX}/regions`);
    return response.data;
  }

  async getTags(): Promise<TagListResponse> {
    const response = await axios.get(`${API_PREFIX}/tags`);
    return response.data;
  }

  async getCities(params?: { region?: string; tags?: string[] }): Promise<CityListResponse> {
    const response = await axios.get(`${API_PREFIX}/cities`, {
      params: {
        region: params?.region || undefined,
        tags: params?.tags && params.tags.length > 0 ? params.tags.join(',') : undefined,
      },
    });
    return response.data;
  }

  async getCityDetail(cityId: string): Promise<CityDetail> {
    const response = await axios.get(`${API_PREFIX}/cities/${cityId}`);
    return response.data;
  }

  async getRoutePreview(payload: RoutePreviewRequest): Promise<RoutePreviewResponse> {
    const response = await axios.post(`${API_PREFIX}/map/route-preview`, payload);
    return response.data;
  }

  async createShareLink(payload: ShareCreateRequest): Promise<ShareCreateResponse> {
    const response = await axios.post(`${API_PREFIX}/share-links`, payload);
    return response.data;
  }

  async getShareDetail(shareId: string): Promise<ShareDetailResponse> {
    const response = await axios.get(`${API_PREFIX}/share-links/${encodeURIComponent(shareId)}`);
    return response.data;
  }

  async fetchStreamChat(request: ChatRequest, callbacks: StreamCallbacks): Promise<void> {
    const requestKey = this.getRequestKey(request);
    if (this.pendingRequests.has(requestKey)) {
      callbacks.onError('请求正在处理中，请稍候');
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
    attempt = 1
  ): Promise<void> {
    // Connection status is exposed to UI for observability badges and retry hints.
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      this.connectionStatus = SSEConnectionStatus.STREAMING;
      callbacks.onConnectionChange?.(this.connectionStatus);

      if (!response.ok) {
        const errorText = await response.text();
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(`HTTP error ${response.status}: ${errorText}`);
        this.pendingRequests.delete(requestKey);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError('无法读取流式响应');
        this.pendingRequests.delete(requestKey);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let streamEnded = false;

      while (true) {
        if (controller.signal.aborted) break;
        if (callbacks.onStop && callbacks.onStop()) {
          await reader.cancel();
          break;
        }

        const { done, value } = await reader.read();
        if (done) {
          if (buffer.trim()) streamEnded = this.handleSSELine(buffer, callbacks, requestKey) || streamEnded;
          this.connectionStatus = SSEConnectionStatus.IDLE;
          if (!streamEnded) callbacks.onComplete();
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
        if (streamEnded) break;
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
        await new Promise((resolve) => setTimeout(resolve, this.getReconnectDelay(attempt)));
        return this.executeStreamRequest(request, callbacks, controller, requestKey, attempt + 1);
      }

      this.connectionStatus = SSEConnectionStatus.ERROR;
      callbacks.onError(`网络错误: ${errorMessage}`);
    }
  }

  private handleSSELine(line: string, callbacks: StreamCallbacks, requestKey: string): boolean {
    // Server emits SSE with "data: <json>" envelopes.
    // Returning true means terminal event reached and caller should stop reading.
    const trimmed = line.replace(/\r$/, '').trim();
    if (!trimmed.startsWith('data:')) return false;

    const dataStr = trimmed.slice(5).trim();
    if (!dataStr) return false;

    if (dataStr === '[DONE]') {
      this.connectionStatus = SSEConnectionStatus.IDLE;
      callbacks.onComplete();
      this.pendingRequests.delete(requestKey);
      return true;
    }

    try {
      const data = JSON.parse(dataStr) as Record<string, unknown>;
      const dataType = String(data.type || '');

      if (dataType === 'heartbeat') return false;
      if (dataType === 'session_id' && typeof data.session_id === 'string') {
        callbacks.onSessionId?.(data.session_id);
        return false;
      }
      // Stage / plan / metadata are process channels, not final answer text.
      // The UI uses them to explain "what the system is doing" before the answer is complete.
      if (dataType === 'stage') {
        callbacks.onStage?.({
          stage: typeof data.stage === 'string' ? data.stage : undefined,
          label: typeof data.label === 'string' ? data.label : undefined,
          progress: data.progress === undefined ? null : Number(data.progress),
        });
        return false;
      }
      if (dataType === 'plan_preview') {
        callbacks.onPlanPreview?.({
          planId: typeof data.plan_id === 'string' ? data.plan_id : null,
          intent: typeof data.intent === 'string' ? data.intent : null,
          explanation: typeof data.explanation === 'string' ? data.explanation : null,
          validationStatus: typeof data.validation_status === 'string' ? data.validation_status : null,
          validationErrors: Array.isArray(data.validation_errors) ? (data.validation_errors as string[]) : [],
          steps: Array.isArray(data.steps) ? (data.steps as Array<Record<string, unknown>>) : [],
        });
        return false;
      }
      if (dataType === 'metadata' || dataType === 'reasoning_metadata') {
        // `reasoning_metadata` is backward-compatible with an older server variant.
        callbacks.onMetadata({
          totalSteps: Number(data.total_steps || 0),
          toolsUsed: Array.isArray(data.tools_used) ? (data.tools_used as string[]) : [],
          hasReasoning: Boolean(data.has_reasoning),
          reasoningLength: Number(data.reasoning_length || 0),
          answerLength: Number(data.answer_length || 0),
          verificationPassed: data.verification_passed === undefined ? null : Boolean(data.verification_passed),
          staleResultCount: Number(data.stale_result_count || 0),
          fallbackSteps: Number(data.fallback_steps || 0),
          planId: typeof data.plan_id === 'string' ? data.plan_id : null,
          executionStats:
            data.execution_stats && typeof data.execution_stats === 'object'
              ? (data.execution_stats as Record<string, unknown>)
              : undefined,
          runId: typeof data.run_id === 'string' ? data.run_id : '',
        });
        if (dataType === 'reasoning_metadata' && Boolean(data.has_reasoning)) callbacks.onReasoningStart();
        return false;
      }
      if (dataType === 'reasoning_start') {
        callbacks.onReasoningStart();
        return false;
      }
      if (dataType === 'reasoning_timestamp' && typeof data.timestamp === 'string') {
        callbacks.onReasoningTimestamp(data.timestamp);
        return false;
      }
      if (dataType === 'reasoning_chunk' && typeof data.content === 'string') {
        callbacks.onReasoning(data.content);
        return false;
      }
      if (dataType === 'reasoning_end') {
        callbacks.onReasoningEnd();
        return false;
      }
      if (dataType === 'answer_start') {
        callbacks.onAnswerStart();
        return false;
      }
      if (dataType === 'tool_start' && typeof data.tool === 'string') {
        callbacks.onToolStart?.(data.tool);
        return false;
      }
      if (dataType === 'tool_end' && typeof data.tool === 'string') {
        callbacks.onToolEnd?.(data.tool, typeof data.result === 'string' ? data.result : '');
        return false;
      }
      // `chunk` is the answer channel; everything above feeds progress, previews, or diagnostics.
      if (dataType === 'chunk' && typeof data.content === 'string') {
        callbacks.onChunk(data.content);
        return false;
      }
      if (dataType === 'error' && typeof data.content === 'string') {
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(data.content);
        this.pendingRequests.delete(requestKey);
        return false;
      }
      if (dataType === 'done') {
        this.connectionStatus = SSEConnectionStatus.IDLE;
        callbacks.onComplete();
        this.pendingRequests.delete(requestKey);
        return true;
      }
      // Keep a tiny compatibility fallback for older payloads that may omit `type`
      // but still expose `chunk` / `error` fields.
      if (typeof data.chunk === 'string') callbacks.onChunk(data.chunk);
      if (typeof data.error === 'string') {
        this.connectionStatus = SSEConnectionStatus.ERROR;
        callbacks.onError(data.error);
        this.pendingRequests.delete(requestKey);
      }
    } catch {
      // Ignore malformed SSE chunks.
    }

    return false;
  }
}

export const apiService = new APIService();
