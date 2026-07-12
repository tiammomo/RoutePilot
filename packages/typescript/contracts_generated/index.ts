/**
 * RoutePilot v1 wire contracts.
 *
 * Generated-facing package synchronized with schemas/ by contract tests.
 * Runtime consumers must still validate untrusted payloads against JSON Schema.
 */

export type Identifier = string;
export type ISODate = string;
export type ISODateTime = string;
export type LocalTime = string;
export type URI = string;
export type IanaTimezone = string;
export type CurrencyCode = string;
export type DecimalString = string;
export type JsonDecimal = number | string;

export type ArtifactType =
  | "TravelQuestion"
  | "TravelAnswer"
  | "TripBrief"
  | "EvidenceBundle"
  | "CandidateSet"
  | "ItineraryPlan"
  | "ConstraintReport"
  | "SemanticRiskReport"
  | "ValidationReport"
  | "TripSnapshot"
  | "ShareSnapshot";

export type SourceKind = "user" | "rag" | "provider" | "agent" | "policy" | "system";
export type CoordinateSystem = "WGS84" | "GCJ-02" | "BD-09";
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface ActorRef {
  actor_type: "user" | "agent" | "service" | "migration";
  actor_id: Identifier;
}

export interface VersionedComponent {
  name: string;
  version: string;
}

export interface SourceRef {
  source_id: Identifier;
  kind: SourceKind;
  name: string;
  version: string;
  uri?: URI | null;
  retrieved_at: ISODateTime;
  publisher?: string | null;
  license?: string | null;
}

export interface ArtifactRef {
  artifact_type: ArtifactType;
  artifact_id: Identifier;
  schema_version: 1;
  version: number;
}

export interface GeoPoint {
  latitude: JsonDecimal;
  longitude: JsonDecimal;
  coordinate_system: CoordinateSystem;
  accuracy_meters?: JsonDecimal | null;
}

export interface ProviderPlaceId {
  provider: string;
  place_id: string;
  version: string;
}

export interface PlaceRef {
  place_id: Identifier;
  display_name: string;
  address?: string | null;
  country_code: string;
  timezone: IanaTimezone;
  location: GeoPoint;
  provider_ids?: ProviderPlaceId[];
  source: SourceRef;
}

export interface MoneyRange {
  min_amount: DecimalString;
  max_amount: DecimalString;
  currency: CurrencyCode;
  basis: "per_person" | "per_group" | "per_room" | "per_item" | "total";
  observed_at: ISODateTime;
  source: SourceRef;
}

export interface TripDateRange {
  start_date: ISODate;
  end_date: ISODate;
  timezone: IanaTimezone;
  flexibility_days?: number;
}

export interface ZonedTimeRange {
  local_date: ISODate;
  start_local_time: LocalTime;
  end_local_time: LocalTime;
  end_day_offset?: 0 | 1;
  timezone: IanaTimezone;
}

export interface Freshness {
  observed_at: ISODateTime;
  valid_until?: ISODateTime | null;
  status: "fresh" | "stale" | "expired" | "unknown";
  source: SourceRef;
}

export interface Citation {
  citation_id: Identifier;
  evidence_id: Identifier;
  title: string;
  locator: string;
  source: SourceRef;
}

export interface TransitLeg {
  mode: "walk" | "bike" | "transit" | "taxi" | "drive" | "rail" | "flight" | "ferry";
  duration_min_minutes: number;
  duration_max_minutes: number;
  distance_meters: number;
  provider_snapshot_ref: SourceRef;
}

export interface ArtifactBase<T extends ArtifactType> {
  artifact_type: T;
  artifact_id: Identifier;
  schema_version: 1;
  version: number;
  created_at: ISODateTime;
  created_by: ActorRef;
  reason: string;
}

export interface TravelQuestion extends ArtifactBase<"TravelQuestion"> {
  question: string;
  locale?: string;
  destination_hint?: string | null;
  asked_at: ISODateTime;
  source: SourceRef;
}

export interface AnswerEvidence {
  evidence_id: Identifier;
  title: string;
  statement: string;
  source: SourceRef;
  freshness: Freshness;
}

