export interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  reasoning?: string;
  diagnostics?: MessageDiagnostics;
}

export interface MessageDiagnostics {
  sessionId?: string;
  toolsUsed?: string[];
  verificationPassed?: boolean | null;
  staleResultCount?: number;
  fallbackSteps?: number;
  planId?: string | null;
  executionStats?: Record<string, unknown>;
  artifact?: TripPlanArtifact | null;
  subagentEvents?: SubagentEvent[];
  runId?: string;
  requestId?: string;
  traceId?: string;
}

export interface TripIntentArtifact {
  name: string;
  confidence?: number | null;
  entities: Record<string, unknown>;
  detail: Record<string, unknown>;
}

export interface ResearchEvidenceArtifact {
  tool?: string;
  status?: string;
  query?: string;
  [key: string]: unknown;
}

export interface ResearchDossierArtifact {
  summary: string;
  evidence: ResearchEvidenceArtifact[];
  destinations: string[];
  sourceTools: string[];
}

export interface ItineraryDraftArtifact {
  planId?: string | null;
  explanation: string;
  steps: Record<string, unknown>[];
  validationStatus: string;
  validationErrors: unknown[];
}

export interface BudgetReportArtifact {
  summary: Record<string, unknown>;
  executionBudget: Record<string, unknown>;
  staleResultCount: number;
  fallbackSteps: number;
}

export interface VerificationReportArtifact {
  passed?: boolean | null;
  shouldRetry: boolean;
  issues: Record<string, unknown>[];
  refreshTargets: string[];
  summary: string;
}

export interface TripPlanArtifact {
  intent: TripIntentArtifact;
  research: ResearchDossierArtifact;
  itinerary: ItineraryDraftArtifact;
  budget: BudgetReportArtifact;
  verification: VerificationReportArtifact;
  answer: string;
  reasoning: string;
  toolsUsed: string[];
  metadata: Record<string, unknown>;
}

