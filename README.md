# Focus Buddy

`Focus Buddy` is a macOS-first personal accountability companion that runs locally and uses `Gemma 4 E2B` through Ollama to review your camera feed during a focus session.

Model strategy in the current repo:

- shipped default: `Gemma 4 E2B`
- optional higher-accuracy profile: `Gemma 4 E4B`
- internal benchmark track only: `Qwen 3.5 0.8B` and `Qwen 3.5 2B`
- `Unsloth` is not a runtime dependency; it is only a tooling path for later quantization or fine-tuning work

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

The service is intentionally strict now: it expects a running local Ollama instance with `gemma4:e2b` available. It does not silently present mock reviews as real sessions. Internally, the runtime supports a generic `standard` profile for `gemma4:e2b` and a `higher_accuracy` profile for `gemma4:e4b`, but the desktop app keeps the user-facing story simple and Gemma-first.

Optional environment variables:

```bash
export FOCUS_CATCHER_GEMMA_BACKEND=ollama
export FOCUS_CATCHER_GEMMA_MODEL=gemma4:e2b
export FOCUS_CATCHER_GEMMA_HIGHER_ACCURACY_MODEL=gemma4:e4b
export FOCUS_CATCHER_DEFAULT_RUNTIME_PROFILE=standard
export FOCUS_CATCHER_OLLAMA_URL=http://127.0.0.1:11434
export FOCUS_CATCHER_OLLAMA_TIMEOUT_SEC=45
export FOCUS_CATCHER_OLLAMA_KEEP_ALIVE=10m
```

- `mock`: skip Ollama completely
- `ollama`: require Ollama explicitly

## Internal model benchmarking

`Qwen 3.5` stays in this repo only as an evaluation track for now. The desktop app does not expose raw model-family selection.

Run the internal benchmark harness against a private JSONL dataset of keyframes:

```bash
pnpm inference:benchmark -- /absolute/path/to/focus-benchmark.jsonl
```

Example dataset row:

```json
{"id":"focus-001","camera_path":"images/focus-001.jpg","screen_path":"images/focus-001-screen.jpg","expected_label":"focused"}
```

You can override the benchmarked models:

```bash
pnpm inference:benchmark -- /absolute/path/to/focus-benchmark.jsonl --model gemma4:e2b --model gemma4:e4b --model qwen3.5:0.8b --model qwen3.5:2b
```

## Notes

- Default mode is camera-only. Screen analysis is opt-in per session.
- Live reviews are appended to `reviews.ndjson` as the session runs, and keyframes are only written on first review, label change, or stronger distraction states.
- After the fact, sessions are reviewed through saved keyframes, timeline entries, and rescans. Full continuous video is not recorded.
- `Rescan session` rereads saved keyframes and writes a separate `rescan.ndjson` plus `summary.json`.
- Temporary keyframes are deleted after an unsaved session’s review window expires.