export interface AnswerSection {
  heading: string;
  body: string;
  evidence_refs?: Identifier[];
}

export interface TravelAnswer extends ArtifactBase<"TravelAnswer"> {
  question_ref: ArtifactRef;
  question: string;
  answer_status: "answered" | "needs_clarification" | "insufficient_evidence";
  summary: string;
  sections?: AnswerSection[];
  evidence?: AnswerEvidence[];
  citations?: Citation[];
  assumptions?: string[];
  limitations?: string[];
  suggested_questions?: string[];
  generated_at: ISODateTime;
}

export interface TravelerGroup {
  adults: number;
  children_ages?: number[];
  seniors?: number;
  rooms?: number;
  accessibility_needs?: string[];
}

export interface TravelPreference {
  preference_id: Identifier;
  category: "pace" | "food" | "culture" | "nature" | "shopping" | "lodging" | "mobility" | "other";
  value: string;
  priority: number;
}

export interface ConstraintSpec {
  constraint_id: Identifier;
  constraint_type: "date" | "budget" | "mobility" | "dietary" | "lodging" | "visit" | "avoid" | "other";
  hard: boolean;
  priority: number;
  description: string;
  source: SourceRef;
}

export interface ClarificationItem {
  question_id: Identifier;
  prompt: string;
  required: boolean;
  status: "open" | "answered" | "dismissed";
  answer?: string | null;
}

export interface TripBrief extends ArtifactBase<"TripBrief"> {
  destination: PlaceRef;
  date_window: TripDateRange;
  travelers: TravelerGroup;
  budget: MoneyRange;
  preferences?: TravelPreference[];
  constraints?: ConstraintSpec[];
  clarification_items?: ClarificationItem[];
  source: SourceRef;
}

export interface EvidenceClaim {
  claim_id: Identifier;
  statement: string;
  confidence: JsonDecimal;
}

export interface EvidenceItem {
  evidence_id: Identifier;
  kind: "poi" | "area" | "lodging_area" | "opening_hours" | "weather" | "route" | "price" | "policy";
  title: string;
  summary: string;
  place_ref?: PlaceRef | null;
  claims: EvidenceClaim[];
  source: SourceRef;
  freshness: Freshness;
  retrieved_at: ISODateTime;
}

export interface EvidenceConflict {
  conflict_id: Identifier;
  topic: string;
  evidence_refs: Identifier[];
  detail: string;
  resolution_status: "unresolved" | "resolved" | "accepted_risk";
}

export interface EvidenceBundle extends ArtifactBase<"EvidenceBundle"> {
  trip_brief_ref: ArtifactRef;
  timezone: IanaTimezone;
  evidence: EvidenceItem[];
  citations?: Citation[];
  conflicts?: EvidenceConflict[];
}

export interface Candidate {
  candidate_id: Identifier;
  category: "area" | "poi" | "lodging_area" | "activity";
  place_ref: PlaceRef;
  rationale: string;
  evidence_refs: Identifier[];
  score: JsonDecimal;
  estimated_cost?: MoneyRange | null;
  recommended_duration_minutes?: number | null;
  tags?: string[];
}

export interface CandidateSet extends ArtifactBase<"CandidateSet"> {
  trip_brief_ref: ArtifactRef;
  evidence_bundle_ref: ArtifactRef;
  timezone: IanaTimezone;
  candidates: Candidate[];
  selection_notes?: string[];
}

export interface PlanAssumption {
  assumption_id: Identifier;
  text: string;
  source: SourceRef;
  evidence_refs?: Identifier[];
}

export interface PlaceAlternative {
  place_ref: PlaceRef;
  rationale: string;
  evidence_refs: Identifier[];
}

export interface PlanTimeBlock {
  block_id: Identifier;
  title: string;
  category: "visit" | "meal" | "lodging" | "transit" | "free_time" | "check_in" | "check_out";
  place_ref: PlaceRef;
  time_range: ZonedTimeRange;
  duration_minutes: number;
  transit_from_previous?: TransitLeg | null;
  cost_range?: MoneyRange | null;
  evidence_refs: Identifier[];
  alternatives?: PlaceAlternative[];
}

