# Inference Service

Local FastAPI service for the Focus Buddy desktop app.

Responsibilities:

- verify local `gemma4:e2b` availability through Ollama
- manage consumer session lifecycle
- append live `reviews.ndjson` entries
- save keyframes for label changes and stronger distraction moments
- run slower rescans over saved keyframes
- write `summary.json`

Run locally:

```bash
uv sync
uv run uvicorn focus_catcher.api:app --app-dir src --reload --port 8000
```
