export interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ApiKeyItem {
  id: string;
  project_id: string;
  key_prefix: string;
  label: string;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface ApiKeyCreatedResponse extends ApiKeyItem {
  raw_key: string;
}

export interface LogBatch {
  id: string;
  project_id: string;
  source: string;
  filename: string | null;
  status: "queued" | "pending" | "processing" | "parsing" | "grouping" | "done" | "failed";
  line_count: number;
  error: string | null;
  created_at: string;
}

export interface BatchUploadResponse {
  batch_id: string;
  status: string;
  message: string;
}

export interface LoadDemoDataResponse extends BatchUploadResponse {
  scenario_id: string;
  total_lines: number;
}

export interface DemoScenarioItem {
  scenario_id: string;
  has_incident: boolean;
  root_cause_category: string;
  origin_service: string;
  start_time: string;
  end_time: string;
  expected_key_patterns: string[];
  noise_level: string;
  service_scope: string;
  total_lines: number;
  summary: string;
}

export interface LogEvent {
  id: number;
  project_id: string;
  batch_id: string;
  ts: string;
  service: string;
  level: string;
  message: string;
  trace_id: string | null;
  pattern_id: string | null;
  attributes: Record<string, unknown>;
  raw_line: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrendBucket {
  bucket_start: string;
  count: number;
}

export interface ErrorPattern {
  id: string;
  project_id: string;
  fingerprint: string;
  template: string;
  level: string;
  sample_service: string;
  first_seen: string;
  last_seen: string;
  total_count: number;
  example_event_ids: number[];
  trend: TrendBucket[];
}

export interface OriginCandidate {
  pattern_id: string;
  score: number;
  service: string;
  template: string;
  level: string;
  count: number;
  first_seen: string;
  reason: string;
}

export interface IncidentPatternItem {
  pattern_id: string;
  count: number;
  first_seen: string;
  template: string | null;
  level: string | null;
  sample_service: string | null;
}

export interface TimelineItem {
  event_id: number;
  timestamp: string;
  service: string;
  level: string;
  pattern_id: string | null;
  message: string;
}

export interface Incident {
  id: string;
  project_id: string;
  status: "open" | "resolved";
  severity: "critical" | "high" | "medium" | "low";
  started_at: string;
  ended_at: string | null;
  origin_pattern_id: string | null;
  origin_pattern_template: string | null;
  affected_services: string[];
  event_count: number;
  resolution_note: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  origin_candidates: OriginCandidate[];
  patterns: IncidentPatternItem[];
  timeline: TimelineItem[];
}

export interface VerifiedClaim {
  text: string;
  cited_line_ids: string[];
  cited_event_ids: number[];
  invalid_citations: string[];
  supported: boolean;
  status: "supported" | "unsupported";
}

export interface EvidenceLine {
  short_id: string;
  event_id: number;
  ts: string;
  service: string;
  level: string;
  message: string;
}

export interface IncidentReport {
  id: string | null;
  incident_id: string;
  version: number;
  status: "not_generated" | "pending" | "processing" | "done" | "failed";
  summary: string | null;
  root_cause: string | null;
  confidence: "low" | "medium" | "high" | null;
  severity: string | null;
  affected_services: string[];
  suggested_fixes: string[];
  claims: VerifiedClaim[];
  evidence_lines: EvidenceLine[];
  validation_status: "not_generated" | "pending" | "verified" | "partial" | "unverified" | "failed";
  unsupported_claim_count: number;
  model_name: string | null;
  prompt_version: string | null;
  input_tokens: number;
  output_tokens: number;
  total_incident_events: number;
  selected_evidence_lines: number;
  error: string | null;
  created_at: string | null;
  disclaimer: string;
}

export interface ExplainTriggerResponse {
  report_id: string;
  incident_id: string;
  version: number;
  status: string;
  message: string;
}

export interface SimilarIncidentMatch {
  incident_id: string;
  similarity_score: number;
  status: string;
  severity: string;
  started_at: string;
  ended_at: string | null;
  summary: string | null;
  root_cause: string | null;
  suggested_fixes: string[];
  resolution_note: string | null;
  resolved_at: string | null;
}

export interface SimilarIncidentsResponse {
  incident_id: string;
  items: SimilarIncidentMatch[];
}

export interface ErrorRatePoint {
  bucket: string;
  total_events: number;
  error_events: number;
}

export interface TopPatternSummary {
  id: string;
  template: string;
  level: string;
  sample_service: string;
  total_count: number;
}

export interface ProjectStats {
  project_id: string;
  total_events: number;
  error_events: number;
  total_patterns: number;
  total_incidents: number;
  open_incidents: number;
  resolved_incidents: number;
  error_rate_series: ErrorRatePoint[];
  top_patterns: TopPatternSummary[];
}
