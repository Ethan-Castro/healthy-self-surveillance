# Architecture

## Core split

- `services/inference` owns session state, local Gemma review orchestration, session artifacts, and rescans.
- `apps/desktop` owns the personal companion UI, local media permissions, preview surfaces, session controls, and the rolling review log.
- `apps/android` remains an older scaffold and is not part of the current v1 consumer flow.

## Inference pipeline

1. Desktop captures local camera and optional screen streams.
2. Renderer sends downscaled stills plus frame sequence metadata to the local FastAPI service.
3. The service uses local `Gemma 4 E2B` through Ollama for live multimodal reviews and slower rescans.
4. The service smooths visible state changes so the companion does not flicker between labels.
5. The store persists:
   - `session.json`
   - `reviews.ndjson`
   - `keyframes/`
   - `rescan.ndjson`
   - `summary.json`

## Upgrade path

- Improve the live capture loop with better change detection and smarter keyframe selection.
- Add richer prompt tuning or a second local reviewer model for rescans.
- Revisit Android only if there is still demand for a paired-device companion after the desktop flow stabilizes.
