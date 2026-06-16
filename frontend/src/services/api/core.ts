import axios, { type InternalAxiosRequestConfig } from 'axios';
import { logger } from '@/utils/logger';

export const API_BASE =
  (typeof window !== 'undefined' && window.ENV?.NEXT_PUBLIC_API_BASE) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  'http://localhost:38083';

export const API_PREFIX = `${API_BASE}/api`;

type AxiosTraceConfig = InternalAxiosRequestConfig & {
  metadata?: {
    requestId: string;
    traceId: string;
    startedAt: number;
  };
};

export interface APIRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

function generateClientTraceId(prefix = 'req'): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (uuid) return `${prefix}-${uuid}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function buildTraceHeaders() {
  const requestId = generateClientTraceId('req');
  const traceId = generateClientTraceId('trace');
  return {
    requestId,
    traceId,
    headers: {
      'X-Request-ID': requestId,
      'X-Trace-ID': traceId,
    },
  };
}

export function toAxiosRequestConfig(options?: APIRequestOptions) {
  return {
    signal: options?.signal,
    timeout: options?.timeoutMs,
  };
}

export const apiClient = axios.create();

apiClient.interceptors.request.use((config: AxiosTraceConfig) => {
  const trace = buildTraceHeaders();
  config.headers = config.headers || {};
  config.headers['X-Request-ID'] = trace.requestId;
  config.headers['X-Trace-ID'] = trace.traceId;
  config.metadata = {
    requestId: trace.requestId,
    traceId: trace.traceId,
    startedAt: Date.now(),
  };
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    const config = response.config as AxiosTraceConfig;
    const elapsedMs = config.metadata ? Date.now() - config.metadata.startedAt : undefined;
    if (config.metadata) {
      logger.info(
        `REST ${response.config.method?.toUpperCase() || 'GET'} ${response.config.url} request_id=${config.metadata.requestId} trace_id=${config.metadata.traceId} status=${response.status} duration_ms=${elapsedMs}`
      );
    }
    return response;
  },
  (error) => {
    const config = (error.config || {}) as AxiosTraceConfig;
    if (config.metadata) {
      logger.error(
        `REST ${config.method?.toUpperCase() || 'GET'} ${config.url || ''} request_id=${config.metadata.requestId} trace_id=${config.metadata.traceId} failed: ${error.message}`
      );
    }
    return Promise.reject(error);
  }
);
