# Project Overview: Focus Buddy (healthy-self-surveillance)

Focus Buddy is a local-first, privacy-focused personal accountability companion. It uses local AI models (Gemma 4 E2B via Ollama) to monitor a user's focus session by analyzing camera feeds and optionally screen captures. The project is designed as a monorepo consisting of a desktop application and an inference service.

## Architecture

- **`apps/desktop`**: An Electron + React (TypeScript) sidecar app. It handles local media permissions, camera previews, session controls, and displays a rolling review log.
- **`services/inference`**: A Python 3.13 FastAPI service that manages session state, orchestrates AI reviews via Ollama, writes review data (`reviews.ndjson`), saves keyframes, and performs session rescans.
- **`apps/android`**: An older, inactive scaffold (not part of the current v1 consumer flow).

## Technology Stack

- **Monorepo Management**: `pnpm` workspaces.
- **Desktop App**: Electron, React, TypeScript, Vite.
- **Inference Service**: Python 3.13, FastAPI, `uv` for dependency management.
- **AI Backend**: Local [Ollama](https://ollama.com/) instance.
- **Primary Model**: `gemma4:e2b` (shipped default).
- **Secondary Model**: `gemma4:e4b` (higher-accuracy profile).
- **Benchmarking Models**: `qwen3.5:0.8b` and `qwen3.5:2b` (internal tracks only).

## Building and Running

### Prerequisites
- [Ollama](https://ollama.com/) installed and running locally.
- Pull the default model: `ollama pull gemma4:e2b`.
- Node.js and `pnpm` installed.
- Python 3.13 and `uv` installed.

### Initial Setup
1. **Install JS dependencies**:
   ```bash
   pnpm install
   ```
2. **Install Python dependencies**:
   ```bash
   cd services/inference
   uv sync
   ```

### Development Commands
- **Start All (Concurrent)**:
  ```bash
  pnpm dev
  ```
- **Desktop App Only**:
  ```bash
  pnpm desktop:dev
  ```
- **Inference Service Only**:
  ```bash
  pnpm inference:dev
  ```
- **Run Python Tests**:
  ```bash
  pnpm inference:test
  ```
- **Build Desktop App**:
  ```bash
  pnpm desktop:build
  ```

### Internal Benchmarking
To run the internal model benchmark harness:
```bash
pnpm inference:benchmark -- /path/to/benchmark.jsonl
```

## Development Conventions

- **Local-First**: Always prioritize local execution. Do not introduce cloud dependencies for the core monitoring flow.
- **Model Usage**: Stick to `gemma4:e2b` for the consumer flow. Internal research on other models should remain in the benchmarking track.
- **Data Persistence**: Sessions are stored with the following artifacts:
  - `session.json`: Session metadata.
  - `reviews.ndjson`: Live review appends.
  - `keyframes/`: Images captured during label changes or distractions.
  - `rescan.ndjson` / `summary.json`: Results from session rescans.
- **Python Tooling**: Use `uv` for all Python dependency and environment management.
- **Strict Inference**: The service expects a running Ollama instance and will not mock reviews by default unless configured.

## Optional Environment Variables

The inference service can be configured via environment variables (see `README.md` for full list):
- `FOCUS_CATCHER_GEMMA_BACKEND`: `ollama` (default) or `mock`.
- `FOCUS_CATCHER_OLLAMA_URL`: Default is `http://127.0.0.1:11434`.
- `FOCUS_CATCHER_DEFAULT_RUNTIME_PROFILE`: `standard` (`gemma4:e2b`) or `higher_accuracy` (`gemma4:e4b`).
