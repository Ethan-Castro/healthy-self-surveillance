from __future__ import annotations

import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .adapters import GemmaAdapter, build_gemma_adapter
from .models import (
    FocusLabel,
    GemmaDecision,
    GemmaReviewStatus,
    RescanResult,
    ReviewEntry,
    ReviewInput,
    ReviewMode,
    SessionConfig,
    SessionRecord,
    SessionSnapshot,
    SessionStatus,
    SessionSummary,
    SetupStatus,
    TransitionRequest,
    utcnow,
)
from .storage import SessionStore


SERVICE_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = SERVICE_ROOT / "data"


class FocusCatcherService:
    def __init__(
        self,
        data_root: Path = DATA_ROOT,
        gemma_adapter: GemmaAdapter | None = None,
    ) -> None:
        self.store = SessionStore(data_root / "sessions")
        self.store.load_existing()
        self.gemma_adapter = gemma_adapter or build_gemma_adapter()
        self._state_lock = Lock()
        self._job_lock = Lock()
        self._inflight_sessions: set[str] = set()
        self._last_review_requested_at: dict[str, object] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="focus-buddy")
        self._cleanup_expired_temporary_sessions()

    def setup_status(self) -> SetupStatus:
        self._cleanup_expired_temporary_sessions()
        return self.gemma_adapter.check_setup()

    def list_sessions(self) -> list[SessionSnapshot]:
        self._cleanup_expired_temporary_sessions()
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
            companion_message="I’ll be a gentle accountability buddy while you work.",
        )
        session.summary = self._build_summary(session.review_history)
        self.store.save(session)
        self.store.write_summary(session.id, session.summary)
        return session.to_snapshot()

    def get_session(self, session_id: str) -> SessionSnapshot:
        self._cleanup_expired_temporary_sessions()
        return self.store.get(session_id).to_snapshot()

    def start_session(self, session_id: str, request: TransitionRequest) -> SessionSnapshot:
        setup = self.setup_status()
        if not setup.ready:
            raise ValueError(setup.message)

        with self._state_lock:
            session = self.store.get(session_id)
            session.status = SessionStatus.RUNNING
            session.review_status = GemmaReviewStatus.IDLE
            session.short_reason = "Live reviews begin with the next frame."
            session.companion_message = "You’re live. Keep the next few minutes simple and I’ll keep watch."
            session.temporary_expires_at = None
            session.updated_at = request.timestamp
            self.store.save(session)
            return session.to_snapshot()

    def pause_session(self, session_id: str, request: TransitionRequest) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.status = SessionStatus.PAUSED
            session.review_status = GemmaReviewStatus.IDLE
            session.short_reason = "Session paused."
            session.companion_message = "Paused. Take a breath and resume when you want."
            session.updated_at = request.timestamp
            self.store.save(session)
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
            self.store.save(session)
            self.store.write_summary(session.id, session.summary)
            return session.to_snapshot()

    def submit_review(self, session_id: str, review_input: ReviewInput) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            if session.status != SessionStatus.RUNNING:
                raise ValueError("session is not running")

            session.updated_at = utcnow()
            self.store.save(session)

        if not review_input.camera_image_b64:
            return self.store.get(session_id).to_snapshot()

        if not self._should_queue_review(self.store.get(session_id), review_input):
            return self.store.get(session_id).to_snapshot()

        with self._state_lock:
            session = self.store.get(session_id)
            session.review_status = GemmaReviewStatus.REVIEWING
            self.store.save(session)

        self._executor.submit(self._run_live_review, session_id, review_input)
        return self.store.get(session_id).to_snapshot()

    def save_session(self, session_id: str) -> SessionSnapshot:
        with self._state_lock:
            session = self.store.get(session_id)
            session.is_saved = True
            session.temporary_expires_at = None
            session.companion_message = "Saved locally. You can revisit or rescan this session later."
            session.summary = self._build_summary(session.review_history)
            self.store.save(session)
            self.store.write_summary(session.id, session.summary)
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
            self.store.save(session)
            self.store.replace_rescan(session.id, timeline)
            self.store.write_summary(session.id, revised_summary)

        return RescanResult(
            session_id=session_id,
            revised_summary=revised_summary,
            revised_timeline=timeline,
            artifact_paths=self.store.get(session_id).artifacts,
            persisted=self.store.get(session_id).is_saved,
        )

    def _run_live_review(self, session_id: str, review_input: ReviewInput) -> None:
        try:
            session = self.store.get(session_id)
            decision = self.gemma_adapter.review_live(
                review_input=review_input,
                config=session.config,
                recent_reviews=session.review_history,
                current_label=session.current_label.value,
            )
            self._apply_live_decision(session_id, review_input, decision)
        except Exception as exc:  # pragma: no cover - runtime path
            with self._state_lock:
                session = self.store.get(session_id)
                session.review_status = GemmaReviewStatus.ERROR
                session.short_reason = "I missed that check."
                session.companion_message = "I lost the thread for a second. I’ll try again on the next review."
                session.updated_at = utcnow()
                self.store.save(session)
        finally:
            with self._job_lock:
                self._inflight_sessions.discard(session_id)

    def _apply_live_decision(self, session_id: str, review_input: ReviewInput, decision: GemmaDecision) -> None:
        with self._state_lock:
            session = self.store.get(session_id)
            if session.status != SessionStatus.RUNNING:
                return

            keyframe_path = None
            if self._should_capture_keyframe(session, decision) and review_input.camera_image_b64:
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
            )

            self._update_visible_state(session, entry)
            entry.buddy_note = session.companion_message
            session.review_history.append(entry)
            session.last_review_at = entry.timestamp
            session.last_review_sequence = review_input.frame_sequence
            session.review_status = GemmaReviewStatus.READY
            session.summary = self._build_summary(session.review_history)
            session.updated_at = entry.timestamp

            self.store.save(session)
            self.store.append_review(session.id, entry)
            self.store.write_summary(session.id, session.summary)

    def _update_visible_state(self, session: SessionRecord, entry: ReviewEntry) -> None:
        required_confirmations = 1 if entry.label == FocusLabel.AWAY else 2

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

    def _should_capture_keyframe(self, session: SessionRecord, decision: GemmaDecision) -> bool:
        if not session.review_history:
            return True
        if decision.label != session.current_label:
            return True
        if decision.label in {FocusLabel.DISTRACTED, FocusLabel.AWAY}:
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

    def _clamp_sentence(self, text: str) -> str:
        trimmed = " ".join(text.strip().split())
        if len(trimmed) <= 140:
            return trimmed
        return trimmed[:137].rstrip() + "..."

    def _sequence_from_keyframe_name(self, name: str) -> int:
        prefix = name.split("-", 1)[0]
        try:
            return int(prefix)
        except ValueError:
            return 0