export interface ArtifactPatch {
  intent?: Partial<TripIntentArtifact>;
  research?: Partial<ResearchDossierArtifact>;
  itinerary?: Partial<ItineraryDraftArtifact>;
  budget?: Partial<BudgetReportArtifact>;
  verification?: Partial<VerificationReportArtifact>;
  answer?: string;
  reasoning?: string;
  toolsUsed?: string[];
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PlanPreviewStep {
  id?: string;
  title?: string;
  description?: string;
  tool?: string;
  [key: string]: unknown;
}

export interface PlanPreview {
  planId?: string | null;
  intent?: string | null;
  explanation?: string | null;
  validationStatus?: string | null;
  validationErrors?: unknown[];
  steps: PlanPreviewStep[];
  artifact?: TripPlanArtifact | null;
  artifactPatch?: ArtifactPatch | null;
  subagent?: string | null;
  skills?: string[];
}

export const CHAT_STREAM_EVENT_TYPES = {
  SESSION_ID: 'session_id',
  REASONING_START: 'reasoning_start',
  REASONING_CHUNK: 'reasoning_chunk',
  REASONING_END: 'reasoning_end',
  ANSWER_START: 'answer_start',
  STAGE: 'stage',
  PLAN_PREVIEW: 'plan_preview',
  SUBAGENT_START: 'subagent_start',
  SUBAGENT_END: 'subagent_end',
  ARTIFACT_PATCH: 'artifact_patch',
  TOOL_START: 'tool_start',
  TOOL_END: 'tool_end',
  CHUNK: 'chunk',
  METADATA: 'metadata',
  ERROR: 'error',
  DONE: 'done',
} as const;

export type ChatStreamEventType = (typeof CHAT_STREAM_EVENT_TYPES)[keyof typeof CHAT_STREAM_EVENT_TYPES];

export interface StreamStageEvent {
  stage?: string;
  label?: string;
  progress?: number | null;
  subagent?: string | null;
}

export interface SubagentEvent {
  subagent: string;
  description?: string | null;
  skills?: string[];
  toolNames?: string[];
  sequence?: number | null;
  trigger?: string | null;
  status?: string | null;
  summary?: string | null;
  timestamp?: string;
  clientKey?: string;
}

export interface SessionInfo {
  session_id: string;
  message_count: number;
  last_active: string;
  name?: string;
  model_id?: string;
}

export interface AppConfig {
  apiBase: string;
}

export type ChatMode = 'direct' | 'react' | 'plan';

export interface ChatRequest {
  message: string;
  display_message?: string;
  session_id: string;
  mode?: ChatMode;
}

export interface ChatResponse {
  success: boolean;
  response?: string;
  error?: string;
  session_id?: string;
}

export interface SessionMessagesResponse {
  success: boolean;
  messages: Message[];
}

export interface LatestArtifactResponse {
  success: boolean;
  session_id: string;
  artifact_found: boolean;
  artifact: TripPlanArtifact | null;
  run_id?: string | null;
  message_timestamp?: string | null;
  message_index?: number | null;
}

export interface ArtifactHistoryEntry {
  artifact: TripPlanArtifact;
  run_id?: string | null;
  message_timestamp?: string | null;
  message_index: number;
}

export interface ArtifactHistoryResponse {
  success: boolean;
  session_id: string;
  count: number;
  entries: ArtifactHistoryEntry[];
}

export interface ModelInfo {
  model_id: string;
  name: string;
  provider: string;
  model: string;
}

export interface AvailableModelsResponse {
  success: boolean;
  models: ModelInfo[];
}

export interface SetModelRequest {
  model_id: string;
}

export interface SetModelResponse {
  success: boolean;
  message?: string;
  model_id: string;
}

export interface GetSessionModelResponse {
  success: boolean;
  model_id: string;
}

export interface CityAttraction {
  name: string;
  type: string;
  duration: string;
  ticket: number;
  district?: string | null;
  note?: string | null;
}

export interface CitySummary {
  id: string;
  name: string;
  region: string;
  tags: string[];
  description: string;
  avg_budget_per_day: number;
  best_seasons: string[];
  trip_duration: string;
  walk_intensity: 'low' | 'medium' | 'high';
  rain_friendly: boolean;
  family_friendly: boolean;
  food_friendly: boolean;
  style_label: string;
  editorial_note: string;
  data_source: 'curated';
}

export interface CityDetail extends CitySummary {
  attractions: CityAttraction[];
}

export interface CityListResponse {
  cities: CitySummary[];
}

export interface RegionListResponse {
  regions: string[];
}

export interface TagListResponse {
  tags: string[];
}

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  services: Record<string, string>;
}

export interface LLMHealthResponse {
  status: 'ok' | 'not initialized';
  llm_adapter: boolean;
  tools_count: number;
  memory_enabled: boolean;
}

export interface ToolsHealthResponse {
  status: 'ok' | 'not initialized';
  initialized: boolean;
  configured_tools_count: number;
  circuit_open_count: number;
  slo: Record<string, unknown>;
  intent_aggregate: Record<string, Record<string, unknown>>;
  window_minutes: number;
  diagnostics: Record<string, unknown>;
}

export interface ToolIntentsHealthResponse {
  status: 'ok' | 'not initialized';
  window_minutes: number;
  total_requests: number;
  intent_aggregate: Record<string, Record<string, unknown>>;
}

export interface RoutePreviewRequest {
  spots: string[];
  city?: string;
  provider?: 'auto' | 'amap';
}

export interface RoutePoint {
  name: string;
  lat: number;
  lng: number;
}

export interface RoutePreviewResponse {
  success: boolean;
  provider: 'amap';
  points: RoutePoint[];
  distance_m: number;
  duration_s: number;
  static_map_url: string;
  route_polyline: [number, number][];
}

export interface ShareCreateRequest {
  title?: string;
  content: string;
  html_content?: string;
}

export interface ShareCreateResponse {
  success: boolean;
  share_id: string;
  share_url: string;
}

export interface ShareDetailResponse {
  success: boolean;
  share_id: string;
  title?: string;
  content: string;
  html_content?: string | null;
  created_at: string;
}
