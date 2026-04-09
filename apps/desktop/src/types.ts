export type FocusLabel = "focused" | "drifting" | "distracted" | "away";
export type SessionStatus = "created" | "running" | "paused" | "stopped";
export type GemmaReviewStatus = "idle" | "reviewing" | "ready" | "error";
export type ReviewMode = "live" | "rescan";
export type RuntimeProfile = "standard" | "higher_accuracy" | "edge";
export type AnalysisMode = "classification" | "annotation";
export type LiveCoachingMode = "off" | "notifications" | "ambient" | "full";
export type ContextCaptureReason = "interval" | "transition" | "nudge" | "manual" | "start" | "stop";
export type SessionEventType =
  | "session_started"
  | "session_paused"
  | "session_resumed"
  | "session_stopped"
  | "review_submitted"
  | "review_applied"
  | "label_transition"
  | "nudge_sent"
  | "recovery_detected"
  | "remarkable_marked"
  | "remarkable_cleared"
  | "context_captured";
export type ConfidenceBucket = "low" | "medium" | "high";
export type InsightCategory =
  | "pattern"
  | "trigger"
  | "recovery"
  | "environment"
  | "experiment_result"
  | "consistency";

export interface DataSourceToggles {
  camera: boolean;
  screen: boolean;
  app_context: boolean;
  input_activity: boolean;
  sound_features: boolean;
  location: boolean;
  calendar_context: boolean;
  manual_tags: boolean;
}

export interface ManualTags {
  task?: string | null;
  mood?: string | null;
  energy?: string | null;
  caffeine?: string | null;
  environment?: string | null;
  location_label?: string | null;
  note?: string | null;
  phone_present?: boolean | null;
}

export interface AnalyticsPreferences {
  raw_retention_days: number;
  keep_remarkable_raw: boolean;
  analytics_version: string;
  live_coaching_mode: LiveCoachingMode;
  capture_toggles: DataSourceToggles;
  default_manual_tags: ManualTags;
}

export interface SetupStatus {
  ready: boolean;
  model_name: string;
  runtime_profile: RuntimeProfile;
  available_runtime_profiles: RuntimeProfile[];
  mode: string;
  message: string;
  checked_at: string;
}

export interface SessionConfig {
  session_name: string;
  include_screen_analysis: boolean;
  runtime_profile: RuntimeProfile;
  analysis_mode: AnalysisMode;
  live_coaching_mode: LiveCoachingMode;
  capture_toggles: DataSourceToggles;
  manual_tags: ManualTags;
  focused_review_cadence_ms: number;
  active_review_cadence_ms: number;
  timelapse_capture_interval_reviews: number;
  temporary_review_window_sec: number;
}

export interface ReviewInput {
  frame_sequence: number;
  camera_image_b64?: string | null;
  screen_image_b64?: string | null;
  include_screen_analysis: boolean;
  force_review?: boolean;
}

export interface ContextCaptureRequest {
  timestamp?: string;
  reason: ContextCaptureReason;
  device_id?: string;
  capture_source?: string;
  context_source?: string;
  screen_enabled?: boolean;
  app_name?: string | null;
  window_title?: string | null;
  app_category?: string | null;
  system_idle_seconds?: number | null;
  system_idle_state?: string | null;
  keyboard_events?: number;
  mouse_events?: number;
  scroll_events?: number;
  sound_rms?: number | null;
  sound_peak?: number | null;
  sound_bucket?: string | null;
  location_label?: string | null;
  calendar_title?: string | null;
  calendar_category?: string | null;
  manual_tags?: ManualTags;
  phone_present?: boolean | null;
}

export interface RemarkableRequest {
  remarkable?: boolean;
  note?: string | null;
}

export interface ReviewEntry {
  timestamp: string;
  sequence: number;
  mode: ReviewMode;
  label: FocusLabel;
  confidence: number;
  reasons: string[];
  note: string;
  buddy_note: string;
  keyframe_path?: string | null;
  screen_used: boolean;
  remarkable: boolean;
  remarkable_note?: string | null;
}

export interface SessionEvent {
  timestamp: string;
  type: SessionEventType;
  sequence?: number | null;
  label?: FocusLabel | null;
  detail?: string | null;
  metadata: Record<string, string | number | boolean | null>;
}

export interface ContextSnapshot {
  timestamp: string;
  reason: ContextCaptureReason;
  device_id: string;
  capture_source: string;
  context_source: string;
  screen_enabled: boolean;
  app_name?: string | null;
  window_title?: string | null;
  app_category?: string | null;
  system_idle_seconds?: number | null;
  system_idle_state?: string | null;
  keyboard_events: number;
  mouse_events: number;
  scroll_events: number;
  sound_rms?: number | null;
  sound_peak?: number | null;
  sound_bucket?: string | null;
  location_label?: string | null;
  calendar_title?: string | null;
  calendar_category?: string | null;
  manual_tags: ManualTags;
  phone_present?: boolean | null;
}

