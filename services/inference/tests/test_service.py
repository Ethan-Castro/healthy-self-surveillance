import base64
import json
import time
from datetime import timedelta
from pathlib import Path

import pytest

from focus_catcher.models import (
    FocusLabel,
    GemmaDecision,
    ReviewInput,
    SessionConfig,
    SetupStatus,
    TransitionRequest,
    utcnow,
)
from focus_catcher.service import FocusCatcherService


def frame_payload(data: bytes = b"fake-jpeg") -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")


def decision(label: FocusLabel, note: str, reasons: list[str] | None = None) -> GemmaDecision:
    return GemmaDecision(
        label=label,
        confidence=0.84,
        reasons=reasons or [],
        note=note,
    )


class SequenceGemmaAdapter:
    def __init__(
        self,
        live_decisions: list[GemmaDecision],
        *,
        rescan_decision: GemmaDecision | None = None,
        ready: bool = True,
        delay_sec: float = 0.0,
    ) -> None:
        self.live_decisions = live_decisions
        self.rescan_decision = rescan_decision or decision(
            FocusLabel.FOCUSED,
            "The saved frame still looks on task.",
        )
        self.ready = ready
        self.delay_sec = delay_sec
        self.live_calls = 0
        self.rescan_calls = 0

    def check_setup(self) -> SetupStatus:
        return SetupStatus(
            ready=self.ready,
            model_name="gemma4:e2b",
            mode="test",
            message="ready" if self.ready else "gemma unavailable",
        )

    def review_live(self, review_input, config, recent_reviews, current_label):  # noqa: ANN001
        del review_input, config, recent_reviews, current_label
        self.live_calls += 1
        if self.delay_sec:
            time.sleep(self.delay_sec)
        index = min(self.live_calls - 1, len(self.live_decisions) - 1)
        return self.live_decisions[index]

    def review_rescan(self, image_b64, config, live_reviews):  # noqa: ANN001
        del image_b64, config, live_reviews
        self.rescan_calls += 1
        return self.rescan_decision


def wait_for_reviews(service: FocusCatcherService, session_id: str, count: int):
    deadline = time.time() + 3
    while time.time() < deadline:
        snapshot = service.get_session(session_id)
        if snapshot.summary.total_reviews >= count:
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {count} reviews")


def read_lines(path: str) -> list[str]:
    payload = Path(path).read_text(encoding="utf-8").strip()
    if not payload:
        return []
    return payload.splitlines()


def test_start_requires_ready_setup_and_recovers(tmp_path) -> None:
    adapter = SequenceGemmaAdapter([decision(FocusLabel.FOCUSED, "You look settled.")], ready=False)
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())

        with pytest.raises(ValueError, match="gemma unavailable"):
            service.start_session(session.session_id, TransitionRequest())

        adapter.ready = True
        started = service.start_session(session.session_id, TransitionRequest())
        assert started.status.value == "running"
    finally:
        service._executor.shutdown(wait=True)


def test_live_reviews_append_logs_and_confirm_drifting_transition(tmp_path) -> None:
    adapter = SequenceGemmaAdapter(
        [
            decision(FocusLabel.DRIFTING, "Your attention looks a little loose.", ["looking_away"]),
            decision(FocusLabel.DRIFTING, "Your attention still looks loose.", ["looking_away"]),
        ]
    )
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())
        service.start_session(session.session_id, TransitionRequest())

        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=1, camera_image_b64=frame_payload(), force_review=True),
        )
        first = wait_for_reviews(service, session.session_id, 1)
        assert first.current_label == FocusLabel.FOCUSED
        assert first.short_reason.startswith("Double-checking:")

        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=2, camera_image_b64=frame_payload(b"frame-2"), force_review=True),
        )
        second = wait_for_reviews(service, session.session_id, 2)
        assert second.current_label == FocusLabel.DRIFTING
        assert second.summary.total_reviews == 2
        assert second.summary.label_counts["drifting"] == 2

        record = service.store.get(session.session_id)
        assert len(read_lines(record.artifacts.reviews_file)) == 2
        assert len(list(Path(record.artifacts.keyframes_dir).glob("*.jpg"))) >= 2
    finally:
        service._executor.shutdown(wait=True)


