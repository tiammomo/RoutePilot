// 类型定义
export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  reasoning?: string;  // AI思考过程（可选）
  diagnostics?: MessageDiagnostics;
}

export interface MessageDiagnostics {
  toolsUsed?: string[];
  verificationPassed?: boolean | null;
  staleResultCount?: number;
  fallbackSteps?: number;
}

export interface SessionInfo {
  session_id: string;
  message_count: number;
  last_active: string;
  name?: string;  // 会话名称（可选）
  model_id?: string;  // 会话使用的模型ID（可选）
}

export interface AppConfig {
  apiBase: string;
}

// 对话模式类型
export type ChatMode = 'direct' | 'react' | 'plan';

export interface ChatRequest {
  message: string;
  session_id: string;
  mode?: ChatMode;  // 对话模式（可选）
}

export interface ChatResponse {
  success: boolean;
  response?: string;
  error?: string;
  session_id?: string;
}

// 模型信息
export interface ModelInfo {
  model_id: string;
  name: string;
  provider: string;
  model: string;
}

// 可用模型响应
export interface AvailableModelsResponse {
  success: boolean;
  models: ModelInfo[];
}

// 设置模型请求
export interface SetModelRequest {
  model_id: string;
}

// 设置模型响应
export interface SetModelResponse {
  success: boolean;
  message: string;
  model_id: string;
}

// 获取会话模型响应
export interface GetSessionModelResponse {
  success: boolean;
  model_id: string;
}
