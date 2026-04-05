# Focus Buddy

`Focus Buddy` is a macOS-first personal accountability companion that runs locally and uses `Gemma 4 E2B` through Ollama to review your camera feed during a focus session.

The current repo includes:

- `apps/desktop`: Electron + React sidecar app with camera setup, live buddy state, rolling review log, session save, and session rescan.
- `services/inference`: FastAPI + Python 3.13 local service that manages session state, sends frames to local `gemma4:e2b`, writes `reviews.ndjson`, saves keyframes, and runs slower rescans.
- `apps/android`: an older Android scaffold that is not part of the current v1 consumer flow.

## Quick start

1. Install JS dependencies:

```bash
pnpm install
```

2. Install Python dependencies:

```bash
cd services/inference
uv sync
```

3. Start the inference service:

```bash
cd services/inference
uv run uvicorn focus_catcher.api:app --app-dir src --reload --port 8000
```

4. In another terminal, start the desktop app:

```bash
cd apps/desktop
pnpm dev
```

## Verification

- Python tests:

```bash
pnpm inference:test
```

- Desktop typecheck/build:

```bash
pnpm desktop:build
```

## Gemma 4 E2B

The service is intentionally strict now: it expects a running local Ollama instance with `gemma4:e2b` available. It does not silently present mock reviews as real sessions.

Optional environment variables:

```bash
export FOCUS_CATCHER_GEMMA_BACKEND=ollama
export FOCUS_CATCHER_GEMMA_MODEL=gemma4:e2b
export FOCUS_CATCHER_OLLAMA_URL=http://127.0.0.1:11434
export FOCUS_CATCHER_OLLAMA_TIMEOUT_SEC=45
export FOCUS_CATCHER_OLLAMA_KEEP_ALIVE=10m
```

- `mock`: skip Ollama completely
- `ollama`: require Ollama explicitly

## Notes

- Default mode is camera-only. Screen analysis is opt-in per session.
- Live reviews are appended to `reviews.ndjson` as the session runs, and keyframes are only written on first review, label change, or stronger distraction states.
- `Rescan session` rereads saved keyframes and writes a separate `rescan.ndjson` plus `summary.json`.
- Temporary keyframes are deleted after an unsaved session’s review window expires.
