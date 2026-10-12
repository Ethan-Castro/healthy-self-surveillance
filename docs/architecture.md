# Architecture

## Core split

- `services/inference` owns session state, local Gemma review orchestration, session artifacts, and rescans.
- `apps/desktop` owns the personal companion UI, local media permissions, preview surfaces, session controls, and the rolling review log.
- `apps/android` remains an older scaffold and is not part of the current v1 consumer flow.

## Inference pipeline

1. Desktop captures local camera and optional screen streams.
2. Renderer sends downscaled stills plus frame sequence metadata to the local FastAPI service.
3. The service uses local `Gemma 4 E2B` through Ollama for live multimodal reviews and slower rescans.
4. The default runtime profile is `standard` (`gemma4:e2b`), with internal support for a `higher_accuracy` profile (`gemma4:e4b`) without exposing raw model selection in the consumer UI.
5. `Qwen 3.5` is kept out of the shipped path and only exercised through an internal benchmark harness.
6. The service smooths visible state changes so the companion does not flicker between labels.
7. The store persists `session.json`, `reviews.ndjson`, `keyframes/`, `rescan.ndjson`, and `summary.json`.
8. After-the-fact review is keyframe-based: the app replays saved moments and rescans, not full continuous footage.

## Upgrade path

- Improve the live capture loop with better change detection and smarter keyframe selection.
- Benchmark `Gemma 4 E4B`, `Qwen 3.5 0.8B`, and `Qwen 3.5 2B` against the same private dataset before changing the shipped default.
- Add richer prompt tuning or a second local reviewer model for rescans only after the baseline Gemma path is stable.
- Revisit Android only if there is still demand for a paired-device companion after the desktop flow stabilizes.
