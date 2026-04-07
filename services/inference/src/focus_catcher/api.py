from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .models import (
    RescanResult,
    ReviewInput,
    SessionCreateRequest,
    SessionReviewDetail,
    SessionSnapshot,
    SetupStatus,
    TransitionRequest,
)
from .service import FocusCatcherService


service = FocusCatcherService()
app = FastAPI(title="Focus Buddy", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def healthcheck() -> dict[str, object]:
    setup = service.setup_status()
    return {
        "status": "ok",
        "setup_ready": setup.ready,
        "model_name": setup.model_name,
        "runtime_profile": setup.runtime_profile,
        "available_runtime_profiles": setup.available_runtime_profiles,
        "message": setup.message,
    }


@app.get("/api/setup", response_model=SetupStatus)
def setup_status() -> SetupStatus:
    return service.setup_status()


@app.get("/api/sessions", response_model=list[SessionSnapshot])
def list_sessions() -> list[SessionSnapshot]:
    return service.list_sessions()


@app.post("/api/sessions", response_model=SessionSnapshot)
def create_session(request: SessionCreateRequest) -> SessionSnapshot:
    return service.create_session(request.config)


@app.get("/api/sessions/{session_id}", response_model=SessionSnapshot)
def get_session(session_id: str) -> SessionSnapshot:
    try:
        return service.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.get("/api/sessions/{session_id}/review", response_model=SessionReviewDetail)
def get_session_review(session_id: str) -> SessionReviewDetail:
    try:
        return service.get_session_review(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.get("/api/sessions/{session_id}/keyframes/{filename}")
def get_session_keyframe(session_id: str, filename: str) -> FileResponse:
    try:
        session = service.store.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc

    safe_name = Path(filename).name
    keyframe_path = Path(session.artifacts.keyframes_dir) / safe_name
    if not keyframe_path.exists() or not keyframe_path.is_file():
        raise HTTPException(status_code=404, detail="keyframe not found")

    return FileResponse(keyframe_path, media_type="image/jpeg")


@app.post("/api/sessions/{session_id}/start", response_model=SessionSnapshot)
def start_session(session_id: str, request: TransitionRequest) -> SessionSnapshot:
    try:
        return service.start_session(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/pause", response_model=SessionSnapshot)
def pause_session(session_id: str, request: TransitionRequest) -> SessionSnapshot:
    try:
        return service.pause_session(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.post("/api/sessions/{session_id}/stop", response_model=SessionSnapshot)
def stop_session(session_id: str, request: TransitionRequest) -> SessionSnapshot:
    try:
        return service.stop_session(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.post("/api/sessions/{session_id}/review", response_model=SessionSnapshot)
def submit_review(session_id: str, review_input: ReviewInput) -> SessionSnapshot:
    try:
        return service.submit_review(session_id, review_input)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/save", response_model=SessionSnapshot)
def save_session(session_id: str) -> SessionSnapshot:
    try:
        return service.save_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.post("/api/sessions/{session_id}/rescan", response_model=RescanResult)
def rescan_session(session_id: str) -> RescanResult:
    try:
        return service.rescan_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
