export type FocusLabel = "focused" | "drifting" | "distracted" | "away";
export type SessionStatus = "created" | "running" | "paused" | "stopped";
export type GemmaReviewStatus = "idle" | "reviewing" | "ready" | "error";
export type ReviewMode = "live" | "rescan";
export type RuntimeProfile = "standard" | "higher_accuracy";

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
  focused_review_cadence_ms: number;
  active_review_cadence_ms: number;
  temporary_review_window_sec: number;
}

export interface ReviewInput {
  frame_sequence: number;
  camera_image_b64?: string | null;
  screen_image_b64?: string | null;
  include_screen_analysis: boolean;
  force_review?: boolean;
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
}

export interface SessionSummary {
  total_reviews: number;
  label_counts: Record<FocusLabel, number>;
  focus_ratio: number;
  distraction_reviews: number;
  most_common_reason?: string | null;
}

export interface SessionArtifacts {
  session_dir: string;
  session_file: string;
  reviews_file: string;
  keyframes_dir: string;
  rescan_file: string;
  summary_file: string;
}

export interface SessionSnapshot {
  session_id: string;
  session_name: string;
  created_at: string;
  updated_at: string;
  status: SessionStatus;
  runtime_profile: RuntimeProfile;
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
}

export interface SessionReviewDetail {
  session: SessionSnapshot;
  live_timeline: ReviewEntry[];
  rescan_timeline: ReviewEntry[];
}

export interface RescanResult {
  session_id: string;
  revised_summary: SessionSummary;
  revised_timeline: ReviewEntry[];
  artifact_paths: SessionArtifacts;
  persisted: boolean;
}