def test_only_one_live_review_runs_at_a_time(tmp_path) -> None:
    adapter = SequenceGemmaAdapter(
        [decision(FocusLabel.FOCUSED, "You look settled.")],
        delay_sec=0.2,
    )
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())
        service.start_session(session.session_id, TransitionRequest())

        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=1, camera_image_b64=frame_payload(), force_review=True),
        )
        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=2, camera_image_b64=frame_payload(b"next"), force_review=True),
        )

        wait_for_reviews(service, session.session_id, 1)
        assert adapter.live_calls == 1
    finally:
        service._executor.shutdown(wait=True)


def test_pause_blocks_reviews_until_resumed(tmp_path) -> None:
    adapter = SequenceGemmaAdapter([decision(FocusLabel.FOCUSED, "You look settled.")])
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())
        service.start_session(session.session_id, TransitionRequest())
        service.pause_session(session.session_id, TransitionRequest())

        with pytest.raises(ValueError, match="session is not running"):
            service.submit_review(
                session.session_id,
                ReviewInput(frame_sequence=1, camera_image_b64=frame_payload(), force_review=True),
            )

        service.start_session(session.session_id, TransitionRequest())
        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=2, camera_image_b64=frame_payload(b"resume"), force_review=True),
        )
        resumed = wait_for_reviews(service, session.session_id, 1)
        assert resumed.summary.total_reviews == 1
    finally:
        service._executor.shutdown(wait=True)


def test_unsaved_session_keyframes_expire_after_review_window(tmp_path) -> None:
    adapter = SequenceGemmaAdapter(
        [decision(FocusLabel.DISTRACTED, "A clear distraction is visible.", ["phone_visible"])]
    )
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())
        service.start_session(session.session_id, TransitionRequest())
        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=1, camera_image_b64=frame_payload(), force_review=True),
        )
        wait_for_reviews(service, session.session_id, 1)

        stopped = service.stop_session(session.session_id, TransitionRequest())
        assert stopped.can_rescan is True
        assert stopped.temporary_expires_at is not None

        record = service.store.get(session.session_id)
        record.temporary_expires_at = utcnow() - timedelta(seconds=1)
        service.store.save(record)
        service._cleanup_expired_temporary_sessions()

        expired = service.get_session(session.session_id)
        assert expired.can_rescan is False
        assert list(Path(record.artifacts.keyframes_dir).glob("*.jpg")) == []
    finally:
        service._executor.shutdown(wait=True)


def test_save_and_rescan_write_separate_artifacts(tmp_path) -> None:
    adapter = SequenceGemmaAdapter(
        [decision(FocusLabel.DISTRACTED, "You look pulled away.", ["phone_visible"])],
        rescan_decision=decision(FocusLabel.FOCUSED, "This saved frame looks steady."),
    )
    service = FocusCatcherService(data_root=tmp_path, gemma_adapter=adapter)
    try:
        session = service.create_session(SessionConfig())
        service.start_session(session.session_id, TransitionRequest())
        service.submit_review(
            session.session_id,
            ReviewInput(frame_sequence=1, camera_image_b64=frame_payload(), force_review=True),
        )
        wait_for_reviews(service, session.session_id, 1)
        service.stop_session(session.session_id, TransitionRequest())

        saved = service.save_session(session.session_id)
        assert saved.is_saved is True
        assert saved.temporary_expires_at is None

        result = service.rescan_session(session.session_id)
        record = service.store.get(session.session_id)

        live_lines = read_lines(record.artifacts.reviews_file)
        rescan_lines = read_lines(record.artifacts.rescan_file)
        parsed_rescan = [json.loads(line) for line in rescan_lines]

        assert len(live_lines) == 1
        assert len(parsed_rescan) == len(result.revised_timeline) == 1
        assert adapter.rescan_calls == 1
        assert result.persisted is True
        assert result.revised_summary.total_reviews == 1
    finally:
        service._executor.shutdown(wait=True)
