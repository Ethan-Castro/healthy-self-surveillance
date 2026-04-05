from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


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


def empty_label_counts() -> dict[str, int]:
    return {label.value: 0 for label in FocusLabel}


class SetupStatus(BaseModel):
    ready: bool
    model_name: str = "gemma4:e2b"
    mode: str = "ollama"
    message: str
    checked_at: datetime = Field(default_factory=utcnow)


class SessionConfig(BaseModel):
    session_name: str = "Focus Buddy Session"
    include_screen_analysis: bool = False
    focused_review_cadence_ms: int = Field(default=2000, ge=500, le=10000)
    active_review_cadence_ms: int = Field(default=1000, ge=250, le=5000)
    temporary_review_window_sec: int = Field(default=600, ge=60, le=86400)

    @model_validator(mode="after")
    def validate_cadence(self) -> "SessionConfig":
        if self.active_review_cadence_ms > self.focused_review_cadence_ms:
            raise ValueError("active review cadence must be less than or equal to focused cadence")
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
    force_review: bool = False


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


class SessionSummary(BaseModel):
    total_reviews: int = 0
    label_counts: dict[str, int] = Field(default_factory=empty_label_counts)
    focus_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    distraction_reviews: int = 0
    most_common_reason: str | None = None


class SessionArtifacts(BaseModel):
    session_dir: str
    session_file: str
    reviews_file: str
    keyframes_dir: str
    rescan_file: str
    summary_file: str


class SessionSnapshot(BaseModel):
    session_id: str
    session_name: str
    status: SessionStatus
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
    summary: SessionSummary = Field(default_factory=SessionSummary)
    is_saved: bool = False
    temporary_expires_at: datetime | None = None
    rescan_available: bool = False
    pending_label: FocusLabel | None = None
    pending_confirmations: int = 0
    label_started_at: datetime = Field(default_factory=utcnow)
    last_nudge_at: datetime | None = None
    last_review_sequence: int = 0

    def to_snapshot(self, limit: int = 14) -> SessionSnapshot:
        recent_reviews = self.review_history[-limit:]
        return SessionSnapshot(
            session_id=self.id,
            session_name=self.config.session_name,
            status=self.status,
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
        )