export interface SessionMetrics {
  session_length_ms: number;
  focused_ms: number;
  unfocused_ms: number;
  drifting_ms: number;
  distracted_ms: number;
  away_ms: number;
  focus_ratio: number;
  longest_focus_streak_ms: number;
  time_to_first_drift_ms?: number | null;
  time_to_first_distraction_ms?: number | null;
  drift_count: number;
  distraction_count: number;
  away_count: number;
  recovery_count: number;
  avg_recovery_ms?: number | null;
  nudge_count: number;
  nudge_effective_count: number;
  nudge_effectiveness_rate: number;
  focus_stability_score: number;
  interruption_density: number;
  label_transition_count: number;
  context_capture_count: number;
  last_computed_at: string;
}

export interface InsightCard {
  id: string;
  category: InsightCategory;
  title: string;
  summary: string;
  confidence: ConfidenceBucket;
  sample_size: number;
  supporting_metrics: Record<string, string | number | boolean | null>;
  date_range?: string | null;
  generated_by: string;
}

export interface RemarkableMoment {
  created_at: string;
  sequence?: number | null;
  session_level: boolean;
  note?: string | null;
  keyframe_path?: string | null;
}

export interface ComparisonPoint {
  dimension: string;
  key: string;
  sample_size: number;
  session_count: number;
  avg_focus_ratio: number;
  avg_recovery_ms?: number | null;
  avg_session_length_ms: number;
  confidence: ConfidenceBucket;
}

export interface ExperimentDimensionView {
  dimension: string;
  comparisons: ComparisonPoint[];
}

export interface HourBlock {
  hour: number;
  sample_size: number;
  focus_ratio: number;
}

export interface SessionSummary {
  total_reviews: number;
  label_counts: Record<FocusLabel, number>;
  focus_ratio: number;
  distraction_reviews: number;
  most_common_reason?: string | null;
}

export interface DayRollup {
  date: string;
  session_count: number;
  total_focused_ms: number;
  total_unfocused_ms: number;
  avg_focus_ratio: number;
  avg_recovery_ms?: number | null;
  best_hour_blocks: HourBlock[];
  worst_hour_blocks: HourBlock[];
  top_contexts: ComparisonPoint[];
  insights: InsightCard[];
}

export interface WeekRollup {
  week_id: string;
  week_start: string;
  week_end: string;
  session_count: number;
  avg_focus_ratio: number;
  avg_recovery_ms?: number | null;
  consistency_delta?: number | null;
  best_conditions: ComparisonPoint[];
  weakest_conditions: ComparisonPoint[];
  insights: InsightCard[];
}

export interface SessionArtifacts {
  session_dir: string;
  session_file: string;
  reviews_file: string;
  keyframes_dir: string;
  rescan_file: string;
  summary_file: string;
  events_file: string;
  contexts_file: string;
  metrics_file: string;
  insights_file: string;
}

export interface SessionSnapshot {
  session_id: string;
  session_name: string;
  created_at: string;
  updated_at: string;
  status: SessionStatus;
  runtime_profile: RuntimeProfile;
  analysis_mode: AnalysisMode;
  live_coaching_mode: LiveCoachingMode;
  capture_toggles: DataSourceToggles;
  manual_tags: ManualTags;
  current_label: FocusLabel;
  short_reason: string;
  companion_message: string;
  review_status: GemmaReviewStatus;
  last_review_at?: string | null;
  include_screen_analysis: boolean;
  is_saved: boolean;
  temporary_expires_at?: string | null;
  summary: SessionSummary;
  recent_reviews: ReviewEntry[];
  can_rescan: boolean;
  keyframe_count: number;
  rescan_review_count: number;
  remarkable: boolean;
  metrics_ready: boolean;
  analytics_version: string;
}

export interface SessionReviewDetail {
  session: SessionSnapshot;
  live_timeline: ReviewEntry[];
  rescan_timeline: ReviewEntry[];
}

export interface SessionAnalyticsDetail {
  session: SessionSnapshot;
  metrics: SessionMetrics;
  insights: InsightCard[];
  contexts: ContextSnapshot[];
  events: SessionEvent[];
  remarkable_moments: RemarkableMoment[];
  privacy_ledger: DataSourceToggles;
}

export interface DayAnalyticsView {
  generated_at: string;
  today: DayRollup;
}

export interface WeekAnalyticsView {
  generated_at: string;
  week: WeekRollup;
}

export interface ExperimentComparisonView {
  generated_at: string;
  dimensions: ExperimentDimensionView[];
  insights: InsightCard[];
}

export interface RescanResult {
  session_id: string;
  revised_summary: SessionSummary;
  revised_timeline: ReviewEntry[];
  artifact_paths: SessionArtifacts;
  persisted: boolean;
}
