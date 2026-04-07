# Inference Service

Local FastAPI service for the Focus Buddy desktop app.

Responsibilities:

- verify local `gemma4:e2b` availability through Ollama
- optionally verify `gemma4:e4b` for the higher-accuracy internal runtime profile
- manage consumer session lifecycle
- append live `reviews.ndjson` entries
- save keyframes for label changes and stronger distraction moments
- run slower rescans over saved keyframes
- write `summary.json`
- provide an internal benchmark harness for `Gemma 4` and `Qwen 3.5` evaluation without changing the shipped app path

Run locally:

```bash
uv sync
uv run uvicorn focus_catcher.api:app --app-dir src --reload --port 8000
```

Benchmark local models against a private dataset:

```bash
uv run focus-buddy-benchmark /absolute/path/to/focus-benchmark.jsonl
```

Dataset rows are JSONL objects with:

```json
{"id":"focus-001","camera_path":"images/focus-001.jpg","screen_path":"images/focus-001-screen.jpg","expected_label":"focused"}
```
