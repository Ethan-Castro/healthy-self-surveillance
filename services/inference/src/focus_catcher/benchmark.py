from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from urllib import error, request

from .adapters import OllamaGemmaAdapter
from .models import FocusLabel, ReviewInput, SessionConfig, utcnow

DEFAULT_BENCHMARK_MODELS = [
    "gemma4:e2b",
    "gemma4:e4b",
    "qwen3.5:0.8b",
    "qwen3.5:2b",
]


@dataclass(slots=True)
class BenchmarkExample:
    example_id: str
    camera_path: Path
    screen_path: Path | None = None
    expected_label: str | None = None
    description: str | None = None


def load_benchmark_dataset(dataset_path: Path) -> list[BenchmarkExample]:
    base_dir = dataset_path.resolve().parent
    examples: list[BenchmarkExample] = []
    for index, raw_line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        camera_path = _resolve_dataset_path(base_dir, payload["camera_path"])
        screen_path = (
            _resolve_dataset_path(base_dir, payload["screen_path"])
            if payload.get("screen_path")
            else None
        )
        expected_label = payload.get("expected_label")
        if expected_label is not None and expected_label not in {label.value for label in FocusLabel}:
            raise ValueError(f"unexpected expected_label at line {index}: {expected_label}")
        examples.append(
            BenchmarkExample(
                example_id=str(payload.get("id") or f"example-{index}"),
                camera_path=camera_path,
                screen_path=screen_path,
                expected_label=expected_label,
                description=payload.get("description"),
            )
        )
    if not examples:
        raise ValueError("benchmark dataset is empty")
    return examples


def run_ollama_benchmark(
    dataset_path: Path,
    model_names: list[str],
    *,
    base_url: str,
    timeout_sec: float,
    keep_alive: str,
) -> dict[str, object]:
    examples = load_benchmark_dataset(dataset_path)
    available_models = fetch_available_models(base_url)
    model_results: list[dict[str, object]] = []

    for model_name in model_names:
        if model_name not in available_models:
            model_results.append(
                {
                    "model_name": model_name,
                    "status": "missing",
                    "error": f"Model {model_name} is not available in Ollama at {base_url}.",
                }
            )
            continue

        adapter = OllamaGemmaAdapter(
            model_name=model_name,
            base_url=base_url.rstrip("/"),
            timeout_sec=timeout_sec,
            keep_alive=keep_alive,
        )
        runs: list[dict[str, object]] = []

        for index, example in enumerate(examples, start=1):
            config = SessionConfig(include_screen_analysis=example.screen_path is not None)
            review_input = ReviewInput(
                frame_sequence=index,
                camera_image_b64=_image_as_data_url(example.camera_path),
                screen_image_b64=_image_as_data_url(example.screen_path) if example.screen_path else None,
                include_screen_analysis=example.screen_path is not None,
                force_review=True,
            )
            started_at = perf_counter()
            try:
                decision = adapter.review_live(
                    review_input=review_input,
                    config=config,
                    recent_reviews=[],
                    current_label=FocusLabel.FOCUSED.value,
                )
            except Exception as exc:
                latency_ms = round((perf_counter() - started_at) * 1000, 1)
                runs.append(
                    {
                        "example_id": example.example_id,
                        "ok": False,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
                )
                continue

            latency_ms = round((perf_counter() - started_at) * 1000, 1)
            runs.append(
                {
                    "example_id": example.example_id,
                    "ok": True,
                    "latency_ms": latency_ms,
                    "expected_label": example.expected_label,
                    "predicted_label": decision.label.value,
                    "confidence": decision.confidence,
                    "reasons": decision.reasons,
                    "note": decision.note,
                    "exact_match": (
                        None
                        if example.expected_label is None
                        else decision.label.value == example.expected_label
                    ),
                }
            )

        model_results.append(summarize_model_runs(model_name, runs))

    return {
        "generated_at": utcnow().isoformat(),
        "dataset_path": str(dataset_path.resolve()),
        "models": model_results,
    }


def summarize_model_runs(model_name: str, runs: list[dict[str, object]]) -> dict[str, object]:
    latency_values = [float(run["latency_ms"]) for run in runs if run.get("ok")]
    exact_matches = [
        bool(run["exact_match"])
        for run in runs
        if run.get("ok") and run.get("exact_match") is not None
    ]
    success_count = sum(1 for run in runs if run.get("ok"))
    failure_count = len(runs) - success_count

    return {
        "model_name": model_name,
        "status": "ok",
        "examples_total": len(runs),
        "success_count": success_count,
        "failure_count": failure_count,
        "json_success_rate": round(success_count / len(runs), 3) if runs else 0.0,
        "exact_label_accuracy": round(sum(exact_matches) / len(exact_matches), 3)
        if exact_matches
        else None,
        "latency_ms": {
            "mean": round(mean(latency_values), 1) if latency_values else None,
            "p50": percentile(latency_values, 50),
            "p95": percentile(latency_values, 95),
        },
        "runs": runs,
    }


def fetch_available_models(base_url: str) -> set[str]:
    response = request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=5)
    payload = json.loads(response.read().decode("utf-8"))
    return {model["name"] for model in payload.get("models", [])}


def percentile(values: list[float], target: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    index = (len(ordered) - 1) * (target / 100)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    interpolated = ordered[lower] + (ordered[upper] - ordered[lower]) * weight
    return round(interpolated, 1)


def _resolve_dataset_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    resolved = candidate if candidate.is_absolute() else (base_dir / candidate)
    if not resolved.exists():
        raise FileNotFoundError(f"benchmark asset not found: {resolved}")
    return resolved


def _image_as_data_url(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".") or "jpeg"
    if suffix == "jpg":
        suffix = "jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/{suffix};base64,{payload}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run local Focus Buddy VLM benchmarks against an Ollama dataset."
    )
    parser.add_argument("dataset", type=Path, help="JSONL dataset of camera/screen examples.")
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Ollama model name to benchmark. Repeat to benchmark multiple models.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON file to write the benchmark report to.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:11434",
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=45.0,
        help="Per-review timeout in seconds.",
    )
    parser.add_argument(
        "--keep-alive",
        default="10m",
        help="Ollama keep_alive value for each request.",
    )
    args = parser.parse_args()

    try:
        report = run_ollama_benchmark(
            args.dataset,
            args.models or DEFAULT_BENCHMARK_MODELS,
            base_url=args.base_url,
            timeout_sec=args.timeout_sec,
            keep_alive=args.keep_alive,
        )
    except error.URLError as exc:  # pragma: no cover - CLI path
        raise SystemExit(f"Failed to reach Ollama at {args.base_url}: {exc}") from exc

    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":  # pragma: no cover - CLI path
    main()
