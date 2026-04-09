from __future__ import annotations

import base64
import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .adapters import GemmaAdapter, build_gemma_adapter
from .analytics import (
    build_day_rollup,
    build_experiment_view,
    build_remarkable_index,
    build_session_insights,
    build_today_and_week,
    build_week_rollup,
    compute_session_metrics,
)
from .models import (
    ANALYTICS_VERSION,
    AnalyticsPreferences,
    ConfidenceBucket,
    ContextCaptureReason,
    ContextCaptureRequest,
    ContextSnapshot,
    DayAnalyticsView,
    DayRollup,
    ExperimentComparisonView,
    FocusLabel,
    GemmaDecision,
    GemmaReviewStatus,
    InsightCard,
    ManualTags,
    RemarkableMoment,
    RemarkableRequest,
    RescanResult,
    ReviewEntry,
    ReviewInput,
    ReviewMode,
    SessionAnalyticsDetail,
    SessionConfig,
    SessionCreateRequest,
    SessionEvent,
    SessionEventType,
    SessionRecord,
    SessionReviewDetail,
    SessionSnapshot,
    SessionStatus,
    SessionSummary,
    SetupStatus,
    TransitionRequest,
    RuntimeProfile,
    WeekAnalyticsView,
    utcnow,
)
from .storage import AnalyticsStore, SessionStore


SERVICE_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = SERVICE_ROOT / "data"
logger = logging.getLogger("focus_buddy.service")


