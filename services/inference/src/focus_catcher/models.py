from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


ANALYTICS_VERSION = "v1"


def utcnow() -> datetime:
    return datetime.now(UTC)


class FocusLabel(str, Enum):
    FOCUSED = "focused"
    DRIFTING = "drifting"
    DISTRACTED = "distracted"
    AWAY = "away"


class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class GemmaReviewStatus(str, Enum):
    IDLE = "idle"
    REVIEWING = "reviewing"
    READY = "ready"
    ERROR = "error"


class ReviewMode(str, Enum):
    LIVE = "live"
    RESCAN = "rescan"


class RuntimeProfile(str, Enum):
    STANDARD = "standard"
    HIGHER_ACCURACY = "higher_accuracy"
    EDGE = "edge"


class AnalysisMode(str, Enum):
    CLASSIFICATION = "classification"
    ANNOTATION = "annotation"


class LiveCoachingMode(str, Enum):
    OFF = "off"
    NOTIFICATIONS = "notifications"
    AMBIENT = "ambient"
    FULL = "full"


class SessionEventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_STOPPED = "session_stopped"
    REVIEW_SUBMITTED = "review_submitted"
    REVIEW_APPLIED = "review_applied"
    LABEL_TRANSITION = "label_transition"
    NUDGE_SENT = "nudge_sent"
    RECOVERY_DETECTED = "recovery_detected"
    REMARKABLE_MARKED = "remarkable_marked"
    REMARKABLE_CLEARED = "remarkable_cleared"
    CONTEXT_CAPTURED = "context_captured"


class ContextCaptureReason(str, Enum):
    INTERVAL = "interval"
    TRANSITION = "transition"
    NUDGE = "nudge"
    MANUAL = "manual"
    START = "start"
    STOP = "stop"


