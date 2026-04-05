from __future__ import annotations

import base64
import json
from pathlib import Path
from threading import RLock

from .models import ReviewEntry, ReviewMode, SessionArtifacts, SessionRecord, SessionSummary


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
        )
        Path(artifacts.reviews_file).touch(exist_ok=True)
        Path(artifacts.rescan_file).touch(exist_ok=True)
        Path(artifacts.summary_file).touch(exist_ok=True)
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

    def load_existing(self) -> None:
        with self._lock:
            for session_dir in self.base_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                session_file = session_dir / "session.json"
                if not session_file.exists():
                    continue
                payload = json.loads(session_file.read_text(encoding="utf-8"))
                session = SessionRecord.model_validate(payload)
                self._sessions[session.id] = session

    def _strip_data_url(self, payload: str) -> str:
        if "," in payload and payload.startswith("data:"):
            return payload.split(",", 1)[1]
        return payload
