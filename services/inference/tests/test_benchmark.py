import json

from focus_catcher.benchmark import load_benchmark_dataset, percentile, summarize_model_runs


def test_load_benchmark_dataset_resolves_relative_paths(tmp_path) -> None:
    camera = tmp_path / "camera.jpg"
    camera.write_bytes(b"fake-camera")
    screen = tmp_path / "screen.jpg"
    screen.write_bytes(b"fake-screen")
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "sample-1",
                "camera_path": "camera.jpg",
                "screen_path": "screen.jpg",
                "expected_label": "focused",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    examples = load_benchmark_dataset(dataset)

    assert len(examples) == 1
    assert examples[0].camera_path == camera
    assert examples[0].screen_path == screen
    assert examples[0].expected_label == "focused"


def test_summarize_model_runs_tracks_success_latency_and_accuracy() -> None:
    summary = summarize_model_runs(
        "gemma4:e2b",
        [
            {"example_id": "one", "ok": True, "latency_ms": 500.0, "exact_match": True},
            {"example_id": "two", "ok": True, "latency_ms": 700.0, "exact_match": False},
            {"example_id": "three", "ok": False, "latency_ms": 1500.0, "error": "timeout"},
        ],
    )

    assert summary["status"] == "ok"
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["json_success_rate"] == 0.667
    assert summary["exact_label_accuracy"] == 0.5
    assert summary["latency_ms"]["p50"] == 600.0


def test_percentile_returns_none_for_empty_values() -> None:
    assert percentile([], 95) is None
