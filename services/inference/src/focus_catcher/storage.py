from __future__ import annotations

import base64
import json
from pathlib import Path
from threading import RLock

from .models import (
    AnalyticsPreferences,
    ContextSnapshot,
    DayRollup,
    InsightCard,
    RemarkableIndexEntry,
    ReviewEntry,
    ReviewMode,
    SessionArtifacts,
    SessionEvent,
    SessionMetrics,
    SessionRecord,
    SessionSummary,
    WeekRollup,
)


class SessionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = RLock()

    def create_artifacts(self, session_id: str) -> SessionArtifacts:
        session_dir = self.base_dir / session_id
        keyframes_dir = session_dir / "keyframes"
        session_dir.mkdir(parents=True, exist_ok=True)
        keyframes_dir.mkdir(parents=True, exist_ok=True)

        artifacts = SessionArtifacts(
            session_dir=str(session_dir),
            session_file=str(session_dir / "session.json"),
            reviews_file=str(session_dir / "reviews.ndjson"),
            keyframes_dir=str(keyframes_dir),
            rescan_file=str(session_dir / "rescan.ndjson"),
            summary_file=str(session_dir / "summary.json"),
            events_file=str(session_dir / "events.ndjson"),
            contexts_file=str(session_dir / "contexts.ndjson"),
            metrics_file=str(session_dir / "metrics.json"),
            insights_file=str(session_dir / "insights.json"),
        )
        for path in (
            artifacts.reviews_file,
            artifacts.rescan_file,
            artifacts.summary_file,
            artifacts.events_file,
            artifacts.contexts_file,
            artifacts.metrics_file,
            artifacts.insights_file,
        ):
            Path(path).touch(exist_ok=True)
        return artifacts

    def list(self) -> list[SessionRecord]:
        with self._lock:
            return sorted(
                (session.model_copy(deep=True) for session in self._sessions.values()),
                key=lambda session: session.created_at,
                reverse=True,
            )

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            return self._sessions[session_id].model_copy(deep=True)

    def save(self, session: SessionRecord) -> SessionRecord:
        with self._lock:
            stored = session.model_copy(deep=True)
            self._sessions[stored.id] = stored
            Path(stored.artifacts.session_file).write_text(
                stored.model_dump_json(indent=2),
                encoding="utf-8",
            )
            return stored.model_copy(deep=True)

    def append_review(self, session_id: str, review: ReviewEntry) -> None:
        session = self.get(session_id)
        path = Path(
            session.artifacts.reviews_file if review.mode == ReviewMode.LIVE else session.artifacts.rescan_file
        )
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(review.model_dump_json())
                handle.write("\n")

    def append_event(self, session_id: str, event: SessionEvent) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.events_file)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json())
                handle.write("\n")

    def append_context(self, session_id: str, context: ContextSnapshot) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.contexts_file)
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(context.model_dump_json())
                handle.write("\n")

    def replace_rescan(self, session_id: str, entries: list[ReviewEntry]) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.rescan_file)
        with self._lock:
            payload = "\n".join(entry.model_dump_json() for entry in entries)
            if payload:
                payload += "\n"
            path.write_text(payload, encoding="utf-8")

    def write_summary(self, session_id: str, summary: SessionSummary) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.summary_file)
        with self._lock:
            path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    def write_metrics(self, session_id: str, metrics: SessionMetrics) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.metrics_file)
        with self._lock:
            path.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")

    def write_insights(self, session_id: str, insights: list[InsightCard]) -> None:
        session = self.get(session_id)
        path = Path(session.artifacts.insights_file)
        with self._lock:
            payload = [card.model_dump(mode="json") for card in insights]
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_keyframe(
        self,
        session_id: str,
        sequence: int,
        label: str,
        image_b64: str,
    ) -> str:
        session = self.get(session_id)
        payload = self._strip_data_url(image_b64)
        path = Path(session.artifacts.keyframes_dir) / f"{sequence:06d}-{label}.jpg"
        with self._lock:
            path.write_bytes(base64.b64decode(payload))
        return str(path)

    def clear_temporary_artifacts(self, session_id: str) -> None:
        session = self.get(session_id)
        keyframes_dir = Path(session.artifacts.keyframes_dir)
        with self._lock:
            for entry in keyframes_dir.glob("*"):
                entry.unlink(missing_ok=True)
            Path(session.artifacts.rescan_file).write_text("", encoding="utf-8")
            Path(session.artifacts.contexts_file).write_text("", encoding="utf-8")

    def prune_raw_evidence(
        self,
        session_id: str,
        *,
        keep_sequences: set[int],
        clear_contexts: bool,
    ) -> None:
        session = self.get(session_id)
        keyframes_dir = Path(session.artifacts.keyframes_dir)
        with self._lock:
            for keyframe in keyframes_dir.glob("*.jpg"):
                prefix = keyframe.name.split("-", 1)[0]
                try:
                    sequence = int(prefix)
                except ValueError:
                    sequence = -1
                if sequence not in keep_sequences:
                    keyframe.unlink(missing_ok=True)
            if clear_contexts:
                Path(session.artifacts.contexts_file).write_text("", encoding="utf-8")

    def load_existing(self) -> None:
        with self._lock:
            for session_dir in self.base_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                session_file = session_dir / "session.json"
                if not session_file.exists():
                    continue
                payload = json.loads(session_file.read_text(encoding="utf-8"))
                artifacts = payload.setdefault("artifacts", {})
                artifacts.setdefault("events_file", str(session_dir / "events.ndjson"))
                artifacts.setdefault("contexts_file", str(session_dir / "contexts.ndjson"))
                artifacts.setdefault("metrics_file", str(session_dir / "metrics.json"))
                artifacts.setdefault("insights_file", str(session_dir / "insights.json"))
                for path_key in ("events_file", "contexts_file", "metrics_file", "insights_file"):
                    Path(artifacts[path_key]).touch(exist_ok=True)
                session = SessionRecord.model_validate(payload)
                self._sessions[session.id] = session

    def _strip_data_url(self, payload: str) -> str:
        if "," in payload and payload.startswith("data:"):
            return payload.split(",", 1)[1]
        return payload


class AnalyticsStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.days_dir = self.base_dir / "days"
        self.weeks_dir = self.base_dir / "weeks"
        self.preferences_path = self.base_dir / "preferences.json"
        self.remarkable_index_path = self.base_dir / "remarkable-index.json"
        self._lock = RLock()

        self.days_dir.mkdir(parents=True, exist_ok=True)
        self.weeks_dir.mkdir(parents=True, exist_ok=True)

    def load_preferences(self) -> AnalyticsPreferences:
        with self._lock:
            if not self.preferences_path.exists():
                preferences = AnalyticsPreferences()
                self.save_preferences(preferences)
                return preferences
            payload = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            return AnalyticsPreferences.model_validate(payload)

    def save_preferences(self, preferences: AnalyticsPreferences) -> AnalyticsPreferences:
        with self._lock:
            stored = preferences.model_copy(deep=True)
            self.preferences_path.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
            return stored

    def write_day_rollup(self, rollup: DayRollup) -> None:
        with self._lock:
            path = self.days_dir / f"{rollup.date}.json"
            path.write_text(rollup.model_dump_json(indent=2), encoding="utf-8")

    def write_week_rollup(self, rollup: WeekRollup) -> None:
        with self._lock:
            path = self.weeks_dir / f"{rollup.week_id}.json"
            path.write_text(rollup.model_dump_json(indent=2), encoding="utf-8")

    def write_remarkable_index(self, entries: list[RemarkableIndexEntry]) -> None:
        with self._lock:
            payload = [entry.model_dump(mode="json") for entry in entries]
            self.remarkable_index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