export interface PlanDay {
  date: ISODate;
  timezone: IanaTimezone;
  time_blocks: PlanTimeBlock[];
  day_summary: string;
  daily_cost: MoneyRange;
}

export interface BudgetCategoryTotal {
  category: "lodging" | "food" | "transport" | "tickets" | "shopping" | "other";
  cost: MoneyRange;
}

export interface BudgetSummary {
  estimated_total: MoneyRange;
  category_totals?: BudgetCategoryTotal[];
  contingency_percent: JsonDecimal;
}

export interface RouteSummary {
  total_distance_meters: number;
  total_transit_duration_minutes: number;
  legs_count: number;
  source: SourceRef;
}

export interface RiskSummary {
  risk_id: Identifier;
  severity: Severity;
  message: string;
  evidence_refs?: Identifier[];
  resolution?: string | null;
}

export type PlanStatus =
  | "generated"
  | "candidate"
  | "selected"
  | "validated"
  | "published"
  | "superseded"
  | "rejected"
  | "revoked";

export interface ItineraryPlan extends ArtifactBase<"ItineraryPlan"> {
  plan_id: Identifier;
  status: PlanStatus;
  trip_brief_ref: ArtifactRef;
  candidate_set_ref: ArtifactRef;
  evidence_bundle_ref: ArtifactRef;
  timezone: IanaTimezone;
  assumptions?: PlanAssumption[];
  days: PlanDay[];
  budget_summary: BudgetSummary;
  route_summary: RouteSummary;
  citations: Citation[];
  unresolved_risks?: RiskSummary[];
  validation_ref?: ArtifactRef | null;
}

export interface MetricObservation {
  metric: string;
  value: string;
  unit: string;
}

export interface ConstraintCheck {
  check_id: Identifier;
  constraint_ref?: Identifier | null;
  category: "time" | "route" | "budget" | "opening_hours" | "hard_constraint";
  outcome: "pass" | "warning" | "fail";
  message: string;
  source: SourceRef;
  related_block_ids?: Identifier[];
  observations?: MetricObservation[];
}

export interface CheckSummary {
  passed: number;
  warnings: number;
  failed: number;
}

export interface ConstraintReport extends ArtifactBase<"ConstraintReport"> {
  plan_ref: ArtifactRef;
  timezone: IanaTimezone;
  checked_at: ISODateTime;
  engine: VersionedComponent;
  outcome: "pass" | "warning" | "fail";
  checks: ConstraintCheck[];
  summary: CheckSummary;
}

export interface EvidenceCoverage {
  claims_total: number;
  claims_supported: number;
  claims_missing: number;
  coverage_ratio: JsonDecimal;
}

export interface SemanticRisk {
  risk_id: Identifier;
  category: "evidence_gap" | "assumption" | "source_conflict" | "soft_constraint" | "ambiguity";
  severity: Severity;
  message: string;
  affected_block_ids?: Identifier[];
  evidence_refs?: Identifier[];
  suggested_resolution?: string | null;
}

export interface SemanticRiskReport extends ArtifactBase<"SemanticRiskReport"> {
  plan_ref: ArtifactRef;
  evidence_bundle_ref: ArtifactRef;
  timezone: IanaTimezone;
  assessed_at: ISODateTime;
  reviewer: VersionedComponent;
  assessment_source: SourceRef;
  outcome: "pass" | "warning" | "fail";
  evidence_coverage: EvidenceCoverage;
  risks?: SemanticRisk[];
  source_conflicts?: EvidenceConflict[];
}

export interface ValidationIssue {
  issue_id: Identifier;
  origin: "constraint" | "semantic" | "policy";
  severity: Severity;
  message: string;
  source_report_ref: ArtifactRef;
}

export interface ValidationReport extends ArtifactBase<"ValidationReport"> {
  plan_ref: ArtifactRef;
  constraint_report_ref: ArtifactRef;
  semantic_risk_report_ref: ArtifactRef;
  timezone: IanaTimezone;
  generated_at: ISODateTime;
  policy_version: string;
  verdict: "pass" | "warning" | "fail";
  publishable: boolean;
  blockers?: ValidationIssue[];
  warnings?: ValidationIssue[];
}