class FocusCatcherService:
    def __init__(
        self,
        data_root: Path = DATA_ROOT,
        gemma_adapter: GemmaAdapter | None = None,
    ) -> None:
        self.store = SessionStore(data_root / "sessions")
        self.analytics_store = AnalyticsStore(data_root / "analytics")
        self.preferences = self.analytics_store.load_preferences()
        self.store.load_existing()
        self.gemma_adapter = gemma_adapter or build_gemma_adapter()
        self._state_lock = Lock()
        self._job_lock = Lock()
        self._inflight_sessions: set[str] = set()
        self._queued_reviews: dict[str, ReviewInput] = {}
        self._last_review_requested_at: dict[str, object] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="focus-buddy")
        self._cleanup_expired_temporary_sessions()
        self._cleanup_expired_raw_evidence()
        self._refresh_rollups()

    def setup_status(self, runtime_profile: RuntimeProfile | None = None) -> SetupStatus:
        self._cleanup_expired_temporary_sessions()
        self._cleanup_expired_raw_evidence()
        return self.gemma_adapter.check_setup(runtime_profile)

    def get_preferences(self) -> AnalyticsPreferences:
        self.preferences = self.analytics_store.load_preferences()
        return self.preferences.model_copy(deep=True)

    def update_preferences(self, preferences: AnalyticsPreferences) -> AnalyticsPreferences:
        self.preferences = self.analytics_store.save_preferences(preferences)
        self._cleanup_expired_raw_evidence()
        return self.preferences.model_copy(deep=True)

    def list_sessions(self) -> list[SessionSnapshot]:
        self._cleanup_expired_temporary_sessions()
        self._cleanup_expired_raw_evidence()
        return [session.to_snapshot() for session in self.store.list()]

    def create_session(self, config: SessionConfig) -> SessionSnapshot:
        self._cleanup_expired_temporary_sessions()
        session_id = str(uuid4())
        artifacts = self.store.create_artifacts(session_id)
        session = SessionRecord(
            id=session_id,
            config=config,
            artifacts=artifacts,
            short_reason="Camera-only by default. Start when you're ready.",
            companion_message=(
                "I’ll classify attention simply."
                if config.analysis_mode.value == "classification"
                else "I’ll annotate what I see and keep the feedback gentle."
            ),
            analytics_version=ANALYTICS_VERSION,
        )
        session.summary = self._build_summary(session.review_history)
        self._refresh_session_analytics_mutating(session)
        self.store.save(session)
        self.store.write_summary(session.id, session.summary)
        self.store.write_metrics(session.id, session.metrics)
        self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        logger.info(
            "Focus Buddy Debug: created session session_id=%s analysis_mode=%s runtime_profile=%s include_screen=%s",
            session_id,
            config.analysis_mode.value,
            config.runtime_profile.value,
            config.include_screen_analysis,
        )
        return session.to_snapshot()

    def get_session(self, session_id: str) -> SessionSnapshot:
        self._cleanup_expired_temporary_sessions()
        self._cleanup_expired_raw_evidence()
        return self.store.get(session_id).to_snapshot()

    def get_session_review(self, session_id: str) -> SessionReviewDetail:
        self._cleanup_expired_temporary_sessions()
        self._cleanup_expired_raw_evidence()
        session = self.store.get(session_id)
        return SessionReviewDetail(
            session=session.to_snapshot(limit=max(len(session.review_history), 14)),
            live_timeline=session.review_history,
            rescan_timeline=session.rescan_history,
        )

    def get_session_analytics(self, session_id: str) -> SessionAnalyticsDetail:
        self._cleanup_expired_raw_evidence()
        session = self.store.get(session_id)
        return SessionAnalyticsDetail(
            session=session.to_snapshot(limit=max(len(session.review_history), 20)),
            metrics=session.metrics,
            insights=session.insights,
            contexts=session.context_history[-48:],
            events=session.event_history[-96:],
            remarkable_moments=session.remarkable_moments,
            privacy_ledger=session.config.capture_toggles,
        )

    def get_today_analytics(self) -> DayAnalyticsView:
        sessions = [session for session in self.store.list() if session.summary.total_reviews > 0]
        day_rollup, _ = build_today_and_week(sessions)
        self.analytics_store.write_day_rollup(day_rollup)
        return DayAnalyticsView(today=day_rollup)

    def get_week_analytics(self) -> WeekAnalyticsView:
        sessions = [session for session in self.store.list() if session.summary.total_reviews > 0]
        _, week_rollup = build_today_and_week(sessions)
        self.analytics_store.write_week_rollup(week_rollup)
        return WeekAnalyticsView(week=week_rollup)

    def get_experiment_analytics(self) -> ExperimentComparisonView:
        sessions = [session for session in self.store.list() if session.summary.total_reviews > 0]
        return build_experiment_view(sessions)

    def get_analytics_insights(self) -> list[InsightCard]:
        sessions = [session for session in self.store.list() if session.summary.total_reviews > 0]
        day_rollup, week_rollup = build_today_and_week(sessions)
        insights = [
            *day_rollup.insights,
            *week_rollup.insights,
        ]
        recent_session_insights = [
            card
            for session in sessions[:3]
            for card in session.insights[:2]
        ]
        insights.extend(recent_session_insights)
        deduped: list[InsightCard] = []
        seen = set()
        for card in insights:
            key = (card.category.value, card.title, card.summary)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(card)
        return deduped[:12]

    def start_session(self, session_id: str, request: TransitionRequest) -> SessionSnapshot:
        session = self.store.get(session_id)
        setup = self.setup_status(session.config.runtime_profile)
        if not setup.ready:
            raise ValueError(setup.message)

        with self._state_lock:
            session = self.store.get(session_id)
            event_type = (
                SessionEventType.SESSION_RESUMED if session.status == SessionStatus.PAUSED else SessionEventType.SESSION_STARTED
            )
            session.status = SessionStatus.RUNNING
            session.review_status = GemmaReviewStatus.IDLE
            session.short_reason = "Live reviews begin with the next frame."
            session.companion_message = "You’re live. Keep the next few minutes simple and I’ll keep watch."
            session.temporary_expires_at = None
            session.updated_at = request.timestamp
            event = self._record_event_mutating(
                session,
                event_type,
                detail="Session entered live review mode.",
                label=session.current_label,
                metadata={
                    "live_coaching_mode": session.config.live_coaching_mode.value,
                    "analysis_mode": session.config.analysis_mode.value,
                },
                timestamp=request.timestamp,
            )
            self.store.save(session)
            self.store.append_event(session.id, event)
            logger.info(
                "Focus Buddy Debug: started session session_id=%s analysis_mode=%s runtime_profile=%s",
                session_id,
                session.config.analysis_mode.value,
                session.config.runtime_profile.value,
            )
            return session.to_snapshot()

    def pause_session(self, session_id: str, request: TransitionRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.status = SessionStatus.PAUSED
            session.review_status = GemmaReviewStatus.IDLE
            session.short_reason = "Session paused."
            session.companion_message = "Paused. Take a breath and resume when you want."
            session.updated_at = request.timestamp
            event = self._record_event_mutating(
                session,
                SessionEventType.SESSION_PAUSED,
                detail="Session paused.",
                label=session.current_label,
                timestamp=request.timestamp,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_event(session.id, event)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot()

    def stop_session(self, session_id: str, request: TransitionRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.status = SessionStatus.STOPPED
            session.review_status = GemmaReviewStatus.READY if session.review_history else GemmaReviewStatus.IDLE
            session.updated_at = request.timestamp
            if not session.is_saved:
                session.temporary_expires_at = utcnow().replace(microsecond=0) + timedelta(
                    seconds=session.config.temporary_review_window_sec
                )
            session.short_reason = "Session ended."
            if session.is_saved:
                session.companion_message = "Session ended. You can rescan it any time from the saved session."
            else:
                session.companion_message = (
                    "Session ended. You can rescan or save this before temporary keyframes expire."
                )
            session.summary = self._build_summary(session.review_history)
            event = self._record_event_mutating(
                session,
                SessionEventType.SESSION_STOPPED,
                detail="Session stopped.",
                label=session.current_label,
                timestamp=request.timestamp,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_event(session.id, event)
            self.store.write_summary(session.id, session.summary)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot()

    def submit_review(self, session_id: str, review_input: ReviewInput) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            if session.status != SessionStatus.RUNNING:
                raise ValueError("session is not running")

            session.updated_at = utcnow()
            self.store.save(session)

        if not review_input.camera_image_b64:
            logger.info(
                "Focus Buddy Debug: skipped live review without camera image session_id=%s frame_sequence=%s",
                session_id,
                review_input.frame_sequence,
            )
            return self.store.get(session_id).to_snapshot()

        if not self._should_queue_review(self.store.get(session_id), review_input):
            with self._job_lock:
                if review_input.force_review and session_id in self._inflight_sessions:
                    self._queued_reviews[session_id] = review_input
                    logger.info(
                        "Focus Buddy Debug: buffered forced live review session_id=%s frame_sequence=%s while another review was inflight",
                        session_id,
                        review_input.frame_sequence,
                    )
            return self.store.get(session_id).to_snapshot()

        with self._state_lock:
            session = self.store.get(session_id)
            session.review_status = GemmaReviewStatus.REVIEWING
            submit_event = self._record_event_mutating(
                session,
                SessionEventType.REVIEW_SUBMITTED,
                sequence=review_input.frame_sequence,
                detail="Live review queued.",
                label=session.current_label,
                metadata={
                    "screen_enabled": bool(review_input.screen_image_b64),
                    "capture_source": review_input.capture_source,
                    "device_id": review_input.device_id,
                },
            )
            self.store.save(session)
            self.store.append_event(session.id, submit_event)
            logger.info(
                "Focus Buddy Debug: queued live review session_id=%s frame_sequence=%s force=%s screen=%s analysis_mode=%s runtime_profile=%s",
                session_id,
                review_input.frame_sequence,
                review_input.force_review,
                bool(review_input.screen_image_b64),
                session.config.analysis_mode.value,
                session.config.runtime_profile.value,
            )

        self._executor.submit(self._run_live_review, session_id, review_input)
        return self.store.get(session_id).to_snapshot()

    def save_session(self, session_id: str) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.is_saved = True
            session.temporary_expires_at = None
            session.companion_message = "Saved locally. You can revisit or rescan this session later."
            session.summary = self._build_summary(session.review_history)
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.write_summary(session.id, session.summary)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
            return session.to_snapshot()

    def rescan_session(self, session_id: str) -> RescanResult:
        with self._state_lock:
            session = self.store.get(session_id)
            if session.status != SessionStatus.STOPPED:
                raise ValueError("stop the session before rescanning")
            if not session.rescan_available:
                raise ValueError("no saved keyframes are available to rescan")

        keyframe_dir = Path(self.store.get(session_id).artifacts.keyframes_dir)
        timeline: list[ReviewEntry] = []
        live_reviews = self.store.get(session_id).review_history

        for keyframe in sorted(keyframe_dir.glob("*.jpg")):
            sequence = self._sequence_from_keyframe_name(keyframe.name)
            image_b64 = base64.b64encode(keyframe.read_bytes()).decode("utf-8")
            decision = self.gemma_adapter.review_rescan(
                image_b64=image_b64,
                config=self.store.get(session_id).config,
                live_reviews=live_reviews,
            )
            timeline.append(
                ReviewEntry(
                    sequence=sequence,
                    mode=ReviewMode.RESCAN,
                    label=decision.label,
                    confidence=decision.confidence,
                    reasons=decision.reasons,
                    note=decision.note,
                    buddy_note=self._rescan_buddy_line(decision),
                    keyframe_path=str(keyframe),
                    screen_used=self.store.get(session_id).config.include_screen_analysis,
                )
            )

        revised_summary = self._build_summary(timeline)

        with self._state_lock:
            session = self.store.get(session_id)
            session.rescan_history = timeline
            session.summary = revised_summary
            session.updated_at = utcnow()
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.replace_rescan(session.id, timeline)
            self.store.write_summary(session.id, revised_summary)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)

        self._refresh_rollups()
        return RescanResult(
            session_id=session_id,
            revised_summary=revised_summary,
            revised_timeline=timeline,
            artifact_paths=self.store.get(session_id).artifacts,
            persisted=self.store.get(session_id).is_saved,
        )

    def add_context(self, session_id: str, request: ContextCaptureRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            context = ContextSnapshot(
                timestamp=request.timestamp,
                reason=request.reason,
                device_id=request.device_id,
                capture_source=request.capture_source,
                context_source=request.context_source,
                screen_enabled=request.screen_enabled,
                app_name=request.app_name,
                window_title=request.window_title,
                app_category=request.app_category or self._categorize_app_context(request.app_name, request.window_title),
                system_idle_seconds=request.system_idle_seconds,
                system_idle_state=request.system_idle_state,
                keyboard_events=request.keyboard_events,
                mouse_events=request.mouse_events,
                scroll_events=request.scroll_events,
                sound_rms=request.sound_rms,
                sound_peak=request.sound_peak,
                sound_bucket=request.sound_bucket,
                location_label=request.location_label or session.config.manual_tags.location_label,
                calendar_title=request.calendar_title,
                calendar_category=request.calendar_category,
                manual_tags=self._merge_manual_tags(session.config.manual_tags, request.manual_tags),
                phone_present=request.phone_present if request.phone_present is not None else request.manual_tags.phone_present,
            )
            session.config.manual_tags = context.manual_tags
            session.context_history.append(context)
            context_event = self._record_event_mutating(
                session,
                SessionEventType.CONTEXT_CAPTURED,
                detail=f"Context captured via {context.reason.value}.",
                label=session.current_label,
                metadata={
                    "app_category": context.app_category,
                    "screen_enabled": context.screen_enabled,
                    "location_label": context.location_label,
                },
                timestamp=context.timestamp,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_context(session.id, context)
            self.store.append_event(session.id, context_event)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot()

    def set_session_remarkable(self, session_id: str, request: RemarkableRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.remarkable = request.remarkable
            session.remarkable_moments = [
                moment for moment in session.remarkable_moments if not moment.session_level
            ]
            if request.remarkable:
                session.remarkable_moments.append(
                    RemarkableMoment(session_level=True, note=request.note)
                )
            event = self._record_event_mutating(
                session,
                SessionEventType.REMARKABLE_MARKED if request.remarkable else SessionEventType.REMARKABLE_CLEARED,
                detail=request.note or ("Session marked as remarkable." if request.remarkable else "Session no longer remarkable."),
                label=session.current_label,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_event(session.id, event)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot()

    def set_moment_remarkable(self, session_id: str, sequence: int, request: RemarkableRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            review = self._find_review_entry(session, sequence)
            review.remarkable = True
            review.remarkable_note = request.note
            session.remarkable_moments = [
                moment
                for moment in session.remarkable_moments
                if moment.session_level or moment.sequence != sequence
            ]
            session.remarkable_moments.append(
                RemarkableMoment(
                    sequence=sequence,
                    note=request.note,
                    keyframe_path=review.keyframe_path,
                )
            )
            event = self._record_event_mutating(
                session,
                SessionEventType.REMARKABLE_MARKED,
                sequence=sequence,
                detail=request.note or "Moment marked as remarkable.",
                label=review.label,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_event(session.id, event)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot(limit=max(len(self.store.get(session_id).review_history), 20))

    def clear_moment_remarkable(self, session_id: str, sequence: int) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            review = self._find_review_entry(session, sequence)
            review.remarkable = False
            review.remarkable_note = None
            session.remarkable_moments = [
                moment
                for moment in session.remarkable_moments
                if moment.session_level or moment.sequence != sequence
            ]
            event = self._record_event_mutating(
                session,
                SessionEventType.REMARKABLE_CLEARED,
                sequence=sequence,
                detail="Moment remarkable flag cleared.",
                label=review.label,
            )
            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_event(session.id, event)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
        self._refresh_rollups()
        return session.to_snapshot(limit=max(len(self.store.get(session_id).review_history), 20))

    def _run_live_review(self, session_id: str, review_input: ReviewInput) -> None:
        try:
            session = self.store.get(session_id)
            decision = self.gemma_adapter.review_live(
                review_input=review_input,
                config=session.config,
                recent_reviews=session.review_history,
                current_label=session.current_label.value,
            )
            logger.info(
                "Focus Buddy Debug: gemma live decision session_id=%s frame_sequence=%s model=%s label=%s confidence=%.2f reasons=%s note=%s",
                session_id,
                review_input.frame_sequence,
                decision.model_name,
                decision.label.value,
                decision.confidence,
                ",".join(decision.reasons) if decision.reasons else "-",
                decision.note,
            )
            self._apply_live_decision(session_id, review_input, decision)
        except Exception as exc:  # pragma: no cover - runtime path
            logger.exception(
                "Focus Buddy Debug: live review failed session_id=%s frame_sequence=%s error=%s",
                session_id,
                review_input.frame_sequence,
                exc,
            )
            with self._state_lock:
                session = self.store.get(session_id)
                session.review_status = GemmaReviewStatus.ERROR
                session.short_reason = "I missed that check."
                session.companion_message = "I lost the thread for a second. I’ll try again on the next review."
                session.updated_at = utcnow()
                self.store.save(session)
        finally:
            queued_review: ReviewInput | None = None
            with self._job_lock:
                self._inflight_sessions.discard(session_id)
                queued_review = self._queued_reviews.pop(session_id, None)
            if queued_review is not None:
                logger.info(
                    "Focus Buddy Debug: flushing buffered live review session_id=%s frame_sequence=%s",
                    session_id,
                    queued_review.frame_sequence,
                )
                try:
                    self.submit_review(session_id, queued_review)
                except Exception as queued_exc:  # pragma: no cover - runtime path
                    logger.exception(
                        "Focus Buddy Debug: buffered live review failed to queue session_id=%s frame_sequence=%s error=%s",
                        session_id,
                        queued_review.frame_sequence,
                        queued_exc,
                    )

    def _apply_live_decision(self, session_id: str, review_input: ReviewInput, decision: GemmaDecision) -> None:
        with self._state_lock:
            session = self.store.get(session_id)
            if session.status != SessionStatus.RUNNING:
                return

            keyframe_path = None
            if self._should_capture_keyframe(session, review_input, decision) and review_input.camera_image_b64:
                keyframe_path = self.store.write_keyframe(
                    session_id=session.id,
                    sequence=review_input.frame_sequence,
                    label=decision.label.value,
                    image_b64=review_input.camera_image_b64,
                )
                session.rescan_available = True

            entry = ReviewEntry(
                sequence=review_input.frame_sequence,
                mode=ReviewMode.LIVE,
                label=decision.label,
                confidence=decision.confidence,
                reasons=decision.reasons,
                note=self._clamp_sentence(decision.note),
                buddy_note="",
                keyframe_path=keyframe_path,
                screen_used=session.config.include_screen_analysis and bool(review_input.screen_image_b64),
                capture_source=review_input.capture_source,
            )

            extra_events = self._update_visible_state(session, entry)
            entry.buddy_note = session.companion_message
            session.review_history.append(entry)
            session.last_review_at = entry.timestamp
            session.last_review_sequence = review_input.frame_sequence
            session.review_status = GemmaReviewStatus.READY
            session.summary = self._build_summary(session.review_history)
            session.updated_at = entry.timestamp

            review_event = self._record_event_mutating(
                session,
                SessionEventType.REVIEW_APPLIED,
                sequence=review_input.frame_sequence,
                detail=entry.note,
                label=decision.label,
                metadata={
                    "model_name": decision.model_name,
                    "keyframe_saved": bool(keyframe_path),
                    "screen_used": entry.screen_used,
                    "capture_source": review_input.capture_source,
                },
                timestamp=entry.timestamp,
            )

            self._refresh_session_analytics_mutating(session)
            self.store.save(session)
            self.store.append_review(session.id, entry)
            self.store.append_event(session.id, review_event)
            for event in extra_events:
                self.store.append_event(session.id, event)
            self.store.write_summary(session.id, session.summary)
            self.store.write_metrics(session.id, session.metrics)
            self.store.write_insights(session.id, session.insights)
            logger.info(
                "Focus Buddy Debug: applied live state session_id=%s frame_sequence=%s decision_label=%s visible_label=%s keyframe_saved=%s companion=%s",
                session_id,
                review_input.frame_sequence,
                decision.label.value,
                session.current_label.value,
                bool(keyframe_path),
                session.companion_message,
            )

        self._refresh_rollups()

    def _update_visible_state(self, session: SessionRecord, entry: ReviewEntry) -> list[SessionEvent]:
        required_confirmations = 1 if entry.label == FocusLabel.AWAY else 2
        previous_visible_label = session.current_label
        previous_companion = session.companion_message

        if entry.label == session.current_label:
            session.pending_label = None
            session.pending_confirmations = 0
            session.short_reason = entry.note
        else:
            if session.pending_label == entry.label:
                session.pending_confirmations += 1
            else:
                session.pending_label = entry.label
                session.pending_confirmations = 1

            if session.pending_confirmations >= required_confirmations:
                session.current_label = entry.label
                session.short_reason = entry.note
                session.label_started_at = entry.timestamp
                session.pending_label = None
                session.pending_confirmations = 0
            else:
                session.short_reason = self._clamp_sentence(f"Double-checking: {entry.note}")

        companion_message, next_nudge_at = self._companion_message(
            label=session.current_label,
            reason=session.short_reason,
            label_started_at=session.label_started_at,
            last_nudge_at=session.last_nudge_at,
            now=entry.timestamp,
        )
        session.companion_message = companion_message
        session.last_nudge_at = next_nudge_at

        extra_events: list[SessionEvent] = []
        if session.current_label != previous_visible_label:
            extra_events.append(
                self._record_event_mutating(
                    session,
                    SessionEventType.LABEL_TRANSITION,
                    sequence=entry.sequence,
                    detail=f"Visible label changed to {session.current_label.value}.",
                    label=session.current_label,
                    timestamp=entry.timestamp,
                )
            )
            if previous_visible_label != FocusLabel.FOCUSED and session.current_label == FocusLabel.FOCUSED:
                extra_events.append(
                    self._record_event_mutating(
                        session,
                        SessionEventType.RECOVERY_DETECTED,
                        sequence=entry.sequence,
                        detail="Recovered back to focus.",
                        label=session.current_label,
                        timestamp=entry.timestamp,
                    )
                )

        if companion_message != previous_companion and (
            companion_message.startswith("Quick reset:") or companion_message.startswith("Tiny reset:")
        ):
            extra_events.append(
                self._record_event_mutating(
                    session,
                    SessionEventType.NUDGE_SENT,
                    sequence=entry.sequence,
                    detail=companion_message,
                    label=session.current_label,
                    timestamp=entry.timestamp,
                )
            )

        return extra_events

    def _refresh_session_analytics_mutating(self, session: SessionRecord) -> None:
        session.metrics = compute_session_metrics(session)
        session.insights = build_session_insights(session)
        session.analytics_version = ANALYTICS_VERSION

    def _refresh_rollups(self) -> None:
        sessions = [session for session in self.store.list() if session.summary.total_reviews > 0]
        if not sessions:
            empty_day, empty_week = build_today_and_week([])
            self.analytics_store.write_day_rollup(empty_day)
            self.analytics_store.write_week_rollup(empty_week)
            self.analytics_store.write_remarkable_index([])
            return

        sessions_by_day: dict[str, list[SessionRecord]] = defaultdict(list)
        sessions_by_week: dict[str, list[SessionRecord]] = defaultdict(list)
        week_reference: dict[str, datetime] = {}
        for session in sessions:
            day_key = session.created_at.astimezone().date().isoformat()
            sessions_by_day[day_key].append(session)
            week_id = f"{session.created_at.astimezone().isocalendar().year}-W{session.created_at.astimezone().isocalendar().week:02d}"
            sessions_by_week[week_id].append(session)
            week_reference.setdefault(week_id, session.created_at)

        for day_key, day_sessions in sessions_by_day.items():
            self.analytics_store.write_day_rollup(build_day_rollup(day_key, day_sessions))

        for week_id, week_sessions in sessions_by_week.items():
            reference = week_reference[week_id]
            self.analytics_store.write_week_rollup(build_week_rollup(reference, week_sessions, sessions))

        self.analytics_store.write_remarkable_index(build_remarkable_index(sessions))

    def _should_queue_review(self, session: SessionRecord, review_input: ReviewInput) -> bool:
        cadence_ms = (
            session.config.active_review_cadence_ms
            if session.current_label in {FocusLabel.DRIFTING, FocusLabel.DISTRACTED}
            else session.config.focused_review_cadence_ms
        )
        now = utcnow()
        with self._job_lock:
            if session.id in self._inflight_sessions:
                return False
            last_request_at = self._last_review_requested_at.get(session.id)
            if review_input.force_review or last_request_at is None:
                self._inflight_sessions.add(session.id)
                self._last_review_requested_at[session.id] = now
                return True
            elapsed_ms = (now - last_request_at).total_seconds() * 1000
            if elapsed_ms >= cadence_ms:
                self._inflight_sessions.add(session.id)
                self._last_review_requested_at[session.id] = now
                return True
            return False

    def _should_capture_keyframe(
        self,
        session: SessionRecord,
        review_input: ReviewInput,
        decision: GemmaDecision,
    ) -> bool:
        if not session.review_history:
            return True
        if decision.label != session.current_label:
            return True
        if decision.label in {FocusLabel.DISTRACTED, FocusLabel.AWAY}:
            return True
        last_keyframe_sequence = next(
            (
                review.sequence
                for review in reversed(session.review_history)
                if review.keyframe_path
            ),
            0,
        )
        if review_input.frame_sequence - last_keyframe_sequence >= session.config.timelapse_capture_interval_reviews:
            return True
        return False

    def _build_summary(self, reviews: list[ReviewEntry]) -> SessionSummary:
        label_counts = {label.value: 0 for label in FocusLabel}
        if not reviews:
            return SessionSummary(label_counts=label_counts)

        label_counter = Counter(review.label.value for review in reviews)
        reason_counter = Counter(reason for review in reviews for reason in review.reasons)
        for label, count in label_counter.items():
            label_counts[label] = count

        focus_ratio = label_counter.get(FocusLabel.FOCUSED.value, 0) / len(reviews)
        distraction_reviews = label_counter.get(FocusLabel.DISTRACTED.value, 0)

        return SessionSummary(
            total_reviews=len(reviews),
            label_counts=label_counts,
            focus_ratio=round(focus_ratio, 3),
            distraction_reviews=distraction_reviews,
            most_common_reason=reason_counter.most_common(1)[0][0] if reason_counter else None,
        )

    def _companion_message(
        self,
        label: FocusLabel,
        reason: str,
        label_started_at: datetime,
        last_nudge_at: datetime | None,
        now: datetime,
    ) -> tuple[str, datetime | None]:
        del reason
        baseline = {
            FocusLabel.FOCUSED: "You’re on track. Keep this stretch simple.",
            FocusLabel.DRIFTING: "Small drift. A quiet reset should do it.",
            FocusLabel.DISTRACTED: "You look pulled away. One reset and come back to one thing.",
            FocusLabel.AWAY: "Looks like you stepped away. Rejoin when you’re ready.",
        }[label]

        dwell_seconds = (now - label_started_at).total_seconds()
        cooldown_ready = last_nudge_at is None or (now - last_nudge_at).total_seconds() >= 90
        if label == FocusLabel.DISTRACTED and dwell_seconds >= 10 and cooldown_ready:
            return "Quick reset: put the distraction down and return to one small step.", now
        if label == FocusLabel.DRIFTING and dwell_seconds >= 20 and cooldown_ready:
            return "Tiny reset: eyes back on the task for the next minute.", now
        return baseline, last_nudge_at

    def _rescan_buddy_line(self, decision: GemmaDecision) -> str:
        if decision.label == FocusLabel.FOCUSED:
            return "Rescan still reads this moment as on track."
        if decision.label == FocusLabel.DRIFTING:
            return "Rescan reads this as a soft drift rather than a full break."
        if decision.label == FocusLabel.DISTRACTED:
            return "Rescan confirms a real distraction signal here."
        return "Rescan reads this moment as away from the task."

    def _cleanup_expired_temporary_sessions(self) -> None:
        now = utcnow()
        for session in self.store.list():
            if session.is_saved or session.temporary_expires_at is None:
                continue
            if session.temporary_expires_at > now:
                continue

            session.rescan_available = False
            session.temporary_expires_at = None
            session.updated_at = now
            session.companion_message = "Temporary keyframes expired. Save future sessions if you want to revisit them."
            self.store.clear_temporary_artifacts(session.id)
            self.store.save(session)

    def _cleanup_expired_raw_evidence(self) -> None:
        retention_delta = timedelta(days=self.preferences.raw_retention_days)
        now = utcnow()
        for session in self.store.list():
            if now - session.updated_at <= retention_delta:
                continue
            if session.remarkable:
                continue

            keep_sequences = {
                moment.sequence
                for moment in session.remarkable_moments
                if not moment.session_level and moment.sequence is not None
            }
            keep_contexts = bool(session.remarkable_moments)
            for review in session.review_history:
                if review.sequence not in keep_sequences:
                    review.keyframe_path = None
            if not keep_contexts:
                session.context_history = []
            self.store.prune_raw_evidence(
                session.id,
                keep_sequences=keep_sequences,
                clear_contexts=not keep_contexts,
            )
            self.store.save(session)

    def _record_event_mutating(
        self,
        session: SessionRecord,
        event_type: SessionEventType,
        *,
        sequence: int | None = None,
        detail: str | None = None,
        label: FocusLabel | None = None,
        metadata: dict[str, object] | None = None,
        timestamp: datetime | None = None,
    ) -> SessionEvent:
        serializable_metadata: dict[str, str | int | float | bool | None] = {}
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    serializable_metadata[key] = value
                else:
                    serializable_metadata[key] = str(value)
        event = SessionEvent(
            timestamp=timestamp or utcnow(),
            type=event_type,
            sequence=sequence,
            detail=detail,
            label=label,
            metadata=serializable_metadata,
        )
        session.event_history.append(event)
        return event

    def _categorize_app_context(self, app_name: str | None, window_title: str | None) -> str | None:
        combined = " ".join(part.lower() for part in (app_name, window_title) if part)
        if not combined:
            return None
        if any(term in combined for term in ("code", "xcode", "terminal", "cursor", "vim", "notion")):
            return "builder"
        if any(term in combined for term in ("youtube", "netflix", "spotify", "music", "vlc")):
            return "media"
        if any(term in combined for term in ("instagram", "x ", "twitter", "discord", "slack", "reddit", "tiktok")):
            return "social"
        if any(term in combined for term in ("chrome", "safari", "arc", "firefox", "edge")):
            return "browser"
        if any(term in combined for term in ("docs", "sheets", "word", "excel", "powerpoint")):
            return "document"
        return "other"

    def _merge_manual_tags(self, existing, incoming):  # noqa: ANN001
        merged = existing.model_copy(deep=True)
        for field_name in ManualTags.model_fields:
            incoming_value = getattr(incoming, field_name)
            if incoming_value is not None and incoming_value != "":
                setattr(merged, field_name, incoming_value)
        return merged

    def _find_review_entry(self, session: SessionRecord, sequence: int) -> ReviewEntry:
        for review in session.review_history:
            if review.sequence == sequence:
                return review
        for review in session.rescan_history:
            if review.sequence == sequence:
                return review
        raise KeyError(sequence)

    def _clamp_sentence(self, text: str) -> str:
        trimmed = " ".join(text.strip().split())
        if len(trimmed) <= 180:
            return trimmed
        return trimmed[:177].rstrip() + "..."

    def _sequence_from_keyframe_name(self, name: str) -> int:
        prefix = name.split("-", 1)[0]
        try:
            return int(prefix)
        except ValueError:
            return 0
