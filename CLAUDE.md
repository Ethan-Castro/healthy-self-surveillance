# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Focus Buddy — a macOS-first local accountability companion that uses Gemma 4 E2B (via Ollama) to review camera feeds during focus sessions. Everything runs locally; there are no cloud dependencies for the core monitoring flow.

## Monorepo Layout

- **`apps/desktop`** — Electron + React (TypeScript, Vite). The renderer talks to the inference service over HTTP; Electron's main process proxies API calls via IPC (`desktopShell.apiRequest`). A floating "bubble" orb window shows the current label.
- **`services/inference`** — Python 3.13 FastAPI service. Manages session state, sends frames to Ollama, writes review data to disk, and runs session rescans.
- **`apps/android`** — Inactive scaffold, not part of the current v1 flow.

Package manager: **pnpm** (workspaces in `apps/*`). Python tooling: **uv**.

## Build & Dev Commands

```bash
# Install all JS deps
pnpm install

# Install Python deps
cd services/inference && uv sync

# Run both services concurrently
pnpm dev

# Desktop only
pnpm desktop:dev

# Inference service only
pnpm inference:dev

# Python tests
pnpm inference:test
# Single test file
cd services/inference && uv run pytest tests/test_service.py
# Single test by name
cd services/inference && uv run pytest tests/test_service.py -k "test_name"

# Desktop typecheck
pnpm desktop:typecheck

# Desktop production build
pnpm desktop:build

# Internal model benchmark (requires JSONL dataset + Ollama)
pnpm inference:benchmark -- /path/to/focus-benchmark.jsonl
```

## Architecture

### Inference service (`services/inference/src/focus_catcher/`)

- **`api.py`** — FastAPI routes. Singleton `FocusCatcherService` at module level. CORS allows the Vite dev server origin.
- **`service.py`** — Core business logic. Session lifecycle (create → start → pause → stop → save → rescan). Live reviews run in a `ThreadPoolExecutor`. Label transitions use a confirmation counter (1 for "away", 2 for other changes) before the visible label updates.
- **`models.py`** — All Pydantic models. `SessionRecord` is the full internal state; `SessionSnapshot` is the API-facing projection (produced via `to_snapshot()`). Key enums: `FocusLabel`, `SessionStatus`, `GemmaReviewStatus`, `RuntimeProfile`, `AnalysisMode`.
- **`adapters.py`** — `GemmaAdapter` protocol with two implementations: `OllamaGemmaAdapter` (real Ollama calls) and `MockGemmaAdapter` (deterministic, for tests/dev). Built by `build_gemma_adapter()` based on `FOCUS_CATCHER_GEMMA_BACKEND` env var (`ollama` or `mock`).
- **`storage.py`** — `SessionStore` persists sessions to disk as `session.json` + `reviews.ndjson` + `keyframes/` + `rescan.ndjson` + `summary.json` under `services/inference/data/sessions/<session_id>/`.
- **`benchmark.py`** — CLI harness for comparing models against a JSONL dataset.

### Desktop app (`apps/desktop/`)

- **`electron/main.mjs`** — Main process. Creates the main window and an always-on-top transparent bubble window. IPC handlers: `focus-buddy:api-request`, `focus-buddy:toggle-bubble`, `focus-buddy:notify`, `focus-buddy:debug-log`.
- **`electron/preload.mjs`** — Exposes `window.desktopShell` to the renderer (API proxy, bubble toggle, notifications, debug logging).
- **`src/App.tsx`** — Single-page React app with all session UI. Polls the session at 250ms intervals when running; captures camera frames via canvas, computes a pixel-signature delta to trigger early reviews on motion.
- **`src/api.ts`** — Typed HTTP client. Routes through `desktopShell.apiRequest` when in Electron, falls back to direct `fetch` in browser.
- **`src/types.ts`** — TypeScript interfaces mirroring the Python Pydantic models.
- **`src/ReviewOverlay.tsx`** — Time-lapse and cinematic-snippet playback overlay.

### Communication flow

Renderer → (IPC) → Electron main → (HTTP) → FastAPI → Ollama → Gemma model. The renderer sends base64 JPEG frames; the service returns a `SessionSnapshot` with the current label and companion message.

## Conventions

- **Local-first**: no cloud services in the core flow. Ollama must be running with `gemma4:e2b` available.
- **Mock mode**: set `FOCUS_CATCHER_GEMMA_BACKEND=mock` to skip Ollama entirely (useful for UI development and tests).
- **Runtime profiles**: `standard` (gemma4:e2b), `higher_accuracy` (gemma4:e4b), and `edge` (LFM2.5-VL-450M via `hf.co/LiquidAI/LFM2.5-VL-450M-GGUF:Q4_0`). The desktop app exposes a model dropdown in the setup card. The edge model name is configurable via `FOCUS_CATCHER_EDGE_MODEL` env var.
- **Analysis modes**: `annotation` (Gemma writes descriptive notes) and `classification` (binary focused/unfocused with deterministic copy).
- **Session data** is stored under `services/inference/data/` (gitignored). Temporary keyframes auto-expire if the session is not saved.
- Tests use `MockGemmaAdapter` — no Ollama required to run the test suite.