class ConfidenceBucket(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InsightCategory(str, Enum):
    PATTERN = "pattern"
    TRIGGER = "trigger"
    RECOVERY = "recovery"
    ENVIRONMENT = "environment"
    EXPERIMENT_RESULT = "experiment_result"
    CONSISTENCY = "consistency"


def empty_label_counts() -> dict[str, int]:
    return {label.value: 0 for label in FocusLabel}


class DataSourceToggles(BaseModel):
    camera: bool = True
    screen: bool = False
    app_context: bool = False
    input_activity: bool = False
    sound_features: bool = False
    location: bool = False
    calendar_context: bool = False
    manual_tags: bool = False


class ManualTags(BaseModel):
    task: str | None = None
    mood: str | None = None
    energy: str | None = None
    caffeine: str | None = None
    environment: str | None = None
    location_label: str | None = None
    note: str | None = None
    phone_present: bool | None = None


class AnalyticsPreferences(BaseModel):
    raw_retention_days: int = Field(default=7, ge=1, le=365)
    keep_remarkable_raw: bool = True
    analytics_version: str = ANALYTICS_VERSION
    live_coaching_mode: LiveCoachingMode = LiveCoachingMode.NOTIFICATIONS
    capture_toggles: DataSourceToggles = Field(default_factory=DataSourceToggles)
    default_manual_tags: ManualTags = Field(default_factory=ManualTags)


class SetupStatus(BaseModel):
    ready: bool
    model_name: str = "gemma4:e2b"
    runtime_profile: RuntimeProfile = RuntimeProfile.STANDARD
    available_runtime_profiles: list[RuntimeProfile] = Field(
        default_factory=lambda: [RuntimeProfile.STANDARD]
    )
    mode: str = "ollama"
    message: str
    checked_at: datetime = Field(default_factory=utcnow)


class SessionConfig(BaseModel):
    session_name: str = "Focus Buddy Session"
    include_screen_analysis: bool = False
    runtime_profile: RuntimeProfile = RuntimeProfile.STANDARD
    analysis_mode: AnalysisMode = AnalysisMode.ANNOTATION
    live_coaching_mode: LiveCoachingMode = LiveCoachingMode.NOTIFICATIONS
    capture_toggles: DataSourceToggles = Field(default_factory=DataSourceToggles)
    manual_tags: ManualTags = Field(default_factory=ManualTags)
    focused_review_cadence_ms: int = Field(default=1200, ge=250, le=10000)
    active_review_cadence_ms: int = Field(default=650, ge=250, le=5000)
    timelapse_capture_interval_reviews: int = Field(default=1, ge=1, le=20)
    temporary_review_window_sec: int = Field(default=600, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_cadence(self) -> "SessionConfig":
        if self.active_review_cadence_ms > self.focused_review_cadence_ms:
            raise ValueError("active review cadence must be less than or equal to focused cadence")
        self.capture_toggles.camera = True
        if self.include_screen_analysis:
            self.capture_toggles.screen = True
        return self


class SessionCreateRequest(BaseModel):
    config: SessionConfig = Field(default_factory=SessionConfig)


class TransitionRequest(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)


class ReviewInput(BaseModel):
    frame_sequence: int = Field(default=0, ge=0)
    camera_image_b64: str | None = None
    screen_image_b64: str | None = None
    include_screen_analysis: bool = False
    device_id: str = "mac"
    capture_source: str = "mac_camera"
    force_review: bool = False


class ContextCaptureRequest(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    reason: ContextCaptureReason = ContextCaptureReason.INTERVAL
    device_id: str = "mac"
    capture_source: str = "mac_camera"
    context_source: str = "mac"
    screen_enabled: bool = False
    app_name: str | None = None
    window_title: str | None = None
    app_category: str | None = None
    system_idle_seconds: int | None = Field(default=None, ge=0)
    system_idle_state: str | None = None
    keyboard_events: int = Field(default=0, ge=0)
    mouse_events: int = Field(default=0, ge=0)
    scroll_events: int = Field(default=0, ge=0)
    sound_rms: float | None = Field(default=None, ge=0.0)
    sound_peak: float | None = Field(default=None, ge=0.0)
    sound_bucket: str | None = None
    location_label: str | None = None
    calendar_title: str | None = None
    calendar_category: str | None = None
    manual_tags: ManualTags = Field(default_factory=ManualTags)
    phone_present: bool | None = None


class PreferencesUpdateRequest(BaseModel):
    preferences: AnalyticsPreferences


class RemarkableRequest(BaseModel):
    remarkable: bool = True
    note: str | None = None


class GemmaDecision(BaseModel):
    label: FocusLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    note: str
    model_name: str = "gemma4:e2b"


class ReviewEntry(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    sequence: int
    mode: ReviewMode
    label: FocusLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    note: str
    buddy_note: str
    keyframe_path: str | None = None
    screen_used: bool = False
    capture_source: str = "mac_camera"
    remarkable: bool = False
    remarkable_note: str | None = None


PrimitiveMetricValue = str | int | float | bool | None


class SessionEvent(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    type: SessionEventType
    sequence: int | None = None
    label: FocusLabel | None = None
    detail: str | None = None
    metadata: dict[str, PrimitiveMetricValue] = Field(default_factory=dict)


class ContextSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=utcnow)
    reason: ContextCaptureReason = ContextCaptureReason.INTERVAL
    device_id: str = "mac"
    capture_source: str = "mac_camera"
    context_source: str = "mac"
    screen_enabled: bool = False
    app_name: str | None = None
    window_title: str | None = None
    app_category: str | None = None
    system_idle_seconds: int | None = Field(default=None, ge=0)
    system_idle_state: str | None = None
    keyboard_events: int = Field(default=0, ge=0)
    mouse_events: int = Field(default=0, ge=0)
    scroll_events: int = Field(default=0, ge=0)
    sound_rms: float | None = Field(default=None, ge=0.0)
    sound_peak: float | None = Field(default=None, ge=0.0)
    sound_bucket: str | None = None
    location_label: str | None = None
    calendar_title: str | None = None
    calendar_category: str | None = None
    manual_tags: ManualTags = Field(default_factory=ManualTags)
    phone_present: bool | None = None


class SessionMetrics(BaseModel):
    session_length_ms: int = 0
    focused_ms: int = 0
    unfocused_ms: int = 0
    drifting_ms: int = 0
    distracted_ms: int = 0
    away_ms: int = 0
    focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    longest_focus_streak_ms: int = 0
    time_to_first_drift_ms: int | None = None
    time_to_first_distraction_ms: int | None = None
    drift_count: int = 0
    distraction_count: int = 0
    away_count: int = 0
    recovery_count: int = 0
    avg_recovery_ms: float | None = None
    nudge_count: int = 0
    nudge_effective_count: int = 0
    nudge_effectiveness_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    focus_stability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    interruption_density: float = Field(default=0.0, ge=0.0)
    label_transition_count: int = 0
    context_capture_count: int = 0
    last_computed_at: datetime = Field(default_factory=utcnow)


class InsightCard(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: InsightCategory
    title: str
    summary: str
    confidence: ConfidenceBucket = ConfidenceBucket.LOW
    sample_size: int = Field(default=0, ge=0)
    supporting_metrics: dict[str, PrimitiveMetricValue] = Field(default_factory=dict)
    date_range: str | None = None
    generated_by: str = "rules"


class RemarkableMoment(BaseModel):
    created_at: datetime = Field(default_factory=utcnow)
    sequence: int | None = None
    session_level: bool = False
    note: str | None = None
    keyframe_path: str | None = None


class ComparisonPoint(BaseModel):
    dimension: str
    key: str
    sample_size: int = Field(default=0, ge=0)
    session_count: int = Field(default=0, ge=0)
    avg_focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_recovery_ms: float | None = None
    avg_session_length_ms: float = Field(default=0.0, ge=0.0)
    confidence: ConfidenceBucket = ConfidenceBucket.LOW


class ExperimentDimensionView(BaseModel):
    dimension: str
    comparisons: list[ComparisonPoint] = Field(default_factory=list)


class HourBlock(BaseModel):
    hour: int = Field(ge=0, le=23)
    sample_size: int = Field(default=0, ge=0)
    focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class SessionSummary(BaseModel):
    total_reviews: int = 0
    label_counts: dict[str, int] = Field(default_factory=empty_label_counts)
    focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    distraction_reviews: int = 0
    most_common_reason: str | None = None


class DayRollup(BaseModel):
    date: str
    session_count: int = Field(default=0, ge=0)
    total_focused_ms: int = 0
    total_unfocused_ms: int = 0
    avg_focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_recovery_ms: float | None = None
    best_hour_blocks: list[HourBlock] = Field(default_factory=list)
    worst_hour_blocks: list[HourBlock] = Field(default_factory=list)
    top_contexts: list[ComparisonPoint] = Field(default_factory=list)
    insights: list[InsightCard] = Field(default_factory=list)


class WeekRollup(BaseModel):
    week_id: str
    week_start: str
    week_end: str
    session_count: int = Field(default=0, ge=0)
    avg_focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_recovery_ms: float | None = None
    consistency_delta: float | None = None
    best_conditions: list[ComparisonPoint] = Field(default_factory=list)
    weakest_conditions: list[ComparisonPoint] = Field(default_factory=list)
    insights: list[InsightCard] = Field(default_factory=list)


class SessionArtifacts(BaseModel):
    session_dir: str
    session_file: str
    reviews_file: str
    keyframes_dir: str
    rescan_file: str
    summary_file: str
    events_file: str
    contexts_file: str
    metrics_file: str
    insights_file: str


class SessionSnapshot(BaseModel):
    session_id: str
    session_name: str
    created_at: datetime
    updated_at: datetime
    status: SessionStatus
    runtime_profile: RuntimeProfile
    analysis_mode: AnalysisMode
    live_coaching_mode: LiveCoachingMode
    capture_toggles: DataSourceToggles
    manual_tags: ManualTags
    current_label: FocusLabel
    short_reason: str
    companion_message: str
    review_status: GemmaReviewStatus
    last_review_at: datetime | None = None
    include_screen_analysis: bool = False
    is_saved: bool = False
    temporary_expires_at: datetime | None = None
    summary: SessionSummary = Field(default_factory=SessionSummary)
    recent_reviews: list[ReviewEntry] = Field(default_factory=list)
    can_rescan: bool = False
    keyframe_count: int = 0
    rescan_review_count: int = 0
    remarkable: bool = False
    metrics_ready: bool = False
    analytics_version: str = ANALYTICS_VERSION


class SessionReviewDetail(BaseModel):
    session: SessionSnapshot
    live_timeline: list[ReviewEntry] = Field(default_factory=list)
    rescan_timeline: list[ReviewEntry] = Field(default_factory=list)


class SessionAnalyticsDetail(BaseModel):
    session: SessionSnapshot
    metrics: SessionMetrics = Field(default_factory=SessionMetrics)
    insights: list[InsightCard] = Field(default_factory=list)
    contexts: list[ContextSnapshot] = Field(default_factory=list)
    events: list[SessionEvent] = Field(default_factory=list)
    remarkable_moments: list[RemarkableMoment] = Field(default_factory=list)
    privacy_ledger: DataSourceToggles = Field(default_factory=DataSourceToggles)


class DayAnalyticsView(BaseModel):
    generated_at: datetime = Field(default_factory=utcnow)
    today: DayRollup


class WeekAnalyticsView(BaseModel):
    generated_at: datetime = Field(default_factory=utcnow)
    week: WeekRollup


class ExperimentComparisonView(BaseModel):
    generated_at: datetime = Field(default_factory=utcnow)
    dimensions: list[ExperimentDimensionView] = Field(default_factory=list)
    insights: list[InsightCard] = Field(default_factory=list)


class RemarkableIndexEntry(BaseModel):
    session_id: str
    session_name: str
    created_at: datetime
    session_level: bool = False
    sequence: int | None = None
    note: str | None = None
    keyframe_path: str | None = None


class RescanResult(BaseModel):
    session_id: str
    revised_summary: SessionSummary
    revised_timeline: list[ReviewEntry]
    artifact_paths: SessionArtifacts
    persisted: bool


class SessionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    status: SessionStatus = SessionStatus.CREATED
    config: SessionConfig = Field(default_factory=SessionConfig)
    artifacts: SessionArtifacts
    current_label: FocusLabel = FocusLabel.FOCUSED
    short_reason: str = "Waiting for the session to begin."
    companion_message: str = "Set up your camera and start when you're ready."
    review_status: GemmaReviewStatus = GemmaReviewStatus.IDLE
    last_review_at: datetime | None = None
    review_history: list[ReviewEntry] = Field(default_factory=list)
    rescan_history: list[ReviewEntry] = Field(default_factory=list)
    context_history: list[ContextSnapshot] = Field(default_factory=list)
    event_history: list[SessionEvent] = Field(default_factory=list)
    metrics: SessionMetrics = Field(default_factory=SessionMetrics)
    insights: list[InsightCard] = Field(default_factory=list)
    remarkable_moments: list[RemarkableMoment] = Field(default_factory=list)
    summary: SessionSummary = Field(default_factory=SessionSummary)
    is_saved: bool = False
    remarkable: bool = False
    temporary_expires_at: datetime | None = None
    rescan_available: bool = False
    pending_label: FocusLabel | None = None
    pending_confirmations: int = 0
    label_started_at: datetime = Field(default_factory=utcnow)
    last_nudge_at: datetime | None = None
    last_review_sequence: int = 0
    analytics_version: str = ANALYTICS_VERSION

    def to_snapshot(self, limit: int = 14) -> SessionSnapshot:
        recent_reviews = self.review_history[-limit:]
        return SessionSnapshot(
            session_id=self.id,
            session_name=self.config.session_name,
            created_at=self.created_at,
            updated_at=self.updated_at,
            status=self.status,
            runtime_profile=self.config.runtime_profile,
            analysis_mode=self.config.analysis_mode,
            live_coaching_mode=self.config.live_coaching_mode,
            capture_toggles=self.config.capture_toggles,
            manual_tags=self.config.manual_tags,
            current_label=self.current_label,
            short_reason=self.short_reason,
            companion_message=self.companion_message,
            review_status=self.review_status,
            last_review_at=self.last_review_at,
            include_screen_analysis=self.config.include_screen_analysis,
            is_saved=self.is_saved,
            temporary_expires_at=self.temporary_expires_at,
            summary=self.summary,
            recent_reviews=recent_reviews,
            can_rescan=self.status == SessionStatus.STOPPED and self.rescan_available,
            keyframe_count=sum(1 for review in self.review_history if review.keyframe_path),
            rescan_review_count=len(self.rescan_history),
            remarkable=self.remarkable,
            metrics_ready=self.metrics.session_length_ms > 0 or bool(self.review_history),
            analytics_version=self.analytics_version,
        )