export interface TripSnapshot extends ArtifactBase<"TripSnapshot"> {
  trip_id: Identifier;
  title: string;
  status: "draft" | "planning" | "ready" | "archived";
  timezone: IanaTimezone;
  brief: TripBrief;
  itinerary: ItineraryPlan;
  validation: ValidationReport;
  generated_at: ISODateTime;
  source_artifact_versions: ArtifactRef[];
}

export interface PublicGeoPoint {
  latitude: JsonDecimal;
  longitude: JsonDecimal;
  coordinate_system: CoordinateSystem;
  accuracy_meters: number;
}

export interface PublicPlace {
  display_name: string;
  locality: string;
  country_code: string;
  approximate_location?: PublicGeoPoint | null;
}

export interface ShareTransitSummary {
  mode: "walk" | "bike" | "transit" | "taxi" | "drive" | "rail" | "flight" | "ferry";
  duration_minutes: number;
}

export interface ShareTimeBlock {
  block_id: Identifier;
  title: string;
  category: "visit" | "meal" | "lodging" | "transit" | "free_time" | "check_in" | "check_out";
  time_range: ZonedTimeRange;
  place: PublicPlace;
  transit_from_previous?: ShareTransitSummary | null;
  citation_refs?: Identifier[];
}

export interface ShareDay {
  date: ISODate;
  timezone: IanaTimezone;
  summary: string;
  time_blocks: ShareTimeBlock[];
}

export interface ShareSnapshot extends ArtifactBase<"ShareSnapshot"> {
  public_id: Identifier;
  trip_snapshot_ref: ArtifactRef;
  title: string;
  destination: PublicPlace;
  date_window: TripDateRange;
  days: ShareDay[];
  citations?: Citation[];
  published_at: ISODateTime;
}

export type Artifact =
  | TravelQuestion
  | TravelAnswer
  | TripBrief
  | EvidenceBundle
  | CandidateSet
  | ItineraryPlan
  | ConstraintReport
  | SemanticRiskReport
  | ValidationReport
  | TripSnapshot
  | ShareSnapshot;

export type LifecycleState =
  | "queued"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "cancel_requested"
  | "completed"
  | "failed"
  | "canceled";

export type RunPhase =
  | "accepted"
  | "clarification"
  | "research"
  | "planning"
  | "validation"
  | "approval"
  | "publishing"
  | "finalizing"
  | "finished";

export interface RunAcceptedData {
  lifecycle_state: "queued";
  phase: "accepted";
  control_version: number;
}

export interface LifecycleChangedData {
  previous_state: LifecycleState;
  lifecycle_state: LifecycleState;
  control_version: number;
  reason_code?: string | null;
}

export interface PhaseChangedData {
  previous_phase: RunPhase;
  phase: RunPhase;
  progress_percent: number;
  label?: string | null;
  control_version?: number | null;
}

export interface PublicSourceSummary {
  kind: "rag" | "provider" | "knowledge_base";
  name: string;
  version: string;
}

export interface AgentActivityData {
  agent: "orchestrator" | "research" | "planner" | "validation" | "semantic_verifier";
  activity: string;
  status: "started" | "progress" | "completed" | "failed";
  duration_ms?: number | null;
  sources?: PublicSourceSummary[];
  control_version?: number | null;
}

export interface ArtifactChangedData {
  artifact_ref: ArtifactRef;
  status: PlanStatus;
  control_version?: number | null;
}

export interface CitationAddedData {
  citation: Citation;
  artifact_ref: ArtifactRef;
  control_version?: number | null;
}

export interface RiskDetectedData {
  risk_id: Identifier;
  severity: Severity;
  message: string;
  artifact_ref?: ArtifactRef | null;
  control_version?: number | null;
}

export interface InputField {
  field_id: Identifier;
  label: string;
  input_type: "text" | "date" | "number" | "single_select" | "multi_select" | "confirmation";
  required: boolean;
  options?: string[];
}

export interface InputRequiredData {
  request_id: Identifier;
  prompt: string;
  fields: InputField[];
  expires_at?: ISODateTime | null;
  control_version?: number | null;
}

export interface ApprovalRequiredData {
  approval_id: Identifier;
  prompt: string;
  artifact_ref: ArtifactRef;
  expires_at?: ISODateTime | null;
  control_version?: number | null;
}

export interface RunCompletedData {
  lifecycle_state: "completed";
  snapshot_ref: ArtifactRef;
  duration_ms: number;
  control_version?: number | null;
}

export interface PublicError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface RunFailedData {
  lifecycle_state: "failed";
  failed_phase: RunPhase;
  error: PublicError;
  control_version?: number | null;
}

export interface RunCanceledData {
  lifecycle_state: "canceled";
  canceled_by: "user" | "system" | "operator";
  reason?: string | null;
  control_version?: number | null;
}

export interface HeartbeatData {
  server_time: ISODateTime;
}

export interface RunEventBase<T extends string, D> {
  event_id: Identifier;
  schema_version: 1;
  seq: number;
  type: T;
  occurred_at: ISODateTime;
  trip_id: Identifier;
  run_id: Identifier;
  trace_id: Identifier;
  audience: "trip_members";
  data: D;
}

export type RunAcceptedEvent = RunEventBase<"run.accepted", RunAcceptedData>;
export type RunLifecycleChangedEvent = RunEventBase<"run.lifecycle_changed", LifecycleChangedData>;
export type RunPhaseChangedEvent = RunEventBase<"run.phase_changed", PhaseChangedData>;
export type AgentActivityEvent = RunEventBase<"agent.activity", AgentActivityData>;
export type ArtifactCandidateUpdatedEvent = RunEventBase<"artifact.candidate_updated", ArtifactChangedData>;
export type ArtifactPublishedEvent = RunEventBase<"artifact.published", ArtifactChangedData>;
export type CitationAddedEvent = RunEventBase<"citation.added", CitationAddedData>;
export type RiskDetectedEvent = RunEventBase<"risk.detected", RiskDetectedData>;
export type InputRequiredEvent = RunEventBase<"input.required", InputRequiredData>;
export type ApprovalRequiredEvent = RunEventBase<"approval.required", ApprovalRequiredData>;
export type RunCompletedEvent = RunEventBase<"run.completed", RunCompletedData>;
export type RunFailedEvent = RunEventBase<"run.failed", RunFailedData>;
export type RunCanceledEvent = RunEventBase<"run.canceled", RunCanceledData>;
export type HeartbeatEvent = RunEventBase<"heartbeat", HeartbeatData>;

export type RunEvent =
  | RunAcceptedEvent
  | RunLifecycleChangedEvent
  | RunPhaseChangedEvent
  | AgentActivityEvent
  | ArtifactCandidateUpdatedEvent
  | ArtifactPublishedEvent
  | CitationAddedEvent
  | RiskDetectedEvent
  | InputRequiredEvent
  | ApprovalRequiredEvent
  | RunCompletedEvent
  | RunFailedEvent
  | RunCanceledEvent
  | HeartbeatEvent;

export const CONTRACT_SCHEMA_VERSIONS = {
  TravelQuestion: 1,
  TravelAnswer: 1,
  TripBrief: 1,
  EvidenceBundle: 1,
  CandidateSet: 1,
  ItineraryPlan: 1,
  ConstraintReport: 1,
  SemanticRiskReport: 1,
  ValidationReport: 1,
  TripSnapshot: 1,
  ShareSnapshot: 1,
  RunEvent: 1,
} as const;

export interface ContractMap {
  "TravelQuestion@1": TravelQuestion;
  "TravelAnswer@1": TravelAnswer;
  "TripBrief@1": TripBrief;
  "EvidenceBundle@1": EvidenceBundle;
  "CandidateSet@1": CandidateSet;
  "ItineraryPlan@1": ItineraryPlan;
  "ConstraintReport@1": ConstraintReport;
  "SemanticRiskReport@1": SemanticRiskReport;
  "ValidationReport@1": ValidationReport;
  "TripSnapshot@1": TripSnapshot;
  "ShareSnapshot@1": ShareSnapshot;
  "RunEvent@1": RunEvent;
}

export type ContractName = keyof ContractMap;
